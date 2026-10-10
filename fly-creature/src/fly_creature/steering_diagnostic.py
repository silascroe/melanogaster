"""Matched left/right visual-input probes of the candidate MaleCNS steering path.

No pixels, object tuning, steering decoder, or body motion is modeled here.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from importlib.resources import files
import json
from pathlib import Path

import numpy as np

from .circuit import Circuit, Connection, Neuron
from .lif import LIFNetwork


TYPES = {"LC10a", "AOTU019", "AOTU025", "DNa02"}
BRIDGES = {("LC10a", "AOTU019"), ("LC10a", "AOTU025"),
           ("AOTU019", "DNa02"), ("AOTU025", "DNa02")}
BASELINE_MS = 50
STIMULUS_MS = 200
RECOVERY_MS = 100
INPUT_MV = 90.0
BIN_MS = 10


def load_candidate(path: Path | None = None) -> Circuit:
    if path is None:
        path = Path(str(files("fly_creature").joinpath("data/visual_steering_v1.json")))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported steering circuit schema")
    neurons = tuple(
        Neuron(int(row["body_id"]), str(row["type"]), str(row["side"]),
               str(row["predicted_nt"]))
        for row in payload["neurons"]
    )
    by_id = {n.body_id: n for n in neurons}
    if len(by_id) != len(neurons) or {n.cell_type for n in neurons} != TYPES:
        raise ValueError("Duplicate IDs or missing/unexpected candidate neuron types")
    if any(n.side not in ("L", "R") for n in neurons):
        raise ValueError("Candidate circuit contains an unknown side")
    connections = tuple(
        Connection(int(row["pre"]), int(row["post"]), int(row["synapse_count"]))
        for row in payload["connections"]
    )
    if not connections:
        raise ValueError("Candidate circuit has no recorded connections")
    for edge in connections:
        if edge.pre not in by_id or edge.post not in by_id or edge.synapse_count <= 0:
            raise ValueError("Invalid candidate connection")
        if (by_id[edge.pre].cell_type, by_id[edge.post].cell_type) not in BRIDGES:
            raise ValueError("Connection outside the selected two-hop route")
    return Circuit(neurons, connections, dict(payload["provenance"]))


def condition_circuit(source: Circuit, condition: str) -> Circuit:
    by_id = {n.body_id: n for n in source.neurons}
    dn_by_side = {n.side: n.body_id for n in source.neurons if n.cell_type == "DNa02"}
    if set(dn_by_side) != {"L", "R"}:
        raise ValueError("Expected one DNa02 on each side")
    if condition == "intact":
        return source
    if condition == "bridge_removed":
        edges = tuple(e for e in source.connections if by_id[e.post].cell_type != "DNa02")
    elif condition in ("AOTU019_output_removed", "AOTU025_output_removed"):
        removed_type = condition.split("_", 1)[0]
        edges = tuple(e for e in source.connections
                      if not (by_id[e.pre].cell_type == removed_type
                              and by_id[e.post].cell_type == "DNa02"))
    elif condition == "bridge_side_swapped":
        edges = tuple(
            replace(e, post=dn_by_side["R" if by_id[e.post].side == "L" else "L"])
            if by_id[e.post].cell_type == "DNa02" else e
            for e in source.connections
        )
    else:
        raise ValueError(f"Unknown condition: {condition}")
    return Circuit(source.neurons, edges, source.provenance)


def run_trial(circuit: Circuit, stimulus_side: str) -> dict:
    network = LIFNetwork(circuit)
    state = network.initial_state()
    lc_by_side = {side: np.asarray([network.index[n.body_id] for n in circuit.neurons
                                   if n.cell_type == "LC10a" and n.side == side],
                                  dtype=np.int64) for side in ("L", "R")}
    lc = lc_by_side[stimulus_side]
    aotu = {cell_type: {side: network.index[next(n.body_id for n in circuit.neurons
                  if n.cell_type == cell_type and n.side == side)] for side in ("L", "R")}
            for cell_type in ("AOTU019", "AOTU025")}
    dn = {side: network.index[next(n.body_id for n in circuit.neurons
          if n.cell_type == "DNa02" and n.side == side)] for side in ("L", "R")}
    current = np.zeros(len(network.node_ids), dtype=np.float64)
    spike_totals = {cell_type: {side: 0 for side in ("L", "R")}
                    for cell_type in ("LC10a", "AOTU019", "AOTU025", "DNa02")}
    voltage_sums = {side: 0.0 for side in ("L", "R")}
    voltage_samples = 0
    bins = []
    total_ms = BASELINE_MS + STIMULUS_MS + RECOVERY_MS
    for t in range(total_ms):
        stimulated = BASELINE_MS <= t < BASELINE_MS + STIMULUS_MS
        current[lc] = INPUT_MV if stimulated else 0.0
        fired = network.step(state, current)
        for side in ("L", "R"):
            if stimulated:
                voltage_sums[side] += float(state.voltage_mv[dn[side]])
        voltage_samples += int(stimulated)
        if t % BIN_MS == 0:
            bins.append({"start_ms": t, "stimulus_on": stimulated,
                         "LC10a_L": 0, "LC10a_R": 0,
                         "AOTU019_L": 0, "AOTU019_R": 0,
                         "AOTU025_L": 0, "AOTU025_R": 0,
                         "DNa02_L": 0, "DNa02_R": 0,
                         "DNa02_L_mean_mv": 0.0, "DNa02_R_mean_mv": 0.0})
        row = bins[-1]
        for side in ("L", "R"):
            lc_count = int(fired[lc_by_side[side]].sum())
            row[f"LC10a_{side}"] += lc_count
            spike_totals["LC10a"][side] += lc_count
            for cell_type in ("AOTU019", "AOTU025"):
                count = int(fired[aotu[cell_type][side]])
                row[f"{cell_type}_{side}"] += count
                spike_totals[cell_type][side] += count
            dn_count = int(fired[dn[side]])
            row[f"DNa02_{side}"] += dn_count
            spike_totals["DNa02"][side] += dn_count
            row[f"DNa02_{side}_mean_mv"] += float(state.voltage_mv[dn[side]]) / BIN_MS
    for row in bins:
        for side in ("L", "R"):
            row[f"DNa02_{side}_mean_mv"] = round(row[f"DNa02_{side}_mean_mv"], 4)
    mean_voltage = {side: round(voltage_sums[side] / voltage_samples, 4)
                    for side in ("L", "R")}
    return {"stimulus_side": stimulus_side,
            "stimulated_LC10a_count": len(lc),
            "spike_totals": spike_totals,
            "stimulus_mean_DNa02_voltage_mv": mean_voltage,
            "stimulus_DNa02_L_minus_R_mv": round(mean_voltage["L"] - mean_voltage["R"], 4),
            "bins": bins}


def run() -> dict:
    source = load_candidate()
    conditions = {}
    for condition in ("intact", "bridge_removed", "bridge_side_swapped"):
        candidate = condition_circuit(source, condition)
        conditions[condition] = {side: run_trial(candidate, side) for side in ("L", "R")}
    return {
        "question": "Does a matched left/right LC10a pulse create a DNa02 activity difference in the selected LIF model?",
        "circuit": {"neurons": len(source.neurons), "recorded_edges": len(source.connections),
                    "source": "data/visual_steering_v1.json"},
        "protocol": {"baseline_ms": BASELINE_MS, "stimulus_ms": STIMULUS_MS,
                     "recovery_ms": RECOVERY_MS, "bin_ms": BIN_MS,
                     "input": f"{INPUT_MV} mV model current to every LC10a on the stimulated side",
                     "fixed_parameters": "Existing 1 ms LIF, 0.05 mV per synapse, one-step delay; ACh +, GABA -"},
        "conditions": conditions,
        "limits": "Engineered simultaneous cell input; model voltages and spikes, not measured physiology or steering commands.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write full 10 ms traces to JSON")
    args = parser.parse_args()
    result = run()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    summary = {condition: {side: {
        "spikes": trial["spike_totals"],
        "DNa02_mean_mv": trial["stimulus_mean_DNa02_voltage_mv"],
        "DNa02_L_minus_R_mv": trial["stimulus_DNa02_L_minus_R_mv"],
    } for side, trial in trials.items()} for condition, trials in result["conditions"].items()}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
