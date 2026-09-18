# FlyTest project guide

FlyTest is a local-first exploration of the official FlyEM Male CNS
connectome. It is an educational, inspectable research toy—not a validated
biophysical brain model, a behavioral simulator, or a FlyDoom replacement.

## Protect the data

- Never edit files under `data/original-data/`. They are the untouched official
  release and are evidence for provenance checks.
- Treat `data/working/` as a separate working copy. Do not silently normalize,
  overwrite, or replace it with a different release.
- Keep `backups/` separate from both Git history and the working data.
- Do not commit Feather files, backup copies, `.venv/`, caches, or bulky
  timestep traces. The source manifest and compact derived reports may be
  committed.
- Run `python -m flytest.verify` after operations that might affect the data.
  Original and working copies must remain byte-identical.

## Keep the code boundaries clear

- `src/flytest/data.py` owns read-only release loading and streaming access.
- `src/flytest/analysis.py` owns selection, annotation joins, signs, and graph
  construction.
- `src/flytest/simulation.py` owns the small configurable LIF reference model.
- Diagnostic modules own experiments and artifacts; do not hide experiment-
  specific behavior in production defaults.
- Preserve the existing one-step delay, native-sign convention, and default LIF
  behavior unless an experiment explicitly changes and records them.
- Keep raw connectome facts distinct from modelling assumptions. A predicted
  transmitter sign or toy coupling value is not the same thing as a measured
  biological parameter.

## Work experimentally

- Prefer a small, named, reproducible circuit question over whole-brain work.
- Keep topology, timing, thresholds, and other parameters fixed when testing a
  single causal factor.
- Do not begin behavioral, muscle, game, or FlyDoom integration without an
  explicit input/output definition and a circuit-level diagnostic first.
- Write inspectable CSV/JSON/Markdown artifacts and explain surprising results
  in plain language.

## Validate changes

From the project root, use the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m flytest.verify
git diff --check
git status
```

When a diagnostic changes, run it against the real working copy and inspect
its output before committing. Tests should cover both focused behavior and
regression of the existing baseline.

## Use Git carefully

- Keep `main` as the known working baseline.
- Use a descriptive `experiment/<name>` branch for new analysis or simulator
  behavior.
- Commit code, tests, documentation, manifests, and compact reports together.
- Never use `git add -f` to include raw connectome files or local backups.
- Review the staged file list before committing. A clean commit must not hide a
  data mutation or an accidental large artifact.

## Explain decisions

Document non-obvious choices in `docs/decisions.md`. In user-facing responses,
separate what came from the official dataset, what the simulator assumes, and
what the experiment actually demonstrated. Keep explanations understandable
to someone learning the subject rather than assuming neuroscience or software
engineering expertise.
