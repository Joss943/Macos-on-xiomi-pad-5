import hashlib
import struct
import unittest

from rewrite_macho_pauth import RewriteError, rewrite_bytes


MH_MAGIC_64 = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
CPU_SUBTYPE_ARM64E = 2
LC_SEGMENT_64 = 0x19
LC_CODE_SIGNATURE = 0x1D
S_ATTR_PURE_INSTRUCTIONS = 0x80000000


def make_signed_fixture(instructions):
    code_offset = 256
    signature_offset = code_offset + 4 * len(instructions)
    commands_size = 152 + 16
    signature_size = 100
    header = struct.pack(
        "<8I",
        MH_MAGIC_64,
        CPU_TYPE_ARM64,
        CPU_SUBTYPE_ARM64E,
        2,
        2,
        commands_size,
        0,
        0,
    )
    segment = struct.pack(
        "<II16sQQQQiiII",
        LC_SEGMENT_64,
        152,
        b"__TEXT\0".ljust(16, b"\0"),
        0x100000000,
        signature_offset,
        0,
        signature_offset,
        7,
        5,
        1,
        0,
    )
    section = struct.pack(
        "<16s16sQQIIIIIIII",
        b"__text\0".ljust(16, b"\0"),
        b"__TEXT\0".ljust(16, b"\0"),
        0x100000000 + code_offset,
        4 * len(instructions),
        code_offset,
        2,
        0,
        0,
        S_ATTR_PURE_INSTRUCTIONS,
        0,
        0,
        0,
    )
    signature_command = struct.pack("<IIII", LC_CODE_SIGNATURE, 16, signature_offset, signature_size)
    prefix = header + segment + section + signature_command
    assert len(prefix) == 200
    prefix += bytes(code_offset - len(prefix))
    prefix += struct.pack(f"<{len(instructions)}I", *instructions)
    assert len(prefix) == signature_offset

    code_directory_length = 80
    code_directory = bytearray()
    code_directory += struct.pack(
        ">9I",
        0xFADE0C02,
        code_directory_length,
        0x20000,
        0,
        60,
        44,
        0,
        1,
        signature_offset,
    )
    code_directory += bytes((20, 1, 0, 12))
    code_directory += struct.pack(">I", 0)
    code_directory += b"fixture\0"
    code_directory += bytes(60 - len(code_directory))
    code_directory += hashlib.sha1(prefix).digest()
    assert len(code_directory) == code_directory_length
    superblob = (
        struct.pack(">III", 0xFADE0CC0, 20 + code_directory_length, 1)
        + struct.pack(">II", 0, 20)
        + code_directory
    )
    assert len(superblob) == signature_size
    return prefix + superblob


class MachOArm64eRewriteTests(unittest.TestCase):
    def test_one_word_pac_lowerings_refresh_signature_and_verify(self):
        source = make_signed_fixture([0xDAC10041, 0xDAC11041, 0xD71F0864, 0xD65F0BFF])
        rewritten, report = rewrite_bytes(source)

        code = struct.unpack_from("<4I", rewritten, 256)
        self.assertEqual(code, (0xD503201F, 0xD503201F, 0xD61F0060, 0xD65F03C0))
        self.assertTrue(report["verified"])
        self.assertEqual(report["recognized_candidates"], 4)
        self.assertTrue(report["signature_refresh"]["verified"])
        self.assertEqual(report["post_rewrite_scan"]["recognized_candidates"], 0)

    def test_instruction_expansion_fails_closed_without_output(self):
        source = make_signed_fixture([0xF8F1F7FA, 0xD503201F, 0xD503201F, 0xD503201F])

        with self.assertRaises(RewriteError) as context:
            rewrite_bytes(source)

        self.assertEqual(context.exception.report["expanded_forms_requiring_relocation"], 1)
        self.assertFalse(context.exception.report["image_modified"])

    def test_unsupported_pac_instruction_fails_closed(self):
        source = make_signed_fixture([0xD69F0BFF, 0xD503201F, 0xD503201F, 0xD503201F])

        with self.assertRaises(RewriteError) as context:
            rewrite_bytes(source)

        self.assertEqual(context.exception.report["rejected_forms"], 1)
        self.assertFalse(context.exception.report["image_modified"])


if __name__ == "__main__":
    unittest.main()
