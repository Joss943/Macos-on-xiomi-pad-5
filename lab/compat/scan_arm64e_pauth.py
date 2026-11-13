#!/usr/bin/env python3
"""Find known pointer-authentication instruction words in an arm64e Mach-O.

The scanner reads executable instruction sections and sectionless executable
segments. Segment-only hits are candidates, not proof: literal data can occur
inside an executable mapping. It never modifies the input file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

from arm64e_pauth import lower_sequence


CPU_TYPE_ARM64 = 0x0100000C
CPU_SUBTYPE_ARM64E = 2
CPU_SUBTYPE_MASK = 0x00FFFFFF
MH_FILESET = 12
LC_SEGMENT_64 = 0x19
LC_FILESET_ENTRY = 0x80000035
VM_PROT_EXECUTE = 0x4
S_ATTR_PURE_INSTRUCTIONS = 0x80000000
S_ATTR_SOME_INSTRUCTIONS = 0x00000400


class MachOError(ValueError):
    pass


def _load_macho(data: bytes, base: int, label: str, segment_fallback: bool):
    if base < 0 or base + 32 > len(data):
        raise MachOError(f"truncated Mach-O header at {base:#x}")
    magic, cpu, subtype, filetype, ncmds, sizeofcmds, flags, reserved = struct.unpack_from("<8I", data, base)
    if magic != 0xFEEDFACF:
        raise MachOError(f"expected a little-endian 64-bit Mach-O at {base:#x}")
    if cpu != CPU_TYPE_ARM64 or subtype & CPU_SUBTYPE_MASK != CPU_SUBTYPE_ARM64E:
        raise MachOError(f"expected an arm64e Mach-O slice at {base:#x}")
    command_start = base + 32
    command_end = command_start + sizeofcmds
    if ncmds > 65536 or command_end > len(data):
        raise MachOError("load-command table leaves file bounds")
    regions = []
    fileset_entries = []
    uncovered = []
    offset = command_start
    for _ in range(ncmds):
        if offset + 8 > command_end:
            raise MachOError("truncated load command")
        command, command_size = struct.unpack_from("<II", data, offset)
        if command_size < 8 or offset + command_size > command_end:
            raise MachOError("invalid load-command size")
        if command == LC_FILESET_ENTRY:
            if command_size < 32:
                raise MachOError("truncated LC_FILESET_ENTRY")
            vmaddr, file_offset = struct.unpack_from("<QQ", data, offset + 8)
            ident_offset = struct.unpack_from("<I", data, offset + 24)[0]
            if ident_offset < 32 or ident_offset >= command_size:
                raise MachOError("invalid fileset entry identifier offset")
            ident_start = offset + ident_offset
            ident_end = data.find(b"\0", ident_start, offset + command_size)
            if ident_end < 0 or file_offset + 32 > len(data):
                raise MachOError("invalid fileset entry identifier or file offset")
            ident = data[ident_start:ident_end].decode("utf-8", "replace")
            fileset_entries.append((ident, file_offset))
        if command == LC_SEGMENT_64:
            if command_size < 72:
                raise MachOError("truncated LC_SEGMENT_64")
            name = struct.unpack_from("<16s", data, offset + 8)[0].split(b"\0", 1)[0].decode("ascii", "replace")
            file_offset, file_size = struct.unpack_from("<QQ", data, offset + 40)
            initprot, section_count = struct.unpack_from("<iI", data, offset + 60)
            if 72 + section_count * 80 > command_size:
                raise MachOError("section table leaves LC_SEGMENT_64")
            instruction_sections = []
            for index in range(section_count):
                section_offset = offset + 72 + index * 80
                section_name = struct.unpack_from("<16s", data, section_offset)[0].split(b"\0", 1)[0].decode("ascii", "replace")
                size = struct.unpack_from("<Q", data, section_offset + 40)[0]
                section_file_offset = struct.unpack_from("<I", data, section_offset + 48)[0]
                section_flags = struct.unpack_from("<I", data, section_offset + 64)[0]
                if section_flags & (S_ATTR_PURE_INSTRUCTIONS | S_ATTR_SOME_INSTRUCTIONS):
                    instruction_sections.append((section_name, section_file_offset, size))
            if instruction_sections:
                regions.extend((label + ":" + name + "," + section, start, size, "instruction-section") for section, start, size in instruction_sections if size)
            elif initprot & VM_PROT_EXECUTE and section_count == 0 and segment_fallback:
                if file_size:
                    regions.append((label + ":" + name, file_offset, file_size, "executable-segment-candidate"))
            elif initprot & VM_PROT_EXECUTE and file_size:
                uncovered.append(label + ":" + name)
        offset += command_size
    if offset != command_end:
        raise MachOError("load-command sizes do not match sizeofcmds")
    return filetype, regions, fileset_entries, uncovered


def scan_bytes(data: bytes, sample_limit: int = 256) -> dict:
    if len(data) < 32:
        raise MachOError("truncated Mach-O header")
    root_type, root_regions, fileset_entries, root_uncovered = _load_macho(data, 0, "root", False)
    regions = list(root_regions)
    uncovered = [] if root_type == MH_FILESET else list(root_uncovered)
    if root_type == MH_FILESET:
        if not fileset_entries:
            raise MachOError("MH_FILESET has no LC_FILESET_ENTRY commands")
        for ident, file_offset in fileset_entries:
            _, member_regions, nested, member_uncovered = _load_macho(data, file_offset, ident, True)
            if nested:
                raise MachOError(f"nested fileset in {ident} is unsupported")
            regions.extend(member_regions)
            uncovered.extend(member_uncovered)

    hits = []
    rejected = []
    scanned = 0
    hit_count = 0
    rejected_count = 0
    expanded_count = 0
    counts = Counter()
    region_summaries = []
    confidence_counts = Counter()
    for region, start, size, confidence in regions:
        if size % 4 or start + size > len(data):
            raise MachOError(f"invalid instruction region {region}")
        region_hits = Counter()
        region_rejected = 0
        region_scanned = 0
        for position in range(start, start + size, 4):
            word = struct.unpack_from("<I", data, position)[0]
            scanned += 1
            region_scanned += 1
            try:
                result = lower_sequence(word)
            except ValueError as error:
                rejected_count += 1
                region_rejected += 1
                if len(rejected) < sample_limit:
                    rejected.append({"file_offset": position, "word": f"0x{word:08x}", "reason": str(error), "region": region, "confidence": confidence})
            else:
                if result:
                    hit_count += 1
                    expanded_count += len(result.replacements) > 1
                    counts[result.mnemonic] += 1
                    region_hits[result.mnemonic] += 1
                    if len(hits) < sample_limit:
                        hits.append({"file_offset": position, "word": f"0x{word:08x}", "instruction": result.mnemonic, "replacement_words": [f"0x{replacement:08x}" for replacement in result.replacements], "region": region, "confidence": confidence})
        region_summaries.append({"name": region, "confidence": confidence, "instruction_words_scanned": region_scanned, "recognized_candidates": sum(region_hits.values()), "rejected_forms": region_rejected, "by_instruction": dict(sorted(region_hits.items()))})
        confidence_counts[confidence] += region_scanned

    return {
        "schema": "nabu-arm64e-pauth-scan-v1",
        "architecture": "arm64e",
        "filetype": "MH_FILESET" if root_type == MH_FILESET else f"type-{root_type}",
        "sha256": hashlib.sha256(data).hexdigest(),
        "regions": [{"name": name, "file_offset": start, "size": size, "confidence": confidence} for name, start, size, confidence in regions],
        "summary": {"fileset_members_scanned": len(fileset_entries), "instruction_words_scanned": scanned, "recognized_candidates": hit_count, "expanded_sequences": expanded_count, "rejected_forms": rejected_count, "by_instruction": dict(sorted(counts.items())), "words_by_confidence": dict(sorted(confidence_counts.items()))},
        "region_summaries": region_summaries,
        "uncovered_executable_segments": uncovered,
        "hit_samples": hits,
        "rejected_samples": rejected,
        "warning": "Executable-segment candidates can include data; instruction-section offsets require disassembly and review before rewriting.",
        "image_modified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("macho", type=Path, help="arm64e Mach-O or kernelcache")
    parser.add_argument("--output", type=Path, help="write JSON to a new file")
    args = parser.parse_args()
    try:
        data = args.macho.read_bytes()
        report = scan_bytes(data)
        rendered = json.dumps(report, indent=2)
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(rendered + "\n")
        print(json.dumps(report["summary"]))
    except (OSError, MachOError, struct.error) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
