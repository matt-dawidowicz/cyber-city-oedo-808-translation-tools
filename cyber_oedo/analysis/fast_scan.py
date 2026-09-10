"""Native hot loops for large binary reconnaissance scans.

The public scanners process an 84 MiB payload. Per-byte Python loops dominate
that workload, so deterministic token state machines live in Numba-compiled
functions while formatting and file I/O remain ordinary Python.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit


@njit(cache=True)
def _sector_metrics_native(data, sector_size):
    """Compute per-sector histograms and entropy in compiled code."""

    sector_count = data.size // sector_size
    nonzero = np.empty(sector_count, dtype=np.int32)
    unique = np.empty(sector_count, dtype=np.int16)
    entropy = np.empty(sector_count, dtype=np.float64)
    zero = np.empty(sector_count, dtype=np.bool_)
    counts = np.empty(256, dtype=np.int32)
    for sector in range(sector_count):
        counts[:] = 0
        start = sector * sector_size
        for index in range(sector_size):
            counts[data[start + index]] += 1
        zero_count = counts[0]
        unique_count = 0
        entropy_value = -0.0
        for count in counts:
            if count:
                unique_count += 1
                probability = count / sector_size
                entropy_value -= probability * math.log2(probability)
        nonzero[sector] = sector_size - zero_count
        unique[sector] = unique_count
        entropy[sector] = entropy_value
        zero[sector] = zero_count == sector_size
    return nonzero, unique, entropy, zero


def sector_metrics(data: object, sector_size: int):
    """Return vectorized sector metrics for one aligned bytes-like object."""

    if sector_size <= 0:
        raise ValueError("sector_size must be positive")
    if len(data) % sector_size:  # type: ignore[arg-type]
        raise ValueError("data length must be sector-aligned")
    view = np.frombuffer(data, dtype=np.uint8)  # type: ignore[arg-type]
    try:
        return _sector_metrics_native(view, sector_size)
    finally:
        del view


@njit(cache=True)
def _count_broad_sjis_runs(data, minimum_japanese):
    """Count deterministic broad Shift-JIS runs in compiled code."""

    offset = 0
    size = data.size
    count = 0
    while offset < size:
        start = offset
        japanese = 0
        while offset < size:
            first = data[offset]
            if 0x20 <= first <= 0x7E or first == 0x09 or first == 0x0A or first == 0x0D:
                offset += 1
            elif 0xA1 <= first <= 0xDF:
                japanese += 1
                offset += 1
            elif (
                (0x81 <= first <= 0x9F or 0xE0 <= first <= 0xEF)
                and offset + 1 < size
                and (
                    0x40 <= data[offset + 1] <= 0x7E or 0x80 <= data[offset + 1] <= 0xFC
                )
            ):
                japanese += 1
                offset += 2
            else:
                break
        if japanese >= minimum_japanese and offset > start:
            count += 1
        offset = max(offset + 1, start + 1)
    return count


@njit(cache=True)
def _fill_broad_sjis_runs(
    data,
    minimum_japanese,
    starts,
    ends,
    japanese_counts,
):
    """Fill broad Shift-JIS run coordinates in compiled code."""

    offset = 0
    size = data.size
    output_index = 0
    while offset < size:
        start = offset
        japanese = 0
        while offset < size:
            first = data[offset]
            if 0x20 <= first <= 0x7E or first == 0x09 or first == 0x0A or first == 0x0D:
                offset += 1
            elif 0xA1 <= first <= 0xDF:
                japanese += 1
                offset += 1
            elif (
                (0x81 <= first <= 0x9F or 0xE0 <= first <= 0xEF)
                and offset + 1 < size
                and (
                    0x40 <= data[offset + 1] <= 0x7E or 0x80 <= data[offset + 1] <= 0xFC
                )
            ):
                japanese += 1
                offset += 2
            else:
                break
        if japanese >= minimum_japanese and offset > start:
            starts[output_index] = start
            ends[output_index] = offset
            japanese_counts[output_index] = japanese
            output_index += 1
        offset = max(offset + 1, start + 1)
    return output_index


def broad_sjis_runs(data: object, minimum_japanese: int):
    """Return exact broad Shift-JIS run coordinates without Python scanning."""

    if minimum_japanese <= 0:
        raise ValueError("minimum_japanese must be positive")
    view = np.frombuffer(data, dtype=np.uint8)  # type: ignore[arg-type]
    try:
        count = _count_broad_sjis_runs(view, minimum_japanese)
        starts = np.empty(count, dtype=np.int64)
        ends = np.empty(count, dtype=np.int64)
        japanese = np.empty(count, dtype=np.int32)
        filled = _fill_broad_sjis_runs(
            view,
            minimum_japanese,
            starts,
            ends,
            japanese,
        )
        if filled != count:
            raise AssertionError("broad Shift-JIS run count changed")
        return starts, ends, japanese
    finally:
        del view


@njit(cache=True)
def _scan_decodable_broad_sjis_native(
    data,
    minimum_japanese,
    pair_codepoint,
    starts,
    ends,
    japanese_counts,
    write_output,
):
    """Filter structurally valid but undecodable broad runs in native code."""

    offset = 0
    size = data.size
    output_index = 0
    while offset < size:
        start = offset
        japanese = 0
        decodable = True
        while offset < size:
            first = data[offset]
            if (
                0x20 <= first <= 0x7E
                or first == 0x09
                or first == 0x0A
                or first == 0x0D
            ):
                offset += 1
            elif 0xA1 <= first <= 0xDF:
                japanese += 1
                offset += 1
            elif (
                (0x81 <= first <= 0x9F or 0xE0 <= first <= 0xEF)
                and offset + 1 < size
                and (
                    0x40 <= data[offset + 1] <= 0x7E
                    or 0x80 <= data[offset + 1] <= 0xFC
                )
            ):
                key = data[offset + 1] | (first << 8)
                if pair_codepoint[key] < 0:
                    decodable = False
                japanese += 1
                offset += 2
            else:
                break
        if japanese >= minimum_japanese and offset > start and decodable:
            if write_output:
                starts[output_index] = start
                ends[output_index] = offset
                japanese_counts[output_index] = japanese
            output_index += 1
        offset = max(offset + 1, start + 1)
    return output_index


def decodable_broad_sjis_runs(data: object, minimum_japanese: int):
    """Return broad Shift-JIS runs already proven decodable by lookup table."""

    if minimum_japanese <= 0:
        raise ValueError("minimum_japanese must be positive")
    view = np.frombuffer(data, dtype=np.uint8)  # type: ignore[arg-type]
    dummy_offsets = np.empty(1, dtype=np.int64)
    dummy_counts = np.empty(1, dtype=np.int32)
    try:
        count = _scan_decodable_broad_sjis_native(
            view,
            minimum_japanese,
            _PAIR_CODEPOINT,
            dummy_offsets,
            dummy_offsets,
            dummy_counts,
            False,
        )
        starts = np.empty(count, dtype=np.int64)
        ends = np.empty(count, dtype=np.int64)
        japanese = np.empty(count, dtype=np.int32)
        filled = _scan_decodable_broad_sjis_native(
            view,
            minimum_japanese,
            _PAIR_CODEPOINT,
            starts,
            ends,
            japanese,
            True,
        )
        if filled != count:
            raise AssertionError("decodable broad Shift-JIS run count changed")
        return starts, ends, japanese
    finally:
        del view


def _build_sjis_codepoint_tables():
    """Build strict Shift-JIS token-to-codepoint lookup tables once."""

    single = np.full(256, -1, dtype=np.int32)
    pair = np.full(65536, -1, dtype=np.int32)
    for value in (*range(0x20, 0x7F), *range(0xA1, 0xE0)):
        try:
            text = bytes((value,)).decode("shift_jis")
        except UnicodeDecodeError:
            continue
        if len(text) == 1:
            single[value] = ord(text)
    lead_values = (*range(0x81, 0xA0), *range(0xE0, 0xF0))
    trail_values = (*range(0x40, 0x7F), *range(0x80, 0xFD))
    for high in lead_values:
        for low in trail_values:
            try:
                text = bytes((high, low)).decode("shift_jis")
            except UnicodeDecodeError:
                continue
            if len(text) == 1:
                pair[low | (high << 8)] = ord(text)
    return single, pair


_SINGLE_CODEPOINT, _PAIR_CODEPOINT = _build_sjis_codepoint_tables()


@njit(cache=True)
def _scan_likely_sjis_native(
    data,
    minimum_tokens,
    single_codepoint,
    pair_codepoint,
    starts,
    ends,
    metrics,
    write_output,
):
    """Filter deterministic natural-language candidates in compiled code."""

    seen_generation = np.zeros(65536, dtype=np.int32)
    codepoint_counts = np.zeros(65536, dtype=np.int32)
    generation = 0
    offset = 0
    size = data.size
    output_index = 0
    while offset < size:
        start = offset
        tokens = 0
        hiragana = 0
        katakana = 0
        kanji = 0
        fullwidth = 0
        ascii_printable = 0
        max_count = 0
        decodable = True
        generation += 1
        while offset < size:
            first = data[offset]
            codepoint = -1
            if 0x20 <= first <= 0x7E or 0xA1 <= first <= 0xDF:
                codepoint = single_codepoint[first]
                offset += 1
            elif (
                (0x81 <= first <= 0x9F or 0xE0 <= first <= 0xEF)
                and offset + 1 < size
                and (
                    0x40 <= data[offset + 1] <= 0x7E or 0x80 <= data[offset + 1] <= 0xFC
                )
            ):
                key = data[offset + 1] | (first << 8)
                codepoint = pair_codepoint[key]
                offset += 2
            else:
                break
            tokens += 1
            if codepoint < 0:
                decodable = False
                continue
            if seen_generation[codepoint] != generation:
                seen_generation[codepoint] = generation
                codepoint_counts[codepoint] = 1
                count = 1
            else:
                codepoint_counts[codepoint] += 1
                count = codepoint_counts[codepoint]
            if count > max_count:
                max_count = count
            if 0x3040 <= codepoint <= 0x309F:
                hiragana += 1
            elif 0x30A0 <= codepoint <= 0x30FF:
                katakana += 1
            if 0x3400 <= codepoint <= 0x9FFF:
                kanji += 1
            if 0xFF01 <= codepoint <= 0xFF60:
                fullwidth += 1
            if 0x20 <= codepoint <= 0x7E:
                ascii_printable += 1

        plausible = False
        if (
            tokens >= minimum_tokens
            and decodable
            and tokens >= 5
            and 100 * max_count <= 55 * tokens
        ):
            if not (ascii_printable > 2 and fullwidth < 4):
                kana = hiragana + katakana
                natural_sentence = (
                    tokens >= 8 and kana >= 3 and 100 * kana >= 20 * tokens
                )
                japanese_label = (
                    tokens >= 5 and kana >= 2 and 100 * (kana + kanji) >= 60 * tokens
                )
                fullwidth_label = fullwidth >= 5 and ascii_printable == 0
                plausible = natural_sentence or japanese_label or fullwidth_label
        if plausible:
            if write_output:
                starts[output_index] = start
                ends[output_index] = offset
                metrics[output_index, 0] = tokens
                metrics[output_index, 1] = hiragana
                metrics[output_index, 2] = katakana
                metrics[output_index, 3] = kanji
                metrics[output_index, 4] = fullwidth
            output_index += 1
        offset = max(offset + 1, start + 1)
    return output_index


def likely_sjis_runs(data: object, minimum_tokens: int):
    """Return deterministic natural-language Shift-JIS candidates."""

    if minimum_tokens <= 0:
        raise ValueError("minimum_tokens must be positive")
    view = np.frombuffer(data, dtype=np.uint8)  # type: ignore[arg-type]
    dummy_offsets = np.empty(1, dtype=np.int64)
    dummy_metrics = np.empty((1, 5), dtype=np.int32)
    try:
        count = _scan_likely_sjis_native(
            view,
            minimum_tokens,
            _SINGLE_CODEPOINT,
            _PAIR_CODEPOINT,
            dummy_offsets,
            dummy_offsets,
            dummy_metrics,
            False,
        )
        starts = np.empty(count, dtype=np.int64)
        ends = np.empty(count, dtype=np.int64)
        metrics = np.empty((count, 5), dtype=np.int32)
        filled = _scan_likely_sjis_native(
            view,
            minimum_tokens,
            _SINGLE_CODEPOINT,
            _PAIR_CODEPOINT,
            starts,
            ends,
            metrics,
            True,
        )
        if filled != count:
            raise AssertionError("likely Shift-JIS run count changed")
        return starts, ends, metrics
    finally:
        del view
