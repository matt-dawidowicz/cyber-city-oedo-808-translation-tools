# Definitive Edition master plan

This document supersedes the fixed-footprint translation strategy.

The project goal is to build the best English-language version of Cyber City OEDO 808: Attribute of the Beast that the PC Engine CD hardware can support while preserving source meaning, clue order, characterization, game logic, and audiovisual identity.

## Core rules

1. Japanese meaning and continuity are authoritative.
2. Approved English may be as long as necessary. Japanese byte counts, record sizes, text-box geometry, and sector allocations are not editorial constraints unless a proven engine contract makes them constraints.
3. Longer is not automatically better. Preserve deliberate terseness, especially Gogul, Hasegawa, UI commands, and hardboiled exchanges. Extra space restores nuance, not padding.
4. Use idiomatic American English with late-1980s/early-1990s cyberpunk pulp energy. No contemporary slang, memes, gratuitous profanity, fake noir, or unsupported exposition.
5. OVA/dub material informs performance and rhythm, never unsupported facts.
6. Engine and disc layout change to serve the translation, not the reverse.
7. Performance improvements are part of the edition: remove avoidable optical reloads, redundant waits, and oversized restores without changing intended behavior.
8. Every binary change remains source-guarded and independently disable-able until runtime-certified.

## Editorial authority

Use the existing Voice Bible, Translation Audit, story/continuity guide, original Japanese, and runtime scene order as controlling references.

Canonical terminology includes OEDO 808, Oriental Electric Darwinism Oasis, Cyber Police, Security Force, Special Investigations Bureau, Cyber Police Security Plan, Mobile Detective, Cyber Skyscraper, cyberoid, Old City, Public Terminal, Police ID, Cash Card, computer raid, system destruction, media-jacking, mech-jacking, and Tin Bastard.

Character targets remain: Sengoku hardboiled/abrasive with concern disguised as irritation; Gogul laconic and technical; Benten poised and dryly theatrical; Varsus hyperliteral and analytical; Hasegawa clipped institutional menace; Okyo warm and capable; Maya mature and cool; Makze cultivated authoritarian menace; Rudolf cocky field-agent charm; Tomomi controlled until late emotional exposure; Chang expert without caricature; Security Force crude and territorial; old broker sly and economical.

## Translation workflow

### Pass 1 - source and continuity
Verify Japanese meaning, speaker, scene, clue order, what each character knows, recurring terminology, and whether the line is mandatory/optional/repeated.

### Pass 2 - unconstrained performance rewrite
Rewrite only when accuracy, implication, characterization, rhythm, clue clarity, dramatic timing, atmosphere, continuity, or readability improves. No byte or box-width target is permitted.

### Pass 3 - scene pass
Read complete conversations in runtime order. Fix repeated sentence openings, awkward back-and-forth, pronoun ambiguity, over-repeated names, abrupt connective logic, clue clarity, and reveal leaks.

### Pass 4 - timing/control pass
For the 79 records with meaningful controls embedded between visible source runs, explicitly anchor waits, voice barriers, indirect-text calls, and input waits to the intended English phrase. Never place controls by byte percentage.

### Pass 5 - playthrough performance QA
Judge text in motion with voice playback, portraits, pauses, menus, and transitions. Runtime context overrides an isolated spreadsheet interpretation.

## Native English text engine

Release architecture:
- outer marker 27 28 retained;
- English-mode signature 7D 45;
- one byte per 8x16 English glyph;
- 22 ordinary English columns across the existing approximately 176-pixel dialogue field;
- three visible rows;
- automatic English wrapping;
- controls 21/2A/2F/3D/40/5C/7E preserved;
- Japanese records retain stock fallback;
- common atlas may also serve command UI and compatible information screens.

The packed two-character private-Shift-JIS renderer is historical/proof-only.

## CD resource policy

Do not hunt for tiny holes merely to preserve original sizes. For each resource prove its start LBA, sector span, exact byte length, destination RAM extent, pointer/offset width, MPR assumptions, downstream references, and CD-DA dependencies. If those fields are mutable, rebuild the resource at its natural English size.

Prefer resource-granularity rebuilding over string-by-string relocation: parse the resource, compile all translated records, lay out a new resource image, rebuild internal offsets, assign a new CD extent, update the descriptor/caller, and move later resources as required.

## Track-2 resource linker

Build a deterministic resource graph containing resource identity, original LBA/span/length, references/callers, internal record graph, translated size, alignment, RAM destination contract, and relocatability. The linker assigns new LBAs after compilation. Every absolute LBA must be represented as a relocation. Regenerate Mode-1 EDC/ECC after link.

## Opening narration

KURUZER is the first end-to-end target. Compile the complete approved narration through the native English engine, preserve intentional thought/page boundaries, allow the resource to grow beyond its historical extent, prove its loader/source reference, update length/span/LBA data, and verify the following resource still loads. The narration is not to be shortened to 696 bytes.

## Conversation choices and icons

Treat command/system UI as a separate client of the English typography layer. Preserve command IDs, gameplay metadata, and useful existing pictograms. Rewrite label storage to variable-length/indexed English strings and render labels with the native atlas. Do not redraw icons unless they contain Japanese text.

## Dynamic labels

Replace fixed 13-byte Shift-JIS slots with an English label pool. Fixed metadata/state records retain stable identity; text fields become pointer/offset/index references to variable-length English strings. Preserve opcode 3D semantics.

## Other text families

Startup/save/memory UI, opening dossiers, Media Mix, OEDONET/information pages, mission titles, ending/save-completion, and credits keep their proven interpreters where useful but may reuse the English atlas. Graphics-backed title presentation stays a graphics pipeline.

## Load-time redesign

### Dialogue entry
Combine resident dialogue module, speaker-local data, portrait data, and ADPCM blocks into a permanent Super System Card cache manager with cache validity/signatures and stock CD fallback.

Independent measured wins already include portrait cache about 1.58 s, ADPCM cache about 0.43 s, resident module about 0.57-0.63 s, and speaker-local retention about 0.20 s warm. Re-measure the permanent combined path; do not simply add these numbers.

### Setup waits
Profile the approximately 64 consecutive VSync calls (about 1.07 s) and replace fixed waits with completion conditions where safe.

### Dialogue return
Replace the giant CD-based exploration VRAM restore with Card-RAM-backed preservation of only dialogue-clobbered exploration regions. The existing selective CD restore remains a fallback/proof.

### Audio teardown
Measure the 127-frame bartender fade-clear path and separate actual audio completion from conservative waiting.

### Optical layout
Once resources are rebuildable, physically cluster high-frequency related resources (room, dialogue module, speaker data, portrait, ADPCM, return data) to reduce seek latency. CD layout becomes a performance variable.

## Quality-of-life improvements

Allowed when they preserve intended design: faster text speed and responsive skip, readable English command labels, consistent terminology, improved line/page breaks, removal of avoidable multi-second loading pauses, clear save/load messaging, restoration of clues previously compressed, clearer database/news formatting, and bug fixes proven to contradict intended behavior.

Do not redesign puzzles, reorder clues, remove intentional ambiguity, or add story facts without a separate design decision.

## Build layers

Keep independently switchable layers: translation-native-engine, resource-rebuild, load-cache, fast-return, audio-wait-cleanup, ui-english, bugfixes, and cosmetic-title. A release candidate combines only certified layers.

## Release gates

A definitive build requires: complete continuity audit; complete style-guide pass; all 79 semantic-control records anchored; native English renderer certified across Mission 0-8; all translated resources linked without hidden fixed-size assumptions; full Mission 0-8 playthrough; command/menu/information text verification; ending and credits verification; save/reload across mission boundaries; CD audio continuity; no stale absolute-LBA references; full sector-change manifest; before/after load-time benchmarks; and no line shortened solely for technical fit.
