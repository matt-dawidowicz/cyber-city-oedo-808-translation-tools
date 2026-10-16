# Mesen live $7B path proof — controlled source-authenticated diagnostic (Oct 15, 2026)

**Status:** live HuC6280 external-pool *mechanism* validated for one controlled introductory narration redirect. **Not a naturally triggered bartender interaction, not a Mission 0 English release, and not game-wide certification.** The normal experimental bartender pilot remains unchanged.

## Provenance and isolation

- Original Track 2 Mode-1 payload SHA-256: `0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223`.
- The existing M0-B pilot builder from PR #42 commit `5a7fad948a1d226607cde8369444618514efaa62` produced a fresh, separate CloneCD set with only the authenticated 8-sector patch described by its manifest.
- To reach the interpreter's private redirect without relying on unproven street/bar navigation, a **third, diagnostic-only copy** received an additional *source-byte-guarded* patch to the first naturally used opening-narration record.
- Source marker: `0x00175828: 27 28`; original body begins at `0x0017582A` with `81 75 89 B4 82` and terminates at `0x00175ADF: 00`.
- The first five body bytes became `7B 00 00 B0 02` (pool offset zero; skip `0x02B0 = 688` source bytes). The original terminator was **not** moved. One additional relative Track-2 sector, 747, was rewritten with regenerated Mode-1 EDC/ECC.
- This diagnostic temporarily substitutes the text **“Bartender: Welcome.”** into *introductory narration* to exercise the **same assembled machine-code path** as the intended bartender pilot. It is not an editorial change to ship, and it does **not** authenticate navigation to the bar.
- The original disc, normal M0-B pilot, and user-provided BIOS remain byte-for-byte unchanged. Neither source/modified game sectors nor the BIOS are committed to the repository.

## Actual live MesenCE 2.2.1 observations

With Japanese Super CD-ROM System v3.0, the generated 88-track CUE, and `--testRunner --enableStdout --pcEngine.port1.type=PceController`:

| Observed point | Emulator frame | Concrete observation |
|---|---:|---|
| Native dispatcher receives $7B | 5008 | PC `$B17A`, A=`$7B`, pointer `$C36B`, MPR3=$81 |
| Pool redirect entry | 5008 | PC `$B1AD` |
| Pool loader | 5008 | PC `$B26E`, saved stock source pointer `$C61F` |
| BIOS `CD_READ` #1 | 5008 | absolute LBA `$AE5F`, 4 blocks, destination `$6000`, mode `$01` |
| BIOS `CD_READ` #2 | 5075 | LBA `$AE63` with the same transfer parameters |
| BIOS `CD_READ` #3 | 5088 | LBA `$AE67` |
| BIOS `CD_READ` #4 | 5101 | LBA `$AE6B` |
| Stock cell-renderer call | 5119–5191 | ten callbacks at `$5915`, approximately 8 frames apart, pool remains active |
| Source restoration | 5199 | PC `$B19F`, mapped stock MPR3 `$81`; return from pool pointer `$6016` |
| Further gameplay | through 6158 | 11 total dispatch entries, 19 stock renderer entries, one redirect, one pool-loader entry, one source-restoration entry; no observed crash |

The captured Mesen screenshot at local emulator frame 5,328 shows the English string **“Bartender: Welcome.”** displayed correctly as visible pixels over the introduction. Subsequent frames transitioned to the next original presentation scene. The live trace records **82** pool read-helper callbacks over the observed interval, including indirect parser loads.

These observations provide live proof that the generated **$7B -> four-bank CD load -> English cell renderer -> source restoration** code is reachable and functions in this controlled circumstance. This is materially stronger than synthetic CPU execution alone.

## What remains unproven

- Natural entry into the **actual** M0-B bar, execution of the **unchanged normal pilot** bartender redirect at payload offset `0x00145892`, and its context-specific flags and resource lifetime.
- Rendering under the bartender background and alternate scene/overlay MPR maps.
- Dialogues with timed waits, variable-width text, dynamic indexes, multiple redirects, Japanese fallback immediately following the source restoration, choices, portrait/ADPCM synchronization, and save/reload.
- Game-wide Mission 0–8/ENDING handling and translations.
- A real Mesen trace of the **last** unread consumer through the source terminator and independent examination of BIOS error-return paths.

**Release gate remains closed.** Keep PR #42's original $7B P1 review thread unresolved until a natural bartender encounter and subsequent clean continuation are demonstrated. Do not distribute the diagnostic disc.

## Reproduce the controlled intro test without manual disc editing

From this branch, with the authenticated original CloneCD set, an installed
8×16 rasterization font, and Python 3.11+:

```bash
python -m cyber_oedo.runtime.mission0_pool_pilot \
  /path/to/original.ccd /path/to/new-diagnostic-output /path/to/font.ttf \
  --diagnostic-intro-redirect
```

The new **explicit opt-in** flag adds the proven early intro redirect to the
existing M0-B bartender pilot, but does **not** replace the normal bartender
redirect or enable it in release mode. It requires the original full Track 2
SHA-256, the exact recorded intro marker/record SHA-256 and untouched source
terminator. This modifies only a **fresh output disc copy**, never source files.

The generated manifest has `diagnostic_intro_redirect=true`,
`natural_bartender_certified=false`, and `release_enabled=false`.
Without the flag, the normal single-bartender pilot is unchanged.

Run the generated read-only Mesen Lua trace. Under the documented automation,
the intro diagnostic reaches $7B around emulated frame 5,008; frame timing
depends on controller events and emulator configuration. This is a
**diagnostic runtime path**, not proof that the true in-game bartender
conversation is navigable or completely translated.
