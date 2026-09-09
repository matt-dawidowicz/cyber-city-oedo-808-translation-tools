"""Describe the maintained command surface without importing tool modules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """Describe one command exposed through the unified command."""

    name: str
    module: str
    summary: str
    group: str


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        "extract-track2-mode1",
        "extract_track2_mode1",
        "Extract the 2048-byte Mode 1 payload from the raw IMG.",
        "Pipeline",
    ),
    CommandSpec(
        "scan-track",
        "scan_track",
        "Build broad structural and string reconnaissance output.",
        "Pipeline",
    ),
    CommandSpec(
        "scan-likely-sjis",
        "scan_likely_sjis",
        "Find likely natural-language Shift-JIS runs.",
        "Pipeline",
    ),
    CommandSpec(
        "extract-dialogue",
        "extract_dialogue",
        "Extract structured dialogue records.",
        "Pipeline",
    ),
    CommandSpec(
        "extract-auxiliary-text",
        "extract_auxiliary_text",
        "Subtract dialogue ranges from broad text candidates.",
        "Pipeline",
    ),
    CommandSpec(
        "build-translation-inventory",
        "build_translation_inventory",
        "Build the translator-facing occurrence inventory.",
        "Pipeline",
    ),
    CommandSpec(
        "validate-translation-inventory",
        "validate_translation_inventory",
        "Validate a generated or translator-edited inventory.",
        "Pipeline",
    ),
    CommandSpec(
        "analyze-text-slots",
        "analyze_text_slots",
        "Measure named resource regions and likely padding tails.",
        "Pipeline",
    ),
    CommandSpec(
        "build-human-test-disc",
        "build_human_test_disc",
        "Build the authenticated stock-renderer human-test image.",
        "Pipeline",
    ),
    CommandSpec(
        "describe-contracts",
        "cyber_oedo.commands.describe_contracts",
        "Print versioned external data contracts as JSON.",
        "Automation",
    ),
    CommandSpec(
        "plan-human-test",
        "cyber_oedo.commands.plan_human_test",
        "Emit a no-disc hash-only human-test patch plan.",
        "Automation",
    ),
    CommandSpec(
        "inventory-summary",
        "cyber_oedo.commands.inventory_summary",
        "Summarize a translator inventory as stable JSON.",
        "Automation",
    ),
    CommandSpec(
        "disassemble-huc6280",
        "disassemble_huc6280",
        "Produce deterministic HuC6280 diagnostic disassembly.",
        "Diagnostics",
    ),
    CommandSpec(
        "clonecd-cue",
        "clonecd_cue",
        "Create a non-destructive CUE view of a CloneCD set.",
        "Diagnostics",
    ),
    CommandSpec(
        "render-pce-tiles",
        "render_pce_tiles",
        "Render PC Engine 4bpp tiles for visual inspection.",
        "Diagnostics",
    ),
    CommandSpec(
        "make-contact-sheet",
        "make_contact_sheet",
        "Combine diagnostic renders into a labeled contact sheet.",
        "Diagnostics",
    ),
    CommandSpec(
        "title-screen",
        "title_screen",
        "Generate or preview the clean replacement title asset.",
        "Diagnostics",
    ),
    CommandSpec(
        "scan-reversed-sjis",
        "scan_reversed_sjis",
        "Run the non-canonical reversed-code exploration scanner.",
        "Experimental",
    ),
    CommandSpec(
        "build-wide-engine-stage1",
        "build_wide_engine_stage1",
        "Build the isolated Stage 1 English text-engine experiment.",
        "Experimental",
    ),
)


def command_by_name(name: str) -> CommandSpec | None:
    """Return the command specification matching ``name``."""

    return next(
        (item for item in COMMANDS if item.name == name),
        None,
    )


def script_modules() -> tuple[str, ...]:
    """Return legacy top-level script modules in deterministic order."""

    return tuple(
        sorted(
            {
                item.module
                for item in COMMANDS
                if "." not in item.module
            }
        )
    )
