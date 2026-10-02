# External dialogue-pool runtime certification status

The external English-pool build is structurally complete but is not yet marked
release-certified.

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

## Remaining release gate

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
