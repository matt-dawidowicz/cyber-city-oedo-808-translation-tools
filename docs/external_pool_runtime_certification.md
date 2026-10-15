# External dialogue-pool runtime certification status

A separately constructed external English-pool image was previously
structurally inspected. **That image's redirect helper is not reproduced
by the current checked-in native-English runtime assembler.** Consequently
the branch itself does not implement the full `27 28 7B` redirect path and
must not be presented as a complete or release-certified pool-capable build.

The image-level findings below describe the historical experimental image,
not a runtime handler available from `native_english_runtime.py`.

## Proven

- The growth-pool CloneCD image boots through the Super CD-ROM System screen.
- The boot path accepts Run and begins ordinary game-sector reads.
- Exactly 1,908 source records contain the expected fixed-address `27 28 7B`
  redirect form.
- All ten Mission 0-8 text overlays contain the intended parser, font, stream
  read, and stream advance hooks.
- Mission pools occupy only the authenticated zero-filled Track-2 tail.
- 46 tail sectors remain untouched and zero-filled.
- Every actually changed raw Mode-1 sector regenerates to the emitted EDC/ECC.
- The M0-B redirect helper in the built image has been decoded:
  redirect -> lazy pool load -> external byte read/advance -> stock parser.
- The M0-B pool load contract reads four four-sector chunks into Super System
  Card banks `$7C-$7F`.

## Historical savestate limitation

The retained bartender state restores a different overlay/MPR configuration and
therefore cannot prove the disc-loaded Mission-0 text overlay.

A controlled MesenCE harness was built to install the exact patched M0-B
overlay and point the real parser at a real redirect. This exposed two harness
facts:

1. HuC6280 direct-page state is visible in Mesen at the internal-RAM logical
   page (`$20xx`), not hardware page `$00xx`.
2. MesenCE's Lua `setCpuState()` / `loadSavestate()` reports a changed PC
   inside a callback, but the core resumes the instruction path that was
   already scheduled when that callback returns. Even a newly serialized state
   containing PC `$9543` exhibits this behavior when loaded from the callback.

Therefore this harness cannot honestly establish the required live redirect
chain.

## Remaining implementation and release gates

Before runtime certification, check a pool redirect loader/dispatcher into
the repository itself, source-guard the `$7C-$7F` Card-RAM mapping and stream
pointer lifecycle, add synthetic tests for cross-bank bounds/terminators and
stock-parser fallbacks, and demonstrate that the checked-in build reproduces
the prior image-level evidence.

A valid certification run must observe, in normal execution order:

1. a real dialogue parser entry;
2. encounter of opcode `7B`;
3. the expected mission-pool CD read(s);
4. redirected stream reads from Card RAM;
5. at least one stock cell-renderer call produced from redirected English;
6. clean return through ordinary dialogue controls.

This should be obtained from a natural interactive playthrough or from an
emulator harness that can start from a chosen CPU state without callback
resumption semantics.

Until that trace exists, the pool runtime remains **structurally verified,
runtime pending** rather than release-certified.
