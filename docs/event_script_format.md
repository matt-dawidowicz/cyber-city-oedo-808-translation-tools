# Mission 0-B event-script format

Status: interpreter decoded and source-guarded; parser validated on every
Mission 0-B event resource; relinking validated statically on all 41
dialogue-bearing resources. Implementation: `cyber_oedo/script/event.py`.

Scene and conversation resources (`KURUZER`, `ZAKO0001`, `MAYA01`, …) are
small event programs. Dialogue records are inline in them, and the program
moves between commands with **relative** offsets, so a translated record can
grow only if every offset that spans it is rewritten. This is what the
resource linker needs before any resource other than the opening narration
can carry longer English.

## Resident body layout

The loader strips the 16-byte resource header (see `named_resource_linker.md`).
The resident body is:

| Part | Format |
|---|---|
| entry table | 7-byte entries: 5 condition bytes, then a big-endian offset measured **from the offset field itself**. Entry 0 is `FF FE 00 FF FE` and points at the script start; other entries point at per-topic handlers. The table ends at the first entry whose first two bytes are zero; that entry's offset points at the label table (walker `$9E39`). |
| label table | 14-byte topic labels: flag byte (`$9DB9` sets bit 0 when a topic is learned) and a 13-byte Shift-JIS name. |
| script | handlers, each a command sequence ending in `00`. |
| tail | up to 15 never-executed bytes: descriptor lengths are 16-byte multiples, so some resources end in stale padding or a cut-off copy of a handler. |

The game reads entries' bytes 0-4 (`$75F8-$7610`, `$9E40`) as conditions;
bytes 5-6 are the offsets.

## Interpreter

Script pointer: zero page `$7F/$80`. `$9F11` reads the current byte and `$9F14`
advances. The dispatch table at `$9048` (opcode, handler) has 27 commands;
`$9013` runs a handler until it reads `00`.

Operand helpers:

- `$9648` WORD: big-endian 16-bit.
- `$962B` VALUE: tag byte then WORD; tag `01` reads a variable, any other tag
  is an immediate.
- `$97AC` EXPR: tokens from the table at `$97D1` until `26`. Tokens `01`,
  `03`, `31`, `2F`, `37` take a WORD; `3F` takes one byte; the operators
  `10-16`, `19`, `1A-1E`, `3B` take none.

| Opcode | Handler | Operands |
|---|---|---|
| `00` | — | end of handler |
| `06` | `$94CC` | WORD variable, EXPR (assignment) |
| `22`, `23` | `$9194`, `$91A4` | WORD variable (increment / decrement) |
| `24` | `$94E2` | EXPR, then offset: **IF** — when false, pointer += offset |
| `27` | `$9534` | one byte; `27 28` starts a dialogue record parsed to its `00` |
| `2B`, `35`, `4B` | | none |
| `2D` | `$9516` | offset: **GOTO** — pointer += offset (16-bit wrap) |
| `2E`, `2F`, `38`, `3B`, `3C` | | one byte (flag operations) |
| `30` | `$9173` | name up to NUL; the pointer is left on the NUL, ending the handler (chain) |
| `32` | `$909C` | index, last index, wrap mode; then `last index + 1` blocks, each a big-endian length and body (**rotating choice**; the handler writes the next index back into the script) |
| `33`, `34`, `44`, `47` | | VALUE |
| `36`, `3A` | `$9703`, `$9659` | NUL-terminated name (load/call another resource; pointer corrected for heap compaction) |
| `46` | `$93B6` | 3 × VALUE |
| `48` | `$941F` | 2 × VALUE, plus a third VALUE when the second's low byte is 2 |
| `49` | `$91B7` | 4 × VALUE |
| `4A` | `$92DF` | 5 × VALUE |
| `4C` | `$9202` | EXPR, EXPR |

IF and GOTO offsets are measured from the byte after the offset field; a
choice block's length is the size of its body.

`48` is the only data-dependent shape. The parser accepts it only when the
second VALUE is an immediate, and fails closed when it is a variable.

## Validation (authenticated Track 2)

- Interpreter guards match: dispatch and expression tables, fetch/advance,
  operand helpers, IF, GOTO, dialogue, choice skip and entry walker.
- 44 of 48 Mission 0-B resources are event programs; all 44 parse
  completely. The other four (`CMDDIC`, `OBJDIC`, `VARIABLE`, `MESSAGE`) are
  data tables.
- Every IF, GOTO, choice-length and entry offset lands on a command boundary.
- An unchanged relink is byte-identical for all 44.
- The parser finds every dialogue record that the plain marker scan finds,
  plus one in `BILL4`; `MAYA01`'s one "missing" record is the cut-off copy in
  its stale tail.
- Doubling every dialogue record in each of the 41 dialogue-bearing
  resources (e.g. `TERM` 5,968 → 10,708 bytes, `HOAN1` 3,024 → 5,390) and
  re-parsing reproduces every offset's target command, every record position
  and the tail.

## Not yet established

- Other overlays: Missions 1-8 likely share the interpreter, but their copies
  are not yet guarded or parsed.
- Whether `3A`/`36`-loaded resources share any state that depends on byte
  positions in the caller.
