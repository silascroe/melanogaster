"""Verify actual rendered Godot ticks, queued commands and encoded video metadata."""
import json
import math
from pathlib import Path
import subprocess

from fly_creature.pursuit_activity import ActivityProjection
from fly_creature.pursuit_delay_diagnostic import DECLARED, overlap_adapter, simulate
from fly_creature.pursuit_step4 import ActivityAdapter

root = Path(__file__).resolve().parents[1]
output = root / "outputs/pursuit_activity"
probe = Path(r"C:\Users\ringd\.codex\tools\ffmpeg\ffmpeg-9.0.2-essentials_build\bin\ffprobe.exe")
model = overlap_adapter(ActivityAdapter.build(ActivityProjection.from_packaged_data()), 15)
report = {"scope": "Godot integration replay of already evaluated harmonic path, not new generalization evidence",
          "godot": "4.7.stable", "model": "activity_v1", "trials": {}}
for condition in ("intact", "disconnected"):
    stem = output / f"activity_{condition}"
    log = stem.with_suffix(".log").read_text(encoding="utf-8")
    if "ERROR:" in log or "SCRIPT ERROR" in log:
        raise AssertionError("Godot errors")
    ticks = [json.loads(line.split("PURSUIT_TICK ", 1)[1]) for line in log.splitlines()
             if line.startswith("PURSUIT_TICK ")]
    assert len(ticks) == 800, len(ticks)
    queue_error = 0.0
    for i, tick in enumerate(ticks):
        s = tick["steering"]
        assert tick["model"] == s["model"] == "activity_v1"
        assert s["model_time_ms"] == (i + 1) * 10
        assert abs(tick["time_s"] - (i + 1) * .01) < 1e-8
        assert tick["condition"] == condition
        assert abs(tick["facing_travel_dot"] - 1.0) < 1e-6, tick["facing_travel_dot"]
        expected = 0.0 if i < 20 else max(-1.2, min(1.2,
            math.radians(.65 * ticks[i - 20]["steering"]["right_minus_left_activity"]) / .01))
        queue_error = max(queue_error, abs(s["turn_rate_rad_s"] - expected))
    assert queue_error < 1e-10, queue_error
    error = sum(abs(t["steering"]["bearing_deg"]) for t in ticks) / len(ticks)
    expected_error = simulate("harmonic", model, DECLARED, fresh=True,
                             condition="intact" if condition == "intact" else "bridge_removed")["mean_abs_bearing_deg"]
    assert abs(error - expected_error) < .01, (error, expected_error)
    if condition == "disconnected":
        assert all(t["steering"]["turn_rate_rad_s"] == 0 and t["heading_rad"] == 0 for t in ticks)
    metadata = json.loads(subprocess.check_output([str(probe), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,nb_frames,duration", "-of", "json",
        str(stem.with_suffix(".mp4"))], text=True))["streams"][0]
    assert (metadata["width"], metadata["height"], metadata["r_frame_rate"]) == (1920, 1080, "60/1"), metadata
    report["trials"][condition] = {"ticks": len(ticks), "simulation_seconds": ticks[-1]["time_s"],
        "mean_abs_bearing_deg": round(error, 6), "offline_mean_abs_bearing_deg": expected_error,
        "max_motor_queue_error_rad_s": queue_error, "final_heading_rad": ticks[-1]["heading_rad"],
        "nonzero_turn_ticks": sum(t["steering"]["turn_rate_rad_s"] != 0 for t in ticks),
        "min_facing_travel_dot": min(t["facing_travel_dot"] for t in ticks),
        "video": metadata, "errors": 0}
report["passed"] = True
destination = root / "docs/evidence/godot_pursuit_activity_v1.json"
destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
