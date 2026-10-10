"""Run a compact real-data acceptance check for the 1,024-node arena stage.

This diagnostic measures the existing Python/NumPy runtime at the first scale
target chosen for the project. It proves graph selection, deterministic batch
replay, and the live session contract without committing the full trajectory.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from .arena_simulation import ArenaRunConfig
from .data import MaleCNSPaths
from .sensorimotor import SensorimotorConfig
from .visual_simulation import VisualModel


TARGET_STAGE = 1024
REQUIRED_FRAME_FIELDS = (
    "retina",
    "input_currents",
    "active_spikes",
    "action",
    "position_x",
    "position_y",
)


class _ArenaModel(Protocol):
    def run_arena(self, config: ArenaRunConfig) -> dict[str, Any]:
        ...

    def create_arena_session(self, config: ArenaRunConfig) -> Any:
        ...


@dataclass(frozen=True)
class ArenaScaleConfig:
    """Fixed workload for the first serious arena scale measurement."""

    network_stage: int = TARGET_STAGE
    duration_ms: float = 24.0

    def to_arena_config(self) -> ArenaRunConfig:
        self.validate()
        return ArenaRunConfig(
            mode="demo",
            network_stage=self.network_stage,
            neural=SensorimotorConfig(
                duration_ms=self.duration_ms,
                coupling_mv_per_synapse=3.0,
                input_duration_ms=0.0,
            ),
        )

    def validate(self) -> None:
        if self.network_stage != TARGET_STAGE:
            raise ValueError(
                f"arena scale diagnostic requires network_stage {TARGET_STAGE}"
            )
        if not 1.0 <= self.duration_ms <= 300.0:
            raise ValueError("duration_ms must be between 1 and 300")


def _require_network_gate(network: dict[str, Any], requested_stage: int) -> None:
    stage = int(network.get("stage", -1))
    actual = int(network.get("actual_node_count", 0))
    if stage != requested_stage:
        raise ValueError(f"arena returned stage {stage}, expected {requested_stage}")
    if actual < 1000:
        raise ValueError(f"arena scale graph must contain at least 1000 nodes, got {actual}")
    if actual != requested_stage:
        raise ValueError(
            f"arena scale graph must contain exactly {requested_stage} nodes, got {actual}"
        )
    if not bool(network.get("unified")):
        raise ValueError("arena scale graph must be a unified induced graph")
    if int(network.get("edge_count", 0)) <= 0:
        raise ValueError("arena scale graph must contain induced edges")


def _causal_trace_complete(trajectory: Any) -> bool:
    if not isinstance(trajectory, list) or not trajectory:
        return False
    return all(
        isinstance(frame, dict) and all(field in frame for field in REQUIRED_FRAME_FIELDS)
        for frame in trajectory
    )


def _compact_network(network: dict[str, Any]) -> dict[str, Any]:
    """Keep graph counts while dropping large population/selection inventories."""

    compact = {
        key: network[key]
        for key in (
            "stage",
            "requested_node_count",
            "target_node_count",
            "actual_node_count",
            "edge_count",
            "unified",
        )
        if key in network
    }
    channels = network.get("channels")
    if isinstance(channels, dict):
        compact["channels"] = {
            str(name): {
                key: value
                for key, value in channel.items()
                if key in {"node_count", "edge_count"}
            }
            for name, channel in channels.items()
            if isinstance(channel, dict)
        }
    return compact


def _live_payload(config: ArenaRunConfig) -> dict[str, Any]:
    return {
        "time_ms": 0.0,
        "body": {"x": 0.0, "y": 0.0, "heading_degrees": 0.0},
        "lights": [light.as_dict() for light in config.lights],
        "threats": [threat.as_dict() for threat in config.threats],
    }


def _next_live_payload(previous: dict[str, Any]) -> dict[str, Any]:
    return {
        "time_ms": previous["next_time_ms"],
        "body": previous["next_body"],
        "lights": previous["next_lights"],
        "threats": previous["next_threats"],
    }


def _write_report(output_dir: Path, summary: dict[str, Any]) -> None:
    network = summary["network"]
    timing = summary["timing"]
    live = summary["live"]
    result = summary["result"]
    lines = [
        "# 1,024-node arena acceptance",
        "",
        "This is a scale and interface check for the existing Python/NumPy arena runtime, not a biological behavior claim.",
        "",
        f"- Requested stage: `{network['requested_node_count']}`",
        f"- Actual unique nodes: `{network['actual_node_count']}`",
        f"- Induced edges: `{network['edge_count']}`",
        f"- Unified graph: `{network['unified']}`",
        f"- Initial build and replay: `{timing['initial_build_and_replay_seconds']:.3f}` s",
        f"- Cached replay: `{timing['cached_replay_seconds']:.3f}` s",
        f"- Live steps: `{live['step_count']}`",
        f"- Live step timings: `{live['step_timings_seconds']}` s",
        f"- Batch replay digest match: `{result['replay_digest_match']}`",
        f"- Causal trace complete: `{result['causal_trace_complete']}`",
        f"- Acceptance result: `{result['success']}`",
        "",
        "The first timing includes graph expansion, induced-edge construction, runtime compilation, and one replay. The second timing measures the cached stage. No full trajectory is stored in this compact artifact.",
    ]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_arena_scale(
    model: _ArenaModel,
    *,
    output_dir: Path,
    config: ArenaScaleConfig | None = None,
) -> dict[str, Any]:
    """Run the fixed 1,024-node workload and write compact acceptance evidence."""

    scale_config = config or ArenaScaleConfig()
    arena_config = scale_config.to_arena_config()

    initial_start = time.perf_counter()
    first = model.run_arena(arena_config)
    initial_seconds = time.perf_counter() - initial_start
    network_payload = dict(first.get("network") or {})
    _require_network_gate(network_payload, scale_config.network_stage)
    network = _compact_network(network_payload)
    if not _causal_trace_complete(first.get("trajectory")):
        raise ValueError("arena scale batch replay does not contain a complete causal trace")

    cached_start = time.perf_counter()
    second = model.run_arena(arena_config)
    cached_seconds = time.perf_counter() - cached_start
    first_digest = str(first.get("replay_digest", ""))
    second_digest = str(second.get("replay_digest", ""))
    replay_digest_match = bool(first_digest) and first_digest == second_digest
    if not replay_digest_match:
        raise ValueError("arena scale batch replay digest changed between identical runs")

    session = model.create_arena_session(arena_config)
    first_live_start = time.perf_counter()
    live_first = session.step(_live_payload(arena_config))
    first_live_seconds = time.perf_counter() - first_live_start
    second_live_start = time.perf_counter()
    live_second = session.step(_next_live_payload(live_first))
    second_live_seconds = time.perf_counter() - second_live_start
    for live_frame in (live_first, live_second):
        if not isinstance(live_frame.get("frame"), dict):
            raise ValueError("arena scale live session returned no frame")

    summary = {
        "experiment": "real 1024-node arena scale acceptance",
        "dataset": {
            "name": "FlyEM Male CNS",
            "release": "v1.0",
            "source_manifest": "data/metadata/source_manifest.json",
        },
        "network": network,
        "timing": {
            "initial_build_and_replay_seconds": initial_seconds,
            "cached_replay_seconds": cached_seconds,
        },
        "live": {
            "step_count": 2,
            "step_indices": [live_first.get("step_index"), live_second.get("step_index")],
            "step_timings_seconds": [first_live_seconds, second_live_seconds],
        },
        "result": {
            "success": True,
            "replay_digest": first_digest,
            "replay_digest_match": replay_digest_match,
            "causal_trace_complete": True,
            "batch_frame_count": len(first["trajectory"]),
        },
        "configuration": asdict(scale_config),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_report(output_dir, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the real FlyTest 1,024-node arena acceptance check")
    parser.add_argument("--data-dir", type=Path, default=Path("data/working/male-cns-v1.0"))
    parser.add_argument("--output", type=Path, default=Path("outputs/diagnostics/arena-1024"))
    parser.add_argument("--stage", type=int, default=TARGET_STAGE)
    parser.add_argument("--duration-ms", type=float, default=24.0)
    args = parser.parse_args()
    model = VisualModel(MaleCNSPaths(args.data_dir))
    summary = run_arena_scale(
        model,
        output_dir=args.output,
        config=ArenaScaleConfig(network_stage=args.stage, duration_ms=args.duration_ms),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
