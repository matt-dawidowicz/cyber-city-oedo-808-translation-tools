"""Original, source-authored Oedo English 8x16 pixel glyphs and coverage audit.

Source patterns are editable, 1-bpp pixel art; no third-party font
binary is included. A shared baseline avoids per-letter vertical drift.
The audited 2026-09-24 translation had 91 glyphs; the later Definitive
TSV is unavailable, so the 95-slot pilot set is NOT a fresh corpus census.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from cyber_oedo.text.font_atlas import RasterConfig, RasterizedAtlas
from cyber_oedo.text.packed_english import DEFAULT_DISPLAY_CHARACTERS
from cyber_oedo.text.vwf_text import VwfFont, derive_vwf_font

PILOT_CHARACTERS = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789"
    " !\"#$%&'()*+,-./:;=?@[]_"
    "“”‘’—–…¥■"
)
NATIVE_GLYPH_LIMIT = 95
CAP_TOP = 3
BASELINE = 11
DESCEND_BOTTOM = 13
_VERTICAL_ROW_MAP = (0, 0, 1, 2, 3, 4, 5, 6, 6)

# Unicode scalar as hex : seven /-delimited scanlines. X is foreground.
# All printable ASCII and the nine documented translation-only symbols
# have editable source art; the default pilot selects only 95 of them.
_PATTERN_DATA = """
0020:.../.../.../.../.../.../...
0021:XX/XX/XX/XX/XX/../XX
0022:X.X/X.X/X.X/.../.../.../...
0023:.X.X./.X.X./XXXXX/.X.X./XXXXX/.X.X./.X.X.
0024:.XXX./X.X../X.X../.XXX./..X.X/..X.X/.XXX.
0025:XX..X/XX.X./..X../.X.../X..../X.XX./X..XX
0026:.XX../X..X./X..X./.XX../X.X.X/X..X./.XX.X
0027:XX/XX/.X/../../../..
0028:..XX/.X../X.../X.../X.../.X../..XX
0029:XX../..X./...X/...X/...X/..X./XX..
002A:...../X.X.X/.XXX./XXXXX/.XXX./X.X.X/.....
002B:...../..X../..X../XXXXX/..X../..X../.....
002C:../../../../../XX/XX
002D:...../...../...../XXXX./...../...../.....
002E:../../../../../XX/XX
002F:....X/...X./..X../.X.../X..../...../.....
0030:.XXX./XX..X/X.X.X/X.X.X/X..XX/X...X/.XXX.
0031:.X./XX./.X./.X./.X./.X./XXX
0032:.XXX./X...X/....X/..XX./.X.../X..../XXXXX
0033:XXXX./....X/....X/.XXX./....X/....X/XXXX.
0034:...X./..XX./.X.X./X..X./XXXXX/...X./...X.
0035:XXXXX/X..../X..../XXXX./....X/....X/XXXX.
0036:.XXXX/X..../X..../XXXX./X...X/X...X/.XXX.
0037:XXXXX/....X/...X./..X../.X.../.X.../.X...
0038:.XXX./X...X/X...X/.XXX./X...X/X...X/.XXX.
0039:.XXX./X...X/X...X/.XXXX/....X/....X/XXXX.
003A:../XX/XX/../XX/XX/..
003B:../XX/XX/../XX/XX/X.
003C:...X./..X../.X.../X..../.X.../..X../...X.
003D:...../XXXXX/...../XXXXX/...../...../.....
003E:X..../.X.../..X../...X./..X../.X.../X....
003F:.XXX./X...X/....X/..XX./..X../...../..X..
0040:.XXXXX./X.....X/X.XXX.X/X.X.X.X/X.XXXX./X....../.XXXXX.
0041:.XXX./X...X/X...X/XXXXX/X...X/X...X/X...X
0042:XXXX./X...X/X...X/XXXX./X...X/X...X/XXXX.
0043:.XXXX/X..../X..../X..../X..../X..../.XXXX
0044:XXXX./X...X/X...X/X...X/X...X/X...X/XXXX.
0045:XXXXX/X..../X..../XXXX./X..../X..../XXXXX
0046:XXXXX/X..../X..../XXXX./X..../X..../X....
0047:.XXXX/X..../X..../X.XXX/X...X/X...X/.XXXX
0048:X...X/X...X/X...X/XXXXX/X...X/X...X/X...X
0049:XXX/.X./.X./.X./.X./.X./XXX
004A:..XXX/...X./...X./...X./...X./X..X./.XX..
004B:X...X/X..X./X.X../XX.../X.X../X..X./X...X
004C:X..../X..../X..../X..../X..../X..../XXXXX
004D:X.....X/XX...XX/X.X.X.X/X..X..X/X.....X/X.....X/X.....X
004E:X...X/XX..X/X.X.X/X..XX/X...X/X...X/X...X
004F:.XXX./X...X/X...X/X...X/X...X/X...X/.XXX.
0050:XXXX./X...X/X...X/XXXX./X..../X..../X....
0051:.XXX./X...X/X...X/X...X/X.X.X/X..X./.XX.X
0052:XXXX./X...X/X...X/XXXX./X.X../X..X./X...X
0053:.XXXX/X..../X..../.XXX./....X/....X/XXXX.
0054:XXXXX/..X../..X../..X../..X../..X../..X..
0055:X...X/X...X/X...X/X...X/X...X/X...X/.XXX.
0056:X...X/X...X/X...X/X...X/X...X/.X.X./..X..
0057:X.....X/X.....X/X.....X/X..X..X/X.X.X.X/XX...XX/X.....X
0058:X...X/X...X/.X.X./..X../.X.X./X...X/X...X
0059:X...X/X...X/.X.X./..X../..X../..X../..X..
005A:XXXXX/....X/...X./..X../.X.../X..../XXXXX
005B:XXX/X../X../X../X../X../XXX
005C:X..../.X.../..X../...X./....X/...../.....
005D:XXX/..X/..X/..X/..X/..X/XXX
005E:..X../.X.X./X...X/...../...../...../.....
005F:...../...../...../...../...../...../XXXXX
0060:XX/XX/.X/../../../..
0061:...../...../.XXX./....X/.XXXX/X...X/.XXXX
0062:X..../X..../XXXX./X...X/X...X/X...X/XXXX.
0063:...../...../.XXXX/X..../X..../X..../.XXXX
0064:....X/....X/.XXXX/X...X/X...X/X...X/.XXXX
0065:...../...../.XXX./X...X/XXXXX/X..../.XXXX
0066:..XX./.X..X/.X.../XXXX./.X.../.X.../.X...
0067:...../...../.XXXX/X...X/X...X/.XXXX/....X
0068:X..../X..../XXXX./X...X/X...X/X...X/X...X
0069:.X./.../XX./.X./.X./.X./XXX
006A:..X/.../.XX/..X/..X/..X/..X
006B:X..../X..../X..X./X.X../XX.../X.X../X..X.
006C:XX./.X./.X./.X./.X./.X./.XX
006D:......./......./XXX.XX./X..X..X/X..X..X/X..X..X/X..X..X
006E:...../...../XXXX./X...X/X...X/X...X/X...X
006F:...../...../.XXX./X...X/X...X/X...X/.XXX.
0070:...../...../XXXX./X...X/X...X/XXXX./X....
0071:...../...../.XXXX/X...X/X...X/.XXXX/....X
0072:...../...../X.XXX/XX.../X..../X..../X....
0073:...../...../.XXXX/X..../.XXX./....X/XXXX.
0074:.X.../.X.../XXXX./.X.../.X.../.X..X/..XX.
0075:...../...../X...X/X...X/X...X/X...X/.XXXX
0076:...../...../X...X/X...X/X...X/.X.X./..X..
0077:......./......./X.....X/X..X..X/X..X..X/X.X.X.X/.X...X.
0078:...../...../X...X/.X.X./..X../.X.X./X...X
0079:...../...../X...X/X...X/X...X/.XXXX/....X
007A:...../...../XXXXX/...X./..X../.X.../XXXXX
007B:..XX/.X../.X../X.../.X../.X../..XX
007C:X/X/X/X/X/X/X
007D:XX../..X./..X./...X/..X./..X./XX..
007E:...../...../.XX.X/X.XX./...../...../.....
201C:X.X/X.X/X.X/.../.../.../...
201D:X.X/X.X/.X./.../.../.../...
2018:XX/XX/X./../../../..
2019:XX/XX/.X/../../../..
2014:......./......./......./XXXXXXX/......./......./.......
2013:...../...../...../XXXXX/...../...../.....
2026:......./......./......./......./......./X.X.X.X/X.X.X.X
00A5:X...X/.X.X./..X../XXXXX/..X../XXXXX/..X..
25A0:XXXXX/XXXXX/XXXXX/XXXXX/XXXXX/XXXXX/XXXXX
"""

_BITMAP_ROWS = {
    chr(int(key, 16)): value
    for key, value in (line.split(":", 1) for line in _PATTERN_DATA.splitlines() if line)
}
_DESCENDERS = {
    "g": ("...XX", ".XXX."),
    "j": ("..X", "XX."),
    "p": ("X....", "X...."),
    "q": ("....X", "....X"),
    "y": ("...XX", ".XXX."),
    ",": ("X.", ".."),
}


class OedoPixelFontError(ValueError):
    """An unsupported character, malformed glyph, or slot overflow."""


def glyph_bitmap(character: str) -> bytes:
    """Pack nine aligned body rows and up to two descender rows as 8x16 1-bpp."""
    if len(character) != 1:
        raise OedoPixelFontError("glyph_bitmap expects one Unicode scalar")
    if character not in _BITMAP_ROWS:
        raise OedoPixelFontError(
            f"no authored bitmap for {character!r} U+{ord(character):04X}"
        )
    rows = _BITMAP_ROWS[character].split("/")
    if len(rows) != 7 or len(set(map(len, rows))) != 1:
        raise OedoPixelFontError(f"malformed seven-row glyph {character!r}")
    width = len(rows[0])
    if not 1 <= width <= 7 or any(set(r) - {"X", "."} for r in rows):
        raise OedoPixelFontError(f"bad pixel grid for {character!r}")
    xshift = int(width <= 6)
    bitmap = bytearray(16)
    for y, src in enumerate(_VERTICAL_ROW_MAP, start=CAP_TOP):
        for x, pixel in enumerate(rows[src]):
            if pixel == "X":
                bitmap[y] |= 0x80 >> (x + xshift)
    for y, row in enumerate(_DESCENDERS.get(character, ()), start=BASELINE + 1):
        if len(row) != width or set(row) - {"X", "."}:
            raise OedoPixelFontError(f"malformed descender {character!r}")
        for x, pixel in enumerate(row):
            if pixel == "X":
                bitmap[y] |= 0x80 >> (x + xshift)
    if character != " " and not any(bitmap):
        raise OedoPixelFontError(f"empty bitmap {character!r}")
    return bytes(bitmap)


def authored_atlas(characters: str = PILOT_CHARACTERS) -> RasterizedAtlas:
    """Generate exact native atlas, with no external .ttf or font binary."""
    if not characters or len(set(characters)) != len(characters):
        raise OedoPixelFontError("atlas repertoire must be nonempty and unique")
    if len(characters) > NATIVE_GLYPH_LIMIT:
        raise OedoPixelFontError(f"exceeds native {NATIVE_GLYPH_LIMIT}-slot atlas")
    if " " not in characters or "?" not in characters:
        raise OedoPixelFontError("native font needs space and question mark")
    bitmaps = tuple(glyph_bitmap(ch) for ch in characters)
    digest = hashlib.sha256(
        b"OEDO-AUTHORED-8x16-v2\x00"
        + characters.encode("utf-8") + b"\x00" + b"".join(bitmaps)
    ).hexdigest()
    return RasterizedAtlas(
        characters=characters,
        glyphs=bitmaps,
        source_sha256=digest,
        config=RasterConfig(point_size=13, threshold=128),
    )


def authored_vwf(characters: str = PILOT_CHARACTERS) -> VwfFont:
    """Proportional metrics from actual emitted glyph pixels, not TTF widths."""
    atlas = authored_atlas(characters)
    return derive_vwf_font(atlas.characters, atlas.glyphs, tracking=1, space_advance=4)


@dataclass(frozen=True)
class GlyphCoverageReport:
    source_rows: int
    nonempty_rows: int
    visible_characters: int
    unique_characters: int
    used: str
    missing: tuple[dict[str, str | int], ...]
    native_slots_needed: int
    native_slot_capacity: int
    would_fit_native: bool

    def as_dict(self) -> dict:
        return asdict(self)


def audit_glyphs(
    texts: Iterable[str], *, supported: str = PILOT_CHARACTERS
) -> GlyphCoverageReport:
    """Count exact visible English symbols; never substitute unsupported glyphs."""
    source_rows = nonempty = total = 0
    counts: Counter[str] = Counter()
    for value in texts:
        if not isinstance(value, str):
            raise TypeError("translation rows must be strings")
        source_rows += 1
        if not value:
            continue
        nonempty += 1
        counts.update(value)
        total += len(value)
    missing = tuple(
        {
            "character": ch,
            "codepoint": f"U+{ord(ch):04X}",
            "name": unicodedata.name(ch, "UNKNOWN"),
            "occurrences": count,
        }
        for ch, count in sorted(counts.items(), key=lambda item: ord(item[0]))
        if ch not in supported
    )
    needed = len(set(counts) | {" ", "?"})
    return GlyphCoverageReport(
        source_rows=source_rows,
        nonempty_rows=nonempty,
        visible_characters=total,
        unique_characters=len(counts),
        used="".join(ch for ch in DEFAULT_DISPLAY_CHARACTERS if ch in counts),
        missing=missing,
        native_slots_needed=needed,
        native_slot_capacity=NATIVE_GLYPH_LIMIT,
        would_fit_native=nonempty > 0 and not missing and needed <= NATIVE_GLYPH_LIMIT,
    )


_TRANSLATION_COLUMNS = (
    "Definitive Localization", "Final Localization",
    "english_translation", "English Translation", "Translation", "english",
)


def audit_translation_file(
    path: Path, *, column: str | None = None
) -> GlyphCoverageReport:
    """Read only the selected reviewed English TSV/CSV column; refuse ambiguity."""
    if path.suffix.lower() not in {".tsv", ".csv"}:
        raise OedoPixelFontError("audit accepts reviewed TSV or CSV only")
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        fields = reader.fieldnames or []
        matches = [name for name in _TRANSLATION_COLUMNS if name in fields]
        if column is None:
            if len(matches) != 1:
                raise OedoPixelFontError(
                    f"specify --column; missing or ambiguous English column: {fields}"
                )
            column = matches[0]
        elif column not in fields:
            raise OedoPixelFontError(f"selected column {column!r} is missing")
        return audit_glyphs((row[column] or "" for row in reader))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Oedo dialogue glyph coverage")
    parser.add_argument("source", type=Path, help="Reviewed English TSV/CSV")
    parser.add_argument("--column", help="Exact visible English source column")
    parser.add_argument("--output", type=Path, help="Optional JSON coverage report")
    args = parser.parse_args(argv)
    report = audit_translation_file(args.source, column=args.column)
    content = json.dumps(report.as_dict(), indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    return 0 if report.would_fit_native else 1


if __name__ == "__main__":
    raise SystemExit(main())
