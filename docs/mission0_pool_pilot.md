# Mission 0-B first English-pool vertical slice (experimental)

This is a **single-line, opt-in proof build**, not a translation release,
not an emulator-certified patch, and not a replacement for a complete Mission 0
playthrough. The original Japanese disc remains unchanged. Do not merge this
path as a completed English engine based solely on its green CI.

## Source provenance and why the RAM mapping matters

All offsets below refer to the SHA-256-authenticated original **2048-byte
Track 2 payload**:

`0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223`.

The original Mission 0-B loader at CPU `$64DF`, disc payload
`0x00131800+$64DF`, requests `$0301` bytes of LBA `$107D`
into **RAM `$A400`**. The pilot changes that guarded size instruction to
`$1C00`, extending the installed copy through RAM `$BFFF`.

| Purpose | Actual RAM addresses | Original disc payload bytes |
|---|---|---|
| Indexed records, immutable | `$A400-$A700` | `0x0013B800-0x0013BB00` |
| English 8x16 atlas | `$A800` onward | `0x0013BC00` onward |
| Native English and pool code | `$B000` onward | `0x0013C400` onward |
| Source tail reserved for four Card-RAM banks | `$7C-$7F` via temporary MPR3 `$6000` reads | sectors `0xA059-0xA068` relative to Track 2 |

The source atlas area begins with `$400` bytes of zero, followed by
`$E5` fill. The first `$1000` source bytes assigned to code are all
`$E5`. The 16 tail sectors are all zero. The builder checks the
**entire original payload hash** and exact expected bytes for every mutation.

**Critical correction:** writing a routine to the original disc at
`source_base + $A300`, just because the CPU address is `$A300`,
does not prove the game's loader ever installs it there. The ordinary
`$A400` indexed-table load also overwrites source assumptions about
the runtime. This pilot installs code via the directly proven indexed
loader, separate from the live table.

## Redirect, source continuation and bank safety

Pilot record: the original bartender `27 28` marker at
`0x00145890` and Shift-JIS body
`バーテン「いらっしゃいませ」` at `0x00145892`.
Its existing null terminator remains at `0x001458AE`.

Proposed on-disc **v2 pilot** body:

```text
7B <pool_offset_lo> <pool_offset_hi> <source_skip_lo> <source_skip_hi>
```

The skip is relative to the first byte AFTER these five bytes. Its
purpose is to restore the **original Japanese record's terminator
position**, rather than leave the outer script interpreting 23 remaining
Shift-JIS bytes as commands. The earlier draft
`27 28 7B offset_lo offset_hi 00` is a **different, unproven historical
format** and cannot be silently substituted. This v2 contract is
exclusive to the new proof builder, not a claim about the missing
experimental image.

The runtime patches only M0-B `$9543`/parser-dispatch,
`$9F11` stream read, `$9F14` stream advance, the font hook,
the indexed loader, and their guarded data. It stores the stock script
return pointer in overlay-resident memory, uses a source-visible
`$7B` private redirect, and loads the first four tail Card-RAM banks
using four `CD_READ ($E009)` calls of four sectors each.

The byte reader temporarily maps Card RAM into **MPR3**, fetches the
requested byte from `$6000-$7FFF`, and immediately restores the
original MPR3 before returning to stock game code (which may execute
inside `$6000-$7FFF`). The pointer advance helper handles bank
crossings and returns to the saved stock pointer at the original
terminator. The output is experimental because CD BIOS side effects,
interrupts, real register lifetimes, nested indirect text, long waits,
and all MPR configurations still need actual emulator evidence.

## Building and testing

Run from the repository with dependencies installed:

```bash
python -m cyber_oedo.runtime.mission0_pool_pilot \
  "/path/to/Cyber City Oedo 808 - Kemono no Alignment (Japan).ccd" \
  "/path/to/output/m0b-pilot" \
  "/path/to/font.ttf"
```

This creates a new CloneCD set and a manifest under the specified
**previously nonexistent** output directory. The original CCD/IMG/SUB
are not modified. The manifest sets `release_enabled=false` and
`emulator_certified=false`, records changed sectors and runtime label
addresses, and generates `mesen_m0b_pool_pilot_trace.lua` using the
exact assembled code addresses.

In MesenCE 2.2.1:
1. Load the **experimental output CCD**.
2. Load the generated read-only Lua trace (not the generic historical
   external pool trace).
3. Start a new game and naturally reach the Mission 0 bartender line.
4. Check the script log for one private redirect, four ordered pool
   CD_READs at absolute LBAs `$AE5F,$AE63,$AE67,$AE6B`, banked reads,
   rendered cells, and the parser returning to the original source
   without an intervening error.
5. Visually verify English text, Japanese fallback, timing, scroll,
   subsequent dialogue, scene changes, audio and save/load. Capture
   actual MPRs, CD statuses, screenshots/video and the Lua transcript.
6. On a failure, disable this proof layer; do not infer correctness
   from static tests or partial traces.

The user must supply a legally obtained source disc and local font.
Do not commit or distribute game ROM sectors, proprietary images, or
font binaries.

## What automated tests actually prove

- The source-patch addresses use distinct, non-overlapping original
  disc regions and preserve the original body terminator location.
- The generated interpreter and font fit the extended **installed**
  M0-B allocation.
- Synthetic HuC6280 instruction stepping tests the stream helper,
  four BIOS request parameter blocks, bank rollover, restoration of
  stock MPR3, save/restore of BIOS direct-page parameters, and the
  fail-closed path on an injected CD error.
- The generated Mesen script contains real assembler addresses and
  never writes emulator state.

**They do not prove:** BIOS compatibility with real System Card 3.0,
a fully rendered English dialogue in a live game, sprite/VRAM
equivalence, all seven control types, Japanese fallback in all
contexts, or any later mission/ending interpreter.

The original external-pool `$7B` review thread should remain OPEN
until real gameplay and clean script continuation are witnessed. PR #42
should remain unmerged as a finished English engine.
