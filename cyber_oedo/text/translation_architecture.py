"""Translation ownership and mutation strategy derived from Tier A/B evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class TranslationFamilyPlan:
    family: str
    storage_owner: str
    renderer: str
    mutation_strategy: str
    relocation_unit: str
    live_gate: str
    activation: str


TRANSLATION_FAMILY_PLANS = (
    TranslationFamilyPlan(
        "common_dialogue",
        "owning mission resource/script stream",
        "shared M0-M8 stock Shift-JIS renderer",
        "compile controls explicitly; relocate only at a proven resource/script ownership boundary",
        "whole owning record or script structure, never a blind byte substring",
        "representative M0 parser/renderer/glyph path captured; later mission bank mapping still requires representative captures",
        "planning_only_until_destination_ownership_and_scene_lifetime_are_proven",
    ),
    TranslationFamilyPlan(
        "dynamic_labels",
        "24 x 32-byte indexed table loaded to $A400",
        "opcode 3D -> common stock renderer",
        "preserve both text slots and state bytes; do not flatten discovery-state alternates",
        "complete indexed table/load contract",
        "M0 loader/state selection statically proven; representative live state evidence exists, later mission lifetime still gated",
        "fixed_slot_edits_only_unless_table_relocation_is_proven",
    ),
    TranslationFamilyPlan(
        "command_system_ui",
        "37 x 16-byte common overlay table",
        "overlay-local UI path",
        "preserve per-entry metadata; use same-size text where possible, otherwise relocate the complete table only after caller/ownership proof",
        "complete 37-entry table",
        "cross-overlay bytes proven; representative live UI caller capture still required before relocation",
        "same_size_only",
    ),
    TranslationFamilyPlan(
        "startup_information_and_dossiers",
        "row-addressed startup presentation streams",
        "startup information/dossier renderer",
        "row reflow is permitted through source-guarded records; preserve binary formatting records exactly",
        "one complete presentation page/stream",
        "existing stock-renderer human-test path provides practical startup coverage; new layout still needs replay",
        "guarded_same_size_and_row_reflow",
    ),
    TranslationFamilyPlan(
        "resource_local_ui",
        "named mission resource",
        "resource-specific UI caller",
        "patch only within the named resource until its exact caller/load lifetime is proven; never borrow neighboring padding",
        "complete named resource region",
        "per-family caller/MPR capture required for relocation or renderer changes",
        "same_size_only",
    ),
    TranslationFamilyPlan(
        "ending_oedonet",
        "ENDING OEDONET presentation stream",
        "ENDING row-addressed presentation renderer",
        "preserve every formatting record and rewrite only decoded text payloads/coordinates",
        "complete OEDONET page stream",
        "ENDING-specific live renderer/MPR capture required before growth or relocation",
        "same_size_or_row_reflow_only",
    ),
    TranslationFamilyPlan(
        "ending_completion_save",
        "ENDING mixed opcode stream",
        "ENDING Shift-JIS presentation paths",
        "preserve opcode/position bytes; replace only null-terminated text payloads unless complete stream relocation is proven",
        "complete FF-terminated ending stream",
        "ENDING-specific live capture required before growth or relocation",
        "same_size_only",
    ),
    TranslationFamilyPlan(
        "ending_credits",
        "ENDING opcode-2 ASCII records",
        "ENDING fixed-width ASCII path",
        "translate as ASCII while preserving opcode, coordinates, terminators, and available record capacity",
        "individual opcode-2 record or complete FF-terminated stream",
        "ENDING replay required for final layout certification",
        "same_size_ascii_ready",
    ),
    TranslationFamilyPlan(
        "graphics_backed",
        "explicit authenticated graphic asset",
        "tile/graphic presentation",
        "replace through the graphics encoder/profile for that exact asset; never route through text relocation",
        "complete graphic asset plus palette contract",
        "visual replay required",
        "asset_specific",
    ),
)


def build_translation_architecture() -> dict[str, object]:
    return {
        "policy": {
            "default": "preserve stock renderer and storage contract",
            "no_global_escape_marker": True,
            "no_padding_as_ownership": True,
            "no_cross_resource_borrowing": True,
            "growth_requires": [
                "complete reachability proof",
                "complete destination ownership proof",
                "load/lifetime proof",
                "all pointer/length sites mapped",
                "bank/address-window proof",
                "source guards for old and destination bytes",
                "focused emulator replay",
            ],
        },
        "families": [asdict(plan) for plan in TRANSLATION_FAMILY_PLANS],
        "recommended_final_architecture": (
            "family-specific compilers feeding one guarded patch plan; retain the "
            "stock renderer by default and introduce relocation only at proven "
            "ownership units rather than through a game-wide text escape mechanism"
        ),
    }
