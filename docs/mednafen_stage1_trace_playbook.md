# Stage 1 English engine: debugger trace playbook

## Purpose and boundary

Use this procedure to identify the code and data ownership that produces the
Sengoku opening monologue.  It is **not** a release or translation-insertion
procedure.

RetroArch with Beetle PCE remains the normal playback and visual-test
environment.  It does not present Mednafen's interactive HuC6280 debugger to
the frontend user.  Use the separately installed Mednafen debugger only to
trace the failed experiment.

Do not load, save, or test the stock-renderer build with this procedure.  Do
not make another marker-based engine build from its results.

## Reproduction image

Use only this retained failure artifact:

`human_test_builds/wide-engine-stage1-tagged-escape-2026-07-28/Cyber City Oedo
808 - Kemono no Alignment (Japan) [Wide Engine Stage 1 Escape Test].ccd`

The `.ccd`, `.img`, and `.sub` files must remain together in that directory.
Its `ENGINE_TEST_FAILED_DO_NOT_USE.txt` marker is intentional.

## Debugger controls

Mednafen is installed at `D:\Emulation\Mednafen\mednafen.exe` and its current
configuration binds the debugger as follows:

| Action | Key |
| --- | --- |
| Toggle master debugger | `Alt+D` |
| Select CPU debugger | `Alt+1` |
| Run from a breakpoint | `R` |
| Execute one instruction | `S` |
| Edit disassembly address | `Enter` |
| Toggle a PC breakpoint on the selected instruction | `Space` |
| Edit logical/physical read breakpoints | `Shift+R` |
| Edit logical/physical write breakpoints | `Shift+W` |
| Switch a watch between logical and physical addressing | `M` |

The HuC6280 has banked physical address space.  PC breakpoints are logical
CPU addresses and trigger only at an instruction boundary.  For memory
breakpoints, a leading `*` requests a physical address; the debugger also
accepts PC Engine `segment:offset` physical form such as `*ff:0000-ff:03ff`.

## Minimal trace sequence

1. Launch the failed tagged `.ccd` in standalone Mednafen, then enter the
   debugger with `Alt+D`, followed by `Alt+1`.
2. Navigate to logical CPU address `$95D4` with `Enter`; press `Space` to set
   a PC breakpoint.  This is the original parser dispatch location.
3. Set a second PC breakpoint at `$56C0`; this is the prior candidate glyph
   path that calls `$E060`.
4. Run (`R`) and advance through the Sengoku opening until either breakpoint
   is hit.  Before resuming, record: the displayed PC, MPR/bank mapping,
   A/X/Y/SP/status registers, and the values at zero-page `$7F/$80`.
5. At `$95D4`, step (`S`) through the dispatch and record the branch taken
   plus `$7F/$80` both before and after each stream read.  `$9F11` reads from
   `($7F)` and `$9F14` advances that pair, but this must be confirmed against
   the live bank mapping.
6. At `$56C0`, record the call context immediately before and after the
   `JSR $E060`.  Do not patch or poke memory from the debugger.
7. If the corruption begins after a renderer/VDC write, add a *temporary*
   physical write breakpoint for the relevant port only after recording the
   current MPR state.  Do not use raw payload offsets as CPU addresses.

## Required evidence before any new engine design

Capture screenshots or a short written trace containing all of the following:

- Active dialogue-record address, MPR mapping, and the bytes at the live
  `$7F/$80` stream pointer.
- Parser PC and call chain for the opening line.
- Glyph/font-buffer address and VDC destination for one rendered character.
- The first divergence between an unmodified stock-renderer replay and the
  failed tagged image.

Only this evidence can establish a record-local selector or a safe new text
path.  A byte pattern that appears absent from extracted dialogue does not
establish parser ownership and must not be used as a global escape marker.
