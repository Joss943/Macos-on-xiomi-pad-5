#!/usr/bin/env python3
"""Lower selected AArch64 pointer-authentication instructions for nabu.

This module is one building block for an arm64e compatibility tool. It maps
selected instructions to ordinary AArch64 words or short instruction
sequences; it does not locate code in Mach-O files, relocate branches, update
signatures or make an OS image bootable. Unknown or unsafe cases fail closed.

The instruction encodings follow Arm's A-profile architecture reference
manual. The lowering rules were cross-checked against UniXNU-zeta's BSD-2-
Clause-Patent implementation (revision eb489285a1d9153872f00c93ebb519a269b249b5).
See NOTICE.md for attribution and license.
"""

from __future__ import annotations

import argparse
import json
from typing import NamedTuple


NOP = 0xD503201F
RET = 0xD65F03C0

_DP1SRC = (
    "pacia", "pacib", "pacda", "pacdb", "autia", "autib", "autda", "autdb",
    "paciza", "pacizb", "pacdza", "pacdzb", "autiza", "autizb", "autdza",
    "autdzb", "xpaci", "xpacd",
)
# These encodings occupy the architected HINT space. On a CPU without FEAT_PAuth
# they are architectural NOPs; spelling them out also lets the rewriter report
# which PAC-specific operations it found in an arm64e image.
_PAUTH_HINTS = {
    0xD503211F: "pacia1716",
    0xD503215F: "pacib1716",
    0xD503219F: "autia1716",
    0xD50321DF: "autib1716",
    0xD503231F: "paciaz",
    0xD503235F: "pacibz",
    0xD503239F: "autiaz",
    0xD50323DF: "autibz",
    0xD503233F: "paciasp",
    0xD503237F: "pacibsp",
    0xD50323BF: "autiasp",
    0xD50323FF: "autibsp",
    0xD50320FF: "xpaclri",
}
_BRANCHES = (
    (0xD61F081F, 0xFFFFFC1F, "braaz", 0xD61F0000),
    (0xD61F0C1F, 0xFFFFFC1F, "brabz", 0xD61F0000),
    (0xD63F081F, 0xFFFFFC1F, "blraaz", 0xD63F0000),
    (0xD63F0C1F, 0xFFFFFC1F, "blrabz", 0xD63F0000),
    (0xD71F0800, 0xFFFFFC00, "braa", 0xD61F0000),
    (0xD71F0C00, 0xFFFFFC00, "brab", 0xD61F0000),
    (0xD73F0800, 0xFFFFFC00, "blraa", 0xD63F0000),
    (0xD73F0C00, 0xFFFFFC00, "blrab", 0xD63F0000),
)


class Lowering(NamedTuple):
    mnemonic: str
    replacement: int


class SequenceLowering(NamedTuple):
    mnemonic: str
    replacements: tuple[int, ...]


def lower(word: int) -> Lowering | None:
    """Return an exact one-word lowering, None for an unrelated instruction.

    ValueError marks an encoding or addressing mode that this compatibility
    path cannot preserve exactly. Callers must leave the input image untouched
    when any requested instruction raises.
    """
    if not 0 <= word <= 0xFFFFFFFF:
        raise ValueError(f"instruction word outside uint32: {word!r}")

    if word in _PAUTH_HINTS:
        return Lowering(_PAUTH_HINTS[word], NOP)

    if word & 0xFFFF0000 == 0xDAC10000:
        opcode = (word >> 10) & 0x3F
        modifier = (word >> 5) & 0x1F
        if opcode >= len(_DP1SRC):
            return None
        if opcode >= 8 and modifier != 31:
            raise ValueError(f"{word:#010x}: unallocated zero-modifier PAC form")
        return Lowering(_DP1SRC[opcode], NOP)

    if word & 0xFFE0FC00 == 0x9AC03000:
        rd = word & 0x1F
        replacement = NOP if rd == 31 else 0xD2800000 | rd  # MOVZ Xd, #0
        return Lowering("pacga", replacement)

    for value, mask, mnemonic, branch_base in _BRANCHES:
        if word & mask == value:
            rn = (word >> 5) & 0x1F
            if rn == 31:
                raise ValueError(f"{word:#010x}: authenticated branch through register 31")
            return Lowering(mnemonic, branch_base | (rn << 5))

    if word in (0xD65F0BFF, 0xD65F0FFF):
        mnemonic = "retaa" if word == 0xD65F0BFF else "retab"
        return Lowering(mnemonic, RET)

    if word in (0xD69F0BFF, 0xD69F0FFF):
        raise ValueError(f"{word:#010x}: ERETAA/ERETAB cannot execute at EL0")

    if word & 0xFF200400 == 0xF8200400:
        mnemonic = "ldrab" if word & 0x00800000 else "ldraa"
        encoded_offset = (((word >> 22) & 1) << 9) | ((word >> 12) & 0x1FF)
        offset = (encoded_offset - 1024 if encoded_offset & 0x200 else encoded_offset) * 8
        writeback = (word >> 11) & 1
        registers = word & 0x3FF

        if writeback and -256 <= offset <= 255:
            replacement = 0xF8400C00 | ((offset & 0x1FF) << 12) | registers
            return Lowering(mnemonic, replacement)
        if not writeback and offset >= 0:
            replacement = 0xF9400000 | ((offset // 8) << 10) | registers
            return Lowering(mnemonic, replacement)
        if not writeback and offset >= -256:
            replacement = 0xF8400000 | ((offset & 0x1FF) << 12) | registers
            return Lowering(mnemonic, replacement)
        raise ValueError(f"{word:#010x}: {mnemonic} offset {offset} has no exact LDR form")

    return None


def lower_sequence(word: int) -> SequenceLowering | None:
    """Lower an instruction to one or more words when the semantics allow it.

    The multiword LDRAA/LDRAB cases use the load destination as a temporary
    only when it does not alias the base. A full Mach-O rewriter must still
    relocate branches and metadata before these sequences can be installed.
    """
    try:
        direct = lower(word)
    except ValueError as error:
        if word & 0xFF200400 != 0xF8200400 or "no exact LDR form" not in str(error):
            raise
        direct = None
    if direct is not None:
        return SequenceLowering(direct.mnemonic, (direct.replacement,))
    if not 0 <= word <= 0xFFFFFFFF:
        raise ValueError(f"instruction word outside uint32: {word!r}")
    if word & 0xFF200400 != 0xF8200400:
        return None

    mnemonic = "ldrab" if word & 0x00800000 else "ldraa"
    encoded_offset = (((word >> 22) & 1) << 9) | ((word >> 12) & 0x1FF)
    offset = (encoded_offset - 1024 if encoded_offset & 0x200 else encoded_offset) * 8
    writeback = (word >> 11) & 1
    rt = word & 0x1F
    rn = (word >> 5) & 0x1F

    if not -4096 <= offset <= 4088 or offset % 8:
        raise ValueError(f"{word:#010x}: invalid LDRAA/LDRAB immediate {offset}")
    if writeback:
        if rn == rt and rn != 31:
            raise ValueError(f"{word:#010x}: pre-indexed load overlaps base and destination")
        rd = rn
        addend = abs(offset)
    else:
        if rt == 31 or rt == rn:
            raise ValueError(f"{word:#010x}: no safe temporary register for expanded load")
        rd = rt
        addend = abs(offset)

    if addend == 0:
        raise ValueError(f"{word:#010x}: zero-offset load unexpectedly needs expansion")
    shift = 1 if addend == 4096 else 0
    immediate = addend >> (12 if shift else 0)
    if immediate > 0xFFF:
        raise ValueError(f"{word:#010x}: address adjustment does not fit ADD/SUB immediate")
    opcode = 0xD1000000 if offset < 0 else 0x91000000  # SUB/ADD Xd, Xn, #imm
    adjustment = opcode | (shift << 22) | (immediate << 10) | (rn << 5) | rd
    load_base = rn if writeback else rt
    load = 0xF9400000 | (load_base << 5) | rt  # LDR Xt, [Xn/SP]
    return SequenceLowering(mnemonic, (adjustment, load))


def _word(value: str) -> int:
    return int(value, 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("words", nargs="+", type=_word, help="little-endian instruction words, e.g. 0xdac10041")
    args = parser.parse_args()
    report = []
    try:
        for word in args.words:
            result = lower_sequence(word)
            report.append({
                "input": f"0x{word:08x}",
                "instruction": result.mnemonic if result else None,
                "replacements": [f"0x{replacement:08x}" for replacement in result.replacements] if result else [],
            })
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps({"schema": "nabu-arm64e-lowering-v2", "hardware_tested": False, "words": report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

