"""Check frozen hashes and recompute fresh scores from local CSV traces."""
import csv
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
report = json.loads((root / "docs/evidence/pursuit_motion_v1.json").read_text())
for name, expected in report["input_sha256"].items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
frozen = json.loads((root / "docs/evidence/pursuit_stress_v1.json").read_text())
for name, row in report["old_cases"].items():
    assert all(row["baseline"][k] == v for k, v in frozen["trials"][name]["intact"].items()), name
count = 0
for name, controls in report["fresh_cases"].items():
    for control in report["shuffle_errors"]:
        path = root / f"outputs/research/pursuit_motion/{name}_{control}.csv"
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 1000
        assert all(abs(float(r["t_s"]) - (i + 1) * .01) < 1e-12 for i, r in enumerate(rows))
        active = [r for r in rows if r["active"] == "True"]
        error = round(sum(abs(float(r["bearing_deg"])) for r in active) / len(active), 6)
        assert error == controls[control]["active_mean_abs_bearing_deg"]
        assert sum(r["visible"] == "True" for r in active) / len(active) == controls[control]["active_in_view_fraction"]
        assert sum(abs(float(r["turn_rate_rad_s"])) >= 1.2 - 1e-10 for r in rows) / 1000 == controls[control]["turn_cap_fraction"]
        count += 1
for control, summary in report["fresh_summary"].items():
    aggregate = sum(r[control]["active_mean_abs_bearing_deg"] for r in report["fresh_cases"].values()) / 12
    assert abs(aggregate - summary["mean_error_deg"]) < 1e-12
    assert sum(r[control]["within_envelope"] for r in report["fresh_cases"].values()) == summary["envelope_cases"]
    if control in report["shuffle_errors"]:
        aggregates = [sum(r.values()) / 12 for r in report["shuffle_errors"][control]]
        assert all(abs(a - b) < 1e-12 for a, b in zip(aggregates, summary["shuffle_aggregate_errors"]))
        assert sum(aggregate < value for value in aggregates) == summary["beats_shuffle_aggregates"]
assert report["production_changed"] is False
print(f"48 baseline cases, {count} fresh traces, hashes and aggregates verified")
