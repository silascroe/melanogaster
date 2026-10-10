from __future__ import annotations

from pathlib import Path

from flytest.arena_simulation import ArenaRunConfig
from flytest.wall_blocking import WallBlockingConfig, run_wall_blocking


def _frame(
    *,
    time_ms: float,
    position_x: float,
    blocked: bool,
    collision_ids: tuple[str, ...] = (),
    wall_visible: bool = False,
) -> dict[str, object]:
    touch_source = "obstacle" if wall_visible else None
    touch_id = "wall" if wall_visible else None
    return {
        "time_ms": time_ms,
        "position_x": position_x,
        "position_y": 0.0,
        "heading_degrees": 0.0,
        "retina": [0.5],
        "input_currents": {"visual_center": 1.0},
        "active_spikes": [{"body_id": 1}],
        "action": "forward" if not wall_visible else "escape_left",
        "action_source": "vision" if not wall_visible else "touch",
        "visual_stimulus_active": True,
        "visual_output_spike": True,
        "retina_centroid_x": 0.0,
        "retina_max": 0.5,
        "turn_command_degrees": 0.0,
        "forward_step": 0.25,
        "motion": {
            "blocked": blocked,
            "collision_ids": list(collision_ids),
            "boundary_contacts": [],
        },
        "world_cause": {
            "obstacle_id": touch_id,
            "obstacle_contact": False,
            "touch_source": touch_source,
            "touch_id": touch_id,
            "touch_urgency": 0.8 if wall_visible else 0.0,
        },
        "obstacle_id": touch_id,
        "obstacle_distance": 0.35 if wall_visible else None,
        "obstacle_contact": False,
        "nearby_obstacle_ids": ["wall"] if wall_visible else [],
        "touch_source": touch_source,
        "touch_id": touch_id,
        "touch_urgency": 0.8 if wall_visible else 0.0,
    }


def test_wall_blocking_writes_causal_artifacts(tmp_path: Path) -> None:
    class StubArenaModel:
        def run_arena(self, config: ArenaRunConfig) -> dict[str, object]:
            assert config.mode == "sandbox"
            assert config.threats == ()
            assert len(config.lights) == 1
            assert len(config.obstacles) == 1
            assert config.obstacles[0].obstacle_id == "wall"
            return {
                "dataset": {"release": "fixture"},
                "network": {
                    "stage": 54,
                    "requested_node_count": 54,
                    "actual_node_count": 2,
                    "edge_count": 1,
                    "unified": False,
                },
                "replay_digest": "fixture-digest",
                "trajectory": [
                    _frame(time_ms=0.0, position_x=0.0, blocked=False),
                    _frame(
                        time_ms=1.0,
                        position_x=0.6,
                        blocked=True,
                        collision_ids=("wall",),
                        wall_visible=True,
                    ),
                ],
            }

    output_dir = tmp_path / "wall-blocking"
    summary = run_wall_blocking(
        StubArenaModel(),
        output_dir=output_dir,
        config=WallBlockingConfig(
            beacon_x=3.0,
            beacon_y=0.0,
            wall_x=1.5,
            wall_y=0.0,
            wall_width=1.0,
            wall_height=3.0,
            duration_ms=2.0,
        ),
    )

    assert summary["experiment"] == "deterministic wall blocking"
    assert summary["result"]["success"]
    assert summary["result"]["collision_observed"]
    assert summary["result"]["touch_observed"]
    assert summary["result"]["front_face_crossed"] is False
    assert summary["causal_trace"]["complete"]
    assert (output_dir / "summary.json").is_file()
    assert (output_dir / "trajectory.csv").is_file()
    report = (output_dir / "report.md").read_text(encoding="utf-8")
    assert "Wall blocking" in report
    assert "front face" in report
