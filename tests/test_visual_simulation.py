import json
from dataclasses import replace
from pathlib import Path

import pyarrow as pa
import pyarrow.feather as feather
import pytest

from flytest.data import (
    ANNOTATION_FILENAME,
    NEUROTRANSMITTER_FILENAME,
    WEIGHTS_FILENAME,
    MaleCNSPaths,
)
from flytest.analysis import select_induced_network, select_multihop_network
from flytest.arena_circuit import ArenaCircuitRuntime, ArenaStage
from flytest.arena_simulation import (
    ArenaLight,
    ArenaMemoryConfig,
    ArenaObstacle,
    ArenaRunConfig,
    ArenaThreat,
    ArenaWorld,
    _ArenaMemoryState,
    _feature_currents,
    advance_arena_objects,
    resolve_body_motion,
)
from flytest.simulation import LIFConfig
from flytest.sensorimotor import SensorimotorConfig
from flytest.visual_simulation import VisualModel, VisualRunConfig


def _write_visual_fixture(tmp_path: Path) -> MaleCNSPaths:
    data_dir = tmp_path / "male-cns-v1.0"
    data_dir.mkdir()
    body_ids = [1, 2, 3, 10, 11, 12]
    feather.write_feather(
        pa.table(
            {
                "bodyId": body_ids,
                "type": ["SN", "IN", "DN", "LC", "OL", "DN"],
                "instance": ["SN_L", "IN_L", "DN_L", "LC_R", "OL_R", "DN_R"],
                "status": ["Traced"] * len(body_ids),
                "superclass": [
                    "vnc_sensory",
                    "vnc_intrinsic",
                    "descending_neuron",
                    "visual_projection",
                    "ol_intrinsic",
                    "descending_neuron",
                ],
                "class": [None] * len(body_ids),
                "somaSide": ["L", "L", "L", "R", "R", "R"],
            }
        ),
        data_dir / ANNOTATION_FILENAME,
    )
    feather.write_feather(
        pa.table(
            {
                "body": body_ids,
                "cell_type": ["SN", "IN", "DN", "LC", "OL", "DN"],
                "predicted_nt": ["acetylcholine"] * len(body_ids),
                "predicted_nt_confidence": [0.9] * len(body_ids),
                "consensus_nt": ["acetylcholine"] * len(body_ids),
                "total_nt_predictions": [10] * len(body_ids),
            }
        ),
        data_dir / NEUROTRANSMITTER_FILENAME,
    )
    feather.write_feather(
        pa.table(
            {
                "body_pre": [1, 2, 2, 10, 11, 11],
                "body_post": [2, 3, 1, 11, 12, 10],
                "weight": [10, 10, 5, 10, 10, 5],
            }
        ),
        data_dir / WEIGHTS_FILENAME,
    )
    return MaleCNSPaths(data_dir)


def _write_multihop_fixture(tmp_path: Path) -> MaleCNSPaths:
    data_dir = tmp_path / "male-cns-expansion"
    data_dir.mkdir()
    body_ids = list(range(1, 9))
    feather.write_feather(
        pa.table(
            {
                "bodyId": body_ids,
                "type": ["SN", "IN", "DN", "IN", "IN", "DN", "SN", "IN"],
                "instance": [f"N{body_id}_L" for body_id in body_ids],
                "status": ["Traced"] * len(body_ids),
                "superclass": [
                    "vnc_sensory",
                    "vnc_intrinsic",
                    "descending_neuron",
                    "vnc_intrinsic",
                    "vnc_intrinsic",
                    "descending_neuron",
                    "vnc_sensory",
                    "vnc_intrinsic",
                ],
                "class": [None] * len(body_ids),
                "somaSide": ["L"] * len(body_ids),
            }
        ),
        data_dir / ANNOTATION_FILENAME,
    )
    feather.write_feather(
        pa.table(
            {
                "body": body_ids,
                "cell_type": ["N"] * len(body_ids),
                "predicted_nt": ["acetylcholine"] * len(body_ids),
                "predicted_nt_confidence": [0.9] * len(body_ids),
                "consensus_nt": ["acetylcholine"] * len(body_ids),
                "total_nt_predictions": [10] * len(body_ids),
            }
        ),
        data_dir / NEUROTRANSMITTER_FILENAME,
    )
    feather.write_feather(
        pa.table(
            {
                "body_pre": [1, 2, 2, 3, 4, 5, 6, 7],
                "body_post": [2, 3, 4, 4, 5, 6, 5, 8],
                "weight": [10, 10, 9, 8, 7, 6, 5, 4],
            }
        ),
        data_dir / WEIGHTS_FILENAME,
    )
    return MaleCNSPaths(data_dir)


def test_visual_model_runs_touch_and_vision_into_one_body(tmp_path: Path) -> None:
    model = VisualModel(_write_visual_fixture(tmp_path), neighbor_limit=4, max_edges=50)
    payload = model.run(
        VisualRunConfig(
            neural=SensorimotorConfig(
                duration_ms=6.0,
                tau_ms=1.0,
                rest_mv=0.0,
                threshold_mv=1.0,
                reset_mv=0.0,
                refractory_ms=2.0,
                coupling_mv_per_synapse=0.2,
                input_current_mv=2.0,
                input_start_ms=0.0,
                input_duration_ms=1.0,
                turn_degrees_per_target_spike=20.0,
                forward_step_per_target_spike=2.0,
            ),
            visual_contrast=1.0,
            visual_coupling_mv_per_synapse=0.2,
            visual_target_x=7.0,
            visual_target_y=4.0,
        )
    )

    assert payload["network"]["node_count"] >= 6
    assert payload["network"]["edge_count"] >= 4
    assert payload["network"]["channels"].keys() == {"touch", "vision"}
    assert {node["channel"] for node in payload["nodes"]} == {"touch", "vision"}
    assert len(payload["trajectory"]) == 6
    assert payload["outcome"]["touch_target_spike_count"] == 1
    assert payload["outcome"]["visual_target_spike_count"] == 1
    assert payload["outcome"]["target_spike_count"] == 2
    assert payload["outcome"]["turn_event_count"] == 1
    assert payload["outcome"]["final_heading_degrees"] == pytest.approx(40.0)
    assert payload["outcome"]["final_position"] == [
        pytest.approx(2.0 * 0.7660444431),
        pytest.approx(2.0 * 0.6427876097),
    ]

    active = payload["spikes_by_time"]
    assert any(event["channel"] == "touch" for frame in active for event in frame)
    assert any(event["channel"] == "vision" for frame in active for event in frame)


def _arena_fixture_config(
    *, threats: tuple[ArenaThreat, ...] = (),
) -> ArenaRunConfig:
    return ArenaRunConfig(
        mode="sandbox",
        neural=SensorimotorConfig(
            duration_ms=8,
            tau_ms=1.0,
            rest_mv=0.0,
            threshold_mv=1.0,
            reset_mv=0.0,
            refractory_ms=2.0,
            coupling_mv_per_synapse=0.2,
            input_current_mv=2.0,
            turn_degrees_per_target_spike=20.0,
            forward_step_per_target_spike=1.0,
        ),
        visual_coupling_mv_per_synapse=0.2,
        lights=(ArenaLight("left-light", 1.0, 1.0, 1.0),),
        threats=threats,
    )


def test_arena_retina_reports_light_direction_and_touch_proximity() -> None:
    config = ArenaRunConfig(
        neural=SensorimotorConfig(duration_ms=8),
        lights=(ArenaLight("left", 1.0, 1.0),),
        threats=(ArenaThreat("threat", 0.5, 0.0, radius=1.0),),
    )
    observation = ArenaWorld(config).observe(
        0.0,
        position_x=0.0,
        position_y=0.0,
        heading_degrees=0.0,
    )

    assert observation.visual_active
    assert observation.retina_max > 0
    assert observation.retina_centroid_x < 0
    assert observation.touch_active
    assert observation.threat_id == "threat"


def test_arena_replays_visual_path_and_is_deterministic(tmp_path: Path) -> None:
    model = VisualModel(_write_visual_fixture(tmp_path), neighbor_limit=4, max_edges=50)
    request = _arena_fixture_config()
    first = model.run_arena(request)
    second = model.run_arena(request)

    assert first == second
    assert first["schema_version"] == 2
    assert first["environment"]["retina"]["width"] == 9
    assert len(first["trajectory"]) == 8
    assert first["outcome"]["visual_target_spike_count"] >= 1
    assert any(row["action_source"] == "vision" for row in first["trajectory"])
    assert first["trajectory"][0]["retina_centroid_x"] < 0


def test_live_arena_session_keeps_neural_state_and_matches_batch_prefix(tmp_path: Path) -> None:
    model = VisualModel(_write_visual_fixture(tmp_path), neighbor_limit=4, max_edges=50)
    config = _arena_fixture_config()
    batch = model.run_arena(config)
    session = model.create_arena_session(config)

    first = session.step(
        {
            "time_ms": 0.0,
            "body": {"x": 0.0, "y": 0.0, "heading_degrees": 0.0},
            "lights": [light.as_dict() for light in config.lights],
            "threats": [],
        }
    )
    second = session.step(
        {
            "time_ms": 1.0,
            "body": first["next_body"],
            "lights": first["next_lights"],
            "threats": [],
        }
    )

    assert session.metadata()["protocol"] == "godot_world_to_python_neural_step"
    assert first["step_index"] == 0
    assert second["step_index"] == 1
    assert first["frame"]["world_source"] == "external_client"
    for live_frame, batch_frame in zip(
        (first["frame"], second["frame"]), batch["trajectory"][:2]
    ):
        assert live_frame["action"] == batch_frame["action"]
        assert live_frame["active_spikes"] == batch_frame["active_spikes"]
        assert live_frame["input_currents"] == batch_frame["input_currents"]
        assert live_frame["retina"] == batch_frame["retina"]


def test_live_arena_session_rejects_clock_and_object_drift(tmp_path: Path) -> None:
    model = VisualModel(_write_visual_fixture(tmp_path), neighbor_limit=4, max_edges=50)
    config = _arena_fixture_config()
    session = model.create_arena_session(config)

    with pytest.raises(ValueError, match="time_ms"):
        session.step({"time_ms": 4.0, "body": {"x": 0, "y": 0}})
    with pytest.raises(ValueError, match="object IDs"):
        session.step(
            {
                "time_ms": 0.0,
                "body": {"x": 0, "y": 0},
                "lights": [{"id": "wrong", "x": 0, "y": 0}],
                "threats": [],
            }
        )


def test_arena_touch_target_takes_priority_over_visual_target(tmp_path: Path) -> None:
    model = VisualModel(_write_visual_fixture(tmp_path), neighbor_limit=4, max_edges=50)
    request = _arena_fixture_config(
        threats=(ArenaThreat(
            "timed-threat",
            0.0,
            1.0,
            radius=1.0,
            trigger="timed",
            active_start_ms=0.0,
            active_end_ms=3.0,
        ),),
    )
    payload = model.run_arena(request)

    assert payload["outcome"]["touch_target_spike_count"] >= 1
    assert any(row["action"].startswith("escape_") for row in payload["trajectory"])
    assert all(
        row["action_source"] == "touch"
        for row in payload["trajectory"]
        if row["touch_target_spike"]
    )


def test_arena_request_rejects_invalid_retina_dimensions() -> None:
    with pytest.raises(ValueError, match="retina dimensions"):
        ArenaRunConfig.from_mapping({"mode": "sandbox", "retina": {"width": 2}})


def test_stage_54_is_the_legacy_two_context_control(tmp_path: Path) -> None:
    model = VisualModel(_write_visual_fixture(tmp_path), neighbor_limit=4, max_edges=50)
    stage = model.arena_stages[54]

    assert stage.unified is False
    assert stage.target_node_count == 54
    assert len(stage.nodes) == len(model.node_rows)
    assert {row["channel"] for row in stage.nodes} == {"touch", "vision"}


def test_multihop_selection_and_induced_edges_are_deterministic(tmp_path: Path) -> None:
    paths = _write_multihop_fixture(tmp_path)
    kwargs = {
        "target_count": 6,
        "route_superclasses": ("vnc_sensory", "vnc_intrinsic", "descending_neuron"),
        "min_weight": 3,
    }
    first = select_multihop_network(paths, [1, 2, 3], **kwargs)
    second = select_multihop_network(paths, [1, 2, 3], **kwargs)
    induced = select_induced_network(paths, [node.body_id for node in first.nodes], min_weight=3)

    assert [node.body_id for node in first.nodes] == [1, 2, 3, 4, 5, 6]
    assert first.selection == second.selection
    assert [(edge.body_pre, edge.body_post) for edge in induced.edges] == [
        (1, 2),
        (2, 3),
        (2, 4),
        (3, 4),
        (4, 5),
        (5, 6),
        (6, 5),
    ]


def test_unified_runtime_propagates_population_input_with_one_step_delay() -> None:
    nodes = (
        {"channel": "merged", "channels": ["vision"], "body_id": 1, "role": "source", "superclass": "visual_projection", "soma_side": "L"},
        {"channel": "merged", "channels": ["vision"], "body_id": 2, "role": "target", "superclass": "descending_neuron", "soma_side": "L"},
        {"channel": "merged", "channels": ["touch"], "body_id": 3, "role": "source", "superclass": "vnc_sensory", "soma_side": "L"},
        {"channel": "merged", "channels": ["touch"], "body_id": 4, "role": "target", "superclass": "descending_neuron", "soma_side": "L"},
    )
    edges = (
        {"body_pre": 1, "body_post": 2, "weight": 1, "sign": 1},
        {"body_pre": 3, "body_post": 4, "weight": 1, "sign": 1},
    )
    runtime = ArenaCircuitRuntime(
        ArenaStage(100, 4, True, (), nodes, edges, {}),
        LIFConfig(dt_ms=1, tau_ms=1, rest_mv=0, threshold_mv=1, reset_mv=0, mv_per_synapse=1),
    )

    first = runtime.step({"visual_left": 2.0})
    second = runtime.step({})

    assert first.output_votes["turn_left"] == 0
    assert second.output_votes["turn_left"] == 1
    assert second.output_nodes["turn_left"] == [2]


def test_moving_objects_reflect_and_shift_retina_features() -> None:
    config = ArenaRunConfig(
        neural=SensorimotorConfig(duration_ms=4),
        world_min_x=-1,
        world_max_x=1,
        world_min_y=-1,
        world_max_y=1,
        lights=(ArenaLight("moving", 0.9, 0.2, vx=0.3),),
        threats=(),
    )
    lights, _ = advance_arena_objects(config, config.lights, (), dt_ms=1.0)
    first = ArenaWorld(config).observe(0.0, position_x=0.0, position_y=0.0, heading_degrees=0.0)
    second = ArenaWorld(config).observe(
        1.0,
        position_x=0.0,
        position_y=0.0,
        heading_degrees=0.0,
        lights=lights,
        previous_retina=first.retina,
    )

    assert lights[0].x == pytest.approx(0.8)
    assert lights[0].vx == pytest.approx(-0.3)
    assert second.motion_energy > 0
    assert second.looming_score > 0
    assert second.retina_centroid_x < first.retina_centroid_x


def test_arena_request_rejects_invalid_stage_velocity_and_object_bounds() -> None:
    with pytest.raises(ValueError, match="network_stage"):
        ArenaRunConfig.from_mapping({"network_stage": 100.5})
    with pytest.raises(ValueError, match="velocity"):
        ArenaRunConfig.from_mapping({"lights": [{"id": "fast", "x": 0, "y": 0, "vx": 2}]})
    with pytest.raises(ValueError, match="inside world bounds"):
        ArenaRunConfig.from_mapping({"lights": [{"id": "outside", "x": 100, "y": 0}]})


def test_arena_memory_persists_target_and_habituates_repeated_threats() -> None:
    config = ArenaRunConfig(
        neural=SensorimotorConfig(duration_ms=40, input_current_mv=2.0),
        memory=ArenaMemoryConfig(target_memory_ms=20, habituation_step=0.2),
        lights=(ArenaLight("light", 2.0, 0.0),),
        threats=(ArenaThreat("threat", 0.5, 0.0, radius=1.0),),
    )
    world = ArenaWorld(config)
    memory = _ArenaMemoryState()
    visible = world.observe(0.0, position_x=0.0, position_y=0.0, heading_degrees=0.0)
    _feature_currents(visible, memory, config, time_ms=0.0)
    lost = world.observe(
        10.0,
        position_x=0.0,
        position_y=0.0,
        heading_degrees=0.0,
        lights=(),
        threats=(),
        previous_retina=visible.retina,
    )
    _, remembered = _feature_currents(lost, memory, config, time_ms=10.0)
    expired = world.observe(
        25.0,
        position_x=0.0,
        position_y=0.0,
        heading_degrees=0.0,
        lights=(),
        threats=(),
        previous_retina=lost.retina,
    )
    _, forgotten = _feature_currents(expired, memory, config, time_ms=25.0)

    assert remembered["memory_visual_active"] is True
    assert remembered["memory_visual_gain"] == pytest.approx(0.5)
    assert forgotten["memory_visual_active"] is False

    memory.threat_encounters["threat"] = 3
    threat_observation = world.observe(
        0.0, position_x=0.0, position_y=0.0, heading_degrees=0.0
    )
    currents, features = _feature_currents(
        threat_observation, memory, config, time_ms=0.0
    )
    assert features["threat_gain"] == pytest.approx(0.6)
    assert currents["threat_urgency"] < config.neural.input_current_mv


def test_empty_sandbox_has_strict_json_outcome(tmp_path: Path) -> None:
    model = VisualModel(_write_visual_fixture(tmp_path), neighbor_limit=4, max_edges=50)
    config = _arena_fixture_config()
    empty = ArenaRunConfig(
        mode=config.mode,
        neural=config.neural,
        visual_coupling_mv_per_synapse=config.visual_coupling_mv_per_synapse,
        lights=(),
        threats=config.threats,
    )
    payload = model.run_arena(empty)

    json.dumps(payload, allow_nan=False)
    assert payload["outcome"]["final_distance_to_light"] is None


def test_obstacle_proximity_becomes_touch_input() -> None:
    config = ArenaRunConfig(
        body_radius=0.35,
        touch_range=0.45,
        lights=(),
        threats=(),
        obstacles=(ArenaObstacle("wall", 0.9, 0.0, width=0.5, height=1.5),),
    )

    observation = ArenaWorld(config).observe(
        0.0,
        position_x=0.0,
        position_y=0.0,
        heading_degrees=0.0,
    )

    assert observation.touch_active
    assert observation.touch_source == "obstacle"
    assert observation.touch_id == "wall"
    assert observation.obstacle_contact is False
    assert observation.obstacle_distance == pytest.approx(0.65)
    assert observation.touch_urgency > 0


def test_body_motion_stops_at_obstacle_and_slides_on_clear_axis() -> None:
    config = ArenaRunConfig(
        body_radius=0.25,
        lights=(),
        threats=(),
        obstacles=(ArenaObstacle("wall", 1.5, 0.0, width=1.0, height=2.0),),
    )

    blocked = resolve_body_motion(
        config,
        start_x=0.0,
        start_y=0.0,
        requested_x=3.0,
        requested_y=0.0,
    )
    sliding = resolve_body_motion(
        config,
        start_x=0.0,
        start_y=-0.5,
        requested_x=3.0,
        requested_y=-3.0,
    )

    assert blocked.collision_ids == ("wall",)
    assert blocked.blocked
    assert 0.0 < blocked.actual_x < 1.0
    assert blocked.actual_y == pytest.approx(0.0)
    assert sliding.collision_ids == ("wall",)
    assert sliding.actual_x > 2.7
    assert sliding.actual_y == pytest.approx(-3.0, abs=0.1)


def test_demo_obstacles_are_explicit_but_sandbox_defaults_empty() -> None:
    direct_demo = ArenaRunConfig()
    demo = ArenaRunConfig.from_mapping({"mode": "demo"})
    direct_sandbox = ArenaRunConfig(mode="sandbox")
    sandbox = ArenaRunConfig.from_mapping({"mode": "sandbox"})

    expected_obstacle_ids = [
        "demo-wall-a",
        "demo-wall-b",
    ]
    assert [obstacle.obstacle_id for obstacle in direct_demo.obstacles] == expected_obstacle_ids
    assert [obstacle.obstacle_id for obstacle in demo.obstacles] == expected_obstacle_ids
    assert direct_demo.lights == demo.lights
    assert direct_demo.threats == demo.threats
    assert direct_sandbox.lights == sandbox.lights == ()
    assert direct_sandbox.threats == sandbox.threats == ()
    assert direct_sandbox.obstacles == sandbox.obstacles == ()


def test_arena_frames_expose_collision_cause_and_requested_motion(tmp_path: Path) -> None:
    model = VisualModel(_write_visual_fixture(tmp_path), neighbor_limit=4, max_edges=50)
    request = _arena_fixture_config()
    request = replace(
        request,
        obstacles=(ArenaObstacle("wall", 0.8, 0.0, width=0.8, height=1.5),),
    )
    payload = model.run_arena(request)

    assert payload["environment"]["obstacles"][0]["id"] == "wall"
    assert all("body_requested" in row and "world_cause" in row for row in payload["trajectory"])
    assert all("collision_ids" in row["motion"] for row in payload["trajectory"])
    collision_frames = [
        row for row in payload["trajectory"] if "wall" in row["motion"]["collision_ids"]
    ]
    assert collision_frames
    assert payload["outcome"]["collision_event_count"] == len(collision_frames)
    assert payload["outcome"]["blocked_frame_count"] > 0
    assert payload["outcome"]["collision_ids"] == ["wall"]
    assert any(
        row["body_requested"]["x"] != pytest.approx(row["body_after"]["x"])
        or row["body_requested"]["y"] != pytest.approx(row["body_after"]["y"])
        for row in collision_frames
    )
    json.dumps(payload, allow_nan=False)
