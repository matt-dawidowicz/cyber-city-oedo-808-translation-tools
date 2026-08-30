# Toolkit release checklist

Use this checklist for a tooling release. Translation build-profile milestones
and emulator/runtime certification are related but separate concerns.

## Before tagging

- [ ] `CHANGELOG.md` describes user-visible tooling changes.
- [ ] The toolkit version is updated deliberately and is not confused with a
      translation profile name.
- [ ] `python -m unittest discover -s tests -v` passes.
- [ ] `python -m compileall -q .` passes.
- [ ] `python -m cyber_oedo doctor` reports no failures.
- [ ] Wheel and source-distribution builds complete from a clean checkout.
- [ ] The installed wheel can run `cyber-oedo --help` outside the source tree.
- [ ] Documentation reflects the installed command surface.
- [ ] No disc images, BIOS files, extracted full-text data, or generated game
      assets are included in release artifacts.

## When binary behavior changed

- [ ] Synthetic regression coverage demonstrates the new rule.
- [ ] Real-disc regenerated artifacts were compared to the prior baseline.
- [ ] Changed record counts, offsets, sectors, or hashes are explained.
- [ ] Source authentication still rejects unsupported images.
- [ ] Patch guards and raw-sector EDC/ECC validation still pass.
- [ ] Runtime-only claims have explicit runtime evidence.

## Release artifacts

- [ ] Tag the exact reviewed commit.
- [ ] Record SHA-256 hashes for published archives.
- [ ] Keep the source-only/legal-data boundary explicit in release notes.
- [ ] Link any runtime validation report needed to interpret the release.

## After release

- [ ] Verify installation instructions from the published artifact.
- [ ] Move completed entries out of the `Unreleased` changelog section.
- [ ] Open follow-up issues for deferred compatibility or architecture work.
