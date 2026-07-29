# Stage 1 runtime failure: global escape markers are not viable

Both Stage 1 English-engine images failed during Mission 0 playback and are
retained only as reproduction artifacts. Neither may be used for saves,
translation insertion, or future renderer work.

The first image interpreted any `FF` as the start of an English escape block.
The loaded Mission 0 data has an ordinary `FF FE` pair immediately before the
Sengoku prologue. The user observed a crash after that prologue.

The tagged revision required `FF 00`, but the same loaded module contains 483
raw `FF 00` pairs. The user observed a green screen with scattered tile
fragments after the prologue. This is evidence of renderer-state corruption,
not a legibility issue.

Static byte absence in extracted dialogue is therefore insufficient. Do not
choose another global escape marker. Resume only with an emulator trace that
proves the active record pointer, parser call context, glyph/font buffer,
VDC destination, and resource ownership at the exact target dialogue field.
The stock-renderer path remains the only playable build direction.
