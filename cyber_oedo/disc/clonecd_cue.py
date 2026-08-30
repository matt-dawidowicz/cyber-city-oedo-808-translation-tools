"""Create a non-destructive one-file CUE view of a CloneCD disc set.

The PC Engine CD image used by this project is a single raw 2352-byte IMG
with a CloneCD CCD table of contents.  Mesen accepts a CUE descriptor, but
does not offer the CCD file in its normal Open filter.  This utility converts
only the TOC metadata: it never reads or changes the IMG or SUB contents.
"""

from __future__ import annotations

import argparse
import configparser
from dataclasses import dataclass
from pathlib import Path


RAW_SECTOR_SIZE = 2352


@dataclass(frozen=True)
class Track:
    """One CCD TOC track expressed in raw-image sector coordinates."""

    number: int
    control: int
    absolute_lba: int

    @property
    def cue_mode(self) -> str:
        """Return the CUE track type implied by the CloneCD control field."""

        return "MODE1/2352" if self.control & 0x04 else "AUDIO"


def parse_tracks(ccd_path: Path) -> list[Track]:
    """Read and validate the numbered track entries from a CCD descriptor."""

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    with ccd_path.open("r", encoding="ascii", newline="") as stream:
        parser.read_file(stream)

    tracks: list[Track] = []
    for section in parser.sections():
        if not section.startswith("Entry "):
            continue
        entry = parser[section]
        point = int(entry["Point"], 0)
        if not 1 <= point <= 99:
            continue
        tracks.append(
            Track(
                number=point,
                control=int(entry["Control"], 0),
                absolute_lba=int(entry["PLBA"], 0),
            )
        )

    tracks.sort(key=lambda track: track.number)
    expected = list(range(1, len(tracks) + 1))
    if [track.number for track in tracks] != expected:
        raise ValueError("CCD track numbers must be consecutive from 1")
    if not tracks or tracks[0].absolute_lba != 0:
        raise ValueError("CCD Track 1 must begin at raw image LBA 0")
    if any(
        later.absolute_lba <= earlier.absolute_lba
        for earlier, later in zip(tracks, tracks[1:])
    ):
        raise ValueError("CCD track starts must be strictly increasing")
    return tracks


def cue_time(lba: int) -> str:
    """Format a non-negative raw-image sector offset as CUE MM:SS:FF."""

    if lba < 0:
        raise ValueError("CUE times cannot be negative")
    minutes, remainder = divmod(lba, 75 * 60)
    seconds, frames = divmod(remainder, 75)
    return f"{minutes:02d}:{seconds:02d}:{frames:02d}"


def render_cue(
    *, image_name: str, tracks: list[Track], catalog: str | None
) -> str:
    """Render a CUE descriptor that references the original monolithic IMG."""

    lines: list[str] = []
    if catalog and catalog != "0" * len(catalog):
        lines.append(f"CATALOG {catalog}")
    lines.append(f'FILE "{image_name}" BINARY')
    for track in tracks:
        lines.append(f"  TRACK {track.number:02d} {track.cue_mode}")
        lines.append(f"    INDEX 01 {cue_time(track.absolute_lba)}")
    return "\n".join(lines) + "\n"


def build_cue(ccd_path: Path, output_path: Path) -> None:
    """Validate the CloneCD companions and write a new descriptor only."""

    if ccd_path.suffix.lower() != ".ccd":
        raise ValueError("source path must name a .ccd file")
    image_path = ccd_path.with_suffix(".img")
    sub_path = ccd_path.with_suffix(".sub")
    for companion in (image_path, sub_path):
        if not companion.is_file():
            raise FileNotFoundError(f"missing CloneCD companion: {companion}")
    if image_path.stat().st_size % RAW_SECTOR_SIZE:
        raise ValueError(
            "raw CloneCD IMG is not a whole number of 2352-byte sectors"
        )

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    with ccd_path.open("r", encoding="ascii", newline="") as stream:
        parser.read_file(stream)
    tracks = parse_tracks(ccd_path)
    image_sectors = image_path.stat().st_size // RAW_SECTOR_SIZE
    if tracks[-1].absolute_lba >= image_sectors:
        raise ValueError("CCD track start lies outside the raw IMG")
    output_path.write_text(
        render_cue(
            image_name=image_path.name,
            tracks=tracks,
            catalog=parser["Disc"].get("Catalog"),
        ),
        encoding="ascii",
        newline="\n",
    )


def main() -> int:
    """Generate a CUE descriptor alongside a supplied CloneCD descriptor."""

    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument(
        "ccd", type=Path, help="source CloneCD .ccd file"
    )
    argument_parser.add_argument(
        "output", type=Path, help="new .cue file; must not exist"
    )
    args = argument_parser.parse_args()
    if args.output.exists():
        argument_parser.error(
            f"refusing to overwrite existing output: {args.output}"
        )
    build_cue(args.ccd, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
