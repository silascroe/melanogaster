"""Fixed-fly DNa02 firing sensitivity under moving-object pulses.

Only pulse span and speeds come from published experiments. Retinal input,
LIF dynamics, bridge scale, and tonic current are explicit model assumptions.
None of this changes the playable neural runtime.
"""

from __future__ import annotations

import argparse
import hashlib
from importlib.resources import files
import json
from pathlib import Path

import numpy as np

from .lif import LIFNetwork
from .steering import INPUT_MV
from .steering_diagnostic import load_candidate
from .visual_motion_experiment import FULL_MOTION_DEG_S, STATIC_FLOOR, load_upstream_map


BASELINE_MS = 100
STEP_MS = 20
SWEEP_SPAN_DEG = 22.5
SPEEDS_DEG_S = (25, 75)
CENTERS_DEG = (25, 45)  # Engineered frontal/lateral sample points.
SIDES = ("L", "R")
DIRECTIONS = ("outward", "inward", "static")
INPUT_MODES = ("position_full", "motion_full")
BRIDGE_SCALES = (1, 2, 4)
DN_TONIC_MV = (0, 16, 20)  # 15 mV is this LIF model's steady-state rheobase.
CONDITIONS = ("intact", "bridge_removed")


def run_trial(circuit, centers: dict[int, float], *, side: str, center: int,
              direction: str, speed: int, input_mode: str, bridge_scale: int,
              dn_tonic_mv: int, condition: str) -> dict:
    if (side not in SIDES or center not in CENTERS_DEG or direction not in DIRECTIONS
            or speed not in SPEEDS_DEG_S or input_mode not in INPUT_MODES
            or bridge_scale not in BRIDGE_SCALES or dn_tonic_mv not in DN_TONIC_MV
            or condition not in CONDITIONS):
        raise ValueError("Unknown fixed-fly condition")
    network = LIFNetwork(circuit)
    by_id = {neuron.body_id: neuron for neuron in circuit.neurons}
    bridge = np.asarray([
        by_id[network.node_ids[int(post)]].cell_type == "DNa02"
        and by_id[network.node_ids[int(pre)]].cell_type in ("AOTU019", "AOTU025")
        for pre, post in zip(network.pre, network.post)
    ])
    if int(bridge.sum()) != 4:
        raise RuntimeError("Expected the four selected AOTU-to-DNa02 edges")
    network.edge_current_mv[bridge] *= (bridge_scale if condition == "intact" else 0)
    state = network.initial_state()
    lc = {hemisphere: np.asarray([
        network.index[neuron.body_id] for neuron in circuit.neurons
        if neuron.cell_type == "LC10a" and neuron.side == hemisphere
    ], dtype=np.int64) for hemisphere in SIDES}
    lc_centers = {hemisphere: np.asarray([
        centers[neuron.body_id] for neuron in circuit.neurons
        if neuron.cell_type == "LC10a" and neuron.side == hemisphere
    ]) for hemisphere in SIDES}
    aotu = {kind: {hemisphere: network.index[next(
        neuron.body_id for neuron in circuit.neurons
        if neuron.cell_type == kind and neuron.side == hemisphere
    )] for hemisphere in SIDES} for kind in ("AOTU019", "AOTU025")}
    dn = {hemisphere: network.index[next(
        neuron.body_id for neuron in circuit.neurons
        if neuron.cell_type == "DNa02" and neuron.side == hemisphere
    )] for hemisphere in SIDES}
    external = np.zeros(len(network.node_ids), dtype=np.float64)
    external[list(dn.values())] = dn_tonic_mv
    pulse_ms = round(SWEEP_SPAN_DEG / speed * 1000)
    if pulse_ms % STEP_MS:
        raise RuntimeError("Pulse duration must divide into world steps")
    baseline_dn = {hemisphere: 0 for hemisphere in SIDES}
    pulse_dn = {hemisphere: 0 for hemisphere in SIDES}
    pulse_aotu = {kind: {hemisphere: 0 for hemisphere in SIDES} for kind in aotu}
    pulse_lc = 0
    first_pulse_dn_ms = {hemisphere: None for hemisphere in SIDES}
    first_pulse_aotu_ms = {kind: {hemisphere: None for hemisphere in SIDES}
                           for kind in aotu}
    max_pre_reset_dn_mv = {hemisphere: -65.0 for hemisphere in SIDES}
    # The no-target baseline runs with tonic DN drive but no visual current.
    for _ in range(BASELINE_MS):
        fired = network.step(state, external)
        for hemisphere in SIDES:
            baseline_dn[hemisphere] += int(fired[dn[hemisphere]])
    pulse_frames = pulse_ms // STEP_MS
    for frame in range(pulse_frames):
        if direction == "static":
            angle = float(center)
            retinal_speed = 0.0
        else:
            fraction = (frame + 0.5) / pulse_frames
            angle = (center - SWEEP_SPAN_DEG / 2 + fraction * SWEEP_SPAN_DEG
                     if direction == "outward" else
                     center + SWEEP_SPAN_DEG / 2 - fraction * SWEEP_SPAN_DEG)
            retinal_speed = 0.0 if frame == 0 else float(speed)
        factor = (1.0 if input_mode == "position_full" else
                  STATIC_FLOOR + (1.0 - STATIC_FLOOR)
                  * min(retinal_speed / FULL_MOTION_DEG_S, 1.0))
        weights = 0.1 + 0.9 * np.exp(-0.5 * ((angle - lc_centers[side]) / 18.0) ** 2)
        external[lc[side]] = INPUT_MV * factor * (weights / weights.mean())
        for offset in range(STEP_MS):
            t_ms = frame * STEP_MS + offset
            fired = network.step(state, external)
            pulse_lc += int(fired[lc[side]].sum())
            for kind in aotu:
                for hemisphere in SIDES:
                    if fired[aotu[kind][hemisphere]]:
                        pulse_aotu[kind][hemisphere] += 1
                        if first_pulse_aotu_ms[kind][hemisphere] is None:
                            first_pulse_aotu_ms[kind][hemisphere] = t_ms
            for hemisphere in SIDES:
                index = dn[hemisphere]
                if fired[index]:
                    pulse_dn[hemisphere] += 1
                    if first_pulse_dn_ms[hemisphere] is None:
                        first_pulse_dn_ms[hemisphere] = t_ms
                # A fired LIF neuron is reset before state is returned. This
                # is a bound on subthreshold samples, not the spike peak.
                max_pre_reset_dn_mv[hemisphere] = max(
                    max_pre_reset_dn_mv[hemisphere], float(state.voltage_mv[index]))
    toward = side
    away = "L" if side == "R" else "R"
    return {
        "pulse_ms": pulse_ms,
        "baseline_DNa02_spikes": baseline_dn,
        "pulse_LC10a_spikes": pulse_lc,
        "pulse_AOTU_spikes": pulse_aotu,
        "pulse_DNa02_spikes": pulse_dn,
        "toward_minus_away_DNa02_spikes": pulse_dn[toward] - pulse_dn[away],
        "first_pulse_AOTU_spike_ms": first_pulse_aotu_ms,
        "first_pulse_DNa02_spike_ms": first_pulse_dn_ms,
        "max_sampled_subthreshold_DNa02_mv": {
            hemisphere: round(value, 4)
            for hemisphere, value in max_pre_reset_dn_mv.items()
        },
    }


def run() -> dict:
    circuit = load_candidate()
    centers, _ = load_upstream_map(circuit)
    source = Path(str(files("fly_creature").joinpath("data/visual_steering_v1.json")))
    rows = []
    for bridge_scale in BRIDGE_SCALES:
        for dn_tonic_mv in DN_TONIC_MV:
            for input_mode in INPUT_MODES:
                for speed in SPEEDS_DEG_S:
                    for center in CENTERS_DEG:
                        for side in SIDES:
                            for direction in DIRECTIONS:
                                conditions = {
                                    condition: run_trial(
                                        circuit, centers, side=side, center=center,
                                        direction=direction, speed=speed,
                                        input_mode=input_mode, bridge_scale=bridge_scale,
                                        dn_tonic_mv=dn_tonic_mv, condition=condition,
                                    ) for condition in CONDITIONS
                                }
                                rows.append({
                                    "bridge_scale": bridge_scale,
                                    "dn_tonic_mv": dn_tonic_mv,
                                    "input_mode": input_mode,
                                    "speed_deg_s": speed,
                                    "center_deg": center,
                                    "side": side,
                                    "direction": direction,
                                    **conditions,
                                })
    summary = []
    for bridge_scale in BRIDGE_SCALES:
        for dn_tonic_mv in DN_TONIC_MV:
            for input_mode in INPUT_MODES:
                subset = [row for row in rows if row["bridge_scale"] == bridge_scale
                          and row["dn_tonic_mv"] == dn_tonic_mv
                          and row["input_mode"] == input_mode]
                moving = [row for row in subset if row["direction"] != "static"]
                summary.append({
                    "bridge_scale": bridge_scale,
                    "dn_tonic_mv": dn_tonic_mv,
                    "input_mode": input_mode,
                    "moving_trials": len(moving),
                    "moving_with_any_DNa02_spike": sum(
                        sum(row["intact"]["pulse_DNa02_spikes"].values()) > 0
                        for row in moving),
                    "moving_with_toward_spike_bias": sum(
                        row["intact"]["toward_minus_away_DNa02_spikes"] > 0
                        for row in moving),
                    "moving_with_bridge_dependent_toward_bias": sum(
                        row["intact"]["toward_minus_away_DNa02_spikes"]
                        > row["bridge_removed"]["toward_minus_away_DNa02_spikes"]
                        for row in moving),
                    "total_moving_intact_DNa02_spikes": sum(
                        sum(row["intact"]["pulse_DNa02_spikes"].values())
                        for row in moving),
                })
    return {
        "question": "Does a published-geometry moving-object pulse elicit DNa02 firing in the selected MaleCNS route?",
        "status": "offline sensitivity study; no playable change or biological calibration",
        "circuit_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "protocol": {
            "fly": "Fixed at origin; no movement or motor feedback.",
            "source_pulse_geometry": "22.5-degree azimuth sweeps at 25 or 75 degrees/s follow Collie et al.; "
                                     "centers at 25 and 45 degrees are our model probes.",
            "baseline_ms": BASELINE_MS, "world_step_ms": STEP_MS,
            "input": "Upstream-derived LC10a rank map; full 90 mV current normalized across the "
                     "stimulated side. Position or previous magnitude-only motion factor. "
                     "All per-cell retinal angles and current amplitudes are unmeasured assumptions.",
            "sensitivity": "AOTU-to-DNa02 model edge currents scaled by 1, 2, or 4; symmetric tonic "
                           "DNa02 current-equivalent drive at 0, 16, or 20 mV. The latter straddle "
                           "this LIF model's 15 mV steady-state firing threshold. None is a measured parameter.",
            "control": "All four AOTU-to-DNa02 edges removed with otherwise identical stimulus, "
                       "tonic drive, cells, and LIF state.",
            "interpretation": "A positive toward-side spike difference must also exceed the bridge-removed "
                              "control; static and reversed sweeps test selectivity. This is a "
                              "sensitivity analysis, not fitted physiology.",
        },
        "summary": summary,
        "trials": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
