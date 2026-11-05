"""Pixel-accurate synthetic previews of the Oedo authored 8x16 font.

No proprietary game art, ROM, BIOS, or font binary is read or distributed.
The font pixels and widths are sourced from cyber_oedo.text.oedo_pixel_font.
These are mockups, NOT live Mesen screenshots or certified shadow features.

Usage: python tools/preview_oedo_pixel_font.py /tmp/oedo-font-preview
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cyber_oedo.text.oedo_pixel_font import authored_vwf, glyph_bitmap
from cyber_oedo.text.vwf_text import wrap_vwf


def draw_text(image, text: str, x: int, y: int, *, vwf: bool, shadow: bool) -> None:
    metrics = authored_vwf()
    for char in text:
        m = metrics.metric(char)
        points = [
            (x + (cx - m.left if vwf else cx), y + row)
            for row, value in enumerate(glyph_bitmap(char))
            for cx in range(8)
            if value & (0x80 >> cx)
        ]
        if shadow:
            for px, py in points:
                if 0 <= px + 1 < image.width and 0 <= py + 1 < image.height:
                    image.putpixel((px + 1, py + 1), (5, 9, 18))
        for px, py in points:
            if 0 <= px < image.width and 0 <= py < image.height:
                image.putpixel((px, py), (246, 246, 233))
        x += m.advance if vwf else 8


def specimen():
    from PIL import Image, ImageDraw, ImageFont

    result = Image.new("RGB", (824, 525), (16, 26, 38))
    draw = ImageDraw.Draw(result)
    draw.text((16, 12), "OEDO PIXEL — ORIGINAL 8x16 / 95 CORE GLYPHS",
              font=ImageFont.load_default(), fill=(247, 238, 218))
    sections = (
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "abcdefghijklmnopqrstuvwxyz",
        "0123456789",
        " !\"#$%&'()*+,-./:;=?@[]_",
        "“”‘’—–…¥■",
    )
    y = 45
    for section in sections:
        for start in range(0, len(section), 18):
            for index, char in enumerate(section[start:start + 18]):
                x = 20 + index * 44
                for ry, byte in enumerate(glyph_bitmap(char)):
                    for cx in range(8):
                        if byte & (0x80 >> cx):
                            left, top = x + cx * 3, y + ry * 3
                            draw.rectangle(
                                (left, top, left + 2, top + 2),
                                fill=(239, 236, 226),
                            )
            y += 56
        y += 5
    return result


def panel(*, vwf: bool, warm: bool, shadow: bool):
    from PIL import Image, ImageDraw

    result = Image.new("RGB", (256, 224))
    pix = result.load()
    for y in range(224):
        rgb = ((172 + y // 14, 143 + y // 15, 125 + y // 17) if warm
               else (24 + y // 9, 23 + y // 15, 45 + y // 7))
        for x in range(256):
            pix[x, y] = rgb
    draw = ImageDraw.Draw(result)
    if warm:
        draw.rectangle((3, 28, 250, 135), fill=(151, 125, 119))
        for x in range(11, 245, 22):
            draw.line((x, 29, x, 135), fill=(179, 159, 149), width=2)
    else:
        draw.rectangle((0, 115, 255, 156), fill=(13, 23, 35))
        draw.polygon(((25, 155), (38, 103), (47, 105), (59, 155)),
                     fill=(14, 15, 24))
        draw.line((0, 160, 255, 160), fill=(216, 79, 108), width=2)
    text = "“You’re late,” Sengoku. — ¥500!"
    lines = (wrap_vwf(text, authored_vwf(), max_pixels=176)
             if vwf else ("“You’re late,”", "Sengoku. — ¥500!"))
    for n, line in enumerate(lines):
        draw_text(result, line, 20, 170 + 17 * n, vwf=vwf, shadow=shadow)
    return result


def preview_files(output: Path) -> tuple[Path, Path]:
    from PIL import Image, ImageDraw, ImageFont

    output.mkdir(parents=True, exist_ok=True)
    glyphs = output / "oedo_pixel_font_specimen.png"
    specimen().save(glyphs)
    board = Image.new("RGB", (572, 559), (10, 18, 31))
    draw = ImageDraw.Draw(board)
    draw.text((14, 10), "OEDO ENGLISH PIXEL FONT / PREVIEW, NOT IN-GAME",
              fill=(242, 240, 226), font=ImageFont.load_default())
    configurations = (
        (False, False, False, "8px FIXED CELL / PILOT"),
        (True, False, False, "PROPORTIONAL / NO SHADOW"),
        (True, False, True, "VWF / SHADOW CONCEPT"),
        (True, True, True, "VWF / BRIGHT SCENE CONCEPT"),
    )
    for index, (vwf, warm, shadow, caption) in enumerate(configurations):
        x, y = 16 + index % 2 * 272, 54 + index // 2 * 256
        draw.text((x, y - 17), caption,
                  fill=(218, 225, 218), font=ImageFont.load_default())
        board.paste(panel(vwf=vwf, warm=warm, shadow=shadow), (x, y))
    examples = output / "oedo_pixel_font_dialogue_comparison.png"
    board.save(examples)
    return glyphs, examples


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview Oedo source-authored glyphs")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args(argv)
    for path in preview_files(args.output_dir):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
