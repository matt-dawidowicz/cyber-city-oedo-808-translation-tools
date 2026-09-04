# Data and rights policy

## Purpose

This repository contains original reverse-engineering research and tools that
operate on a user-supplied copy of *Cyber City Oedo 808: Kemono no Alignment*
for PC Engine CD. It is not a game distribution and is not affiliated with or
endorsed by the game's developers, publishers, or rights holders.

## Allowed repository content

- original source code and documentation;
- synthetic tests and synthetic binary fixtures;
- cryptographic hashes identifying analyzed source data;
- offsets, lengths, format descriptions, and compact research metadata;
- small excerpts necessary to explain a technical finding; and
- narrowly scoped evidence that cannot reconstruct substantial game content.

## Excluded repository content

Do not commit:

- original or modified disc images;
- `.ccd`, `.img`, `.sub`, `.cue`, `.iso`, `.chd`, or raw extracted `.bin`
  images;
- extracted program/data-track payloads or audio tracks;
- emulator BIOS or System Card images;
- complete dialogue dumps or generated translation inventories;
- decompressed graphics dumps or bulk screenshots; or
- files that permit substantial reconstruction of copyrighted game content.

`.gitignore` blocks common forms of local artifacts, but contributors must still
review staged changes.

## Local workflow

Use a legally obtained source image locally. Extracted payloads, generated TSVs,
renders, traces, and emulator evidence stay outside source control unless they
have been reduced to compact non-infringing metadata suitable for the evidence
directory.

If a future translation release is produced, distribute a patch against a
hash-identified source rather than a modified disc image.

## Reporting issues

Include hashes, offsets, short hexadecimal excerpts, and synthetic reproducers
where possible. Do not attach complete sectors, disc images, audio, BIOS files,
or private filesystem paths when they are unnecessary.

## Licensing

The repository's original code and documentation are licensed under the MIT
License. Third-party game content remains the property of its respective rights
holders and is not covered by that license.
