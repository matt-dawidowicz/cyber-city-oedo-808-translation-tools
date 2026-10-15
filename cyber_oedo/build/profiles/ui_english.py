"""Reviewed English UI terminology for the final localization pass.

This module is translation/profile data only.  It deliberately does not emit
binary patches yet: the final English renderer/relocation architecture must be
activated only after its runtime ownership gates are satisfied.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UiLabel:
    source: str
    english: str


@dataclass(frozen=True, slots=True)
class OpeningText:
    entry_id: str
    payload_offset: int
    source: str
    english: str
    presentation: str


COMMON_COMMAND_LABELS = (
    UiLabel("見る", "Look"),
    UiLabel("話す", "Talk"),
    UiLabel("見せる", "Show"),
    UiLabel("調べる", "Examine"),
    UiLabel("尋ねる", "Ask"),
    UiLabel("取る", "Take"),
    UiLabel("渡す", "Give"),
    UiLabel("使う", "Use"),
    UiLabel("動かす", "Move"),
    UiLabel("押す", "Push"),
    UiLabel("引く", "Pull"),
    UiLabel("待つ", "Wait"),
    UiLabel("叩く", "Hit"),
    UiLabel("ヴァーサス", "Varsus"),
    UiLabel("持ち物", "Items"),
    UiLabel("システム", "System"),
    UiLabel("データセーブ", "Save"),
    UiLabel("データロード", "Load"),
    UiLabel("移動", "Travel"),
    UiLabel("調査依頼", "Request Investigation"),
    UiLabel("モード設定", "Mode Setup"),
    UiLabel("サーモセンス", "Thermosense"),
    UiLabel("空気密度測定", "Air Density"),
    UiLabel("特殊嗅覚作動", "Scent Sensor"),
    UiLabel("特殊聴覚作動", "Audio Sensor"),
    UiLabel("特殊視覚作動", "Vision Sensor"),
    UiLabel("識別", "Identify"),
    UiLabel("リンク", "Link"),
    UiLabel("逮捕状発行", "Arrest Warrant"),
    UiLabel("捜査礼状発行", "Search Warrant"),
    UiLabel("パラライザー", "Paralyzer"),
    UiLabel("ワッパガン", "Cuff Gun"),
    UiLabel("モンタージュ", "Composite"),
    UiLabel("指紋照合", "Fingerprints"),
    UiLabel("血液鑑定", "Blood Test"),
    UiLabel("サンプリング", "Sampling"),
    UiLabel("モード", "Mode"),
)

MODE_LABELS = (
    UiLabel("捜査モード", "Investigation Mode"),
    UiLabel("逮捕モード", "Arrest Mode"),
    UiLabel("推理モード", "Deduction Mode"),
    UiLabel("迎撃モード", "Intercept Mode"),
)

OPENING_MENU_AND_READOUTS = (
    OpeningText("T00013", 0x00001C31, "ＮＥＷＧＡＭＥ", "NEW GAME", "menu"),
    OpeningText(
        "T00014",
        0x00001C43,
        "（最初から）",
        "(Start from the beginning)",
        "menu_help",
    ),
    OpeningText("T00015", 0x00001C53, "ＤＡＴＡＬＯＡＤ", "LOAD GAME", "menu"),
    OpeningText(
        "T00016",
        0x00001C67,
        "（セーブしたところから）",
        "(Continue a saved game)",
        "menu_help",
    ),
    OpeningText(
        "T00017",
        0x00001C83,
        "ＭＥＭＯＲＹＣＨＥＣＫ",
        "MEMORY CHECK",
        "menu",
    ),
    OpeningText(
        "T00018",
        0x00001C9D,
        "（空きメモリーの確認）",
        "(Check free space)",
        "menu_help",
    ),
    OpeningText(
        "T00019",
        0x00001CB7,
        "項目を選んでＩボタンを押して下さい。",
        "Select an option and press Button I.",
        "menu_help",
    ),
    OpeningText("T00020", 0x00001D8A, "データをロードします。", "Loading...", "system"),
    OpeningText(
        "T00021",
        0x00001DA4,
        "ファイル名を選んで下さい。",
        "Select a save file.",
        "system",
    ),
    OpeningText("T00032", 0x00001FFC, "ファイルが有りません。", "No save file found.", "system"),
    OpeningText(
        "T00033",
        0x000020BB,
        "メモリーが壊れています。",
        "Backup memory is corrupted.",
        "system",
    ),
    OpeningText(
        "T00034",
        0x00002182,
        "ＯＥＤＯ８０８ファイルは",
        "The OEDO808 save file",
        "system_fragment",
    ),
    OpeningText(
        "T00035",
        0x0000219E,
        "正しく存在しています。",
        "is present and valid.",
        "system_fragment",
    ),
    OpeningText(
        "T00036",
        0x0000227F,
        "作成可能です。",
        "A save file can be created.",
        "system",
    ),
    OpeningText(
        "T00037",
        0x0000233C,
        "空きメモリーが足りません。",
        "Not enough free backup memory.",
        "system",
    ),
    OpeningText(
        "T00038",
        0x0000235A,
        "何かファイルを消して下さい。",
        "Delete another file to free space.",
        "system",
    ),
    OpeningText(
        "T00039",
        0x00002425,
        "ＯＥＤＯ８０８ファイルが",
        "The OEDO808 save file",
        "system_fragment",
    ),
    OpeningText(
        "T00043",
        0x0000252E,
        "フォーマットされていません。",
        "Backup memory is not formatted.",
        "system",
    ),
    OpeningText(
        "T00081",
        0x000209FC,
        "ＣＤ−ＲＯＭ　Ｄｒｉｖｅ　Ｒｅａｄｙ．",
        "CD-ROM DRIVE........READY",
        "terminal",
    ),
    OpeningText(
        "T00082",
        0x00020A26,
        "ＡＤＰＣＭ　　Ｄｒｉｖｅｒ　Ｉｎｓｔａｌｌｅｄ．",
        "ADPCM DRIVER........INSTALLED",
        "terminal",
    ),
    OpeningText(
        "T00083",
        0x00020A5A,
        "ＭＵＳＩＣ　　Ｄｒｉｖｅｒ　Ｉｎｓｔａｌｌｅｄ．",
        "MUSIC DRIVER........INSTALLED",
        "terminal",
    ),
    OpeningText(
        "T00084",
        0x00020A8E,
        "Ｃｈｅｃｋｉｎｇ　Ｓｔａｔｉｃ−ＲＡＭ・・・・ＯＫ．",
        "STATIC RAM..........OK",
        "terminal",
    ),
    OpeningText(
        "T00085",
        0x00020AC7,
        "Ｃｏｍｍｕｎｉｃａｔｉｏｎ　Ｉｎｔｅｒｆａｃｅ　Ｒｅａｄｙ．",
        "COMM INTERFACE......READY",
        "terminal",
    ),
    OpeningText(
        "T00086",
        0x00020B07,
        "Ｎｅｔｗｏｒｋ　Ｓｙｓｔｅｍ　ｉｓ　ＯＫ．",
        "NETWORK SYSTEM......OK",
        "terminal",
    ),
    OpeningText(
        "T00087",
        0x00020B35,
        "Ｕｓｅｒ　Ｉｄｅｎｔｉｔｙ：",
        "USER ID:",
        "terminal",
    ),
    OpeningText(
        "T00088",
        0x00020B57,
        "ＳＹＵＮＳＵＫＥ　ＳＥＮＧＯＫＵ",
        "SHUNSUKE SENGOKU",
        "terminal",
    ),
    OpeningText(
        "T00089",
        0x00020B7E,
        "＊＊　Ｏ−Ｅ−Ｄ−Ｏ　Ｍａｉｎ　Ｄａｔａ　Ｂａｓｅ　＊＊",
        "** O-E-D-O MAIN DATABASE **",
        "terminal_heading",
    ),
    OpeningText(
        "T00090",
        0x00020BBA,
        "Ｌｉｓｔ　ｏｆ　Ｃｙｂｅｒ　Ｃｒｉｍｉｎａｌ",
        "CYBERCRIMINAL INDEX",
        "terminal_heading",
    ),
)
