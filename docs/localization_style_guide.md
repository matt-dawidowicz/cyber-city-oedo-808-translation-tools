# Final localization style guide

## Target

The English release should read like a professionally localized early-1990s
cyberpunk adventure: hardboiled, economical, technically literate, and
occasionally melodramatic, without becoming a parody of period localization.

The governing rule is: **translate the Japanese game. Use the English OVA for
established continuity, terminology, characterization, and performance rhythm,
but never as a replacement script.**

Natural English outranks Japanese syntax. Fidelity to meaning, characterization,
story state, and game mechanics outranks literal word order.

## Continuity and the Mission 0 origin story

Mission 0 predates the familiar OVA team arrangement.

At the opening:

- Sengoku is an independent lone-wolf bounty hunter returning to Oedo after
  seven years away;
- he has pursued Chris Dunford / Rose Rash from Shanghai;
- Benten and Gogul are Class-A cybercriminals who have repeatedly escaped
  Sengoku's traps;
- Sengoku knows them as dangerous quarry/rivals, not established coworkers; and
- the Cyber Security / Mobile Detective arrangement is something the game still
  has to establish.

Their English relationship must progress from early suspicion/rivalry, through
grudging cooperation, to the sharper familiar ensemble rhythm of the later
game. Do not back-project later coworker banter into early Mission 0.

## Character voices

### Sengoku
Hardboiled, abrasive, impatient, sardonic, and streetwise. His narration should
have cyber-noir economy. Concern is often disguised as irritation. Use
contractions and direct constructions. Strong language is permitted when the
Japanese supports it; do not inflate profanity merely to imitate the dub.

### Benten
Poised, elegant, economical, dryly theatrical when appropriate, and dangerous
without needing to announce it. Avoid gratuitous vulgarity.

### Gogul
Laconic, technically competent, measured, and dry. His size should not turn him
into a generic bruiser; preserve his intelligence and engineering background.

### Hasegawa
Clipped institutional menace. Calm authority is usually more effective than
shouting. Commands should sound like commands.

### Okyo
Warm, lively, capable, teasing when appropriate, but never childish.

### Maya
Cool, mature, capable, and worldly. She should sound comfortable explaining
Oedo's criminal and political power structure.

### Makze
Cultivated authoritarian menace. Avoid cartoon-villain excess where controlled
confidence is sufficient.

### Varsus
Precise, analytical, hyperliteral, and mildly pedantic. Do not add generic robot
catchphrases.

### Dr. Chang
Expert scientist with only lightly marked non-native English where the Japanese
actually supports it. Do not turn irregular grammar into caricature.

### Security Force personnel
Crude, macho, territorial gang-soldier speech. Keep individual lines natural
rather than stuffing every sentence with slang.

## OVA relationship

Prefer established franchise forms when the Japanese supports them: Sengoku,
Benten, Gogul, Hasegawa, Okyo, and Varsus.

Use established English terminology when several faithful renderings are
possible. Do not import dub-only jokes, sexual language, profanity absent from
the Japanese, new insults, added plot information, or unrelated OVA lines.

The desired result should feel compatible with the English OVA without becoming
a fan rewrite of it.

## Dynamic identities and investigative state

The game mechanically changes labels as Sengoku learns information. Preserve
unknown person -> identified person, generic object -> identified object,
unknown location -> named location, and suspect descriptor -> proper name
transitions.

Do not reveal an OVA-known name early merely because the translator recognizes
the character. Repeated Japanese may receive different English in different
contexts; occurrence context outranks canonical-string reuse.

## Dialogue prose

Prefer spoken English: contractions, concise clauses, active voice, natural
fragments, and idiomatic reactions. Remove Japanese redundancies only when they
carry no new information, characterization, emphasis, investigation state, or
player guidance.

Avoid modern quip-heavy dialogue. The target is cyberpunk crime fiction, not
contemporary superhero banter.

## Profanity

Profanity is contextual, not a target metric. Translate genuine aggression with
appropriately strong English. Do not add profanity because the English OVA dub
is famous for it.

## Menus and commands

Menu language prioritizes immediate comprehension and stable terminology.

| Japanese | English |
|---|---|
| 見る | Look |
| 話す | Talk |
| 見せる | Show |
| 調べる | Examine |
| 尋ねる | Ask |
| 取る | Take |
| 渡す | Give |
| 使う | Use |
| 動かす | Move |
| 押す | Push |
| 引く | Pull |
| 待つ | Wait |
| 叩く | Hit |
| ヴァーサス | Varsus |
| 持ち物 | Items |
| システム | System |
| データセーブ | Save |
| データロード | Load |
| 移動 | Travel |
| 調査依頼 | Request Investigation |
| モード設定 | Mode Setup |
| サーモセンス | Thermosense |
| 空気密度測定 | Air Density |
| 特殊嗅覚作動 | Scent Sensor |
| 特殊聴覚作動 | Audio Sensor |
| 特殊視覚作動 | Vision Sensor |
| 識別 | Identify |
| リンク | Link |
| 逮捕状発行 | Arrest Warrant |
| 捜査礼状発行 | Search Warrant |
| パラライザー | Paralyzer |
| ワッパガン | Cuff Gun |
| モンタージュ | Composite |
| 指紋照合 | Fingerprints |
| 血液鑑定 | Blood Test |
| サンプリング | Sampling |
| モード | Mode |

Move manipulates something; Travel changes location.

Mode terminology is fixed as Investigation Mode, Arrest Mode, Deduction Mode,
and Intercept Mode.

## Opening computer register

The opening readout should look like an intentional cyber-terminal rather than
literal fullwidth Japanese English:

    CD-ROM DRIVE........READY
    ADPCM DRIVER........INSTALLED
    MUSIC DRIVER........INSTALLED
    STATIC RAM..........OK
    COMM INTERFACE......READY
    NETWORK SYSTEM......OK
    USER ID:
    SHUNSUKE SENGOKU
    ** O-E-D-O MAIN DATABASE **
    CYBERCRIMINAL INDEX

This is a presentation register, not ordinary dialogue.

## Typography

Preserve useful typographic distinctions where the English renderer supports
them: smart double quotes, smart apostrophes, em dash, en dash where genuinely
needed, ellipsis, yen sign, and standard ASCII punctuation. Typography must
never be encoded by repurposing dialogue control bytes.

## Capacity and line length

Do not degrade prose merely to reproduce the original Japanese byte count. This
is a CD title. Disc capacity is not the governing constraint.

When English grows, prefer proven resource-length updates, pointer-aware
relocation, additional owned CD sectors/resources, and renderer/layout
improvements over unnatural abbreviation.

The constraints that still matter are RAM residency, VRAM ownership, pointer
width/windows, loader lengths, overlay lifetime, and control semantics.

## Control-byte fidelity

Dialogue controls are part of the performance. Preserve explicit line/page
progression, timed pauses, press/release waits, voice synchronization, glyph
delay, text attributes, and dynamic label insertion.

## Translator uncertainty

When a referent, technical term, joke, or context remains genuinely uncertain,
record the uncertainty. A reviewed translator note is preferable to false
certainty.
