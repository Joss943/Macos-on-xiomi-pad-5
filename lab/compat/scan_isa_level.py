#!/usr/bin/env python3
"""Count AArch64 instructions that a Kryo 485 core (SM8150, nabu) cannot execute.

Kryo 485 is Cortex-A76 (performance) plus Cortex-A55 (efficiency): ARMv8.2-A with
LSE, RDM, FP16, DotProd, RAS, crypto and RCpc (LDAPR). Anything newer traps as an
undefined instruction, and IMPLEMENTATION DEFINED system registers in the Apple
space (S3_x_C15_Cx_x) address Apple-only hardware.

The scanner disassembles a Mach-O with llvm-objdump (every AArch64 feature enabled
so that new instructions decode by name) and classifies each mnemonic. It reads
the input only. Literal pools inside __text decode as instructions too, so counts
are upper bounds; samples carry addresses for manual confirmation.

Usage:
  scan_isa_level.py <macho> [--objdump PATH] [--json OUT] [--samples N]
Exit status: 0 when no trapping instruction was found, 1 otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict

PAUTH_NON_HINT = {
    "pacia", "pacib", "pacda", "pacdb", "autia", "autib", "autda", "autdb",
    "paciza", "pacizb", "pacdza", "pacdzb", "autiza", "autizb", "autdza", "autdzb",
    "xpaci", "xpacd", "pacga", "braa", "brab", "braaz", "brabz", "blraa", "blrab",
    "blraaz", "blrabz", "retaa", "retab", "eretaa", "eretab", "ldraa", "ldrab",
}
PAUTH_HINT = {
    "paciasp", "pacibsp", "autiasp", "autibsp", "paciaz", "pacibz", "autiaz", "autibz",
    "pacia1716", "pacib1716", "autia1716", "autib1716", "xpaclri",
}
BY_MNEMONIC = {
    "fjcvtzs": "FEAT_JSCVT (v8.3)",
    "fcmla": "FEAT_FCMA (v8.3)",
    "fcadd": "FEAT_FCMA (v8.3)",
    "cfinv": "FEAT_FlagM (v8.4)",
    "rmif": "FEAT_FlagM (v8.4)",
    "setf8": "FEAT_FlagM (v8.4)",
    "setf16": "FEAT_FlagM (v8.4)",
    "sb": "FEAT_SB (v8.5)",
    "axflag": "FEAT_FlagM2 (v8.5)",
    "xaflag": "FEAT_FlagM2 (v8.5)",
    "frint32x": "FEAT_FRINTTS (v8.5)",
    "frint32z": "FEAT_FRINTTS (v8.5)",
    "frint64x": "FEAT_FRINTTS (v8.5)",
    "frint64z": "FEAT_FRINTTS (v8.5)",
    "wfet": "FEAT_WFxT (v8.7)",
    "wfit": "FEAT_WFxT (v8.7)",
    "ld64b": "FEAT_LS64 (v8.7)",
    "st64b": "FEAT_LS64 (v8.7)",
    "st64bv": "FEAT_LS64 (v8.7)",
    "st64bv0": "FEAT_LS64 (v8.7)",
    "smstart": "FEAT_SME",
    "smstop": "FEAT_SME",
}
for _m in ("ldapur", "ldapurb", "ldapurh", "ldapursb", "ldapursh", "ldapursw",
           "stlur", "stlurb", "stlurh"):
    BY_MNEMONIC[_m] = "FEAT_LRCPC2 (v8.4)"
for _m in ("irg", "gmi", "subp", "subps", "addg", "subg", "stg", "stzg", "st2g", "stz2g",
           "ldg", "stgp", "ldgm", "stgm", "stzgm"):
    BY_MNEMONIC[_m] = "FEAT_MTE (v8.5)"
for _m in ("bfdot", "bfmmla", "bfmlalb", "bfmlalt", "bfcvt", "bfcvtn", "bfcvtn2"):
    BY_MNEMONIC[_m] = "FEAT_BF16 (v8.6)"
for _m in ("smmla", "ummla", "usmmla", "usdot", "sudot"):
    BY_MNEMONIC[_m] = "FEAT_I8MM (v8.6)"
CSSC_SCALAR = {"abs", "cnt", "ctz", "smax", "smin", "umax", "umin"}
MOPS = re.compile(r"^(cpyf?[pme](wn|rn|n|wt|rt|t|wtwn|wtrn|wtn|rtwn|rtrn|rtn|twn|trn|tn)?|set[pme](t|n|tn)?|setg[pme](t|n|tn)?)$")
APPLE_SYSREG = re.compile(r"\bS3_[0-7]_C15_C\d+_[0-7]\b", re.IGNORECASE)
SVE_OPERAND = re.compile(r"(^|[\s,{\[])(z\d+|p\d+|za\w*)\b", re.IGNORECASE)
LINE = re.compile(r"^\s*(?P<addr>[0-9a-fA-F]+):\s+(?P<mnemonic>[a-z][a-z0-9.]*)(?:\s+(?P<ops>.*))?$")


def classify(mnemonic: str, operands: str) -> str | None:
    """Return the missing feature for one instruction, or None if Kryo 485 runs it."""
    base = mnemonic.split(".", 1)[0]
    ops = operands or ""
    if base in PAUTH_NON_HINT:
        return "FEAT_PAuth non-HINT (v8.3)"
    if base in BY_MNEMONIC:
        return BY_MNEMONIC[base]
    if base == "bc":
        return "FEAT_HBC (v8.8)"
    if MOPS.match(base):
        return "FEAT_MOPS (v8.8)"
    if base in CSSC_SCALAR and "." not in mnemonic and re.match(r"^\s*[wx]\d+", ops):
        return "FEAT_CSSC (v8.9)"
    if base in ("mrs", "msr"):
        if APPLE_SYSREG.search(ops):
            return "Apple IMPLEMENTATION DEFINED sysreg"
        first = ops.split(",", 1)[0].strip().lower()
        if first == "dit":
            return "FEAT_DIT (v8.4)"
        if first in ("cntvctss_el0", "cntpctss_el0"):
            return "FEAT_ECV (v8.6)"
        if first in ("tco",):
            return "FEAT_MTE (v8.5)"
    if base == "tlbi":
        op = ops.split(",", 1)[0].strip().lower()
        if op.startswith("r"):
            return "FEAT_TLBIRANGE (v8.4)"
        if op.endswith("os"):
            return "FEAT_TLBIOS (v8.4)"
    if base == "dsb" and "nxs" in ops.lower():
        return "FEAT_XS (v8.7)"
    if SVE_OPERAND.search(ops):
        return "FEAT_SVE/SME"
    return None


def scan_listing(text: str, sample_limit: int = 8) -> dict:
    features: Counter = Counter()
    samples: dict = defaultdict(list)
    hints = 0
    total = 0
    for raw in text.splitlines():
        match = LINE.match(raw)
        if not match:
            continue
        total += 1
        mnemonic = match["mnemonic"].lower()
        operands = match["ops"] or ""
        if mnemonic in PAUTH_HINT:
            hints += 1
            continue
        feature = classify(mnemonic, operands)
        if feature is None:
            continue
        features[feature] += 1
        if len(samples[feature]) < sample_limit:
            samples[feature].append(f"{match['addr']}: {mnemonic} {operands}".strip())
    return {
        "instructions": total,
        "pauth_hint_nops": hints,
        "trapping_or_foreign": sum(features.values()),
        "by_feature": dict(sorted(features.items(), key=lambda item: -item[1])),
        "samples": {key: value for key, value in samples.items()},
    }


def find_objdump(explicit: str | None) -> list[str]:
    if explicit:
        return [explicit]
    for name in ("llvm-objdump", "llvm-objdump-18", "llvm-objdump-19", "llvm-objdump-20"):
        path = shutil.which(name)
        if path:
            return [path]
    if shutil.which("xcrun"):
        return ["xcrun", "llvm-objdump"]
    raise SystemExit("scan_isa_level: llvm-objdump not found; pass --objdump")


def disassemble(path: str, objdump: list[str]) -> str:
    command = objdump + ["-d", "--no-show-raw-insn", "--mattr=+all", path]
    result = subprocess.run(command, check=True, capture_output=True, text=True, errors="replace")
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("macho")
    parser.add_argument("--objdump")
    parser.add_argument("--json")
    parser.add_argument("--samples", type=int, default=8)
    args = parser.parse_args(argv)
    with open(args.macho, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    report = scan_listing(disassemble(args.macho, find_objdump(args.objdump)), args.samples)
    report = {"input_sha256": digest, "target": "Kryo 485 (Cortex-A76/A55, ARMv8.2-A+RCpc)", **report}
    text = json.dumps(report, indent=2)
    if args.json:
        with open(args.json, "w") as handle:
            handle.write(text + "\n")
    print(text)
    return 0 if report["trapping_or_foreign"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
