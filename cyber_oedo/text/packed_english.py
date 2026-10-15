"""Collision-free packed English tokens for the stock two-byte glyph parser.

The common dialogue parser already treats any first byte above 0x80 as the
start of one two-byte glyph. English can therefore use a private Shift-JIS
lead range instead of introducing a new escape marker into the bytecode.

One private token represents two English display glyphs. The renderer can
intercept the private lead range, resolve the token through a pair table, and
compose two 8x16 glyphs into the existing 16x16 staging cell. Ordinary
Shift-JIS continues through the stock EX_GETFNT path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

PRIVATE_LEADS = tuple(range(0xF0, 0xFD))
PRIVATE_TRAILS = tuple(range(0x40, 0x7F)) + tuple(range(0x80, 0xFD))
PRIVATE_TOKEN_CAPACITY = len(PRIVATE_LEADS) * len(PRIVATE_TRAILS)

# Printable ASCII plus typographic characters used by the final localization
# master. A build-specific atlas may supply any subset/superset, but one byte
# is enough to address the complete repertoire.
DEFAULT_DISPLAY_CHARACTERS = (
    "".join(chr(value) for value in range(0x20, 0x7F))
    + "“”‘’—–…¥■"
)


class PackedEnglishError(ValueError):
    """Raised when text cannot be represented by the configured packed atlas."""


def private_token_for_index(index: int) -> bytes:
    """Return the two-byte private-SJIS token for a zero-based pair index."""

    if not 0 <= index < PRIVATE_TOKEN_CAPACITY:
        raise PackedEnglishError(
            f"private token index {index} is outside 0..{PRIVATE_TOKEN_CAPACITY - 1}"
        )
    lead_index, trail_index = divmod(index, len(PRIVATE_TRAILS))
    return bytes((PRIVATE_LEADS[lead_index], PRIVATE_TRAILS[trail_index]))


def private_index_from_token(token: bytes) -> int:
    """Decode one private-SJIS token back to its zero-based pair index."""

    if len(token) != 2:
        raise PackedEnglishError("a packed English token must be exactly two bytes")
    lead, trail = token
    try:
        lead_index = PRIVATE_LEADS.index(lead)
        trail_index = PRIVATE_TRAILS.index(trail)
    except ValueError as error:
        raise PackedEnglishError(
            f"not a private English token: {token.hex(' ')}"
        ) from error
    return lead_index * len(PRIVATE_TRAILS) + trail_index


@dataclass(frozen=True, slots=True)
class GlyphRepertoire:
    """Stable one-byte glyph IDs used by the packed runtime pair table."""

    characters: str = DEFAULT_DISPLAY_CHARACTERS

    def __post_init__(self) -> None:
        if len(set(self.characters)) != len(self.characters):
            raise PackedEnglishError("glyph repertoire contains duplicate characters")
        if len(self.characters) > 256:
            raise PackedEnglishError("glyph repertoire exceeds one-byte glyph IDs")

    @property
    def char_to_id(self) -> dict[str, int]:
        return {
            character: index
            for index, character in enumerate(self.characters)
        }

    def glyph_id(self, character: str) -> int:
        try:
            return self.char_to_id[character]
        except KeyError as error:
            raise PackedEnglishError(
                f"character {character!r} is not present in the English glyph repertoire"
            ) from error

    def character(self, glyph_id: int) -> str:
        if not 0 <= glyph_id < len(self.characters):
            raise PackedEnglishError(f"invalid glyph ID {glyph_id}")
        return self.characters[glyph_id]


@dataclass(frozen=True, slots=True)
class PackedEnglishDictionary:
    """Deterministic map between character pairs and private glyph tokens."""

    pairs: tuple[str, ...]
    repertoire: GlyphRepertoire = GlyphRepertoire()

    def __post_init__(self) -> None:
        if len(self.pairs) > PRIVATE_TOKEN_CAPACITY:
            raise PackedEnglishError(
                f"{len(self.pairs)} character pairs exceed the "
                f"{PRIVATE_TOKEN_CAPACITY}-token private namespace"
            )
        if len(set(self.pairs)) != len(self.pairs):
            raise PackedEnglishError("packed dictionary contains duplicate pairs")
        for pair in self.pairs:
            if len(pair) != 2:
                raise PackedEnglishError(
                    f"pair {pair!r} is not exactly two characters"
                )
            self.repertoire.glyph_id(pair[0])
            self.repertoire.glyph_id(pair[1])

    @classmethod
    def from_texts(
        cls,
        texts: Iterable[str],
        *,
        repertoire: GlyphRepertoire | None = None,
    ) -> "PackedEnglishDictionary":
        """Build a deterministic lexicographically ordered pair dictionary.

        Text is paired from its first character. Odd-length strings receive a
        trailing ordinary space. Controls are deliberately outside this API;
        callers pack only visible English spans between preserved bytecode
        controls.
        """

        glyphs = repertoire or GlyphRepertoire()
        found: set[str] = set()
        for text in texts:
            if not isinstance(text, str):
                raise TypeError("packed English input must be text")
            for character in text:
                glyphs.glyph_id(character)
            padded = text if len(text) % 2 == 0 else text + " "
            found.update(
                padded[index : index + 2]
                for index in range(0, len(padded), 2)
            )
        return cls(tuple(sorted(found)), glyphs)

    @property
    def pair_to_index(self) -> dict[str, int]:
        return {
            pair: index
            for index, pair in enumerate(self.pairs)
        }

    def encode_visible_text(self, text: str) -> bytes:
        """Encode visible English as private two-byte glyph tokens."""

        for character in text:
            self.repertoire.glyph_id(character)
        padded = text if len(text) % 2 == 0 else text + " "
        mapping = self.pair_to_index
        result = bytearray()
        for offset in range(0, len(padded), 2):
            pair = padded[offset : offset + 2]
            try:
                index = mapping[pair]
            except KeyError as error:
                raise PackedEnglishError(
                    f"pair {pair!r} is absent from this packed dictionary"
                ) from error
            result.extend(private_token_for_index(index))
        return bytes(result)

    def decode_visible_text(
        self,
        encoded: bytes,
        *,
        strip_pad: bool = False,
    ) -> str:
        """Decode packed private tokens for diagnostics and round-trip tests."""

        if len(encoded) % 2:
            raise PackedEnglishError(
                "packed English byte stream must have even length"
            )
        pieces: list[str] = []
        for offset in range(0, len(encoded), 2):
            index = private_index_from_token(encoded[offset : offset + 2])
            if index >= len(self.pairs):
                raise PackedEnglishError(
                    f"token index {index} exceeds dictionary size {len(self.pairs)}"
                )
            pieces.append(self.pairs[index])
        decoded = "".join(pieces)
        return decoded.rstrip(" ") if strip_pad else decoded

    def runtime_pair_table(self) -> bytes:
        """Return two one-byte glyph IDs per token for the runtime renderer."""

        table = bytearray()
        for pair in self.pairs:
            table.append(self.repertoire.glyph_id(pair[0]))
            table.append(self.repertoire.glyph_id(pair[1]))
        return bytes(table)

    def utilization_report(self) -> dict[str, int | float]:
        used = len(self.pairs)
        return {
            "used_tokens": used,
            "token_capacity": PRIVATE_TOKEN_CAPACITY,
            "free_tokens": PRIVATE_TOKEN_CAPACITY - used,
            "utilization_percent": used / PRIVATE_TOKEN_CAPACITY * 100.0,
            "runtime_pair_table_bytes": used * 2,
            "glyph_repertoire_size": len(self.repertoire.characters),
            "glyph_atlas_1bpp_bytes_at_8x16": (
                len(self.repertoire.characters) * 16
            ),
        }
