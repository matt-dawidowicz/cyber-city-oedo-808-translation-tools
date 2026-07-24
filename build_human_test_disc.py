#!/usr/bin/env python3
"""Build a guarded CloneCD image for early human testing.

This command creates a complete disposable copy of the supplied CloneCD set
and applies the ``mission0-v7`` guarded insertion profile. The profile
translates startup notices, prompts, mission-title subtitles, and the opening
Mission 0 bartender conversation and complete ten-page opening narration with
sentence-case fullwidth Shift-JIS English that the original 16x16 BIOS font
path can render. Narration is word-wrapped on the code-confirmed 11-cell line
width. A narrowly scoped renderer hook recognizes fullwidth English comma and
period codes as hanging punctuation, matching the original Japanese behavior.
The three Media Mix merchandise pages are translated and reflowed onto
non-overlapping tile rows without changing the general text renderer.

The source CCD, IMG, and SUB must match the analyzed release exactly. Every
replacement must match its expected Japanese bytes and preserve byte length.
Only the affected 2048-byte user-data sectors are changed; their raw Mode 1
EDC/ECC fields are rebuilt. The builder then compares every raw sector against
the source and rejects changes outside the expected absolute LBAs.

This is a playable vertical slice, not a complete English translation. Most
dialogue, interfaces, and later game content remain Japanese until the compact
Latin renderer and relocation work are done.
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
)
from game_layout import (
    MODE1_USER_DATA_OFFSET,
    RAW_SECTOR_SIZE,
    SECTOR_SIZE,
    TRACK2_SECTOR_COUNT,
    TRACK2_START_LBA,
)


BUILD_PROFILE = "mission0-v7"
OUTPUT_STEM = (
    "Cyber City Oedo 808 - Kemono no Alignment (Japan) "
    "[Human Test v0.7]"
)
PROLOGUE_WRAP_WIDTH = 11
INFORMATION_HIDDEN_ROW = 0x1E
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
        "  2: The Decoy Program",
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
        "  VHS 9600 / LD 7600 + Tax",
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
        "  1: Rebel Lone Wolf",
        "Media Mix novel volume 1",
        0x0A,
    ),
    InformationScreenLine(
        "novel",
        0x00006982,
        0x0A,
        "　　　　　　　　　　華麗なる堕天使（第２巻）",
        "",
        "Media Mix novel superseded volume 2",
        INFORMATION_HIDDEN_ROW,
    ),
    InformationScreenLine(
        "novel",
        0x000069B2,
        0x0B,
        "　　　　　　　　　　魔眼の闘士　　（第３巻）",
        " 3: Evil-Eyed Warrior",
        "Media Mix novel volume 3",
        0x0E,
    ),
    InformationScreenLine(
        "novel",
        0x000069E2,
        0x0C,
        "　　　　　商品概要：富士見ファンタジア文庫",
        "Fujimi Fantasia Bunko",
        "Media Mix novel imprint",
        0x10,
    ),
    InformationScreenLine(
        "novel",
        0x00006A10,
        0x0D,
        "　　　　　著　　者：遠藤明範",
        "",
        "Media Mix novel superseded author",
        INFORMATION_HIDDEN_ROW,
    ),
    InformationScreenLine(
        "novel",
        0x00006A30,
        0x0E,
        "　　　　　発売元　：富士見書房（株）",
        "",
        "Media Mix novel superseded publisher",
        INFORMATION_HIDDEN_ROW,
    ),
    InformationScreenLine(
        "novel",
        0x00006A58,
        0x0F,
        "　　　　　価　格　：５００円（税込み）",
        "",
        "Media Mix novel superseded price",
        INFORMATION_HIDDEN_ROW,
    ),
    InformationScreenLine(
        "novel",
        0x00006A83,
        0x16,
        "＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋",
        "       Now on Sale",
        "Media Mix novel availability",
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
        "  2: Magnificent Fallen Angel",
        "Media Mix novel volume 2",
        0x0C,
    ),
    InformationScreenLine(
        "novel",
        0x00006B03,
        0x18,
        "＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋",
        "  A. Endo / Fujimi Shobo",
        "Media Mix novel author and publisher",
        0x12,
    ),
    InformationScreenLine(
        "novel",
        0x00006B43,
        0x1B,
        "＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃＃",
        "   JPY 500 (Tax Included)",
        "Media Mix novel price",
        0x14,
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
        "",
        "Media Mix music superseded soundtrack title",
        INFORMATION_HIDDEN_ROW,
    ),
    InformationScreenLine(
        "music",
        0x00006CA6,
        0x0A,
        "　　　　　　　　　　クリミナルナイト（ゲーム音楽）",
        "",
        "Media Mix music superseded game title",
        INFORMATION_HIDDEN_ROW,
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
        "       Now on Sale",
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
        " Command of Remembrance (OST)",
        "Media Mix music soundtrack title",
        0x0A,
    ),
    InformationScreenLine(
        "music",
        0x00006DDF,
        0x18,
        "＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋＋",
        "  Criminal Night (Game Music)",
        "Media Mix music game title",
        0x0C,
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
    + INFORMATION_SCREEN_TEXT_PATCHES
)


# Mission 0's active dialogue renderer is in the executable block whose
# payload-to-CPU mapping is ``payload 0x00131800 == CPU $0000``. Its original
# kinsoku table treats Japanese comma/stop codes as hanging punctuation, but
# not the fullwidth English comma/period codes emitted by this builder. The
# three-byte default return is redirected to an unused, unreferenced zero-fill
# cave in the same mapped 8 KiB page. The cave preserves every original
# punctuation entry and returns the existing 12-cell limit only for Shift-JIS
# ``81 43`` and ``81 44``.
MISSION0_RENDERER_PATCHES: tuple[PayloadPatch, ...] = (
    PayloadPatch(
        offset=0x00137165,
        expected=bytes.fromhex("A9 0B 60"),
        replacement=bytes.fromhex("4C 0E 55"),
        label="Mission 0 English hanging-punctuation hook",
    ),
    PayloadPatch(
        offset=0x00136D0E,
        expected=b"\x00" * 22,
        replacement=bytes.fromhex(
            "A5 03 C9 81 D0 0A A5 02 C9 43 F0 07 "
            "C9 44 F0 03 A9 0B 60 A9 0C 60"
        ),
        label="Mission 0 English hanging-punctuation code cave",
    ),
)


HUMAN_TEST_BINARY_PATCHES = (
    MISSION0_RENDERER_PATCHES
    + INFORMATION_SCREEN_LAYOUT_PATCHES
)


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
        path. It does not claim to increase line width or replace the future
        compact Latin renderer.
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


def build_tester_readme(ccd_name: str) -> str:
    """Return the human-testing instructions included beside the image.

    Args:
        ccd_name: Filename testers should open in an emulator.

    Returns:
        Plain-text instructions with scope, boot steps, visible proof, and
        limitations.
    """

    lines = [
        "Cyber City Oedo 808 - Human Test v0.7",
        "======================================",
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
        "- The notice identifies a HUMAN TEST BUILD.",
        "- Startup, load, and memory prompts use fullwidth English.",
        "- Mission 1 through Mission 8 title subtitles use English.",
        "- The opening Mission 0 bartender conversation uses English.",
        "- Sengoku's complete ten-page opening narration uses English.",
        "- All three Media Mix merchandise pages use readable English.",
        "- Merchandise lines use non-overlapping 16-pixel row spacing.",
        "- Mission 0 dialogue uses lowercase letters.",
        "- Narration words wrap on the renderer's 11-cell grid.",
        "- English comma and period stay attached as hanging punctuation.",
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
        "- More letters per line require a compact Latin renderer patch.",
        "- A guarded Mission 0 punctuation hook changes renderer behavior.",
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
    """Serialize exact renderer-patch evidence for the build manifest.

    Args:
        binary_patches: Guarded non-text payload patches in application order.

    Returns:
        JSON-serializable rows containing coordinates, labels, and exact
        before/after hexadecimal bytes.
    """

    rows: list[dict[str, Any]] = []
    for patch in binary_patches:
        relative_sector = patch.offset // SECTOR_SIZE
        rows.append(
            {
                "purpose": patch.label,
                "payload_offset": f"0x{patch.offset:08X}",
                "relative_sector": relative_sector,
                "absolute_lba": TRACK2_START_LBA + relative_sector,
                "expected_hex": patch.expected.hex(" "),
                "replacement_hex": patch.replacement.hex(" "),
                "bytes": len(patch.expected),
            }
        )
    return rows


def build_human_test_disc(
    source_ccd: pathlib.Path,
    output_directory: pathlib.Path,
) -> pathlib.Path:
    """Build and verify the ``mission0-v7`` CloneCD test set.

    Args:
        source_ccd: Authenticated source CloneCD descriptor.
        output_directory: New directory that will receive the completed set.

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
    text_payload_patches = tuple(
        patch.to_payload_patch()
        for patch in HUMAN_TEST_PATCHES
    )
    payload_patches = text_payload_patches + HUMAN_TEST_BINARY_PATCHES

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
        expected_lbas = tuple(
            report.absolute_lba
            for report in sector_reports
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
            "created_utc": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "scope": (
                "Same-size fullwidth Shift-JIS startup, mission-title, and "
                "selected Mission 0 translation with sentence case, "
                "11-cell word wrapping, and English hanging punctuation; "
                "plus reflowed Media Mix information pages; not complete."
            ),
            "source_hashes": SOURCE_HASHES,
            "output_hashes": output_hashes,
            "image_bytes": output_paths[".img"].stat().st_size,
            "changed_absolute_lbas": list(changed_lbas),
            "changed_relative_sectors": [
                report.relative_sector
                for report in sector_reports
            ],
            "modified_sectors": [
                dataclasses.asdict(report)
                for report in sector_reports
            ],
            "text_patches": _manifest_patch_rows(HUMAN_TEST_PATCHES),
            "binary_patches": _manifest_binary_patch_rows(
                HUMAN_TEST_BINARY_PATCHES
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
            build_tester_readme(ccd_name),
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
            "fullwidth English startup, Mission 0, and Media Mix text."
        ),
        epilog=(
            "The output is a limited vertical slice. It does not modify the "
            "compact text renderer; Media Mix rows are reflowed in place."
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
    args = parser.parse_args()

    try:
        output_ccd = build_human_test_disc(
            args.source_ccd,
            args.output_directory,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))

    changed_relative = sorted(
        {
            patch.offset // SECTOR_SIZE
            for patch in (
                tuple(
                    text_patch.to_payload_patch()
                    for text_patch in HUMAN_TEST_PATCHES
                )
                + HUMAN_TEST_BINARY_PATCHES
            )
        }
    )
    changed_absolute = [
        TRACK2_START_LBA + sector
        for sector in changed_relative
    ]
    print(f"output_ccd={output_ccd}")
    print(f"profile={BUILD_PROFILE}")
    print(f"text_patches={len(HUMAN_TEST_PATCHES)}")
    print(f"binary_patches={len(HUMAN_TEST_BINARY_PATCHES)}")
    print(
        "changed_relative_sectors="
        + ",".join(str(value) for value in changed_relative)
    )
    print(
        "changed_absolute_lbas="
        + ",".join(str(value) for value in changed_absolute)
    )
    print("structural_validation=passed")
    print("human_emulator_test=pending")


if __name__ == "__main__":
    main()
