"""Re-run one competing-cue scene with two batch action decoders.

The replays share a graph, world, and initial state. Their neural inputs are
matched through the first differing action; after that, each run is genuinely
closed-loop and its future sensory stream may diverge.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Protocol

from .arena_simulation import ArenaRunConfig
from .data import MaleCNSPaths
from .threat_crossing import ThreatCrossingConfig
from .visual_simulation import VisualModel


STAGE = 1024
ESCAPE_ACTIONS = ("escape_left", "escape_right")
VISUAL_ACTIONS = ("turn_left", "turn_right", "forward")
CSV_COLUMNS = (
    "condition", "policy", "time_ms", "action", "action_source",
    "touch_stimulus_active", *ESCAPE_ACTIONS, *VISUAL_ACTIONS,
    "body_before_x", "body_before_y", "body_after_x", "body_after_y",
    "escape_cooldown_after_ms",
)


class ArenaRunner(Protocol):
    def run_arena(
        self, config: ArenaRunConfig, *, decoder_policy: str = "touch_priority"
    ) -> dict[str, Any]: ...


def compare_replays(
    priority: list[dict[str, Any]], strongest: list[dict[str, Any]]
) -> dict[str, Any]:
    """Identify the first policy-caused action difference on matched inputs."""
    if not priority or len(priority) != len(strongest):
        raise ValueError("paired trajectories must be nonempty and have equal frame counts")
    for index, (left, right) in enumerate(zip(priority, strongest)):
        # A difference before the action means this is not a controlled decoder test.
        for key in ("time_ms", "input_currents", "retina", "body_before"):
            if left[key] != right[key]:
                raise ValueError(f"unmatched pre-decision state at {left['time_ms']} ms: {key}")
        left_votes = left["neural_cause"]["output_votes"]
        right_votes = right["neural_cause"]["output_votes"]
        if left_votes != right_votes:
            raise ValueError(f"unmatched pre-decision state at {left['time_ms']} ms: votes")
        if left["action"] == right["action"]:
            if left["body_after"] != right["body_after"]:
                raise ValueError(f"unmatched body after equal action at {left['time_ms']} ms")
            continue

        cooldown_before = (
            float(priority[index - 1]["escape_cooldown_remaining_ms"]) if index else 0.0
        )
        touch_vote = max(float(left_votes.get(action, 0.0)) for action in ESCAPE_ACTIONS)
        visual_vote = max(float(left_votes.get(action, 0.0)) for action in VISUAL_ACTIONS)
        clean_competition = (
            bool(left["touch_stimulus_active"])
            and cooldown_before <= 0.0
            and touch_vote > 0.0
            and visual_vote > touch_vote
            and left["action"] in ESCAPE_ACTIONS
            and left["action_source"] == "touch"
            and right["action"] in VISUAL_ACTIONS
        )
        return {
            "status": "decoder_changed_action" if clean_competition else "different_action_without_clean_competition",
            "first_action_divergence_ms": float(left["time_ms"]),
            "matched_prefix_frames": index,
            "votes_at_divergence": dict(left_votes),
            "touch_vote": touch_vote,
            "visual_vote": visual_vote,
            "priority_action": left["action"],
            "strongest_action": right["action"],
            "escape_cooldown_before_ms": cooldown_before,
            "priority_body_after": left["body_after"],
            "strongest_body_after": right["body_after"],
        }
    return {
        "status": "no_action_divergence",
        "first_action_divergence_ms": None,
        "matched_prefix_frames": len(priority),
    }


def _rows(condition: str, policy: str, frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for frame in frames:
        votes = frame["neural_cause"]["output_votes"]
        rows.append({
            "condition": condition,
            "policy": policy,
            "time_ms": frame["time_ms"],
            "action": frame["action"],
            "action_source": frame["action_source"],
            "touch_stimulus_active": frame["touch_stimulus_active"],
            **{action: float(votes.get(action, 0.0)) for action in (*ESCAPE_ACTIONS, *VISUAL_ACTIONS)},
            "body_before_x": frame["body_before"]["x"],
            "body_before_y": frame["body_before"]["y"],
            "body_after_x": frame["body_after"]["x"],
            "body_after_y": frame["body_after"]["y"],
            "escape_cooldown_after_ms": frame["escape_cooldown_remaining_ms"],
        })
    return rows


def _report(summary: dict[str, Any]) -> str:
    result = summary["comparison"]
    lines = [
        "# Competing-cue decoder replay",
        "",
        "The stage-1,024 beacon/threat scene starts the collision-triggered threat",
        "at 2 ms. The graph, neural settings, world, and initial body state are",
        "identical for the touch-priority and strongest-vote batch replays.",
        "Only the decoder policy changes. A no-threat control uses touch priority.",
        "",
        f"Status: `{result['status']}`. No-threat control escapes: {summary['control_escape_count']}.",
        f"Strongest-vote crossing matches the control's action and body on "
        f"{summary['strongest_matches_control_action_body_frames']} of "
        f"{summary['frame_count']} frames.",
        "",
    ]
    if result["first_action_divergence_ms"] is not None:
        lines += [
            f"First different action: **{result['first_action_divergence_ms']:g} ms**,",
            f"after {result['matched_prefix_frames']} matched frames. Both policies",
            f"saw touch vote {result['touch_vote']:g} and visual vote {result['visual_vote']:g};",
            f"cooldown before the decision was {result['escape_cooldown_before_ms']:g} ms.",
            f"Touch priority chose `{result['priority_action']}`; strongest vote chose",
            f"`{result['strongest_action']}`.",
            "",
        ]
    priority_end = summary["endpoints"]["touch_priority"]
    strongest_end = summary["endpoints"]["strongest_vote"]
    lines += [
        "## Final body positions (toy world units)",
        "",
        "| Decoder | x | y | heading |",
        "| --- | ---: | ---: | ---: |",
        f"| Touch priority | {priority_end['x']:.2f} | {priority_end['y']:.2f} | {priority_end['heading_degrees']:.0f}° |",
        f"| Strongest vote | {strongest_end['x']:.2f} | {strongest_end['y']:.2f} | {strongest_end['heading_degrees']:.0f}° |",
        "",
    ]
    lines += [
        "The trajectory CSV shows votes, actual actions, and body positions in",
        "all three runs. Through the first different action the recorded neural",
        "inputs, votes, and pre-action body states match. After that, different",
        "body actions can alter future sensations and spikes; later differences",
        "are closed-loop consequences, not matched-input decoder comparisons.",
        "",
        "Connectome facts: the local FlyEM Male CNS release supplies node/edge",
        "wiring and native signs. Synthetic sensory input, LIF parameters,",
        "descending action labels, vote aggregation, memory, body, and both",
        "decoders are model assumptions. This tests one designed scene, not",
        "biological predator avoidance or robust behavior across scenes.",
        "",
    ]
    return "\n".join(lines)


def run_decoder_competition(
    model: ArenaRunner,
    *,
    output_dir: Path,
    scenario: ThreatCrossingConfig | None = None,
) -> dict[str, Any]:
    """Run a bounded no-threat control and two fully closed-loop policy replays."""
    scenario = scenario or ThreatCrossingConfig(duration_ms=12.0, threat_active_start_ms=2.0)
    scenario.validate()
    control_config = scenario.to_arena_config(STAGE, include_threat=False)
    crossing_config = scenario.to_arena_config(STAGE, include_threat=True)
    runs = (
        ("control", "touch_priority", control_config),
        ("crossing", "touch_priority", crossing_config),
        ("crossing", "strongest_vote", crossing_config),
    )
    trajectories: dict[tuple[str, str], list[dict[str, Any]]] = {}
    csv_rows: list[dict[str, Any]] = []
    for condition, policy, config in runs:
        payload = model.run_arena(config, decoder_policy=policy)
        network = payload["network"]
        if (
            int(network.get("stage", -1)) != STAGE
            or int(network.get("actual_node_count", -1)) != STAGE
            or int(network.get("edge_count", 0)) <= 0
        ):
            raise ValueError(f"{condition}/{policy} did not return an induced {STAGE}-node graph")
        frames = payload["trajectory"]
        if not frames:
            raise ValueError(f"{condition}/{policy} returned no frames")
        trajectories[(condition, policy)] = frames
        csv_rows.extend(_rows(condition, policy, frames))

    control = trajectories[("control", "touch_priority")]
    priority = trajectories[("crossing", "touch_priority")]
    strongest = trajectories[("crossing", "strongest_vote")]
    if len(control) != len(priority):
        raise ValueError("control and crossing runs must have equal frame counts")
    control_match_count = sum(
        left["action"] == right["action"] and left["body_after"] == right["body_after"]
        for left, right in zip(control, strongest)
    )
    summary = {
        "experiment": "stage-1024 competing-cue decoder replay",
        "stage": STAGE,
        "frame_count": len(priority),
        "scenario": {
            "duration_ms": scenario.duration_ms,
            "threat_active_start_ms": scenario.threat_active_start_ms,
            "beacon": [scenario.beacon_x, scenario.beacon_y],
            "threat_start": [scenario.threat_start_x, scenario.threat_start_y],
            "threat_velocity": [scenario.threat_vx, scenario.threat_vy],
        },
        "control_escape_count": sum(row["action"] in ESCAPE_ACTIONS for row in control),
        "strongest_matches_control_action_body_frames": control_match_count,
        "comparison": compare_replays(priority, strongest),
        "endpoints": {
            "touch_priority": priority[-1]["body_after"],
            "strongest_vote": strongest[-1]["body_after"],
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(_report(summary), encoding="utf-8")
    with (output_dir / "trajectory.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(csv_rows)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/working/male-cns-v1.0"))
    parser.add_argument("--output", type=Path, default=Path("outputs/diagnostics/decoder-competition"))
    args = parser.parse_args()
    model = VisualModel(MaleCNSPaths(args.data_dir))
    print(json.dumps(run_decoder_competition(model, output_dir=args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
