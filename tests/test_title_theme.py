from __future__ import annotations

import pathlib
import tempfile
import unittest
import wave

from cyber_oedo.audio.title_theme import (
    CDDA_CHANNELS,
    CDDA_SAMPLE_RATE,
    CDDA_SAMPLE_WIDTH,
    TRACK1_BYTES,
    TRACK1_SAMPLE_FRAMES,
    build_theme_track,
)


class TitleThemeTests(unittest.TestCase):
    def _wav(self, frames: int) -> pathlib.Path:
        directory = pathlib.Path(tempfile.mkdtemp())
        path = directory / "theme.wav"
        sample = (1000).to_bytes(2, "little", signed=True)
        frame = sample + sample
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(CDDA_CHANNELS)
            stream.setsampwidth(CDDA_SAMPLE_WIDTH)
            stream.setframerate(CDDA_SAMPLE_RATE)
            stream.writeframes(frame * frames)
        return path

    def test_short_theme_is_padded_to_exact_track_size(self) -> None:
        result = build_theme_track(self._wav(1000), fade_out_seconds=0)
        self.assertEqual(len(result.raw_cdda), TRACK1_BYTES)
        self.assertEqual(result.output_frames, TRACK1_SAMPLE_FRAMES)
        self.assertEqual(result.source_frames, 1000)
        self.assertGreater(result.padded_frames, 0)
        self.assertEqual(result.truncated_frames, 0)

    def test_long_theme_is_truncated_to_exact_track_size(self) -> None:
        result = build_theme_track(
            self._wav(TRACK1_SAMPLE_FRAMES + 100),
            fade_out_seconds=0,
        )
        self.assertEqual(len(result.raw_cdda), TRACK1_BYTES)
        self.assertEqual(result.truncated_frames, 100)
        self.assertEqual(result.padded_frames, 0)


if __name__ == "__main__":
    unittest.main()
