#!/usr/bin/env python3
"""Build tiny AArch64 Linux probes for PAC instructions and ID_AA64ISAR1_EL1.

The generated ELF is intended to run as the Android shell user from
/data/local/tmp. It reads one architectural ID register or executes PACIA and
AUTIA, then writes the result to stdout. It does not access storage devices,
change boot state, or flash firmware. Older CPUs may terminate it with SIGILL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
from pathlib import Path


ELF_BASE = 0x400000
ELF_ENTRY = ELF_BASE + 64 + 56

PROBES = {
    "pac": {
        "description": "Execute PACIA/AUTIA on a fixed non-null pointer and emit restored,signed values.",
        "words": [
            0xD10043FF,  # sub sp, sp, #16
            0xD2824683,  # movz x3, #0x1234
            0xF90003E3,  # str x3, [sp]
            0xD280ACE4,  # movz x4, #0x567
            0xDAC10083,  # pacia x3, x4
            0xF90013E3,  # str x3, [sp, #8]
            0xDAC11083,  # autia x3, x4
            0xF90003E3,  # str x3, [sp]
            0xD2800020,  # movz x0, #1 (stdout)
            0x910003E1,  # mov x1, sp
            0xD2800202,  # movz x2, #16
            0xD2800808,  # movz x8, #64 (write)
            0xD4000001,  # svc #0
            0xD2800000,  # movz x0, #0
            0xD2800BA8,  # movz x8, #93 (exit)
            0xD4000001,  # svc #0
        ],
        "expected_stdout_bytes": 16,
    },
    "isar1": {
        "description": "Read ID_AA64ISAR1_EL1 at EL0 and emit its 64-bit value.",
        "words": [
            0xD10043FF,  # sub sp, sp, #16
            0xD5380620,  # mrs x0, ID_AA64ISAR1_EL1
            0xF90003E0,  # str x0, [sp]
            0xD2800020,  # movz x0, #1 (stdout)
            0x910003E1,  # mov x1, sp
            0xD2800102,  # movz x2, #8
            0xD2800808,  # movz x8, #64 (write)
            0xD4000001,  # svc #0
            0xD2800000,  # movz x0, #0
            0xD2800BA8,  # movz x8, #93 (exit)
            0xD4000001,  # svc #0
        ],
        "expected_stdout_bytes": 8,
    },
    "isar2": {
        "description": "Read ID_AA64ISAR2_EL1 at EL0 and emit its 64-bit value.",
        "words": [
            0xD10043FF,  # sub sp, sp, #16
            0xD5380640,  # mrs x0, ID_AA64ISAR2_EL1
            0xF90003E0,  # str x0, [sp]
            0xD2800020,  # movz x0, #1 (stdout)
            0x910003E1,  # mov x1, sp
            0xD2800102,  # movz x2, #8
            0xD2800808,  # movz x8, #64 (write)
            0xD4000001,  # svc #0
            0xD2800000,  # movz x0, #0
            0xD2800BA8,  # movz x8, #93 (exit)
            0xD4000001,  # svc #0
        ],
        "expected_stdout_bytes": 8,
    },
}


def make_elf(words: list[int]) -> bytes:
    code = struct.pack(f"<{len(words)}I", *words)
    file_size = 64 + 56 + len(code)
    ident = b"\x7fELF" + bytes((2, 1, 1, 0)) + bytes(8)
    header = struct.pack(
        "<16sHHIQQQIHHHHHH",
        ident,
        2,  # ET_EXEC
        183,  # EM_AARCH64
        1,
        ELF_ENTRY,
        64,
        0,
        0,
        64,
        56,
        1,
        0,
        0,
        0,
    )
    load_segment = struct.pack(
        "<IIQQQQQQ",
        1,  # PT_LOAD
        5,  # PF_R | PF_X
        0,
        ELF_BASE,
        0,
        file_size,
        file_size,
        0x1000,
    )
    return header + load_segment + code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=sorted(PROBES))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    payload = make_elf(PROBES[args.kind]["words"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(payload)
    os.chmod(args.output, 0o755)

    print(json.dumps({
        "schema": "nabu-arm64e-el0-probe-v1",
        "kind": args.kind,
        "description": PROBES[args.kind]["description"],
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "expected_stdout_bytes": PROBES[args.kind]["expected_stdout_bytes"],
        "hardware_tested": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
