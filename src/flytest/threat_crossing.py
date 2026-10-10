"""Compare the arena's response to a moving threat across three graph stages.

This diagnostic keeps the existing arena runtime unchanged and asks a narrow
behavior question: when a moving threat crosses the fly's route, does the
connectome-backed touch pathway produce a threat-linked escape action? Each
stage runs the same beacon scenario once as a no-threat control and once with
the baseline threat geometry. The 1,024-node stage also runs two nearby threat
geometries to test narrow response generalization. A response is evidence from
the causal trace, not a claim of biological avoidance.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from .arena_simulation import (
    ARENA_NETWORK_STAGES,
    ArenaLight,
    ArenaRunConfig,
    ArenaThreat,
)
from .data import MaleCNSPaths
from .sensorimotor import SensorimotorConfig
from .visual_simulation import VisualModel


COMPARISON_STAGES = (54, 250, 1024)
GENERALIZATION_STAGE = 1024
BASELINE_GEOMETRY_ID = "centerline"
THREAT_ID = "crossing-threat"
REQUIRED_FRAME_FIELDS = (
    "world_cause",
    "neural_cause",
    "threat_id",
    "input_currents",
    "active_spikes",
    "action",
    "action_source",
    "position_x",
    "position_y",
    "touch_source",
    "touch_target_spike",
    "threats",
)


class _ArenaRunner(Protocol):
    """The small part of ``VisualModel`` needed by this diagnostic."""

    def run_arena(self, config: ArenaRunConfig) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class ThreatGeometry:
    """One deterministic threat path used by the crossing diagnostic."""

    geometry_id: str
    start_x: float
    start_y: float
    vx: float
    vy: float

    def validate(self) -> None:
        if not self.geometry_id:
            raise ValueError("geometry_id must be non-empty")
        for name, value in (
            ("start_x", self.start_x),
            ("start_y", self.start_y),
            ("vx", self.vx),
            ("vy", self.vy),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if max(abs(self.vx), abs(self.vy)) > 1.0:
            raise ValueError("geometry velocity components must be between -1 and 1")


@dataclass(frozen=True)
class ThreatCrossingConfig:
    """Fixed moving-threat scenario used for stage comparison and geometry tests."""

    duration_ms: float = 60.0
    stages: tuple[int, ...] = COMPARISON_STAGES
    beacon_x: float = 2.0
    beacon_y: float = 2.0
    beacon_intensity: float = 1.0
    threat_start_x: float = 0.6
    threat_start_y: float = -0.3
    threat_radius: float = 0.65
    threat_vx: float = 0.0
    threat_vy: float = 0.1
    threat_active_start_ms: float = 0.0
    threat_active_end_ms: float = 60.0
    initial_x: float = 0.0
    initial_y: float = 0.0
    initial_heading_degrees: float = 0.0
    turn_degrees_per_target_spike: float = 15.0
    forward_step_per_target_spike: float = 0.25

    def baseline_geometry(self) -> ThreatGeometry:
        return ThreatGeometry(
            BASELINE_GEOMETRY_ID,
            self.threat_start_x,
            self.threat_start_y,
            self.threat_vx,
            self.threat_vy,
        )

    def geometry_matrix(self) -> tuple[ThreatGeometry, ...]:
        """Return the baseline plus two nearby paths for the 1,024-node run."""

        baseline = self.baseline_geometry()
        return (
            baseline,
            ThreatGeometry(
                "right-lane",
                baseline.start_x + 0.7,
                baseline.start_y - 0.2,
                baseline.vx,
                baseline.vy,
            ),
            ThreatGeometry(
                "late-crossing",
                baseline.start_x + 0.4,
                baseline.start_y - 0.7,
                baseline.vx,
                baseline.vy,
            ),
        )

    def validate(self) -> None:
        if not math.isfinite(self.duration_ms) or not 1.0 <= self.duration_ms <= 300.0:
            raise ValueError("duration_ms must be between 1 and 300")
        if tuple(self.stages) != COMPARISON_STAGES:
            raise ValueError(f"stages must be exactly {COMPARISON_STAGES}")
        if GENERALIZATION_STAGE not in self.stages:
            raise ValueError(f"stages must include {GENERALIZATION_STAGE} for geometry tests")
        for stage in self.stages:
            if stage not in ARENA_NETWORK_STAGES:
                raise ValueError(f"stage must be one of {ARENA_NETWORK_STAGES}")
        for name, value in (
            ("beacon_x", self.beacon_x),
            ("beacon_y", self.beacon_y),
            ("beacon_intensity", self.beacon_intensity),
            ("threat_start_x", self.threat_start_x),
            ("threat_start_y", self.threat_start_y),
            ("threat_radius", self.threat_radius),
            ("threat_vx", self.threat_vx),
            ("threat_vy", self.threat_vy),
            ("threat_active_start_ms", self.threat_active_start_ms),
            ("threat_active_end_ms", self.threat_active_end_ms),
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
        if not 0.0 < self.threat_radius <= 4.0:
            raise ValueError("threat_radius must be between 0 and 4")
        if max(abs(self.threat_vx), abs(self.threat_vy)) > 1.0:
            raise ValueError("threat velocity components must be between -1 and 1")
        if self.threat_active_start_ms < 0.0:
            raise ValueError("threat_active_start_ms must be non-negative")
        if self.threat_active_end_ms <= self.threat_active_start_ms:
            raise ValueError("threat active interval is invalid")
        if self.threat_active_end_ms < self.duration_ms:
            raise ValueError("threat active interval must cover the replay")
        if self.forward_step_per_target_spike <= 0.0:
            raise ValueError("forward_step_per_target_spike must be positive")
        for geometry in self.geometry_matrix():
            geometry.validate()

    def to_arena_config(
        self,
        stage: int,
        *,
        include_threat: bool,
        geometry: ThreatGeometry | None = None,
    ) -> ArenaRunConfig:
        """Build one control or crossing run without changing arena defaults."""

        self.validate()
        selected_geometry = geometry or self.baseline_geometry()
        selected_geometry.validate()
        threat = ArenaThreat(
            THREAT_ID,
            selected_geometry.start_x,
            selected_geometry.start_y,
            self.threat_radius,
            "collision",
            self.threat_active_start_ms,
            self.threat_active_end_ms,
            selected_geometry.vx,
            selected_geometry.vy,
        )
        config = ArenaRunConfig(
            mode="sandbox",
            network_stage=stage,
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
            threats=(threat,) if include_threat else (),
            obstacles=(),
        )
        config.validate()
        return config


def _require_network_gate(network: dict[str, Any], stage: int) -> None:
    actual_stage = int(network.get("stage", -1))
    actual_nodes = int(network.get("actual_node_count", 0))
    if actual_stage != stage:
        raise ValueError(f"arena returned stage {actual_stage}, expected {stage}")
    if actual_nodes != stage:
        raise ValueError(f"arena returned {actual_nodes} nodes for stage {stage}")
    if int(network.get("edge_count", 0)) <= 0:
        raise ValueError("threat crossing graph must contain induced edges")


def _causal_trace_summary(trajectory: list[dict[str, Any]]) -> dict[str, Any]:
    complete_frame_count = sum(
        all(field in row for field in REQUIRED_FRAME_FIELDS) for row in trajectory
    )
    return {
        "required_fields": list(REQUIRED_FRAME_FIELDS),
        "frame_count": len(trajectory),
        "complete_frame_count": complete_frame_count,
        "complete": bool(trajectory) and complete_frame_count == len(trajectory),
    }


def _threat_distance(row: dict[str, Any]) -> float | None:
    threats = row.get("threats")
    if not isinstance(threats, list):
        return None
    threat = next(
        (item for item in threats if isinstance(item, dict) and item.get("id") == THREAT_ID),
        None,
    )
    if threat is None:
        return None
    try:
        return math.hypot(
            float(threat["x"]) - float(row["position_x"]),
            float(threat["y"]) - float(row["position_y"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _first_time_ms(rows: list[dict[str, Any]]) -> float | None:
    for row in rows:
        try:
            value = float(row["time_ms"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            return value
    return None


def _latency_ms(start_ms: float | None, end_ms: float | None) -> float | None:
    if start_ms is None or end_ms is None:
        return None
    return end_ms - start_ms


def _response_detected(metrics: dict[str, Any]) -> bool:
    return bool(
        metrics["threat_detected_frame_count"] > 0
        and metrics["threat_touch_output_spike_count"] > 0
        and metrics["threat_escape_action_count"] > 0
    )


def _stage_metrics(
    payload: dict[str, Any],
    *,
    stage: int,
    condition: str,
    geometry_id: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    network = dict(payload.get("network") or {})
    _require_network_gate(network, stage)
    trajectory = list(payload.get("trajectory") or [])
    if not trajectory:
        raise ValueError(f"{condition} stage {stage} replay produced no trajectory")
    causal_trace = _causal_trace_summary(trajectory)
    escape_rows = [
        row for row in trajectory if str(row.get("action", "")).startswith("escape_")
    ]
    threat_rows = [
        row
        for row in trajectory
        if row.get("threat_id") == THREAT_ID and row.get("touch_source") == "threat"
    ]
    threat_spike_rows = [row for row in threat_rows if row.get("touch_target_spike")]
    threat_escape_rows = [
        row for row in threat_rows
        if str(row.get("action", "")).startswith("escape_")
        and row.get("action_source") == "touch"
    ]
    threat_detected_first_time_ms = _first_time_ms(threat_rows)
    threat_touch_output_first_time_ms = _first_time_ms(threat_spike_rows)
    threat_escape_first_time_ms = _first_time_ms(threat_escape_rows)
    distances = [distance for row in trajectory if (distance := _threat_distance(row)) is not None]
    action_counts = Counter(str(row.get("action", "")) for row in trajectory)
    metrics = {
        "condition": condition,
        "geometry_id": geometry_id,
        "stage": stage,
        "frame_count": len(trajectory),
        "causal_trace_complete": causal_trace["complete"],
        "complete_frame_count": causal_trace["complete_frame_count"],
        "action_counts": dict(sorted(action_counts.items())),
        "escape_action_count": len(escape_rows),
        "threat_detected_frame_count": len(threat_rows),
        "threat_touch_output_spike_count": len(threat_spike_rows),
        "threat_escape_action_count": len(threat_escape_rows),
        "threat_detected_first_time_ms": threat_detected_first_time_ms,
        "threat_touch_output_first_time_ms": threat_touch_output_first_time_ms,
        "threat_escape_first_time_ms": threat_escape_first_time_ms,
        "touch_response_latency_ms": _latency_ms(
            threat_detected_first_time_ms,
            threat_touch_output_first_time_ms,
        ),
        "escape_response_latency_ms": _latency_ms(
            threat_detected_first_time_ms,
            threat_escape_first_time_ms,
        ),
        "minimum_threat_distance": min(distances) if distances else None,
        "replay_digest": payload.get("replay_digest"),
        "network": {
            key: network.get(key)
            for key in (
                "stage",
                "requested_node_count",
                "actual_node_count",
                "edge_count",
                "unified",
            )
        },
    }
    rows = _trajectory_rows(
        trajectory,
        stage=stage,
        condition=condition,
        geometry_id=geometry_id,
    )
    return metrics, rows


def _trajectory_rows(
    trajectory: list[dict[str, Any]],
    *,
    stage: int,
    condition: str,
    geometry_id: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(trajectory):
        rows.append(
            {
                "stage": stage,
                "condition": condition,
                "geometry_id": geometry_id,
                "frame": index,
                "time_ms": row.get("time_ms"),
                "position_x": row.get("position_x"),
                "position_y": row.get("position_y"),
                "threat_id": row.get("threat_id"),
                "threat_distance": _threat_distance(row),
                "touch_source": row.get("touch_source"),
                "touch_urgency": row.get("touch_urgency"),
                "touch_target_spike": row.get("touch_target_spike"),
                "action": row.get("action"),
                "action_source": row.get("action_source"),
                "escape_marker": row.get("escape_marker"),
                "active_spike_count": len(row.get("active_spikes", [])),
            }
        )
    return rows


def _write_trajectory_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "stage",
        "condition",
        "geometry_id",
        "frame",
        "time_ms",
        "position_x",
        "position_y",
        "threat_id",
        "threat_distance",
        "touch_source",
        "touch_urgency",
        "touch_target_spike",
        "action",
        "action_source",
        "escape_marker",
        "active_spike_count",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _report_markdown(summary: dict[str, Any]) -> str:
    def format_time(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.2f} ms"

    rows = []
    for stage in COMPARISON_STAGES:
        stage_summary = summary["stages"][str(stage)]
        control = stage_summary["control"]
        crossing = stage_summary["crossing"]
        rows.append(
            "| `{stage}` | `{control_escape}` | `{detected}` | `{spikes}` | `{escape}` | `{latency}` | `{response}` |".format(
                stage=stage,
                control_escape=control["escape_action_count"],
                detected=crossing["threat_detected_frame_count"],
                spikes=crossing["threat_touch_output_spike_count"],
                escape=crossing["threat_escape_action_count"],
                latency=format_time(crossing["escape_response_latency_ms"]),
                response=stage_summary["response_detected"],
            )
        )
    response_count = summary["result"]["response_detected_stage_count"]
    response_label = "response detected" if response_count else "no threat-linked escape response detected"
    generalization_stage = summary["result"]["geometry_generalization_stage"]
    generalization_summary = summary["stages"][str(generalization_stage)]
    geometry_rows = []
    for geometry_id, geometry_summary in generalization_summary["geometries"].items():
        if geometry_id == BASELINE_GEOMETRY_ID:
            continue
        crossing = geometry_summary["crossing"]
        geometry_rows.append(
            "| `{geometry}` | `{detected}` | `{spikes}` | `{escape}` | `{latency}` | `{response}` |".format(
                geometry=geometry_id,
                detected=crossing["threat_detected_frame_count"],
                spikes=crossing["threat_touch_output_spike_count"],
                escape=crossing["threat_escape_action_count"],
                latency=format_time(crossing["escape_response_latency_ms"]),
                response=geometry_summary["response_detected"],
            )
        )
    geometry_response_count = summary["result"]["geometry_variant_response_count"]
    geometry_variant_count = summary["result"]["geometry_variant_count"]
    lines = [
        "# Threat crossing",
        "",
        "A deterministic moving-threat replay compared with a no-threat control at stages 54, 250, and 1,024.",
        "The experiment asks whether a threat crossing the toy fly's route produces a threat-linked escape action through the existing causal chain, then checks two nearby paths at 1,024 nodes.",
        "",
        "## Result",
        "",
        f"- Structural run: `{summary['result']['success']}`",
        f"- Behavioral readout: **{response_label}** in `{response_count}` of `{len(COMPARISON_STAGES)}` stages",
        "",
        "| Stage | Control escape actions | Threat frames sensed | Threat touch spikes | Threat-linked escapes | Escape latency | Response detected |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        *rows,
        "",
        "## Geometry generalization",
        "",
        f"At stage `{generalization_stage}`, `{geometry_response_count}` of `{geometry_variant_count}` nearby threat geometries produced the same causal response criterion. Escape latency is measured from first threat sensing to the first touch-sourced escape action.",
        "",
        "| Geometry | Threat frames sensed | Threat touch spikes | Threat-linked escapes | Escape latency | Response detected |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
        *geometry_rows,
        "",
        "## What the columns mean",
        "",
        "- Threat frames sensed: the moving threat became the world's active touch source.",
        "- Threat touch spikes: the touch population produced an output spike while the threat was sensed.",
        "- Threat-linked escapes: the selected action was an escape action with `action_source=touch` while the threat was sensed.",
        "- Escape latency: elapsed replay time between first threat sensing and the first threat-linked escape action.",
        "- Response detected: threat sensed, touch output spike present, and at least one threat-linked escape action; the no-threat control is reported separately.",
        "",
        "## Boundaries",
        "",
        "- Real: node/edge wiring and the native-sign runtime come from the local FlyEM Male CNS v1.0 release.",
        "- Assumed: the synthetic retina, static beacon, moving threat, collision-radius sensing, point-mass body, and action decoder.",
        "- Demonstrated: this narrow stage and geometry matrix's causal response, if any. It does not demonstrate biological predator avoidance, learning, or broad generalization.",
        "",
        f"Scenario parameters: `{json.dumps(summary['configuration'], sort_keys=True)}`",
        "",
    ]
    return "\n".join(lines)


def run_threat_crossing(
    model: _ArenaRunner,
    *,
    output_dir: Path,
    config: ThreatCrossingConfig | None = None,
) -> dict[str, Any]:
    """Run controls, baseline crossings, and a small 1,024-node geometry matrix."""

    scenario = config or ThreatCrossingConfig()
    scenario.validate()
    stage_summaries: dict[str, Any] = {}
    trajectory_rows: list[dict[str, Any]] = []
    response_detected_stage_count = 0
    geometry_variant_response_count = 0
    baseline_geometry = scenario.baseline_geometry()
    variant_geometries = tuple(scenario.geometry_matrix()[1:])

    for stage in scenario.stages:
        control_payload = model.run_arena(
            scenario.to_arena_config(stage, include_threat=False)
        )
        crossing_payload = model.run_arena(
            scenario.to_arena_config(
                stage,
                include_threat=True,
                geometry=baseline_geometry,
            )
        )
        control_metrics, control_rows = _stage_metrics(
            control_payload,
            stage=stage,
            condition="control",
            geometry_id="control",
        )
        crossing_metrics, crossing_rows = _stage_metrics(
            crossing_payload,
            stage=stage,
            condition="crossing",
            geometry_id=baseline_geometry.geometry_id,
        )
        trajectory_rows.extend(control_rows)
        trajectory_rows.extend(crossing_rows)
        response_detected = _response_detected(crossing_metrics)
        if response_detected:
            response_detected_stage_count += 1
        geometry_summaries: dict[str, Any] = {
            baseline_geometry.geometry_id: {
                "crossing": crossing_metrics,
                "response_detected": response_detected,
            }
        }
        if stage == GENERALIZATION_STAGE:
            for geometry in variant_geometries:
                geometry_condition = f"crossing:{geometry.geometry_id}"
                geometry_payload = model.run_arena(
                    scenario.to_arena_config(
                        stage,
                        include_threat=True,
                        geometry=geometry,
                    )
                )
                geometry_metrics, geometry_rows = _stage_metrics(
                    geometry_payload,
                    stage=stage,
                    condition=geometry_condition,
                    geometry_id=geometry.geometry_id,
                )
                trajectory_rows.extend(geometry_rows)
                geometry_response_detected = _response_detected(geometry_metrics)
                if geometry_response_detected:
                    geometry_variant_response_count += 1
                geometry_summaries[geometry.geometry_id] = {
                    "crossing": geometry_metrics,
                    "response_detected": geometry_response_detected,
                }
        stage_summaries[str(stage)] = {
            "control": control_metrics,
            "crossing": crossing_metrics,
            "geometries": geometry_summaries,
            "causal_trace_complete": bool(
                control_metrics["causal_trace_complete"]
                and crossing_metrics["causal_trace_complete"]
                and all(
                    geometry_summary["crossing"]["causal_trace_complete"]
                    for geometry_summary in geometry_summaries.values()
                )
            ),
            "response_detected": response_detected,
        }

    summary: dict[str, Any] = {
        "experiment": "deterministic threat crossing",
        "dataset": {
            "name": "FlyEM Male CNS",
            "release": "v1.0",
            "source_manifest": "data/metadata/source_manifest.json",
        },
        "configuration": {
            **asdict(scenario),
            "baseline_geometry_id": baseline_geometry.geometry_id,
            "geometry_generalization_stage": GENERALIZATION_STAGE,
            "geometry_matrix": [asdict(geometry) for geometry in scenario.geometry_matrix()],
        },
        "stages": stage_summaries,
        "result": {
            "success": all(
                stage_summary["causal_trace_complete"]
                for stage_summary in stage_summaries.values()
            ),
            "response_detected_stage_count": response_detected_stage_count,
            "response_detected_any": response_detected_stage_count > 0,
            "geometry_generalization_stage": GENERALIZATION_STAGE,
            "geometry_variant_count": len(variant_geometries),
            "geometry_variant_response_count": geometry_variant_response_count,
            "geometry_variant_response_any": geometry_variant_response_count > 0,
        },
        "notes": [
            "Each stage uses the same static beacon and baseline moving collision-triggered threat.",
            "A no-threat control is run once at every stage and reused as the comparison for the geometry matrix.",
            "The 1,024-node stage adds two nearby threat geometries without changing the neural or body parameters.",
            "A behavioral response requires threat sensing, a touch output spike, and a touch-sourced escape action.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"
    report_path = output_dir / "report.md"
    trajectory_path = output_dir / "trajectory.csv"
    summary["outputs"] = {
        "summary": str(summary_path),
        "report": str(report_path),
        "trajectory": str(trajectory_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(_report_markdown(summary), encoding="utf-8")
    _write_trajectory_csv(trajectory_path, trajectory_rows)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the FlyTest threat-crossing diagnostic")
    parser.add_argument("--data-dir", type=Path, default=Path("data/working/male-cns-v1.0"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/diagnostics/threat-crossing"),
    )
    parser.add_argument("--duration-ms", type=float, default=60.0)
    args = parser.parse_args()

    model = VisualModel(MaleCNSPaths(args.data_dir))
    summary = run_threat_crossing(
        model,
        output_dir=args.output,
        config=ThreatCrossingConfig(duration_ms=args.duration_ms),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["result"]["success"]:
        raise SystemExit("threat crossing diagnostic did not produce complete causal traces")


if __name__ == "__main__":
    main()
