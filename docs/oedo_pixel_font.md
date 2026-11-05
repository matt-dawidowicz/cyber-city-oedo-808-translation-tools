# Oedo Pixel — source-authored 8x16 English font

**Status: opt-in typography prototype, not live-certified proportional text.**

## Script-based scope

The previously audited September 24 translation had **91 distinct visible
characters**. Its only non-ASCII symbols were **“ ” ‘ ’ — – … ¥ ■**.
The later Definitive Edition TSV is unavailable for an independent recount.
The **95-glyph working set** is a deliberate pilot repertoire, *not* an exact
count of that unavailable Definitive script.

The current native hook can address **95 font storage codes** ($20–$7E).
The core comprises Latin A–Z/a–z, digits 0–9, ordinary punctuation
and the nine documented non-ASCII marks. Other printable ASCII
characters still have authored bitmap shapes and can replace unused
symbols in an audited build. We have found no reason to add all
accented alphabets, superscripts, mathematical operators, or Greek.

CD space is plentiful; native ROM storage codes, RAM/VRAM capacity
and memory-bank lifetime still impose real technical limits.

## Implemented

- Editable, original seven-row source patterns in
  `cyber_oedo/text/oedo_pixel_font.py`, expanded to 8x16 1-bpp cells
- **Consistent baseline:** top row 3; body through row 11;
  descenders through row 13, avoiding individually centered letters
- Bitmap SHA-256 includes the actual pixels and ordered repertoire,
  with no TTF/OTF file to install or redistribute
- Existing VWF tools measure the real bitmaps: narrow `i`/`l`
  advance 4px, wide `M`/`W` 8px, space 4px, tracking 1px
- Strict glyph audit: the chosen English TSV/CSV column is scanned
  for Unicode codepoint, name, frequency and 95-slot availability;
  unsupported characters are **not silently replaced**
- `--authored-pixel-font` builds a separate authenticated M0-B
  experimental disc with these exact glyphs, retaining the original
  builder behavior unless explicitly enabled

## Generate previews

```sh
python tools/preview_oedo_pixel_font.py /tmp/oedo-font-previews
```

The generated specimen and fixed/VWF panels are **synthetic previews**,
not frames captured from Mesen. The proposed drop shadow is also
**mockup-only**, not an implemented in-game drawing feature.

## Audit a translated script when the Definitive TSV is available

```sh
python -m cyber_oedo.text.oedo_pixel_font definitive.tsv \
  --column 'Definitive Localization' --output glyph_coverage.json
```

The command fails if there are missing glyphs, ambiguous/missing columns,
an empty script, or a 95-slot overflow. No Definitive TSV is provided or
reconstructed by these changes.

## Test a separate original-disc-derived English build

```sh
python -m cyber_oedo.runtime.mission0_pool_pilot \
  /path/to/original.ccd /path/to/new-output \
  --authored-pixel-font --diagnostic-intro-redirect
```

The output manifest marks `font_style=authored_pixel`, exports measured
`proportional_metrics`, and explicitly sets
`proportional_runtime_certified=false`,
`emulator_certified=false`, and `release_enabled=false`.

**Important:** the current live native pilot uses 8-pixel *fixed*
English storage cells. Its proportionally spaced mockups use the
existing build-time VWF system but are **not yet wired into live
Mesen gameplay**. Real VWF tile allocation, controls, font contrast,
scene transitions and the natural bartender encounter still require
separate emulator validation.

No proprietary game data, BIOS, or font binaries are committed.
