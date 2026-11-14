#!/usr/bin/env python3
"""Check that every symbol a kext imports is exported by a kernelcache fileset.

Use it with the macOS 27.3 kernelcache extracted from the local IPSW and the
`nm -u` list produced by the touch-kext CI (artifact nabu-touch-kext-symbols):

  check_kext_symbols.py kernelcache.macho undefined-symbols.txt [--json out.json]

It reads both files only. A symbol counts as exported when a fileset member's
LC_SYMTAB defines it (N_SECT). Exit status 0 means every import resolves.
"""
from __future__ import annotations

import argparse
import json
import sys

import scan_arm64e_pauth
from inspect_iohid_vtable import VTableError, _symbol_table


def exported_symbols(data: bytes) -> dict[str, str]:
    root_type, _, entries, _ = scan_arm64e_pauth._load_macho(data, 0, "root", False)
    if root_type != scan_arm64e_pauth.MH_FILESET:
        raise VTableError("input is not an MH_FILESET kernelcache")
    owners: dict[str, str] = {}
    for member_id, offset in entries:
        try:
            symbols, _, _, _ = _symbol_table(data, offset)
        except VTableError as error:
            if str(error) == "fileset member has no LC_SYMTAB":
                continue
            raise
        for name in symbols:
            owners.setdefault(name, member_id)
    return owners


def check(data: bytes, imports: list[str]) -> dict[str, object]:
    owners = exported_symbols(data)
    resolved = {name: owners[name] for name in imports if name in owners}
    missing = sorted(name for name in imports if name not in owners)
    by_member: dict[str, int] = {}
    for member in resolved.values():
        by_member[member] = by_member.get(member, 0) + 1
    return {"imports": len(imports), "resolved": len(resolved), "missing": missing,
            "resolved_by_member": dict(sorted(by_member.items()))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("kernelcache")
    parser.add_argument("undefined_symbols")
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    with open(args.undefined_symbols) as handle:
        imports = sorted({line.split()[-1] for line in handle if line.strip()})
    with open(args.kernelcache, "rb") as handle:
        report = check(handle.read(), imports)
    text = json.dumps(report, indent=2)
    if args.json:
        with open(args.json, "w") as handle:
            handle.write(text + "\n")
    print(text)
    return 0 if not report["missing"] else 1


if __name__ == "__main__":
    sys.exit(main())
