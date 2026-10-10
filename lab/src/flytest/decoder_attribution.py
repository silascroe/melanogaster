"""Audit the arena's action decoder against recorded stage-1,024 vote vectors.

The shadow decoder never drives the body. Both readouts are scored on the same
recorded neural steps, avoiding a false claim of matched closed-loop futures.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Protocol

from .arena_circuit import ACTION_ORDER
from .arena_simulation import ArenaRunConfig
from .data import MaleCNSPaths
from .threat_crossing import ThreatCrossingConfig
from .visual_simulation import VisualModel


STAGE = 1024
ESCAPE_ACTIONS = ("escape_left", "escape_right")
VISUAL_ACTIONS = ("turn_left", "turn_right", "forward")
VOTE_COLUMNS = (
    "condition", "time_ms", "touch_stimulus_active", "actual_action",
    "actual_source", *ACTION_ORDER, "priority_vote_action", "shadow_action",
    "competitive", "policy_sensitive", "realized_priority_override",
)


class ArenaRunner(Protocol):
    def run_arena(self, config: ArenaRunConfig) -> dict[str, Any]: ...


def _winner(votes: Mapping[str, float], actions: tuple[str, ...]) -> str | None:
    """Use the production vote ranking, but without its memory gates."""
    ranked = sorted(actions, key=lambda action: (-float(votes.get(action, 0)), ACTION_ORDER.index(action)))
    return ranked[0] if ranked and float(votes.get(ranked[0], 0)) > 0 else None


def analyze_vote_trace(
    frames: list[dict[str, Any]], *, condition: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Compare action policies on identical recorded votes, not alternate trajectories."""
    rows: list[dict[str, Any]] = []
    actual_counts: Counter[str] = Counter()
    shadow_counts: Counter[str] = Counter()
    for frame in frames:
        cause = frame["neural_cause"]
        votes = cause["output_votes"]
        escape = _winner(votes, ESCAPE_ACTIONS)
        visual = _winner(votes, VISUAL_ACTIONS)
        priority = escape or visual or "stop"
        shadow = _winner(votes, ACTION_ORDER) or "stop"
        competitive = escape is not None and visual is not None
        sensitive = competitive and priority != shadow
        actual = str(frame["action"])
        realized = sensitive and actual == priority and str(frame["action_source"]) == "touch"
        actual_counts[actual] += 1
        shadow_counts[shadow] += 1
        rows.append({
            "condition": condition,
            "time_ms": frame["time_ms"],
            "touch_stimulus_active": bool(frame.get("touch_stimulus_active", False)),
            "actual_action": actual,
            "actual_source": str(frame["action_source"]),
            **{action: float(votes.get(action, 0)) for action in ACTION_ORDER},
            "priority_vote_action": priority,
            "shadow_action": shadow,
            "competitive": competitive,
            "policy_sensitive": sensitive,
            "realized_priority_override": realized,
        })

    competitive_count = sum(row["competitive"] for row in rows)
    sensitive_count = sum(row["policy_sensitive"] for row in rows)
    realized_count = sum(row["realized_priority_override"] for row in rows)
    if realized_count:
        attribution = "observed_priority_override"
    elif sensitive_count:
        attribution = "latent_priority_sensitivity"
    elif competitive_count:
        attribution = "no_priority_effect_on_observed_votes"
    else:
        attribution = "untested_no_competition"
    return {
        "frames": len(rows),
        "competitive_frames": competitive_count,
        "policy_sensitive_vote_frames": sensitive_count,
        "realized_priority_override_frames": realized_count,
        "actual_action_counts": dict(sorted(actual_counts.items())),
        "shadow_action_counts": dict(sorted(shadow_counts.items())),
        "attribution": attribution,
    }, rows


def _report(summary: Mapping[str, Any], rows: list[dict[str, Any]]) -> str:
    control = summary["conditions"]["control"]
    crossing = summary["conditions"]["crossing"]
    salient = [
        row for row in rows
        if row["condition"] == "crossing"
        and (row["competitive"] or row["actual_action"] in ESCAPE_ACTIONS)
    ]
    return "\n".join([
        "# Decoder attribution at 1,024 nodes",
        "",
        "The existing touch-priority decoder controlled both replays. A shadow",
        "strongest-population-wins decoder scored the **same recorded descending votes**",
        "frame by frame; it did not control the body or change future neural inputs.",
        "",
        "| Condition | Frames | Both populations voted | Vote-policy differences | Realized priority overrides | Actual escapes | Shadow escape votes |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        *(
            f"| {name} | {result['frames']} | {result['competitive_frames']} | "
            f"{result['policy_sensitive_vote_frames']} | {result['realized_priority_override_frames']} | "
            f"{sum(result['actual_action_counts'].get(a, 0) for a in ESCAPE_ACTIONS)} | "
            f"{sum(result['shadow_action_counts'].get(a, 0) for a in ESCAPE_ACTIONS)} |"
            for name, result in (("control", control), ("crossing", crossing))
        ),
        "",
        f"Crossing attribution: `{crossing['attribution']}`.",
        "",
        "## Crossing frames that matter",
        "",
        "| Time | Touch vote | Visual vote | Live action/source | Priority vote | Shadow vote |",
        "| ---: | ---: | ---: | --- | --- | --- |",
        *(
            f"| {float(row['time_ms']):.1f} ms | "
            f"{max(row[action] for action in ESCAPE_ACTIONS):g} | "
            f"{max(row[action] for action in VISUAL_ACTIONS):g} | "
            f"{row['actual_action']} / {row['actual_source']} | "
            f"{row['priority_vote_action']} | {row['shadow_action']} |"
            for row in salient
        ),
        *(("| No competitive or live-escape frames | - | - | - | - | - |",) if not salient else ()),
        "",
        "A realized override means both touch and vision voted, the priority",
        "policy selected a touch escape despite the shadow winner being visual,",
        "and the live action was that touch escape. This isolates the decoder's",
        "contribution on that frame; it does not show an alternate flight path.",
        "If both populations never voted together, arbitration was not tested.",
        "Vote differences without a realized override are only latent sensitivity",
        "because cooldown and recovery may gate the live decoder.",
        "Shadow action totals are vote-only tallies, not simulated alternate body",
        "actions; ordinary differences may reflect live cooldown or recovery.",
        "They are not alternate closed-loop outcomes.",
        "",
        "Connectome facts: node/edge wiring and native signs come from the local",
        "FlyEM Male CNS release. Assumptions: sensory currents, touch/visual",
        "action labels, vote aggregation, priority and shadow decoders, and body.",
        "The CSV records every frame's raw action votes and both readouts.",
        "",
    ])


def run_decoder_attribution(
    model: ArenaRunner,
    *,
    output_dir: Path,
    scenario: ThreatCrossingConfig | None = None,
) -> dict[str, Any]:
    scenario = scenario or ThreatCrossingConfig()
    scenario.validate()
    conditions: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    for name, include_threat in (("control", False), ("crossing", True)):
        config = scenario.to_arena_config(STAGE, include_threat=include_threat)
        payload = model.run_arena(config)
        network = payload["network"]
        if int(network.get("stage", -1)) != STAGE or int(network.get("actual_node_count", -1)) != STAGE:
            raise ValueError(f"{name} did not return a {STAGE}-node stage")
        if int(network.get("edge_count", 0)) <= 0:
            raise ValueError(f"{name} graph has no edges")
        result, condition_rows = analyze_vote_trace(payload["trajectory"], condition=name)
        if not condition_rows:
            raise ValueError(f"{name} trajectory is empty")
        conditions[name] = result
        rows.extend(condition_rows)

    summary = {
        "experiment": "stage-1024 decoder attribution",
        "stage": STAGE,
        "duration_ms": scenario.duration_ms,
        "conditions": conditions,
        "interpretation_boundary": "same recorded neural votes; not alternate closed-loop behavior",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(_report(summary, rows), encoding="utf-8")
    with (output_dir / "votes.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=VOTE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/working/male-cns-v1.0"))
    parser.add_argument("--output", type=Path, default=Path("outputs/diagnostics/decoder-attribution"))
    args = parser.parse_args()
    model = VisualModel(MaleCNSPaths(args.data_dir))
    print(json.dumps(run_decoder_attribution(model, output_dir=args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
