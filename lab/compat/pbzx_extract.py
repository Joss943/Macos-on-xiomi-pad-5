#!/usr/bin/env python3
"""Decode Apple's chunked PBZX stream using only the Python standard library."""

from __future__ import annotations

import argparse
import hashlib
import json
import lzma
import struct
import sys
from pathlib import Path


MAGIC = b"pbzx"
MAX_BLOCK_SIZE = 64 * 1024 * 1024
MAX_COMPRESSED_BLOCK = 128 * 1024 * 1024
MAX_OUTPUT_SIZE = 64 * 1024 * 1024 * 1024
MAX_BLOCKS = 4096


class PbzxError(ValueError):
    pass


def decode(source_path: Path, destination: Path) -> dict:
    source_path = source_path.resolve(strict=True)
    if not source_path.is_file():
        raise PbzxError(f"not a file: {source_path}")
    destination = destination.resolve()
    if destination.exists():
        raise PbzxError(f"refusing to overwrite {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    blocks = 0
    output_size = 0
    digest = hashlib.sha256()
    created = False
    try:
        with source_path.open("rb") as source, destination.open("xb") as output:
            created = True
            if source.read(4) != MAGIC:
                raise PbzxError("input does not start with PBZX magic")
            raw = source.read(8)
            if len(raw) != 8:
                raise PbzxError("truncated PBZX header")
            block_size = struct.unpack(">Q", raw)[0]
            if not 0 < block_size <= MAX_BLOCK_SIZE:
                raise PbzxError(f"invalid PBZX block size: {block_size}")

            while True:
                header = source.read(16)
                if not header:
                    break
                if len(header) != 16:
                    raise PbzxError("truncated PBZX chunk header")
                expanded_size, stored_size = struct.unpack(">QQ", header)
                if not 0 < expanded_size <= block_size:
                    raise PbzxError(f"invalid PBZX expanded chunk size: {expanded_size}")
                if not 0 < stored_size <= MAX_COMPRESSED_BLOCK:
                    raise PbzxError(f"invalid PBZX stored chunk size: {stored_size}")
                if stored_size > expanded_size:
                    raise PbzxError("PBZX stored chunk is larger than its expanded size")
                if output_size + expanded_size > MAX_OUTPUT_SIZE:
                    raise PbzxError("PBZX output exceeds safety limit")
                encoded = source.read(stored_size)
                if len(encoded) != stored_size:
                    raise PbzxError("truncated PBZX chunk data")
                if stored_size == expanded_size:
                    expanded = encoded
                else:
                    if not encoded.startswith(b"\xfd7zXZ\x00"):
                        raise PbzxError("compressed PBZX chunk is not an XZ stream")
                    try:
                        expanded = lzma.decompress(
                            encoded, format=lzma.FORMAT_XZ, memlimit=256 * 1024 * 1024
                        )
                    except lzma.LZMAError as error:
                        raise PbzxError(f"invalid XZ chunk {blocks}: {error}") from error
                if len(expanded) != expanded_size:
                    raise PbzxError(
                        f"PBZX chunk {blocks} length mismatch: expected {expanded_size}, got {len(expanded)}"
                    )
                output.write(expanded)
                digest.update(expanded)
                output_size += len(expanded)
                blocks += 1
                if blocks > MAX_BLOCKS:
                    raise PbzxError("PBZX block count exceeds safety limit")
            if blocks == 0:
                raise PbzxError("PBZX stream has no chunks")
    except Exception:
        if created:
            try:
                destination.unlink()
            except FileNotFoundError:
                pass
        raise

    return {
        "output": str(destination),
        "blocks": blocks,
        "expanded_bytes": output_size,
        "expanded_sha256": digest.hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="PBZX input stream")
    parser.add_argument("output", type=Path, help="new destination file")
    args = parser.parse_args()
    try:
        print(json.dumps(decode(args.input, args.output), indent=2))
        return 0
    except (OSError, PbzxError) as error:
        print(f"pbzx_extract: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
