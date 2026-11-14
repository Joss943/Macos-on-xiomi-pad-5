#!/usr/bin/env python3
"""Rewrite the supported arm64e PAC instructions in one thin Mach-O safely.

This is an experimental, fixed-width code rewrite, not an arm64e emulator or a
bootable-system builder. It refuses files with unscanned executable regions,
unsupported PAC forms, or any lowering that changes instruction count. A
successful output receives refreshed ad-hoc CodeDirectories; CMS is removed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

import macho_codesign
import scan_arm64e_pauth
from arm64e_pauth import lower_sequence


class RewriteError(ValueError):
    def __init__(self, message: str, report: dict[str, object]):
        super().__init__(message)
        self.report = report


def rewrite_bytes(data: bytes) -> tuple[bytes, dict[str, object]]:
    """Rewrite a complete, unambiguous PAC instruction set or leave it untouched."""
    root_type, regions, entries, uncovered = scan_arm64e_pauth._load_macho(data, 0, "root", False)
    if root_type == scan_arm64e_pauth.MH_FILESET:
        if not entries:
            raise RewriteError("MH_FILESET has no entries", {"schema": "nabu-arm64e-rewrite-v1"})
        for ident, file_offset in entries:
            _, member_regions, nested, member_uncovered = scan_arm64e_pauth._load_macho(
                data, file_offset, ident, True
            )
            if nested:
                uncovered.extend(f"nested-fileset:{ident}")
            regions.extend(member_regions)
            uncovered.extend(member_uncovered)

    candidate = bytearray(data)
    counts: Counter[str] = Counter()
    expansion_samples: list[dict[str, object]] = []
    rejected_samples: list[dict[str, object]] = []
    expanded = 0
    rejected = 0
    for region, start, size, confidence in regions:
        if confidence != "instruction-section":
            uncovered.append(f"low-confidence:{region}")
        if size % 4 or start < 0 or start + size > len(data):
            raise RewriteError(f"invalid instruction region {region}", {"schema": "nabu-arm64e-rewrite-v1"})
        for position in range(start, start + size, 4):
            word = struct.unpack_from("<I", data, position)[0]
            try:
                lowered = lower_sequence(word)
            except ValueError as error:
                rejected += 1
                if len(rejected_samples) < 64:
                    rejected_samples.append({
                        "file_offset": position,
                        "word": f"0x{word:08x}",
                        "reason": str(error),
                        "region": region,
                    })
                continue
            if lowered is None:
                continue
            counts[lowered.mnemonic] += 1
            if len(lowered.replacements) != 1:
                expanded += 1
                if len(expansion_samples) < 64:
                    expansion_samples.append({
                        "file_offset": position,
                        "word": f"0x{word:08x}",
                        "instruction": lowered.mnemonic,
                        "replacement_words": [f"0x{item:08x}" for item in lowered.replacements],
                        "region": region,
                    })
                continue
            struct.pack_into("<I", candidate, position, lowered.replacements[0])

    report: dict[str, object] = {
        "schema": "nabu-arm64e-rewrite-v1",
        "architecture": "arm64e",
        "filetype": "MH_FILESET" if root_type == scan_arm64e_pauth.MH_FILESET else f"type-{root_type}",
        "input_sha256": hashlib.sha256(data).hexdigest(),
        "instruction_words_scanned": sum(size // 4 for _, _, size, _ in regions),
        "regions_scanned": len(regions),
        "recognized_candidates": sum(counts.values()),
        "by_instruction": dict(sorted(counts.items())),
        "expanded_forms_requiring_relocation": expanded,
        "expanded_samples": expansion_samples,
        "rejected_forms": rejected,
        "rejected_samples": rejected_samples,
        "uncovered_executable_segments": sorted(set(uncovered)),
        "image_modified": False,
        "bootable_image": False,
    }
    if uncovered or expanded or rejected:
        reasons = []
        if uncovered:
            reasons.append(f"{len(set(uncovered))} executable region(s) are not completely covered")
        if expanded:
            reasons.append(f"{expanded} PAC loads need instruction relocation")
        if rejected:
            reasons.append(f"{rejected} PAC forms have no safe lowering")
        raise RewriteError("refusing partial rewrite: " + "; ".join(reasons), report)
    if sum(counts.values()) == 0:
        raise RewriteError("no supported PAC instructions were found", report)

    output, signature_report = macho_codesign.resign_signature(bytes(candidate))
    rescanned = scan_arm64e_pauth.scan_bytes(output)
    if rescanned["summary"]["recognized_candidates"] or rescanned["summary"]["rejected_forms"]:
        report["post_rewrite_scan"] = rescanned["summary"]
        raise RewriteError("rewritten Mach-O still contains recognized or rejected PAC forms", report)
    report.update({
        "output_sha256": hashlib.sha256(output).hexdigest(),
        "signature_refresh": signature_report,
        "post_rewrite_scan": rescanned["summary"],
        "image_modified": True,
        "verified": True,
    })
    return output, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="thin little-endian ARM64e Mach-O or MH_FILESET")
    parser.add_argument("output", type=Path, help="new output path; existing files are never overwritten")
    parser.add_argument("--report", type=Path, help="optional JSON audit report path")
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("input and output paths must differ")
    try:
        rewritten, report = rewrite_bytes(args.input.read_bytes())
    except (OSError, RewriteError, macho_codesign.SignatureError, scan_arm64e_pauth.MachOError, struct.error) as error:
        report = error.report if isinstance(error, RewriteError) else {
            "schema": "nabu-arm64e-rewrite-v1",
            "verified": False,
            "error": f"{type(error).__name__}: {error}",
            "image_modified": False,
        }
        if args.report:
            with args.report.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(report, stream, indent=2)
                stream.write("\n")
        print(json.dumps(report, indent=2))
        parser.exit(2, f"{error}\n")
    try:
        with args.output.open("xb") as stream:
            stream.write(rewritten)
        if args.report:
            with args.report.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(report, stream, indent=2)
                stream.write("\n")
    except OSError as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
