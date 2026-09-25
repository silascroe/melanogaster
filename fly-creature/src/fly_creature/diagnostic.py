"""Inspect the selected circuit with one matched approach and a disconnected control."""

from __future__ import annotations

import json

from .circuit import load_circuit
from .controller import CreatureSession


def run() -> dict[str, object]:
    circuit = load_circuit()
    result: dict[str, object] = {"circuit_neurons": len(circuit.neurons), "circuit_edges": len(circuit.connections)}
    for condition in ("intact", "disconnected"):
        session = CreatureSession(circuit, condition=condition)
        frames = []
        for frame_index in range(36):
            distance = 8.0 - frame_index * 0.2
            row = session.step({
                "dt_ms": 50,
                "fly": {"x": 0.0, "z": 0.0, "heading_rad": 0.0},
                "object": {"x": 0.0, "z": -distance, "radius": 0.45},
            })
            frames.append({"frame": frame_index, "distance_m": round(distance, 2), **row})
        result[condition] = {
            "first_jump_frame": next((row["frame"] for row in frames if row["jump"]), None),
            "total_gf_spikes": sum(row["spikes"]["DNp01"] for row in frames),
            "frames": frames,
        }
    return result


def main() -> None:
    print(json.dumps(run(), indent=2))


if __name__ == "__main__":
    main()
