#!/usr/bin/env python3
"""Inventory Mach-O CPU slices in a mounted macOS system tree.

The report distinguishes ordinary ARM64 from ARM64e files before a target
specific PAC rewrite is considered. It reads only Mach-O headers and never
changes an input file.
"""

from __future__ import annotations

import argparse
import json
import os
import struct
from pathlib import Path


CPU_TYPE_ARM64 = 0x0100000C
CPU_SUBTYPE_ARM64E = 2
CPU_SUBTYPE_MASK = 0x00FFFFFF
FAT_MAGICS = {
    b"\xca\xfe\xba\xbe": (">", False),
    b"\xca\xfe\xba\xbf": (">", True),
    b"\xbe\xba\xfe\xca": ("<", False),
    b"\xbf\xba\xfe\xca": ("<", True),
}
THIN_MAGICS = {
    b"\xcf\xfa\xed\xfe": "<",
    b"\xfe\xed\xfa\xcf": ">",
}
CPU_NAMES = {
    0x01000007: "x86_64",
    CPU_TYPE_ARM64: "arm64",
}
FILE_TYPES = {
    1: "object",
    2: "execute",
    6: "dylib",
    7: "dylinker",
    8: "bundle",
    11: "fileset",
}


class MachOError(ValueError):
    pass


def _slice_info(stream, file_size: int, offset: int, size: int) -> dict:
    if offset < 0 or size < 32 or offset + size > file_size:
        raise MachOError("slice leaves file bounds")
    stream.seek(offset)
    header = stream.read(32)
    endian = THIN_MAGICS.get(header[:4])
    if endian is None or len(header) < 32:
        raise MachOError("slice is not a 64-bit Mach-O")
    magic, cputype, subtype, filetype, ncmds, sizeofcmds, flags, reserved = struct.unpack(
        endian + "8I", header
    )
    subtype_base = subtype & CPU_SUBTYPE_MASK
    name = CPU_NAMES.get(cputype, f"cpu-{cputype:#x}")
    if cputype == CPU_TYPE_ARM64 and subtype_base == CPU_SUBTYPE_ARM64E:
        name = "arm64e"
    return {
        "offset": offset,
        "size": size,
        "cputype": f"0x{cputype:08x}",
        "cpusubtype": f"0x{subtype:08x}",
        "architecture": name,
        "arm64e": cputype == CPU_TYPE_ARM64 and subtype_base == CPU_SUBTYPE_ARM64E,
        "filetype": FILE_TYPES.get(filetype, f"type-{filetype}"),
        "load_commands": ncmds,
        "load_commands_size": sizeofcmds,
        "flags": f"0x{flags:08x}",
        "reserved": reserved,
    }


def inspect_stream(stream, file_size: int) -> dict | None:
    stream.seek(0)
    magic = stream.read(4)
    if magic in THIN_MAGICS:
        return {"format": "thin", "slices": [_slice_info(stream, file_size, 0, file_size)]}
    fat = FAT_MAGICS.get(magic)
    if fat is None:
        return None
    endian, wide = fat
    stream.seek(0)
    header = stream.read(8)
    _, count = struct.unpack(endian + "II", header)
    if count == 0 or count > 128:
        raise MachOError(f"invalid fat slice count: {count}")
    stride = 32 if wide else 20
    table_end = 8 + count * stride
    if table_end > file_size:
        raise MachOError("fat architecture table leaves file bounds")
    slices = []
    for index in range(count):
        stream.seek(8 + index * stride)
        entry = stream.read(stride)
        if wide:
            cputype, subtype, offset, size, align, reserved = struct.unpack(endian + "IIQQII", entry)
        else:
            cputype, subtype, offset, size, align = struct.unpack(endian + "IIIII", entry)
        info = _slice_info(stream, file_size, offset, size)
        if info["cputype"] != f"0x{cputype:08x}" or info["cpusubtype"] != f"0x{subtype:08x}":
            raise MachOError(f"fat header and slice {index} architecture disagree")
        info["alignment"] = align
        if wide:
            info["fat_reserved"] = reserved
        slices.append(info)
    return {"format": "fat64" if wide else "fat32", "slices": slices}


def inspect_file(path: Path, root: Path) -> dict | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        size = path.stat().st_size
        if size < 32:
            return None
        with path.open("rb") as stream:
            result = inspect_stream(stream, size)
        if result is None:
            return None
        return {"path": path.relative_to(root).as_posix(), "size": size, **result}
    except (OSError, MachOError, struct.error) as error:
        return {"path": path.relative_to(root).as_posix(), "error": f"{type(error).__name__}: {error}"}


def inventory(root: Path) -> dict:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"root is not a directory: {root}")
    images = []
    for directory, subdirs, names in os.walk(root, followlinks=False):
        subdirs[:] = [name for name in subdirs if not (Path(directory) / name).is_symlink()]
        for name in names:
            result = inspect_file(Path(directory) / name, root)
            if result is not None:
                images.append(result)
    images.sort(key=lambda item: item["path"].casefold())
    arm64e = sum(any(item.get("arm64e", False) for item in image.get("slices", [])) for image in images)
    arm64 = sum(any(item.get("architecture") == "arm64" for item in image.get("slices", [])) for image in images)
    errors = sum("error" in image for image in images)
    return {
        "schema": "nabu-macho-architecture-inventory-v1",
        "root": str(root),
        "totals": {"macho_files": len(images), "arm64_files": arm64, "arm64e_files": arm64e, "parse_errors": errors},
        "images": images,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="mounted, read-only Sonoma system tree")
    parser.add_argument("--output", type=Path, help="write JSON report to a new file")
    args = parser.parse_args()
    try:
        report = inventory(args.root)
        rendered = json.dumps(report, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(rendered)
                stream.write("\n")
        print(json.dumps(report["totals"]))
        return 0
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

