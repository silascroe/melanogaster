# FlyTest project guide

FlyTest is a local-first workspace around the official FlyEM Male CNS
connectome. Its existing Python diagnostics and `arena3d/` are an educational,
inspectable research lab—not a validated biophysical brain or behavior model.
`fly-creature/` is a separate, portable interactive-creature project in the same workspace.
Its intended experience does not turn the old arena's chosen circuit or action
rules into established fly biology.

## Keep the two projects distinct

- Preserve `src/flytest/` diagnostics, `arena3d/`, and their compact results as
  the experimental record. Do not refactor the old arena merely to make the new
  project fit its assumptions.
- Develop the new creature entirely under `fly-creature/`, including its own
  source, Godot project, assets, dependency manifest, and compact circuit data
  when those are needed. A copy of that directory should eventually run without
  files or imports from the rest of FlyTest. Adapt useful loader, selection, or
  neural-simulator code into the new project rather than depending on the lab
  package at runtime; do not copy the entire lab.
- Select the new project's circuit from its stated sensory inputs and neural
  outputs. The old 1,024-neuron touch/vision selection is an experimental stage,
  not a default circuit or a known complete behavior circuit.
- Keep a playable demonstration separate from scientific claims. A visible
  reaction can depend on engineered sensors, motor decoding, body physics, or
  safety rules; trace those contributions before crediting the connectome.

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

The creature now has two world ownership boundaries: its original Godot
scene owns body state, while `fly-creature/src/fly_creature/playground.py`
owns the simultaneous comparison world. Read `fly-creature/docs/ARCHITECTURE.md`
and `docs/playground.md` inside that project before changing either bridge.

- `src/flytest/data.py` owns read-only release loading and streaming access.
- `src/flytest/analysis.py` owns selection, annotation joins, signs, and graph
  construction.
- `src/flytest/simulation.py` owns the small configurable LIF reference model.
- Diagnostic modules own experiments and artifacts; do not hide experiment-
  specific behavior in production defaults.
- New creature world, body, and interface code belongs to the new project,
  rather than being folded into the legacy arena's defaults.
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
- For `fly-creature/`, define what the world senses, which selected neurons
  receive that signal, which neural activity is read, and how the body responds
  before implementing a new reaction. Compare intact wiring with a suitable
  control before claiming that the connectome caused a useful behavior.
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

Document lab choices in `docs/decisions.md` and new-project choices under
`fly-creature/`. In user-facing responses, separate what came from the official
dataset, what the simulator assumes, and what the experiment actually
demonstrated. Keep explanations understandable
to someone learning the subject rather than assuming neuroscience or software
engineering expertise.
