import importlib.util
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location("scan_arm64e_pauth", ROOT / "scan_arm64e_pauth.py")
SCAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCAN)


def macho_with_instruction(word: int, base_offset: int = 0) -> bytes:
    segment_size = 72 + 80
    code_offset = base_offset + 32 + segment_size
    header = struct.pack("<8I", 0xFEEDFACF, 0x0100000C, 2, 2, 1, segment_size, 0, 0)
    segment = struct.pack("<II16sQQQQiiII", 0x19, segment_size, b"__TEXT", 0x1000, 4, base_offset, segment_size + 4, 7, 5, 1, 0)
    section = struct.pack("<16s16sQQIIIIIIII", b"__text", b"__TEXT", 0x1000, 4, code_offset, 2, 0, 0, 0x80000400, 0, 0, 0)
    return header + segment + section + struct.pack("<I", word)


def fileset_with_instruction(word: int) -> bytes:
    ident = b"com.apple.kernel\0"
    command_size = 56
    member_offset = 32 + command_size
    command = struct.pack("<IIQQII", SCAN.LC_FILESET_ENTRY, command_size, 0x2000, member_offset, 32, 0)
    command += ident + bytes(command_size - len(command) - len(ident))
    header = struct.pack("<8I", 0xFEEDFACF, 0x0100000C, 2, SCAN.MH_FILESET, 1, command_size, 0, 0)
    return header + command + macho_with_instruction(word, member_offset)


class PointerAuthScanTests(unittest.TestCase):
    def test_scans_instruction_sections_without_changing_bytes(self):
        image = macho_with_instruction(0xD503233F)
        report = SCAN.scan_bytes(image)
        self.assertEqual(report["summary"]["by_instruction"], {"paciasp": 1})
        self.assertEqual(report["hit_samples"][0]["replacement_words"], ["0xd503201f"])
        self.assertFalse(report["image_modified"])

    def test_refuses_non_arm64e_images(self):
        image = bytearray(macho_with_instruction(0xD503233F))
        struct.pack_into("<I", image, 8, 0)
        with self.assertRaises(SCAN.MachOError):
            SCAN.scan_bytes(bytes(image))

    def test_follows_fileset_entry_to_kernel_code(self):
        report = SCAN.scan_bytes(fileset_with_instruction(0xD503233F))
        self.assertEqual(report["filetype"], "MH_FILESET")
        self.assertEqual(report["summary"]["fileset_members_scanned"], 1)
        self.assertEqual(report["summary"]["by_instruction"], {"paciasp": 1})

    def test_refuses_truncated_instruction_section(self):
        image = macho_with_instruction(0xD503233F)[:-1]
        with self.assertRaises(SCAN.MachOError):
            SCAN.scan_bytes(image)


if __name__ == "__main__":
    unittest.main()
