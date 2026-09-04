# Cyber City Oedo 808 translation research toolkit

This repository contains reverse-engineering and text-analysis tools for the
Japanese PC Engine CD release of *Cyber City Oedo 808: Kemono no Alignment*.

## Restart status

The project has been reset to a **research baseline**. The previous playable
translation prototype, stock-renderer patch profile, title-screen replacement,
wide-text experiments, Stage 1 runtime experiment, and their compatibility
wrappers have been removed from the active tree. They remain available in Git
history if a specific finding needs to be recovered.

There is currently **no supported translation patch builder** in this branch.
That is deliberate. The next implementation should be based on verified runtime
behavior rather than carrying forward prototype assumptions.

## Preserved findings

The retained tools and evidence establish the following baseline for the
analyzed disc:

- Track 2 contains 41,199 Mode 1 data sectors.
- The extracted 2048-byte payload is 84,375,552 bytes.
- Its SHA-256 is
  `0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223`.
- Main dialogue is stored as null-terminated Shift-JIS records.
- Candidate dialogue records begin with bytes `27 28`.
- Low ASCII-range bytes inside those records must be treated as controls, not
  as safe ASCII text.
- The boot program uses the System Card BIOS `EX_GETFNT` service at `$E060`.
- Named resource boundaries and repeated mission-bank anchors are useful
  structural evidence, but constant-fill tails are not automatically safe
  relocation space.

See [research baseline](docs/research_baseline.md) for the evidence retained
across the restart.

## Repository layout

- `cyber_oedo/disc/` — CloneCD/Mode 1 layout and extraction primitives.
- `cyber_oedo/analysis/` — structural scans and HuC6280 diagnostics.
- `cyber_oedo/text/` — dialogue, auxiliary-text, and translation-inventory
  extraction/validation.
- `cyber_oedo/graphics/` — generic PC Engine 4bpp tile diagnostics.
- `cyber_oedo/contracts/` — versioned text/automation data schemas.
- `docs/evidence/` — compact evidence artifacts worth preserving across
  implementation resets.
- `tests/` — synthetic tests that do not require copyrighted game data.

There are no top-level compatibility scripts. The installable package and
`cyber-oedo` command are the canonical interface.

## Setup

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

For graphics commands without the development tools, install `.[graphics]`.

## Core workflow

Use the unified command surface:

```powershell
python -m cyber_oedo --help
python -m cyber_oedo doctor

python -m cyber_oedo extract-track2-mode1 `
  "C:\path\to\Cyber City Oedo 808 - Kemono no Alignment (Japan).img" `
  .\track02_mode1_2048.bin

python -m cyber_oedo scan-track `
  .\track02_mode1_2048.bin `
  --output-dir .\scan

python -m cyber_oedo scan-likely-sjis `
  .\track02_mode1_2048.bin `
  .\scan\likely_shift_jis.tsv

python -m cyber_oedo extract-dialogue `
  .\track02_mode1_2048.bin `
  .\dialogue.tsv

python -m cyber_oedo extract-auxiliary-text `
  .\scan\likely_shift_jis.tsv `
  .\dialogue.tsv `
  .\auxiliary_text.tsv

python -m cyber_oedo build-translation-inventory `
  .\dialogue.tsv `
  .\auxiliary_text.tsv `
  .\translation_inventory.tsv

python -m cyber_oedo validate-translation-inventory `
  .\translation_inventory.tsv
```

The generated payloads, scans, inventories, and renders are local artifacts and
must not be committed.

## Current research boundary

The repository intentionally does **not** claim that every extracted string is
player-visible, that every control byte is fully understood, or that any
candidate padding region is safe for relocation. Runtime entry paths, pointer
ownership, resource loading, and renderer behavior must be proven before a new
insertion engine is designed.

Useful references:

- [Disc layout](docs/disc_layout.md)
- [Text format](docs/text_format.md)
- [Research baseline](docs/research_baseline.md)
- [Architecture](docs/architecture.md)
- [External contracts](docs/contracts.md)
- [Data and rights policy](docs/data_policy.md)

## Data boundary

This repository does not contain the game, BIOS files, extracted tracks, audio,
full text dumps, or modified disc images. Supply a legally obtained source image
locally. See [data_policy.md](docs/data_policy.md) before adding evidence or
fixtures.

## License

The original code and documentation in this repository are licensed under the
MIT License. Third-party game content remains the property of its respective
rights holders.
