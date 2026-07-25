# Disc layout and address math

## Source image

The analyzed release is a CloneCD set:

| File | Role | SHA-256 |
|---|---|---|
| `.ccd` | table of contents and track metadata | `716e509edaeeddc1b12c827ada3579b15c612a5f16400b72dabad2c6bcfece1b` |
| `.img` | interleaved 2352-byte raw sectors for all tracks | `815a8dda33ba2bb046fcbde773ad3a80fc6f89a96ef07e9c06bcc1c2e5fddece` |
| `.sub` | 96-byte-per-sector subchannel data | `ae8f54a4cd83e5e985d975f29654f8aa2f384cb4f7dcbd16a39b05b3263db411` |

There are 88 tracks. Track 2 is the program/data track; the other 87 are audio.

## Track 2 geometry

| Property | Value |
|---|---:|
| INDEX 01 absolute LBA | 3,590 |
| First valid Mode 1 absolute LBA | 3,590 |
| Last valid Mode 1 absolute LBA | 44,788 |
| Valid Mode 1 sector count | 41,199 |
| Relative sector range | 0-41,198 |
| Extracted payload bytes | 84,375,552 |
| Track 3 pregap absolute LBA | 44,789-44,938 |

The 150 sectors after the Mode 1 range are Track 3's pregap. They are not part
of the extracted data payload. Treating the pregap as additional Track 2 data
produces invalid mode/sync assumptions and shifts later track timing.

The valid payload SHA-256 is:

```text
0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223
```

## Three coordinate systems

The tools name coordinates explicitly:

### Absolute LBA

A sector number in the full disc image.

```text
absolute_lba = 3590 + relative_sector
```

### Relative payload sector

A 2048-byte sector in `track02_mode1_2048.bin`.

```text
relative_sector = payload_offset // 2048
within_sector   = payload_offset % 2048
```

### Payload byte offset

A direct byte address in `track02_mode1_2048.bin`.

```text
payload_offset = relative_sector * 2048 + within_sector
```

Example: resource sector 651 begins at:

```text
relative sector: 651
payload offset:  651 * 2048 = 0x00145800
absolute LBA:    3590 + 651 = 4241
```

To locate that sector in the raw IMG:

```text
raw sector start = absolute_lba * 2352
user-data start  = raw sector start + 16
```

Never apply a 2048-byte payload offset directly to the raw IMG.

## Raw Mode 1 sector shape

Each selected raw sector is 2352 bytes:

| Raw byte range | Size | Meaning |
|---|---:|---|
| `0x000-0x00B` | 12 | sync pattern (`00 FF...FF 00`) |
| `0x00C-0x00E` | 3 | BCD minute/second/frame address |
| `0x00F` | 1 | mode byte (`01`) |
| `0x010-0x80F` | 2048 | user data extracted by this toolkit |
| `0x810-0x813` | 4 | EDC |
| `0x814-0x81B` | 8 | reserved zero bytes |
| `0x81C-0x92F` | 276 | ECC P/Q parity |

`extract_track2_mode1.py` checks the sync and mode byte, then copies
`0x010-0x80F`. It does not verify the mathematical correctness of EDC/ECC.

## Why payload edits cannot simply be copied back

Changing even one user-data byte invalidates the raw sector's EDC and ECC.
A correct reinserter must rebuild those fields for every modified sector. It
must then place the rebuilt 2352-byte sectors back at their original absolute
LBAs without changing:

- the number of sectors;
- Track 2 INDEX 01;
- Track 3's pregap;
- any audio-track start;
- audio sector contents; or
- `.sub` sector alignment.

`cdrom_mode1.py` now implements this operation for guarded same-size payload
patches. `build_human_test_disc.py` uses it only on an authenticated copy,
rebuilds every affected sector, compares the complete source/output images,
and preserves the CCD and SUB byte-for-byte.

This does not authorize general reinsertion. The current profile does not
relocate data, update pointers, or alter dialogue controls.

## PCE-CD boot header observations

The extracted payload has a valid PC Engine CD header. The observed fields are:

| Field | Value |
|---|---|
| boot index | relative sector 3 |
| boot length | 16 sectors |
| load address | `$4000` |
| execute address | `$4000` |
| MPR mapping | `00 01 02 03 04` |
| title field | `SAMPLE PROGRAM` |

`SAMPLE PROGRAM` appears to be a development placeholder and is not evidence of
a bad dump.

### Opening-title graphic

The first visible title is a complete raw background image rather than a
Shift-JIS string or hardcoded tilemap. Its confirmed payload geometry is:

| Field | Value |
|---|---|
| start offset | `0x0000A000` |
| exclusive end | `0x00011800` |
| byte size | `0x7800` (30,720) |
| tile count | 960 |
| tile order | 32 columns by 30 rows |
| pixel size | 256 by 240 |
| tile encoding | PC Engine 8-by-8 planar 4bpp |
| source SHA-256 | `74319e81bfeba32b385620a8bf32848e78da19271c87b6337decf4991a2fe5c4` |

The title's seven 16-color animation palettes occupy payload
`0x00002848` through `0x00002927` (224 bytes), with SHA-256
`650a61cee3f91e3c4b2a5159feb38800384daa2ad6ba48903f3596417fa1085b`.
The clean-title variant replaces all seven frames with one repeated grayscale
ramp so four-bit edge coverage remains stable. Palette indexes 0 through 5 are
black because the original title routine leaves a few low-index pixels active
in the upper border; clean-logo coverage is remapped into indexes 6 through
15. The distinct 32-byte portrait palette at `0x00002828` through
`0x00002847` is not part of the patch.

The boot program transfers this ready-to-display block without requiring a
new tilemap. The optional clean-title patch can therefore replace the complete
same-size range while preserving boot code, display dimensions, and disc
geometry. `title_screen.py` generates the replacement; no original graphic
bytes are stored in the repository.

### Opening profile records

The seven opening dossiers occupy two resource copies:

| Copy | First visible record | Last visible record |
|---|---:|---:|
| primary | `0x00020BF1` | `0x0002180D` |
| repeated | `0x00060B8D` | `0x00061783` |

Each visible line begins with `00 0C RR`, where `RR` is an 8-pixel tile-row
operand, and ends with a null byte. The v0.9 builder changes 160 same-size text
runs and 46 row commands across these banks. It does not alter the adjacent
portrait data, record order, separators, or profile-selection controls.

## Mission analysis banks

Repeated engine/resource anchors divide the payload for inventory grouping:

| Bank | Start sector | End sector, exclusive |
|---|---:|---:|
| `MISSION_0` | 0 | 5,376 |
| `MISSION_1` | 5,376 | 11,047 |
| `MISSION_2` | 11,047 | 16,554 |
| `MISSION_3` | 16,554 | 20,924 |
| `MISSION_4` | 20,924 | 25,371 |
| `MISSION_5` | 25,371 | 29,334 |
| `MISSION_6` | 29,334 | 32,831 |
| `MISSION_7` | 32,831 | 36,132 |
| `MISSION_8` | 36,132 | 39,435 |
| `ENDING` | 39,435 | 41,199 |

These are not filesystem partitions. They are stable analysis labels defined
once in `game_layout.py`.

## Resource regions

The payload is directoryless but contains uppercase module names at many sector
boundaries, including `BARTEN1`, `BILL1`, `INVENTRY`, `PERSON`, `HASE1`, and
`GATE1`.

Many neighboring names are four sectors apart, but fixed four-sector sizing is
not universal. Some named resources span eight, twelve, or more sectors, and
their starting phase changes between missions. `analyze_text_slots.py` therefore
uses consecutive sector-aligned names as candidate region boundaries.

That boundary is still heuristic. A module can contain code, tables, graphics,
or references that do not appear in a string scan.

## Address-handling checklist

Before documenting or patching an address:

1. State whether it is an absolute LBA, relative sector, payload offset, CPU
   address, or raw IMG byte offset.
2. For payload offsets, record both `sector` and `within_sector`.
3. Keep ranges half-open in code: `[start, end)`.
4. Verify the payload SHA-256 before comparing offsets across copies.
5. Recheck any address after changing extraction geometry.
