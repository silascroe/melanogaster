"""Audit parallel checkpoints and assemble them with the frozen benchmark runner.

The runner names its cache files by recording, although recording names recur
across NoP1/P1 archives. This adapter preserves condition-specific checkpoints
and routes cache reads in the runner's declared archive order. It does not
change the runner, any predictor, any calibration, or any saved prediction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import numpy as np

import fly_creature.lc10a_response_benchmark as benchmark

FROZEN_SOURCE = "5c6498f18ec20e39f119c600f39cc1fcef21fc8d0bd782cb6338eaaeec27fad7"
KINDS = ("AOTU019", "AOTU025")


def assignments(records: list[dict]) -> dict[str, set[tuple[str, str, str]]]:
    result = {}
    for kind in KINDS:
        result[f"NoP1_{kind}"] = {
            (r["condition"], r["type"], r["recording"])
            for r in records if r["condition"] == "NoP1" and r["type"] == kind
        }
        bins: list[set] = [set(), set()]
        loads = [0, 0]
        rows = [r for r in records if r["condition"] == "P1" and r["type"] == kind]
        for row in sorted(rows, key=lambda r: r["samples"] * r["replay_trials"], reverse=True):
            target = 0 if loads[0] <= loads[1] else 1
            bins[target].add(("P1", kind, row["recording"]))
            loads[target] += int(row["samples"] * row["replay_trials"])
        for index, group in enumerate(bins):
            result[f"P1_{kind}_part{index}"] = group
    return result


def checkpoint_name(recording: str) -> str:
    return hashlib.sha256(recording.encode()).hexdigest()[:20] + ".npz"


def audit(output_dir: Path) -> tuple[dict, dict]:
    source = Path(benchmark.__file__).resolve()
    if benchmark.sha(source) != FROZEN_SOURCE:
        raise ValueError("Frozen runner source has changed")
    review = json.loads((output_dir / "preflight_review.json").read_text(encoding="utf-8"))
    if review["status"] != "pass":
        raise ValueError("Full preflight must pass")
    expected = {(r["condition"], r["type"], r["recording"]): r for r in review["records"]}
    allocated = assignments(review["records"])
    if len(expected) != 69 or set().union(*allocated.values()) != set(expected):
        raise ValueError("Worker assignments do not cover the frozen 69 units")
    locations = {}
    witness_rows = {}
    workers = []
    common_names = None
    for worker, assigned in allocated.items():
        root = output_dir / "parallel-workers" / worker
        progress = json.loads((root / "progress.json").read_text(encoding="utf-8"))
        if progress["source_sha256"] != FROZEN_SOURCE:
            raise ValueError(f"Worker source differs: {worker}")
        completed = progress["completed_recordings"]
        if len(set(completed)) != len(completed):
            raise ValueError(f"Repeated ledger identity: {worker}")
        condition, kind = next(iter(assigned))[:2]
        done = {(condition, kind, identity) for identity in completed}
        if not done <= assigned:
            raise ValueError(f"Worker completed an unassigned unit: {worker}")
        expected_pulses = sum(expected[key]["quiescent_pulses"] for key in done)
        expected_trials = sum(expected[key]["replay_trials"] for key in done)
        if progress["quiet_pulses"] != expected_pulses or progress["replay_trials"] != expected_trials:
            raise ValueError(f"Ledger counts differ from preflight: {worker}")
        for key in sorted(done):
            path = root / "recording-checkpoints" / checkpoint_name(key[2])
            if key in locations:
                raise ValueError(f"Unit appears in multiple workers: {key}")
            with np.load(path, allow_pickle=False) as saved:
                if str(saved["source_sha"]) != FROZEN_SOURCE:
                    raise ValueError(f"Checkpoint source differs: {key}")
                names = [str(value) for value in saved["names"]]
                if len(names) != 345 or len(set(names)) != 345:
                    raise ValueError(f"Predictor identity/count differs: {key}")
                if common_names is None:
                    common_names = names
                if names != common_names:
                    raise ValueError(f"Predictor order differs: {key}")
                keys = [tuple(json.loads(str(value))) for value in saved["keys"]]
                if len(keys) != expected[key]["trial_cells"] or keys != sorted(set(keys)):
                    raise ValueError(f"Trial-cell identity/count differs: {key}")
                if any(tuple(row[:3]) != key for row in keys):
                    raise ValueError(f"Checkpoint condition/type/recording differs: {key}")
                values = saved["predictions"]
                if values.shape != (len(keys), 345) or not np.isfinite(values).all():
                    raise ValueError(f"Incomplete prediction matrix: {key}")
                trials = json.loads(str(saved["trials_json"]))
                if any((r["condition"], r["type"], r["recording"]) != key for r in trials):
                    raise ValueError(f"Replay metadata identity differs: {key}")
                if len({r["trial"] for r in trials}) != expected[key]["replay_trials"]:
                    raise ValueError(f"Replay trial count differs: {key}")
                for row in trials:
                    if "canonical_activity_sha256" in row:
                        witness_rows[key] = row
                locations[key] = path
        workers.append({"worker": worker, "completed": len(done), "assigned": len(assigned)})
    report = {"status": "complete" if set(locations) == set(expected) else "partial",
              "completed_units": len(locations), "expected_units": 69,
              "source_sha256": FROZEN_SOURCE, "predictors": 345, "workers": workers,
              "cross_condition_filename_overlaps": len(expected) - len({key[2] for key in expected}),
              "checkpoint_keys_counts_and_finite_predictions": "pass"}
    (output_dir / "assembly_audit.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report, {"locations": locations, "witness_rows": witness_rows}


def assemble(output_dir: Path, data_dir: Path, audited: dict) -> dict:
    locations = audited["locations"]
    sequence = []
    for condition, archives in (("NoP1", benchmark.ARCHIVES), ("P1", benchmark.P1_ARCHIVES)):
        for kind, (filename, _) in archives.items():
            with zipfile.ZipFile(data_dir / filename) as archive:
                for member in sorted(n for n in archive.namelist() if n.endswith("_int.mat")):
                    identity = kind + "/" + Path(member).stem.removesuffix("_int")
                    if identity != benchmark.DUPLICATE:
                        sequence.append((condition, kind, identity))
    if len(sequence) != 69 or set(sequence) != set(locations):
        raise ValueError("Native archive traversal differs from audited checkpoint coverage")
    cache = (output_dir / "recording-checkpoints").resolve()
    witnesses = output_dir / "sensor-witnesses"
    cache.mkdir(parents=True, exist_ok=True)
    witnesses.mkdir(parents=True, exist_ok=True)
    routed = {}
    manifest = []
    groups = set()
    for key in sequence:
        original = locations[key]
        destination = cache / "by-condition" / key[0] / original.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)
        routed[key] = destination
        # The unchanged runner checks this legacy filename before np.load.
        alias = cache / original.name
        if not alias.exists():
            shutil.copy2(original, alias)
        manifest.append({"condition": key[0], "type": key[1], "recording": key[2],
                         "checkpoint": str(destination.relative_to(output_dir)),
                         "sha256": benchmark.sha(destination)})
        group = key[:2]
        if group not in groups and key in audited["witness_rows"]:
            witness = original.parent.parent / "sensor-witnesses" / ("_".join(group) + ".npz")
            with np.load(original, allow_pickle=False) as cp, np.load(witness, allow_pickle=False) as saved:
                if str(saved["source_sha"]) != FROZEN_SOURCE or str(saved["member_sha"]) != str(cp["member_sha"]):
                    raise ValueError(f"Witness provenance differs: {key}")
            shutil.copy2(witness, witnesses / witness.name)
            groups.add(group)
    if len(groups) != 4:
        raise ValueError("Four full native sensory witnesses are required")
    original_load, original_save = np.load, np.savez_compressed
    consumed = []

    def routed_load(file, *args, **kwargs):
        path = Path(file).resolve() if isinstance(file, (str, Path)) else None
        if path is not None and path.parent == cache and path.suffix == ".npz":
            if len(consumed) >= len(sequence):
                raise ValueError("Unexpected extra checkpoint read")
            key = sequence[len(consumed)]
            if path.name != checkpoint_name(key[2]):
                raise ValueError("Checkpoint read order differs from native archive order")
            consumed.append(key)
            return original_load(routed[key], *args, **kwargs)
        return original_load(file, *args, **kwargs)

    def guarded_save(file, *args, **kwargs):
        path = Path(file).resolve() if isinstance(file, (str, Path)) else None
        if path is not None and path.parent == cache:
            raise ValueError("Frozen runner rejected a routed checkpoint; assembly stopped before replay")
        return original_save(file, *args, **kwargs)

    np.load, np.savez_compressed = routed_load, guarded_save
    original_dumps = json.dumps

    def json_default(value):
        # The frozen runner's score gates can contain np.bool_. Keep the runner
        # byte-identical and teach only this assembly invocation to serialize
        # NumPy scalar wrappers as their ordinary Python values.
        if isinstance(value, np.generic):
            return value.item()
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    def dumps_with_numpy_scalars(obj, *args, **kwargs):
        kwargs.setdefault("default", json_default)
        return original_dumps(obj, *args, **kwargs)

    json.dumps = dumps_with_numpy_scalars
    try:
        result = benchmark.run(data_dir, output_dir, skip_review=True)
    finally:
        np.load, np.savez_compressed = original_load, original_save
        json.dumps = original_dumps
    if consumed != sequence or not all(row["checkpoint_reused"] for row in result["recordings"]):
        raise ValueError("Full assembly did not reuse exactly the 69 audited units")
    if benchmark.sha(Path(benchmark.__file__)) != FROZEN_SOURCE:
        raise ValueError("Frozen runner changed during assembly")
    (output_dir / "assembly_manifest.json").write_text(json.dumps({
        "status": "pass", "adapter_sha256": benchmark.sha(Path(__file__)),
        "runner_sha256": FROZEN_SOURCE, "routed_units": len(consumed),
        "all_runner_cache_validations_passed": True, "checkpoints": manifest,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=benchmark.OUTPUT_DIR)
    parser.add_argument("--data-dir", type=Path, default=benchmark.ROOT / "outputs/research/aotu-recordings")
    parser.add_argument("--run", action="store_true", help="Require complete coverage, then assemble and score")
    args = parser.parse_args()
    output_dir, data_dir = args.output_dir.resolve(), args.data_dir.resolve()
    report, audited = audit(output_dir)
    print(json.dumps(report, indent=2), flush=True)
    if args.run:
        if report["status"] != "complete":
            raise ValueError("Wait for all 69 condition/type/recording units before scoring")
        result = assemble(output_dir, data_dir, audited)
        print(json.dumps({"status": result["status"], "counts": result["counts"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
