"""Render the controlled motion/delay ablations, without fitting anything."""
import json
import os
from pathlib import Path
root = Path(__file__).resolve().parents[1]
cache = root / "outputs/research/matplotlib-cache"
cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(cache))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

r = json.loads((root / "docs/evidence/pursuit_motion_v1.json").read_text())
fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
names = ["baseline", "position_only", "reversed_direction", "target_only", "continuous_visible", "zero_delay"]
labels = ["Current", "No direction rule", "Reversed rule", "Target-only oracle", "Visibility history", "No motor delay"]
values = [r["old_cases"]["speed_3"][n]["active_mean_abs_bearing_deg"] for n in names]
axes[0].barh(labels, values, color=["#217a88", "#d18a29", "#a94e52", "#777777", "#777777", "#557ca4"])
axes[0].invert_yaxis()
axes[0].axvline(10, color="black", linestyle="--", label="Declared error limit")
axes[0].set(title="Fastest old stress case (one-factor changes)", xlabel="Mean absolute target bearing (degrees)")
axes[0].legend(fontsize=8)
names = ["baseline", "position_only", "disconnected", "ordinary_delayed", "ordinary_immediate"]
labels = ["Current", "No direction rule", "Disconnected", "Ordinary / 200 ms", "Ordinary / 0 ms"]
values = [r["fresh_summary"][n]["mean_error_deg"] for n in names]
axes[1].barh(labels, values, color=["#217a88", "#d18a29", "#a94e52", "#557ca4", "#6b8b48"])
for i, name in enumerate(names[:2]):
    shuffles = r["fresh_summary"][name]["shuffle_aggregate_errors"]
    axes[1].plot([min(shuffles), max(shuffles)], [i, i], color="black", linewidth=2)
    axes[1].scatter([np.median(shuffles)], [i], color="black", marker="|", s=110)
axes[1].invert_yaxis()
axes[1].set(title="12 fresh fast/mixed-motion cases", xlabel="Mean case error (degrees)")
fig.suptitle("Motion rule helps gentle tracking; imposed motor delay limits fast tracking\nBlack ranges: 32 wiring shuffles under the same direction condition", fontsize=12)
fig.savefig(root / "docs/evidence/pursuit_motion_v1.png", dpi=160)
fig.savefig(root / "docs/evidence/pursuit_motion_v1.svg")
svg = root / "docs/evidence/pursuit_motion_v1.svg"
svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
