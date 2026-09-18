"""Serve an inspectable browser view of two connectome-backed sensory channels."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, field, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .analysis import LocalNetwork, PathwaySelection, select_local_network, select_native_pathway
from .data import MaleCNSPaths
from .sensorimotor import SensorimotorConfig
from .simulation import LIFConfig, SimulationResult, simulate_lif


WEB_DIR = Path(__file__).with_name("web")
DEFAULT_HTML = WEB_DIR / "fly.html"


@dataclass(frozen=True)
class VisualRunConfig:
    """Neural parameters plus the deliberately simple visual environment."""

    neural: SensorimotorConfig = field(
        default_factory=lambda: SensorimotorConfig(
            duration_ms=120.0,
            coupling_mv_per_synapse=3.0,
            input_duration_ms=50.0,
        )
    )
    visual_contrast: float = 1.0
    visual_coupling_mv_per_synapse: float = 5.0
    visual_target_x: float = 7.0
    visual_target_y: float = 4.0

    def validate(self) -> None:
        self.neural.validate()
        if not math.isfinite(self.visual_contrast) or self.visual_contrast < 0:
            raise ValueError("visual_contrast must be finite and non-negative")
        if (
            not math.isfinite(self.visual_coupling_mv_per_synapse)
            or self.visual_coupling_mv_per_synapse < 0
        ):
            raise ValueError("visual_coupling_mv_per_synapse must be finite and non-negative")
        if not math.isfinite(self.visual_target_x) or not math.isfinite(self.visual_target_y):
            raise ValueError("visual target position must be finite")

    def touch_lif(self) -> LIFConfig:
        return self.neural.to_lif()

    def visual_lif(self) -> LIFConfig:
        return replace(
            self.touch_lif(),
            mv_per_synapse=self.visual_coupling_mv_per_synapse,
            input_current_mv=self.neural.input_current_mv * self.visual_contrast,
        )


@dataclass(frozen=True)
class CachedChannel:
    name: str
    selection: PathwaySelection
    network: LocalNetwork


def _path_leg_map(selection: PathwaySelection) -> dict[tuple[int, int, int], str]:
    return {
        selection.path_edge_keys[0]: "source_to_intermediate",
        selection.path_edge_keys[1]: "intermediate_to_target",
    }


def _path_summary(channel: CachedChannel) -> dict[str, Any]:
    selection = channel.selection
    return {
        "channel": channel.name,
        "source_id": selection.source_id,
        "intermediate_id": selection.intermediate_id,
        "target_id": selection.target_id,
        "path_edge_keys": [list(key) for key in selection.path_edge_keys],
        "selection": selection.selection,
    }


def _node_rows(channel: CachedChannel) -> list[dict[str, Any]]:
    selection = channel.selection
    roles = {
        selection.source_id: "source",
        selection.intermediate_id: "intermediate",
        selection.target_id: "target",
    }
    rows = []
    for node in channel.network.nodes:
        role = roles.get(node.body_id, "context")
        rows.append(
            {
                "channel": channel.name,
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


def _edge_rows(channel: CachedChannel) -> list[dict[str, Any]]:
    path_legs = _path_leg_map(channel.selection)
    rows = []
    for edge in channel.network.edges:
        key = (edge.body_pre, edge.body_post, edge.weight)
        rows.append(
            {
                "channel": channel.name,
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


def _run_channel(
    channel: CachedChannel,
    *,
    lif_config: LIFConfig,
) -> SimulationResult:
    return simulate_lif(
        [node.body_id for node in channel.network.nodes],
        [edge.body_pre for edge in channel.network.edges],
        [edge.body_post for edge in channel.network.edges],
        [edge.weight for edge in channel.network.edges],
        [edge.sign for edge in channel.network.edges],
        input_nodes=[channel.selection.source_id],
        config=lif_config,
    )


def _channel_events(result: SimulationResult, channel_name: str) -> list[dict[str, Any]]:
    return [
        {**event, "channel": channel_name}
        for event in result.spike_events()
    ]


class VisualModel:
    """Cache one tactile graph and one visual graph, then replay both cheaply."""

    def __init__(
        self,
        paths: MaleCNSPaths,
        *,
        min_weight: int = 3,
        neighbor_limit: int = 24,
        max_edges: int = 500,
    ) -> None:
        self.paths = paths
        touch_selection = select_native_pathway(paths, min_weight=min_weight)
        visual_selection = select_native_pathway(
            paths,
            source_superclass="visual_projection",
            intermediate_superclass="ol_intrinsic",
            target_superclass="descending_neuron",
            min_weight=min_weight,
        )
        self.channels = (
            CachedChannel(
                "touch",
                touch_selection,
                select_local_network(
                    paths,
                    [
                        touch_selection.source_id,
                        touch_selection.intermediate_id,
                        touch_selection.target_id,
                    ],
                    neighbor_limit=neighbor_limit,
                    min_weight=min_weight,
                    max_edges=max_edges,
                ),
            ),
            CachedChannel(
                "vision",
                visual_selection,
                select_local_network(
                    paths,
                    [
                        visual_selection.source_id,
                        visual_selection.intermediate_id,
                        visual_selection.target_id,
                    ],
                    neighbor_limit=neighbor_limit,
                    min_weight=min_weight,
                    max_edges=max_edges,
                ),
            ),
        )
        touch_ids = {node.body_id for node in self.channels[0].network.nodes}
        visual_ids = {node.body_id for node in self.channels[1].network.nodes}
        overlap = sorted(touch_ids & visual_ids)
        if overlap:
            raise ValueError(f"local sensory contexts unexpectedly overlap: {overlap}")
        self.node_rows = [
            row
            for channel in self.channels
            for row in _node_rows(channel)
        ]
        self.edge_rows = [
            row
            for channel in self.channels
            for row in _edge_rows(channel)
        ]

    def run(
        self,
        config: VisualRunConfig | SensorimotorConfig | None = None,
    ) -> dict[str, Any]:
        if config is None:
            run_config = VisualRunConfig()
        elif isinstance(config, SensorimotorConfig):
            run_config = VisualRunConfig(neural=config)
        else:
            run_config = config
        run_config.validate()

        touch_channel, vision_channel = self.channels
        touch_result = _run_channel(touch_channel, lif_config=run_config.touch_lif())
        vision_result = _run_channel(vision_channel, lif_config=run_config.visual_lif())
        if len(touch_result.times_ms) != len(vision_result.times_ms):
            raise ValueError("touch and visual simulations must have the same timestep count")

        touch_indices = {
            body_id: index for index, body_id in enumerate(touch_result.node_ids)
        }
        vision_indices = {
            body_id: index for index, body_id in enumerate(vision_result.node_ids)
        }
        touch_source_index = touch_indices[touch_channel.selection.source_id]
        touch_intermediate_index = touch_indices[touch_channel.selection.intermediate_id]
        touch_target_index = touch_indices[touch_channel.selection.target_id]
        vision_source_index = vision_indices[vision_channel.selection.source_id]
        vision_intermediate_index = vision_indices[vision_channel.selection.intermediate_id]
        vision_target_index = vision_indices[vision_channel.selection.target_id]

        heading = run_config.neural.initial_heading_degrees
        position_x = run_config.neural.initial_x
        position_y = run_config.neural.initial_y
        trajectory: list[dict[str, Any]] = []
        spikes_by_time: list[list[dict[str, Any]]] = []
        for time_index, time_ms in enumerate(touch_result.times_ms.tolist()):
            touch_spikes = touch_result.spikes[time_index]
            vision_spikes = vision_result.spikes[time_index]
            touch_target_spike = bool(touch_spikes[touch_target_index])
            visual_target_spike = bool(vision_spikes[vision_target_index])
            target_spike = touch_target_spike or visual_target_spike

            touch_turn = (
                run_config.neural.turn_degrees_per_target_spike
                if touch_target_spike
                else 0.0
            )
            visual_angle_error = 0.0
            visual_turn = 0.0
            if visual_target_spike:
                desired_heading = math.degrees(
                    math.atan2(
                        run_config.visual_target_y - position_y,
                        run_config.visual_target_x - position_x,
                    )
                )
                visual_angle_error = (desired_heading - heading + 180.0) % 360.0 - 180.0
                visual_turn = max(
                    -run_config.neural.turn_degrees_per_target_spike,
                    min(
                        run_config.neural.turn_degrees_per_target_spike,
                        visual_angle_error,
                    ),
                )
            turn_command = touch_turn + visual_turn
            if target_spike:
                heading += turn_command
                radians = math.radians(heading)
                position_x += run_config.neural.forward_step_per_target_spike * math.cos(radians)
                position_y += run_config.neural.forward_step_per_target_spike * math.sin(radians)

            active = [
                {"channel": "touch", "body_id": int(body_id)}
                for body_id, is_active in zip(
                    touch_result.node_ids, touch_spikes.tolist()
                )
                if is_active
            ]
            active.extend(
                {"channel": "vision", "body_id": int(body_id)}
                for body_id, is_active in zip(
                    vision_result.node_ids, vision_spikes.tolist()
                )
                if is_active
            )
            spikes_by_time.append(active)
            touch_active = _stimulus_active(float(time_ms), run_config.neural)
            visual_active = touch_active and run_config.visual_contrast > 0
            trajectory.append(
                {
                    "time_ms": float(time_ms),
                    "stimulus_active": touch_active,
                    "touch_stimulus_active": touch_active,
                    "visual_stimulus_active": visual_active,
                    "source_spike": bool(touch_spikes[touch_source_index]),
                    "intermediate_spike": bool(touch_spikes[touch_intermediate_index]),
                    "target_spike": target_spike,
                    "touch_source_spike": bool(touch_spikes[touch_source_index]),
                    "touch_intermediate_spike": bool(touch_spikes[touch_intermediate_index]),
                    "touch_target_spike": touch_target_spike,
                    "visual_source_spike": bool(vision_spikes[vision_source_index]),
                    "visual_intermediate_spike": bool(vision_spikes[vision_intermediate_index]),
                    "visual_target_spike": visual_target_spike,
                    "source_voltage_mv": float(touch_result.voltages_mv[time_index, touch_source_index]),
                    "intermediate_voltage_mv": float(
                        touch_result.voltages_mv[time_index, touch_intermediate_index]
                    ),
                    "target_voltage_mv": float(
                        touch_result.voltages_mv[time_index, touch_target_index]
                    ),
                    "touch_source_voltage_mv": float(
                        touch_result.voltages_mv[time_index, touch_source_index]
                    ),
                    "touch_intermediate_voltage_mv": float(
                        touch_result.voltages_mv[time_index, touch_intermediate_index]
                    ),
                    "touch_target_voltage_mv": float(
                        touch_result.voltages_mv[time_index, touch_target_index]
                    ),
                    "visual_source_voltage_mv": float(
                        vision_result.voltages_mv[time_index, vision_source_index]
                    ),
                    "visual_intermediate_voltage_mv": float(
                        vision_result.voltages_mv[time_index, vision_intermediate_index]
                    ),
                    "visual_target_voltage_mv": float(
                        vision_result.voltages_mv[time_index, vision_target_index]
                    ),
                    "touch_turn_degrees": float(touch_turn),
                    "visual_turn_degrees": float(visual_turn),
                    "visual_angle_error_degrees": float(visual_angle_error),
                    "turn_command_degrees": float(turn_command),
                    "heading_degrees": float(heading),
                    "position_x": float(position_x),
                    "position_y": float(position_y),
                }
            )

        touch_counts = touch_result.spike_counts()
        visual_counts = vision_result.spike_counts()
        final = trajectory[-1]
        spike_events = sorted(
            _channel_events(touch_result, "touch")
            + _channel_events(vision_result, "vision"),
            key=lambda event: (float(event["time_ms"]), str(event["channel"])),
        )
        parameters = {
            **asdict(run_config.neural),
            "neural": asdict(run_config.neural),
            "visual_contrast": run_config.visual_contrast,
            "visual_coupling_mv_per_synapse": run_config.visual_coupling_mv_per_synapse,
            "visual_target_x": run_config.visual_target_x,
            "visual_target_y": run_config.visual_target_y,
            "touch_synaptic_gain": run_config.touch_lif().synaptic_gain,
            "visual_synaptic_gain": run_config.visual_lif().synaptic_gain,
            "synaptic_tau_ms": run_config.touch_lif().synaptic_tau_ms,
        }
        return {
            "experiment": "dual sensory connectome-backed local circuit",
            "dataset": {
                "name": "FlyEM Male CNS",
                "release": "v1.0",
                "data_dir": str(self.paths.data_dir),
                "source_manifest": "data/metadata/source_manifest.json",
            },
            "path": _path_summary(touch_channel),
            "pathways": {
                "touch": _path_summary(touch_channel),
                "vision": _path_summary(vision_channel),
            },
            "selection": touch_channel.selection.selection,
            "network": {
                "node_count": len(self.node_rows),
                "edge_count": len(self.edge_rows),
                "channels": {
                    channel.name: {
                        "node_count": len(channel.network.nodes),
                        "edge_count": len(channel.network.edges),
                    }
                    for channel in self.channels
                },
                "neighbor_limit": touch_channel.network.selection["neighbor_limit"],
                "max_edges": touch_channel.network.selection["max_edges"],
            },
            "parameters": parameters,
            "action_decoder": {
                "touch_output": "one fixed turn and forward step per selected descending-target spike",
                "vision_output": "steer toward the visual beacon, capped at one turn quantum per selected descending-target spike",
                "turn_degrees_per_target_spike": run_config.neural.turn_degrees_per_target_spike,
                "forward_step_per_target_spike": run_config.neural.forward_step_per_target_spike,
                "heading_convention": "positive degrees rotate counterclockwise; arbitrary toy axis",
            },
            "environment": {
                "visual_target": {
                    "x": run_config.visual_target_x,
                    "y": run_config.visual_target_y,
                    "label": "visual beacon",
                }
            },
            "nodes": self.node_rows,
            "edges": self.edge_rows,
            "trajectory": trajectory,
            "spikes_by_time": spikes_by_time,
            "spike_events": spike_events,
            "outcome": {
                "spike_counts": {
                    "touch": {str(body_id): count for body_id, count in touch_counts.items()},
                    "vision": {str(body_id): count for body_id, count in visual_counts.items()},
                },
                "touch_source_spike_count": touch_counts.get(touch_channel.selection.source_id, 0),
                "touch_intermediate_spike_count": touch_counts.get(
                    touch_channel.selection.intermediate_id, 0
                ),
                "touch_target_spike_count": touch_counts.get(touch_channel.selection.target_id, 0),
                "visual_source_spike_count": visual_counts.get(vision_channel.selection.source_id, 0),
                "visual_intermediate_spike_count": visual_counts.get(
                    vision_channel.selection.intermediate_id, 0
                ),
                "visual_target_spike_count": visual_counts.get(vision_channel.selection.target_id, 0),
                "target_spike_count": sum(
                    int(row["touch_target_spike"]) + int(row["visual_target_spike"])
                    for row in trajectory
                ),
                "turn_event_count": sum(bool(row["target_spike"]) for row in trajectory),
                "final_heading_degrees": final["heading_degrees"],
                "final_position": [final["position_x"], final["position_y"]],
                "total_spikes": int(touch_result.spikes.sum() + vision_result.spikes.sum()),
            },
            "notes": [
                "The browser shows two separate 27-node local contexts around selected three-node paths.",
                "The touch channel uses the existing vnc sensory pathway; the visual channel starts at an annotated visual_projection neuron and crosses optic-lobe intrinsic circuitry.",
                "The visual beacon, synthetic sensory pulses, body, and descending-spike decoder are explicit toy assumptions.",
                "The selected pathways are real connectome records, but this is not a retina model or a complete fly behavior.",
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


def _config_from_query(query: dict[str, list[str]]) -> VisualRunConfig:
    duration_ms = _number(query, "duration_ms", 120.0)
    coupling = _number(query, "coupling", 3.0)
    input_duration_ms = _number(query, "input_duration_ms", 50.0)
    turn_degrees = _number(query, "turn_degrees", 15.0)
    forward_step = _number(query, "forward_step", 1.0)
    visual_contrast = _number(query, "visual_contrast", 1.0)
    visual_coupling = _number(query, "visual_coupling", 5.0)
    if not 1 <= duration_ms <= 300:
        raise ValueError("duration_ms must be between 1 and 300")
    if coupling < 0:
        raise ValueError("coupling must be non-negative")
    if input_duration_ms < 0 or input_duration_ms > duration_ms:
        raise ValueError("input_duration_ms must be between 0 and duration_ms")
    if visual_contrast < 0 or visual_contrast > 1.5:
        raise ValueError("visual_contrast must be between 0 and 1.5")
    if visual_coupling < 0:
        raise ValueError("visual_coupling must be non-negative")
    return VisualRunConfig(
        neural=SensorimotorConfig(
            duration_ms=duration_ms,
            coupling_mv_per_synapse=coupling,
            input_duration_ms=input_duration_ms,
            turn_degrees_per_target_spike=turn_degrees,
            forward_step_per_target_spike=forward_step,
        ),
        visual_contrast=visual_contrast,
        visual_coupling_mv_per_synapse=visual_coupling,
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
                self._send(
                    json.dumps({"error": str(error)}).encode("utf-8"),
                    "application/json",
                    400,
                )
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
    print("[flytest] selecting and caching the tactile and visual connectome contexts...")
    model = VisualModel(
        MaleCNSPaths(data_dir),
        neighbor_limit=neighbor_limit,
        max_edges=max_edges,
    )
    server = FlyServer((host, port), model, html_path.read_bytes())
    print(f"[flytest] visual simulation: http://{host}:{port}")
    print(f"[flytest] network: {len(model.node_rows)} nodes, {len(model.edge_rows)} edges")
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
