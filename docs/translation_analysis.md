# Cyber City Oedo 808: English Translation Analysis

> Status note: This report records the original static-analysis milestone.
> The current repository now includes a structurally verified fullwidth
> Mission 0 vertical slice and Mode 1 EDC/ECC rebuilding. See
> `human_test_build.md` and `validation_results.md` for the newer milestone.
> The later compact-renderer experiment is frozen at commit `3abaf64` and is
> excluded from the playable build. The active direction is stock-renderer
> paging plus pointer-aware relocation.

## Verdict

An English patch is technically viable.

The main dialogue is not compressed and is not baked into the background art. It is stored as ordinary, null-terminated Shift-JIS inside named scene modules. The boot program calls the PC Engine CD System Card's `EX_GETFNT` routine to turn Shift-JIS codes into 16×16 glyphs.

The hard part is therefore not extracting the Japanese. It is adding compact English rendering, preserving embedded control bytes, updating any affected pointers or lengths, and rebuilding valid raw Mode 1 sectors without disturbing the 87 audio tracks.

No source disc files were modified during this analysis.

## Disc structure

- Format: CloneCD `.ccd` + raw `.img` + `.sub`
- Tracks: 88 total
- Audio tracks: 87
- Program/data track: track 2
- Track 2 INDEX 01 starts at absolute LBA 3,590
- Valid Mode 1 payload: 41,199 sectors, relative sectors 0–41,198
- Absolute Mode 1 range: LBA 3,590–44,788
- Track 3 pregap: LBA 44,789–44,938 (150 sectors)
- Extracted 2048-byte payload size: 84,375,552 bytes
- Extracted payload SHA-256: `0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223`

Source hashes:

| File | SHA-256 |
|---|---|
| `.ccd` | `716e509edaeeddc1b12c827ada3579b15c612a5f16400b72dabad2c6bcfece1b` |
| `.img` | `815a8dda33ba2bb046fcbde773ad3a80fc6f89a96ef07e9c06bcc1c2e5fddece` |
| `.sub` | `ae8f54a4cd83e5e985d975f29654f8aa2f384cb4f7dcbd16a39b05b3263db411` |

The PCE-CD header is valid. It identifies a 16-sector boot program beginning at relative sector 3, loaded and executed at `$4000`. The header title is the development-era placeholder `SAMPLE PROGRAM`; this is harmless.

## Text and rendering architecture

### Encoding

- Japanese and fullwidth Latin text use normal Shift-JIS.
- Strings are terminated by `00`.
- Dialogue records are reliably introduced by bytes `27 28`.
- Low ASCII-range bytes inside a record are not ordinary English characters. They are bytecode or layout controls.

This means a translation cannot safely write normal ASCII directly into the existing strings.

### Font path

The boot program calls BIOS address `$E060` (`EX_GETFNT`) multiple times. The observed setup selects the 16×16 transfer mode. The BIOS routine accepts a Shift-JIS code and returns the corresponding glyph.

This gives two insertion options:

1. **Proof-of-concept:** encode English with fullwidth Shift-JIS Latin glyphs. This needs little renderer work, but remains fixed-width at 16 pixels per character and is unlikely to fit natural English.
2. **Release-quality:** add an escape-coded 8×16 or variable-width Latin path while leaving existing control bytes and Japanese Shift-JIS behavior intact.

The second option is strongly preferred.

### Embedded controls

The dominant values observed inside dialogue are:

| Byte | Occurrences | Current status |
|---|---:|---|
| `40` | 1,538 | Appears at dialogue/paragraph transitions; exact runtime behavior still needs tracing |
| `2F` | 1,004 | Often repeated around pauses or line/page transitions; exact behavior unconfirmed |
| `21` | 831 | Common near the end of a displayed unit; exact behavior unconfirmed |
| `5C` | 18 | Seen on mission-title records; exact behavior unconfirmed |

These values must remain tagged in the editable script until a runtime trace confirms their precise semantics.

### Resource layout

The data track is directoryless, but contains named modules such as:

- `BARTEN1`
- `BILL1`
- `INVENTRY`
- `PERSON`
- `HASE1`
- `GATE1`
- `MISSION`-specific scene modules

Many modules begin on recurring four-sector boundaries and are surrounded by constant-fill regions (`00`, `08`, `E5`, or `FF`). This is promising for relocation, but the fill bytes are not automatically safe free space: some neighboring sectors hold code, graphics, tables, or additional resources. Pointer and length fields must be mapped before using that room.

Nine identical engine/resource anchors were found at relative sectors:

`5,376`, `11,047`, `16,554`, `20,924`, `25,371`, `29,334`, `32,831`, `36,132`, and `39,435`.

These anchors separate the later mission/ending banks. Mission 0 occupies the initial bank.

## Extracted text inventory

The editable inventory contains:

| Category | Occurrences | Unique candidate text |
|---|---:|---:|
| High-confidence dialogue | 3,721 | 2,337 |
| Auxiliary/UI/item/location/system text | 1,325 | 670 |
| Combined likely unique strings | — | 3,007 |
| Records flagged for manual review | 219 | Included in the inventory |

Unique likely text contains approximately 80,638 Japanese/fullwidth source characters:

- Dialogue: 68,295
- Auxiliary text: 12,343

This is an upper-bound translation inventory. It includes duplicated records, developer/debug menus, database material, and possibly unreachable content. A runtime coverage pass is needed before calling every entry player-visible.

High-confidence dialogue occurrences by bank:

| Bank | Records |
|---|---:|
| Mission 0 | 549 |
| Mission 1 | 557 |
| Mission 2 | 503 |
| Mission 3 | 410 |
| Mission 4 | 319 |
| Mission 5 | 331 |
| Mission 6 | 316 |
| Mission 7 | 231 |
| Mission 8 | 505 |

The source also contains an original typo in the opening notice: `ＭＩＳＳＯＮ８` is missing the second `I`.

## Mission titles

Suggested working translations:

| Japanese | Working English |
|---|---|
| ＭＩＳＳＩＯＮ １　【大使護衛】 | Mission 1: Ambassador Escort |
| ＭＩＳＳＩＯＮ ２　【機密ファイル】 | Mission 2: Classified File |
| ＭＩＳＳＩＯＮ ３　【容疑者】 | Mission 3: The Suspect |
| ＭＩＳＳＩＯＮ ４　【連続殺人】 | Mission 4: Serial Murders |
| ＭＩＳＳＩＯＮ ５　【不破博士失跡】 | Mission 5: Dr. Fuwa Missing |
| ＭＩＳＳＩＯＮ ６　【赤毛と青目】 | Mission 6: Red Hair and Blue Eyes |
| ＭＩＳＳＩＯＮ ７　【誘拐】 | Mission 7: Kidnapping |
| ＭＩＳＳＩＯＮ ８　【アジト】 | Mission 8: The Hideout |

## Sample localization

The script is suitable for a natural, hard-boiled English voice. For example:

| Japanese | Suggested English |
|---|---|
| このゲームはＭＩＳＳＩＯＮ０からＭＩＳＳＯＮ８までの全９パートから構成されています。 | The game is divided into nine parts, Mission 0 through Mission 8. |
| ひとつのＭＩＳＳＩＯＮが終了するまで途中セーブは出来ません。 | You can't save until the current mission is complete. |
| バーテン「いらっしゃいませ」 | Bartender: “Welcome.” |
| バーテン「お客さん、この辺は初めてでしょう。いや、なに、顔を見りゃそれぐらいわかりますよ」 | Bartender: “First time around here, isn't it? I can tell just by looking at you.” |
| バーテン「いったいどの辺から来なさったんです？　おっと、つまらないこと聞いちまいましたね」 | Bartender: “Where'd you come in from? Ah—never mind. Shouldn't have asked.” |
| バーテン「ところで、あちらのお嬢さん、気を付けた方がいいですよ。どうも賞金稼ぎらしいですからね。ま、これは忠告ってやつです」 | Bartender: “By the way, watch out for the girl over there. She looks like a bounty hunter. Just a friendly warning.” |

## Recommended implementation sequence

1. **Runtime trace**
   - Boot the unmodified disc with a Japanese System Card BIOS.
   - Break on `$E060` and the dialogue renderer.
   - Confirm the meanings of `40`, `2F`, `21`, and `5C`.
   - Record line width, visible rows, page timing, and which extracted records are reachable.

2. **Minimal insertion proof**
   - Replace one short line with same-size fullwidth English.
   - Patch only the necessary Mode 1 user-data sector.
   - Recompute EDC/ECC and verify the CloneCD image still boots.

3. **English renderer**
   - Add an escape prefix for Latin text so existing bytecodes remain unambiguous.
   - Add an 8×16 or variable-width font.
   - Add English-aware wrapping without changing Japanese rendering.

4. **Reinserter**
   - Preserve tagged control bytes.
   - Start with in-place strings.
   - Map and update module-local pointers/lengths before relocating expanded text.
   - Keep all track starts, audio timing, pregaps, and `.sub` data unchanged.

5. **Translate and test by mission**
   - Complete Mission 0 first as the vertical slice.
   - Exercise every branch, inventory description, save/load screen, and mission transition.
   - Expand to Missions 1–8 only after the renderer and rebuild path are stable.

## Current validation boundary

Completed:

- CCD/IMG/SUB layout parsed
- Track 2 Mode 1 sectors validated structurally
- Valid data/pregap boundary identified
- PCE-CD boot header parsed
- Boot-program font calls identified
- Raw PCE 4bpp graphics rendered successfully
- Shift-JIS dialogue and auxiliary text extracted
- Translation inventory generated with offsets, mission banks, control tags, duplicate IDs, and review flags

Not yet completed:

- Emulator boot or hardware test
- Exact bytecode semantics
- Pointer/length relocation map
- English font patch
- Rebuilt raw-sector EDC/ECC validation
- Full translation

Static analysis did not require or use the earlier Sega CD `Nostalgia 1907` pipeline.
