# Contributing

This repository is in a research-first restart phase. Changes should improve the
accuracy, reproducibility, or maintainability of the reverse-engineering model
before expanding translation-patching behavior.

## Development setup

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Required checks

Before opening a pull request, run:

```powershell
python -m unittest discover -s .\tests -v
python -m compileall -q .
python -m cyber_oedo --help
python -m cyber_oedo doctor
python -m build --outdir .\dist
```

The synthetic test suite must not require a game image or BIOS.

## Research discipline

Treat static observations, runtime observations, and hypotheses as different
classes of evidence. A repeated byte pattern or constant-fill tail is not a
pointer table or free space until its access path and ownership are proven.

When changing a parser or structural model:

1. add or update a synthetic test for the verified rule;
2. retain a negative or malformed case where practical;
3. update the relevant format or baseline documentation;
4. compare generated counts, offsets, and hashes on a local authenticated
   source image; and
5. record runtime evidence for claims that depend on execution.

The removed root-level `python script.py` interfaces are not a compatibility
requirement. New code should import through `cyber_oedo.*` and expose operator
workflows through the unified `cyber-oedo` command.

## Data boundary

Do not commit copyrighted or user-supplied game data, including disc images,
extracted tracks, audio, BIOS/System Card files, bulk screenshots, or complete
text dumps. Compact hashes, offsets, synthetic fixtures, and narrowly scoped
evidence are preferred. See `docs/data_policy.md`.
