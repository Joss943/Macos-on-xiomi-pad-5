from __future__ import annotations

import struct
import unittest

import inspect_iohid_vtable
import scan_arm64e_pauth


def _segment(vmaddr: int, vmsize: int, fileoff: int, filesize: int) -> bytes:
    return struct.pack(
        "<II16sQQQQiiII",
        scan_arm64e_pauth.LC_SEGMENT_64,
        72,
        b"__DATA_CONST\0\0\0\0",
        vmaddr,
        vmsize,
        fileoff,
        filesize,
        7,
        3,
        0,
        0,
    )


def _header(filetype: int, commands: bytes, ncmds: int) -> bytes:
    return struct.pack(
        "<8I",
        0xFEEDFACF,
        scan_arm64e_pauth.CPU_TYPE_ARM64,
        scan_arm64e_pauth.CPU_SUBTYPE_ARM64E,
        filetype,
        ncmds,
        len(commands),
        0,
        0,
    ) + commands


def _fileset_with_vtable(slots: int) -> bytes:
    member_id = b"com.apple.iokit.IOHIDFamily\0"
    entry = struct.pack(
        "<IIQQII",
        0x80000035,
        32 + len(member_id),
        0,
        0x1000,
        32,
        0,
    ) + member_id
    root = _header(scan_arm64e_pauth.MH_FILESET, entry, 1)

    vmaddr = 0xFFFFFE0000000000
    table = vmaddr + 0x100
    next_table = table + 16 + slots * 8
    strings = b"\0__ZTV11IOHIDDevice\0__ZTVN11IOHIDDevice9MetaClassE\0"
    table_name = 1
    next_name = table_name + len(b"__ZTV11IOHIDDevice\0")
    segment = _segment(vmaddr, 0x1000, 0x2000, 0x1000)
    symoff, stroff = 0x3000, 0x3100
    symtab = struct.pack("<6I", 2, 24, symoff, 2, stroff, len(strings))
    member = _header(11, segment + symtab, 2)

    image = bytearray(0x4000)
    image[: len(root)] = root
    image[0x1000 : 0x1000 + len(member)] = member
    struct.pack_into("<IBBHQ", image, symoff, table_name, 0x0F, 1, 0, table)
    struct.pack_into("<IBBHQ", image, symoff + 16, next_name, 0x0F, 1, 0, next_table)
    image[stroff : stroff + len(strings)] = strings
    return bytes(image)


def _fileset_with_chained_vtable(slots: int, empty_last: bool = False) -> bytes:
    member_id = b"com.apple.iokit.IOHIDFamily\0"
    entry = struct.pack(
        "<IIQQII",
        0x80000035,
        32 + len(member_id),
        0,
        0x1000,
        32,
        0,
    ) + member_id
    vmaddr = 0xFFFFFE0000000000
    root_segment = _segment(vmaddr, 0x4000, 0x4000, 0x4000)
    fixups_offset = 0x8000
    fixups_size = 60
    fixups_command = struct.pack("<4I", inspect_iohid_vtable.LC_DYLD_CHAINED_FIXUPS, 16, fixups_offset, fixups_size)
    root_commands = entry + root_segment + fixups_command
    root = _header(scan_arm64e_pauth.MH_FILESET, root_commands, 3)

    table = vmaddr + 0x100
    next_table = table + 16 + slots * 8
    strings = b"\0__ZTV11IOHIDDevice\0__ZTVN11IOHIDDevice9MetaClassE\0"
    table_name = 1
    next_name = table_name + len(b"__ZTV11IOHIDDevice\0")
    member_segment = _segment(vmaddr, 0x4000, 0x4000, 0x4000)
    symoff, stroff = 0x3000, 0x3100
    symtab = struct.pack("<6I", 2, 24, symoff, 2, stroff, len(strings))
    member = _header(11, member_segment + symtab, 2)

    # starts_in_image has one segment, followed by its starts-in-segment record.
    starts_in_segment = struct.pack("<IHHQIH", 24, 0x4000, 8, 0, 0, 1) + struct.pack("<H", 0)
    starts_in_image = struct.pack("<II", 1, 8) + starts_in_segment
    fixups = struct.pack("<7I", 0, 28, fixups_size, fixups_size, 0, 1, 0) + starts_in_image

    image = bytearray(0x9000)
    image[: len(root)] = root
    image[0x1000 : 0x1000 + len(member)] = member
    struct.pack_into("<IBBHQ", image, symoff, table_name, 0x0F, 1, 0, table)
    struct.pack_into("<IBBHQ", image, symoff + 16, next_name, 0x0F, 1, 0, next_table)
    image[stroff : stroff + len(strings)] = strings
    image[fixups_offset : fixups_offset + len(fixups)] = fixups

    def kernel_cache_pointer(target: int, next_count: int, authenticated: bool, diversity: int = 0) -> int:
        return (
            target
            | ((diversity & 0xFFFF) << 32)
            | (1 << 48)
            | (next_count << 51)
            | (int(authenticated) << 63)
        )

    # The page chain begins at offset 0 and reaches the vtable's first function.
    struct.pack_into("<Q", image, 0x4000, kernel_cache_pointer(0, (0x110 // 4), False))
    present_slots = slots - int(empty_last)
    for slot in range(present_slots):
        next_count = 2 if slot + 1 < present_slots else 0
        raw = kernel_cache_pointer(0x12345 + slot * 8, next_count, slot < 2, 0xA000 + slot)
        struct.pack_into("<Q", image, 0x4000 + 0x110 + slot * 8, raw)
    return bytes(image)


class IOHIDVTableTests(unittest.TestCase):
    def test_infers_slots_from_adjacent_vtable_symbols(self):
        report = inspect_iohid_vtable.inspect_vtable(_fileset_with_vtable(3), reference_slots=3)
        self.assertEqual(report["inferred_function_slots"], 3)
        self.assertTrue(report["reference_slot_layout_matches"])
        self.assertFalse(report["kernelcache_modified"])
        self.assertFalse(report["root_chained_vtable_pointers"]["available"])

    def test_decodes_authenticated_root_kernel_cache_vtable_pointers(self):
        report = inspect_iohid_vtable.inspect_vtable(
            _fileset_with_chained_vtable(4, empty_last=True), reference_slots=4
        )
        chained = report["root_chained_vtable_pointers"]
        self.assertTrue(chained["decoded"])
        self.assertEqual(chained["pointer_format_name"], "DYLD_CHAINED_PTR_64_KERNEL_CACHE")
        self.assertEqual(chained["vtable_slots"], 4)
        self.assertEqual(chained["slots_with_fixups"], 3)
        self.assertEqual(chained["authenticated_slots"], 2)
        self.assertEqual(chained["unauthenticated_slots"], 1)
        self.assertEqual(chained["slots_missing_fixups"], 1)
        self.assertEqual(chained["zero_padding_slot_indexes"], [3])
        self.assertEqual(chained["first_slot"]["target_offset"], 0x12345)
        self.assertEqual(chained["first_slot"]["diversity"], 0xA000)


if __name__ == "__main__":
    unittest.main()
