#!/usr/bin/env python3
"""Decode an Apple IM4P/LZFSE kernelcache and select its ARM64 Mach-O slice."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

try:
    import lzfse
except ImportError as error:  # pragma: no cover - depends on host setup
    raise SystemExit("install the Python lzfse module to decode this kernelcache") from error


CPU_TYPE_ARM64 = 0x0100000C
FAT_MAGIC = 0xCAFEBABE
FAT_MAGIC_64 = 0xCAFEBABF


class DecodeError(ValueError):
    pass


def _der_item(data: bytes, offset: int) -> tuple[int, int, int]:
    if offset + 2 > len(data):
        raise DecodeError("truncated DER tag or length")
    tag, first_length = data[offset], data[offset + 1]
    offset += 2
    if first_length & 0x80:
        count = first_length & 0x7F
        if count == 0 or count > 8 or offset + count > len(data):
            raise DecodeError("invalid DER long-form length")
        length = int.from_bytes(data[offset:offset + count], "big")
        offset += count
    else:
        length = first_length
    if offset + length > len(data):
        raise DecodeError("DER item leaves file bounds")
    return tag, offset, length


def im4p_payload(data: bytes) -> bytes:
    tag, start, length = _der_item(data, 0)
    end = start + length
    if tag != 0x30 or end != len(data):
        raise DecodeError("input is not one complete DER sequence")
    fields = []
    cursor = start
    while cursor < end:
        field_tag, body, size = _der_item(data, cursor)
        fields.append((field_tag, data[body:body + size]))
        cursor = body + size
    if len(fields) < 4 or fields[0][1] != b"IM4P" or fields[3][0] != 0x04:
        raise DecodeError("DER sequence is not a standard IM4P payload")
    return fields[3][1]


def arm64_slice(data: bytes) -> tuple[bytes, int]:
    if len(data) < 32:
        raise DecodeError("decompressed kernelcache is truncated")
    magic = struct.unpack_from(">I", data)[0]
    if magic not in (FAT_MAGIC, FAT_MAGIC_64):
        if data[:4] in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"):
            cpu, subtype = struct.unpack_from("<II", data, 4)
            if cpu != CPU_TYPE_ARM64:
                raise DecodeError(f"thin Mach-O is not ARM64: cputype {cpu:#x}")
            return data, subtype
        raise DecodeError(f"unsupported decompressed kernelcache format: {data[:4].hex()}")

    count = struct.unpack_from(">I", data, 4)[0]
    if count == 0 or count > 128:
        raise DecodeError(f"invalid FAT architecture count: {count}")
    stride = 32 if magic == FAT_MAGIC_64 else 20
    if 8 + count * stride > len(data):
        raise DecodeError("FAT architecture table leaves file bounds")
    matches = []
    for index in range(count):
        offset = 8 + index * stride
        if magic == FAT_MAGIC_64:
            cpu, subtype, slice_start, slice_size, _align, _reserved = struct.unpack_from(">IIQQII", data, offset)
        else:
            cpu, subtype, slice_start, slice_size, _align = struct.unpack_from(">IIIII", data, offset)
        if cpu == CPU_TYPE_ARM64:
            if slice_start + slice_size > len(data):
                raise DecodeError("ARM64 slice leaves file bounds")
            matches.append((data[slice_start:slice_start + slice_size], subtype))
    if len(matches) != 1:
        raise DecodeError(f"expected exactly one ARM64 slice, found {len(matches)}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="kernelcache IM4P extracted from the IPSW")
    parser.add_argument("output", type=Path, help="new output path for the ARM64 Mach-O")
    parser.add_argument("--expected-sha256", help="optional profile hash for the selected ARM64 slice")
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("input and output paths must differ")
    try:
        packed = im4p_payload(args.input.read_bytes())
        decompressed = lzfse.decompress(packed)
        selected, subtype = arm64_slice(decompressed)
        digest = hashlib.sha256(selected).hexdigest()
        if args.expected_sha256 and digest.lower() != args.expected_sha256.lower():
            raise DecodeError(f"ARM64 slice SHA-256 mismatch: {digest}")
        with args.output.open("xb") as stream:
            stream.write(selected)
    except (OSError, DecodeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({
        "schema": "apple-kernelcache-im4p-decode-v1",
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "lzfse_payload_bytes": len(packed),
        "decompressed_bytes": len(decompressed),
        "selected_architecture": "arm64",
        "selected_subtype": f"0x{subtype:08x}",
        "selected_bytes": len(selected),
        "selected_sha256": digest,
        "sha256_pin_verified": bool(args.expected_sha256),
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
