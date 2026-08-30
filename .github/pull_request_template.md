## Summary

Describe the problem and the smallest behavior change needed to solve it.

## Validation

- [ ] `python -m unittest discover -s tests -v`
- [ ] `python -m compileall -q .`
- [ ] `python -m cyber_oedo doctor`
- [ ] Generated inventories were compared when parsing or heuristics changed.
- [ ] Real-disc validation was run when patch coordinates or image logic changed.

## Safety and compatibility

- [ ] The source disc image remains read-only.
- [ ] Existing script entry points remain compatible or have a migration note.
- [ ] Confirmed facts remain separate from heuristics and hypotheses.
- [ ] No copyrighted disc image, BIOS, generated full-text dump, or audio was added.
- [ ] Runtime claims are backed by runtime evidence rather than static inference.
