# P0 dialogue-exit probe: original-game negative result (2026-10-20)

The read-only 38,000-frame diagnostic in `tools/mesen_p0_dialogue_exit_probe.lua` was exercised on the authenticated original game using the same input schedule as the local `p0_exit_local.lua` equivalent.

## Result

**Failed to demonstrate a second interaction.** At frame 38,000:

```
P0_EXT_RESULT adpcm=2 portrait=1 interact=14 gameLoop=1 transition=1 AD_READ=2600 AD_WRITE=2
```

The hook counts did not increase after the initial watcher encounter; at frames 26,000 and 28,000, screenshots still displayed the same watcher portrait and choice menu. Button II, choice-down/confirm, Run/II and subsequent right/I pulses did not establish an exit. The MPR snapshot remained `FF F8 80 81 82 83 84 00`. The script's required second-load condition therefore fails, as intended.

This is **negative evidence about this particular controller schedule**, not proof that the game cannot exit the conversation, nor proof of a combined-cache repair. The original and portrait-only discs have **not** been compared on a complete second-interaction route. No unsafe cache profile should be enabled, and issue #46 remains open.

## Follow-up

Investigate the watcher menu's actual controller mapping and event-loop state, including the difference between command selection and text-advance polling, before committing another long replay. Then establish a source-versus-portrait A/B second interaction and isolate the historical combined-cache first divergence. Do not treat `AD_READ=2600` callback hits as 2600 independent audio transfers.
