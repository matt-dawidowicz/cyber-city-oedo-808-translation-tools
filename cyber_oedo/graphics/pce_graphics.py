"""Encode and decode raw PC Engine four-bit background tiles.

One 8-by-8 tile occupies 32 bytes split into four one-bit planes. This module
contains only the hardware codec and has no image-library dependency, so both
the disc builder and optional PNG diagnostics can use one format definition.
"""

from __future__ import annotations

from collections.abc import Sequence


def encode_tile(pixels: Sequence[int]) -> bytes:
    """Encode row-major palette indexes as one PC Engine 4bpp tile.

    Args:
        pixels: Exactly 64 integers in row-major order. Each value must be a
            palette index from 0 through 15.

    Returns:
        Exactly 32 bytes in the PC Engine planar tile layout.

    Raises:
        ValueError: If the input has the wrong length or contains a value
            outside the four-bit palette-index range.

    Design Decisions:
        This is the inverse of ``decode_tile``. Keeping both operations in a
        dependency-free module gives generated replacement art and diagnostic
        tools one shared, testable definition of the hardware format.
    """

    if len(pixels) != 64:
        raise ValueError(
            "A PC Engine 4bpp tile must contain exactly 64 pixels"
        )
    if any(not isinstance(pixel, int) or not 0 <= pixel <= 15
           for pixel in pixels):
        raise ValueError("Tile pixels must be integer palette indexes 0-15")

    encoded = bytearray(32)
    for y in range(8):
        for x in range(8):
            value = pixels[y * 8 + x]
            mask = 0x80 >> x
            for bit in range(4):
                if value & (1 << bit):
                    plane_offset = y * 2 + bit % 2
                    if bit >= 2:
                        plane_offset += 16
                    encoded[plane_offset] |= mask
    return bytes(encoded)


def decode_tile(tile: bytes) -> list[int]:
    """Decode one raw PC Engine tile into row-major palette indexes.

    Args:
        tile: Exactly 32 bytes in the PC Engine 4bpp planar layout.

    Returns:
        Sixty-four integers in row-major pixel order. Each value is a palette
        index from 0 through 15.

    Raises:
        ValueError: If ``tile`` is not exactly 32 bytes.

    Design Decisions:
        For each row, bytes at offsets ``0/1`` provide bitplanes 0/1 and bytes
        at ``16/17`` provide bitplanes 2/3. Bits are consumed most-significant
        first because bit 7 represents the leftmost pixel.
    """

    if len(tile) != 32:
        raise ValueError("A PC Engine 4bpp tile must be exactly 32 bytes")
    pixels: list[int] = []
    for y in range(8):
        planes = (
            tile[y * 2],
            tile[y * 2 + 1],
            tile[16 + y * 2],
            tile[17 + y * 2],
        )
        for x in range(8):
            mask = 0x80 >> x
            value = sum(
                ((plane & mask) != 0) << bit
                for bit, plane in enumerate(planes)
            )
            pixels.append(value)
    return pixels
