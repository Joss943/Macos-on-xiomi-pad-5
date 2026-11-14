from __future__ import annotations

import struct
import unittest

import scan_arm64e_pauth


def _segment_command(name: str, file_offset: int, file_size: int) -> bytes:
    return struct.pack(
        "<II16sQQQQiiII",
        scan_arm64e_pauth.LC_SEGMENT_64,
        72,
        name.encode("ascii").ljust(16, b"\0"),
        0,
        file_size,
        file_offset,
        file_size,
        7,
        5,
        0,
        0,
    )


def _macho(filetype: int, commands: bytes, ncmds: int) -> bytes:
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


class FilesetCoverageTests(unittest.TestCase):
    def test_root_executable_segments_are_not_dropped(self):
        root_segment = _segment_command("__TEXT_EXEC", 0x800, 4)
        ident = b"com.apple.kernel\0"
        entry_size = 32 + len(ident)
        entry = struct.pack(
            "<IIQQII",
            scan_arm64e_pauth.LC_FILESET_ENTRY,
            entry_size,
            0,
            0x1000,
            32,
            0,
        ) + ident
        root = _macho(scan_arm64e_pauth.MH_FILESET, root_segment + entry, 2)

        member_segment = _segment_command("__TEXT_EXEC", 0x1200, 4)
        member = _macho(2, member_segment, 1)
        image = bytearray(0x1204)
        image[: len(root)] = root
        image[0x1000 : 0x1000 + len(member)] = member

        report = scan_arm64e_pauth.scan_bytes(bytes(image))

        self.assertIn("root:__TEXT_EXEC", report["uncovered_executable_segments"])
        self.assertEqual(report["summary"]["fileset_members_scanned"], 1)
        self.assertIn("com.apple.kernel:__TEXT_EXEC", [r["name"] for r in report["regions"]])


if __name__ == "__main__":
    unittest.main()
