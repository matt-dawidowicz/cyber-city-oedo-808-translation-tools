# Security policy

## Supported code

Security fixes should target the current `main` branch. The toolkit is not a
network service, but it processes binary files and creates output directories,
so malformed-input handling, path safety, and accidental source modification
still matter.

## Reporting a problem

Use a private GitHub security advisory when available. If private reporting is
not available, contact the repository maintainer through GitHub before posting
proof-of-concept details publicly.

Do not attach proprietary disc images, BIOS files, private filesystem paths, or
other copyrighted source material to a report. A minimal synthetic reproducer
is preferred.

## Scope priorities

High-priority reports include behavior that can:

- overwrite or modify a supplied source image unexpectedly;
- write outside an explicitly selected output directory;
- accept the wrong authenticated source and patch it as if it were supported;
- silently skip integrity failures while claiming a verified build; or
- execute unexpected code from crafted input or path names.

Translation wording, reverse-engineering hypotheses, and emulator compatibility
are project correctness issues rather than security vulnerabilities.
