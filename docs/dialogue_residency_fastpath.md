# Dialogue residency and transition fast-path architecture

Status: reverse engineering / live-proof preparation. No cache fast path is release-enabled.

## Why this matters

Mission 0 interaction latency is not one slow transfer. The game repeatedly switches the optical subsystem among:

1. exploration CD-DA playback;
2. fade/teardown;
3. executable/data resource installation;
4. ADPCM source transfer;
5. portrait/dialogue presentation;
6. exploration graphics restoration; and
7. CD-DA playback again.

The existing transition evidence already measures roughly 5.7-6.2 seconds from the first known dialogue CD read to the first parser execution. Exploration exit also contains a fixed 120-frame wait after starting a PCM fade. This document maps the state that must survive before either cost can be removed safely.

## The complete bank-$85 dialogue workspace

Mission 0 maps physical CD-RAM bank $85 into logical $8000-$9FFF during dialogue.

| Logical range | Bytes | Role |
|---|---:|---|
| $8000-$8F50 | 3,921 | dialogue/audio module source-loaded body |
| $8F51-$8FFF | 175 | mutable runtime/BSS |
| $9000-$9FFF | 4,096 | current speaker-local block |
| **total** | **8,192** | one physical 8 KiB bank |

The non-sector-aligned module length is significant. The generic loader reads exactly $0F51 bytes and therefore refreshes the module while preserving the 175-byte BSS immediately after it.

Known BSS state includes $8FDD requested speaker selector, $8FDE cached speaker-local selector, $8FE0+ audio/runtime state, and $8FF7/$8FF8 transfer/runtime flags.

## The stock loader already probes residency

The standard dialogue-module loader begins with:

    LDA $8000
    ORA $8003
    CMP #$4C

The two entrypoints are JMP instructions when the module is present. However, in the shipping code the next instruction is an unconditional LDA #$00 that begins the normal loader argument setup. No branch consumes the comparison result.

The exact resident-check signature occurs twelve times in Track 2. Ten standard copies are the known M0-A/M0-B/M1-M8 dialogue overlays. One additional standard-form loader at payload 0x000D10A6 uses the same idiom for a different $8000 resource, and one older-form copy uses a different setup. The extra loader is deliberately not classified as a dialogue module.

All ten known dialogue-overlay sources begin with the expected JMP entrypoints at source offsets +0 and +3. Their loaded lengths range from $0C15 to $0FE1; every one is exactly two CD sectors of source and every one leaves a BSS/state tail below $9000. M0-A and M8 even share the same LBA $A222 module image. This makes the resident-workspace pattern game-wide within the common dialogue engine, while the unrelated extra loader remains separately classified.

This proves that the game checks a plausible module-residency signature before reloading. It does not prove why the comparison was left unused.

## Self-modification is narrowly bounded

A control-flow walk from the known Mission 0 module entrypoints identifies only two source-loaded bytes modified by reachable module code: $8617 and $8618. They are the operand bytes of the self-modified LDA $0000 instruction at $8616.

Twenty-four reachable STA/INC/DEC sites target only those two bytes.

Immutable-body SHA-256 excluding those two bytes:

    c0b71dfb04f32db00dac4c7e1de7372c14173884c7dfd3970c439609da5360f1

A future cache hit can authenticate the immutable module body, restore $8617/$8618 to their source values, retain the BSS as the stock partial reload already does, and skip the optical module reload. That mutation remains gated on live residency proof.

## Why the stock module load costs two CD commands

The Mission 0 module is $0F51 bytes long: one complete 2 KiB sector plus a $751-byte remainder. The System Card CD_READ interface provides LOCAL transfers in whole-record units; the arbitrary byte-count form is the VRAM-specific $FE mode, not a general LOCAL byte-copy mode. The stock generic byte loader therefore:

    $1425 -> $8000   one full record
    $1426 -> bounce RAM   one full record
    bounce -> $8800       copy only the $751-byte remainder

This preserves the $8F51-$8FFF BSS tail. In the historical trace the two CD_READ starts are 67 frames apart. A resident-module cache removes both commands and the bounce-copy path without requiring a nonexistent exact-length LOCAL BIOS transfer.

## Historical residency evidence

The old Mission 0 V5 capture shows physical bank $85 remaining mapped/active during dialogue and long periods of exploration. Bank-$85 activity plateaus for multi-thousand-frame exploration windows, then increases by only a tiny amount at the next interaction before the stock module reload.

This is consistent with the module surviving exploration, but historical access counts are not a byte-integrity proof.

Use:

    tools/mesen_dialogue_residency_profiler.lua

The profiler fingerprints the immutable module body immediately after a stock load and again at the next loader probe. It also records all writes into the module body and the speaker-local half of the bank.

## Speaker-local caching

Command 1 already contains a small cache: $8FDD is the requested selector and $8FDE is the currently installed selector. If they match, the two-sector local block at $9000 is not reloaded. A full command-0/command-5 teardown deliberately invalidates $8FDE.

The $9000-$9FFF block shares the same persistent physical bank as the module. If it survives exploration, a future fast path can retain or revalidate it instead of relying only on the stock metadata byte.

The four-sector ADPCM block is different: command 1 retransfers it even on a speaker-local cache hit.

## ADPCM state is not one reusable buffer

Command 4, the voice/sample-start path, performs additional descriptor-driven AD_TRANS operations. Therefore ADPCM RAM cannot safely be treated as a persistent copy of command 1's four-sector source.

A safe cache should retain source audio data in CPU/Card RAM and feed ADPCM RAM as needed rather than assuming ADPCM RAM itself remains unchanged.

## Mission 0 voice extent

The command-4 descriptor table begins at module address $8BA3 and contains 157 six-byte entries.

Authenticated table SHA-256:

    3dff96b6bb5aa6bd46dfc2f4265fa401eb0e45c1038f2690f797382d500e903e

All 157 voice clips form one contiguous optical extent:

    first LBA          $16F6
    end exclusive      $228E
    sectors            2,968
    bytes              6,078,464
    raw 1x duration    39.573 s

The hot exploration graphics begin immediately after this voice extent at $228E.

The complete mission voice corpus is therefore far too large for the additional 192 KiB Super CD work RAM. Voice caching must be scoped to the active conversation, a small hot set, or intentionally duplicated/reordered hot clips on the English CD image.

## Why the large exploration VRAM reload exists

The stock exploration graphics load source $22E8 to VDC word $0900 for $EE00 bytes, filling VDC word addresses $0900-$7FFF.

Dialogue presentation writes inside that same range: portraits begin at $4000, dialogue glyph patterns begin at $6D00, and dialogue BAT data begin around $7900.

Therefore the 60,928-byte scene graphics reload on return is not purely redundant. Dialogue has overwritten portions of the exploration image.

The important optimization question is now narrower: how much of the $EE00-byte scene image does dialogue actually change?

Use:

    tools/mesen_dialogue_vram_clobber_profiler.lua

It records actual changed VRAM byte ranges from dialogue-load start until immediately before the stock $22E8 scene restore. If the dirty set is much smaller than $EE00, a cached scene image can restore only the damaged ranges rather than retransferring the entire scene from CD.

## CD-audio mode thrashing

Exploration entry cancels an existing fade and starts CD-DA playback with CD_PLAY before the interactive loop. Every exploration exit calls the transition teardown, which starts CD_FADE mode $0C and then performs 120 EX_VSYNC calls.

Thus an ordinary interaction is an optical-subsystem mode switch:

    CD-DA playback
        -> fade / fixed wait
        -> code + data loads
        -> ADPCM transfer / dialogue
        -> scene graphics restore
        -> CD-DA playback

This is a design-level reason the pauses can approach ten seconds.

## CD_EXEC was missing from the original timing model

The historical profiler measured CD_READ. The later profiler added AD_TRANS. Neither historical trace measured CD_EXEC, the System Card operation that loads an executable and transfers control to it.

The transition profiler now records CD_READ entry -> exact return, CD_EXEC entry -> first execution at its target, AD_TRANS entry -> exact return, CD_PLAY/CD_PAUSE, CD_FADE, AD_STOP/AD_STAT, EX_VSYNC, byte-loader timing, and first dialogue parser execution.

Do not classify raw 20 0F E0 byte sequences in Track 2 as code without runtime/MPR context; several static matches are clearly in graphics/data.

## Likely optimization hierarchy

1. **Shorter safe CD-DA teardown.** Replace multi-second fade policy with a state-correct short stop/pause path only after exact live timing.
2. **Resident dialogue module.** Skip repeated module CD reads if immutable bank-$85 residency is certified; restore the two self-modified operand bytes.
3. **Retain/revalidate speaker-local data.** Avoid repeated two-sector local loads when the $9000 block survives.
4. **Source-cache current ADPCM material.** Stage only the current speaker/conversation rather than attempting a whole mission voice cache.
5. **Selective VRAM restoration.** Restore the measured dialogue-dirty ranges from cached scene data rather than retransferring all $EE00 bytes.
6. **Improve disc locality.** Keep remaining uncached resources contiguous and remove unnecessary seeks.
7. **Compress only after command/seek overhead is reduced.** The raw transfer floor is already a minority of the observed delay.

## Reproducible static report

Run:

    cyber-oedo analyze-dialogue-residency track02_mode1_2048.bin --output dialogue_residency.json

The report source-guards the Mission 0 dialogue module, standard residency probes, all known self-modification sites, audio command/update windows, exploration transition/fade path, Mission 0 voice-descriptor extent, and static dialogue/exploration VRAM overlap.

Static evidence identifies safe candidates. The live profilers decide whether those candidates may become release mutations.
