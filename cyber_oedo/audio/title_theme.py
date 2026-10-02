"""Optional user-supplied title/menu theme injector.

The retail disc's Track 1 is exactly 3,590 raw CD-DA sectors and ends where
Track 2 begins.  Replacing Track 1 byte-for-byte therefore allows a custom
47.866... second menu theme without moving the data track, changing any game
LBAs, or shifting later CD audio tracks.

No copyrighted music is included by this project.  The helper accepts only a
user-supplied 44.1 kHz, 16-bit, stereo PCM WAV and converts it to the exact
raw PCM footprint used by the authenticated disc.
"""

from __future__ import annotations

import hashlib
import pathlib
import wave
from dataclasses import dataclass

CDDA_SAMPLE_RATE = 44_100
CDDA_CHANNELS = 2
CDDA_SAMPLE_WIDTH = 2
CDDA_SECTOR_BYTES = 2352
TRACK1_SECTORS = 3590
TRACK1_BYTES = TRACK1_SECTORS * CDDA_SECTOR_BYTES
TRACK1_SAMPLE_FRAMES = TRACK1_BYTES // (CDDA_CHANNELS * CDDA_SAMPLE_WIDTH)
TRACK1_SECONDS = TRACK1_SAMPLE_FRAMES / CDDA_SAMPLE_RATE
TRACK1_SOURCE_SHA256 = (
    "50dba07846f7f61a13e9e614651a129d704f9501b1832f19ae86b0f4a21d8e61"
)


class TitleThemeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ThemeBuild:
    raw_cdda: bytes
    source_frames: int
    output_frames: int
    truncated_frames: int
    padded_frames: int
    fade_frames: int


def _apply_linear_fade_out(raw: bytearray, frames: int) -> None:
    if frames <= 0:
        return
    total_frames = len(raw) // 4
    frames = min(frames, total_frames)
    start = total_frames - frames
    for frame in range(start, total_frames):
        remaining = total_frames - frame - 1
        scale_num = remaining
        scale_den = max(1, frames - 1)
        byte_at = frame * 4
        for channel in range(2):
            sample_at = byte_at + channel * 2
            sample = int.from_bytes(
                raw[sample_at : sample_at + 2],
                "little",
                signed=True,
            )
            faded = int(sample * scale_num / scale_den)
            raw[sample_at : sample_at + 2] = faded.to_bytes(
                2, "little", signed=True
            )


def build_theme_track(
    wav_path: pathlib.Path,
    *,
    fade_out_seconds: float = 1.5,
) -> ThemeBuild:
    """Convert one PCM WAV to the exact retail Track-1 raw-CDDA footprint."""

    if fade_out_seconds < 0:
        raise TitleThemeError("fade_out_seconds must be non-negative")

    with wave.open(str(wav_path), "rb") as stream:
        if stream.getframerate() != CDDA_SAMPLE_RATE:
            raise TitleThemeError("theme WAV must be 44.1 kHz")
        if stream.getnchannels() != CDDA_CHANNELS:
            raise TitleThemeError("theme WAV must be stereo")
        if stream.getsampwidth() != CDDA_SAMPLE_WIDTH:
            raise TitleThemeError("theme WAV must be 16-bit PCM")
        if stream.getcomptype() != "NONE":
            raise TitleThemeError("theme WAV must be uncompressed PCM")
        source_frames = stream.getnframes()
        raw = bytearray(stream.readframes(source_frames))

    expected_source_bytes = source_frames * CDDA_CHANNELS * CDDA_SAMPLE_WIDTH
    if len(raw) != expected_source_bytes:
        raise TitleThemeError("theme WAV returned an unexpected PCM byte count")

    if len(raw) > TRACK1_BYTES:
        truncated_frames = (len(raw) - TRACK1_BYTES) // 4
        del raw[TRACK1_BYTES:]
    else:
        truncated_frames = 0

    padded_frames = 0
    if len(raw) < TRACK1_BYTES:
        padded = TRACK1_BYTES - len(raw)
        if padded % 4:
            raise AssertionError("Track-1 padding is not sample-frame aligned")
        padded_frames = padded // 4
        raw.extend(bytes(padded))

    # Fade only the audible portion.  If a short source was padded with silence,
    # fade the source tail before the padding rather than fading silence.
    audible_frames = min(source_frames, TRACK1_SAMPLE_FRAMES)
    fade_frames = min(
        audible_frames,
        round(fade_out_seconds * CDDA_SAMPLE_RATE),
    )
    if fade_frames:
        audible = bytearray(raw[: audible_frames * 4])
        _apply_linear_fade_out(audible, fade_frames)
        raw[: audible_frames * 4] = audible

    if len(raw) != TRACK1_BYTES:
        raise AssertionError("theme Track 1 has the wrong final byte length")

    return ThemeBuild(
        raw_cdda=bytes(raw),
        source_frames=source_frames,
        output_frames=TRACK1_SAMPLE_FRAMES,
        truncated_frames=truncated_frames,
        padded_frames=padded_frames,
        fade_frames=fade_frames,
    )


def verify_retail_track1(raw_track: bytes) -> None:
    if len(raw_track) != TRACK1_BYTES:
        raise TitleThemeError("retail Track 1 has the wrong byte length")
    if hashlib.sha256(raw_track).hexdigest() != TRACK1_SOURCE_SHA256:
        raise TitleThemeError("retail Track 1 failed its SHA-256 source guard")


def inject_theme_into_clonecd_img(
    source_img: pathlib.Path,
    output_img: pathlib.Path,
    wav_path: pathlib.Path,
    *,
    fade_out_seconds: float = 1.5,
) -> ThemeBuild:
    """Copy a CloneCD IMG and replace only the raw Track-1 audio extent."""

    image = source_img.read_bytes()
    if len(image) < TRACK1_BYTES:
        raise TitleThemeError("CloneCD IMG is shorter than Track 1")
    verify_retail_track1(image[:TRACK1_BYTES])

    theme = build_theme_track(wav_path, fade_out_seconds=fade_out_seconds)
    output_img.parent.mkdir(parents=True, exist_ok=True)
    output_img.write_bytes(theme.raw_cdda + image[TRACK1_BYTES:])
    return theme
