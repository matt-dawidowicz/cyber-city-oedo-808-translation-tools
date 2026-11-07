"""Build a diagnostic disc with English in several Mission 0-B event resources.

For each named resource, every page-only dialogue record that has English is
recompiled for the stock fullwidth renderer, the event script is relinked
around the new record sizes, and all rebuilt resources are linked back to back
into the owned end-of-Track-2 window.  Load addresses come from the observed
route load order with the new lengths, so the build fails if the route would
need heap compaction.

English is read from a UTF-8 TSV with a ``payload_offset`` column (the
``27 28`` marker's Track 2 payload offset, hex or decimal) and an ``english``
column.  It is never stored in the repository.  Records with other controls,
or whose English cannot keep the source page breaks, stay Japanese and are
listed in the manifest.  Not release-enabled.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pathlib
import shutil
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from cyber_oedo.build.image_verify import compare_and_hash_raw_images, verify_output_patches
from cyber_oedo.build.profiles import mission0_stock as stock_profile
from cyber_oedo.build.source import copy_authenticated_source_set
from cyber_oedo.disc.extract_track2_mode1 import extract_mode1_payload
from cyber_oedo.disc.game_layout import TRACK2_SECTOR_COUNT, TRACK2_START_LBA
from cyber_oedo.disc.named_resources import (
    MISSION0_STREET_ROUTE,
    RESOURCE_HEADER_BYTES,
    NamedResourceDescriptor,
    find_descriptor,
    parse_mission0_b_descriptors,
    predict_heap_addresses,
)
from cyber_oedo.disc.patching import apply_payload_patches
from cyber_oedo.disc.resource_linker import RelinkRequest, relink_named_resources
from cyber_oedo.script.event import parse_event_resource, rebuild_event_resource, verify_event_interpreter
from cyber_oedo.text.stock_english import StockEnglishError, compile_stock_record

BUILD_PROFILE = "mission0-english-resources-test"
OUTPUT_STEM = "Cyber City Oedo 808 - Kemono no Alignment (Japan) [English resources test]"
TRACK2_PAYLOAD_SHA256 = "0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223"


@dataclass(frozen=True, slots=True)
class RecordOutcome:
    resource: str
    payload_offset: int
    status: str
    source_bytes: int
    english_bytes: int | None = None
    detail: str = ""


@dataclass(frozen=True, slots=True)
class EnglishResource:
    descriptor: NamedResourceDescriptor
    data: bytes
    outcomes: tuple[RecordOutcome, ...]


def load_english_tsv(path: pathlib.Path) -> dict[int, str]:
    """Read ``payload_offset`` -> English, rejecting duplicate offsets."""

    english: dict[int, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if not reader.fieldnames or not {"payload_offset", "english"} <= set(reader.fieldnames):
            raise ValueError("English TSV needs payload_offset and english columns")
        for row in reader:
            offset = int(row["payload_offset"], 0)
            if offset in english:
                raise ValueError(f"duplicate payload_offset 0x{offset:08X}")
            text = " ".join((row["english"] or "").split())
            if text:
                english[offset] = text
    return english


def english_resource(
    payload: bytes,
    descriptor: NamedResourceDescriptor,
    english: Mapping[int, str],
) -> EnglishResource:
    """Recompile every page-only record with English and relink the script."""

    start = descriptor.resource_payload_offset
    resource = payload[start : start + descriptor.byte_length]
    layout = parse_event_resource(resource)
    body_base = start + RESOURCE_HEADER_BYTES
    replacements: dict[int, bytes] = {}
    outcomes: list[RecordOutcome] = []
    for span in layout.dialogue:
        marker = body_base + span.start
        source = layout.body[span.start : span.end]
        text = english.get(marker)
        if text is None:
            outcomes.append(RecordOutcome(descriptor.name, marker, "no_english", len(source)))
            continue
        try:
            record = compile_stock_record(source, text)
        except StockEnglishError as error:
            outcomes.append(RecordOutcome(descriptor.name, marker, "kept_japanese", len(source), detail=str(error)))
            continue
        replacements[span.start] = record
        outcomes.append(RecordOutcome(descriptor.name, marker, "english", len(source), len(record)))
    return EnglishResource(descriptor, rebuild_event_resource(resource, replacements), tuple(outcomes))


def plan_english_resources(
    payload: bytes,
    english: Mapping[int, str],
    resource_names: Sequence[str],
    route: Sequence[str] = MISSION0_STREET_ROUTE,
):
    """Rebuild *resource_names* and relink them with route-predicted addresses."""

    verify_event_interpreter(payload)
    descriptors = parse_mission0_b_descriptors(payload)
    missing = [name for name in resource_names if name not in route]
    if missing:
        raise ValueError(f"resources {missing} are not on the certified route {list(route)}")
    rebuilt = {
        name: english_resource(payload, find_descriptor(descriptors, name), english)
        for name in resource_names
    }
    lengths = tuple(
        (name, len(rebuilt[name].data) if name in rebuilt else find_descriptor(descriptors, name).byte_length)
        for name in route
    )
    addresses = predict_heap_addresses(lengths)
    relinks = relink_named_resources(
        payload,
        tuple(
            RelinkRequest(item.descriptor, item.data, addresses[name])
            for name, item in rebuilt.items()
        ),
    )
    return rebuilt, addresses, relinks


def build_english_resources_test(
    source_ccd: pathlib.Path,
    output_directory: pathlib.Path,
    english_tsv: pathlib.Path,
    resource_names: Sequence[str],
    route: Sequence[str] = MISSION0_STREET_ROUTE,
) -> pathlib.Path:
    english = load_english_tsv(english_tsv)
    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise ValueError(f"output directory already exists: {output_directory}")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = pathlib.Path(
        tempfile.mkdtemp(dir=output_directory.parent, prefix=f".{output_directory.name}.")
    )
    try:
        source_paths, output_paths = copy_authenticated_source_set(
            source_ccd, temporary, OUTPUT_STEM, stock_profile.SOURCE_HASHES
        )
        payload_path = temporary / "track02_mode1_2048.bin"
        _, payload_sha = extract_mode1_payload(
            source_paths[".img"], payload_path,
            start_lba=TRACK2_START_LBA, sector_count=TRACK2_SECTOR_COUNT,
        )
        if payload_sha != TRACK2_PAYLOAD_SHA256:
            raise ValueError(f"Track 2 payload hash mismatch: {payload_sha}")
        payload = payload_path.read_bytes()
        rebuilt, addresses, relinks = plan_english_resources(payload, english, resource_names, route)
        patches = tuple(patch for relink in relinks for patch in relink.patches)

        reports = apply_payload_patches(
            output_paths[".img"], patches,
            start_lba=TRACK2_START_LBA, sector_count=TRACK2_SECTOR_COUNT,
            atomic=False,  # The whole output directory is staged.
        )
        verify_output_patches(output_paths[".img"], patches, start_lba=TRACK2_START_LBA)
        comparison = compare_and_hash_raw_images(source_paths[".img"], output_paths[".img"])
        expected = tuple(r.absolute_lba for r in reports if r.before_sha256 != r.after_sha256)
        if comparison.changed_lbas != expected:
            raise ValueError(
                f"unexpected changed sectors: expected {expected}, found {comparison.changed_lbas}"
            )

        outcomes = [outcome for item in rebuilt.values() for outcome in item.outcomes]
        manifest = {
            "build_profile": BUILD_PROFILE,
            "release_enabled": False,
            "english_tsv_sha256": hashlib.sha256(english_tsv.read_bytes()).hexdigest(),
            "route": list(route),
            "predicted_load_addresses": {name: f"0x{address:04X}" for name, address in addresses.items()},
            "resources": [
                {
                    "name": relink.descriptor.name,
                    "original_lba": f"0x{relink.descriptor.absolute_lba:04X}",
                    "original_length": relink.descriptor.byte_length,
                    "relinked_lba": f"0x{relink.linked.start_sector:04X}",
                    "relinked_span": relink.linked.sector_span,
                    "relinked_length": relink.linked.byte_length,
                    "records": dict(Counter(o.status for o in rebuilt[relink.descriptor.name].outcomes)),
                }
                for relink in relinks
            ],
            "kept_japanese": [
                {"resource": o.resource, "payload_offset": f"0x{o.payload_offset:08X}", "detail": o.detail}
                for o in outcomes if o.status == "kept_japanese"
            ],
            "changed_absolute_lbas": list(comparison.changed_lbas),
            "output_img_sha256": comparison.output_sha256,
        }
        (temporary / "english_resources_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        payload_path.unlink()
        temporary.replace(output_directory)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return output_directory / f"{OUTPUT_STEM}.ccd"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a disc with English in several Mission 0-B event resources (diagnostic)."
    )
    parser.add_argument("source_ccd", type=pathlib.Path)
    parser.add_argument("output_directory", type=pathlib.Path)
    parser.add_argument("--english-tsv", type=pathlib.Path, required=True,
                        help="UTF-8 TSV with payload_offset and english columns")
    parser.add_argument("--resources", required=True,
                        help="comma-separated resource names, e.g. KURUZER,ZAKO0001")
    parser.add_argument("--route", default=",".join(MISSION0_STREET_ROUTE),
                        help="comma-separated observed load order (default: street route)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        output = build_english_resources_test(
            args.source_ccd, args.output_directory, args.english_tsv,
            tuple(args.resources.split(",")), tuple(args.route.split(",")),
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"output_ccd={output}")
    print(f"profile={BUILD_PROFILE}")
    return 0
