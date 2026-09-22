"""Run a small, deterministic beacon-approach arena diagnostic.

This module deliberately sits above the production arena model. It freezes a
static beacon in an otherwise empty sandbox, reuses the existing
connectome-backed visual pathway, and writes a compact causal trace. The
scenario is a calibration question for the current toy controller, not a new
behavior model or a claim that the fly has learned attraction to light.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from .arena_simulation import ARENA_NETWORK_STAGES, ArenaLight, ArenaRunConfig
from .sensorimotor import SensorimotorConfig


class _ArenaRunner(Protocol):
    """The small part of ``VisualModel`` needed by this diagnostic."""

    def run_arena(self, config: ArenaRunConfig) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class BeaconApproachConfig:
    """Fixed scenario parameters for one beacon-approach replay."""

    duration_ms: float = 30.0
    network_stage: int = 54
    beacon_x: float = 2.0
    beacon_y: float = 2.0
    beacon_intensity: float = 1.0
    approach_threshold: float = 1.5
    initial_x: float = 0.0
    initial_y: float = 0.0
    initial_heading_degrees: float = 0.0
    turn_degrees_per_target_spike: float = 15.0
    forward_step_per_target_spike: float = 0.25

    def _arena_config(self) -> ArenaRunConfig:
        """Build the production arena config without validating twice."""

        return ArenaRunConfig(
            mode="sandbox",
            network_stage=self.network_stage,
            neural=SensorimotorConfig(
                duration_ms=self.duration_ms,
                turn_degrees_per_target_spike=self.turn_degrees_per_target_spike,
                forward_step_per_target_spike=self.forward_step_per_target_spike,
                initial_heading_degrees=self.initial_heading_degrees,
                initial_x=self.initial_x,
                initial_y=self.initial_y,
            ),
            lights=(
                ArenaLight(
                    "beacon",
                    self.beacon_x,
                    self.beacon_y,
                    self.beacon_intensity,
                ),
            ),
            threats=(),
            obstacles=(),
        )

    def to_arena_config(self) -> ArenaRunConfig:
        """Build the production arena config without changing its defaults."""

        self.validate()
        return self._arena_config()

    def validate(self) -> None:
        if not math.isfinite(self.duration_ms) or not 1.0 <= self.duration_ms <= 300.0:
            raise ValueError("duration_ms must be between 1 and 300")
        if self.network_stage not in ARENA_NETWORK_STAGES:
            raise ValueError(f"network_stage must be one of {ARENA_NETWORK_STAGES}")
        for name, value in (
            ("beacon_x", self.beacon_x),
            ("beacon_y", self.beacon_y),
            ("initial_x", self.initial_x),
            ("initial_y", self.initial_y),
            ("initial_heading_degrees", self.initial_heading_degrees),
            ("turn_degrees_per_target_spike", self.turn_degrees_per_target_spike),
            ("forward_step_per_target_spike", self.forward_step_per_target_spike),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if not 0.0 < self.beacon_intensity <= 1.5:
            raise ValueError("beacon_intensity must be between 0 and 1.5")
        if not 0.0 < self.approach_threshold:
            raise ValueError("approach_threshold must be positive")
        if self.forward_step_per_target_spike <= 0.0:
            raise ValueError("forward_step_per_target_spike must be positive")
        self._arena_config().validate()


def _distance_to_beacon(row: dict[str, Any], config: BeaconApproachConfig) -> float:
    return math.hypot(
        config.beacon_x - float(row["position_x"]),
        config.beacon_y - float(row["position_y"]),
    )


def _causal_trace_summary(trajectory: list[dict[str, Any]]) -> dict[str, Any]:
    required_fields = (
        "retina",
        "input_currents",
        "active_spikes",
        "action",
        "position_x",
        "position_y",
    )
    complete_frame_count = sum(
        all(field in row for field in required_fields) for row in trajectory
    )
    vision_action_frame_count = sum(
        row.get("action_source") == "vision" for row in trajectory
    )
    visual_frame_count = sum(
        bool(row.get("visual_stimulus_active")) for row in trajectory
    )
    return {
        "required_fields": list(required_fields),
        "frame_count": len(trajectory),
        "complete_frame_count": complete_frame_count,
        "complete": bool(trajectory) and complete_frame_count == len(trajectory),
        "visual_stimulus_frame_count": visual_frame_count,
        "vision_action_frame_count": vision_action_frame_count,
        "visual_output_spike_frame_count": sum(
            bool(row.get("visual_output_spike")) for row in trajectory
        ),
    }


def _trajectory_rows(
    trajectory: list[dict[str, Any]],
    config: BeaconApproachConfig,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(trajectory):
        currents = row.get("input_currents", {})
        rows.append(
            {
                "frame": index,
                "time_ms": row.get("time_ms"),
                "position_x": row.get("position_x"),
                "position_y": row.get("position_y"),
                "heading_degrees": row.get("heading_degrees"),
                "distance_to_beacon": _distance_to_beacon(row, config),
                "retina_centroid_x": row.get("retina_centroid_x"),
                "retina_max": row.get("retina_max"),
                "visual_stimulus_active": row.get("visual_stimulus_active"),
                "visual_output_spike": row.get("visual_output_spike"),
                "action": row.get("action"),
                "action_source": row.get("action_source"),
                "turn_command_degrees": row.get("turn_command_degrees"),
                "forward_step": row.get("forward_step"),
                "active_spike_count": len(row.get("active_spikes", [])),
                "visual_left_current": currents.get("visual_left", 0.0),
                "visual_center_current": currents.get("visual_center", 0.0),
                "visual_right_current": currents.get("visual_right", 0.0),
                "visual_motion_current": currents.get("visual_motion", 0.0),
                "visual_looming_current": currents.get("visual_looming", 0.0),
            }
        )
    return rows


def _write_trajectory_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "frame",
        "time_ms",
        "position_x",
        "position_y",
        "heading_degrees",
        "distance_to_beacon",
        "retina_centroid_x",
        "retina_max",
        "visual_stimulus_active",
        "visual_output_spike",
        "action",
        "action_source",
        "turn_command_degrees",
        "forward_step",
        "active_spike_count",
        "visual_left_current",
        "visual_center_current",
        "visual_right_current",
        "visual_motion_current",
        "visual_looming_current",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _report_markdown(summary: dict[str, Any]) -> str:
    scenario = summary["scenario"]
    result = summary["result"]
    causal = summary["causal_trace"]
    status = "PASS" if result["success"] else "FAIL"
    lines = [
        "# Beacon approach",
        "",
        "A deterministic, obstacle-free replay of the existing FlyTest arena.",
        "It asks one narrow question: does the current visual pathway drive the",
        "toy body inside the configured distance threshold at any point in the",
        "replay?",
        "",
        "## Result",
        "",
        f"- Status: **{status}**",
        f"- Initial distance: `{result['initial_distance_to_beacon']:.3f}` m",
        f"- Closest distance: `{result['minimum_distance_to_beacon']:.3f}` m",
        f"- Final distance: `{result['final_distance_to_beacon']:.3f}` m",
        f"- Distance threshold: `{result['approach_threshold']:.3f}` m",
        f"- Threshold reached: `{result['threshold_reached']}`",
        f"- Distance decreased: `{result['distance_decreased']}`",
        f"- Closest frame: `{result['minimum_distance_frame']}`",
        "",
        "## Causal trace",
        "",
        f"The run contains `{causal['frame_count']}` frames; "
        f"`{causal['complete_frame_count']}` include the required retina, "
        "input-current, spike, action, and body-position fields.",
        f"Visual stimulus frames: `{causal['visual_stimulus_frame_count']}`. "
        f"Frames with a vision-sourced action: `{causal['vision_action_frame_count']}`. "
        f"Frames with a visual output spike: `{causal['visual_output_spike_frame_count']}`.",
        "",
        "## What is real, assumed, and demonstrated",
        "",
        "- Real: the staged node and edge selection comes from the local FlyEM "
        "Male CNS v1.0 release.",
        "- Assumed: the 9×5 retina, static beacon, point-mass body, movement "
        "step, turn decoder, and approach threshold.",
        "- Demonstrated: this one fixed replay's observed trajectory and causal "
        "trace. It does not demonstrate a biological light-seeking behavior or "
        "a learned controller.",
        "",
        f"Scenario parameters: `{json.dumps(scenario, sort_keys=True)}`",
        "",
        "The closest-distance criterion is intentional: the current toy action "
        "decoder is a reflex mapping, so the body may pass near the beacon and "
        "then turn away. Sustained tracking is a separate experiment.",
        "",
    ]
    return "\n".join(lines)


def run_beacon_approach(
    model: _ArenaRunner,
    *,
    output_dir: Path | None = None,
    config: BeaconApproachConfig | None = None,
) -> dict[str, Any]:
    """Run the beacon scenario and optionally write compact artifacts."""

    scenario = config or BeaconApproachConfig()
    payload = model.run_arena(scenario.to_arena_config())
    trajectory = list(payload.get("trajectory", []))
    if not trajectory:
        raise ValueError("beacon approach replay produced no trajectory frames")

    distances = [_distance_to_beacon(row, scenario) for row in trajectory]
    initial_distance = math.hypot(
        scenario.beacon_x - scenario.initial_x,
        scenario.beacon_y - scenario.initial_y,
    )
    minimum_index = min(range(len(distances)), key=distances.__getitem__)
    minimum_distance = distances[minimum_index]
    final_distance = distances[-1]
    distance_decreased = minimum_distance < initial_distance - 1e-9
    threshold_reached = minimum_distance <= scenario.approach_threshold + 1e-9
    causal_trace = _causal_trace_summary(trajectory)
    result = {
        "success": bool(distance_decreased and threshold_reached),
        "distance_decreased": distance_decreased,
        "threshold_reached": threshold_reached,
        "initial_distance_to_beacon": initial_distance,
        "minimum_distance_to_beacon": minimum_distance,
        "final_distance_to_beacon": final_distance,
        "minimum_distance_frame": minimum_index,
        "minimum_distance_time_ms": trajectory[minimum_index]["time_ms"],
        "approach_threshold": scenario.approach_threshold,
        "distance_reduction": initial_distance - minimum_distance,
        "distance_reduction_fraction": (
            (initial_distance - minimum_distance) / initial_distance
            if initial_distance > 0.0
            else 0.0
        ),
    }
    summary: dict[str, Any] = {
        "experiment": "deterministic beacon approach",
        "dataset": payload.get("dataset", {}),
        "scenario": asdict(scenario),
        "network": {
            key: payload.get("network", {}).get(key)
            for key in (
                "stage",
                "requested_node_count",
                "actual_node_count",
                "edge_count",
                "unified",
            )
        },
        "result": result,
        "causal_trace": causal_trace,
        "replay_digest": payload.get("replay_digest"),
        "notes": [
            "The connectome stage and native-sign LIF runtime are reused unchanged.",
            "The beacon is static and the sandbox contains no threats or obstacles.",
            "Success means the body gets closer than its start and reaches the configured threshold at least once.",
        ],
    }

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        trajectory_path = output_dir / "trajectory.csv"
        report_path = output_dir / "report.md"
        summary_path = output_dir / "summary.json"
        _write_trajectory_csv(trajectory_path, _trajectory_rows(trajectory, scenario))
        summary["outputs"] = {
            "summary": str(summary_path),
            "trajectory": str(trajectory_path),
            "report": str(report_path),
        }
        report_path.write_text(_report_markdown(summary), encoding="utf-8")
        summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the FlyTest beacon-approach diagnostic")
    parser.add_argument("--data-dir", type=Path, default=Path("data/working/male-cns-v1.0"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/diagnostics/beacon-approach"),
    )
    parser.add_argument("--duration-ms", type=float, default=30.0)
    parser.add_argument("--threshold", type=float, default=1.5)
    parser.add_argument("--beacon-x", type=float, default=2.0)
    parser.add_argument("--beacon-y", type=float, default=2.0)
    parser.add_argument("--stage", type=int, default=54)
    args = parser.parse_args()

    from .data import MaleCNSPaths
    from .visual_simulation import VisualModel

    model = VisualModel(MaleCNSPaths(args.data_dir), neighbor_limit=24, max_edges=500)
    summary = run_beacon_approach(
        model,
        output_dir=args.output,
        config=BeaconApproachConfig(
            duration_ms=args.duration_ms,
            network_stage=args.stage,
            beacon_x=args.beacon_x,
            beacon_y=args.beacon_y,
            approach_threshold=args.threshold,
        ),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["result"]["success"]:
        raise SystemExit("beacon approach criterion was not met")


if __name__ == "__main__":
    main()
