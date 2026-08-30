# Development and maintenance guide

## Purpose

The repository now has two compatible operator surfaces:

1. the historical root scripts, such as `python extract_dialogue.py ...`; and
2. the installable `cyber-oedo` command, such as
   `cyber-oedo extract-dialogue ...`.

The unified command forwards arguments to the existing scripts rather than
rewriting their command-line parsers. This keeps the modernization low risk and
provides a stable entry point for future internal package moves.

## Editable installation

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The base project has no mandatory third-party runtime dependency. Pillow remains
optional for graphics work and is provided by the `graphics` and `dev` extras.

## Daily quality gate

Run these checks before committing:

```powershell
python -m unittest discover -s .\tests -v
python -m compileall -q .
python -m cyber_oedo doctor
```

Before changing packaging or the public command surface, build both supported
distribution formats:

```powershell
python -m build --outdir .\dist
```

CI repeats these checks on Windows and Linux for the oldest supported Python
minor version and a current Python minor version. It then force-installs the
built wheel and runs `python -m cyber_oedo --help` plus `doctor` from outside
the checkout. That last step is important: an editable source tree can hide
missing package files that a real wheel install would expose.

CI runs once for each pull-request commit and for pushes to `main`. Superseded
runs on the same ref are cancelled so rapid maintenance commits do not waste
runner capacity.

## Real-disc validation gate

Synthetic tests are necessary but cannot prove title-specific image behavior.
Run the local authenticated workflow when a change touches any of the following:

- source hashes or CloneCD path handling;
- payload or raw-sector coordinate conversion;
- patch coordinates, expected bytes, or replacement bytes;
- EDC/ECC regeneration;
- dialogue record extraction semantics;
- resource boundary or relocation logic; or
- title-screen or palette insertion.

For changes that can alter generated analysis data, compare the old and new
artifacts rather than checking only whether generation succeeds. At minimum,
compare record counts, offset sets, schema headers, and stable hashes where they
are already documented.

## Compatibility policy

Root scripts are compatibility entry points. They should continue working while
implementation code moves under `cyber_oedo/` in later refactors. A future
removal requires a documented deprecation period and a migration note.

The unified command is the preferred automation surface because its command
names can remain stable even if Python module paths change internally.

## Packaging boundary

The first package release intentionally installs existing root modules as
`py-modules`. That is transitional architecture, not the desired final layout.
It gives downstream users an installable environment without duplicating or
moving verified binary logic in the same change.

See `docs/modernization_roadmap.md` for the planned internal migration.
