"""Check actual Godot service snapshots, UI checks and encoded preview."""
import json
from pathlib import Path
import subprocess
from statistics import mean

from fly_creature.playground import PlaygroundSession

root = Path(__file__).resolve().parents[1]
output = root / "outputs/playground"
log = (output / "playground.log").read_text(encoding="utf-8")
checklog = (output / "playground_check.log").read_text(encoding="utf-8")
assert "ERROR:" not in log and "ERROR:" not in checklog
ui = [json.loads(line.split("PLAYGROUND_UI_CHECK ", 1)[1]) for line in checklog.splitlines()
      if line.startswith("PLAYGROUND_UI_CHECK ")][-1]
assert ui["passed"] and all(ui[k] for k in ("pause", "mouse_drag", "inflight_reset", "sliders", "mirror", "keyboard_pause"))
snapshots = [json.loads(line.split("PLAYGROUND_SNAPSHOT ", 1)[1]) for line in log.splitlines()
             if line.startswith("PLAYGROUND_SNAPSHOT ")]
assert snapshots[0]["tick"] == 0 and snapshots[-1]["tick"] >= 800
previous = snapshots[0]
for snapshot in snapshots[1:]:
    assert snapshot["sequence"] == previous["sequence"] + 1
    assert 1 <= snapshot["tick"] - previous["tick"] <= 5
    for body in snapshot["models"].values():
        assert body["steering"]["model_time_ms"] == snapshot["tick"] * 10
    previous = snapshot
last = snapshots[-1]
world = PlaygroundSession({"preset": "gentle"})
sequence = 0
while world.tick < last["tick"]:
    sequence += 1
    expected = world.step({"sequence": sequence, "ticks": min(5, int(last["tick"]) - world.tick)})
for name, actual in last["models"].items():
    e = expected["models"][name]
    assert abs(actual["mean_error_deg"] - e["mean_error_deg"]) < 1e-9
    for key in ("x", "z", "heading_rad"):
        assert abs(actual[key] - e[key]) < 1e-9
assert last["models"]["disconnected"]["steering"]["turn_rate_rad_s"] == 0
probe = Path(r"C:\Users\ringd\.codex\tools\ffmpeg\ffmpeg-9.0.2-essentials_build\bin\ffprobe.exe")
video = json.loads(subprocess.check_output([str(probe), "-v", "error", "-select_streams", "v:0",
    "-show_entries", "stream=width,height,r_frame_rate,duration,nb_frames", "-of", "json",
    str(output / "playground.mp4")], text=True))["streams"][0]
assert (video["width"], video["height"], video["r_frame_rate"]) == (1920, 1080, "60/1")
report = {"passed": True, "godot": "4.7.stable", "ui": ui,
          "snapshot_count": len(snapshots), "final_tick": last["tick"],
          "final_mean_errors_deg": {n: b["mean_error_deg"] for n, b in last["models"].items()},
          "mean_compute_ms": mean(s.get("compute_ms", 0) for s in snapshots[1:]),
          "mean_roundtrip_ms": mean(s["roundtrip_ms"] for s in snapshots[1:]),
          "video": video, "preview_scope": "Existing gentle trajectory, integration evidence only"}
(root / "docs/evidence/playground_v1.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
