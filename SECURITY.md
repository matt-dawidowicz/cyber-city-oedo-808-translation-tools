# Security policy

## Supported code

Security fixes target the current `main` branch. The restart baseline is a local
analysis toolkit, not a network service or a supported translation patcher. It
reads user-supplied binary data and writes derived analysis artifacts, so input
validation, path safety, and source-file immutability still matter.

## Reporting a problem

Use a private GitHub security advisory when available. If private reporting is
not available, contact the repository maintainer through GitHub before posting
proof-of-concept details publicly.

Do not attach proprietary disc images, BIOS files, private filesystem paths, or
other copyrighted source material. Prefer a minimal synthetic reproducer.

## Scope priorities

High-priority reports include behavior that can:

- overwrite or modify a supplied source image unexpectedly;
- write outside an explicitly selected output location;
- mis-handle crafted binary input in a way that corrupts unrelated files; or
- execute unexpected code from crafted input or path names.

Translation wording, reverse-engineering hypotheses, false-positive scan
results, and emulator compatibility are correctness issues rather than security
vulnerabilities unless they also cross a security boundary.
