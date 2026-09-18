"""Serve an inspectable browser view of a connectome-backed local circuit."""

from __future__ import annotations

import argparse
import json
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .analysis import LocalNetwork, PathwaySelection, select_local_network, select_native_pathway
from .data import MaleCNSPaths
from .sensorimotor import SensorimotorConfig
from .simulation import SimulationResult, simulate_lif


WEB_DIR = Path(__file__).with_name("web")
DEFAULT_HTML = WEB_DIR / "fly.html"


def _path_leg_map(selection: PathwaySelection) -> dict[tuple[int, int, int], str]:
    return {
        selection.path_edge_keys[0]: "source_to_intermediate",
        selection.path_edge_keys[1]: "intermediate_to_target",
    }


def _node_rows(selection: PathwaySelection, network: LocalNetwork) -> list[dict[str, Any]]:
    roles = {
        selection.source_id: "source",
        selection.intermediate_id: "intermediate",
        selection.target_id: "target",
    }
    rows = []
    for node in network.nodes:
        role = roles.get(node.body_id, "context")
        rows.append(
            {
                "body_id": node.body_id,
                "label": node.instance or node.type or f"body {node.body_id}",
                "type": node.type,
                "instance": node.instance,
                "superclass": node.superclass,
                "class": node.class_label,
                "soma_side": node.soma_side,
                "consensus_nt": node.consensus_nt,
                "fast_sign": node.fast_sign,
                "role": role,
                "is_path_node": role != "context",
            }
        )
    return rows


def _edge_rows(selection: PathwaySelection, network: LocalNetwork) -> list[dict[str, Any]]:
    path_legs = _path_leg_map(selection)
    rows = []
    for edge in network.edges:
        key = (edge.body_pre, edge.body_post, edge.weight)
        rows.append(
            {
                "body_pre": edge.body_pre,
                "body_post": edge.body_post,
                "weight": edge.weight,
                "transmitter_pre": edge.transmitter_pre,
                "sign": edge.sign,
                "signed_weight": edge.signed_weight,
                "is_path_edge": key in path_legs,
                "path_leg": path_legs.get(key, ""),
            }
        )
    return rows


def _stimulus_active(time_ms: float, config: SensorimotorConfig) -> bool:
    return config.input_start_ms <= time_ms < config.input_start_ms + config.input_duration_ms


class VisualModel:
    """Cache one real local graph and run cheap parameterized replays."""

    def __init__(
        self,
        paths: MaleCNSPaths,
        *,
        min_weight: int = 3,
        neighbor_limit: int = 24,
        max_edges: int = 500,
    ) -> None:
        self.paths = paths
        self.selection = select_native_pathway(paths, min_weight=min_weight)
        self.network = select_local_network(
            paths,
            [self.selection.source_id, self.selection.intermediate_id, self.selection.target_id],
            neighbor_limit=neighbor_limit,
            min_weight=min_weight,
            max_edges=max_edges,
        )
        self.node_rows = _node_rows(self.selection, self.network)
        self.edge_rows = _edge_rows(self.selection, self.network)

    def run(self, config: SensorimotorConfig | None = None) -> dict[str, Any]:
        run_config = config or SensorimotorConfig()
        lif_config = run_config.to_lif()
        node_ids = [node.body_id for node in self.network.nodes]
        result = simulate_lif(
            node_ids,
            [edge.body_pre for edge in self.network.edges],
            [edge.body_post for edge in self.network.edges],
            [edge.weight for edge in self.network.edges],
            [edge.sign for edge in self.network.edges],
            input_nodes=[self.selection.source_id],
            config=lif_config,
        )
        node_indices = {body_id: index for index, body_id in enumerate(result.node_ids)}
        source_index = node_indices[self.selection.source_id]
        intermediate_index = node_indices[self.selection.intermediate_id]
        target_index = node_indices[self.selection.target_id]

        heading = run_config.initial_heading_degrees
        position_x = run_config.initial_x
        position_y = run_config.initial_y
        trajectory: list[dict[str, Any]] = []
        spikes_by_time: list[list[int]] = []
        for time_index, time_ms in enumerate(result.times_ms.tolist()):
            active_ids = [
                int(body_id)
                for body_id, active in zip(result.node_ids, result.spikes[time_index].tolist())
                if active
            ]
            spikes_by_time.append(active_ids)
            target_spike = bool(result.spikes[time_index, target_index])
            turn_command = run_config.turn_degrees_per_target_spike if target_spike else 0.0
            if target_spike:
                heading += turn_command
                radians = math.radians(heading)
                position_x += run_config.forward_step_per_target_spike * math.cos(radians)
                position_y += run_config.forward_step_per_target_spike * math.sin(radians)
            trajectory.append(
                {
                    "time_ms": float(time_ms),
                    "stimulus_active": _stimulus_active(float(time_ms), run_config),
                    "source_spike": bool(result.spikes[time_index, source_index]),
                    "intermediate_spike": bool(result.spikes[time_index, intermediate_index]),
                    "target_spike": target_spike,
                    "source_voltage_mv": float(result.voltages_mv[time_index, source_index]),
                    "intermediate_voltage_mv": float(result.voltages_mv[time_index, intermediate_index]),
                    "target_voltage_mv": float(result.voltages_mv[time_index, target_index]),
                    "turn_command_degrees": float(turn_command),
                    "heading_degrees": float(heading),
                    "position_x": float(position_x),
                    "position_y": float(position_y),
                }
            )

        spike_counts = result.spike_counts()
        final = trajectory[-1]
        return {
            "experiment": "visual connectome-backed local circuit",
            "dataset": {
                "name": "FlyEM Male CNS",
                "release": "v1.0",
                "data_dir": str(self.paths.data_dir),
                "source_manifest": "data/metadata/source_manifest.json",
            },
            "path": {
                "source_id": self.selection.source_id,
                "intermediate_id": self.selection.intermediate_id,
                "target_id": self.selection.target_id,
                "path_edge_keys": [list(key) for key in self.selection.path_edge_keys],
            },
            "selection": self.selection.selection,
            "network": {
                "node_count": len(self.network.nodes),
                "edge_count": len(self.network.edges),
                "neighbor_limit": self.network.selection["neighbor_limit"],
                "max_edges": self.network.selection["max_edges"],
            },
            "parameters": {
                **run_config.__dict__,
                "synaptic_gain": lif_config.synaptic_gain,
                "synaptic_tau_ms": lif_config.synaptic_tau_ms,
            },
            "action_decoder": {
                "output": "one fixed turn and forward step per selected descending-target spike",
                "turn_degrees_per_target_spike": run_config.turn_degrees_per_target_spike,
                "forward_step_per_target_spike": run_config.forward_step_per_target_spike,
            },
            "nodes": self.node_rows,
            "edges": self.edge_rows,
            "trajectory": trajectory,
            "spikes_by_time": spikes_by_time,
            "spike_events": result.spike_events(),
            "outcome": {
                "spike_counts": {str(body_id): count for body_id, count in spike_counts.items()},
                "source_spike_count": spike_counts.get(self.selection.source_id, 0),
                "intermediate_spike_count": spike_counts.get(self.selection.intermediate_id, 0),
                "target_spike_count": spike_counts.get(self.selection.target_id, 0),
                "turn_event_count": sum(bool(row["target_spike"]) for row in trajectory),
                "final_heading_degrees": final["heading_degrees"],
                "final_position": [final["position_x"], final["position_y"]],
                "total_spikes": int(result.spikes.sum()),
            },
            "notes": [
                "The browser shows a 27-node local context around a selected three-node sensory-to-descending path.",
                "Only the selected sensory source receives the synthetic external pulse.",
                "The body and descending-spike decoder are explicit toy assumptions.",
            ],
        }


def _number(query: dict[str, list[str]], name: str, default: float) -> float:
    raw = query.get(name, [str(default)])[0]
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be numeric") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _config_from_query(query: dict[str, list[str]]) -> SensorimotorConfig:
    duration_ms = _number(query, "duration_ms", 120.0)
    coupling = _number(query, "coupling", 3.0)
    input_duration_ms = _number(query, "input_duration_ms", 50.0)
    turn_degrees = _number(query, "turn_degrees", 15.0)
    forward_step = _number(query, "forward_step", 1.0)
    if not 1 <= duration_ms <= 300:
        raise ValueError("duration_ms must be between 1 and 300")
    if coupling < 0:
        raise ValueError("coupling must be non-negative")
    if input_duration_ms < 0 or input_duration_ms > duration_ms:
        raise ValueError("input_duration_ms must be between 0 and duration_ms")
    return SensorimotorConfig(
        duration_ms=duration_ms,
        coupling_mv_per_synapse=coupling,
        input_duration_ms=input_duration_ms,
        turn_degrees_per_target_spike=turn_degrees,
        forward_step_per_target_spike=forward_step,
    )


class _Handler(BaseHTTPRequestHandler):
    server: "FlyServer"

    def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send(self.server.html, "text/html; charset=utf-8")
            return
        if parsed.path == "/health":
            self._send(b"ok\n", "text/plain; charset=utf-8")
            return
        if parsed.path == "/api/run":
            try:
                payload = self.server.model.run(_config_from_query(parse_qs(parsed.query)))
                body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                self._send(body, "application/json; charset=utf-8")
            except (ValueError, KeyError) as error:
                self._send(json.dumps({"error": str(error)}).encode("utf-8"), "application/json", 400)
            return
        self._send(b"not found\n", "text/plain; charset=utf-8", 404)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[flytest] {format % args}")


class FlyServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], model: VisualModel, html: bytes) -> None:
        super().__init__(address, _Handler)
        self.model = model
        self.html = html


def serve(
    *,
    data_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    neighbor_limit: int = 24,
    max_edges: int = 500,
) -> None:
    html_path = DEFAULT_HTML
    if not html_path.is_file():
        raise FileNotFoundError(f"Visual UI not found: {html_path}")
    print("[flytest] selecting and caching the local connectome context...")
    model = VisualModel(
        MaleCNSPaths(data_dir), neighbor_limit=neighbor_limit, max_edges=max_edges
    )
    server = FlyServer((host, port), model, html_path.read_bytes())
    print(f"[flytest] visual simulation: http://{host}:{port}")
    print(f"[flytest] network: {len(model.network.nodes)} nodes, {len(model.network.edges)} edges")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[flytest] stopping visual simulation")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the FlyTest visual simulation")
    parser.add_argument("--data-dir", type=Path, default=Path("data/working/male-cns-v1.0"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--neighbors", type=int, default=24)
    parser.add_argument("--max-edges", type=int, default=500)
    args = parser.parse_args()
    serve(
        data_dir=args.data_dir,
        host=args.host,
        port=args.port,
        neighbor_limit=args.neighbors,
        max_edges=args.max_edges,
    )


if __name__ == "__main__":
    main()
