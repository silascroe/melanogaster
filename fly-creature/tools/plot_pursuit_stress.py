"""Plot frozen stress evidence; visualization does not select model settings."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

root = Path(__file__).resolve().parents[1]
report = json.loads((root / "docs/evidence/pursuit_stress_v1.json").read_text())
families = ["distance", "speed", "reversal", "heading", "dropout", "reentry"]
colors = plt.get_cmap("tab10").colors
fig, axes = plt.subplots(1, 2, figsize=(13, 5.2), constrained_layout=True)
for i, family in enumerate(families):
    rows = [r for r in report["trials"].values() if r["case"]["family"] == family]
    axes[0].scatter([r["direct_matched"]["active_mean_abs_bearing_deg"] for r in rows],
                    [r["intact"]["active_mean_abs_bearing_deg"] for r in rows],
                    color=colors[i], label=family, s=45, alpha=.85)
maximum = max(max(r[c]["active_mean_abs_bearing_deg"] for c in ("intact", "direct_matched"))
              for r in report["trials"].values() if r["supported"]) * 1.05
axes[0].plot([0, maximum], [0, maximum], "--", color="grey", linewidth=1)
axes[0].set(xlim=(0, maximum), ylim=(0, maximum),
            xlabel="Matched ordinary controller error (degrees)",
            ylabel="Intact connectome controller error (degrees)",
            title="36 supported-task cases: below line favors intact")
axes[0].legend(fontsize=8)
x = np.arange(len(families))
for offset, control, label, color in ((-.25, "intact", "Intact", "#276c91"),
                                     (0, "direct_matched", "Matched ordinary", "#b16b30")):
    axes[1].bar(x + offset, [report["groups"][f]["controllers"][control]["mean_case_error_deg"]
                            for f in families], width=.25, label=label, color=color)
shuffle = [np.mean([r["shuffle_error_deg"]["median"] for r in report["trials"].values()
                    if r["case"]["family"] == f]) for f in families]
axes[1].bar(x + .25, shuffle, width=.25, label="Median shuffled per case", color="#888888")
axes[1].set(xticks=x, xticklabels=families, ylabel="Mean case error (degrees)",
            title="Family means; same sensors, body, delay and turn cap")
axes[1].tick_params(axis="x", labelrotation=25)
axes[1].legend(fontsize=8)
for ax in axes:
    ax.spines[["right", "top"]].set_visible(False)
fig.suptitle("Frozen activity_v1 stress test — model behavior, not measured fly biology", fontsize=12)
for suffix in ("png", "svg"):
    destination = root / f"docs/evidence/pursuit_stress_v1.{suffix}"
    fig.savefig(destination, dpi=150)
    if suffix == "svg":
        destination.write_text("\n".join(line.rstrip() for line in destination.read_text(encoding="utf-8").splitlines()) + "\n", encoding="utf-8")
print("Saved pursuit stress comparison charts")
