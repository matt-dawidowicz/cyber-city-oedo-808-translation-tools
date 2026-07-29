#!/usr/bin/env python3
"""Build a guarded CloneCD image for early human testing.

This command creates a complete disposable copy of the supplied CloneCD set
and applies the ``mission0-stock-renderer`` guarded insertion profile. The
profile is based on the committed ``mission0-v9`` stable baseline and removes
all dialogue-renderer code patches. It translates startup notices, prompts,
mission-title subtitles, and the opening
Mission 0 bartender conversation and complete ten-page opening narration with
sentence-case fullwidth Shift-JIS English that the original 16x16 BIOS font
path can render. Narration is word-wrapped on the code-confirmed 11-cell line
width. English punctuation stays inside that ordinary 11-cell budget.
Both copies of all seven opening criminal dossiers are translated and reflowed
without changing their portraits, interpreter, or record sizes.
The three Media Mix merchandise pages are translated and reflowed onto
non-overlapping tile rows without changing the general text renderer. An
optional antialiased title graphic and isolated grayscale palette replace the
original opening art; downstream builders can retain the original screen
without disabling translation patches.

The source CCD, IMG, and SUB must match the analyzed release exactly. Every
replacement must match its expected Japanese bytes and preserve byte length.
Only the affected 2048-byte user-data sectors are changed; their raw Mode 1
EDC/ECC fields are rebuilt. The builder then compares every raw sector against
the source and rejects changes outside the expected absolute LBAs.

This is a playable vertical slice, not a complete English translation. Most
dialogue, interfaces, and later game content remain Japanese until their
resource ownership, pointers, and page layouts are mapped.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import hashlib
import json
import pathlib
import shutil
import tempfile
from dataclasses import dataclass
from typing import Any

from cdrom_mode1 import (
    MODE1_SYNC,
    PayloadPatch,
    apply_payload_patches,
    read_payload_range,
)
from game_layout import (
    MODE1_USER_DATA_OFFSET,
    RAW_SECTOR_SIZE,
    SECTOR_SIZE,
    TRACK2_SECTOR_COUNT,
    TRACK2_START_LBA,
)
from title_screen import (
    TITLE_ASSET_BYTES,
    TITLE_PALETTE_BYTES,
    build_clean_title_asset,
    build_grayscale_title_palette_cycle,
)


BUILD_PROFILE = "mission0-stock-renderer"
OUTPUT_STEM = (
    "Cyber City Oedo 808 - Kemono no Alignment (Japan) "
    "[Stock Renderer Test]"
)
PROLOGUE_WRAP_WIDTH = 11
INFORMATION_HIDDEN_ROW = 0x1E
TITLE_SCREEN_OFFSET = 0x0000A000
TITLE_PALETTE_OFFSET = 0x00002848
TITLE_SCREEN_MODES = ("clean", "original")
DEFAULT_TITLE_SCREEN_MODE = "clean"
TITLE_SCREEN_SOURCE_SHA256 = (
    "74319e81bfeba32b385620a8bf32848e"
    "78da19271c87b6337decf4991a2fe5c4"
)
TITLE_PALETTE_SOURCE_SHA256 = (
    "650a61cee3f91e3c4b2a5159feb38800"
    "384daa2ad6ba48903f3596417fa1085b"
)
MANIFEST_INLINE_BINARY_LIMIT = 64
SOURCE_HASHES = {
    ".ccd": (
        "716e509edaeeddc1b12c827ada3579b15"
        "c612a5f16400b72dabad2c6bcfece1b"
    ),
    ".img": (
        "815a8dda33ba2bb046fcbde773ad3a80fc"
        "6f89a96ef07e9c06bcc1c2e5fddece"
    ),
    ".sub": (
        "ae8f54a4cd83e5e985d975f29654f8aa"
        "2f384cb4f7dcbd16a39b05b3263db411"
    ),
}


@dataclass(frozen=True, slots=True)
class InPlaceTextPatch:
    """Describe one fullwidth Shift-JIS startup-text replacement.

    Attributes:
        offset: Byte address in the extracted Track 2 payload.
        source_text: Exact decoded text expected at the address.
        english: Printable ASCII wording converted to fullwidth characters.
        purpose: Human-readable location and intent for reports.
        wrap_width: Optional fullwidth-cell width used to pad word-wrapped
            lines before encoding.

    Notes:
        ``english`` may be shorter than ``source_text`` and is right-padded
        with fullwidth spaces. It may never be longer.
    """

    offset: int
    source_text: str
    english: str
    purpose: str
    wrap_width: int | None = None

    @property
    def formatted_english(self) -> str:
        """Return ASCII English with optional cell-aware word wrapping.

        Returns:
            Original English when ``wrap_width`` is ``None``. Otherwise,
            returns lines flattened into one string with every non-final line
            padded to ``wrap_width`` cells.

        Raises:
            ValueError: If the configured width or wording cannot be wrapped.

        Notes:
            Padding relies on the game's automatic fixed-cell wrap. It adds no
            control bytes and does not change renderer behavior.
        """

        if self.wrap_width is None:
            return self.english
        return wrap_ascii_text(self.english, self.wrap_width)

    @property
    def replacement_text(self) -> str:
        """Return fullwidth English padded to the source character count.

        Returns:
            Fullwidth Shift-JIS text with exactly ``len(source_text)`` Unicode
            characters.

        Raises:
            ValueError: If the English contains non-ASCII text or exceeds the
                source character count after conversion.
        """

        replacement = ascii_to_fullwidth(self.formatted_english)
        available = len(self.source_text)
        if len(replacement) > available:
            raise ValueError(
                f"{self.purpose}: English uses {len(replacement)} "
                f"characters; capacity is {available}"
            )
        return replacement + ("\u3000" * (available - len(replacement)))

    def to_payload_patch(self) -> PayloadPatch:
        """Encode and validate this text patch for the raw-sector layer.

        Returns:
            A same-size ``PayloadPatch`` using Shift-JIS source and replacement
            bytes.

        Raises:
            UnicodeEncodeError: If source or replacement text is not encodable
                as Shift-JIS.
            ValueError: If encoded byte lengths differ.
        """

        expected = self.source_text.encode("shift_jis")
        replacement = self.replacement_text.encode("shift_jis")
        if len(expected) != len(replacement):
            raise ValueError(
                f"{self.purpose}: Shift-JIS byte lengths differ "
                f"({len(expected)} != {len(replacement)})"
            )
        return PayloadPatch(
            offset=self.offset,
            expected=expected,
            replacement=replacement,
            label=self.purpose,
        )


@dataclass(frozen=True, slots=True)
class InformationScreenLine:
    """Describe one row-addressed Media Mix information-screen record.

    The game stores each visible line as a three-byte ``00 01 RR`` row command
    followed immediately by a null-terminated, fullwidth Shift-JIS string.
    ``RR`` addresses an 8-pixel tile row even though the BIOS glyphs are
    16 pixels tall. The Japanese data places most body lines on consecutive
    rows, which makes adjacent glyphs overlap vertically. This model keeps the
    text and row edits together so a translator cannot accidentally update one
    without documenting the other.

    Attributes:
        screen: Stable page identifier used by tests and build reports.
        text_offset: Payload byte offset of the first Shift-JIS text byte.
        source_row: Exact row byte expected in the original ``00 01 RR``
            command.
        source_text: Exact decoded, null-terminated text payload expected at
            ``text_offset``. The terminator itself is not replaced.
        english: Printable ASCII replacement. An empty string intentionally
            clears the source line with fullwidth spaces.
        purpose: Human-readable role for diagnostics and the build manifest.
        target_row: Row used by the English layout. ``None`` preserves
            ``source_row``.

    Side Effects:
        Instances are immutable descriptions. Converting one to payload
        patches does not modify a file.

    Failure Conditions:
        Construction rejects offsets that cannot have a preceding command and
        row values outside the five-bit, 32-row tilemap coordinate range.
        Text conversion can also fail under ``InPlaceTextPatch`` constraints.

    Design Decisions:
        Cleared source lines are moved to ``INFORMATION_HIDDEN_ROW``. That row
        is outside the visible 30-row field but keeps both tile rows of a
        16-pixel blank glyph inside the 32-row background map. This avoids
        changing record lengths, terminators, or the page interpreter.
        The interpreter draws records in storage order, so visible target rows
        must also increase in tuple order. Visible body lines use a common
        three-cell left margin, and wording is shortened when necessary to fit
        one source record. Moving a late decorative record upward would make
        its line appear after lower lines.
    """

    screen: str
    text_offset: int
    source_row: int
    source_text: str
    english: str
    purpose: str
    target_row: int | None = None

    def __post_init__(self) -> None:
        """Validate coordinates before they can enter a build profile.

        Raises:
            ValueError: If the text does not immediately follow a three-byte
                row command or either row is outside ``0x00`` through
                ``0x1F``.
        """

        if self.text_offset < 3:
            raise ValueError(
                f"{self.purpose}: text offset has no preceding row command"
            )
        if not 0 <= self.source_row <= 0x1F:
            raise ValueError(
                f"{self.purpose}: invalid source row {self.source_row:#x}"
            )
        if not 0 <= self.display_row <= 0x1F:
            raise ValueError(
                f"{self.purpose}: invalid target row {self.display_row:#x}"
            )

    @property
    def command_offset(self) -> int:
        """Return the payload offset of the line's ``00 01 RR`` command."""

        return self.text_offset - 3

    @property
    def display_row(self) -> int:
        """Return the source row or its explicit English-layout replacement."""

        if self.target_row is None:
            return self.source_row
        return self.target_row

    def to_text_patch(self) -> InPlaceTextPatch:
        """Return the guarded, same-size text replacement for this line."""

        return InPlaceTextPatch(
            offset=self.text_offset,
            source_text=self.source_text,
            english=self.english,
            purpose=self.purpose,
        )

    def to_layout_patch(self) -> PayloadPatch | None:
        """Return a guarded row-command edit, or ``None`` when unchanged.

        Returns:
            A three-byte payload patch preserving the ``00 01`` opcode and
            replacing only its row operand, or ``None`` if the original row is
            already correct for the English layout.
        """

        if self.display_row == self.source_row:
            return None
        return PayloadPatch(
            offset=self.command_offset,
            expected=bytes((0x00, 0x01, self.source_row)),
            replacement=bytes((0x00, 0x01, self.display_row)),
            label=f"{self.purpose} row",
        )


@dataclass(frozen=True, slots=True)
class OpeningProfileField:
    """Describe one field duplicated across the opening dossier banks.

    The opening stores seven criminal profiles twice. Each visible string
    immediately follows a ``00 0C RR`` command, where ``RR`` is an 8-pixel
    tile row. The two banks contain equivalent profile data at different
    addresses; one Gogul alias is shorter in the repeated copy. This model
    keeps the two guarded source strings, one English translation, and any
    layout edit together.

    Attributes:
        profile: Stable lowercase profile identifier used by tests and
            manifest labels.
        offsets: Payload offsets of the primary and repeated text strings.
        source_row: Exact row operand expected before both strings.
        source_text: Exact primary-bank Shift-JIS text.
        english: Printable ASCII replacement. An empty string clears the
            source field with fullwidth spaces.
        purpose: Concise field role for build diagnostics.
        target_row: Optional English-layout row. ``None`` preserves the source
            row.
        repeated_source_text: Exact repeated-bank text when it differs from
            ``source_text``. ``None`` means both copies must match.

    Side Effects:
        Instances are immutable. Conversion methods only allocate guarded
        patch descriptions.

    Failure Conditions:
        Construction rejects malformed copy counts, offsets that cannot have a
        preceding command, and rows outside the 32-row background map.
        Fullwidth conversion and same-size validation are delegated to
        ``InPlaceTextPatch``.

    Design Decisions:
        Both copies are mandatory so later navigation cannot reveal an
        untranslated duplicate. Japanese name lines are cleared offscreen and
        the existing romanized line is moved from row 5 to row 4. This removes
        the original one-row overlap without relocating records or altering
        portrait data.
    """

    profile: str
    offsets: tuple[int, int]
    source_row: int
    source_text: str
    english: str
    purpose: str
    target_row: int | None = None
    repeated_source_text: str | None = None

    def __post_init__(self) -> None:
        """Validate copy addresses and source/target row coordinates.

        Raises:
            ValueError: If the field lacks exactly two usable offsets or a row
                falls outside ``0x00`` through ``0x1F``.
        """

        if len(self.offsets) != 2:
            raise ValueError(
                f"{self.profile} {self.purpose}: expected two copies"
            )
        if any(offset < 3 for offset in self.offsets):
            raise ValueError(
                f"{self.profile} {self.purpose}: invalid text offset"
            )
        if not 0 <= self.source_row <= 0x1F:
            raise ValueError(
                f"{self.profile} {self.purpose}: invalid source row"
            )
        if not 0 <= self.display_row <= 0x1F:
            raise ValueError(
                f"{self.profile} {self.purpose}: invalid target row"
            )

    @property
    def display_row(self) -> int:
        """Return the source row or its explicit English-layout replacement."""

        if self.target_row is None:
            return self.source_row
        return self.target_row

    def source_for_copy(self, copy_index: int) -> str:
        """Return the guarded source text for one dossier-bank copy.

        Args:
            copy_index: Zero for the primary bank or one for the repeated bank.

        Returns:
            ``source_text`` except for a declared repeated-bank variant.

        Raises:
            IndexError: If ``copy_index`` is not zero or one.
        """

        if copy_index not in (0, 1):
            raise IndexError("opening profile copy index must be zero or one")
        if copy_index == 1 and self.repeated_source_text is not None:
            return self.repeated_source_text
        return self.source_text

    def to_text_patches(self) -> tuple[InPlaceTextPatch, InPlaceTextPatch]:
        """Return same-size fullwidth patches for both dossier copies."""

        copy_labels = ("primary", "repeated")
        return tuple(
            InPlaceTextPatch(
                offset=offset,
                source_text=self.source_for_copy(copy_index),
                english=self.english,
                purpose=(
                    f"opening profile {self.profile} {self.purpose} "
                    f"({copy_labels[copy_index]})"
                ),
            )
            for copy_index, offset in enumerate(self.offsets)
        )

    def to_layout_patches(self) -> tuple[PayloadPatch, ...]:
        """Return guarded row-command edits for both copies when required.

        Returns:
            Two three-byte patches when ``display_row`` differs from
            ``source_row``; otherwise an empty tuple.

        Design Decisions:
            The command prefix ``00 0C`` is preserved byte-for-byte. Only the
            row operand changes, keeping the dossier interpreter and null-
            terminated text structure intact.
        """

        if self.display_row == self.source_row:
            return ()
        return tuple(
            PayloadPatch(
                offset=offset - 3,
                expected=bytes((0x00, 0x0C, self.source_row)),
                replacement=bytes((0x00, 0x0C, self.display_row)),
                label=(
                    f"opening profile {self.profile} {self.purpose} "
                    f"copy {copy_index + 1} row"
                ),
            )
            for copy_index, offset in enumerate(self.offsets)
        )


# These strings are contiguous startup resources in payload sectors 3 and 4.
# Fullwidth English preserves the original byte counts and existing font path.
BOOT_MENU_PATCHES: tuple[InPlaceTextPatch, ...] = (
    InPlaceTextPatch(
        0x00001B2B,
        "ＮＯＴＩＣＥ：注意",
        "TEST DISC",
        "startup notice heading",
    ),
    InPlaceTextPatch(
        0x00001B41,
        "このゲームはＭＩＳＳＩＯＮ０からＭＩＳＳＯＮ８までの",
        "THIS GAME HAS 9 MISSIONS",
        "startup notice line 1",
    ),
    InPlaceTextPatch(
        0x00001B79,
        "全９パートから構成されています。",
        "HUMAN TEST BUILD",
        "startup notice line 2",
    ),
    InPlaceTextPatch(
        0x00001B9D,
        "ひとつのＭＩＳＳＯＮが終了するまで途中セーブは出来ません。",
        "SAVE ONLY AFTER EACH MISSION",
        "startup notice save rule",
    ),
    InPlaceTextPatch(
        0x00001BDB,
        "バックアップメモリは充分に余っていますか？",
        "BACKUP MEMORY READY?",
        "startup notice memory prompt",
    ),
    InPlaceTextPatch(
        0x00001C09,
        "メモリが足りないとセーブできません！",
        "NO SPACE TO SAVE!",
        "startup notice memory warning",
    ),
    InPlaceTextPatch(
        0x00001C43,
        "（最初から）",
        "(NEW)",
        "new game menu explanation",
    ),
    InPlaceTextPatch(
        0x00001C67,
        "（セーブしたところから）",
        "(FROM SAVE)",
        "data load menu explanation",
    ),
    InPlaceTextPatch(
        0x00001C9D,
        "（空きメモリーの確認）",
        "FREE SPACE",
        "memory check menu explanation",
    ),
    InPlaceTextPatch(
        0x00001CB7,
        "項目を選んでＩボタンを押して下さい。",
        "CHOOSE AND PRESS I",
        "main menu instruction",
    ),
    InPlaceTextPatch(
        0x00001D8A,
        "データをロードします。",
        "LOADING...",
        "load screen action",
    ),
    InPlaceTextPatch(
        0x00001DA4,
        "ファイル名を選んで下さい。",
        "CHOOSE FILE",
        "load screen file prompt",
    ),
    InPlaceTextPatch(
        0x00001E12,
        "ＯＫならば",
        "IF OK",
        "load confirmation condition",
    ),
    InPlaceTextPatch(
        0x00001E20,
        "Ｉボタンを押して下さい。",
        "PRESS I NOW",
        "load confirmation instruction",
    ),
    InPlaceTextPatch(
        0x00001EDF,
        "この状態では",
        "CANNOT",
        "new game save warning line 1",
    ),
    InPlaceTextPatch(
        0x00001EEF,
        "セーブができません。",
        "NO SAVING",
        "new game save warning line 2",
    ),
    InPlaceTextPatch(
        0x00001F07,
        "このままスタートしますか？",
        "START NOW?",
        "new game confirmation",
    ),
    InPlaceTextPatch(
        0x00001F25,
        "スタートするときは",
        "TO START",
        "new game instruction line 1",
    ),
    InPlaceTextPatch(
        0x00001F3B,
        "Ｉボタンを押して下さい。",
        "PRESS I NOW",
        "new game instruction line 2",
    ),
    InPlaceTextPatch(
        0x00001FFC,
        "ファイルが有りません。",
        "NO FILE",
        "missing save file error",
    ),
    InPlaceTextPatch(
        0x000020BB,
        "メモリーが壊れています。",
        "MEMORY ERROR",
        "damaged memory error",
    ),
    InPlaceTextPatch(
        0x00002182,
        "ＯＥＤＯ８０８ファイルは",
        "OEDO808 FILE",
        "memory file check line 1",
    ),
    InPlaceTextPatch(
        0x0000219E,
        "正しく存在しています。",
        "FILE OK",
        "memory file check line 2",
    ),
)


# These later startup resources complete the known memory-state messages.
STARTUP_V2_EXTRA_PATCHES: tuple[InPlaceTextPatch, ...] = (
    InPlaceTextPatch(
        0x00002263,
        "ＯＥＤＯ８０８ファイルは",
        "OEDO808 FILE",
        "memory creation line 1",
    ),
    InPlaceTextPatch(
        0x0000227F,
        "作成可能です。",
        "CAN USE",
        "memory creation line 2",
    ),
    InPlaceTextPatch(
        0x0000233C,
        "空きメモリーが足りません。",
        "NO FREE SPACE",
        "insufficient memory line 1",
    ),
    InPlaceTextPatch(
        0x0000235A,
        "何かファイルを消して下さい。",
        "DELETE A FILE",
        "insufficient memory line 2",
    ),
    InPlaceTextPatch(
        0x00002425,
        "ＯＥＤＯ８０８ファイルが",
        "OEDO808 FILE",
        "damaged game file line 1",
    ),
    InPlaceTextPatch(
        0x00002441,
        "壊れています。",
        "IS BAD",
        "damaged game file line 2",
    ),
    InPlaceTextPatch(
        0x00002453,
        "いったん削除してから",
        "DELETE IT",
        "damaged game file recovery line 1",
    ),
    InPlaceTextPatch(
        0x0000246B,
        "スタートして下さい。",
        "THEN START",
        "damaged game file recovery line 2",
    ),
    InPlaceTextPatch(
        0x0000252E,
        "フォーマットされていません。",
        "NOT FORMATTED",
        "unformatted memory line 1",
    ),
    InPlaceTextPatch(
        0x0000254E,
        "フォーマットしてから",
        "FORMAT IT",
        "unformatted memory recovery line 1",
    ),
    InPlaceTextPatch(
        0x00002566,
        "スタートして下さい。",
        "THEN START",
        "unformatted memory recovery line 2",
    ),
)


# Only the subtitle following each existing ``MISSION N`` label is replaced.
# The surrounding record marker and 0x40/0x5C controls remain original.
MISSION_TITLE_PATCHES: tuple[InPlaceTextPatch, ...] = (
    InPlaceTextPatch(
        0x00D1203B,
        "　　【大使護衛】",
        " [GUARD]",
        "Mission 1 title subtitle",
    ),
    InPlaceTextPatch(
        0x017C1BD5,
        "　【機密ファイル】",
        " [SECRET]",
        "Mission 2 title subtitle",
    ),
    InPlaceTextPatch(
        0x0226C03B,
        "　　　【容疑者】",
        " [SUSP.]",
        "Mission 3 title subtitle",
    ),
    InPlaceTextPatch(
        0x02B2A345,
        "　　【連続殺人】",
        " [KILLS]",
        "Mission 4 title subtitle",
    ),
    InPlaceTextPatch(
        0x03364B41,
        "　【不破博士失跡】",
        " [FUWA?]",
        "Mission 5 title subtitle",
    ),
    InPlaceTextPatch(
        0x03B4234A,
        "　　【赤毛と青目】",
        " [R+B]",
        "Mission 6 title subtitle",
    ),
    InPlaceTextPatch(
        0x0428FB71,
        "　　　【誘拐】",
        " [KID]",
        "Mission 7 title subtitle",
    ),
    InPlaceTextPatch(
        0x047D9341,
        "　【不破博士失跡】",
        " [FUWA?]",
        "Mission 5 duplicate title subtitle",
    ),
    InPlaceTextPatch(
        0x0485334A,
        "　　【赤毛と青目】",
        " [R+B]",
        "Mission 6 duplicate title subtitle",
    ),
    InPlaceTextPatch(
        0x04856331,
        "　　　【アジト】",
        " [LAIR]",
        "Mission 8 title subtitle",
    ),
)


# Dialogue is split wherever the original byte stream contains a control.
# Patching only visible runs preserves every marker, terminator, and control.
MISSION0_DIALOGUE_PATCHES: tuple[InPlaceTextPatch, ...] = (
    InPlaceTextPatch(
        0x00145892,
        "バーテン「いらっしゃいませ」",
        "Bart: Welcome.",
        "Mission 0 bartender greeting",
    ),
    InPlaceTextPatch(
        0x001458B8,
        "バーテン「お客さん、この辺は初めてでしょう。",
        "Bart: First time?",
        "Mission 0 bartender newcomer question",
    ),
    InPlaceTextPatch(
        0x001458E5,
        "いや、なに、顔を見りゃそれぐらいわかりますよ」",
        "Your face gave it away.",
        "Mission 0 bartender newcomer answer",
    ),
    InPlaceTextPatch(
        0x0014591B,
        (
            "バーテン「いったいどの辺から来なさったんです？"
            "　おっと、つまらないこと聞いちまいましたね」"
        ),
        "Bart: Where from? Never mind. Bad question.",
        "Mission 0 bartender origin question",
    ),
    InPlaceTextPatch(
        0x00145985,
        (
            "バーテン「ところで、あちらのお嬢さん、気を付けた方が"
            "いいですよ。どうも賞金稼ぎらしいですからね。ま、これは"
            "忠告ってやつです」"
        ),
        (
            "Bart: Watch that girl. Bounty hunter. "
            "Friendly warning."
        ),
        "Mission 0 bartender bounty hunter warning",
    ),
    InPlaceTextPatch(
        0x00145A07,
        (
            "バーテン「いやなに、わたしは最初からあんたも賞金稼ぎ"
            "なんじゃないかと思ってたんですよ」"
        ),
        "Bart: I knew you were a bounty hunter too.",
        "Mission 0 bartender recognizes player",
    ),
    InPlaceTextPatch(
        0x00145A65,
        "バーテン「ご注文は？」",
        "Your order?",
        "Mission 0 bartender order prompt",
    ),
    InPlaceTextPatch(
        0x00145A84,
        (
            "バーテン「無法地帯？　とんでもない。ここにはここの法が"
            "あるんですよ」"
        ),
        "Lawless? No. We have our own law.",
        "Mission 0 bartender law response",
    ),
    InPlaceTextPatch(
        0x00145ACC,
        (
            "バーテン「この上の新市街にある茶色のビルがその本部で"
            "さあ」"
        ),
        "HQ is in the brown building.",
        "Mission 0 bartender headquarters response",
    ),
    InPlaceTextPatch(
        0x00145B0A,
        (
            "バーテン「保安隊？　命が惜しかったら、そんなことは"
            "かぎ回らないに限ると思いますがね」"
        ),
        "Security? If you value life, do not ask.",
        "Mission 0 bartender security response",
    ),
    InPlaceTextPatch(
        0x00145B62,
        "バーテン「さあ、ちょっと知りませんね」",
        "Bart: No idea.",
        "Mission 0 bartender unknown response",
    ),
    InPlaceTextPatch(
        0x00145B8C,
        "俺は少し待ってみることにした。",
        "I waited a bit.",
        "Mission 0 wait narration",
    ),
    InPlaceTextPatch(
        0x00145BAB,
        "……だが何も起こらなかった。",
        "Nothing.",
        "Mission 0 wait result",
    ),
    InPlaceTextPatch(
        0x00145BD6,
        "バーテン「またどうぞ」",
        "Come again.",
        "Mission 0 bartender farewell",
    ),
)


# Each patch ends before one of the nine original 0x40 page controls. This
# translates the complete prologue while preserving its timing and paging.
MISSION0_PROLOGUE_PATCHES: tuple[InPlaceTextPatch, ...] = (
    InPlaceTextPatch(
        0x0017582A,
        "「俺の名はセンゴク、一匹狼の賞金稼ぎ。",
        "Sengoku. Loner.",
        "Mission 0 prologue introduction",
        wrap_width=PROLOGUE_WRAP_WIDTH,
    ),
    InPlaceTextPatch(
        0x00175851,
        (
            "ならず者の電脳犯罪者どもを片っ端から捕まえて"
            "警察に引き渡すのが俺の仕事だ。"
        ),
        "I hunt crooks and turn them in.",
        "Mission 0 opening narration job description",
        wrap_width=PROLOGUE_WRAP_WIDTH,
    ),
    InPlaceTextPatch(
        0x0017589C,
        "クリス・ダンフォード、コードネーム『バラ発疹』、",
        "Danford aka Rose Rash,",
        "Mission 0 prologue target name",
        wrap_width=PROLOGUE_WRAP_WIDTH,
    ),
    InPlaceTextPatch(
        0x001758CD,
        "こいつを追いかけて上海からＯＥＤＯに７年ぶりに舞い戻ってきた。",
        "His trail led me back to Oedo.",
        "Mission 0 prologue return to Oedo",
        wrap_width=PROLOGUE_WRAP_WIDTH,
    ),
    InPlaceTextPatch(
        0x0017590C,
        (
            "だが、この７年の間に俺の知っていたＯＥＤＯ、特に犯罪者"
            "たちのたむろする旧市街はすっかり様子が変わってしまって"
            "いた。"
        ),
        (
            "Seven years changed Oedo. "
            "Old City most of all."
        ),
        "Mission 0 prologue changed city",
        wrap_width=PROLOGUE_WRAP_WIDTH,
    ),
    InPlaceTextPatch(
        0x0017597F,
        (
            "電警−電脳警察−の下部組織だった保安隊が勢力を増し、"
            "旧市街全体を飲み込もうとしている。"
        ),
        "Security Force takes Old City.",
        "Mission 0 prologue Security Force expansion",
        wrap_width=PROLOGUE_WRAP_WIDTH,
    ),
    InPlaceTextPatch(
        0x001759D6,
        "街には武器が溢れ、以前よりずっと物騒な気配が漂っている。",
        "More guns. It's worse.",
        "Mission 0 prologue dangerous streets",
        wrap_width=PROLOGUE_WRAP_WIDTH,
    ),
    InPlaceTextPatch(
        0x00175A0F,
        "この世界最大の都市で何かが始まろうとしている。",
        "It begins.",
        "Mission 0 prologue impending event",
        wrap_width=PROLOGUE_WRAP_WIDTH,
    ),
    InPlaceTextPatch(
        0x00175A3E,
        "俺が仕掛けたワナをいつもすりぬけるＡ級の電脳犯罪者、",
        "Top crooks evade me,",
        "Mission 0 prologue rival criminals",
        wrap_width=PROLOGUE_WRAP_WIDTH,
    ),
    InPlaceTextPatch(
        0x00175A73,
        (
            "『ベンテン』と『ゴーグル』も、この街にやって来ている"
            "らしい。奴らの狙いは……？　なにはともあれ調べてみるか」"
        ),
        "Benten. Goggles. Here. Why? I'll look.",
        "Mission 0 prologue Benten and Goggles",
        wrap_width=PROLOGUE_WRAP_WIDTH,
    ),
)


# These three promotional pages are ordinary row-addressed text, not graphics.
# Body records are reflowed at two tile rows per 16-pixel glyph. Decorative
# box lines and superseded Japanese fragments are blanked on row 0x1E, which is
# below the visible 30-row field but remains inside the 32-row tilemap.
INFORMATION_SCREEN_LINES: tuple[InformationScreenLine, ...] = (
    # Video and LaserDisc merchandise.
    InformationScreenLine(
        "video",
        0x00006500,
        0x03,
        "　　　ＭＥＤＩＡ・ＭＩＸ・ＩＮＦＯＲＭＡＴＩＯＮ",
        "   MEDIA MIX INFORMATION",
        "Media Mix video heading",
    ),
    InformationScreenLine(
        "video",
        0x00006537,
        0x06,
        "　　　　　　ＯＥＤＯ８０８関連商品ファイル",
        "    OEDO 808 GUIDE",
        "Media Mix video guide heading",
    ),
    InformationScreenLine(
        "video",
        0x00006568,
        0x08,
        "　　　　　メディア：ビデオカセット＆ＬＤ",
        "   Video / LaserDisc",
        "Media Mix video format",
    ),
    InformationScreenLine(
        "video",
        0x00006594,
        0x09,
        "　　　　　タイトル：ＤＡＴＡ−１　古の記憶",
        "   1: Ancient Memory",
        "Media Mix video DATA-1 title",
        0x0A,
    ),
    InformationScreenLine(
        "video",
        0x000065C2,
        0x0A,
        "　　　　　　　　　　ＤＡＴＡ−２　おとりの機構",
        "   2: The Decoy Program",
        "Media Mix video DATA-2 title",
        0x0C,
    ),
    InformationScreenLine(
        "video",
        0x000065F4,
        0x0B,
        "　　　　　　　　　　ＤＡＴＡ−３　紅の媒体",
        "   3: Crimson Media",
        "Media Mix video DATA-3 title",
        0x0E,
    ),
    InformationScreenLine(
        "video",
        0x00006622,
        0x0C,
        "　　　　　監　　督：川尻善昭（マッドハウス）",
        "   Dir: Y. Kawajiri",
        "Media Mix video director",
        0x10,
    ),
    InformationScreenLine(
        "video",
        0x00006652,
        0x0D,
        "　　　　　商品概要：カラー／ステレオＨｉＦｉ",
        "",
        "Media Mix video superseded description",
        INFORMATION_HIDDEN_ROW,
    ),
    InformationScreenLine(
        "video",
        0x00006682,
        0x0E,
        "　　　　　発売元　：ジャパンホームビデオ（株）",
        "",
        "Media Mix video superseded publisher",
        INFORMATION_HIDDEN_ROW,
    ),
    InformationScreenLine(
        "video",
        0x000066B4,
        0x0F,
        "　　　　　価　格　：ビデオテープ（ＶＨＳ）",
        "",
        "Media Mix video superseded VHS label",
        INFORMATION_HIDDEN_ROW,
    ),
    InformationScreenLine(
        "video",
        0x000066E2,
        0x10,
        "　　　　　　　　　　９、６００円（税別）",
        "",
        "Media Mix video superseded VHS price",
        INFORMATION_HIDDEN_ROW,
    ),
    InformationScreenLine(
        "video",
        0x0000670E,
        0x11,
        "　　　　　　　　　　レーザーディスク（ＣＬＶ）",
        "   Color / Stereo Hi-Fi",
        "Media Mix video presentation format",
        0x12,
    ),
    InformationScreenLine(
        "video",
        0x00006740,
        0x12,
        "　　　　　　　　　　７、６００円（税別）",
        "",
        "Media Mix video superseded LaserDisc price",
        INFORMATION_HIDDEN_ROW,
    ),
    InformationScreenLine(
        "video",
        0x0000676D,
        0x16,
        "＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋",
        "",
        "Media Mix video superseded box top",
        INFORMATION_HIDDEN_ROW,
    ),
    InformationScreenLine(
        "video",
        0x000067AD,
        0x17,
        (
            "＋" + "　" * 2 + "好" + "　" * 5 + "評"
            + "　" * 4 + "発" + "　" * 4 + "売"
            + "　" * 4 + "中" + "　" * 4 + "＋"
        ),
        "   Japan Home Video",
        "Media Mix video publisher",
        0x14,
    ),
    InformationScreenLine(
        "video",
        0x000067ED,
        0x18,
        "＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋",
        "",
        "Media Mix video superseded box bottom",
        INFORMATION_HIDDEN_ROW,
    ),
    InformationScreenLine(
        "video",
        0x0000682D,
        0x1B,
        "＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃",
        "   VHS 9600 / LD 7600 + Tax",
        "Media Mix video prices",
        0x16,
    ),
    # Paperback novel merchandise.
    InformationScreenLine(
        "novel",
        0x000068B0,
        0x03,
        "　　　ＭＥＤＩＡ・ＭＩＸ・ＩＮＦＯＲＭＡＴＩＯＮ　　　　　　",
        "   MEDIA MIX INFORMATION",
        "Media Mix novel heading",
    ),
    InformationScreenLine(
        "novel",
        0x000068F3,
        0x06,
        "　　　　　　ＯＥＤＯ８０８関連商品ファイル　　　　　　　　　",
        "    OEDO 808 GUIDE",
        "Media Mix novel guide heading",
    ),
    InformationScreenLine(
        "novel",
        0x00006936,
        0x08,
        "　　　　　メディア：小説",
        "   Novels",
        "Media Mix novel format",
    ),
    InformationScreenLine(
        "novel",
        0x00006952,
        0x09,
        "　　　　　タイトル：反逆の孤狼　　（第１巻）",
        "   1: Rebel Lone Wolf",
        "Media Mix novel volume 1",
        0x0A,
    ),
    InformationScreenLine(
        "novel",
        0x00006982,
        0x0A,
        "　　　　　　　　　　華麗なる堕天使（第２巻）",
        "   2: Fallen Angel",
        "Media Mix novel volume 2",
        0x0C,
    ),
    InformationScreenLine(
        "novel",
        0x000069B2,
        0x0B,
        "　　　　　　　　　　魔眼の闘士　　（第３巻）",
        "   3: Evil-Eye Fighter",
        "Media Mix novel volume 3",
        0x0E,
    ),
    InformationScreenLine(
        "novel",
        0x000069E2,
        0x0C,
        "　　　　　商品概要：富士見ファンタジア文庫",
        "   Fantasia Bunko",
        "Media Mix novel imprint",
        0x10,
    ),
    InformationScreenLine(
        "novel",
        0x00006A10,
        0x0D,
        "　　　　　著　　者：遠藤明範",
        "   A. Endo",
        "Media Mix novel author",
        0x12,
    ),
    InformationScreenLine(
        "novel",
        0x00006A30,
        0x0E,
        "　　　　　発売元　：富士見書房（株）",
        "   Fujimi Shobo",
        "Media Mix novel publisher",
        0x14,
    ),
    InformationScreenLine(
        "novel",
        0x00006A58,
        0x0F,
        "　　　　　価　格　：５００円（税込み）",
        "   JPY 500 + Tax",
        "Media Mix novel price",
        0x16,
    ),
    InformationScreenLine(
        "novel",
        0x00006A83,
        0x16,
        "＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋",
        "   Now on Sale",
        "Media Mix novel availability",
        0x18,
    ),
    InformationScreenLine(
        "novel",
        0x00006AC3,
        0x17,
        (
            "＋" + "　" * 2 + "好" + "　" * 5 + "評"
            + "　" * 4 + "発" + "　" * 4 + "売"
            + "　" * 4 + "中" + "　" * 4 + "＋"
        ),
        "",
        "Media Mix novel superseded availability banner",
        INFORMATION_HIDDEN_ROW,
    ),
    InformationScreenLine(
        "novel",
        0x00006B03,
        0x18,
        "＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋",
        "",
        "Media Mix novel superseded footer line 1",
        INFORMATION_HIDDEN_ROW,
    ),
    InformationScreenLine(
        "novel",
        0x00006B43,
        0x1B,
        "＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃",
        "",
        "Media Mix novel superseded footer line 2",
        INFORMATION_HIDDEN_ROW,
    ),
    # Soundtrack and game-music compact discs.
    InformationScreenLine(
        "music",
        0x00006BC6,
        0x03,
        "　　　ＭＥＤＩＡ・ＭＩＸ・ＩＮＦＯＲＭＡＴＩＯＮ　　　　　　",
        "   MEDIA MIX INFORMATION",
        "Media Mix music heading",
    ),
    InformationScreenLine(
        "music",
        0x00006C09,
        0x06,
        "　　　　　　ＯＥＤＯ８０８関連商品ファイル　　　　　　　　　",
        "    OEDO 808 GUIDE",
        "Media Mix music guide heading",
    ),
    InformationScreenLine(
        "music",
        0x00006C4C,
        0x08,
        "　　　　　メディア：ミュージックＣＤ",
        "   Music CD",
        "Media Mix music format",
    ),
    InformationScreenLine(
        "music",
        0x00006C74,
        0x09,
        "　　　　　タイトル：追憶のコマンド（サントラ）",
        "   1: Memory Command",
        "Media Mix music soundtrack title",
        0x0A,
    ),
    InformationScreenLine(
        "music",
        0x00006CA6,
        0x0A,
        "　　　　　　　　　　クリミナルナイト（ゲーム音楽）",
        "   2: Criminal Night",
        "Media Mix music game title",
        0x0C,
    ),
    InformationScreenLine(
        "music",
        0x00006CDC,
        0x0D,
        "　　　　　商品概要：コンパクトディスク",
        "   Compact Disc",
        "Media Mix music presentation format",
        0x0E,
    ),
    InformationScreenLine(
        "music",
        0x00006D06,
        0x0E,
        "　　　　　発売元　：キングレコード（株）",
        "   King Records",
        "Media Mix music publisher",
        0x10,
    ),
    InformationScreenLine(
        "music",
        0x00006D32,
        0x0F,
        "　　　　　価　格　：２、０００円（税別）",
        "   JPY 2000 + Tax",
        "Media Mix music price",
        0x12,
    ),
    InformationScreenLine(
        "music",
        0x00006D5F,
        0x16,
        "＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋",
        "   Now on Sale",
        "Media Mix music availability",
        0x14,
    ),
    InformationScreenLine(
        "music",
        0x00006D9F,
        0x17,
        (
            "＋" + "　" * 2 + "好" + "　" * 5 + "評"
            + "　" * 4 + "発" + "　" * 4 + "売"
            + "　" * 4 + "中" + "　" * 4 + "＋"
        ),
        "",
        "Media Mix music superseded availability banner line 1",
        INFORMATION_HIDDEN_ROW,
    ),
    InformationScreenLine(
        "music",
        0x00006DDF,
        0x18,
        "＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋",
        "",
        "Media Mix music superseded availability banner line 2",
        INFORMATION_HIDDEN_ROW,
    ),
    InformationScreenLine(
        "music",
        0x00006E1F,
        0x1B,
        "＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃",
        "",
        "Media Mix music superseded footer",
        INFORMATION_HIDDEN_ROW,
    ),
)


# Each entry guards both structurally equivalent dossier banks. Record numbers
# and horizontal rules are already readable and remain byte-identical.
OPENING_PROFILE_FIELDS: tuple[OpeningProfileField, ...] = (
    OpeningProfileField(
        "chris",
        (0x00020C3B, 0x00060BD7),
        0x04,
        "氏名　　クリス・ダンフォード",
        "",
        "Japanese name",
        INFORMATION_HIDDEN_ROW,
    ),
    OpeningProfileField(
        "chris",
        (0x00020C5B, 0x00060BF7),
        0x05,
        "　　　　ＣＲＩＳ・ＤＡＮＦＯＲＤ",
        "CHRIS DANFORD",
        "English name",
        0x04,
    ),
    OpeningProfileField(
        "chris",
        (0x00020CAC, 0x00060C48),
        0x08,
        "出生地　都市外管轄区ＰＷ−２１",
        "ORIGIN: PW-21",
        "origin",
    ),
    OpeningProfileField(
        "chris",
        (0x00020CCE, 0x00060C6A),
        0x0A,
        "国籍　　不明",
        "NAT: ?",
        "nationality",
    ),
    OpeningProfileField(
        "chris",
        (0x00020CDE, 0x00060C7A),
        0x0C,
        "性別　　男：８３−１７",
        "SEX M:83-17",
        "sex and body ratio",
    ),
    OpeningProfileField(
        "chris",
        (0x00020CF8, 0x00060C94),
        0x0E,
        "年齢　　３２",
        "AGE 32",
        "age",
    ),
    OpeningProfileField(
        "chris",
        (0x00020D08, 0x00060CA4),
        0x10,
        "身長　　１７３Ｃｍ",
        "HT: 173CM",
        "height",
    ),
    OpeningProfileField(
        "chris",
        (0x00020D1E, 0x00060CBA),
        0x12,
        "体重　　６８Ｋｇ",
        "WT: 68KG",
        "weight",
    ),
    OpeningProfileField(
        "chris",
        (0x00020D32, 0x00060CCE),
        0x14,
        "罪状　　電磁爆弾魔",
        "EM BOMBER",
        "charge",
    ),
    OpeningProfileField(
        "chris",
        (0x00020D48, 0x00060CE4),
        0x15,
        "　　　　　（電脳都市治安維持法違反）",
        "CYBER CITY LAW",
        "charge continuation",
        0x16,
    ),
    OpeningProfileField(
        "chris",
        (0x00020D70, 0x00060D0C),
        0x17,
        "通称　　『バラ発疹』",
        "ROSE RASH",
        "alias",
        0x18,
    ),
    OpeningProfileField(
        "chris",
        (0x00020D88, 0x00060D24),
        0x19,
        "賞金額　￥１２、５００、０００−",
        "B$12,500,000",
        "bounty",
        0x1A,
    ),
    OpeningProfileField(
        "kenichi",
        (0x00020DFD, 0x00060D95),
        0x04,
        "氏名　　氏名：ケニチ・ギヤナ",
        "",
        "Japanese name",
        INFORMATION_HIDDEN_ROW,
    ),
    OpeningProfileField(
        "kenichi",
        (0x00020E1D, 0x00060DB5),
        0x05,
        "　　　　ＫＥＮＩＣＨ・ＧＩＹＡＮＮＡ",
        "KENICHI GIYANNA",
        "English name",
        0x04,
    ),
    OpeningProfileField(
        "kenichi",
        (0x00020E72, 0x00060E0A),
        0x08,
        "出生地　グーンマ・ＣＩＴＹ４２４",
        "ORIGIN GUNMA-424",
        "origin",
    ),
    OpeningProfileField(
        "kenichi",
        (0x00020E96, 0x00060E2E),
        0x0A,
        "国籍　　日本",
        "JAPAN",
        "nationality",
    ),
    OpeningProfileField(
        "kenichi",
        (0x00020EA6, 0x00060E3E),
        0x0C,
        "性別　　男：８６−１４",
        "SEX M:86-14",
        "sex and body ratio",
    ),
    OpeningProfileField(
        "kenichi",
        (0x00020EC0, 0x00060E58),
        0x0E,
        "年齢　　２１",
        "AGE 21",
        "age",
    ),
    OpeningProfileField(
        "kenichi",
        (0x00020ED0, 0x00060E68),
        0x10,
        "身長　　１６６Ｃｍ",
        "HT: 166CM",
        "height",
    ),
    OpeningProfileField(
        "kenichi",
        (0x00020EE6, 0x00060E7E),
        0x12,
        "体重　　５８Ｋｇ",
        "WT: 58KG",
        "weight",
    ),
    OpeningProfileField(
        "kenichi",
        (0x00020EFA, 0x00060E92),
        0x14,
        "罪状　　コンピュータウィルス取締法違反",
        "COMPUTER VIRUS LAW",
        "charge",
    ),
    OpeningProfileField(
        "kenichi",
        (0x00020F24, 0x00060EBC),
        0x16,
        "通称　　『ＫＫベストキラーズ』",
        "KK BEST KILLERS",
        "alias",
    ),
    OpeningProfileField(
        "kenichi",
        (0x00020F46, 0x00060EDE),
        0x18,
        "賞金額　２３４，９００−",
        "B$234,900",
        "bounty",
    ),
    OpeningProfileField(
        "jun",
        (0x00020FB3, 0x00060F47),
        0x04,
        "氏名　　ジュン・本山",
        "",
        "Japanese name",
        INFORMATION_HIDDEN_ROW,
    ),
    OpeningProfileField(
        "jun",
        (0x00020FCB, 0x00060F5F),
        0x05,
        "　　　　ＪＵＮ・ＭＯＴＯＹＡＭＡ",
        "JUN MOTOYAMA",
        "English name",
        0x04,
    ),
    OpeningProfileField(
        "jun",
        (0x0002101C, 0x00060FB0),
        0x08,
        "出生地　マタイサＭＤ−７５３Ａ",
        "MATAISA MD-753A",
        "origin",
    ),
    OpeningProfileField(
        "jun",
        (0x0002103E, 0x00060FD2),
        0x0A,
        "国籍　　韓国",
        "KOREA",
        "nationality",
    ),
    OpeningProfileField(
        "jun",
        (0x0002104E, 0x00060FE2),
        0x0C,
        "性別　　男：５１−４９",
        "SEX M:51-49",
        "sex and body ratio",
    ),
    OpeningProfileField(
        "jun",
        (0x00021068, 0x00060FFC),
        0x0E,
        "年齢　　２４",
        "AGE 24",
        "age",
    ),
    OpeningProfileField(
        "jun",
        (0x00021078, 0x0006100C),
        0x10,
        "身長　　１６９Ｃｍ",
        "HT: 169CM",
        "height",
    ),
    OpeningProfileField(
        "jun",
        (0x0002108E, 0x00061022),
        0x12,
        "体重　　６９．５Ｋｇ",
        "WT: 69.5KG",
        "weight",
    ),
    OpeningProfileField(
        "jun",
        (0x000210A6, 0x0006103A),
        0x14,
        "罪状　　美少女プロテロイド密造販売",
        "BOOTLEG GIRL BOTS",
        "charge",
    ),
    OpeningProfileField(
        "jun",
        (0x000210CC, 0x00061060),
        0x16,
        "通称　　『マニアックＡＭＴ』",
        "MANIAC AMT",
        "alias",
    ),
    OpeningProfileField(
        "jun",
        (0x000210EC, 0x00061080),
        0x18,
        "賞金額　￥５、０１０、０００−",
        "B$5,010,000",
        "bounty",
    ),
    OpeningProfileField(
        "manny",
        (0x0002115F, 0x000610EF),
        0x04,
        "氏名　　マニー・斉藤",
        "",
        "Japanese name",
        INFORMATION_HIDDEN_ROW,
    ),
    OpeningProfileField(
        "manny",
        (0x00021177, 0x00061107),
        0x05,
        "　　　　ＭＡＮＮＹ・ＳＡＩＴＯＨ",
        "MANNY SAITOH",
        "English name",
        0x04,
    ),
    OpeningProfileField(
        "manny",
        (0x000211C8, 0x00061158),
        0x08,
        "出生地　ノ−ス・シー・ウェイ−モハ６０３",
        "N. SEAWAY MOHA-603",
        "origin",
    ),
    OpeningProfileField(
        "manny",
        (0x000211F4, 0x00061184),
        0x0A,
        "国籍　　パプアニューギニア",
        "PAPUA N.G.",
        "nationality",
    ),
    OpeningProfileField(
        "manny",
        (0x00021212, 0x000611A2),
        0x0C,
        "性別　　男：９０−１０",
        "SEX M:90-10",
        "sex and body ratio",
    ),
    OpeningProfileField(
        "manny",
        (0x0002122C, 0x000611BC),
        0x0E,
        "年齢　　３５",
        "AGE 35",
        "age",
    ),
    OpeningProfileField(
        "manny",
        (0x0002123C, 0x000611CC),
        0x10,
        "身長　　１６８Ｃｍ",
        "HT: 168CM",
        "height",
    ),
    OpeningProfileField(
        "manny",
        (0x00021252, 0x000611E2),
        0x12,
        "体重　　８７Ｋｇ",
        "WT: 87KG",
        "weight",
    ),
    OpeningProfileField(
        "manny",
        (0x00021266, 0x000611F6),
        0x14,
        "罪状　　Ｐ．Ｅ衛星ネットワーク爆破",
        "P.E. SATNET BOMB",
        "charge",
    ),
    OpeningProfileField(
        "manny",
        (0x0002128C, 0x0006121C),
        0x16,
        "通称　　『蒼ざめた牙』",
        "PALE FANG",
        "alias",
    ),
    OpeningProfileField(
        "manny",
        (0x000212A6, 0x00061236),
        0x18,
        "賞金額　￥１０，２８０，０００−",
        "B$10,280,000",
        "bounty",
    ),
    OpeningProfileField(
        "sanemaro",
        (0x0002131B, 0x000612A7),
        0x04,
        "氏名　　実麿・光雄",
        "",
        "Japanese name",
        INFORMATION_HIDDEN_ROW,
    ),
    OpeningProfileField(
        "sanemaro",
        (0x00021331, 0x000612BD),
        0x05,
        "　　　　ＳＡＮＥＭＡＲＯ・ＭＩＴＳＵＯ",
        "SANEMARO MITSUO",
        "English name",
        0x04,
    ),
    OpeningProfileField(
        "sanemaro",
        (0x00021388, 0x00061314),
        0x08,
        "出生地　日本−旧市街管轄区Ｃ−８７",
        "OLD CITY C-87",
        "origin",
    ),
    OpeningProfileField(
        "sanemaro",
        (0x000213AE, 0x0006133A),
        0x0A,
        "国籍　　日本",
        "JAPAN",
        "nationality",
    ),
    OpeningProfileField(
        "sanemaro",
        (0x000213BE, 0x0006134A),
        0x0C,
        "性別　　男：９２−８",
        "SEX M:92-8",
        "sex and body ratio",
    ),
    OpeningProfileField(
        "sanemaro",
        (0x000213D6, 0x00061362),
        0x0E,
        "年齢　　４３",
        "AGE 43",
        "age",
    ),
    OpeningProfileField(
        "sanemaro",
        (0x000213E6, 0x00061372),
        0x10,
        "身長　　１８２Ｃｍ",
        "HT: 182CM",
        "height",
    ),
    OpeningProfileField(
        "sanemaro",
        (0x000213FC, 0x00061388),
        0x12,
        "体重　　７９Ｋｇ",
        "WT: 79KG",
        "weight",
    ),
    OpeningProfileField(
        "sanemaro",
        (0x00021410, 0x0006139C),
        0x14,
        "罪状　　無差別殺人",
        "MASS KILL",
        "charge",
    ),
    OpeningProfileField(
        "sanemaro",
        (0x00021426, 0x000613B2),
        0x16,
        "通称　　『コペンハーゲンの雄羊』",
        "COPENHAGEN RAM",
        "alias",
    ),
    OpeningProfileField(
        "sanemaro",
        (0x0002144A, 0x000613D6),
        0x18,
        "賞金額　￥４２，８００，９００−",
        "B$42,800,900",
        "bounty",
    ),
    OpeningProfileField(
        "benten",
        (0x000214BD, 0x00061445),
        0x04,
        "氏名　　メリル・柳川",
        "",
        "Japanese name",
        INFORMATION_HIDDEN_ROW,
    ),
    OpeningProfileField(
        "benten",
        (0x000214D5, 0x0006145D),
        0x05,
        "　　　　ＭＥＲＩＬＬ・ＹＡＮＡＧＡＷＡ",
        "MERILL YANAGAWA",
        "English name",
        0x04,
    ),
    OpeningProfileField(
        "benten",
        (0x0002152C, 0x000614B4),
        0x08,
        "出生地　地球外管轄区Ｄ−６、エルシオン区",
        "OFFWORLD D-6 ELYSION",
        "origin",
    ),
    OpeningProfileField(
        "benten",
        (0x00021558, 0x000614E0),
        0x0A,
        "国籍　　不明",
        "NAT: ?",
        "nationality",
    ),
    OpeningProfileField(
        "benten",
        (0x00021568, 0x000614F0),
        0x0C,
        "性別　　男：６８−３２",
        "SEX M:68-32",
        "sex and body ratio",
    ),
    OpeningProfileField(
        "benten",
        (0x00021582, 0x0006150A),
        0x0E,
        "年齢　　２３",
        "AGE 23",
        "age",
    ),
    OpeningProfileField(
        "benten",
        (0x00021592, 0x0006151A),
        0x10,
        "身長　　１７８Ｃｍ",
        "HT: 178CM",
        "height",
    ),
    OpeningProfileField(
        "benten",
        (0x000215A8, 0x00061530),
        0x12,
        "体重　　５８Ｋｇ",
        "WT: 58KG",
        "weight",
    ),
    OpeningProfileField(
        "benten",
        (0x000215BC, 0x00061544),
        0x14,
        "罪状　　コンピューターレイド",
        "COMPUTER RAID",
        "charge",
    ),
    OpeningProfileField(
        "benten",
        (0x000215DC, 0x00061564),
        0x15,
        "　　　　　（データベース保護法違反）",
        "DATABASE LAW",
        "charge continuation",
        0x16,
    ),
    OpeningProfileField(
        "benten",
        (0x00021604, 0x0006158C),
        0x17,
        "通称　　『ベンテン』",
        "BENTEN",
        "alias",
        0x18,
    ),
    OpeningProfileField(
        "benten",
        (0x0002161C, 0x000615A4),
        0x19,
        "賞金額　￥８９、２００、０００−",
        "B$89,200,000",
        "bounty",
        0x1A,
    ),
    OpeningProfileField(
        "gogul",
        (0x0002168F, 0x00061613),
        0x04,
        "氏名　　蛾眉丸・力也",
        "",
        "Japanese name",
        INFORMATION_HIDDEN_ROW,
    ),
    OpeningProfileField(
        "gogul",
        (0x000216A7, 0x0006162B),
        0x05,
        "　　　　ＧＡＢＩＭＡＲＵ・ＲＩＫＩＹＡ",
        "GABIMARU RIKIYA",
        "English name",
        0x04,
    ),
    OpeningProfileField(
        "gogul",
        (0x000216FE, 0x00061682),
        0x08,
        "出生地　海上都市ＰＸ−７３",
        "OCEAN PX-73",
        "origin",
    ),
    OpeningProfileField(
        "gogul",
        (0x0002171C, 0x000616A0),
        0x0A,
        "国籍　　公海",
        "NONE",
        "nationality",
    ),
    OpeningProfileField(
        "gogul",
        (0x0002172C, 0x000616B0),
        0x0C,
        "性別　　男：９２−１８",
        "SEX M:92-18",
        "sex and body ratio",
    ),
    OpeningProfileField(
        "gogul",
        (0x00021746, 0x000616CA),
        0x0E,
        "年齢　　２８",
        "AGE 28",
        "age",
    ),
    OpeningProfileField(
        "gogul",
        (0x00021756, 0x000616DA),
        0x10,
        "身長　　２０２Ｃｍ",
        "HT: 202CM",
        "height",
    ),
    OpeningProfileField(
        "gogul",
        (0x0002176C, 0x000616F0),
        0x12,
        "体重　　１２３Ｋｇ",
        "WT: 123KG",
        "weight",
    ),
    OpeningProfileField(
        "gogul",
        (0x00021782, 0x00061706),
        0x14,
        "罪状　　メカニックジャック",
        "MECHA HIJACK",
        "charge",
    ),
    OpeningProfileField(
        "gogul",
        (0x000217A0, 0x00061724),
        0x15,
        "　　　　　　　（Ｍ．Ｃ．規制法違反）",
        "M.C. CONTROL LAW",
        "charge continuation",
        0x16,
    ),
    OpeningProfileField(
        "gogul",
        (0x000217C8, 0x0006174C),
        0x17,
        "通称　　『ゴーグル、モス・ゴング』",
        "GOGUL",
        "alias",
        0x18,
        "通称　　『ゴーグル』",
    ),
    OpeningProfileField(
        "gogul",
        (0x000217EE, 0x00061764),
        0x19,
        "賞金額　￥８６、４００、０００−",
        "B$86,400,000",
        "bounty",
        0x1A,
    ),
)


OPENING_PROFILE_TEXT_PATCHES = tuple(
    patch
    for field in OPENING_PROFILE_FIELDS
    for patch in field.to_text_patches()
)
OPENING_PROFILE_LAYOUT_PATCHES = tuple(
    patch
    for field in OPENING_PROFILE_FIELDS
    for patch in field.to_layout_patches()
)


INFORMATION_SCREEN_TEXT_PATCHES = tuple(
    line.to_text_patch()
    for line in INFORMATION_SCREEN_LINES
)
INFORMATION_SCREEN_LAYOUT_PATCHES = tuple(
    layout_patch
    for line in INFORMATION_SCREEN_LINES
    if (layout_patch := line.to_layout_patch()) is not None
)


# The aggregate profile is deliberately explicit so its exact scope appears
# in tests, console output, and the generated build manifest.
HUMAN_TEST_PATCHES = (
    BOOT_MENU_PATCHES
    + STARTUP_V2_EXTRA_PATCHES
    + MISSION_TITLE_PATCHES
    + MISSION0_DIALOGUE_PATCHES
    + MISSION0_PROLOGUE_PATCHES
    + OPENING_PROFILE_TEXT_PATCHES
    + INFORMATION_SCREEN_TEXT_PATCHES
)


# The stock-renderer profile must not patch parser, glyph, cursor, or
# punctuation code. Keeping the empty collection explicit makes that contract
# visible to tests, manifests, and downstream builders.
MISSION0_RENDERER_PATCHES: tuple[PayloadPatch, ...] = ()


HUMAN_TEST_BINARY_PATCHES = (
    OPENING_PROFILE_LAYOUT_PATCHES
    + INFORMATION_SCREEN_LAYOUT_PATCHES
)


def optional_title_screen_patches(
    source_image: pathlib.Path,
    mode: str,
) -> tuple[PayloadPatch, ...]:
    """Build the isolated optional opening-title and palette replacements.

    Args:
        source_image: Authenticated raw CloneCD IMG used to obtain the original
            title bytes for the guarded patch.
        mode: ``"clean"`` to generate the replacement or ``"original"`` to
            leave the title payload untouched.

    Returns:
        Two same-size patches in clean mode: one seven-frame grayscale palette
        cycle and one title-screen tile block. Original mode returns an empty
        tuple.

    Raises:
        OSError: If the clean mode cannot read the source image.
        ValueError: If the mode is unsupported or the title block differs
            from the analyzed release.

    Side Effects:
        Clean mode reads and validates the palette cycle and 15 title sectors.
        Original mode does not open the image.

    Design Decisions:
        Original bytes are read from the user's authenticated disc rather than
        committed to this open-source repository. Independent palette and
        graphic hashes prevent valid-size but wrong source data from becoming
        unsafe guards. The portrait palette at ``0x2828`` is outside the
        patched range. Returning no patch in original mode makes opt-out
        behavior explicit: translation and layout patches remain otherwise
        identical.
    """

    if mode not in TITLE_SCREEN_MODES:
        raise ValueError(
            f"title screen must be one of {TITLE_SCREEN_MODES}, found {mode!r}"
        )
    if mode == "original":
        return ()

    original_palette = read_payload_range(
        source_image,
        TITLE_PALETTE_OFFSET,
        TITLE_PALETTE_BYTES,
        start_lba=TRACK2_START_LBA,
        sector_count=TRACK2_SECTOR_COUNT,
    )
    palette_digest = hashlib.sha256(original_palette).hexdigest()
    if palette_digest != TITLE_PALETTE_SOURCE_SHA256:
        raise ValueError(
            "opening title palette differs from the analyzed release: "
            f"expected {TITLE_PALETTE_SOURCE_SHA256}, "
            f"found {palette_digest}"
        )
    original = read_payload_range(
        source_image,
        TITLE_SCREEN_OFFSET,
        TITLE_ASSET_BYTES,
        start_lba=TRACK2_START_LBA,
        sector_count=TRACK2_SECTOR_COUNT,
    )
    digest = hashlib.sha256(original).hexdigest()
    if digest != TITLE_SCREEN_SOURCE_SHA256:
        raise ValueError(
            "opening title graphic differs from the analyzed release: "
            f"expected {TITLE_SCREEN_SOURCE_SHA256}, found {digest}"
        )
    replacement = build_clean_title_asset()
    return (
        PayloadPatch(
            offset=TITLE_PALETTE_OFFSET,
            expected=original_palette,
            replacement=build_grayscale_title_palette_cycle(),
            label="optional antialiased opening title palette",
        ),
        PayloadPatch(
            offset=TITLE_SCREEN_OFFSET,
            expected=original,
            replacement=replacement,
            label="optional antialiased opening title graphic",
        ),
    )


def relative_sectors_for_patches(
    patches: tuple[PayloadPatch, ...],
) -> set[int]:
    """Return every payload sector intersected by guarded patches.

    Args:
        patches: Same-size payload patches in any order.

    Returns:
        Set of relative 2048-byte sector indexes. An empty patch tuple returns
        an empty set.

    Notes:
        Counting the complete span matters for large graphic replacements;
        using only each patch's starting sector would under-report the title
        patch by 14 sectors.
    """

    sectors: set[int] = set()
    for patch in patches:
        first_sector = patch.offset // SECTOR_SIZE
        last_sector = (patch.end_offset - 1) // SECTOR_SIZE
        sectors.update(range(first_sector, last_sector + 1))
    return sectors


def profile_relative_sectors(title_screen_mode: str) -> tuple[int, ...]:
    """Return payload sectors guarded by one build variant.

    Args:
        title_screen_mode: ``"clean"`` or ``"original"``.

    Returns:
        Sorted relative sector indexes for all text, layout, and
        optional title-screen patches. A guarded sector can remain
        byte-identical when its source and replacement slices already match.

    Raises:
        ValueError: If the requested title-screen mode is unsupported.

    Design Decisions:
        This source-independent helper describes the patch footprint without
        retaining the 30,720 source bytes used by the title guard. The
        completed build manifest remains authoritative for sectors that
        actually differ.
    """

    if title_screen_mode not in TITLE_SCREEN_MODES:
        raise ValueError(
            "title screen must be clean or original"
        )
    patches = (
        tuple(
            text_patch.to_payload_patch()
            for text_patch in HUMAN_TEST_PATCHES
        )
        + HUMAN_TEST_BINARY_PATCHES
    )
    sectors = relative_sectors_for_patches(patches)
    if title_screen_mode == "clean":
        for offset, byte_count in (
            (TITLE_PALETTE_OFFSET, TITLE_PALETTE_BYTES),
            (TITLE_SCREEN_OFFSET, TITLE_ASSET_BYTES),
        ):
            first_sector = offset // SECTOR_SIZE
            last_sector = (offset + byte_count - 1) // SECTOR_SIZE
            sectors.update(range(first_sector, last_sector + 1))
    return tuple(sorted(sectors))


def wrap_ascii_text(text: str, width: int) -> str:
    """Flatten word-wrapped ASCII into fixed-width display cells.

    The original renderer advances automatically after ``width`` fullwidth
    cells. This function pads each non-final line to that boundary, making the
    existing character wrap occur between words without inserting an unknown
    dialogue control.

    Args:
        text: Single-spaced printable ASCII wording without leading or trailing
            whitespace.
        width: Positive number of fullwidth display cells per rendered line.

    Returns:
        ASCII text whose non-final visual lines are right-padded to ``width``.
        No newline or dialogue-control bytes are introduced.

    Raises:
        ValueError: If ``width`` is not positive, text spacing is not
            canonical, or a word is wider than one line.

    Design Decisions:
        This formatter is intentionally limited to the observed fixed-cell
        path. Longer accurate English belongs in mapped relocated records with
        explicit page breaks.
    """

    if width <= 0:
        raise ValueError("wrap width must be positive")
    words = text.split(" ")
    if not text or text.strip() != text or any(not word for word in words):
        raise ValueError(
            "wrapped English must use single internal spaces"
        )
    too_wide = [word for word in words if len(word) > width]
    if too_wide:
        raise ValueError(
            f"word exceeds {width}-cell line: {too_wide[0]!r}"
        )

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
            continue
        lines.append(current.ljust(width))
        current = word
    lines.append(current)
    return "".join(lines)


def ascii_to_fullwidth(text: str) -> str:
    """Convert printable ASCII to fullwidth Unicode equivalents.

    Args:
        text: Printable ASCII text. Ordinary spaces become ideographic spaces.

    Returns:
        Fullwidth text whose characters encode as two-byte Shift-JIS glyphs.

    Raises:
        ValueError: If ``text`` contains a character outside space through
            tilde.

    Design Decisions:
        Converting every printable character keeps the game's low-byte control
        range out of the replacement and preserves two bytes per glyph. ASCII
        hyphen maps to the Shift-JIS minus glyph and apostrophe maps to the
        right single quotation mark because U+FF0D and U+FF07 are not present
        in Python's strict ``shift_jis`` codec.
    """

    converted: list[str] = []
    for character in text:
        codepoint = ord(character)
        if character == " ":
            converted.append("\u3000")
        elif character == "-":
            converted.append("\u2212")
        elif character == "'":
            converted.append("\u2019")
        elif 0x21 <= codepoint <= 0x7E:
            converted.append(chr(codepoint + 0xFEE0))
        else:
            raise ValueError(
                f"unsupported non-printable ASCII character {character!r}"
            )
    return "".join(converted)


def hash_file(path: pathlib.Path) -> str:
    """Return a file's lowercase SHA-256 digest.

    Args:
        path: File to read.

    Returns:
        Lowercase hexadecimal SHA-256 digest.

    Raises:
        OSError: If the file cannot be opened or read.
    """

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_source_set(
    source_ccd: pathlib.Path,
) -> dict[str, pathlib.Path]:
    """Resolve and authenticate the three source CloneCD files.

    Args:
        source_ccd: Path to the source ``.ccd`` descriptor.

    Returns:
        A mapping from lowercase extension to resolved CCD, IMG, and SUB paths.

    Raises:
        OSError: If a source file cannot be read while hashing.
        ValueError: If the descriptor extension is wrong, a companion file is
            missing, or any file hash differs from the analyzed release.
    """

    source_ccd = source_ccd.resolve()
    if source_ccd.suffix.lower() != ".ccd":
        raise ValueError("source path must name a .ccd file")
    paths = {
        extension: source_ccd.with_suffix(extension)
        for extension in SOURCE_HASHES
    }
    for extension, path in paths.items():
        if not path.is_file():
            raise ValueError(
                f"missing CloneCD companion {extension}: {path}"
            )
        actual = hash_file(path)
        expected = SOURCE_HASHES[extension]
        if actual != expected:
            raise ValueError(
                f"{path.name}: SHA-256 mismatch; expected {expected}, "
                f"found {actual}"
            )
    return paths


def compare_raw_images(
    source_image: pathlib.Path,
    output_image: pathlib.Path,
) -> tuple[int, ...]:
    """Return every raw sector that differs between two same-size images.

    Args:
        source_image: Immutable source CloneCD IMG.
        output_image: Patched CloneCD IMG.

    Returns:
        Absolute zero-based raw-sector indexes whose 2352-byte contents differ.

    Raises:
        OSError: If file metadata or reads fail.
        ValueError: If sizes differ, are not raw-sector aligned, or a read is
            incomplete.
    """

    source_size = source_image.stat().st_size
    output_size = output_image.stat().st_size
    if source_size != output_size:
        raise ValueError(
            f"IMG size changed: {source_size:,} != {output_size:,}"
        )
    if source_size % RAW_SECTOR_SIZE:
        raise ValueError("IMG size is not divisible by 2352")

    changed: list[int] = []
    sector_count = source_size // RAW_SECTOR_SIZE
    with source_image.open("rb") as source, output_image.open("rb") as output:
        for absolute_lba in range(sector_count):
            source_sector = source.read(RAW_SECTOR_SIZE)
            output_sector = output.read(RAW_SECTOR_SIZE)
            if (
                len(source_sector) != RAW_SECTOR_SIZE
                or len(output_sector) != RAW_SECTOR_SIZE
            ):
                raise ValueError(
                    f"short image read at absolute LBA {absolute_lba}"
                )
            if source_sector != output_sector:
                changed.append(absolute_lba)
    return tuple(changed)


def verify_output_text(
    output_image: pathlib.Path,
    patches: tuple[PayloadPatch, ...],
) -> None:
    """Verify every replacement directly in the patched raw image.

    Args:
        output_image: Patched CloneCD IMG.
        patches: Same-size payload patches expected in the image.

    Raises:
        OSError: If image seeks or reads fail.
        ValueError: If a raw sector is structurally invalid or replacement
            bytes do not match.

    Notes:
        The missing-file message crosses from payload sector 3 into sector 4.
        Verification therefore follows the same payload-coordinate model as
        the patcher instead of reading replacements as contiguous IMG bytes.
    """

    with output_image.open("rb") as image:
        for patch in patches:
            checked = 0
            while checked < len(patch.replacement):
                payload_position = patch.offset + checked
                relative_sector = payload_position // SECTOR_SIZE
                within_sector = payload_position % SECTOR_SIZE
                chunk_size = min(
                    len(patch.replacement) - checked,
                    SECTOR_SIZE - within_sector,
                )
                absolute_lba = TRACK2_START_LBA + relative_sector
                image.seek(absolute_lba * RAW_SECTOR_SIZE)
                raw = image.read(RAW_SECTOR_SIZE)
                if len(raw) != RAW_SECTOR_SIZE:
                    raise ValueError(
                        f"short read at absolute LBA {absolute_lba}"
                    )
                if raw[: len(MODE1_SYNC)] != MODE1_SYNC or raw[15] != 1:
                    raise ValueError(
                        f"invalid Mode 1 sector at LBA {absolute_lba}"
                    )
                start = MODE1_USER_DATA_OFFSET + within_sector
                end = start + chunk_size
                expected = patch.replacement[
                    checked:checked + chunk_size
                ]
                if raw[start:end] != expected:
                    raise ValueError(
                        f"{patch.label}: output verification failed"
                    )
                checked += chunk_size


def build_tester_readme(ccd_name: str, title_screen_mode: str) -> str:
    """Return the human-testing instructions included beside the image.

    Args:
        ccd_name: Filename testers should open in an emulator.
        title_screen_mode: Selected ``"clean"`` or ``"original"`` variant.

    Returns:
        Plain-text instructions with scope, boot steps, visible proof, and
        limitations.

    Raises:
        ValueError: If the title-screen mode is unsupported.
    """

    if title_screen_mode not in TITLE_SCREEN_MODES:
        raise ValueError("title screen must be clean or original")
    title_expectation = (
        (
            "- The opening uses the antialiased generated title graphic "
            "and artifact-safe grayscale palette."
        )
        if title_screen_mode == "clean"
        else "- The opening retains the original title graphic."
    )
    lines = [
        "Cyber City Oedo 808 - Stock Renderer Test",
        "===========================================",
        "",
        "Purpose",
        "-------",
        "This is a same-size Shift-JIS Mission 0 vertical slice.",
        "It is not a complete English translation.",
        "",
        "How to boot",
        "-----------",
        f"1. Keep the CCD, IMG, and SUB together.",
        f"2. Open this descriptor in a PC Engine CD emulator: {ccd_name}",
        "3. Use a legally obtained Japanese System Card 3.0 BIOS.",
        "4. Do not rename only one member of the CloneCD set.",
        "",
        "Expected visible proof",
        "----------------------",
        "- The first notice heading reads TEST DISC.",
        title_expectation,
        "- The clean title subtitle reads ATTRIBUTE OF THE BEAST.",
        "- The notice identifies a HUMAN TEST BUILD.",
        "- Startup, load, and memory prompts use fullwidth English.",
        "- Mission 1 through Mission 8 title subtitles use English.",
        "- Both banks of all seven opening criminal profiles use English.",
        "- Profile text uses non-overlapping 16-pixel row spacing.",
        "- The opening Mission 0 bartender conversation uses English.",
        "- Sengoku's complete ten-page opening narration uses English.",
        "- All three Media Mix merchandise pages use readable English.",
        "- Merchandise lines use non-overlapping 16-pixel row spacing.",
        "- Mission 0 dialogue uses lowercase letters.",
        "- Narration words wrap on the renderer's 11-cell grid.",
        "- English punctuation stays inside the ordinary 11-cell limit.",
        "- Most other dialogue and interfaces remain Japanese.",
        "",
        "Human test checklist",
        "--------------------",
        "- Boot through the initial notice.",
        "- Start a new game and reach playable Mission 0.",
        "- Return to or reopen the startup menu.",
        "- Exercise DATA LOAD with and without a save.",
        "- Exercise MEMORYCHECK.",
        "- Confirm audio begins and later CD audio still plays.",
        "- Save when the game permits it, restart, and reload.",
        (
            "- Record emulator name/version, BIOS hash, screenshots, "
            "and failures."
        ),
        "",
        "Technical scope",
        "---------------",
        "- Source CCD and SUB are copied byte-for-byte.",
        "- The manifest lists every changed Track 2 payload sector.",
        "- Raw Mode 1 EDC and ECC are regenerated for changed sectors.",
        (
            "- Track starts, pregaps, audio sectors, and subchannels "
            "are unchanged."
        ),
        "",
        "Known limitations",
        "-----------------",
        "- English is fullwidth 16x16 text using the existing BIOS font path.",
        "- The existing renderer still fits only 11 fullwidth cells per line.",
        "- No parser, glyph, cursor, or punctuation code is patched.",
        "- Accurate longer English requires mapped relocation and more pages.",
        (
            "- The title graphic is an optional cosmetic patch; use "
            "--title-screen original to omit it."
        ),
        (
            "- Media Mix row operands change only to separate 16-pixel "
            "glyphs."
        ),
        "- No pointer, string length, or record terminator is changed.",
        (
            "- Structural validation passed; emulator behavior needs "
            "human testing."
        ),
        "",
        "See build_manifest.json for hashes and exact replacements.",
        "",
    ]
    return "\n".join(lines)


def _copy_clonecd_set(
    source_paths: dict[str, pathlib.Path],
    temporary_directory: pathlib.Path,
) -> dict[str, pathlib.Path]:
    """Copy the authenticated source set under the test-build stem.

    Args:
        source_paths: Mapping returned by ``resolve_source_set``.
        temporary_directory: Empty isolated build directory.

    Returns:
        Mapping from extension to copied output path.

    Raises:
        OSError: If any file copy fails.

    Side Effects:
        Copies the source CCD, IMG, and SUB into ``temporary_directory``.
    """

    outputs: dict[str, pathlib.Path] = {}
    for extension, source in source_paths.items():
        destination = temporary_directory / f"{OUTPUT_STEM}{extension}"
        shutil.copy2(source, destination)
        outputs[extension] = destination
    return outputs


def _manifest_patch_rows(
    text_patches: tuple[InPlaceTextPatch, ...],
) -> list[dict[str, Any]]:
    """Serialize exact text-replacement evidence for the build manifest.

    Args:
        text_patches: Profile patches in payload order.

    Returns:
        JSON-serializable rows containing coordinates, labels, text, and byte
        counts.
    """

    rows: list[dict[str, Any]] = []
    for patch in text_patches:
        payload_patch = patch.to_payload_patch()
        relative_sector = patch.offset // SECTOR_SIZE
        rows.append(
            {
                "purpose": patch.purpose,
                "payload_offset": f"0x{patch.offset:08X}",
                "relative_sector": relative_sector,
                "absolute_lba": TRACK2_START_LBA + relative_sector,
                "source_text": patch.source_text,
                "english": patch.english,
                "wrap_width": patch.wrap_width,
                "formatted_english": patch.formatted_english,
                "replacement_text": patch.replacement_text,
                "bytes": len(payload_patch.expected),
            }
        )
    return rows


def _manifest_binary_patch_rows(
    binary_patches: tuple[PayloadPatch, ...],
) -> list[dict[str, Any]]:
    """Serialize guarded binary-patch evidence for the build manifest.

    Args:
        binary_patches: Guarded non-text payload patches in application order.

    Returns:
        JSON-serializable rows containing coordinates, labels, sizes, and
        SHA-256 identities. Patches no larger than 64 bytes also include exact
        before/after hexadecimal bytes.

    Design Decisions:
        Inline bytes are ideal for reviewing small machine-code and operand
        patches. Hashing larger generated art keeps the manifest useful
        without adding roughly 120 KiB of hexadecimal source and replacement
        data.
    """

    rows: list[dict[str, Any]] = []
    for patch in binary_patches:
        relative_sector = patch.offset // SECTOR_SIZE
        row = {
            "purpose": patch.label,
            "payload_offset": f"0x{patch.offset:08X}",
            "relative_sector": relative_sector,
            "absolute_lba": TRACK2_START_LBA + relative_sector,
            "expected_sha256": hashlib.sha256(
                patch.expected
            ).hexdigest(),
            "replacement_sha256": hashlib.sha256(
                patch.replacement
            ).hexdigest(),
            "bytes": len(patch.expected),
        }
        if len(patch.expected) <= MANIFEST_INLINE_BINARY_LIMIT:
            row["expected_hex"] = patch.expected.hex(" ")
            row["replacement_hex"] = patch.replacement.hex(" ")
        rows.append(row)
    return rows


def build_human_test_disc(
    source_ccd: pathlib.Path,
    output_directory: pathlib.Path,
    *,
    title_screen_mode: str = DEFAULT_TITLE_SCREEN_MODE,
) -> pathlib.Path:
    """Build and verify the stock-renderer CloneCD test set.

    Args:
        source_ccd: Authenticated source CloneCD descriptor.
        output_directory: New directory that will receive the completed set.
        title_screen_mode: ``"clean"`` for the generated replacement or
            ``"original"`` to omit that cosmetic patch.

    Returns:
        Final output CCD path that a tester should open.

    Raises:
        OSError: If hashing, copying, patching, verification, writing, cleanup,
            or final directory replacement fails.
        ValueError: If source identity, output state, patch constraints, sector
            integrity, or whole-image comparison fails.

    Side Effects:
        Creates ``output_directory.parent``. Builds in an isolated temporary
        directory, removes that directory after failure, and renames it to the
        requested destination only after every verification passes.
    """

    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise ValueError(
            f"output directory already exists: {output_directory}"
        )
    source_paths = resolve_source_set(source_ccd)
    title_screen_patches = optional_title_screen_patches(
        source_paths[".img"],
        title_screen_mode,
    )
    text_payload_patches = tuple(
        patch.to_payload_patch()
        for patch in HUMAN_TEST_PATCHES
    )
    binary_patches = HUMAN_TEST_BINARY_PATCHES + title_screen_patches
    payload_patches = text_payload_patches + binary_patches

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = pathlib.Path(
        tempfile.mkdtemp(
            dir=output_directory.parent,
            prefix=f".{output_directory.name}.",
        )
    )
    try:
        output_paths = _copy_clonecd_set(source_paths, temporary)
        sector_reports = apply_payload_patches(
            output_paths[".img"],
            payload_patches,
            start_lba=TRACK2_START_LBA,
            sector_count=TRACK2_SECTOR_COUNT,
        )
        verify_output_text(output_paths[".img"], payload_patches)

        changed_lbas = compare_raw_images(
            source_paths[".img"],
            output_paths[".img"],
        )
        changed_reports = tuple(
            report
            for report in sector_reports
            if report.before_sha256 != report.after_sha256
        )
        expected_lbas = tuple(
            report.absolute_lba
            for report in changed_reports
        )
        if changed_lbas != expected_lbas:
            raise ValueError(
                f"unexpected changed sectors: expected {expected_lbas}, "
                f"found {changed_lbas}"
            )

        output_hashes = {
            extension: hash_file(path)
            for extension, path in output_paths.items()
        }
        for extension in (".ccd", ".sub"):
            if output_hashes[extension] != SOURCE_HASHES[extension]:
                raise ValueError(
                    f"{extension} changed during build"
                )

        manifest = {
            "build_profile": BUILD_PROFILE,
            "title_screen_mode": title_screen_mode,
            "created_utc": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "scope": (
                "Same-size fullwidth Shift-JIS startup, mission-title, and "
                "selected Mission 0 translation with sentence case, 11-cell "
                "word wrapping on the unmodified dialogue renderer; both "
                "copies of all seven opening profiles; reflowed Media Mix "
                "information pages; and an optional antialiased title graphic "
                "with an isolated grayscale palette; not complete."
            ),
            "source_hashes": SOURCE_HASHES,
            "output_hashes": output_hashes,
            "image_bytes": output_paths[".img"].stat().st_size,
            "changed_absolute_lbas": list(changed_lbas),
            "changed_relative_sectors": [
                report.relative_sector
                for report in changed_reports
            ],
            "guarded_relative_sectors": [
                report.relative_sector
                for report in sector_reports
            ],
            "modified_sectors": [
                dataclasses.asdict(report)
                for report in changed_reports
            ],
            "text_patches": _manifest_patch_rows(HUMAN_TEST_PATCHES),
            "binary_patches": _manifest_binary_patch_rows(
                binary_patches
            ),
            "verification": {
                "source_hashes_match": True,
                "source_text_matches": True,
                "same_size_replacements": True,
                "mode1_edc_ecc_rebuilt": True,
                "only_expected_raw_sectors_changed": True,
                "ccd_unchanged": True,
                "sub_unchanged": True,
                "emulator_boot_tested": False,
            },
        }
        (temporary / "build_manifest.json").write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        ccd_name = output_paths[".ccd"].name
        (temporary / "HUMAN_TEST_README.txt").write_text(
            build_tester_readme(ccd_name, title_screen_mode),
            encoding="utf-8",
        )
        temporary.replace(output_directory)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return output_directory / f"{OUTPUT_STEM}.ccd"


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser.

    Returns:
        A parser describing the authenticated Mission 0 test build.
        Positional paths are added by ``main``.
    """

    return argparse.ArgumentParser(
        description=(
            "Create a verified CloneCD human-test build with same-size "
            "fullwidth English startup, opening-profile, Mission 0, and "
            "Media Mix text."
        ),
        epilog=(
            "The output is a limited vertical slice. It does not modify the "
            "dialogue parser or renderer; confirmed profile and Media Mix "
            "rows are reflowed in place."
        ),
    )


def main() -> None:
    """Build the test disc from command-line paths.

    Inputs:
        Parses the source CCD and a new output-directory path.

    Outputs:
        Prints the final CCD path, profile, patch count, changed relative
        sectors, and changed absolute LBAs.

    Side Effects:
        Copies approximately 612 MB of CloneCD data, patches the copied IMG,
        verifies the complete result, and writes a manifest and tester guide.

    Failure Conditions:
        ``argparse`` exits with status 2 for CLI syntax or any ``OSError`` or
        ``ValueError`` raised by the guarded build.
    """

    parser = build_parser()
    parser.add_argument(
        "source_ccd",
        type=pathlib.Path,
        help="authenticated source CloneCD .ccd",
    )
    parser.add_argument(
        "output_directory",
        type=pathlib.Path,
        help="new directory for the human-test CloneCD set",
    )
    parser.add_argument(
        "--title-screen",
        choices=TITLE_SCREEN_MODES,
        default=DEFAULT_TITLE_SCREEN_MODE,
        help=(
            "opening graphic variant: antialiased generated title and "
            "grayscale palette, or untouched original (default: clean)"
        ),
    )
    args = parser.parse_args()

    try:
        output_ccd = build_human_test_disc(
            args.source_ccd,
            args.output_directory,
            title_screen_mode=args.title_screen,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))

    manifest_path = output_ccd.parent / "build_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed_relative = manifest["changed_relative_sectors"]
    guarded_relative = manifest["guarded_relative_sectors"]
    changed_absolute = [
        TRACK2_START_LBA + sector
        for sector in changed_relative
    ]
    optional_title_patch_count = (
        2 if args.title_screen == "clean" else 0
    )
    print(f"output_ccd={output_ccd}")
    print(f"profile={BUILD_PROFILE}")
    print(f"title_screen={args.title_screen}")
    print(f"text_patches={len(HUMAN_TEST_PATCHES)}")
    print(
        "binary_patches="
        f"{len(HUMAN_TEST_BINARY_PATCHES) + optional_title_patch_count}"
    )
    print(
        "changed_relative_sectors="
        + ",".join(str(value) for value in changed_relative)
    )
    print(
        "guarded_relative_sectors="
        + ",".join(str(value) for value in guarded_relative)
    )
    print(
        "changed_absolute_lbas="
        + ",".join(str(value) for value in changed_absolute)
    )
    print("structural_validation=passed")
    print("human_emulator_test=pending")


if __name__ == "__main__":
    main()
