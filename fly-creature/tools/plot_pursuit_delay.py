"""Plot the frozen diagnostic's local traces. Requires matplotlib, not runtime."""
import json
import os
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(root / "outputs/research/matplotlib-cache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

traces = root / "outputs/research/pursuit_delay_traces"
fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True, constrained_layout=True)
conditions = (
    ("visual450_motor0_overlap0", "450 ms history, hard hemisphere", "#ab4338"),
    ("visual450_motor0_overlap15", "450 ms history, overlap", "#bb823b"),
    ("visual0_motor200_overlap0", "200 ms motor, hard hemisphere", "#567da0"),
    ("visual0_motor200_overlap15", "200 ms motor, overlap", "#267568"),
)
for ax, prefix, title in zip(axes, ("walking", "pivot"), ("Walking body", "Rotation only (no forward movement)")):
    ax.axhspan(-10, 10, color="#e9ecef", label="Settling band (+/-10 degrees)")
    ax.axvline(2, color="#777777", linestyle=":", linewidth=1)
    for name, label, color in conditions:
        data = json.loads((traces / f"{name}_{prefix}_step_hold.json").read_text())
        ax.plot([r["t_s"] for r in data], [r["bearing_deg"] for r in data],
                label=label, color=color, linewidth=1.4)
    ax.set_title(title)
    ax.set_ylabel("Target bearing (degrees)")
    ax.grid(alpha=.2)
axes[0].legend(loc="upper right", fontsize=8)
axes[1].set_xlabel("Time (seconds); target jumps at 2 s")
fig.suptitle("Pursuit diagnosis: shorter feedback delay + smooth center input\nFixed circuit, gain, field width, and turn cap; synthetic target steps", fontsize=12)
output = root / "docs/evidence/pursuit_delay_v1"
fig.savefig(output.with_suffix(".png"), dpi=160)
fig.savefig(output.with_suffix(".svg"))
svg = output.with_suffix(".svg")
svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines()) + "\n",
               encoding="utf-8")
print(output.with_suffix(".png"))
