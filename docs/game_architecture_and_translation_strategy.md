# Game architecture and translation strategy

## Why this project uses staged reverse engineering

*Cyber City Oedo 808: Kemono no Alignment* is not organized like a modern
content-driven game with one script file, one text renderer, and one stable
resource table. The PC Engine CD program repeatedly loads overlays and
resource-specific data into the same logical address space. A logical CPU
address can therefore mean different code or data at different times. Text is
also split across several unrelated storage and rendering formats: marker-based
dialogue bytecode, fixed-size indexed records, row-addressed information
screens, opening dossier fields, mission resources, and graphics-backed text.

This architecture is workable for a 1991 CD game, but it is hostile to a modern
translation pipeline. The executable does not expose a single authoritative
text API. It mixes presentation, state, content, and control data closely, and
some apparently unused bytes are merely zero-filled or temporarily unused rather
than proven writable storage. Several resources use local pointer schemes and
runtime state that cannot be reconstructed safely from string scanning alone.

The practical consequences are important:

- the same logical HuC6280 address may belong to different overlays;
- finding Japanese text does not prove that the text is reachable in play;
- finding padding does not prove ownership of that padding;
- a zero byte may be a terminator or an operand depending on bytecode context;
- dynamic inserted names and labels can be selected from mutable runtime tables;
- changing renderer behavior globally can corrupt unrelated resources that share
  byte values but not semantics; and
- an emulator boot is evidence of playability, not proof that a patch preserved
  every resource contract.

The failed Stage-1 wide-text experiment demonstrated this directly. A global
escape-marker design treated byte patterns as if they had one meaning across the
loaded program. In practice, ordinary game data reused those patterns and the
experiment corrupted runtime state. The failure is retained as historical
evidence, but the design is abandoned.

## Tier model

The project therefore treats reverse engineering as a sequence of evidence
gates. A later tier may depend on claims established by an earlier tier, but it
must not silently upgrade a heuristic into a fact.

### Tier A — structural extraction

Tier A answers: **what bytes and records exist on the authenticated disc?**

It establishes disc geometry, source hashes, resource candidates, dialogue
bytecode structure, typed controls, source offsets, round-trip parsing, and a
translator-facing inventory. It deliberately distinguishes candidate ownership
from proven ownership.

### Tier B — runtime semantics

Tier B answers: **what does the game actually do with those bytes?**

It maps loaded modules, interpreter paths, indexed record tables, state writes,
stream pointers, font/glyph calls, and eventually VRAM destinations. Static
disassembly is source-guarded against the authenticated payload; live emulator
snapshots are additionally bank-aware so an address reused by another overlay
cannot be mistaken for the target routine.

Tier B is allowed to add analysis, validation, trace tooling, schemas, and patch
*plans*. It is not allowed to activate a game mutation merely because a region
looks empty or a code path seems plausible.

### Tier C — translation compiler and safe mutation

Tier C will answer: **how do we rebuild the game with complete English while
preserving the proven runtime contracts?**

Only after storage ownership, reachability, pointer updates, renderer behavior,
and scene lifetime are sufficiently proven should the project activate
relocation or engine changes. Every mutation should be source-guarded,
reproducible, bounded to reviewed sectors, and followed by structural and
emulator validation.

This tiering is intentionally conservative. It costs more analysis up front but
prevents the project from accumulating fragile one-off hex edits that happen to
work in one scene.

## Translation relationship to the OVA

The game belongs to the same *Cyber City Oedo 808* property as the three-part
OVA and shares its principal cast and setting. The English-language OVA is also
how many English-speaking players know the series. That makes the OVA an
important continuity and terminology reference, but not an authority that
replaces the Japanese game script.

The translation policy is therefore:

1. **Preserve established continuity names and terminology when they match the
   game.** Use familiar forms such as Sengoku, Benten, Gogul, Hasegawa, Okyo,
   and Varsus consistently unless game-specific evidence requires otherwise.
2. **Translate the game's Japanese source, not an English OVA script.** The
   game's plot, dialogue, state-dependent labels, and scene-specific wording are
   primary evidence. OVA dialogue should not be copied into unrelated game
   scenes merely because it sounds familiar.
3. **Match characterization rather than literal syntax.** Sengoku should read as
   terse, confrontational, and streetwise; Hasegawa as hard and authoritarian;
   Benten as controlled and economical; Gogul as technically competent and
   comparatively measured. Natural English is preferred over preserving
   Japanese word order.
4. **Use the English OVA as a tonal reference, not a license for invention.**
   The well-known English dub is freer and more profane than a literal
   translation. Where the Japanese game itself supports aggression, slang, or
   profanity, English can be forceful. New jokes, sexual language, insults, or
   plot information should not be imported solely because the dub used that
   style.
5. **Prefer recognized franchise wording when several faithful translations are
   possible.** Episode/media titles, organization names, recurring character
   names, and setting terms should align with established English usage when it
   does not distort the Japanese game text.
6. **Keep game-specific distinctions.** If the game uses a generic descriptor
   before a character is identified and later switches to a name through
   runtime state, the English build should preserve that discovery instead of
   flattening both states to the OVA-known name.
7. **Record uncertainty instead of normalizing it away.** A translator note is
   preferable to silently choosing an OVA term when the game's intended referent
   is unclear.

The result should feel like an English release of the same *Cyber City Oedo
808* world, not a subtitle transcript and not a fan rewrite of the English dub.
The OVA supplies continuity, voice, and audience expectations; the game supplies
the actual text to be translated.

## Engineering consequence for translation

Translation and reverse engineering are coupled in this title. A translator may
write natural English in the inventory before the final storage mechanism is
known, but insertion must preserve the runtime semantics discovered by the
engine work. Dynamic fields remain dynamic, control order remains explicit, and
longer English is solved through proven layout/relocation/renderer mechanisms
rather than by shortening every line to whatever happens to fit the Japanese
record.

That is why this repository separates:

- source extraction and inventory;
- semantic translation;
- runtime proof;
- layout/relocation planning; and
- final binary mutation.

The separation is not process overhead for its own sake. It is a response to a
game whose original architecture does not provide those boundaries for us.
