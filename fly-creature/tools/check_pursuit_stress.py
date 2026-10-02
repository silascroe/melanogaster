"""Independently recompute recorded scores and check the frozen input hashes."""
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median

root = Path(__file__).resolve().parents[1]
report = json.loads((root / "docs/evidence/pursuit_stress_v1.json").read_text())
for name, expected in report["input_sha256"].items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
assert len(report["trials"]) == 48
assert sum(r["supported"] for r in report["trials"].values()) == 36
assert len(report["shuffle_case_errors_deg"]) == 32
assert report["direct_gain"] == float(min(report["calibration_old_paths"],
    key=lambda k: (report["calibration_old_paths"][k], float(k))))
checked = 0
for name, result in report["trials"].items():
    for control, suffix in (("intact", "intact"), ("direct_matched", "direct")):
        with (root / f"outputs/research/pursuit_stress/{name}_{suffix}.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 1000
        for tick, row in enumerate(rows):
            assert abs(float(row["t_s"]) - (tick + 1) * .01) < 1e-10
            for key in ("fly_x", "fly_z", "heading_deg", "target_x", "target_z",
                        "distance_m", "bearing_deg", "turn_rate_rad_s"):
                assert math.isfinite(float(row[key])), (name, key)
            assert abs(float(row["turn_rate_rad_s"])) <= 1.2
            geometric_visibility = row["active"] == "True" and .4 <= float(row["distance_m"]) <= 9 and abs(float(row["bearing_deg"])) <= 120
            assert (row["visible"] == "True") == geometric_visibility
        active = [row for row in rows if row["active"] == "True"]
        metrics = result[control]
        assert abs(mean(abs(float(row["bearing_deg"])) for row in active) - metrics["active_mean_abs_bearing_deg"]) < 1e-6
        assert sum(row["visible"] == "True" for row in active) / len(active) == metrics["active_in_view_fraction"]
        assert sum(abs(float(row["turn_rate_rad_s"])) >= 1.2 - 1e-10 for row in rows) / 1000 == metrics["turn_cap_fraction"]
        assert sum(row["active"] != "True" and float(row["turn_rate_rad_s"]) != 0 for row in rows) == metrics["inactive_turn_ticks"] == 0
        if result["case"]["family"] in ("dropout", "reentry"):
            returned = 4 + float(result["case"]["level"])
            consecutive = 0
            completion = None
            for row in rows:
                if float(row["t_s"]) >= returned:
                    consecutive = consecutive + 1 if row["visible"] == "True" and abs(float(row["bearing_deg"])) <= 10 else 0
                    if consecutive == 50 and completion is None:
                        completion = round(float(row["t_s"]) - returned, 3)
            assert completion == metrics["reacquisition_s"]
        assert metrics["within_envelope"] == all(metrics["envelope_components"].values())
        checked += 1
    assert result["disconnected"]["mean_abs_turn_rad_s"] == 0
    assert result["shuffle_error_deg"]["median"] == median(s[name] for s in report["shuffle_case_errors_deg"])
for group, summary in report["groups"].items():
    selected = [r for r in report["trials"].values() if (r["supported"] if group == "supported" else
                not r["supported"] if group == "challenge" else r["case"]["family"] == group)]
    for control, values in summary["controllers"].items():
        assert abs(mean(r[control]["active_mean_abs_bearing_deg"] for r in selected) - values["mean_case_error_deg"]) < 1e-10
        assert sum(r[control]["within_envelope"] for r in selected) == values["within_envelope"]
print(f"Checked frozen hashes, {checked} full traces, scores, visibility, recovery, disconnection and aggregates")
