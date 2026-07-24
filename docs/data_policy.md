# Data and rights policy

## Purpose

This repository documents original reverse-engineering research and provides
tools that operate on a user-supplied copy of *Cyber City Oedo 808: Kemono no
Alignment* for PC Engine CD.

It is not a game distribution and is not affiliated with or endorsed by the
game's developers, publishers, or current rights holders.

## Content allowed in the repository

- original Python source code;
- original documentation and format descriptions;
- synthetic tests and synthetic binary fixtures;
- cryptographic hashes used to identify the analyzed release;
- small excerpts necessary to explain findings or localization context; and
- patch-development metadata that does not reconstruct the original game.

## Content excluded from the repository

- original or modified disc images;
- `.ccd`, `.img`, `.sub`, `.cue`, `.iso`, `.chd`, or raw `.bin` images;
- extracted program/data-track payloads;
- audio tracks;
- emulator BIOS or System Card images;
- full dialogue/text dumps and generated translation inventories;
- decompressed graphics, tile dumps, and bulk screenshots; and
- files that allow substantial reconstruction of copyrighted game content.

The root `.gitignore` blocks common forms of these files. Contributors must
still review staged changes because ignore rules cannot identify every renamed
or repackaged asset.

## Local workflow

Users provide their own legally obtained CloneCD image and run the documented
extractors and scanners locally. Generated TSVs and renders stay outside source
control. The human-test builder also produces a complete modified CloneCD set;
that build directory must remain local and excluded from source control.

A future translation release should distribute a patch against a hash-identified
source, not a modified disc image. `build_manifest.json` may be shared after
reviewing it for local paths, but it does not replace that patch format.

## Reporting issues

When filing an issue:

- include offsets, hashes, short hexadecimal excerpts, and tool output needed
  to reproduce the problem;
- do not attach complete disc sectors, audio, BIOS files, or large text dumps;
  and
- redact local paths or account information when they are irrelevant.

## Licensing status

No open-source license has been selected for this repository yet. Copyright in
the original code and documentation remains with their author until a license
is added. Third-party game content remains the property of its respective
rights holders.
