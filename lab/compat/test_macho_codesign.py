import hashlib
import importlib.util
import struct
import sys
import unittest
from pathlib import Path


MODULE = Path(__file__).with_name("macho_codesign.py")
SPEC = importlib.util.spec_from_file_location("macho_codesign", MODULE)
MACHO_CODESIGN = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MACHO_CODESIGN
SPEC.loader.exec_module(MACHO_CODESIGN)


def _code_directory(code: bytes, *, slot: int, hash_type: int, hash_name: str, hash_size: int) -> bytes:
    identifier = b"test.nabu\0"
    code_limit = 256
    page_exponent = 8
    code_slots = 1
    hash_offset = 88 + len(identifier) + 3 * hash_size
    length = hash_offset + code_slots * hash_size
    blob = bytearray(length)
    struct.pack_into(">9I", blob, 0,
                     MACHO_CODESIGN.CSMAGIC_CODEDIRECTORY, length, 0x20400,
                     0x2000, hash_offset, 88, 3, code_slots, code_limit)
    struct.pack_into(">4B", blob, 36, hash_size, hash_type, 15, page_exponent)
    # The v0x20400 header is 88 bytes. Scatter, team, codeLimit64 and the
    # executable-segment fields are zero for this small synthetic fixture.
    blob[88:88 + len(identifier)] = identifier
    digest = hashlib.new(hash_name, code[:code_limit]).digest()[:hash_size]
    blob[hash_offset:hash_offset + hash_size] = digest
    return bytes(blob)


def _unaligned_superblob(children: list[tuple[int, bytes]]) -> bytes:
    table_end = 12 + len(children) * 8
    offsets = []
    cursor = table_end
    for _, child in children:
        offsets.append(cursor)
        cursor += len(child)
    result = bytearray(cursor)
    struct.pack_into(">III", result, 0,
                     MACHO_CODESIGN.CSMAGIC_EMBEDDED_SIGNATURE, cursor, len(children))
    for index, ((slot, child), offset) in enumerate(zip(children, offsets)):
        struct.pack_into(">II", result, 12 + index * 8, slot, offset)
        result[offset:offset + len(child)] = child
    return bytes(result)


def _signed_macho() -> bytes:
    signature_offset = 256
    signature_size = 2048
    code = bytearray(signature_offset)
    struct.pack_into("<IIII", code, 0, MACHO_CODESIGN.MH_MAGIC_64,
                     MACHO_CODESIGN.CPU_TYPE_ARM64, 0, 0)
    struct.pack_into("<IIII", code, 16, 1, 16, 0, 0)
    struct.pack_into("<IIII", code, 32, MACHO_CODESIGN.LC_CODE_SIGNATURE,
                     16, signature_offset, signature_size)
    primary = _code_directory(bytes(code), slot=0, hash_type=1,
                              hash_name="sha1", hash_size=20)
    alternate = _code_directory(bytes(code), slot=0x1000, hash_type=2,
                                hash_name="sha256", hash_size=32)
    resources = struct.pack(">II", 0xFADE0C01, 12) + b"res!"
    cms = struct.pack(">II", MACHO_CODESIGN.CSMAGIC_BLOBWRAPPER, 12) + b"cms!"
    signature = _unaligned_superblob([
        (0, primary), (2, resources), (0x1000, alternate),
        (MACHO_CODESIGN.CSSLOT_SIGNATURESLOT, cms),
    ])
    if len(signature) > signature_size:
        raise AssertionError("synthetic signature does not fit its reserved range")
    return bytes(code) + signature + bytes(signature_size - len(signature))


class MachoCodeSignatureTests(unittest.TestCase):
    def test_refreshes_multiple_directories_and_strips_cms_from_unaligned_superblob(self):
        original = _signed_macho()
        original_location = MACHO_CODESIGN.locate_signature(original)
        _, original_children = MACHO_CODESIGN.parse_superblob(
            original[original_location.data_offset:]
        )
        self.assertTrue(any(child.slot == 2 for child in original_children))

        rewritten, report = MACHO_CODESIGN.resign_signature(original, platform=0)

        self.assertTrue(report["verified"])
        self.assertTrue(report["cms_removed"])
        self.assertEqual(original[:256], rewritten[:256])
        new_location = MACHO_CODESIGN.locate_signature(rewritten)
        self.assertEqual(original_location.data_size, new_location.data_size)
        _, children = MACHO_CODESIGN.parse_superblob(
            rewritten[new_location.data_offset:new_location.data_offset + new_location.data_size]
        )
        self.assertEqual({0, 2, 0x1000}, {child.slot for child in children})

        for child in children:
            if child.slot not in (0, 0x1000):
                continue
            directory = MACHO_CODESIGN.parse_code_directory(child.data, child.slot)
            self.assertEqual(0, directory.platform)
            self.assertTrue(directory.flags & MACHO_CODESIGN.CS_ADHOC)
            expected = hashlib.new(directory.hash_name, rewritten[:directory.code_limit]).digest()
            actual = child.data[directory.hash_offset:directory.hash_offset + directory.hash_size]
            self.assertEqual(expected[:directory.hash_size], actual)

    def test_preserves_unsupported_signature_when_cms_stripping_is_disabled(self):
        with self.assertRaisesRegex(MACHO_CODESIGN.SignatureError, "cannot preserve a CMS"):
            MACHO_CODESIGN.resign_signature(_signed_macho(), strip_cms=False)


if __name__ == "__main__":
    unittest.main()

