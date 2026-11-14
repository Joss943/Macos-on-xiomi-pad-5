"""Inspect an IOHIDDevice vtable inside an arm64e kernelcache fileset.

The report contains symbol addresses and ABI counts only. It does not extract
or write Apple kernel code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import scan_arm64e_pauth


LC_SYMTAB = 0x2
LC_SEGMENT_64 = 0x19
LC_DYLD_CHAINED_FIXUPS = 0x80000034
N_TYPE = 0x0E
DYLD_CHAINED_PTR_64_KERNEL_CACHE = 8
DYLD_CHAINED_PTR_START_NONE = 0xFFFF
DYLD_CHAINED_PTR_START_MULTI = 0x8000
DYLD_CHAINED_PTR_START_LAST = 0x8000


class VTableError(ValueError):
    pass


def _symbol_table(
    data: bytes, base: int
) -> tuple[dict[str, int], list[tuple[int, int, int, int, str]], list[tuple[int, int, int, int, str]], bool]:
    if base < 0 or base + 32 > len(data):
        raise VTableError("truncated fileset member")
    _, _, _, _, ncmds, sizeofcmds, _, _ = struct.unpack_from("<8I", data, base)
    offset = base + 32
    command_end = offset + sizeofcmds
    if ncmds > 65536 or command_end > len(data):
        raise VTableError("load-command table leaves file bounds")

    symtab: tuple[int, int, int, int] | None = None
    segments: list[tuple[int, int, int, int, str]] = []
    chained_fixups = False
    for _ in range(ncmds):
        if offset + 8 > command_end:
            raise VTableError("truncated load command")
        command, command_size = struct.unpack_from("<II", data, offset)
        if command_size < 8 or offset + command_size > command_end:
            raise VTableError("invalid load-command size")
        if command == LC_SYMTAB:
            if command_size < 24:
                raise VTableError("truncated LC_SYMTAB")
            symtab = struct.unpack_from("<4I", data, offset + 8)
        elif command == LC_SEGMENT_64:
            if command_size < 72:
                raise VTableError("truncated LC_SEGMENT_64")
            name = struct.unpack_from("<16s", data, offset + 8)[0].split(b"\0", 1)[0].decode("ascii", "replace")
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", data, offset + 24)
            segments.append((vmaddr, vmsize, fileoff, filesize, name))
        elif command == LC_DYLD_CHAINED_FIXUPS:
            chained_fixups = True
        offset += command_size
    if offset != command_end:
        raise VTableError("load-command sizes do not match sizeofcmds")
    if symtab is None:
        raise VTableError("fileset member has no LC_SYMTAB")

    symoff, nsyms, stroff, strsize = symtab
    if nsyms > 10_000_000 or symoff + nsyms * 16 > len(data) or stroff + strsize > len(data):
        raise VTableError("symbol table leaves file bounds")
    symbols: dict[str, int] = {}
    records: list[tuple[int, int, int, int, str]] = []
    for index in range(nsyms):
        strx, n_type, n_sect, n_desc, n_value = struct.unpack_from("<IBBHQ", data, symoff + index * 16)
        if n_type & N_TYPE != N_TYPE or strx >= strsize:
            continue
        name_start = stroff + strx
        name_end = data.find(b"\0", name_start, stroff + strsize)
        if name_end < 0:
            continue
        name = data[name_start:name_end].decode("utf-8", "replace")
        if name:
            records.append((n_value, n_sect, n_type, n_desc, name))
            symbols[name] = n_value
    return symbols, records, segments, chained_fixups


def _root_segments_and_fixups(
    data: bytes,
) -> tuple[list[tuple[int, int, int, int, str]], tuple[int, int] | None]:
    if len(data) < 32:
        raise VTableError("truncated root Mach-O header")
    _, _, _, _, ncmds, sizeofcmds, _, _ = struct.unpack_from("<8I", data, 0)
    offset = 32
    command_end = offset + sizeofcmds
    if command_end > len(data) or ncmds > 65536:
        raise VTableError("root load-command table leaves file bounds")

    segments: list[tuple[int, int, int, int, str]] = []
    fixups: tuple[int, int] | None = None
    for _ in range(ncmds):
        if offset + 8 > command_end:
            raise VTableError("truncated root load command")
        command, command_size = struct.unpack_from("<II", data, offset)
        if command_size < 8 or offset + command_size > command_end:
            raise VTableError("invalid root load-command size")
        if command == LC_SEGMENT_64:
            if command_size < 72:
                raise VTableError("truncated root LC_SEGMENT_64")
            name = struct.unpack_from("<16s", data, offset + 8)[0].split(b"\0", 1)[0].decode("ascii", "replace")
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", data, offset + 24)
            segments.append((vmaddr, vmsize, fileoff, filesize, name))
        elif command == LC_DYLD_CHAINED_FIXUPS:
            if command_size < 16 or fixups is not None:
                raise VTableError("invalid or duplicate root LC_DYLD_CHAINED_FIXUPS")
            dataoff, datasize = struct.unpack_from("<II", data, offset + 8)
            if dataoff + datasize > len(data):
                raise VTableError("root chained-fixups payload leaves file bounds")
            fixups = (dataoff, datasize)
        offset += command_size
    if offset != command_end:
        raise VTableError("root load-command sizes do not match sizeofcmds")
    return segments, fixups


def _fileset_symbol_records(
    data: bytes,
    entries: list[tuple[str, int]],
) -> tuple[list[tuple[int, int, int, int, str]], int]:
    records: list[tuple[int, int, int, int, str]] = []
    members_with_symbols = 0
    for _, member_offset in entries:
        try:
            _, member_records, _, _ = _symbol_table(data, member_offset)
        except VTableError as error:
            if str(error) == "fileset member has no LC_SYMTAB":
                continue
            raise
        records.extend(member_records)
        members_with_symbols += 1
    return records, members_with_symbols


def _chained_vtable_report(
    data: bytes,
    function_start: int,
    function_end: int,
    fileset_records: list[tuple[int, int, int, int, str]],
    symbol_member_count: int,
) -> dict[str, object]:
    root_segments, fixups_command = _root_segments_and_fixups(data)
    if fixups_command is None:
        return {"available": False, "reason": "root has no LC_DYLD_CHAINED_FIXUPS"}

    fixups_offset, fixups_size = fixups_command
    fixups = data[fixups_offset : fixups_offset + fixups_size]
    if len(fixups) < 28:
        raise VTableError("truncated chained-fixups header")
    version, starts_offset, imports_offset, symbols_offset, imports_count, imports_format, symbols_format = struct.unpack_from(
        "<7I", fixups, 0
    )
    if version != 0 or starts_offset + 4 > len(fixups):
        raise VTableError("unsupported or truncated chained-fixups header")
    segment_count = struct.unpack_from("<I", fixups, starts_offset)[0]
    if segment_count > 65536 or starts_offset + 4 + segment_count * 4 > len(fixups):
        raise VTableError("chained starts-in-image table leaves fixups payload")
    if segment_count != len(root_segments):
        raise VTableError("chained segment count does not match root Mach-O segments")

    target_segment_index = next(
        (
            index
            for index, (vmaddr, vmsize, _, _, _) in enumerate(root_segments)
            if vmaddr <= function_start < function_end <= vmaddr + vmsize
        ),
        None,
    )
    if target_segment_index is None:
        return {"available": True, "decoded": False, "reason": "vtable is outside root segments"}

    segment_starts_offset = struct.unpack_from("<I", fixups, starts_offset + 4 + target_segment_index * 4)[0]
    if segment_starts_offset == 0:
        return {"available": True, "decoded": False, "reason": "vtable root segment has no chain starts"}
    starts_base = starts_offset + segment_starts_offset
    if starts_base + 22 > len(fixups):
        raise VTableError("truncated chained starts-in-segment")
    starts_size, page_size, pointer_format = struct.unpack_from("<IHH", fixups, starts_base)
    segment_offset = struct.unpack_from("<Q", fixups, starts_base + 8)[0]
    max_valid_pointer, page_count = struct.unpack_from("<IH", fixups, starts_base + 16)
    segment_end = starts_base + starts_size
    page_starts_base = starts_base + 22
    page_starts_end = page_starts_base + page_count * 2
    if starts_size < 22 or segment_end > len(fixups) or page_starts_end > segment_end:
        raise VTableError("chained page-start table leaves segment record")
    if pointer_format != DYLD_CHAINED_PTR_64_KERNEL_CACHE:
        return {
            "available": True,
            "decoded": False,
            "root_segment_index": target_segment_index,
            "pointer_format": pointer_format,
            "reason": "vtable uses an unsupported chained-pointer format",
        }
    if page_size == 0:
        raise VTableError("chained page size is zero")

    root_vmaddr, root_vmsize, root_fileoff, root_filesize, root_name = root_segments[target_segment_index]
    first_page = (function_start - root_vmaddr) // page_size
    last_page = (function_end - 1 - root_vmaddr) // page_size
    if last_page >= page_count:
        raise VTableError("vtable pages exceed chained starts-in-segment")
    decoded_slots: dict[int, dict[str, int | bool]] = {}

    for page_index in range(first_page, last_page + 1):
        page_entry = struct.unpack_from("<H", fixups, page_starts_base + page_index * 2)[0]
        if page_entry == DYLD_CHAINED_PTR_START_NONE:
            continue
        if page_entry & DYLD_CHAINED_PTR_START_MULTI:
            overflow_index = page_entry & ~DYLD_CHAINED_PTR_START_MULTI
            chain_starts: list[int] = []
            while True:
                overflow_offset = page_starts_end + overflow_index * 2
                if overflow_offset + 2 > segment_end:
                    raise VTableError("multi-start chain list leaves segment record")
                overflow_entry = struct.unpack_from("<H", fixups, overflow_offset)[0]
                chain_starts.append(overflow_entry & ~DYLD_CHAINED_PTR_START_LAST)
                overflow_index += 1
                if overflow_entry & DYLD_CHAINED_PTR_START_LAST:
                    break
                if len(chain_starts) > page_size // 4:
                    raise VTableError("unterminated multi-start chain list")
        else:
            chain_starts = [page_entry]

        page_vmaddr = root_vmaddr + page_index * page_size
        page_fileoff = root_fileoff + page_index * page_size
        for chain_start in chain_starts:
            chain_offset = chain_start
            visited: set[int] = set()
            for _ in range(page_size // 4 + 1):
                if chain_offset in visited or chain_offset + 8 > page_size:
                    raise VTableError("invalid or cyclic chained pointer in vtable page")
                visited.add(chain_offset)
                pointer_fileoff = page_fileoff + chain_offset
                if pointer_fileoff + 8 > root_fileoff + root_filesize or pointer_fileoff + 8 > len(data):
                    raise VTableError("chained pointer leaves root segment file data")
                raw = struct.unpack_from("<Q", data, pointer_fileoff)[0]
                next_delta = (raw >> 51) & 0xFFF
                pointer_address = page_vmaddr + chain_offset
                if function_start <= pointer_address < function_end:
                    if (pointer_address - function_start) % 8:
                        raise VTableError("chained pointer overlaps a vtable slot boundary")
                    decoded_slots[pointer_address] = {
                        "target_offset": raw & 0x3FFFFFFF,
                        "cache_level": (raw >> 30) & 0x3,
                        "diversity": (raw >> 32) & 0xFFFF,
                        "address_diversity": bool((raw >> 48) & 1),
                        "key": (raw >> 49) & 0x3,
                        "authenticated": bool(raw >> 63),
                    }
                if next_delta == 0:
                    break
                # Apple's format 8 allows a byte or four-byte stride. These
                # kernelcache entries use the documented four-byte stride.
                chain_offset += next_delta * 4
            else:
                raise VTableError("chained pointer walk exceeded the page bound")

    slot_count = (function_end - function_start) // 8
    if (function_end - function_start) % 8:
        raise VTableError("vtable function range is not pointer aligned")
    slot_records = [decoded_slots.get(function_start + slot * 8) for slot in range(slot_count)]
    present = [record for record in slot_records if record is not None]
    authenticated = [record for record in present if record["authenticated"]]
    empty_slots: list[int] = []
    unresolved_nonzero_slots: list[dict[str, object]] = []
    for slot, record in enumerate(slot_records):
        if record is not None:
            continue
        slot_address = function_start + slot * 8
        pointer_fileoff = root_fileoff + slot_address - root_vmaddr
        if pointer_fileoff + 8 > root_fileoff + root_filesize or pointer_fileoff + 8 > len(data):
            raise VTableError("unfixed vtable slot leaves root segment file data")
        raw = struct.unpack_from("<Q", data, pointer_fileoff)[0]
        if raw == 0:
            empty_slots.append(slot)
        else:
            unresolved_nonzero_slots.append({"slot": slot, "raw_word": f"0x{raw:016x}"})
    key_names = {0: "IA", 1: "IB", 2: "DA", 3: "DB"}
    key_counts: dict[str, int] = {}
    cache_level_counts: dict[str, int] = {}
    for record in present:
        key = key_names[int(record["key"])] if record["authenticated"] else "unauthenticated"
        key_counts[key] = key_counts.get(key, 0) + 1
        level = str(record["cache_level"])
        cache_level_counts[level] = cache_level_counts.get(level, 0) + 1

    cache_base = root_vmaddr - segment_offset
    exact_symbols: dict[int, list[str]] = {}
    for symbol_address, _, _, _, symbol_name in fileset_records:
        names = exact_symbols.setdefault(symbol_address, [])
        if symbol_name not in names:
            names.append(symbol_name)
    slot_symbols: list[dict[str, object]] = []
    for slot, record in enumerate(slot_records):
        if record is None or int(record["cache_level"]) != 0:
            continue
        names = exact_symbols.get(cache_base + int(record["target_offset"]), [])
        if names:
            slot_symbols.append({"slot": slot, "symbols": names})
    first_slot = decoded_slots.get(function_start)
    if first_slot is not None:
        first_slot = dict(first_slot)
        if int(first_slot["cache_level"]) == 0:
            first_slot["resolved_target_address"] = f"0x{cache_base + int(first_slot['target_offset']):016x}"
            first_slot["exact_symbols"] = exact_symbols.get(cache_base + int(first_slot["target_offset"]), [])

    return {
        "available": True,
        "decoded": not unresolved_nonzero_slots,
        "kernelcache_root_segment": root_name,
        "root_segment_index": target_segment_index,
        "segment_offset": f"0x{segment_offset:x}",
        "segment_vmsize": root_vmsize,
        "page_size": page_size,
        "pointer_format": pointer_format,
        "pointer_format_name": "DYLD_CHAINED_PTR_64_KERNEL_CACHE",
        "chain_stride_bytes": 4,
        "vtable_slots": slot_count,
        "slots_with_fixups": len(present),
        "authenticated_slots": len(authenticated),
        "unauthenticated_slots": len(present) - len(authenticated),
        "slots_missing_fixups": slot_count - len(present),
        "missing_slot_indexes": [slot for slot, record in enumerate(slot_records) if record is None],
        "zero_padding_slot_indexes": empty_slots,
        "unresolved_nonzero_slots": unresolved_nonzero_slots,
        "authentication_key_counts": key_counts,
        "cache_level_counts": cache_level_counts,
        "cache_level_zero_base": f"0x{cache_base:016x}",
        "exact_symbolized_slots": len(slot_symbols),
        "fileset_members_with_symbols": symbol_member_count,
        "slot_symbols": slot_symbols,
        "first_slot": first_slot,
        "max_valid_pointer": max_valid_pointer,
        "imports_count": imports_count,
        "imports_format": imports_format,
        "symbols_format": symbols_format,
    }


def inspect_vtable(data: bytes, member_id: str = "com.apple.iokit.IOHIDFamily", reference_slots: int = 207) -> dict[str, object]:
    root_type, _, entries, _ = scan_arm64e_pauth._load_macho(data, 0, "root", False)
    if root_type != scan_arm64e_pauth.MH_FILESET:
        raise VTableError("input is not an MH_FILESET kernelcache")
    member_offsets = [offset for ident, offset in entries if ident == member_id]
    if len(member_offsets) != 1:
        raise VTableError(f"expected exactly one fileset member {member_id!r}, found {len(member_offsets)}")

    symbols, records, segments, chained_fixups = _symbol_table(data, member_offsets[0])
    fileset_records, symbol_member_count = _fileset_symbol_records(data, entries)
    table_name = "__ZTV11IOHIDDevice"
    next_name = "__ZTVN11IOHIDDevice9MetaClassE"
    if table_name not in symbols or next_name not in symbols:
        raise VTableError("IOHIDDevice vtable boundary symbols are missing")
    table_address = symbols[table_name]
    next_address = symbols[next_name]
    if next_address <= table_address or (next_address - table_address) % 8:
        raise VTableError("invalid IOHIDDevice vtable boundary")

    table_records = [record for record in records if record[4] == table_name]
    next_records = [record for record in records if record[4] == next_name]
    if len(table_records) != 1 or len(next_records) != 1 or table_records[0][1] != next_records[0][1]:
        raise VTableError("vtable boundary symbols are not unique in one section")

    table_bytes = next_address - table_address
    header_bytes = 16  # Itanium ABI offset-to-top and typeinfo entries.
    if table_bytes < header_bytes or (table_bytes - header_bytes) % 8:
        raise VTableError("vtable extent is not pointer aligned")
    mapping = next((segment for segment in segments if segment[0] <= table_address and table_address + table_bytes <= segment[0] + segment[1]), None)
    if mapping is None:
        raise VTableError("vtable address is not backed by a segment")
    vmaddr, _, fileoff, filesize, segment_name = mapping
    file_offset = fileoff + table_address - vmaddr
    if file_offset + table_bytes > fileoff + filesize or file_offset + table_bytes > len(data):
        raise VTableError("vtable extent leaves its segment")

    inferred_slots = (table_bytes - header_bytes) // 8
    chained_pointers = _chained_vtable_report(
        data,
        table_address + header_bytes,
        next_address,
        fileset_records,
        symbol_member_count,
    )
    return {
        "schema": "arm64e-iohid-vtable-report-v1",
        "kernelcache_sha256": hashlib.sha256(data).hexdigest(),
        "fileset_member": member_id,
        "vtable_symbol": table_name,
        "vtable_address": f"0x{table_address:016x}",
        "address_point": f"0x{table_address + header_bytes:016x}",
        "next_symbol": next_name,
        "next_symbol_address": f"0x{next_address:016x}",
        "segment": segment_name,
        "vtable_extent_bytes_including_abi_header": table_bytes,
        "inferred_function_slots": inferred_slots,
        "callable_slots_from_root_chains": chained_pointers.get("slots_with_fixups"),
        "zero_padding_slots_from_root_chains": chained_pointers.get("zero_padding_slot_indexes"),
        "reference_driver_function_slots": reference_slots,
        "reference_slot_layout_matches": inferred_slots == reference_slots,
        "member_has_lc_dyld_chained_fixups": chained_fixups,
        "root_chained_vtable_pointers": chained_pointers,
        "kernelcache_modified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernelcache", type=Path, help="decompressed arm64e MH_FILESET kernelcache")
    parser.add_argument("--member", default="com.apple.iokit.IOHIDFamily", help="fileset member identifier")
    parser.add_argument("--reference-slots", type=int, default=207, help="reference driver's known virtual slot count")
    parser.add_argument("--output", type=Path, help="write JSON report to a new file")
    args = parser.parse_args()
    try:
        report = inspect_vtable(args.kernelcache.read_bytes(), args.member, args.reference_slots)
    except (OSError, VTableError, scan_arm64e_pauth.MachOError, struct.error) as error:
        parser.error(str(error))
    rendered = json.dumps(report, indent=2)
    if args.output:
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
