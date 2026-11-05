# P0: natural NPC ADPCM regression - 2026-10-18

This is a cold-boot, ordinary-controller replay of the **street watcher NPC**, NOT the naturally reached Mission 0-B bartender. It proves one real dialogue encounter and gives us a repeatable baseline for #46, but does not satisfy #45.

Repro: [tools/mesen_p0_natural_npc_regression.lua](../tools/mesen_p0_natural_npc_regression.lua). Run in fresh, separate MesenCE 2.2.1 portable instances for the source disc and an authenticated --english-pilot --vwf-pilot disc with **performance_experiment=none**:

    Mesen --testRunner game.cue mesen_p0_natural_npc_regression.lua --timeout=120 --enableStdout

Use the Japanese Super CD-ROM 3.0 BIOS, validated 88-track CUE, PC Engine controller on port 1, and enable Debug.ScriptWindow.AllowIoOsAccess so screenshots can be written. Keep the original disc, BIOS, generated discs and screenshots OUTSIDE GitHub.

Original track 2 SHA-256: 0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223

## Replayed route

- Until frame 8600: Run taps before 600, then I taps to clear the intro.
- Frames 8600-13299: right.
- Frames 13300-15599: up.
- Frames 15600 onward: right plus intermittent I to interact with the nearby watcher.

No forced PC, arbitrary RAM writes, savestate shortcut, or changed inputs between discs. The script logs all eight MPRs, the actual common module call, the current $4CFA mapping, and screenshots at 6000, 8600, 13300, 15600, 16500, 17000 and 17800.

## Observed stock vs English-VWF A/B

| Check | Original | English/VWF |
| --- | --- | --- |
| Natural street navigation and watcher NPC | reached | reached |
| Shared dialogue ADPCM call $80E0 | 2 total | 2 total |
| Portrait loader $8405 | 1 | 1 |
| Interaction scan $4B20 | 14 | 14 |
| Instruction at $80E0 during natural watcher | 20 33 E0 | 20 33 E0 |
| Existing mapped bytes at $4CFA | 12 zero bytes | 12 zero bytes |
| MPR0-7 at the natural $80E0 call | FF F8 80 81 85 83 84 00 | same |
| Screenshots through frame 17000 | six captures byte-identical | six captures byte-identical |
| Frame 17800 screenshot | 70 pixels differ from pilot | 70 pixels differ from original |

At frames 16500 and 17000 the screenshot SHA-256 is the same for both discs:
2116612962b3c18c9c956b3d8ba7e9750fc436a0bd4863595639837b0f847a8e.

**Limit:** the 70-pixel frame-17800 difference is localized to one Japanese dialogue glyph in the x160-173, y161-175 text area, consistent with a small dialogue timing difference. This was NOT waived as equivalence, and there is no scripted proof of subsequent dialogue completion, second interaction, later missions, or normal bartender. This is an NPC reachability and callsite proof, not full visual/runtime parity.

## Important correction: residency risk, not demonstrated root cause

A **third** controlled cold-boot replay used a throwaway disc built with the
**historical ADPCM-only experiment** (the checked-in builder deliberately
rejects making this legacy profile now).

- At intro frame 2647, the historic callsite is 20 FA 4C (JSR $4CFA), and
  the mapped $4CFA bytes are the installed cache routine: 43 20 48 43 40 48.
- At the **natural watcher frame 15955**, the same patched call and the same
  installed cave bytes are present. The watcher conversation was reached,
  with two total ADPCM callsite hits and one portrait-loader hit. The
  ADPCM-only variant did **not** crash at this encounter.
- In the two *unpatched-ADPCM* stock and English/VWF runs, $4CFA was zero-filled
  at that frame, but that comparison does not imply a patched disc would jump
  into zeros. The earlier root-cause statement inferred a patched memory map
  from unpatched bytes and was incorrect.

The dialogue module is shared while the cave is injected into Mission-0-B
outer-overlay source. That is still an **unverified cross-mission residency
risk**, not a demonstrated explanation of the earlier all-seven and
portrait+ADPCM combined-profile failures. We have not reproduced their
failure cause or proven cache/overlay safety across later missions.

As a conservative build safeguard, PR #42 currently refuses adpcm,
portrait-adpcm and all-seven profiles even with the unsafe acknowledgment.
It does not remove the stand-alone benchmark code, supply a bank-independent
replacement, or establish that ADPCM alone caused the earlier regression.
Do not characterize this gate as a completed #46 root-cause fix.

## Remaining P0 release gates

- #45: Reach the actual bar naturally, confirm $7B English pool and VWF dispatch, reads, continuation, portraits/voice, timing, and street/second-interaction return.
- #46: Reproduce the **combined** portrait+ADPCM and seven-patch failures against matched cold-boot traces, isolate the actual first divergence, validate overlay residency across later missions, and revisit the unexplained dialogue timing offset. Only then decide if a trampoline or overlay-local cache hook is necessary.
- Do not turn on experimental performance or release certification based on this narrow test.

## 2026-10-18 follow-up: stable portrait-only cave (commit 0f7c3e9)

### Root cause and repair

A cold-boot natural watcher trace of the initial portrait hook found $4C93-$4CC3
overwritten at runtime. In the first proposed trampoline experiment, only the
nine MPR-save instructions moved to $4D59, while the CPU then jumped into a
partially zeroed body at $4C9C, executing invalid instructions. Correctly
restoring MPRs at the call return was therefore insufficient.

The confirmed narrow correction relocates **all 103 bytes** of the portrait
cache from $4C93-$4CF9 to the original-source-zero $4CFA-$4D60 range. The
source guard still checks every replaced byte. This placement is specifically
a Mission-0 experimental cave; later mission/scene residency has NOT been
certified.

The historical ADPCM cache also occupies $4CFA. Both algorithms cannot
coexist in the same cave. The combined benchmark now omits the old ADPCM
cache, rejects explicit inclusion with a clear error, and the engine builder
continues to reject the corresponding ADPCM-containing profiles.

### Deterministic stock-versus-portrait replay

For both source and experimental portrait-only discs, MesenCE 2.2.1 ran from
cold boot on the authenticated 88-track game with standard controller input
and Japanese v3 BIOS. Normal street input reached the watcher naturally.
The critical controller phase change is: **stop sending button I after frame
16000**, while preserving the original navigation controls. This prevents
differences in dialogue-button polling from masquerading as graphics
regressions. Neither replay used forced PC, RAM edits or savestate jumps.

The source disc and the relocated portrait cache disc produced matching
PNG bytes (not merely a visually similar picture) at seven checkpoints:

| Frame | SHA-256 of each matching screenshot |
| --- | --- |
| 6000, 8600 | cf365fae13a5f9790ba99d995dd496ed9ea8977238a3cdf8f07608730c07d0d7 |
| 13300 | 61e077f610355fc65e112d63495ce0492063ef9bda632056404781496b766632 |
| 15600 | 9ba5aca460ad76b0367bce4112df44be8430334836199f5ec2052536de1939f9 |
| 16500, 17000, 17800 | 4c040b913bee5997a46310c5c81969500db13819ef70d999e5e1dd35c8d63e2f |

Both runs observed identical hook counts: common ADPCM $80E0: 2; portrait
loader $8405: 1; interaction scan $4B20: 14; text parser $9F14: 1639.
At 17900 both ended in the same dialogue-loop region ($5B80/$5B81),
with all eight MPRs [FF F8 80 81 82 83 84 00].

This is evidence that the **portrait-only** relocation repairs the specific
watcher rendering regression, under the supplied input contract. It is not
an all-missions/full-UI/ADPCM-cache/performance certification.

### Failed alternative discarded

An experimental attempt to move the legacy ADPCM cave into $90D4 of the
shared dialogue module failed near the intro. Although the source Track-2
image contains zeros in that apparent gap, **live bank contents are not source
zeros**: a read-only Mesen probe observed active data in $8F51-$8FC0 and
$90D4. The game's earlier CD reads do not guarantee those additional source
bytes stay loaded. Source-zero space cannot be assumed to be code-owned RAM.
The attempt was **not** committed; the original audio experiment remains
quarantined.

### Remaining gates

Issue #46 remains open for combined performance optimizations, scene return,
a second encounter and later-mission cache ownership. Issue #45 remains
open because the actual Mission-0-B bartender has still not been reached
through natural gameplay in the English pilot. Nothing here changes any
release-enabled flag.
