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
        "cyber_oedo.disc.extract_track2_mode1",
        "Extract the 2048-byte Mode 1 payload from the raw IMG.",
        "Pipeline",
    ),
    CommandSpec(
        "analyze",
        "cyber_oedo.analysis.pipeline",
        "Run the consolidated Tier-A translation analysis pipeline.",
        "Pipeline",
    ),
    CommandSpec(
        "build-resource-map",
        "cyber_oedo.analysis.build_resource_map",
        "Map every sector-aligned candidate resource region.",
        "Pipeline",
    ),
    CommandSpec(
        "scan-likely-sjis",
        "cyber_oedo.analysis.scan_likely_sjis",
        "Find likely natural-language Shift-JIS runs.",
        "Pipeline",
    ),
    CommandSpec(
        "extract-dialogue",
        "cyber_oedo.text.extract_dialogue",
        "Extract structured dialogue records.",
        "Pipeline",
    ),
    CommandSpec(
        "extract-auxiliary-text",
        "cyber_oedo.text.extract_auxiliary_text",
        "Subtract dialogue ranges from broad text candidates.",
        "Pipeline",
    ),
    CommandSpec(
        "build-translation-inventory",
        "cyber_oedo.text.build_translation_inventory",
        "Build the translator-facing occurrence inventory.",
        "Pipeline",
    ),
    CommandSpec(
        "validate-translation-inventory",
        "cyber_oedo.text.validate_translation_inventory",
        "Validate a generated or translator-edited inventory.",
        "Pipeline",
    ),
    CommandSpec(
        "analyze-text-slots",
        "cyber_oedo.analysis.analyze_text_slots",
        "Measure named resource regions and likely padding tails.",
        "Pipeline",
    ),
    CommandSpec(
        "build-human-test-disc",
        "cyber_oedo.build.human_test",
        "Build the authenticated stock-renderer human-test image.",
        "Pipeline",
    ),
    CommandSpec(
        "build-analysis-db",
        "cyber_oedo.analysis.build_analysis_db",
        "Build a local SQLite database from generated evidence.",
        "Automation",
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
        "scan-track",
        "cyber_oedo.analysis.scan_track",
        "Build optional broad ASCII/SJIS/sector reconnaissance output.",
        "Diagnostics",
    ),
    CommandSpec(
        "disassemble-huc6280",
        "cyber_oedo.commands.disassemble_region",
        "Produce deterministic HuC6280 diagnostic disassembly.",
        "Diagnostics",
    ),
    CommandSpec(
        "prove-dialogue-runtime",
        "cyber_oedo.runtime.dialogue_interpreter",
        "Validate source-guarded Tier-B dialogue runtime evidence.",
        "Diagnostics",
    ),
    CommandSpec(
        "prove-live-dialogue-snapshot",
        "cyber_oedo.runtime.live_snapshot",
        "Validate a bank-aware frozen Mission 0 3D debugger snapshot.",
        "Diagnostics",
    ),
    CommandSpec(
        "prove-text-renderer-runtime",
        "cyber_oedo.runtime.text_renderer",
        "Validate the source-guarded Mission 0 stock text renderer.",
        "Diagnostics",
    ),
    CommandSpec(
        "prove-movement-runtime",
        "cyber_oedo.runtime.movement",
        "Validate source-guarded exploration movement evidence.",
        "Diagnostics",
    ),
    CommandSpec(
        "prove-game-architecture",
        "cyber_oedo.runtime.game_architecture",
        "Validate the cross-overlay runtime architecture map.",
        "Diagnostics",
    ),
    CommandSpec(
        "prove-text-engine-coverage",
        "cyber_oedo.runtime.text_engine_coverage",
        "Validate game-wide dialogue and non-dialogue text families.",
        "Diagnostics",
    ),
    CommandSpec(
        "prove-text-engine-completion",
        "cyber_oedo.runtime.text_engine_completion",
        "Validate information-page commands and resource ownership.",
        "Diagnostics",
    ),
    CommandSpec(
        "diff-live-state",
        "cyber_oedo.runtime.state_diff",
        "Compare two bank-aware frozen runtime snapshots.",
        "Diagnostics",
    ),
    CommandSpec(
        "analyze-cd-loads",
        "cyber_oedo.runtime.cd_load_profile",
        "Analyze Mesen CD_READ traces for repeated load-time work.",
        "Diagnostics",
    ),
    CommandSpec(
        "analyze-cd-transitions",
        "cyber_oedo.runtime.load_transition_profile",
        "Measure full Mission 0 CD-load-to-dialogue latency.",
        "Diagnostics",
    ),
    CommandSpec(
        "analyze-dialogue-load-architecture",
        "cyber_oedo.runtime.dialogue_load_architecture",
        "Map Mission 0 dialogue/audio/portrait load layout.",
        "Diagnostics",
    ),
    CommandSpec(
        "analyze-dialogue-residency",
        "cyber_oedo.runtime.dialogue_residency",
        "Map dialogue-bank residency, audio state, voices, and VRAM overlap.",
        "Diagnostics",
    ),
    CommandSpec(
        "analyze-vram-dirty",
        "cyber_oedo.runtime.vram_dirty_profile",
        "Measure selective exploration-VRAM restore cost from Mesen logs.",
        "Diagnostics",
    ),
    CommandSpec(
        "analyze-transition-budget",
        "cyber_oedo.runtime.transition_budget",
        "Attribute dialogue transition latency from Mesen budget logs.",
        "Diagnostics",
    ),
    CommandSpec(
        "analyze-adpcm-memory",
        "cyber_oedo.runtime.adpcm_memory_architecture",
        "Map Mission 0 ADPCM snapshot and RAM-transfer architecture.",
        "Diagnostics",
    ),
    CommandSpec(
        "plan-card-ram-cache",
        "cyber_oedo.runtime.card_ram_cache_plan",
        "Plan an AD_WRITE-friendly Mission 0 Super System Card cache layout.",
        "Diagnostics",
    ),
    CommandSpec(
        "analyze-cd-hot-assets",
        "cyber_oedo.runtime.cd_load_optimization",
        "Measure hot scene assets and candidate load compression.",
        "Diagnostics",
    ),
    CommandSpec(
        "analyze-scene-seeks",
        "cyber_oedo.runtime.scene_seek_geometry",
        "Measure static seek geometry of hot exploration scene bundles.",
        "Diagnostics",
    ),
    CommandSpec(
        "clonecd-cue",
        "cyber_oedo.disc.clonecd_cue",
        "Create a non-destructive CUE view of a CloneCD set.",
        "Diagnostics",
    ),
    CommandSpec(
        "render-pce-tiles",
        "cyber_oedo.graphics.render_pce_tiles",
        "Render PC Engine 4bpp tiles for visual inspection.",
        "Diagnostics",
    ),
    CommandSpec(
        "make-contact-sheet",
        "cyber_oedo.graphics.make_contact_sheet",
        "Combine diagnostic renders into a labeled contact sheet.",
        "Diagnostics",
    ),
    CommandSpec(
        "title-screen",
        "cyber_oedo.graphics.title_screen",
        "Generate or preview the clean replacement title asset.",
        "Diagnostics",
    ),
)


def command_by_name(name: str) -> CommandSpec | None:
    """Return the command specification matching ``name``."""

    return next((item for item in COMMANDS if item.name == name), None)


def command_modules() -> tuple[str, ...]:
    """Return canonical package command modules in deterministic order."""

    return tuple(sorted({item.module for item in COMMANDS}))
