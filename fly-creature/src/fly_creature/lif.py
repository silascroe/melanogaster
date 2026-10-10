"""One-step delayed LIF reference model adapted from FlyTest's simulation.py.

These dynamics and the current scale are engineering assumptions. The MaleCNS
release supplies edges and synapse counts, not membrane parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .circuit import Circuit


@dataclass
class LIFState:
    voltage_mv: np.ndarray
    refractory_steps: np.ndarray
    previous_spikes: np.ndarray


class LIFNetwork:
    def __init__(self, circuit: Circuit, *, connected: bool = True) -> None:
        self.node_ids = tuple(n.body_id for n in circuit.neurons)
        self.index = {body_id: i for i, body_id in enumerate(self.node_ids)}
        edges = circuit.connections if connected else ()
        self.pre = np.asarray([self.index[e.pre] for e in edges], dtype=np.int64)
        self.post = np.asarray([self.index[e.post] for e in edges], dtype=np.int64)
        # Transmitter labels determine a simple current sign. Receptor-specific
        # effects are unknown here; the existing all-ACh jump circuit retains
        # exactly its former positive weights.
        predicted = {n.body_id: n.predicted_nt for n in circuit.neurons}
        signs = {"acetylcholine": 1.0, "gaba": -1.0}
        if any(predicted[e.pre] not in signs for e in edges):
            raise ValueError("Unknown presynaptic transmitter; sign needs review")
        self.edge_current_mv = np.asarray(
            [e.synapse_count * 0.05 * signs[predicted[e.pre]] for e in edges],
            dtype=np.float64,
        )

    def initial_state(self) -> LIFState:
        count = len(self.node_ids)
        return LIFState(
            voltage_mv=np.full(count, -65.0, dtype=np.float64),
            refractory_steps=np.zeros(count, dtype=np.int64),
            previous_spikes=np.zeros(count, dtype=bool),
        )

    def step(self, state: LIFState, external_current_mv: np.ndarray) -> np.ndarray:
        """Advance 1 ms; spikes from this step affect postsynaptic cells next step."""
        if external_current_mv.shape != state.voltage_mv.shape:
            raise ValueError("One external current is required per neuron")
        if not np.all(np.isfinite(external_current_mv)):
            raise ValueError("External currents must be finite")
        synaptic = np.zeros(len(self.node_ids), dtype=np.float64)
        if len(self.pre):
            active = state.previous_spikes[self.pre]
            if active.any():
                np.add.at(synaptic, self.post[active], self.edge_current_mv[active])
        refractory = state.refractory_steps > 0
        state.voltage_mv[refractory] = -65.0
        state.refractory_steps[refractory] -= 1
        free = ~refractory
        state.voltage_mv[free] += 0.05 * (
            -65.0 - state.voltage_mv[free] + synaptic[free] + external_current_mv[free]
        )
        fired = free & (state.voltage_mv >= -50.0)
        state.voltage_mv[fired] = -65.0
        state.refractory_steps[fired] = 2
        state.previous_spikes = fired.copy()
        return fired
