"""Read-only source/runtime timing audit; no controller tuning or model edits."""
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import re

from fly_creature.pursuit_controller import ActivitySteeringSession
from fly_creature.pursuit_step4 import AUTHOR_GAIN, DT, MAX_TURN_RATE
from fly_creature.pursuit_stress import Case
from fly_creature.pursuit_motion_diagnostic import fresh_cases
from fly_creature.steering import target_feature

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "outputs/research/CollieWilson"
PAPER = "https://wilson.hms.harvard.edu/sites/g/files/omnuum8421/files/2026-03/Collie%202026.pdf"


def source_record(path, patterns):
    text = path.read_text()
    matches = [{"line": i + 1, "matched_patterns": [p for p in patterns if re.search(p, line)]}
               for i, line in enumerate(text.splitlines())
               if any(re.search(pattern, line) for pattern in patterns)]
    return {"path": str(path.relative_to(SOURCE)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "matches": matches}


def activity_command(adapter, feature):
    bearing, motion = feature
    result = adapter.activity_at(bearing, motion)
    requested = math.radians(AUTHOR_GAIN * result["signal"]) / DT
    return max(-MAX_TURN_RATE, min(MAX_TURN_RATE, requested))


def placement_equivalence():
    session = ActivitySteeringSession()
    adapter = session.adapter
    features, actual = [], []
    previous = None
    fly = {"x": 0., "z": 0., "heading_rad": 0.}
    for i in range(600):
        angle = 50 * math.sin(2.7 * (i + 1) * DT) + 20 * math.sin(5.1 * (i + 1) * DT)
        target = {"x": 6 * math.sin(math.radians(angle)),
                  "z": -6 * math.cos(math.radians(angle)), "active": True}
        output = session.step(fly, target, 10)
        bearing = output["bearing_deg"]
        features.append((bearing, bearing - previous if previous is not None else 0.))
        previous = bearing
        actual.append(output["turn_rate_rad_s"])
    splits = {}
    for sensory, motor in ((0, 20), (4, 16), (10, 10), (20, 0)):
        # Warm-up is missing input, not a fictitious centered target. Both
        # bearing and its direction feature retain their original timestamp.
        queue = deque()
        outputs = []
        for i in range(len(features)):
            command = activity_command(adapter, features[i - sensory]) if i >= sensory else 0.
            queue.append(command)
            outputs.append(queue.popleft() if len(queue) > motor else 0.)
        difference = max(abs(a - b) for a, b in zip(actual, outputs))
        assert difference < 1e-12
        splits[f"sensory_{sensory * 10}_motor_{motor * 10}"] = difference
    return {"visible_active_samples": len(actual), "max_abs_turn_difference_rad_s": splits,
            "scope": "Static adapter; same feature timestamps, total delay, warm-up and cap. No hide/reset transitions."}


def runtime_timestamp_probe():
    session = ActivitySteeringSession()
    fly = {"x": 0., "z": 0., "heading_rad": 0.}
    target = {"x": 2., "z": -6., "active": True}
    delivered = None
    heading = turn = 0.
    first_heading = None
    for tick in range(1, 30):
        # Same order as the frozen body loop; keep sensor input clamped to
        # isolate sample/queue/delivery rather than closed-loop dynamics.
        heading += turn * DT
        if heading != 0 and first_heading is None:
            first_heading = tick * 10
        out = session.step(fly, target, 10)
        turn = out["turn_rate_rad_s"]
        if turn != 0 and delivered is None:
            delivered = tick * 10
    assert delivered == 210 and first_heading == 220
    return {"first_sensor_sample_ms": 10, "first_nonzero_delivered_command_ms": delivered,
            "first_changed_heading_sample_ms": first_heading,
            "sensor_to_command_queue_ms": delivered - 10,
            "sensor_to_changed_heading_sample_ms": first_heading - 10,
            "interpretation": "Next body interval is sampled at its endpoint. Not evidence to shorten the queue by one tick."}


def independent_motion(case):
    previous = None
    speeds = []
    for tick in range(1001):
        t = tick * DT
        bearing = target_feature({"x": 0., "z": -.55 * t, "heading_rad": 0.}, case.target(t))["bearing_deg"]
        if previous is not None:
            speeds.append(abs(bearing - previous) / DT)
        previous = bearing
    return {"mean_abs_deg_s": sum(speeds) / len(speeds), "peak_abs_deg_s": max(speeds)}


def run():
    manifest = json.loads((ROOT / "docs/evidence/pursuit_reference_source_v1.json").read_text())
    assert manifest["commit"] == "65d72773121ffe148b56b8ba4f594a7a51c51789"
    for relative, expected in manifest["sha256"].items():
        assert hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() == expected, relative
    records = [
        source_record(SOURCE / "Modeling_Code/support/modelSettings.m",
                      [r"runSettings\.(fs|visuomotor_delay|AOTU019_delay|Others_delay)\s*="]),
        source_record(SOURCE / "Modeling_Code/aotu_steering_model.m",
                      [r"delay_AOTU019 =", r"delay_Others =", r"t_AOTU019 =", r"t_Others =", r"visobj_history\(:, t\) = visobj_history\(:, t\)", r"dt = 2 / fs"]),
        source_record(SOURCE / "Modeling_Code/support/analyzeErrorVsTurn.m",
                      [r"visuomotor_delay", r"circshift"]),
        source_record(SOURCE / "Data_Analysis_Code/data processing/calculate_visualresponselatency.m",
                      [r"max\(dFiringRate\)", r"latency_threshold =", r"selected_time\(peak_idx\)"]),
    ]
    paths = [ROOT / "src/fly_creature/pursuit_controller.py",
             ROOT / "src/fly_creature/pursuit_step4.py", ROOT / "src/fly_creature/playground.py",
             ROOT / "godot/main.gd", Path(__file__)]
    payload = {"audit_date": "2026-10-02", "author_revision": "65d72773121ffe148b56b8ba4f594a7a51c51789",
        "final_paper": {"url": PAPER, "local_copy_saved": False,
            "retrieval_note": "Read full final article via web PDF extraction; direct download denied by host.",
            "anchors": {"visual_response_latency": "PDF page 5, Figure 3D; 40 +/-9 and 36 +/-10 ms",
                "latency_definition": "PDF page 22, e6; firing-rate derivative peak",
                "feedback_delay": "PDF page 24, e8; Equation 6 and preceding paragraph, 200 ms",
                "analysis_filtering": "PDF pages 21-22, e5-e6; post hoc smoothing is not a causal neural time constant"}},
        "source_records": records, "pinned_manifest_hashes_verified": len(manifest["sha256"]),
        "runtime_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        "delay_placement_equivalence": placement_equivalence(),
        "runtime_timestamps": runtime_timestamp_probe(),
        "independent_target_motion": {c.name: independent_motion(c) for c in
            [Case("speed", s) for s in (.35, 1.7, 3)] + [Case("reversal", 2)] +
            [c for c in fresh_cases() if not c.mirror]},
        "production_changed": False}
    output = ROOT / "docs/evidence/pursuit_timing_audit_v1.json"
    output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"delay_placement": payload["delay_placement_equivalence"],
                      "runtime_timestamps": payload["runtime_timestamps"],
                      "independent_motion": payload["independent_target_motion"]}, indent=2))


if __name__ == "__main__":
    run()
