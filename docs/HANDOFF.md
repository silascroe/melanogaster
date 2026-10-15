# FlyTest handoff

Updated 2026-10-14. Read `AGENTS.md` first; it sets the direction and the rules.

## Where things stand

`main` has the playable creature in `fly-creature/` and the live demo page,
published from `fly-creature/site/` to https://silascroe.github.io/melanogaster/
by `.github/workflows/pages.yml`.

The creature runs a reimplementation of the Shiu et al. (2024) whole-brain LIF
model on MaleCNS v1.0. Each reaction passed a pre-declared whole-brain test
against 20 shuffled brains before it went into the game: jump, steering,
feeding, bitter refusal, antennal grooming, courtship song (visual route) and
backing up. The game runs one brain copy per sense, each on a subset chosen from
whole-brain activity, and reaches real time with the all-core Numba engine.
Details, numbers and failures: `fly-creature/docs/whole_brain_result.md`.

The 2026-10-13 work queue (brain speed, female fly, backing up) is done. The
demo page runs the obstacle copy (subset v4) in JavaScript; it matches the
Python engine bit for bit on a recorded input (`fly-creature/tests/web/`).

## Direction

Playable and inspectable, not scientific validation (set 2026-10-10). The
recorded-response validation campaign (LC10a benchmark, AOTU/DNa02 Phase B) is
paused; its frozen results stay in `fly-creature/docs/` and are not to be
resumed unless the owner asks. New reactions still need an input, readout and
an intact-versus-cut check before anything is credited to the wiring.

## Known limits

- **No integrated brain.** One continuous whole brain never settles after a
  stimulus (runaway firing, mostly Kenyon cells), and senses leak into other
  actions. Adaptation and Kenyon-cell silencing were tried with declared rules
  and both failed. The per-sense copies that reset after 500 ms quiet are the
  workaround. This is an open problem; do not promise a fix.
- Holding the forelegs on an obstacle for over a second can drift the obstacle
  copy into a state where MDN falls silent (7 of 12 seeds within 3 s).
- Song depends on the female's path: the target encoder drives LC10a only when
  she is off-centre, so a female straight ahead gets no song.
- Courtship through foreleg pheromone taste failed its test; the ppk25 channel
  could not be tested fairly because its predicted transmitters are unclear.
- Subset v3 failed its right-turn gate (−21%), so the target copy stays on v1.

## Possible next steps

None is authorized by this note; ask the owner. Ideas so far: a proboscis that
visibly reaches the sugar drop, props from Blender, and new reactions taken
from whole-brain screens like the MDN one (`tools/screen_mdn_inputs.py`).

## Checks

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest lab/tests
.\.venv\Scripts\python.exe -m flytest.verify
cd fly-creature; ..\.venv\Scripts\python.exe -m pytest tests; cd ..
git diff --check
```

The creature's web checks need Node.js and are skipped without it.

## History

The day-by-day log of the paused validation campaign (2026-09-26 to 2026-10-10)
and the old lab-arena notes were removed from this file. The last full version
is `git show 4dc1167:docs/HANDOFF.md`. The lab's own instructions are in
`lab/README.md`.
