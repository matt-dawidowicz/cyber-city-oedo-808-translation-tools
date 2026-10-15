# Definitive translation second pass

Status: in progress, first context/grammar sweep completed.

The second pass is not constrained by byte length, record footprint, renderer width, or historical sector allocation. It targets meaning, scene context, grammar, continuity, terminology, and character performance.

## First sweep results

- 162 definitive-line revisions applied.
- 89 terminology/style repairs.
- 73 line-specific context/grammar/meaning corrections.
- 0 blank definitive lines after validation.

## Important corrections

- `基本的にはそうだ` corrected from **"Generally, no."** to **"Basically, yes."**
- `死刑か？` corrected from **"Death?"** to **"The death penalty?"**
- `済まないな、ありがとよ` corrected from **"Thanks. I owe you one."** to **"Sorry about that. Thanks."**
- `明日香は、走り去って行った。` corrected from **"Asuka ran away."** to **"Asuka took off at a run."**
- contextual sentence fragments spanning adjacent records were rewritten to read grammatically as a continuous thought.
- several literal or awkward investigative lines were naturalized without changing clue content.

## Terminology

- `旧市街` is normalized to **Old City** per the project style sheet.
- Sengoku's `ブリキ野郎` nickname is normalized to **Tin Bastard**.
- The explicit *Wizard of Oz* explanation still uses **Tin Man** when Varsus explains the nickname's likely source.
- `サイバーセキュリティ計画` is normalized to **Cyber Security Plan** / **CS Plan** rather than Project.

## Method

Each candidate is classified as:

1. rewrite;
2. retain as already correct;
3. requires full-scene/runtime verification.

Extra CD space is not treated as a reason to inflate every line. Deliberate terseness remains part of character voice, especially for Gogul, Hasegawa, and command/UI text.

## Next editorial sweep

Continue mission-by-mission through the remaining review queue with special attention to:

- omitted Japanese subjects resolved incorrectly in English;
- false polarity / negation;
- split-record sentence grammar;
- pronoun antecedents;
- reveal-order leakage;
- dialogue whose speaker was assigned only a generic voice;
- exposition compressed enough to lose causal or investigative logic;
- mid-line timing/control records that need explicit English anchors.


## Reproducible second-pass input gate

The reviewed Definitive Edition workbook, full-script TSV, and dialogue-only
TSV have separate, source-pinned SHA-256 values in
`cyber_oedo.text.definitive_script_compiler`. The archived September-24
`Final Localization` exporter is not re-keyed to the second-pass revisions.

For historical experimentation only, pass `--master-edition definitive`
to `python -m cyber_oedo.build.packed_dialogue_test`, using a TSV whose digest
matches the pinned Definitive full-script or spoken/narration digest. Its
`Definitive Localization` column is mapped into the packed proof's English
row model; only rows with independently supplied Mission-0-B overlay evidence
are eligible for insertion. Unreviewed or regenerated TSVs fail closed.

This source integration is independent of the unimplemented external-pool
runtime and does not certify the release text engine.
