# Git workflow

This project uses Git for code, experiments, documentation, and provenance. It
does not use Git as a storage system for the roughly gigabyte-sized official
connectome files.

## What belongs in Git

The repository tracks:

- Python source, tests, project configuration, and documentation.
- `data/metadata/source_manifest.json`, which records the official release,
  URLs, sizes, and hashes.
- Compact inspection reports and experiment summaries under `outputs/`.

The repository does not track:

- `data/original-data/`, the untouched downloaded release files.
- `data/working/`, the byte-identical local working copy.
- `backups/`, which is a separate local recovery copy.
- `.venv/`, caches, and bulky per-timestep traces.

Those exclusions are deliberate. A fresh checkout must restore the data files
from the authoritative source and then run the verification command; it must
not silently substitute a modified or incomplete copy.

## Everyday use

From the project root:

```powershell
git status
git switch -c experiment/name-of-experiment
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m flytest.verify
git diff
git add src tests docs README.md pyproject.toml data/metadata outputs
git diff --cached --check
git commit -m "Describe the experiment"
```

Use a branch for an experiment, keep the default `main` branch as the known
working baseline, and commit code changes together with the small report that
records what they produced. Never use `git add -f` for the raw Feather files.

## Restoring a checkout

After cloning this repository, recreate the virtual environment, download the
official release into `data/original-data/male-cns-v1.0/`, make the separate
working copy under `data/working/male-cns-v1.0/`, and run:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m flytest.verify
```

The manifest and the README are the authority for the expected release. The
local backup folder is not required for normal operation.

## Remote repository

The configured `origin` is `https://github.com/silascroe/fly-test.git`. It backs
up tracked source, documentation and compact evidence. The raw connectome,
recordings, portable runtimes, local environments and bulky outputs remain
excluded. Review the staged paths before committing and pushing a checkpoint.
