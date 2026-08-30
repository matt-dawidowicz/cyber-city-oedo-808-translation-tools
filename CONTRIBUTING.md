# Contributing

This repository mixes reverse-engineering research with tooling that can patch
an authenticated disc image. Changes should therefore optimize for auditability,
reproducibility, and failure safety rather than cleverness.

## Development setup

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On macOS or Linux, activate the environment with
`source .venv/bin/activate` instead.

The editable install adds the unified `cyber-oedo` command while preserving all
existing `python script.py ...` entry points.

## Required checks

Before opening a pull request, run:

```powershell
python -m unittest discover -s .\tests -v
python -m compileall -q .
python -m cyber_oedo doctor
python -m build --wheel --outdir .\dist
```

The automated suite is intentionally synthetic and must not require the game
image. Changes that depend on authentic disc data need the additional local
validation described in `docs/development.md`.

## Change discipline

Keep infrastructure refactors separate from binary-behavior changes whenever
possible. A package move should not also change parser rules; a parser change
should not also rewrite patch coordinates.

When behavior changes:

1. Add a synthetic test that demonstrates the new rule.
2. Preserve at least one negative or malformed case.
3. Update the relevant format or architecture documentation.
4. Regenerate local derived artifacts when the stage output can change.
5. Compare counts, offsets, and hashes before accepting the change.
6. Record runtime evidence for any claim that depends on game execution.

## Data boundary

Do not commit copyrighted or user-supplied game data. In particular, do not add
CloneCD images, extracted tracks, audio, BIOS files, screenshots containing
substantial game assets, or complete generated text inventories. See
`docs/data_policy.md` for the repository's detailed boundary.
