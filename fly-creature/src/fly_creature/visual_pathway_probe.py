"""Fixed-fly LC10a -> AOTU -> DNa02 position and motion-pulse probe.

The visual feature is engineered. This probe observes the selected circuit's
internal responses under fixed input rules; it is not fly physiology.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from html import escape
import json
import math
from pathlib import Path
from statistics import mean, median

from .steering import SteeringSession
from .steering_diagnostic import load_candidate
from .visual_input_experiment import load_map, shuffle_lc_wiring, SHUFFLE_SEEDS


STEP_MS = 20
BASELINE_MS = 100
PULSE_MS = 400
DISTANCE_M = 6.0
HALF_SWEEP_DEG = 5.0
CENTERS_DEG = (12, 25, 40, 55)
SIDES = ("L", "R")
MOTIONS = ("static", "outward", "inward")
REGIMES = ("matched_current", "playable_envelope")


def target(side: str, angle_deg: float, *, active: bool = True) -> dict:
    sign = -1 if side == "L" else 1
    angle = math.radians(angle_deg)
    return {"x": sign * DISTANCE_M * math.sin(angle),
            "z": -DISTANCE_M * math.cos(angle), "active": active}


def angle_for(center: int, motion: str, frame: int) -> float:
    if motion == "static":
        return float(center)
    fraction = (frame + 0.5) / (PULSE_MS // STEP_MS)
    if motion == "outward":
        return center - HALF_SWEEP_DEG + 2 * HALF_SWEEP_DEG * fraction
    if motion == "inward":
        return center + HALF_SWEEP_DEG - 2 * HALF_SWEEP_DEG * fraction
    raise ValueError(f"Unknown motion: {motion}")


def trial(circuit, centers: dict[int, float] | None, *, side: str,
          center: int, motion: str, regime: str) -> dict:
    session = SteeringSession(circuit, visual_centers_deg=centers)
    fly = {"x": 0.0, "z": 0.0, "heading_rad": 0.0}
    inactive = target(side, center, active=False)
    for _ in range(BASELINE_MS // STEP_MS):
        session.step(fly, inactive, STEP_MS)
    bins = []
    side_sign = -1 if side == "L" else 1
    for frame in range(PULSE_MS // STEP_MS):
        angle = angle_for(center, motion, frame)
        trace = session.step(
            fly, target(side, angle), STEP_MS,
            record_cells=True,
            input_strength_override=1.0 if regime == "matched_current" else None,
        )
        bins.append({
            "time_ms": (frame + 1) * STEP_MS,
            "angle_deg": round(angle, 3),
            "input_strength": trace["input_strength"][side],
            "LC10a_spikes": trace["LC10a_spikes"][side],
            "AOTU019_spikes": trace["AOTU_spikes"]["AOTU019"][side],
            "AOTU025_spikes": trace["AOTU_spikes"]["AOTU025"][side],
            "AOTU019_mean_mv": trace["AOTU_mean_mv"]["AOTU019"][side],
            "AOTU025_mean_mv": trace["AOTU_mean_mv"]["AOTU025"][side],
            "DNa02_toward_bias_mv": round(side_sign * trace["right_minus_left_mv"], 4),
            "DNa02_spikes": trace["DNa02_spikes"]["L"] + trace["DNa02_spikes"]["R"],
            "toward_turn_rate_rad_s": round(side_sign * trace["turn_rate_rad_s"], 4),
        })
    summary = {
        "mean_input_strength": round(mean(row["input_strength"] for row in bins), 4),
        "LC10a_spikes": sum(row["LC10a_spikes"] for row in bins),
        "AOTU019_spikes": sum(row["AOTU019_spikes"] for row in bins),
        "AOTU025_spikes": sum(row["AOTU025_spikes"] for row in bins),
        "AOTU019_mean_mv": round(mean(row["AOTU019_mean_mv"] for row in bins), 4),
        "AOTU025_mean_mv": round(mean(row["AOTU025_mean_mv"] for row in bins), 4),
        "DNa02_toward_bias_mv": round(mean(row["DNa02_toward_bias_mv"] for row in bins), 4),
        "DNa02_spikes": sum(row["DNa02_spikes"] for row in bins),
        "toward_turn_rate_rad_s": round(mean(row["toward_turn_rate_rad_s"] for row in bins), 4),
    }
    # Keep the probe artifact compact. Per-step values are used to calculate
    # these summaries and can be regenerated; no bulky timestep trace is saved.
    return {"summary": summary}


def run() -> dict:
    circuit = load_candidate()
    centers, mapping = load_map(circuit)
    shuffled = {seed: shuffle_lc_wiring(circuit, seed) for seed in SHUFFLE_SEEDS}
    results = {}
    for regime in REGIMES:
        for side in SIDES:
            for center in CENTERS_DEG:
                for motion in MOTIONS:
                    key = f"{regime}:{side}:{center}:{motion}"
                    uniform = trial(circuit, None, side=side, center=center,
                                    motion=motion, regime=regime)
                    anatomy = trial(circuit, centers, side=side, center=center,
                                    motion=motion, regime=regime)
                    uniform_shuffled = trial(shuffled[101], None, side=side,
                                             center=center, motion=motion, regime=regime)
                    if uniform["summary"] != uniform_shuffled["summary"]:
                        raise RuntimeError(f"Uniform-input shuffle changed response: {key}")
                    metrics = ("AOTU019_spikes", "AOTU025_spikes",
                               "DNa02_toward_bias_mv", "toward_turn_rate_rad_s")
                    shuffled_summaries = {}
                    for seed, candidate in shuffled.items():
                        row = trial(candidate, centers, side=side, center=center,
                                    motion=motion, regime=regime)["summary"]
                        shuffled_summaries[str(seed)] = {
                            metric: row[metric] for metric in metrics
                        }
                    shuffle_median = {
                        metric: round(median(row[metric] for row in shuffled_summaries.values()), 4)
                        for metric in metrics
                    }
                    results[key] = {
                        "uniform": uniform,
                        "anatomy": anatomy,
                        "shuffled_median": shuffle_median,
                        "shuffled_seeds": shuffled_summaries,
                    }
    return {
        "question": "Does provisional per-cell LC10a input separate frontal/lateral and inward/outward AOTU responses?",
        "circuit": {"neurons": len(circuit.neurons),
                    "edges": len(circuit.connections),
                    "anatomy_map_skeleton_digest": mapping["sources"]["ordered_skeleton_sha256"]},
        "protocol": {
            "fly": "fixed at x=z=heading=0; no feedback or movement",
            "target_distance_m": DISTANCE_M,
            "side": list(SIDES), "centers_deg": list(CENTERS_DEG),
            "motion": "400 ms pulse: static or 10 degree azimuth sweep at 25 deg/s; "
                      "outward and inward visit the same angles in reverse order",
            "baseline_ms": BASELINE_MS, "pulse_ms": PULSE_MS,
            "world_step_ms": STEP_MS, "neural_step_ms": 1,
            "matched_current": "Override bearing-amplitude envelope with full current inside the original view gate; "
                               "isolate anatomical distribution at equal total input.",
            "playable_envelope": "Use the existing bearing-amplitude envelope, still with a fixed fly.",
            "conditions": "uniform, anatomy, 12 within-side LC10a output-bundle shuffles; "
                          "uniform shuffle must equal uniform intact.",
            "AOTU_spikes": "Counts from one recorded AOTU019 or AOTU025 cell on the stimulated side, "
                           "per 400 ms pulse; modeled spikes, not measured firing.",
            "DNa02_toward_bias_mv": "Mean DNa02 voltage difference signed toward the target side; "
                                        "positive requests a turn toward the target under the engineered decoder.",
        },
        "results": results,
    }


def write_csv(payload: dict, output: Path) -> None:
    import csv
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("regime", "side", "center_deg", "motion", "condition",
                         "mean_input_strength", "LC10a_spikes", "AOTU019_spikes",
                         "AOTU025_spikes", "DNa02_toward_bias_mv", "DNa02_spikes",
                         "toward_turn_rate_rad_s"))
        for key, conditions in payload["results"].items():
            regime, side, center, motion = key.split(":")
            for condition in ("uniform", "anatomy"):
                row = conditions[condition]["summary"]
                writer.writerow((regime, side, center, motion, condition,
                                 row["mean_input_strength"], row["LC10a_spikes"],
                                 row["AOTU019_spikes"], row["AOTU025_spikes"],
                                 row["DNa02_toward_bias_mv"], row["DNa02_spikes"],
                                 row["toward_turn_rate_rad_s"]))
            row = conditions["shuffled_median"]
            writer.writerow((regime, side, center, motion, "shuffled_median",
                             "", "", row["AOTU019_spikes"], row["AOTU025_spikes"],
                             row["DNa02_toward_bias_mv"], "", row["toward_turn_rate_rad_s"]))


def write_chart(payload: dict, output: Path, regime: str) -> None:
    """Render a small self-contained SVG without a plotting dependency."""
    width, height = 1430, 550
    margin_left, panel_width, gap = 75, 390, 65
    top, plot_height = 165, 255
    metrics = (("AOTU019_spikes", "AOTU019 modeled spikes", "spikes / 400 ms"),
               ("AOTU025_spikes", "AOTU025 modeled spikes", "spikes / 400 ms"),
               ("DNa02_toward_bias_mv", "DNa02 toward-side voltage", "mV difference"))
    colors = {"uniform": "#526176", "anatomy": "#008c82",
              "shuffled_median": "#d58130"}
    chunks = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" '
              f'aria-label="Fixed-fly neural pathway responses under {escape(regime)}">',
              '<rect width="100%" height="100%" fill="#f7f9f9"/>',
              '<style>text{font-family:Arial,sans-serif;fill:#26323d}.small{font-size:14px}.title{font-size:24px;font-weight:bold}.panel{font-size:19px;font-weight:bold}</style>',
              f'<text x="65" y="42" class="title">LC10a visual-pathway probe — {escape(regime.replace("_", " "))}</text>',
              '<text x="65" y="70" class="small">Fixed fly · right-side target · 400 ms pulse · solid outward, dashed inward</text>']
    for panel, (metric, label, unit) in enumerate(metrics):
        left = margin_left + panel * (panel_width + gap)
        values = []
        for center in CENTERS_DEG:
            for motion in ("outward", "inward"):
                trial_result = payload["results"][f"{regime}:R:{center}:{motion}"]
                for condition in colors:
                    row = trial_result[condition]
                    value = row["summary"][metric] if condition != "shuffled_median" else row[metric]
                    values.append(value)
        y_max = max(values) * 1.12 if max(values) > 0 else 1.0
        y_min = min(0.0, min(values))
        if y_min < 0:
            y_min *= 1.1
        chunks.extend([
            f'<text x="{left}" y="125" class="panel">{escape(label)}</text>',
            f'<line x1="{left}" y1="{top+plot_height}" x2="{left+panel_width}" y2="{top+plot_height}" stroke="#8a959f"/>',
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_height}" stroke="#8a959f"/>',
            f'<text x="{left}" y="{top-12}" class="small">{y_max:.1f} {escape(unit)}</text>',
            f'<text x="{left-31}" y="{top+plot_height+4}" class="small">{y_min:.1f}</text>',
        ])
        for center in CENTERS_DEG:
            x = left + (center - CENTERS_DEG[0]) / (CENTERS_DEG[-1] - CENTERS_DEG[0]) * panel_width
            chunks.extend([
                f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top+plot_height}" stroke="#dce4e7"/>',
                f'<text x="{x-9:.1f}" y="{top+plot_height+21}" class="small">{center}°</text>',
            ])
        for condition, color in colors.items():
            for motion in ("outward", "inward"):
                points = []
                for center in CENTERS_DEG:
                    trial_result = payload["results"][f"{regime}:R:{center}:{motion}"]
                    row = trial_result[condition]
                    value = row["summary"][metric] if condition != "shuffled_median" else row[metric]
                    x = left + (center - CENTERS_DEG[0]) / (CENTERS_DEG[-1] - CENTERS_DEG[0]) * panel_width
                    y = top + plot_height - (value - y_min) / (y_max - y_min) * plot_height
                    points.append((x, y))
                joined = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
                dash = ' stroke-dasharray="7 6"' if motion == "inward" else ""
                chunks.append(f'<polyline points="{joined}" fill="none" stroke="{color}" stroke-width="3"{dash}/>')
                if motion == "outward":
                    chunks.extend(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"/>'
                                  for x, y in points)
    for index, (condition, color) in enumerate(colors.items()):
        x = 80 + index * 260
        chunks.extend([f'<line x1="{x}" y1="498" x2="{x+48}" y2="498" stroke="{color}" stroke-width="4"/>',
                       f'<text x="{x+58}" y="503" class="small">{escape(condition.replace("_", " "))}</text>'])
    chunks.append('<text x="850" y="503" class="small">Input amplitude held fixed only in matched-current chart</text>')
    chunks.append('</svg>')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(chunks) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--chart-prefix", required=True, type=Path)
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    write_csv(result, args.csv)
    for regime in REGIMES:
        write_chart(result, args.chart_prefix.parent /
                    f"{args.chart_prefix.name}_{regime}.svg", regime)
    compact = defaultdict(dict)
    for key, conditions in result["results"].items():
        regime, side, center, motion = key.split(":")
        if side == "R" and motion in ("static", "outward", "inward"):
            compact[f"{regime}:{motion}"][center] = {
                condition: {metric: round(row["summary"][metric], 3)
                            for metric in ("AOTU019_spikes", "AOTU025_spikes",
                                           "DNa02_toward_bias_mv")}
                for condition, row in conditions.items()
                if condition in ("uniform", "anatomy")
            }
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
