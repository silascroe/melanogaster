"""A deterministic closed-loop arena for the local connectome slice.

The arena is deliberately explicit about its abstractions. A small synthetic
retina observes lights in a two-dimensional world, the selected visual and
touch pathways receive time-varying currents, and descending spikes are
decoded into a handful of toy body actions. The connectome records remain
real; the retina, world, and action decoder are experiment assumptions.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Mapping, Sequence

import numpy as np

from .sensorimotor import SensorimotorConfig
from .simulation import LIFNetwork, LIFState
from .arena_circuit import ACTION_ORDER, ArenaCircuitRuntime, ArenaStage


ARENA_SCHEMA_VERSION = 2
ARENA_NETWORK_STAGES = (54, 100, 250, 1024)
DEFAULT_RETINA_WIDTH = 9
DEFAULT_RETINA_HEIGHT = 5
DEFAULT_FOV_DEGREES = 120.0
DEFAULT_MAX_RANGE = 12.0
DEFAULT_WORLD_BOUNDS = (-4.0, 10.0, -5.0, 8.0)


def _finite_number(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric") from error
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    number = _finite_number(value, name)
    if not number.is_integer():
        raise ValueError(f"{name} must be an integer")
    return int(number)


def _identifier(value: Any, name: str, default: str) -> str:
    if value is None:
        value = default
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _wrap_degrees(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


@dataclass(frozen=True)
class ArenaLight:
    """A point light visible to the synthetic retina."""

    light_id: str
    x: float
    y: float
    intensity: float = 1.0
    vx: float = 0.0
    vy: float = 0.0

    def validate(self) -> None:
        if not self.light_id:
            raise ValueError("light id cannot be empty")
        if not math.isfinite(self.x) or not math.isfinite(self.y):
            raise ValueError("light position must be finite")
        if not math.isfinite(self.intensity) or not 0.0 <= self.intensity <= 1.5:
            raise ValueError("light intensity must be between 0 and 1.5")
        if not math.isfinite(self.vx) or not math.isfinite(self.vy):
            raise ValueError("light velocity must be finite")
        if max(abs(self.vx), abs(self.vy)) > 1.0:
            raise ValueError("light velocity components must be between -1 and 1")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.light_id,
            "x": self.x,
            "y": self.y,
            "intensity": self.intensity,
            "vx": self.vx,
            "vy": self.vy,
        }


@dataclass(frozen=True)
class ArenaObstacle:
    """An axis-aligned solid in the toy arena.

    The obstacle is deliberately two-dimensional because the current body
    controller is a point-mass in the x/y world plane.  Godot renders the same
    rectangle as a three-dimensional static collision shape.
    """

    obstacle_id: str
    x: float
    y: float
    width: float = 1.0
    height: float = 1.0

    def validate(self) -> None:
        if not self.obstacle_id:
            raise ValueError("obstacle id cannot be empty")
        if not math.isfinite(self.x) or not math.isfinite(self.y):
            raise ValueError("obstacle position must be finite")
        if not math.isfinite(self.width) or not 0.0 < self.width <= 12.0:
            raise ValueError("obstacle width must be between 0 and 12")
        if not math.isfinite(self.height) or not 0.0 < self.height <= 12.0:
            raise ValueError("obstacle height must be between 0 and 12")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.obstacle_id,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class ArenaThreat:
    """A threat that can be timed or activated by body proximity."""

    threat_id: str
    x: float
    y: float
    radius: float = 1.0
    trigger: str = "collision"
    active_start_ms: float = 0.0
    active_end_ms: float = 300.0
    vx: float = 0.0
    vy: float = 0.0

    def validate(self) -> None:
        if not self.threat_id:
            raise ValueError("threat id cannot be empty")
        if not math.isfinite(self.x) or not math.isfinite(self.y):
            raise ValueError("threat position must be finite")
        if not math.isfinite(self.radius) or not 0.0 < self.radius <= 4.0:
            raise ValueError("threat radius must be between 0 and 4")
        if self.trigger not in {"timed", "collision"}:
            raise ValueError("threat trigger must be timed or collision")
        if not math.isfinite(self.active_start_ms) or not math.isfinite(self.active_end_ms):
            raise ValueError("threat timing must be finite")
        if self.active_start_ms < 0 or self.active_end_ms <= self.active_start_ms:
            raise ValueError("threat active interval is invalid")
        if not math.isfinite(self.vx) or not math.isfinite(self.vy):
            raise ValueError("threat velocity must be finite")
        if max(abs(self.vx), abs(self.vy)) > 1.0:
            raise ValueError("threat velocity components must be between -1 and 1")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.threat_id,
            "x": self.x,
            "y": self.y,
            "radius": self.radius,
            "trigger": self.trigger,
            "active_start_ms": self.active_start_ms,
            "active_end_ms": self.active_end_ms,
            "vx": self.vx,
            "vy": self.vy,
        }


@dataclass(frozen=True)
class ArenaMemoryConfig:
    """Deterministic short-term state parameters for one replay."""

    target_memory_ms: float = 20.0
    escape_cooldown_ms: float = 12.0
    recovery_ms: float = 18.0
    habituation_step: float = 0.2
    minimum_threat_gain: float = 0.4

    def validate(self) -> None:
        if not 0.0 <= self.target_memory_ms <= 300.0:
            raise ValueError("target_memory_ms must be between 0 and 300")
        if not 0.0 <= self.escape_cooldown_ms <= 300.0:
            raise ValueError("escape_cooldown_ms must be between 0 and 300")
        if not 0.0 <= self.recovery_ms <= 300.0:
            raise ValueError("recovery_ms must be between 0 and 300")
        if not 0.0 <= self.habituation_step <= 1.0:
            raise ValueError("habituation_step must be between 0 and 1")
        if not 0.0 < self.minimum_threat_gain <= 1.0:
            raise ValueError("minimum_threat_gain must be between 0 and 1")


def _default_lights() -> tuple[ArenaLight, ...]:
    return (ArenaLight("beacon", 7.0, 4.0, 1.0, -0.012, 0.004),)


def _default_threats() -> tuple[ArenaThreat, ...]:
    return (
        ArenaThreat(
            "scripted-threat",
            2.0,
            1.5,
            1.1,
            "timed",
            80.0,
            96.0,
            0.018,
            -0.006,
        ),
    )


def _default_obstacles() -> tuple[ArenaObstacle, ...]:
    """A small zig-zag course for the scripted demo.

    These are intentionally sparse and leave the initial body position clear.
    Sandbox requests can provide their own obstacle set, including no
    obstacles at all.
    """

    return (
        ArenaObstacle("demo-wall-a", 2.8, -1.1, 1.0, 3.1),
        ArenaObstacle("demo-wall-b", 5.5, 3.3, 1.0, 3.0),
    )


@dataclass(frozen=True)
class ArenaRunConfig:
    """Validated configuration for one deterministic arena replay."""

    mode: str = "demo"
    network_stage: int = 54
    neural: SensorimotorConfig = field(
        default_factory=lambda: SensorimotorConfig(
            duration_ms=180.0,
            coupling_mv_per_synapse=3.0,
            input_duration_ms=0.0,
        )
    )
    visual_contrast: float = 1.0
    visual_coupling_mv_per_synapse: float = 5.0
    retina_width: int = DEFAULT_RETINA_WIDTH
    retina_height: int = DEFAULT_RETINA_HEIGHT
    retina_fov_degrees: float = DEFAULT_FOV_DEGREES
    retina_max_range: float = DEFAULT_MAX_RANGE
    world_min_x: float = DEFAULT_WORLD_BOUNDS[0]
    world_max_x: float = DEFAULT_WORLD_BOUNDS[1]
    world_min_y: float = DEFAULT_WORLD_BOUNDS[2]
    world_max_y: float = DEFAULT_WORLD_BOUNDS[3]
    body_radius: float = 0.35
    touch_range: float = 0.45
    visual_deadband: float = 0.15
    escape_turn_degrees: float = 45.0
    memory: ArenaMemoryConfig = field(default_factory=ArenaMemoryConfig)
    lights: tuple[ArenaLight, ...] | None = None
    threats: tuple[ArenaThreat, ...] | None = None
    obstacles: tuple[ArenaObstacle, ...] | None = None

    def __post_init__(self) -> None:
        """Resolve omitted world objects from the selected arena mode.

        ``None`` means "use this mode's defaults"; an explicit empty tuple
        always means "no objects".  This keeps direct Python construction and
        JSON request parsing on the same contract.
        """

        if self.lights is None:
            object.__setattr__(
                self, "lights", _default_lights() if self.mode == "demo" else ()
            )
        if self.threats is None:
            object.__setattr__(
                self, "threats", _default_threats() if self.mode == "demo" else ()
            )
        if self.obstacles is None:
            object.__setattr__(
                self, "obstacles", _default_obstacles() if self.mode == "demo" else ()
            )

    def validate(self) -> None:
        self.neural.validate()
        self.neural.to_lif().validate()
        if self.mode not in {"demo", "sandbox"}:
            raise ValueError("mode must be demo or sandbox")
        if self.network_stage not in ARENA_NETWORK_STAGES:
            raise ValueError(f"network_stage must be one of {ARENA_NETWORK_STAGES}")
        if not 1.0 <= self.neural.duration_ms <= 300.0:
            raise ValueError("duration_ms must be between 1 and 300")
        if not math.isfinite(self.visual_contrast) or not 0.0 <= self.visual_contrast <= 1.5:
            raise ValueError("visual_contrast must be between 0 and 1.5")
        if (
            not math.isfinite(self.visual_coupling_mv_per_synapse)
            or self.visual_coupling_mv_per_synapse < 0
        ):
            raise ValueError("visual_coupling must be non-negative")
        if not 3 <= self.retina_width <= 16 or not 3 <= self.retina_height <= 12:
            raise ValueError("retina dimensions are outside the supported range")
        if not math.isfinite(self.retina_fov_degrees) or not 10.0 <= self.retina_fov_degrees <= 180.0:
            raise ValueError("retina_fov_degrees must be between 10 and 180")
        if not math.isfinite(self.retina_max_range) or self.retina_max_range <= 0:
            raise ValueError("retina_max_range must be positive")
        if not (
            math.isfinite(self.world_min_x)
            and math.isfinite(self.world_max_x)
            and math.isfinite(self.world_min_y)
            and math.isfinite(self.world_max_y)
        ):
            raise ValueError("world bounds must be finite")
        if self.world_max_x <= self.world_min_x or self.world_max_y <= self.world_min_y:
            raise ValueError("world bounds must have positive spans")
        if not math.isfinite(self.body_radius) or not 0.0 < self.body_radius < 2.0:
            raise ValueError("body_radius must be between 0 and 2")
        if not math.isfinite(self.touch_range) or not 0.0 <= self.touch_range <= 4.0:
            raise ValueError("touch_range must be between 0 and 4")
        if (
            self.world_max_x - self.world_min_x <= 2.0 * self.body_radius
            or self.world_max_y - self.world_min_y <= 2.0 * self.body_radius
        ):
            raise ValueError("world bounds must be larger than the body diameter")
        if not (
            self.world_min_x <= self.neural.initial_x <= self.world_max_x
            and self.world_min_y <= self.neural.initial_y <= self.world_max_y
        ):
            raise ValueError("initial position must be inside world bounds")
        if not math.isfinite(self.visual_deadband) or not 0.0 <= self.visual_deadband < 1.0:
            raise ValueError("visual_deadband must be between 0 and 1")
        if not math.isfinite(self.escape_turn_degrees) or self.escape_turn_degrees < 0:
            raise ValueError("escape_turn_degrees must be non-negative")
        self.memory.validate()
        if len(self.lights) > 8 or len(self.threats) > 8 or len(self.obstacles) > 16:
            raise ValueError("an arena can contain at most 8 lights, 8 threats, and 16 obstacles")
        light_ids: set[str] = set()
        for light in self.lights:
            light.validate()
            if not (
                self.world_min_x <= light.x <= self.world_max_x
                and self.world_min_y <= light.y <= self.world_max_y
            ):
                raise ValueError(f"light {light.light_id} must be inside world bounds")
            if light.light_id in light_ids:
                raise ValueError(f"duplicate light id: {light.light_id}")
            light_ids.add(light.light_id)
        threat_ids: set[str] = set()
        for threat in self.threats:
            threat.validate()
            if not (
                self.world_min_x <= threat.x <= self.world_max_x
                and self.world_min_y <= threat.y <= self.world_max_y
            ):
                raise ValueError(f"threat {threat.threat_id} must be inside world bounds")
            if threat.threat_id in threat_ids:
                raise ValueError(f"duplicate threat id: {threat.threat_id}")
            threat_ids.add(threat.threat_id)
        obstacle_ids: set[str] = set()
        for obstacle in self.obstacles:
            obstacle.validate()
            if not (
                self.world_min_x - obstacle.width / 2.0 <= obstacle.x <= self.world_max_x + obstacle.width / 2.0
                and self.world_min_y - obstacle.height / 2.0 <= obstacle.y <= self.world_max_y + obstacle.height / 2.0
            ):
                raise ValueError(f"obstacle {obstacle.obstacle_id} must overlap the world bounds")
            if obstacle.obstacle_id in obstacle_ids:
                raise ValueError(f"duplicate obstacle id: {obstacle.obstacle_id}")
            obstacle_ids.add(obstacle.obstacle_id)

    @property
    def bounds(self) -> dict[str, float]:
        return {
            "min_x": self.world_min_x,
            "max_x": self.world_max_x,
            "min_y": self.world_min_y,
            "max_y": self.world_max_y,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ArenaRunConfig":
        if not isinstance(payload, Mapping):
            raise ValueError("arena request must be a JSON object")

        mode = str(payload.get("mode", "demo"))
        try:
            network_stage = _integer(payload.get("network_stage", 54), "network_stage")
        except (TypeError, ValueError) as error:
            raise ValueError("network_stage must be an integer") from error
        duration_ms = _finite_number(payload.get("duration_ms", 180.0), "duration_ms")
        coupling = _finite_number(payload.get("coupling", 3.0), "coupling")
        turn_degrees = _finite_number(payload.get("turn_degrees", 15.0), "turn_degrees")
        forward_step = _finite_number(payload.get("forward_step", 1.0), "forward_step")
        visual_contrast = _finite_number(
            payload.get("visual_contrast", 1.0), "visual_contrast"
        )
        visual_coupling = _finite_number(
            payload.get("visual_coupling", 5.0), "visual_coupling"
        )

        initial = payload.get("initial", {})
        if not isinstance(initial, Mapping):
            raise ValueError("initial must be a JSON object")
        initial_x = _finite_number(initial.get("x", 0.0), "initial.x")
        initial_y = _finite_number(initial.get("y", 0.0), "initial.y")
        initial_heading = _finite_number(
            initial.get("heading_degrees", 0.0), "initial.heading_degrees"
        )
        neural = SensorimotorConfig(
            duration_ms=duration_ms,
            coupling_mv_per_synapse=coupling,
            input_duration_ms=0.0,
            turn_degrees_per_target_spike=turn_degrees,
            forward_step_per_target_spike=forward_step,
            initial_heading_degrees=initial_heading,
            initial_x=initial_x,
            initial_y=initial_y,
        )

        retina = payload.get("retina", {})
        if not isinstance(retina, Mapping):
            raise ValueError("retina must be a JSON object")
        width = _integer(retina.get("width", DEFAULT_RETINA_WIDTH), "retina.width")
        height = _integer(retina.get("height", DEFAULT_RETINA_HEIGHT), "retina.height")
        fov = _finite_number(
            retina.get("fov_degrees", DEFAULT_FOV_DEGREES), "retina.fov_degrees"
        )
        max_range = _finite_number(
            retina.get("max_range", DEFAULT_MAX_RANGE), "retina.max_range"
        )

        bounds = payload.get("bounds", {})
        if not isinstance(bounds, Mapping):
            raise ValueError("bounds must be a JSON object")
        min_x = _finite_number(bounds.get("min_x", DEFAULT_WORLD_BOUNDS[0]), "bounds.min_x")
        max_x = _finite_number(bounds.get("max_x", DEFAULT_WORLD_BOUNDS[1]), "bounds.max_x")
        min_y = _finite_number(bounds.get("min_y", DEFAULT_WORLD_BOUNDS[2]), "bounds.min_y")
        max_y = _finite_number(bounds.get("max_y", DEFAULT_WORLD_BOUNDS[3]), "bounds.max_y")

        body_radius = _finite_number(payload.get("body_radius", 0.35), "body_radius")
        touch_range = _finite_number(payload.get("touch_range", 0.45), "touch_range")

        lights_payload = payload.get("lights")
        if lights_payload is None:
            lights = _default_lights() if mode == "demo" else ()
        else:
            if not isinstance(lights_payload, Sequence) or isinstance(lights_payload, (str, bytes)):
                raise ValueError("lights must be an array")
            lights = tuple(_light_from_mapping(item, index) for index, item in enumerate(lights_payload))

        threats_payload = payload.get("threats")
        if threats_payload is None:
            threats = _default_threats() if mode == "demo" else ()
        else:
            if not isinstance(threats_payload, Sequence) or isinstance(threats_payload, (str, bytes)):
                raise ValueError("threats must be an array")
            threats = tuple(
                _threat_from_mapping(item, index) for index, item in enumerate(threats_payload)
            )

        obstacles_payload = payload.get("obstacles")
        if obstacles_payload is None:
            obstacles = _default_obstacles() if mode == "demo" else ()
        else:
            if not isinstance(obstacles_payload, Sequence) or isinstance(
                obstacles_payload, (str, bytes)
            ):
                raise ValueError("obstacles must be an array")
            obstacles = tuple(
                _obstacle_from_mapping(item, index)
                for index, item in enumerate(obstacles_payload)
            )

        memory_payload = payload.get("memory", {})
        if not isinstance(memory_payload, Mapping):
            raise ValueError("memory must be a JSON object")
        memory = ArenaMemoryConfig(
            target_memory_ms=_finite_number(
                memory_payload.get("target_memory_ms", 20.0), "memory.target_memory_ms"
            ),
            escape_cooldown_ms=_finite_number(
                memory_payload.get("escape_cooldown_ms", 12.0), "memory.escape_cooldown_ms"
            ),
            recovery_ms=_finite_number(
                memory_payload.get("recovery_ms", 18.0), "memory.recovery_ms"
            ),
            habituation_step=_finite_number(
                memory_payload.get("habituation_step", 0.2), "memory.habituation_step"
            ),
            minimum_threat_gain=_finite_number(
                memory_payload.get("minimum_threat_gain", 0.4), "memory.minimum_threat_gain"
            ),
        )

        config = cls(
            mode=mode,
            network_stage=network_stage,
            neural=neural,
            visual_contrast=visual_contrast,
            visual_coupling_mv_per_synapse=visual_coupling,
            retina_width=width,
            retina_height=height,
            retina_fov_degrees=fov,
            retina_max_range=max_range,
            world_min_x=min_x,
            world_max_x=max_x,
            world_min_y=min_y,
            world_max_y=max_y,
            body_radius=body_radius,
            touch_range=touch_range,
            visual_deadband=_finite_number(
                payload.get("visual_deadband", 0.15), "visual_deadband"
            ),
            escape_turn_degrees=_finite_number(
                payload.get("escape_turn_degrees", 45.0), "escape_turn_degrees"
            ),
            memory=memory,
            lights=lights,
            threats=threats,
            obstacles=obstacles,
        )
        config.validate()
        return config


def _light_from_mapping(value: Any, index: int) -> ArenaLight:
    if not isinstance(value, Mapping):
        raise ValueError(f"lights[{index}] must be an object")
    return ArenaLight(
        _identifier(value.get("id"), f"lights[{index}].id", f"light-{index + 1}"),
        _finite_number(value.get("x", 0.0), f"lights[{index}].x"),
        _finite_number(value.get("y", 0.0), f"lights[{index}].y"),
        _finite_number(value.get("intensity", 1.0), f"lights[{index}].intensity"),
        _finite_number(value.get("vx", 0.0), f"lights[{index}].vx"),
        _finite_number(value.get("vy", 0.0), f"lights[{index}].vy"),
    )


def _obstacle_from_mapping(value: Any, index: int) -> ArenaObstacle:
    if not isinstance(value, Mapping):
        raise ValueError(f"obstacles[{index}] must be an object")
    return ArenaObstacle(
        _identifier(value.get("id"), f"obstacles[{index}].id", f"obstacle-{index + 1}"),
        _finite_number(value.get("x", 0.0), f"obstacles[{index}].x"),
        _finite_number(value.get("y", 0.0), f"obstacles[{index}].y"),
        _finite_number(value.get("width", 1.0), f"obstacles[{index}].width"),
        _finite_number(value.get("height", 1.0), f"obstacles[{index}].height"),
    )


def _threat_from_mapping(value: Any, index: int) -> ArenaThreat:
    if not isinstance(value, Mapping):
        raise ValueError(f"threats[{index}] must be an object")
    return ArenaThreat(
        _identifier(value.get("id"), f"threats[{index}].id", f"threat-{index + 1}"),
        _finite_number(value.get("x", 0.0), f"threats[{index}].x"),
        _finite_number(value.get("y", 0.0), f"threats[{index}].y"),
        _finite_number(value.get("radius", 1.0), f"threats[{index}].radius"),
        str(value.get("trigger", "collision")),
        _finite_number(value.get("active_start_ms", 0.0), f"threats[{index}].active_start_ms"),
        _finite_number(value.get("active_end_ms", 300.0), f"threats[{index}].active_end_ms"),
        _finite_number(value.get("vx", 0.0), f"threats[{index}].vx"),
        _finite_number(value.get("vy", 0.0), f"threats[{index}].vy"),
    )


@dataclass(frozen=True)
class ArenaObservation:
    """One world observation before the neural update."""

    retina: tuple[float, ...]
    retina_mean: float
    retina_max: float
    retina_centroid_x: float
    retina_left: float
    retina_center: float
    retina_right: float
    retina_delta: tuple[float, ...]
    motion_energy: float
    motion_centroid_x: float
    looming_score: float
    visual_active: bool
    touch_active: bool
    threat_id: str | None
    threat_bearing_degrees: float | None
    threat_urgency: float
    obstacle_id: str | None
    obstacle_bearing_degrees: float | None
    obstacle_distance: float | None
    obstacle_contact: bool
    nearby_obstacle_ids: tuple[str, ...]
    touch_source: str | None
    touch_id: str | None
    touch_bearing_degrees: float | None
    touch_urgency: float


def _obstacle_distance(obstacle: ArenaObstacle, position_x: float, position_y: float) -> float:
    """Return the distance from a point to an obstacle rectangle."""

    half_width = obstacle.width / 2.0
    half_height = obstacle.height / 2.0
    dx = max(abs(position_x - obstacle.x) - half_width, 0.0)
    dy = max(abs(position_y - obstacle.y) - half_height, 0.0)
    return math.hypot(dx, dy)


def _obstacle_contact(obstacle: ArenaObstacle, position_x: float, position_y: float, radius: float) -> bool:
    """Return whether a circular body overlaps an obstacle rectangle."""

    return _obstacle_distance(obstacle, position_x, position_y) <= radius + 1e-9


class ArenaWorld:
    """Project deterministic lights and threats into the fly's sensors."""

    def __init__(self, config: ArenaRunConfig) -> None:
        self.config = config

    def observe(
        self,
        time_ms: float,
        *,
        position_x: float,
        position_y: float,
        heading_degrees: float,
        lights: Sequence[ArenaLight] | None = None,
        threats: Sequence[ArenaThreat] | None = None,
        obstacles: Sequence[ArenaObstacle] | None = None,
        previous_retina: Sequence[float] | None = None,
    ) -> ArenaObservation:
        width = self.config.retina_width
        height = self.config.retina_height
        cells = [0.0] * (width * height)
        half_fov = self.config.retina_fov_degrees / 2.0
        angular_sigma = max(1.0, self.config.retina_fov_degrees / width * 1.35)
        vertical_center = (height - 1) / 2.0
        vertical_sigma = max(1.0, height / 2.2)

        active_lights = tuple(self.config.lights if lights is None else lights)
        active_threats_config = tuple(self.config.threats if threats is None else threats)
        active_obstacles_config = tuple(
            self.config.obstacles if obstacles is None else obstacles
        )
        for light in active_lights:
            dx = light.x - position_x
            dy = light.y - position_y
            distance = math.hypot(dx, dy)
            if distance > self.config.retina_max_range or distance == 0:
                continue
            relative_angle = _wrap_degrees(math.degrees(math.atan2(dy, dx)) - heading_degrees)
            if abs(relative_angle) > half_fov:
                continue
            distance_factor = max(0.0, 1.0 - distance / self.config.retina_max_range)
            distance_factor = distance_factor * distance_factor
            for row in range(height):
                vertical_factor = math.exp(
                    -0.5 * ((row - vertical_center) / vertical_sigma) ** 2
                )
                for column in range(width):
                    cell_angle = half_fov - ((column + 0.5) / width) * self.config.retina_fov_degrees
                    angular_factor = math.exp(
                        -0.5 * ((_wrap_degrees(cell_angle - relative_angle)) / angular_sigma) ** 2
                    )
                    index = row * width + column
                    cells[index] += light.intensity * distance_factor * vertical_factor * angular_factor

        cells = [max(0.0, min(1.0, value)) for value in cells]
        if previous_retina is None:
            retina_delta = [0.0] * len(cells)
        else:
            if len(previous_retina) != len(cells):
                raise ValueError("previous_retina must match the configured retina size")
            retina_delta = [current - float(previous) for current, previous in zip(cells, previous_retina)]
        motion_energy = sum(abs(value) for value in retina_delta) / max(1, len(retina_delta))
        total = sum(cells)
        maximum = max(cells, default=0.0)
        mean = total / len(cells) if cells else 0.0
        column_totals = [
            sum(cells[row * width + column] for row in range(height)) / height
            for column in range(width)
        ]
        centroid_denominator = sum(column_totals)
        centroid = 0.0
        if centroid_denominator > 1e-12:
            centroid = sum(
                ((column + 0.5) / width * 2.0 - 1.0) * value
                for column, value in enumerate(column_totals)
            ) / centroid_denominator
        third = max(1, width // 3)
        left_values = column_totals[:third]
        right_values = column_totals[-third:]
        center_values = column_totals[third : width - third] or column_totals
        delta_columns = [
            sum(abs(retina_delta[row * width + column]) for row in range(height)) / height
            for column in range(width)
        ]
        delta_total = sum(delta_columns)
        motion_centroid = 0.0
        if delta_total > 1e-12:
            motion_centroid = sum(
                ((column + 0.5) / width * 2.0 - 1.0) * value
                for column, value in enumerate(delta_columns)
            ) / delta_total

        active_threats: list[tuple[float, ArenaThreat, float]] = []
        for threat in active_threats_config:
            in_window = threat.active_start_ms <= time_ms < threat.active_end_ms
            if not in_window:
                continue
            dx = threat.x - position_x
            dy = threat.y - position_y
            distance = math.hypot(dx, dy)
            if threat.trigger == "timed" or distance <= threat.radius:
                bearing = _wrap_degrees(math.degrees(math.atan2(dy, dx)) - heading_degrees)
                active_threats.append((distance, threat, bearing))
        active_threats.sort(key=lambda item: (item[0], item[1].threat_id))
        nearest_threat = active_threats[0] if active_threats else None
        threat_urgency = 0.0
        if nearest_threat is not None:
            distance, threat, _ = nearest_threat
            threat_urgency = max(0.0, min(1.0, threat.radius / max(threat.radius, distance)))

        active_obstacles: list[tuple[float, ArenaObstacle, float, bool]] = []
        for obstacle in active_obstacles_config:
            distance = _obstacle_distance(obstacle, position_x, position_y)
            contact = _obstacle_contact(
                obstacle, position_x, position_y, self.config.body_radius
            )
            if distance > self.config.body_radius + self.config.touch_range:
                continue
            bearing = _wrap_degrees(
                math.degrees(math.atan2(obstacle.y - position_y, obstacle.x - position_x))
                - heading_degrees
            )
            active_obstacles.append((distance, obstacle, bearing, contact))
        active_obstacles.sort(key=lambda item: (item[0], item[1].obstacle_id))
        nearest_obstacle = active_obstacles[0] if active_obstacles else None
        obstacle_urgency = 0.0
        if nearest_obstacle is not None:
            obstacle_urgency = max(
                0.0,
                min(
                    1.0,
                    1.0
                    - nearest_obstacle[0]
                    / max(self.config.body_radius + self.config.touch_range, 1e-9),
                ),
            )

        touch_candidates: list[tuple[float, int, str, str, float, float]] = []
        if nearest_threat is not None:
            distance, threat, bearing = nearest_threat
            touch_candidates.append(
                (distance, 0, "threat", threat.threat_id, bearing, threat_urgency)
            )
        if nearest_obstacle is not None:
            distance, obstacle, bearing, _ = nearest_obstacle
            touch_candidates.append(
                (distance, 1, "obstacle", obstacle.obstacle_id, bearing, obstacle_urgency)
            )
        touch_candidates.sort(key=lambda item: (item[0], item[1], item[3]))
        nearest_touch = touch_candidates[0] if touch_candidates else None
        looming_score = max(0.0, min(1.0, maximum * 0.35 + motion_energy * 4.0))

        return ArenaObservation(
            retina=tuple(cells),
            retina_mean=float(mean),
            retina_max=float(maximum),
            retina_centroid_x=float(max(-1.0, min(1.0, centroid))),
            retina_left=float(sum(left_values) / len(left_values)),
            retina_center=float(sum(center_values) / len(center_values)),
            retina_right=float(sum(right_values) / len(right_values)),
            retina_delta=tuple(float(value) for value in retina_delta),
            motion_energy=float(min(1.0, motion_energy)),
            motion_centroid_x=float(max(-1.0, min(1.0, motion_centroid))),
            looming_score=float(looming_score),
            visual_active=maximum >= 0.05,
            touch_active=nearest_touch is not None,
            threat_id=nearest_threat[1].threat_id if nearest_threat else None,
            threat_bearing_degrees=float(nearest_threat[2]) if nearest_threat else None,
            threat_urgency=float(threat_urgency),
            obstacle_id=nearest_obstacle[1].obstacle_id if nearest_obstacle else None,
            obstacle_bearing_degrees=(
                float(nearest_obstacle[2]) if nearest_obstacle else None
            ),
            obstacle_distance=(
                float(nearest_obstacle[0]) if nearest_obstacle else None
            ),
            obstacle_contact=any(item[3] for item in active_obstacles),
            nearby_obstacle_ids=tuple(item[1].obstacle_id for item in active_obstacles),
            touch_source=nearest_touch[2] if nearest_touch else None,
            touch_id=nearest_touch[3] if nearest_touch else None,
            touch_bearing_degrees=float(nearest_touch[4]) if nearest_touch else None,
            touch_urgency=float(nearest_touch[5]) if nearest_touch else 0.0,
        )


def _advance_position(
    position: float,
    velocity: float,
    lower: float,
    upper: float,
    dt_ms: float,
) -> tuple[float, float]:
    next_position = position + velocity * dt_ms
    next_velocity = velocity
    while next_position < lower or next_position > upper:
        if next_position < lower:
            next_position = lower + (lower - next_position)
            next_velocity = abs(next_velocity)
        elif next_position > upper:
            next_position = upper - (next_position - upper)
            next_velocity = -abs(next_velocity)
    return next_position, next_velocity


def advance_arena_objects(
    config: ArenaRunConfig,
    lights: Sequence[ArenaLight],
    threats: Sequence[ArenaThreat],
    *,
    dt_ms: float,
) -> tuple[tuple[ArenaLight, ...], tuple[ArenaThreat, ...]]:
    """Advance moving objects and reflect them at the configured bounds."""

    next_lights = []
    for light in lights:
        x, vx = _advance_position(
            light.x, light.vx, config.world_min_x, config.world_max_x, dt_ms
        )
        y, vy = _advance_position(
            light.y, light.vy, config.world_min_y, config.world_max_y, dt_ms
        )
        next_lights.append(replace(light, x=x, y=y, vx=vx, vy=vy))

    next_threats = []
    for threat in threats:
        x, vx = _advance_position(
            threat.x, threat.vx, config.world_min_x, config.world_max_x, dt_ms
        )
        y, vy = _advance_position(
            threat.y, threat.vy, config.world_min_y, config.world_max_y, dt_ms
        )
        next_threats.append(replace(threat, x=x, y=y, vx=vx, vy=vy))
    return tuple(next_lights), tuple(next_threats)


@dataclass(frozen=True)
class ArenaMotion:
    """Result of moving the toy body through the solid arena geometry."""

    requested_x: float
    requested_y: float
    actual_x: float
    actual_y: float
    collision_ids: tuple[str, ...]
    boundary_contacts: tuple[str, ...]
    distance_travelled: float

    @property
    def blocked(self) -> bool:
        return bool(self.collision_ids or self.boundary_contacts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested_x": self.requested_x,
            "requested_y": self.requested_y,
            "actual_x": self.actual_x,
            "actual_y": self.actual_y,
            "collision_ids": list(self.collision_ids),
            "boundary_contacts": list(self.boundary_contacts),
            "blocked": self.blocked,
            "distance_travelled": self.distance_travelled,
        }


def resolve_body_motion(
    config: ArenaRunConfig,
    *,
    start_x: float,
    start_y: float,
    requested_x: float,
    requested_y: float,
) -> ArenaMotion:
    """Resolve one body move with swept, axis-separated circle/AABB contact.

    The body remains a simple circle in the arena plane. Small substeps stop
    the point mass from tunnelling through a wall, while axis separation lets
    it slide along a wall when only one component of the requested movement is
    blocked.
    """

    radius = config.body_radius
    lower_x = config.world_min_x + radius
    upper_x = config.world_max_x - radius
    lower_y = config.world_min_y + radius
    upper_y = config.world_max_y - radius
    current_x = max(lower_x, min(upper_x, float(start_x)))
    current_y = max(lower_y, min(upper_y, float(start_y)))
    collision_ids: set[str] = set()
    boundary_contacts: set[str] = set()

    def attempt_axis(axis: str, desired: float) -> None:
        nonlocal current_x, current_y
        if axis == "x":
            lower, upper = lower_x, upper_x
            current = current_x
        else:
            lower, upper = lower_y, upper_y
            current = current_y
        candidate = max(lower, min(upper, desired))
        if desired < lower:
            boundary_contacts.add("world_min_x" if axis == "x" else "world_min_y")
        elif desired > upper:
            boundary_contacts.add("world_max_x" if axis == "x" else "world_max_y")
        test_x = candidate if axis == "x" else current_x
        test_y = candidate if axis == "y" else current_y
        hit_ids = {
            obstacle.obstacle_id
            for obstacle in config.obstacles
            if _obstacle_contact(obstacle, test_x, test_y, radius)
        }
        if hit_ids:
            collision_ids.update(hit_ids)
            return
        if axis == "x":
            current_x = candidate
        else:
            current_y = candidate

    delta_x = float(requested_x) - current_x
    delta_y = float(requested_y) - current_y
    step_size = max(radius * 0.45, 0.05)
    steps = max(1, int(math.ceil(max(abs(delta_x), abs(delta_y)) / step_size)))
    for _ in range(steps):
        attempt_axis("x", current_x + delta_x / steps)
        attempt_axis("y", current_y + delta_y / steps)

    return ArenaMotion(
        requested_x=float(requested_x),
        requested_y=float(requested_y),
        actual_x=float(current_x),
        actual_y=float(current_y),
        collision_ids=tuple(sorted(collision_ids)),
        boundary_contacts=tuple(sorted(boundary_contacts)),
        distance_travelled=float(math.hypot(current_x - start_x, current_y - start_y)),
    )


def _path_summary(channel: Any) -> dict[str, Any]:
    selection = channel.selection
    return {
        "channel": channel.name,
        "source_id": selection.source_id,
        "intermediate_id": selection.intermediate_id,
        "target_id": selection.target_id,
        "path_edge_keys": [list(key) for key in selection.path_edge_keys],
        "selection": selection.selection,
    }


@dataclass(frozen=True)
class _Action:
    name: str
    source: str
    reason: str
    turn_degrees: float
    move_forward: bool


@dataclass
class _ArenaMemoryState:
    last_visual_time_ms: float | None = None
    last_visual_features: tuple[float, float, float, float, float] = (0, 0, 0, 0, 0)
    escape_cooldown_remaining_ms: float = 0.0
    recovery_remaining_ms: float = 0.0
    threat_encounters: Counter[str] = field(default_factory=Counter)
    obstacle_encounters: Counter[str] = field(default_factory=Counter)
    active_threat_ids: set[str] = field(default_factory=set)
    active_obstacle_ids: set[str] = field(default_factory=set)


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def _feature_currents(
    observation: ArenaObservation,
    memory: _ArenaMemoryState,
    config: ArenaRunConfig,
    *,
    time_ms: float,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Convert sensory features and short-term state into named currents."""

    visual_features = (
        observation.retina_left,
        observation.retina_center,
        observation.retina_right,
        observation.motion_energy,
        observation.looming_score,
    )
    memory_visual_active = False
    memory_gain = 0.0
    if observation.visual_active:
        memory.last_visual_time_ms = time_ms
        memory.last_visual_features = visual_features
        memory_gain = 1.0
    elif memory.last_visual_time_ms is not None:
        age = time_ms - memory.last_visual_time_ms
        if 0.0 <= age <= config.memory.target_memory_ms:
            memory_visual_active = True
            memory_gain = _clamp(1.0 - age / max(config.memory.target_memory_ms, 1e-9))
            visual_features = tuple(value * memory_gain for value in memory.last_visual_features)

    base = config.neural.input_current_mv * config.visual_contrast
    currents = {
        "visual_left": base * visual_features[0] * 12.0,
        "visual_center": base * visual_features[1] * 12.0,
        "visual_right": base * visual_features[2] * 12.0,
        "visual_motion": base * visual_features[3] * 8.0,
        "visual_looming": base * visual_features[4] * 8.0,
        "touch_left": 0.0,
        "touch_right": 0.0,
        "threat_urgency": 0.0,
    }
    threat_gain = 0.0
    if observation.touch_active:
        bearing = observation.touch_bearing_degrees or 0.0
        touch_id = observation.touch_id or ""
        if observation.touch_source == "obstacle":
            encounter_count = memory.obstacle_encounters.get(touch_id, 1)
        else:
            encounter_count = memory.threat_encounters.get(touch_id, 1)
        threat_gain = max(
            config.memory.minimum_threat_gain,
            1.0 - config.memory.habituation_step * max(0, encounter_count - 1),
        )
        if bearing > 1.0:
            currents["touch_left"] = config.neural.input_current_mv * threat_gain
        elif bearing < -1.0:
            currents["touch_right"] = config.neural.input_current_mv * threat_gain
        else:
            currents["touch_left"] = config.neural.input_current_mv * 0.5 * threat_gain
            currents["touch_right"] = config.neural.input_current_mv * 0.5 * threat_gain
        currents["threat_urgency"] = (
            config.neural.input_current_mv * observation.touch_urgency * threat_gain
        )

    return currents, {
        "memory_visual_active": memory_visual_active,
        "memory_visual_gain": memory_gain,
        "visual_features": {
            "left": float(visual_features[0]),
            "center": float(visual_features[1]),
            "right": float(visual_features[2]),
            "motion": float(visual_features[3]),
            "looming": float(visual_features[4]),
        },
        "touch_gain": float(threat_gain),
        "threat_gain": float(threat_gain),
        "input_currents": {key: float(value) for key, value in currents.items()},
    }


def _decode_population_action(
    votes: Mapping[str, float],
    *,
    observation: ArenaObservation,
    memory: _ArenaMemoryState,
    config: ArenaRunConfig,
    output_nodes: Mapping[str, Sequence[int]] | None = None,
    decoder_policy: str = "touch_priority",
) -> _Action:
    """Choose an action only after descending populations have voted."""

    def winner(actions: Sequence[str]) -> str | None:
        ranked = sorted(
            ((float(votes.get(action, 0.0)), action) for action in actions),
            key=lambda item: (
                -item[0],
                ACTION_ORDER.index(item[1]),
                min(output_nodes.get(item[1]) or (2**63 - 1,))
                if output_nodes is not None
                else 2**63 - 1,
            ),
        )
        return ranked[0][1] if ranked and ranked[0][0] > 0 else None

    if decoder_policy not in {"touch_priority", "strongest_vote"}:
        raise ValueError(f"unknown decoder policy: {decoder_policy}")
    escape = winner(("escape_left", "escape_right"))
    visual = winner(("turn_left", "turn_right", "forward"))
    # The diagnostic changes only cross-population arbitration; cooldown and
    # recovery gates, tie order, and all motor effects remain the same.
    if (
        decoder_policy == "strongest_vote"
        and escape is not None
        and visual is not None
        and float(votes[visual]) > float(votes[escape])
    ):
        escape = None
    if escape and memory.escape_cooldown_remaining_ms <= 0.0:
        turn = config.escape_turn_degrees if escape == "escape_left" else -config.escape_turn_degrees
        return _Action(
            escape,
            "touch",
            "descending touch population voted for an escape turn",
            turn,
            True,
        )

    if memory.recovery_remaining_ms > 0.0 and not observation.touch_active:
        return _Action(
            "forward",
            "recovery",
            "post-escape recovery is carrying the body forward",
            0.0,
            True,
        )

    if visual:
        turn = config.neural.turn_degrees_per_target_spike
        if visual == "turn_right":
            turn = -turn
        return _Action(
            visual,
            "memory" if not observation.visual_active else "vision",
            "descending visual population voted for the selected motor action",
            turn,
            True,
        )

    return _Action("stop", "none", "no descending population voted", 0.0, False)


class ArenaSession:
    """One persistent neural controller for a live external world.

    ``ArenaModel.run`` owns the deterministic batch replay used by the website.
    This session is the complementary live interface: a client supplies the
    current body and object state, while this object keeps the LIF state,
    retina history, and arena memory between calls.  The client remains the
    authority for world integration; the returned ``next_*`` values are the
    deterministic result of applying the selected toy action and moving the
    configured objects one timestep.
    """

    def __init__(
        self,
        stage: ArenaStage,
        runtime: ArenaCircuitRuntime,
        config: ArenaRunConfig,
    ) -> None:
        self.stage = stage
        self.runtime = runtime
        self.config = config
        self.world = ArenaWorld(config)
        self.time_ms = 0.0
        self.step_index = 0
        self.position_x = config.neural.initial_x
        self.position_y = config.neural.initial_y
        self.heading_degrees = config.neural.initial_heading_degrees
        self.lights = tuple(config.lights)
        self.threats = tuple(config.threats)
        self.previous_retina: tuple[float, ...] | None = None
        self.memory = _ArenaMemoryState()
        self.previous_threat_ids: set[str] = set()
        self.previous_obstacle_ids: set[str] = set()
        self.trajectory: list[dict[str, Any]] = []
        self.spikes_by_time: list[list[dict[str, Any]]] = []
        self.spike_events: list[dict[str, Any]] = []
        self.spike_counts: Counter[int] = Counter()
        self.closed = False

    def _validate_external_objects(
        self,
        lights: Sequence[ArenaLight],
        threats: Sequence[ArenaThreat],
    ) -> None:
        expected_light_ids = {light.light_id for light in self.config.lights}
        expected_threat_ids = {threat.threat_id for threat in self.config.threats}
        actual_light_ids = {light.light_id for light in lights}
        actual_threat_ids = {threat.threat_id for threat in threats}
        if actual_light_ids != expected_light_ids:
            raise ValueError("live step lights must preserve the session object IDs")
        if actual_threat_ids != expected_threat_ids:
            raise ValueError("live step threats must preserve the session object IDs")
        if len(actual_light_ids) != len(lights):
            raise ValueError("live step lights contain duplicate IDs")
        if len(actual_threat_ids) != len(threats):
            raise ValueError("live step threats contain duplicate IDs")
        for light in lights:
            light.validate()
            if not (
                self.config.world_min_x <= light.x <= self.config.world_max_x
                and self.config.world_min_y <= light.y <= self.config.world_max_y
            ):
                raise ValueError(f"light {light.light_id} must be inside world bounds")
        for threat in threats:
            threat.validate()
            if not (
                self.config.world_min_x <= threat.x <= self.config.world_max_x
                and self.config.world_min_y <= threat.y <= self.config.world_max_y
            ):
                raise ValueError(f"threat {threat.threat_id} must be inside world bounds")

    def _external_state(
        self,
        payload: Mapping[str, Any],
    ) -> tuple[float, float, float, tuple[ArenaLight, ...], tuple[ArenaThreat, ...]]:
        if not isinstance(payload, Mapping):
            raise ValueError("live step request must be a JSON object")
        provided_time = _finite_number(payload.get("time_ms", self.time_ms), "time_ms")
        if abs(provided_time - self.time_ms) > 1e-6:
            raise ValueError(
                f"live step time_ms must be {self.time_ms:g}, got {provided_time:g}"
            )

        body = payload.get("body", {})
        if not isinstance(body, Mapping):
            raise ValueError("body must be a JSON object")
        position_x = _finite_number(body.get("x", self.position_x), "body.x")
        position_y = _finite_number(body.get("y", self.position_y), "body.y")
        heading = _finite_number(
            body.get("heading_degrees", self.heading_degrees),
            "body.heading_degrees",
        )
        if not (
            self.config.world_min_x <= position_x <= self.config.world_max_x
            and self.config.world_min_y <= position_y <= self.config.world_max_y
        ):
            raise ValueError("body position must be inside world bounds")

        lights_payload = payload.get("lights")
        if lights_payload is None:
            lights = self.lights
        else:
            if not isinstance(lights_payload, Sequence) or isinstance(
                lights_payload, (str, bytes)
            ):
                raise ValueError("lights must be an array")
            lights = tuple(
                _light_from_mapping(item, index)
                for index, item in enumerate(lights_payload)
            )

        threats_payload = payload.get("threats")
        if threats_payload is None:
            threats = self.threats
        else:
            if not isinstance(threats_payload, Sequence) or isinstance(
                threats_payload, (str, bytes)
            ):
                raise ValueError("threats must be an array")
            threats = tuple(
                _threat_from_mapping(item, index)
                for index, item in enumerate(threats_payload)
            )
        self._validate_external_objects(lights, threats)
        return position_x, position_y, heading, lights, threats

    def metadata(self) -> dict[str, Any]:
        """Return the inspectable session contract without mutable LIF state."""

        return {
            "schema_version": ARENA_SCHEMA_VERSION,
            "protocol": "godot_world_to_python_neural_step",
            "step_ms": self.config.neural.dt_ms,
            "network": {
                "stage": self.stage.stage,
                "requested_node_count": self.config.network_stage,
                "target_node_count": self.stage.target_node_count,
                "actual_node_count": len(self.stage.nodes),
                "edge_count": len(self.stage.edges),
                "unified": self.stage.unified,
                "selection": self.stage.selection,
                "input_groups": self.runtime.group_metadata(),
                "input_group_details": self.runtime.group_details(),
            },
            "body": {
                "x": self.position_x,
                "y": self.position_y,
                "heading_degrees": self.heading_degrees,
            },
            "environment": {
                "mode": self.config.mode,
                "bounds": self.config.bounds,
                "body_radius": self.config.body_radius,
                "touch_range": self.config.touch_range,
                "lights": [light.as_dict() for light in self.lights],
                "threats": [threat.as_dict() for threat in self.threats],
                "obstacles": [obstacle.as_dict() for obstacle in self.config.obstacles],
                "motion_model": "constant velocity with boundary reflection",
                "body_model": "circle with swept axis-separated AABB collision resolution",
                "retina": {
                    "width": self.config.retina_width,
                    "height": self.config.retina_height,
                    "fov_degrees": self.config.retina_fov_degrees,
                    "max_range": self.config.retina_max_range,
                    "layout": "row-major, left-to-right columns, synthetic luminance",
                },
            },
            "action_decoder": {
                "mode": "descending_population_votes",
                "direct_retinal_centroid_steering": False,
                "touch_priority": True,
                "actions": list(ACTION_ORDER),
                "mapping": {
                    "visual_left": "turn_left",
                    "visual_right": "turn_right",
                    "visual_center": "forward",
                    "touch_left": "escape_right",
                    "touch_right": "escape_left",
                },
            },
            "notes": [
                "Godot supplies the current body and moving-object state on each step.",
                "Python owns the persistent LIF state, retina history, memory, spikes, and action decoder.",
                "Python resolves body motion against the configured static obstacle geometry; Godot renders matching collision shapes.",
                "The retina, memory, and motor mapping remain explicit experiment assumptions.",
            ],
        }

    def step(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Advance one neural timestep, optionally from an external world."""

        if self.closed:
            raise ValueError("arena session is closed")

        external = payload is not None
        if payload is None:
            position_x = self.position_x
            position_y = self.position_y
            heading = self.heading_degrees
            lights = self.lights
            threats = self.threats
        else:
            position_x, position_y, heading, lights, threats = self._external_state(payload)

        time_ms = self.time_ms
        observation = self.world.observe(
            time_ms,
            position_x=position_x,
            position_y=position_y,
            heading_degrees=heading,
            lights=lights,
            threats=threats,
            previous_retina=self.previous_retina,
        )
        active_threat_ids = {observation.threat_id} if observation.threat_id else set()
        for threat_id in sorted(active_threat_ids - self.previous_threat_ids):
            self.memory.threat_encounters[threat_id] += 1
        self.memory.active_threat_ids = active_threat_ids
        self.previous_threat_ids = active_threat_ids
        active_obstacle_ids = set(observation.nearby_obstacle_ids)
        for obstacle_id in sorted(active_obstacle_ids - self.previous_obstacle_ids):
            self.memory.obstacle_encounters[obstacle_id] += 1
        self.memory.active_obstacle_ids = active_obstacle_ids
        self.previous_obstacle_ids = active_obstacle_ids

        currents, feature_state = _feature_currents(
            observation,
            self.memory,
            self.config,
            time_ms=time_ms,
        )
        circuit_step = self.runtime.step(currents)
        action = _decode_population_action(
            circuit_step.output_votes,
            observation=observation,
            memory=self.memory,
            config=self.config,
            output_nodes=circuit_step.output_nodes,
        )

        body_before = {
            "x": float(position_x),
            "y": float(position_y),
            "heading_degrees": float(heading),
        }
        next_heading = _wrap_degrees(heading + action.turn_degrees)
        requested_x = position_x
        requested_y = position_y
        if action.move_forward:
            radians = math.radians(next_heading)
            requested_x += self.config.neural.forward_step_per_target_spike * math.cos(radians)
            requested_y += self.config.neural.forward_step_per_target_spike * math.sin(radians)
        motion = resolve_body_motion(
            self.config,
            start_x=position_x,
            start_y=position_y,
            requested_x=requested_x,
            requested_y=requested_y,
        )
        next_x = motion.actual_x
        next_y = motion.actual_y
        body_after = {
            "x": float(next_x),
            "y": float(next_y),
            "heading_degrees": float(next_heading),
        }

        if action.name.startswith("escape_"):
            self.memory.escape_cooldown_remaining_ms = self.config.memory.escape_cooldown_ms
            self.memory.recovery_remaining_ms = self.config.memory.recovery_ms
        else:
            self.memory.escape_cooldown_remaining_ms = max(
                0.0,
                self.memory.escape_cooldown_remaining_ms - self.config.neural.dt_ms,
            )
            self.memory.recovery_remaining_ms = max(
                0.0,
                self.memory.recovery_remaining_ms - self.config.neural.dt_ms,
            )

        active = circuit_step.active_nodes
        for node in active:
            body_id = int(node["body_id"])
            self.spike_counts[body_id] += 1
            self.spike_events.append(
                {
                    "time_ms": float(time_ms),
                    "body_id": body_id,
                    "neuron_index": int(node["neuron_index"]),
                    "channel": node.get("channel", "merged"),
                    "role": node.get("role", "context"),
                }
            )
        self.spikes_by_time.append(active)

        output_nodes = {
            action_name: list(node_ids)
            for action_name, node_ids in circuit_step.output_nodes.items()
        }
        visual_output_spike = any(
            circuit_step.output_votes.get(name, 0.0) > 0
            for name in ("turn_left", "turn_right", "forward")
        )
        touch_output_spike = any(
            circuit_step.output_votes.get(name, 0.0) > 0
            for name in ("escape_left", "escape_right")
        )
        target_memory_remaining_ms = 0.0
        if self.memory.last_visual_time_ms is not None:
            target_memory_remaining_ms = max(
                0.0,
                self.config.memory.target_memory_ms
                - (time_ms - self.memory.last_visual_time_ms),
            )

        frame_lights = [light.as_dict() for light in lights]
        frame_threats = [threat.as_dict() for threat in threats]
        frame_obstacles = [obstacle.as_dict() for obstacle in self.config.obstacles]
        world_cause = {
            "touch_source": observation.touch_source,
            "touch_id": observation.touch_id,
            "touch_bearing_degrees": observation.touch_bearing_degrees,
            "touch_urgency": observation.touch_urgency,
            "threat_id": observation.threat_id,
            "obstacle_id": observation.obstacle_id,
            "obstacle_contact": observation.obstacle_contact,
            "nearby_obstacle_ids": list(observation.nearby_obstacle_ids),
            "collision_ids": list(motion.collision_ids),
            "boundary_contacts": list(motion.boundary_contacts),
            "blocked": motion.blocked,
        }
        frame = {
            "time_ms": float(time_ms),
            "position_x": float(next_x),
            "position_y": float(next_y),
            "heading_degrees": float(next_heading),
            "body_before": body_before,
            "body_requested": {
                "x": float(requested_x),
                "y": float(requested_y),
                "heading_degrees": float(next_heading),
            },
            "body_after": body_after,
            "motion": motion.as_dict(),
            "world_cause": world_cause,
            "action": action.name,
            "action_source": action.source,
            "action_reason": action.reason,
            "neural_cause": {
                "active_descending_nodes": sorted(
                    {
                        body_id
                        for ids in output_nodes.values()
                        for body_id in ids
                    }
                ),
                "output_votes": dict(circuit_step.output_votes),
                "winning_output_nodes": output_nodes.get(action.name, []),
                "input_groups": feature_state["input_currents"],
                "visual_features": feature_state["visual_features"],
                "world_event": world_cause,
            },
            "turn_command_degrees": float(action.turn_degrees),
            "forward_step": float(
                self.config.neural.forward_step_per_target_spike
                if action.move_forward
                else 0.0
            ),
            "active_spikes": list(active),
            "touch_stimulus_active": observation.touch_active,
            "visual_stimulus_active": observation.visual_active,
            "stimulus_active": observation.touch_active or observation.visual_active,
            "threat_id": observation.threat_id,
            "threat_bearing_degrees": observation.threat_bearing_degrees,
            "threat_urgency": observation.threat_urgency,
            "touch_source": observation.touch_source,
            "touch_id": observation.touch_id,
            "touch_bearing_degrees": observation.touch_bearing_degrees,
            "touch_urgency": observation.touch_urgency,
            "obstacle_id": observation.obstacle_id,
            "obstacle_bearing_degrees": observation.obstacle_bearing_degrees,
            "obstacle_distance": observation.obstacle_distance,
            "obstacle_contact": observation.obstacle_contact,
            "nearby_obstacle_ids": list(observation.nearby_obstacle_ids),
            "retina": list(observation.retina),
            "retina_delta": list(observation.retina_delta),
            "retina_width": self.config.retina_width,
            "retina_height": self.config.retina_height,
            "retina_mean": observation.retina_mean,
            "retina_max": observation.retina_max,
            "retina_centroid_x": observation.retina_centroid_x,
            "retina_left": observation.retina_left,
            "retina_center": observation.retina_center,
            "retina_right": observation.retina_right,
            "motion_energy": observation.motion_energy,
            "motion_centroid_x": observation.motion_centroid_x,
            "looming_score": observation.looming_score,
            "visual_features": feature_state["visual_features"],
            "input_currents": feature_state["input_currents"],
            "memory_visual_active": feature_state["memory_visual_active"],
            "memory_visual_gain": feature_state["memory_visual_gain"],
            "threat_gain": feature_state["threat_gain"],
            "memory": {
                "target_persistence_remaining_ms": float(target_memory_remaining_ms),
                "target_persistence_gain": float(feature_state["memory_visual_gain"]),
                "visual_active_from_memory": bool(feature_state["memory_visual_active"]),
                "escape_cooldown_remaining_ms": float(
                    self.memory.escape_cooldown_remaining_ms
                ),
                "recovery_remaining_ms": float(self.memory.recovery_remaining_ms),
                "threat_encounter_counts": {
                    threat_id: int(count)
                    for threat_id, count in sorted(self.memory.threat_encounters.items())
                },
                "active_threat_ids": sorted(self.memory.active_threat_ids),
                "obstacle_encounter_counts": {
                    obstacle_id: int(count)
                    for obstacle_id, count in sorted(self.memory.obstacle_encounters.items())
                },
                "active_obstacle_ids": sorted(self.memory.active_obstacle_ids),
                "habituation_gain": float(feature_state["threat_gain"]),
            },
            "escape_cooldown_remaining_ms": self.memory.escape_cooldown_remaining_ms,
            "recovery_remaining_ms": self.memory.recovery_remaining_ms,
            "touch_output_spike": touch_output_spike,
            "visual_output_spike": visual_output_spike,
            "touch_target_spike": touch_output_spike,
            "visual_target_spike": visual_output_spike,
            "target_spike": touch_output_spike or visual_output_spike,
            "lights": frame_lights,
            "threats": frame_threats,
            "obstacles": frame_obstacles,
            "escape_marker": action.name.startswith("escape_"),
            "world_source": "external_client" if external else "session_internal",
        }
        self.trajectory.append(frame)
        self.previous_retina = observation.retina

        next_lights, next_threats = advance_arena_objects(
            self.config,
            lights,
            threats,
            dt_ms=self.config.neural.dt_ms,
        )
        self.position_x = next_x
        self.position_y = next_y
        self.heading_degrees = next_heading
        self.lights = next_lights
        self.threats = next_threats
        self.time_ms += self.config.neural.dt_ms
        self.step_index += 1

        return {
            "schema_version": ARENA_SCHEMA_VERSION,
            "step_index": self.step_index - 1,
            "time_ms": float(time_ms),
            "next_time_ms": float(self.time_ms),
            "frame": frame,
            "next_body": {
                "x": float(self.position_x),
                "y": float(self.position_y),
                "heading_degrees": float(self.heading_degrees),
            },
            "next_lights": [light.as_dict() for light in self.lights],
            "next_threats": [threat.as_dict() for threat in self.threats],
            "memory": frame["memory"],
        }

    def result(self) -> dict[str, Any]:
        """Package steps taken by this session in the batch Arena schema."""

        if not self.trajectory:
            raise ValueError("arena session has no steps")
        import hashlib
        import json

        final = self.trajectory[-1]
        action_counts = Counter(row["action"] for row in self.trajectory)
        visual_output_times = [
            row["time_ms"] for row in self.trajectory if row["visual_output_spike"]
        ]
        touch_output_times = [
            row["time_ms"] for row in self.trajectory if row["touch_output_spike"]
        ]
        distance_to_light = [
            min(
                math.hypot(light["x"] - row["position_x"], light["y"] - row["position_y"])
                for light in row["lights"]
            )
            for row in self.trajectory
            if row["lights"]
        ]
        digest_payload = {
            "stage": self.stage.stage,
            "trajectory": self.trajectory,
            "spikes_by_time": self.spikes_by_time,
        }
        replay_digest = hashlib.sha256(
            json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        metadata = self.metadata()
        return {
            "schema_version": ARENA_SCHEMA_VERSION,
            "experiment": "scalable closed-loop synthetic-retina arena",
            "dataset": {
                "name": "FlyEM Male CNS",
                "release": "v1.0",
                "source_manifest": "data/metadata/source_manifest.json",
            },
            "pathways": {
                channel.name: _path_summary(channel) for channel in self.stage.channels
            },
            "network": {
                **metadata["network"],
                "channels": {
                    channel.name: {
                        "node_count": len(channel.network.nodes),
                        "edge_count": len(channel.network.edges),
                    }
                    for channel in self.stage.channels
                },
            },
            "parameters": {
                **asdict(self.config.neural),
                "neural": asdict(self.config.neural),
                "mode": self.config.mode,
                "network_stage": self.config.network_stage,
                "visual_contrast": self.config.visual_contrast,
                "visual_coupling_mv_per_synapse": self.config.visual_coupling_mv_per_synapse,
                "visual_deadband": self.config.visual_deadband,
                "escape_turn_degrees": self.config.escape_turn_degrees,
                "body_radius": self.config.body_radius,
                "touch_range": self.config.touch_range,
                "memory": asdict(self.config.memory),
            },
            "action_decoder": metadata["action_decoder"],
            "environment": metadata["environment"],
            "nodes": list(self.stage.nodes),
            "edges": list(self.stage.edges),
            "trajectory": self.trajectory,
            "spikes_by_time": self.spikes_by_time,
            "spike_events": self.spike_events,
            "replay_digest": replay_digest,
            "outcome": {
                "action_counts": dict(sorted(action_counts.items())),
                "visual_target_spike_count": len(visual_output_times),
                "touch_target_spike_count": len(touch_output_times),
                "target_spike_count": len(visual_output_times) + len(touch_output_times),
                "visual_stimulus_frame_count": sum(
                    bool(row["visual_stimulus_active"]) for row in self.trajectory
                ),
                "touch_stimulus_frame_count": sum(
                    bool(row["touch_stimulus_active"]) for row in self.trajectory
                ),
                "escape_event_count": sum(
                    bool(row["escape_marker"]) for row in self.trajectory
                ),
                "collision_event_count": sum(
                    bool(row["motion"]["collision_ids"]) for row in self.trajectory
                ),
                "blocked_frame_count": sum(
                    bool(row["motion"]["blocked"]) for row in self.trajectory
                ),
                "collision_ids": sorted(
                    {
                        obstacle_id
                        for row in self.trajectory
                        for obstacle_id in row["motion"]["collision_ids"]
                    }
                ),
                "first_visual_target_spike_ms": visual_output_times[0]
                if visual_output_times
                else None,
                "first_touch_target_spike_ms": touch_output_times[0]
                if touch_output_times
                else None,
                "initial_distance_to_light": distance_to_light[0]
                if distance_to_light
                else None,
                "minimum_distance_to_light": min(distance_to_light)
                if distance_to_light
                else None,
                "final_distance_to_light": distance_to_light[-1]
                if distance_to_light
                else None,
                "final_heading_degrees": final["heading_degrees"],
                "final_position": [final["position_x"], final["position_y"]],
                "total_spikes": sum(self.spike_counts.values()),
                "spike_counts": {
                    str(body_id): count
                    for body_id, count in sorted(self.spike_counts.items())
                },
            },
            "notes": [
                "The connectome nodes and edges come from the official local Male CNS v1.0 release.",
                "The retina, moving arena, memory state, and descending-population action mapping are explicit experiment assumptions.",
                "The body is a circular toy agent; static obstacle collisions are deterministic AABB contacts, not biological flight physics.",
                "The 9x5 retina is an environmental sensor front-end; it is not a complete biological retina.",
                "Stage 54 preserves separate local contexts; stages 100 and 250 run a unified induced graph.",
            ],
        }


class ArenaModel:
    """Run deterministic world state through a cached graph stage."""

    def __init__(
        self,
        channels: Sequence[Any] | None = None,
        node_rows: Sequence[dict[str, Any]] | None = None,
        edge_rows: Sequence[dict[str, Any]] | None = None,
        *,
        stages: Mapping[int, ArenaStage] | None = None,
    ) -> None:
        if stages is None:
            if channels is None or node_rows is None or edge_rows is None or len(channels) != 2:
                raise ValueError("arena requires exactly touch and vision channels")
            stage = ArenaStage(
                stage=54,
                target_node_count=len(node_rows),
                unified=False,
                channels=tuple(channels),
                nodes=tuple(dict(row) for row in node_rows),
                edges=tuple(dict(row) for row in edge_rows),
                selection={"stage": 54, "strategy": "legacy"},
            )
            self.stages: dict[int, ArenaStage] = {54: stage}
        else:
            self.stages = dict(stages)
        if not self.stages:
            raise ValueError("arena requires at least one graph stage")
        self._runtime_templates: dict[tuple[int, LIFConfig, LIFConfig | None], ArenaCircuitRuntime] = {}

    def _runtime_for(
        self,
        stage: ArenaStage,
        neural_lif: Any,
        visual_lif: Any,
    ) -> ArenaCircuitRuntime:
        key = (stage.stage, neural_lif, None if stage.unified else visual_lif)
        template = self._runtime_templates.get(key)
        if template is None:
            network_configs = None if stage.unified else {"vision": visual_lif}
            template = ArenaCircuitRuntime(stage, neural_lif, network_configs=network_configs)
            self._runtime_templates[key] = template
        return template.new_run()

    def _run_stage(
        self, stage: ArenaStage, run_config: ArenaRunConfig, *, decoder_policy: str = "touch_priority"
    ) -> dict[str, Any]:
        neural_lif = run_config.neural.to_lif()
        visual_lif = replace(
            neural_lif,
            mv_per_synapse=run_config.visual_coupling_mv_per_synapse,
            input_current_mv=run_config.neural.input_current_mv * run_config.visual_contrast,
        )
        runtime = self._runtime_for(stage, neural_lif, visual_lif)
        world = ArenaWorld(run_config)

        n_steps = max(1, int(round(run_config.neural.duration_ms / run_config.neural.dt_ms)))
        times = np.arange(n_steps, dtype=np.float64) * run_config.neural.dt_ms
        heading = run_config.neural.initial_heading_degrees
        position_x = run_config.neural.initial_x
        position_y = run_config.neural.initial_y
        lights = tuple(run_config.lights)
        threats = tuple(run_config.threats)
        previous_retina: tuple[float, ...] | None = None
        memory = _ArenaMemoryState()
        trajectory: list[dict[str, Any]] = []
        spikes_by_time: list[list[dict[str, Any]]] = []
        spike_events: list[dict[str, Any]] = []
        spike_counts: Counter[int] = Counter()
        previous_threat_ids: set[str] = set()
        previous_obstacle_ids: set[str] = set()

        for time_ms in times.tolist():
            observation = world.observe(
                float(time_ms),
                position_x=position_x,
                position_y=position_y,
                heading_degrees=heading,
                lights=lights,
                threats=threats,
                previous_retina=previous_retina,
            )
            active_threat_ids = {observation.threat_id} if observation.threat_id else set()
            for threat_id in sorted(active_threat_ids - previous_threat_ids):
                memory.threat_encounters[threat_id] += 1
            memory.active_threat_ids = active_threat_ids
            previous_threat_ids = active_threat_ids
            active_obstacle_ids = set(observation.nearby_obstacle_ids)
            for obstacle_id in sorted(active_obstacle_ids - previous_obstacle_ids):
                memory.obstacle_encounters[obstacle_id] += 1
            memory.active_obstacle_ids = active_obstacle_ids
            previous_obstacle_ids = active_obstacle_ids

            currents, feature_state = _feature_currents(
                observation, memory, run_config, time_ms=float(time_ms)
            )
            circuit_step = runtime.step(currents)
            action = _decode_population_action(
                circuit_step.output_votes,
                observation=observation,
                memory=memory,
                config=run_config,
                output_nodes=circuit_step.output_nodes,
                decoder_policy=decoder_policy,
            )

            body_before_heading = heading
            heading = _wrap_degrees(heading + action.turn_degrees)
            body_before_x = position_x
            body_before_y = position_y
            requested_x = position_x
            requested_y = position_y
            if action.move_forward:
                radians = math.radians(heading)
                requested_x += run_config.neural.forward_step_per_target_spike * math.cos(radians)
                requested_y += run_config.neural.forward_step_per_target_spike * math.sin(radians)
            motion = resolve_body_motion(
                run_config,
                start_x=position_x,
                start_y=position_y,
                requested_x=requested_x,
                requested_y=requested_y,
            )
            position_x = motion.actual_x
            position_y = motion.actual_y

            if action.name.startswith("escape_"):
                memory.escape_cooldown_remaining_ms = run_config.memory.escape_cooldown_ms
                memory.recovery_remaining_ms = run_config.memory.recovery_ms
            else:
                memory.escape_cooldown_remaining_ms = max(
                    0.0,
                    memory.escape_cooldown_remaining_ms - run_config.neural.dt_ms,
                )
                memory.recovery_remaining_ms = max(
                    0.0,
                    memory.recovery_remaining_ms - run_config.neural.dt_ms,
                )

            active = circuit_step.active_nodes
            for node in active:
                body_id = int(node["body_id"])
                spike_counts[body_id] += 1
                spike_events.append(
                    {
                        "time_ms": float(time_ms),
                        "body_id": body_id,
                        "neuron_index": int(node["neuron_index"]),
                        "channel": node.get("channel", "merged"),
                        "role": node.get("role", "context"),
                    }
                )
            spikes_by_time.append(active)

            frame_lights = [light.as_dict() for light in lights]
            frame_threats = [threat.as_dict() for threat in threats]
            output_nodes = {
                action_name: list(node_ids)
                for action_name, node_ids in circuit_step.output_nodes.items()
            }
            visual_output_spike = any(
                circuit_step.output_votes.get(name, 0.0) > 0
                for name in ("turn_left", "turn_right", "forward")
            )
            touch_output_spike = any(
                circuit_step.output_votes.get(name, 0.0) > 0
                for name in ("escape_left", "escape_right")
            )
            target_memory_remaining_ms = 0.0
            if memory.last_visual_time_ms is not None:
                target_memory_remaining_ms = max(
                    0.0,
                    run_config.memory.target_memory_ms
                    - (float(time_ms) - memory.last_visual_time_ms),
                )
            world_cause = {
                "touch_source": observation.touch_source,
                "touch_id": observation.touch_id,
                "touch_bearing_degrees": observation.touch_bearing_degrees,
                "touch_urgency": observation.touch_urgency,
                "threat_id": observation.threat_id,
                "obstacle_id": observation.obstacle_id,
                "obstacle_contact": observation.obstacle_contact,
                "nearby_obstacle_ids": list(observation.nearby_obstacle_ids),
                "collision_ids": list(motion.collision_ids),
                "boundary_contacts": list(motion.boundary_contacts),
                "blocked": motion.blocked,
            }
            trajectory.append(
                {
                    "time_ms": float(time_ms),
                    "position_x": float(position_x),
                    "position_y": float(position_y),
                    "heading_degrees": float(heading),
                    "body_before": {
                        "x": float(body_before_x),
                        "y": float(body_before_y),
                        "heading_degrees": float(body_before_heading),
                    },
                    "body_requested": {
                        "x": float(requested_x),
                        "y": float(requested_y),
                        "heading_degrees": float(heading),
                    },
                    "body_after": {
                        "x": float(position_x),
                        "y": float(position_y),
                        "heading_degrees": float(heading),
                    },
                    "motion": motion.as_dict(),
                    "world_cause": world_cause,
                    "action": action.name,
                    "action_source": action.source,
                    "action_reason": action.reason,
                    "neural_cause": {
                        "active_descending_nodes": sorted(
                            {
                                body_id
                                for ids in output_nodes.values()
                                for body_id in ids
                            }
                        ),
                        "output_votes": dict(circuit_step.output_votes),
                        "winning_output_nodes": output_nodes.get(action.name, []),
                        "input_groups": feature_state["input_currents"],
                        "visual_features": feature_state["visual_features"],
                        "world_event": world_cause,
                    },
                    "turn_command_degrees": float(action.turn_degrees),
                    "forward_step": float(
                        run_config.neural.forward_step_per_target_spike
                        if action.move_forward
                        else 0.0
                    ),
                    "active_spikes": list(active),
                    "touch_stimulus_active": observation.touch_active,
                    "visual_stimulus_active": observation.visual_active,
                    "stimulus_active": observation.touch_active or observation.visual_active,
                    "threat_id": observation.threat_id,
                    "threat_bearing_degrees": observation.threat_bearing_degrees,
                    "threat_urgency": observation.threat_urgency,
                    "touch_source": observation.touch_source,
                    "touch_id": observation.touch_id,
                    "touch_bearing_degrees": observation.touch_bearing_degrees,
                    "touch_urgency": observation.touch_urgency,
                    "obstacle_id": observation.obstacle_id,
                    "obstacle_bearing_degrees": observation.obstacle_bearing_degrees,
                    "obstacle_distance": observation.obstacle_distance,
                    "obstacle_contact": observation.obstacle_contact,
                    "nearby_obstacle_ids": list(observation.nearby_obstacle_ids),
                    "retina": list(observation.retina),
                    "retina_delta": list(observation.retina_delta),
                    "retina_width": run_config.retina_width,
                    "retina_height": run_config.retina_height,
                    "retina_mean": observation.retina_mean,
                    "retina_max": observation.retina_max,
                    "retina_centroid_x": observation.retina_centroid_x,
                    "retina_left": observation.retina_left,
                    "retina_center": observation.retina_center,
                    "retina_right": observation.retina_right,
                    "motion_energy": observation.motion_energy,
                    "motion_centroid_x": observation.motion_centroid_x,
                    "looming_score": observation.looming_score,
                    "visual_features": feature_state["visual_features"],
                    "input_currents": feature_state["input_currents"],
                    "memory_visual_active": feature_state["memory_visual_active"],
                    "memory_visual_gain": feature_state["memory_visual_gain"],
                    "threat_gain": feature_state["threat_gain"],
                    "memory": {
                        "target_persistence_remaining_ms": float(target_memory_remaining_ms),
                        "target_persistence_gain": float(feature_state["memory_visual_gain"]),
                        "visual_active_from_memory": bool(feature_state["memory_visual_active"]),
                        "escape_cooldown_remaining_ms": float(memory.escape_cooldown_remaining_ms),
                        "recovery_remaining_ms": float(memory.recovery_remaining_ms),
                        "threat_encounter_counts": {
                            threat_id: int(count)
                            for threat_id, count in sorted(memory.threat_encounters.items())
                        },
                        "active_threat_ids": sorted(memory.active_threat_ids),
                        "obstacle_encounter_counts": {
                            obstacle_id: int(count)
                            for obstacle_id, count in sorted(memory.obstacle_encounters.items())
                        },
                        "active_obstacle_ids": sorted(memory.active_obstacle_ids),
                        "habituation_gain": float(feature_state["threat_gain"]),
                    },
                    "escape_cooldown_remaining_ms": memory.escape_cooldown_remaining_ms,
                    "recovery_remaining_ms": memory.recovery_remaining_ms,
                    "touch_output_spike": touch_output_spike,
                    "visual_output_spike": visual_output_spike,
                    "touch_target_spike": touch_output_spike,
                    "visual_target_spike": visual_output_spike,
                    "target_spike": touch_output_spike or visual_output_spike,
                    "lights": frame_lights,
                    "threats": frame_threats,
                    "obstacles": [obstacle.as_dict() for obstacle in run_config.obstacles],
                    "escape_marker": action.name.startswith("escape_"),
                }
            )
            previous_retina = observation.retina
            lights, threats = advance_arena_objects(
                run_config,
                lights,
                threats,
                dt_ms=run_config.neural.dt_ms,
            )

        final = trajectory[-1]
        action_counts = Counter(row["action"] for row in trajectory)
        visual_output_times = [
            row["time_ms"] for row in trajectory if row["visual_output_spike"]
        ]
        touch_output_times = [
            row["time_ms"] for row in trajectory if row["touch_output_spike"]
        ]
        distance_to_light = [
            min(
                math.hypot(light["x"] - row["position_x"], light["y"] - row["position_y"])
                for light in row["lights"]
            )
            for row in trajectory
            if row["lights"]
        ]
        digest_payload = {
            "stage": stage.stage,
            "trajectory": trajectory,
            "spikes_by_time": spikes_by_time,
        }
        import hashlib
        import json

        replay_digest = hashlib.sha256(
            json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {
            "schema_version": ARENA_SCHEMA_VERSION,
            "experiment": "scalable closed-loop synthetic-retina arena",
            "dataset": {
                "name": "FlyEM Male CNS",
                "release": "v1.0",
                "source_manifest": "data/metadata/source_manifest.json",
            },
            "pathways": {
                channel.name: _path_summary(channel) for channel in stage.channels
            },
            "network": {
                "stage": stage.stage,
                "requested_node_count": run_config.network_stage,
                "target_node_count": stage.target_node_count,
                "actual_node_count": len(stage.nodes),
                "node_count": len(stage.nodes),
                "edge_count": len(stage.edges),
                "unified": stage.unified,
                "channels": {
                    channel.name: {
                        "node_count": len(channel.network.nodes),
                        "edge_count": len(channel.network.edges),
                    }
                    for channel in stage.channels
                },
                "selection": stage.selection,
                "input_groups": runtime.group_metadata(),
                "input_group_details": runtime.group_details(),
            },
            "parameters": {
                **asdict(run_config.neural),
                "neural": asdict(run_config.neural),
                "mode": run_config.mode,
                "network_stage": run_config.network_stage,
                "visual_contrast": run_config.visual_contrast,
                "visual_coupling_mv_per_synapse": run_config.visual_coupling_mv_per_synapse,
                "visual_deadband": run_config.visual_deadband,
                "escape_turn_degrees": run_config.escape_turn_degrees,
                "body_radius": run_config.body_radius,
                "touch_range": run_config.touch_range,
                "memory": asdict(run_config.memory),
            },
            "action_decoder": {
                "mode": "descending_population_votes",
                "direct_retinal_centroid_steering": False,
                "touch_priority": decoder_policy == "touch_priority",
                "policy": decoder_policy,
                "actions": list(ACTION_ORDER),
                "mapping": {
                    "visual_left": "turn_left",
                    "visual_right": "turn_right",
                    "visual_center": "forward",
                    "touch_left": "escape_right",
                    "touch_right": "escape_left",
                },
                "heading_convention": "positive degrees rotate counterclockwise; arbitrary toy axis",
            },
            "environment": {
                "mode": run_config.mode,
                "bounds": run_config.bounds,
                "body_radius": run_config.body_radius,
                "touch_range": run_config.touch_range,
                "lights": [light.as_dict() for light in run_config.lights],
                "threats": [threat.as_dict() for threat in run_config.threats],
                "obstacles": [obstacle.as_dict() for obstacle in run_config.obstacles],
                "motion_model": "constant velocity with boundary reflection",
                "body_model": "circle with swept axis-separated AABB collision resolution",
                "retina": {
                    "width": run_config.retina_width,
                    "height": run_config.retina_height,
                    "fov_degrees": run_config.retina_fov_degrees,
                    "max_range": run_config.retina_max_range,
                    "layout": "row-major, left-to-right columns, synthetic luminance",
                },
            },
            "nodes": list(stage.nodes),
            "edges": list(stage.edges),
            "trajectory": trajectory,
            "spikes_by_time": spikes_by_time,
            "spike_events": spike_events,
            "replay_digest": replay_digest,
            "outcome": {
                "action_counts": dict(sorted(action_counts.items())),
                "visual_target_spike_count": len(visual_output_times),
                "touch_target_spike_count": len(touch_output_times),
                "target_spike_count": len(visual_output_times) + len(touch_output_times),
                "visual_stimulus_frame_count": sum(
                    bool(row["visual_stimulus_active"]) for row in trajectory
                ),
                "touch_stimulus_frame_count": sum(
                    bool(row["touch_stimulus_active"]) for row in trajectory
                ),
                "escape_event_count": sum(bool(row["escape_marker"]) for row in trajectory),
                "collision_event_count": sum(
                    bool(row["motion"]["collision_ids"]) for row in trajectory
                ),
                "blocked_frame_count": sum(
                    bool(row["motion"]["blocked"]) for row in trajectory
                ),
                "collision_ids": sorted(
                    {
                        obstacle_id
                        for row in trajectory
                        for obstacle_id in row["motion"]["collision_ids"]
                    }
                ),
                "first_visual_target_spike_ms": visual_output_times[0]
                if visual_output_times
                else None,
                "first_touch_target_spike_ms": touch_output_times[0]
                if touch_output_times
                else None,
                "initial_distance_to_light": distance_to_light[0]
                if distance_to_light
                else None,
                "minimum_distance_to_light": min(distance_to_light)
                if distance_to_light
                else None,
                "final_distance_to_light": distance_to_light[-1]
                if distance_to_light
                else None,
                "final_heading_degrees": final["heading_degrees"],
                "final_position": [final["position_x"], final["position_y"]],
                "total_spikes": sum(spike_counts.values()),
                "spike_counts": {str(body_id): count for body_id, count in sorted(spike_counts.items())},
            },
            "notes": [
                "The connectome nodes and edges come from the official local Male CNS v1.0 release.",
                "The retina, moving arena, memory state, and descending-population action mapping are explicit experiment assumptions.",
                "The 9x5 retina is an environmental sensor front-end; it is not a complete biological retina.",
                "Stage 54 preserves separate local contexts; stages 100 and 250 run a unified induced graph.",
            ],
        }

    def run(
        self,
        config: ArenaRunConfig | Mapping[str, Any] | None = None,
        *,
        decoder_policy: str = "touch_priority",
    ) -> dict[str, Any]:
        if config is None:
            run_config = ArenaRunConfig()
        elif isinstance(config, ArenaRunConfig):
            run_config = config
        else:
            run_config = ArenaRunConfig.from_mapping(config)
        run_config.validate()
        if decoder_policy not in {"touch_priority", "strongest_vote"}:
            raise ValueError(f"unknown decoder policy: {decoder_policy}")
        try:
            stage = self.stages[run_config.network_stage]
        except KeyError as error:
            raise ValueError(
                f"network stage {run_config.network_stage} is not available in this model"
            ) from error
        return self._run_stage(stage, run_config, decoder_policy=decoder_policy)

    def create_session(
        self, config: ArenaRunConfig | Mapping[str, Any] | None = None
    ) -> ArenaSession:
        """Create a stateful neural session for an external world client."""

        if config is None:
            run_config = ArenaRunConfig()
        elif isinstance(config, ArenaRunConfig):
            run_config = config
        else:
            run_config = ArenaRunConfig.from_mapping(config)
        run_config.validate()
        try:
            stage = self.stages[run_config.network_stage]
        except KeyError as error:
            raise ValueError(
                f"network stage {run_config.network_stage} is not available in this model"
            ) from error
        neural_lif = run_config.neural.to_lif()
        visual_lif = replace(
            neural_lif,
            mv_per_synapse=run_config.visual_coupling_mv_per_synapse,
            input_current_mv=run_config.neural.input_current_mv * run_config.visual_contrast,
        )
        return ArenaSession(
            stage,
            self._runtime_for(stage, neural_lif, visual_lif),
            run_config,
        )
