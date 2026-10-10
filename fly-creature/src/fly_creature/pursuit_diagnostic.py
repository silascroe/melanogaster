"""Closed-loop moving-target comparison for the engineered pursuit slice."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from .steering import SteeringSession
from .steering_diagnostic import load_candidate


DT_S = 0.05
FRAMES = 160
WALK_SPEED = 0.55
SCENARIOS = {
    "crossing": (0.62, 1.0),
    "mirrored_crossing": (0.62, -1.0),
    "faster_crossing": (0.90, 1.0),
}


def run() -> dict:
    circuit = load_candidate()
    results = {}
    for scenario, (frequency, direction) in SCENARIOS.items():
        results[scenario] = {}
        for condition in ("intact", "disconnected", "AOTU019_output_removed",
                          "AOTU025_output_removed"):
            session = SteeringSession(circuit, condition=condition)
            x = z = heading = turn_rate = 0.0
            frames = []
            for frame in range(FRAMES):
                t = frame * DT_S
                heading = math.atan2(math.sin(heading + turn_rate * DT_S),
                                     math.cos(heading + turn_rate * DT_S))
                x += math.sin(heading) * WALK_SPEED * DT_S
                z -= math.cos(heading) * WALK_SPEED * DT_S
                target = {"x": direction * 3.2 * math.sin(t * frequency - 1.2),
                          "z": -6.5, "active": True}
                trace = session.step({"x": x, "z": z, "heading_rad": heading}, target, 50)
                turn_rate = trace["turn_rate_rad_s"]
                frames.append({"time_s": round(t, 2), "fly_x": round(x, 4),
                               "fly_z": round(z, 4),
                               "heading_deg": round(math.degrees(heading), 2),
                               "target_x": round(target["x"], 4),
                               "bearing_deg": trace["bearing_deg"],
                               "DNa02_right_minus_left_mv": trace["right_minus_left_mv"],
                               "turn_rate_rad_s": turn_rate})
            results[scenario][condition] = {
                "mean_absolute_bearing_deg": round(sum(abs(row["bearing_deg"]) for row in frames)
                                                   / len(frames), 3),
                "final_absolute_bearing_deg": abs(frames[-1]["bearing_deg"]),
                "max_absolute_heading_deg": round(max(abs(row["heading_deg"])
                                                      for row in frames), 3),
                "frames": frames,
            }
    return {"protocol": {"frames": FRAMES, "dt_s": DT_S, "walk_speed_m_s": WALK_SPEED,
                         "targets": {name: f"x={direction}*3.2*sin({frequency}*t-1.2), z=-6.5"
                                     for name, (frequency, direction) in SCENARIOS.items()},
                         "conditions": "intact, both AOTU-to-DNa02 branches removed, "
                                       "or each branch output removed alone"},
            "conditions": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({scenario: {condition: {
        name: value for name, value in row.items() if name != "frames"
    } for condition, row in trials.items()}
        for scenario, trials in result["conditions"].items()}, indent=2))


if __name__ == "__main__":
    main()
