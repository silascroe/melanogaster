"""Run a small, deterministic wall-blocking arena diagnostic.

This module keeps the existing connectome-backed arena runtime unchanged and
asks one embodied question: does a solid wall block the toy body's requested
forward motion while the world state exposes an obstacle cause? It is a
collision and causal-trace diagnostic, not evidence of biological navigation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from .arena_simulation import ArenaLight, ArenaObstacle, ArenaRunConfig
from .sensorimotor import SensorimotorConfig


class _ArenaRunner(Protocol):
    """The small part of ``VisualModel`` needed by this diagnostic."""

    def run_arena(self, config: ArenaRunConfig) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class WallBlockingConfig:
    """Fixed scenario parameters for one wall-blocking replay."""

    duration_ms: float = 14.0
    network_stage: int = 54
    beacon_x: float = 3.0
    beacon_y: float = 0.0
    beacon_intensity: float = 1.0
    wall_id: str = "wall"
    wall_x: float = 1.5
    wall_y: float = 0.0
    wall_width: float = 1.0
    wall_height: float = 3.0
    body_radius: float = 0.35
    touch_range: float = 0.45
    initial_x: float = 0.0
    initial_y: float = 0.0
    initial_heading_degrees: float = 0.0
    turn_degrees_per_target_spike: float = 15.0
    forward_step_per_target_spike: float = 0.25

    def _arena_config(self) -> ArenaRunConfig:
        return ArenaRunConfig(
            mode="sandbox",
            network_stage=self.network_stage,
            body_radius=self.body_radius,
            touch_range=self.touch_range,
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
            obstacles=(
                ArenaObstacle(
                    self.wall_id,
                    self.wall_x,
                    self.wall_y,
                    self.wall_width,
                    self.wall_height,
                ),
            ),
        )

    def to_arena_config(self) -> ArenaRunConfig:
        self.validate()
        return self._arena_config()

    def validate(self) -> None:
        if not math.isfinite(self.duration_ms) or not 1.0 <= self.duration_ms <= 300.0:
            raise ValueError("duration_ms must be between 1 and 300")
        if self.network_stage not in {54, 100, 250}:
            raise ValueError("network_stage must be 54, 100, or 250")
        if not self.wall_id:
            raise ValueError("wall_id cannot be empty")
        for name, value in (
            ("beacon_x", self.beacon_x),
            ("beacon_y", self.beacon_y),
            ("wall_x", self.wall_x),
            ("wall_y", self.wall_y),
            ("wall_width", self.wall_width),
            ("wall_height", self.wall_height),
            ("body_radius", self.body_radius),
            ("touch_range", self.touch_range),
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
        if not 0.0 < self.body_radius < 2.0:
            raise ValueError("body_radius must be between 0 and 2")
        if not 0.0 <= self.touch_range <= 4.0:
            raise ValueError("touch_range must be between 0 and 4")
        if self.forward_step_per_target_spike <= 0.0:
            raise ValueError("forward_step_per_target_spike must be positive")
        self._arena_config().validate()


def _wall_distance(row: dict[str, Any], config: WallBlockingConfig) -> float:
    half_width = config.wall_width / 2.0
    half_height = config.wall_height / 2.0
    dx = max(abs(float(row["position_x"]) - config.wall_x) - half_width, 0.0)
    dy = max(abs(float(row["position_y"]) - config.wall_y) - half_height, 0.0)
    return math.hypot(dx, dy)


def _causal_trace_summary(trajectory: list[dict[str, Any]], config: WallBlockingConfig) -> dict[str, Any]:
    required_fields = (
        "retina",
        "input_currents",
        "active_spikes",
        "action",
        "position_x",
        "position_y",
        "motion",
        "world_cause",
    )
    complete_frame_count = sum(
        all(field in row for field in required_fields) for row in trajectory
    )
    return {
        "required_fields": list(required_fields),
        "frame_count": len(trajectory),
        "complete_frame_count": complete_frame_count,
        "complete": bool(trajectory) and complete_frame_count == len(trajectory),
        "visual_stimulus_frame_count": sum(
            bool(row.get("visual_stimulus_active")) for row in trajectory
        ),
        "vision_action_frame_count": sum(
            row.get("action_source") == "vision" for row in trajectory
        ),
        "touch_action_frame_count": sum(
            row.get("action_source") == "touch" for row in trajectory
        ),
        "visual_output_spike_frame_count": sum(
            bool(row.get("visual_output_spike")) for row in trajectory
        ),
        "wall_touch_frame_count": sum(
            row.get("touch_source") == "obstacle"
            and row.get("touch_id") == config.wall_id
            for row in trajectory
        ),
        "blocked_frame_count": sum(
            bool((row.get("motion") or {}).get("blocked")) for row in trajectory
        ),
    }


def _trajectory_rows(
    trajectory: list[dict[str, Any]],
    config: WallBlockingConfig,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(trajectory):
        currents = row.get("input_currents", {})
        motion = row.get("motion", {})
        rows.append(
            {
                "frame": index,
                "time_ms": row.get("time_ms"),
                "position_x": row.get("position_x"),
                "position_y": row.get("position_y"),
                "heading_degrees": row.get("heading_degrees"),
                "distance_to_wall": _wall_distance(row, config),
                "requested_x": (row.get("body_requested") or {}).get("x"),
                "requested_y": (row.get("body_requested") or {}).get("y"),
                "blocked": motion.get("blocked", False),
                "collision_ids": "|".join(motion.get("collision_ids", [])),
                "obstacle_id": row.get("obstacle_id"),
                "obstacle_distance": row.get("obstacle_distance"),
                "obstacle_contact": row.get("obstacle_contact", False),
                "nearby_obstacle_ids": "|".join(row.get("nearby_obstacle_ids", [])),
                "touch_source": row.get("touch_source"),
                "touch_id": row.get("touch_id"),
                "touch_urgency": row.get("touch_urgency", 0.0),
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
        "distance_to_wall",
        "requested_x",
        "requested_y",
        "blocked",
        "collision_ids",
        "obstacle_id",
        "obstacle_distance",
        "obstacle_contact",
        "nearby_obstacle_ids",
        "touch_source",
        "touch_id",
        "touch_urgency",
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
        "# Wall blocking",
        "",
        "A deterministic stage-54 replay with a static beacon behind a solid",
        "wall. It asks whether the toy body is physically blocked and whether",
        "the causal trace exposes the obstacle as the world cause.",
        "",
        "## Result",
        "",
        f"- Status: **{status}**",
        f"- Wall: `{scenario['wall_id']}` at `({scenario['wall_x']}, {scenario['wall_y']})`",
        f"- Blocked frames: `{result['blocked_frame_count']}`",
        f"- Collision observed: `{result['collision_observed']}`",
        f"- Obstacle touch observed: `{result['touch_observed']}`",
        f"- Maximum body center x: `{result['maximum_position_x']:.3f}` m",
        f"- Wall front-face limit: `{result['front_face_limit_x']:.3f}` m",
        f"- Wall front face crossed: `{result['front_face_crossed']}`",
        f"- Minimum point-to-wall distance: `{result['minimum_distance_to_wall']:.3f}` m",
        "",
        "## Causal trace",
        "",
        f"The run contains `{causal['frame_count']}` frames; "
        f"`{causal['complete_frame_count']}` include retina, input-current, "
        "spike, action, body-motion, and world-cause fields.",
        f"Visual action frames: `{causal['vision_action_frame_count']}`. "
        f"Touch action frames: `{causal['touch_action_frame_count']}`. "
        f"Wall-touch frames: `{causal['wall_touch_frame_count']}`.",
        "",
        "## What is real, assumed, and demonstrated",
        "",
        "- Real: the staged node and edge selection comes from the local FlyEM "
        "Male CNS v1.0 release.",
        "- Assumed: the 9×5 retina, beacon, point-mass body, wall rectangle, "
        "collision resolver, and action decoder.",
        "- Demonstrated: this fixed replay's collision and causal trace. It does "
        "not demonstrate biological obstacle avoidance or learned navigation.",
        "",
        f"Scenario parameters: `{json.dumps(scenario, sort_keys=True)}`",
        "",
    ]
    return "\n".join(lines)


def run_wall_blocking(
    model: _ArenaRunner,
    *,
    output_dir: Path | None = None,
    config: WallBlockingConfig | None = None,
) -> dict[str, Any]:
    """Run the wall scenario and optionally write compact artifacts."""

    scenario = config or WallBlockingConfig()
    payload = model.run_arena(scenario.to_arena_config())
    trajectory = list(payload.get("trajectory", []))
    if not trajectory:
        raise ValueError("wall blocking replay produced no trajectory frames")

    front_face_limit_x = scenario.wall_x - scenario.wall_width / 2.0 - scenario.body_radius
    position_xs = [float(row["position_x"]) for row in trajectory]
    distances = [_wall_distance(row, scenario) for row in trajectory]
    collision_observed = any(
        scenario.wall_id in (row.get("motion") or {}).get("collision_ids", [])
        for row in trajectory
    )
    blocked_frame_count = sum(
        bool((row.get("motion") or {}).get("blocked")) for row in trajectory
    )
    touch_observed = any(
        row.get("touch_source") == "obstacle" and row.get("touch_id") == scenario.wall_id
        for row in trajectory
    )
    front_face_crossed = any(
        position_x > front_face_limit_x + 1e-9 for position_x in position_xs
    )
    minimum_index = min(range(len(distances)), key=distances.__getitem__)
    result = {
        "success": bool(
            collision_observed
            and blocked_frame_count > 0
            and touch_observed
            and not front_face_crossed
        ),
        "collision_observed": collision_observed,
        "blocked_frame_count": blocked_frame_count,
        "touch_observed": touch_observed,
        "front_face_crossed": front_face_crossed,
        "front_face_limit_x": front_face_limit_x,
        "maximum_position_x": max(position_xs),
        "minimum_distance_to_wall": min(distances),
        "minimum_distance_frame": minimum_index,
        "minimum_distance_time_ms": trajectory[minimum_index]["time_ms"],
    }
    causal_trace = _causal_trace_summary(trajectory, scenario)
    summary: dict[str, Any] = {
        "experiment": "deterministic wall blocking",
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
            "The beacon is static, the threat set is empty, and the wall is an explicit toy AABB.",
            "Success means a collision and obstacle touch are observed without crossing the wall's front face.",
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
    parser = argparse.ArgumentParser(description="Run the FlyTest wall-blocking diagnostic")
    parser.add_argument("--data-dir", type=Path, default=Path("data/working/male-cns-v1.0"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/diagnostics/wall-blocking"),
    )
    parser.add_argument("--duration-ms", type=float, default=14.0)
    parser.add_argument("--stage", type=int, default=54)
    parser.add_argument("--beacon-x", type=float, default=3.0)
    parser.add_argument("--beacon-y", type=float, default=0.0)
    parser.add_argument("--wall-x", type=float, default=1.5)
    parser.add_argument("--wall-y", type=float, default=0.0)
    parser.add_argument("--wall-width", type=float, default=1.0)
    parser.add_argument("--wall-height", type=float, default=3.0)
    args = parser.parse_args()

    from .data import MaleCNSPaths
    from .visual_simulation import VisualModel

    model = VisualModel(MaleCNSPaths(args.data_dir), neighbor_limit=24, max_edges=500)
    summary = run_wall_blocking(
        model,
        output_dir=args.output,
        config=WallBlockingConfig(
            duration_ms=args.duration_ms,
            network_stage=args.stage,
            beacon_x=args.beacon_x,
            beacon_y=args.beacon_y,
            wall_x=args.wall_x,
            wall_y=args.wall_y,
            wall_width=args.wall_width,
            wall_height=args.wall_height,
        ),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["result"]["success"]:
        raise SystemExit("wall blocking criterion was not met")


if __name__ == "__main__":
    main()
