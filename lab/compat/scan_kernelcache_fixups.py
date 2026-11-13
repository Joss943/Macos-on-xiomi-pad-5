"""Count chained pointer fixups in an arm64e kernelcache fileset."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import inspect_iohid_vtable
import scan_arm64e_pauth


START_NONE = 0xFFFF
START_MULTI = 0x8000
START_LAST = 0x8000
FORMAT_64_KERNEL_CACHE = 8
AUTH_KEY_NAMES = {0: "IA", 1: "IB", 2: "DA", 3: "DB"}
FORMAT_NAMES = {
    1: "DYLD_CHAINED_PTR_ARM64E",
    2: "DYLD_CHAINED_PTR_64",
    3: "DYLD_CHAINED_PTR_32",
    4: "DYLD_CHAINED_PTR_32_CACHE",
    5: "DYLD_CHAINED_PTR_32_FIRMWARE",
    6: "DYLD_CHAINED_PTR_64_OFFSET",
    7: "DYLD_CHAINED_PTR_ARM64E_KERNEL",
    8: "DYLD_CHAINED_PTR_64_KERNEL_CACHE",
    9: "DYLD_CHAINED_PTR_ARM64E_USERLAND",
    10: "DYLD_CHAINED_PTR_ARM64E_FIRMWARE",
    11: "DYLD_CHAINED_PTR_X86_64_KERNEL_CACHE",
    12: "DYLD_CHAINED_PTR_ARM64E_USERLAND24",
    13: "DYLD_CHAINED_PTR_ARM64E_SHARED_CACHE",
    14: "DYLD_CHAINED_PTR_ARM64E_SEGMENTED",
}


class FixupScanError(ValueError):
    pass


def _page_chain_starts(
    fixups: bytes,
    starts_base: int,
    starts_size: int,
    page_starts_base: int,
    page_starts_end: int,
    page_count: int,
    page_index: int,
) -> list[int]:
    entry = struct.unpack_from("<H", fixups, page_starts_base + page_index * 2)[0]
    if entry == START_NONE:
        return []
    if not entry & START_MULTI:
        return [entry]

    segment_end = starts_base + starts_size
    overflow_index = entry & ~START_MULTI
    chain_starts: list[int] = []
    while True:
        overflow_offset = page_starts_end + overflow_index * 2
        if overflow_offset + 2 > segment_end:
            raise FixupScanError("multi-start chain list leaves segment record")
        overflow_entry = struct.unpack_from("<H", fixups, overflow_offset)[0]
        chain_starts.append(overflow_entry & ~START_LAST)
        overflow_index += 1
        if overflow_entry & START_LAST:
            return chain_starts
        if len(chain_starts) > page_count * 16:
            raise FixupScanError("unterminated multi-start chain list")


def scan_kernelcache(data: bytes) -> dict[str, object]:
    root_segments, fixups_command = inspect_iohid_vtable._root_segments_and_fixups(data)
    if fixups_command is None:
        raise FixupScanError("root Mach-O has no LC_DYLD_CHAINED_FIXUPS")
    fixups_offset, fixups_size = fixups_command
    fixups = data[fixups_offset : fixups_offset + fixups_size]
    if len(fixups) < 28:
        raise FixupScanError("truncated chained-fixups header")
    version, starts_offset, imports_offset, symbols_offset, imports_count, imports_format, symbols_format = struct.unpack_from(
        "<7I", fixups, 0
    )
    if version != 0 or starts_offset + 4 > len(fixups):
        raise FixupScanError("unsupported or truncated chained-fixups header")
    segment_count = struct.unpack_from("<I", fixups, starts_offset)[0]
    if segment_count != len(root_segments) or segment_count > 65536:
        raise FixupScanError("chained segment count does not match root segments")
    starts_array_end = starts_offset + 4 + segment_count * 4
    if starts_array_end > len(fixups):
        raise FixupScanError("chained segment-start array leaves payload")

    segment_reports: list[dict[str, object]] = []
    for segment_index, segment in enumerate(root_segments):
        segment_name = segment[4]
        starts_offset_in_image = struct.unpack_from("<I", fixups, starts_offset + 4 + segment_index * 4)[0]
        if starts_offset_in_image == 0:
            continue
        starts_base = starts_offset + starts_offset_in_image
        if starts_base + 22 > len(fixups):
            raise FixupScanError("truncated chained starts-in-segment")
        starts_size, page_size, pointer_format = struct.unpack_from("<IHH", fixups, starts_base)
        segment_offset = struct.unpack_from("<Q", fixups, starts_base + 8)[0]
        max_valid_pointer, page_count = struct.unpack_from("<IH", fixups, starts_base + 16)
        starts_end = starts_base + starts_size
        page_starts_base = starts_base + 22
        page_starts_end = page_starts_base + page_count * 2
        if starts_size < 22 or starts_end > len(fixups) or page_starts_end > starts_end:
            raise FixupScanError("chained page-start table leaves segment record")

        row: dict[str, object] = {
            "segment_index": segment_index,
            "segment": segment_name,
            "segment_offset": f"0x{segment_offset:x}",
            "pointer_format": pointer_format,
            "pointer_format_name": FORMAT_NAMES.get(pointer_format, "unknown"),
            "page_size": page_size,
            "pages": page_count,
            "nonempty_pages": 0,
            "chains": 0,
            "pointer_cells": 0,
            "authenticated_pointer_cells": 0,
            "unauthenticated_pointer_cells": 0,
            "cross_page_pointer_cells": 0,
            "multi_start_pages": 0,
            "cache_level_counts": {},
            "authentication_key_counts": {},
            "unsupported_format": pointer_format != FORMAT_64_KERNEL_CACHE,
        }
        if pointer_format != FORMAT_64_KERNEL_CACHE:
            segment_reports.append(row)
            continue
        if page_size == 0:
            raise FixupScanError("chained page size is zero")

        _, segment_vmsize, segment_fileoff, segment_filesize, _ = segment
        seen_file_offsets: set[int] = set()
        for page_index in range(page_count):
            page_entry = struct.unpack_from("<H", fixups, page_starts_base + page_index * 2)[0]
            chain_starts = _page_chain_starts(
                fixups,
                starts_base,
                starts_size,
                page_starts_base,
                page_starts_end,
                page_count,
                page_index,
            )
            if not chain_starts:
                continue
            row["nonempty_pages"] += 1
            if page_entry & START_MULTI:
                row["multi_start_pages"] += 1
            page_segment_offset = page_index * page_size
            if page_segment_offset >= segment_vmsize:
                raise FixupScanError("chained page starts outside root segment")
            for chain_start in chain_starts:
                row["chains"] += 1
                chain_offset = chain_start
                visited: set[int] = set()
                for _ in range(page_size // 4 + 2):
                    if chain_offset in visited or chain_offset >= page_size + 4:
                        raise FixupScanError("invalid or cyclic pointer chain")
                    visited.add(chain_offset)
                    pointer_fileoff = segment_fileoff + page_segment_offset + chain_offset
                    if pointer_fileoff + 8 > segment_fileoff + segment_filesize or pointer_fileoff + 8 > len(data):
                        raise FixupScanError("chained pointer leaves root segment file data")
                    if pointer_fileoff in seen_file_offsets:
                        raise FixupScanError("overlapping pointer chains reference one fixup twice")
                    seen_file_offsets.add(pointer_fileoff)
                    raw = struct.unpack_from("<Q", data, pointer_fileoff)[0]
                    is_authenticated = bool(raw >> 63)
                    cache_level = (raw >> 30) & 0x3
                    next_delta = (raw >> 51) & 0xFFF
                    row["pointer_cells"] += 1
                    if is_authenticated:
                        row["authenticated_pointer_cells"] += 1
                        key = AUTH_KEY_NAMES[(raw >> 49) & 0x3]
                        key_counts = row["authentication_key_counts"]
                        assert isinstance(key_counts, dict)
                        key_counts[key] = key_counts.get(key, 0) + 1
                    else:
                        row["unauthenticated_pointer_cells"] += 1
                    level_counts = row["cache_level_counts"]
                    assert isinstance(level_counts, dict)
                    level = str(cache_level)
                    level_counts[level] = level_counts.get(level, 0) + 1
                    if chain_offset + 8 > page_size:
                        row["cross_page_pointer_cells"] += 1
                    if next_delta == 0:
                        break
                    chain_offset += next_delta * 4
                else:
                    raise FixupScanError("pointer chain exceeded page bound")
        segment_reports.append(row)

    for key in (
        "nonempty_pages",
        "chains",
        "pointer_cells",
        "authenticated_pointer_cells",
        "unauthenticated_pointer_cells",
        "cross_page_pointer_cells",
        "multi_start_pages",
    ):
        segment_reports_total = sum(int(row[key]) for row in segment_reports)
        if key == "nonempty_pages":
            total_nonempty_pages = segment_reports_total
        elif key == "chains":
            total_chains = segment_reports_total
        elif key == "pointer_cells":
            total_pointer_cells = segment_reports_total
        elif key == "authenticated_pointer_cells":
            total_authenticated = segment_reports_total
        elif key == "unauthenticated_pointer_cells":
            total_unauthenticated = segment_reports_total
        elif key == "cross_page_pointer_cells":
            total_cross_page = segment_reports_total
        else:
            total_multi_pages = segment_reports_total

    key_counts: dict[str, int] = {}
    for row in segment_reports:
        counts = row["authentication_key_counts"]
        assert isinstance(counts, dict)
        for key, count in counts.items():
            key_counts[key] = key_counts.get(key, 0) + int(count)

    return {
        "schema": "arm64e-kernelcache-chained-fixups-report-v1",
        "kernelcache_sha256": hashlib.sha256(data).hexdigest(),
        "root_fixups_command_bytes": fixups_size,
        "pointer_format_stride_bytes": 4,
        "fixup_segment_count": segment_count,
        "segments_with_fixups": len(segment_reports),
        "nonempty_pages": total_nonempty_pages,
        "chains": total_chains,
        "pointer_cells": total_pointer_cells,
        "authenticated_pointer_cells": total_authenticated,
        "unauthenticated_pointer_cells": total_unauthenticated,
        "cross_page_pointer_cells": total_cross_page,
        "multi_start_pages": total_multi_pages,
        "authentication_key_counts": key_counts,
        "imports_count": imports_count,
        "imports_format": imports_format,
        "symbols_format": symbols_format,
        "segments": segment_reports,
        "kernelcache_modified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernelcache", type=Path, help="decompressed arm64e MH_FILESET kernelcache")
    parser.add_argument("--output", type=Path, help="write JSON report to a new file")
    args = parser.parse_args()
    try:
        report = scan_kernelcache(args.kernelcache.read_bytes())
    except (OSError, FixupScanError, inspect_iohid_vtable.VTableError, scan_arm64e_pauth.MachOError, struct.error) as error:
        parser.error(str(error))
    rendered = json.dumps(report, indent=2)
    if args.output:
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
