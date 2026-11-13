import importlib.util
import io
import struct
import unittest
from pathlib import Path


MODULE = Path(__file__).with_name("inspect_macho_arch.py")
SPEC = importlib.util.spec_from_file_location("inspect_macho_arch", MODULE)
MACHO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MACHO)


def thin(cputype, subtype, filetype=2):
    return struct.pack("<8I", 0xFEEDFACF, cputype, subtype, filetype, 0, 0, 0, 0)


class MachOArchitectureTests(unittest.TestCase):
    def test_arm64_and_arm64e_are_distinguished(self):
        ordinary = MACHO.inspect_stream(io.BytesIO(thin(MACHO.CPU_TYPE_ARM64, 0)), 32)
        auth = MACHO.inspect_stream(io.BytesIO(thin(MACHO.CPU_TYPE_ARM64, 2)), 32)
        self.assertEqual(ordinary["slices"][0]["architecture"], "arm64")
        self.assertFalse(ordinary["slices"][0]["arm64e"])
        self.assertEqual(auth["slices"][0]["architecture"], "arm64e")
        self.assertTrue(auth["slices"][0]["arm64e"])

    def test_universal_header_must_match_each_slice(self):
        payload = thin(MACHO.CPU_TYPE_ARM64, 2)
        header = struct.pack(">II", 0xCAFEBABE, 1)
        arch = struct.pack(">IIIII", MACHO.CPU_TYPE_ARM64, 2, 28, len(payload), 2)
        report = MACHO.inspect_stream(io.BytesIO(header + arch + payload), len(header + arch + payload))
        self.assertEqual(report["format"], "fat32")
        self.assertTrue(report["slices"][0]["arm64e"])

    def test_non_macho_is_ignored(self):
        self.assertIsNone(MACHO.inspect_stream(io.BytesIO(b"not a Mach-O"), 12))


if __name__ == "__main__":
    unittest.main()

