import importlib.util
import struct
import sys
import tempfile
import unittest
import lzma
from pathlib import Path


MODULE = Path(__file__).with_name("pbzx_extract.py")
SPEC = importlib.util.spec_from_file_location("pbzx_extract", MODULE)
PBZX = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PBZX
SPEC.loader.exec_module(PBZX)


def chunk(payload, compress=True):
    encoded = lzma.compress(payload) if compress else payload
    return struct.pack(">QQ", len(payload), len(encoded)) + encoded


class PbzxExtractTests(unittest.TestCase):
    def test_decodes_xz_and_raw_chunks(self):
        chunks = [b"first xz block " * 16, b"raw block" * 4]
        stream = b"pbzx" + struct.pack(">Q", 1024) + chunk(chunks[0]) + chunk(chunks[1], False)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Payload"
            output = root / "cpio"
            source.write_bytes(stream)
            report = PBZX.decode(source, output)
            self.assertEqual(output.read_bytes(), b"".join(chunks))
            self.assertEqual(report["blocks"], 2)

    def test_rejects_truncated_chunk_without_leaving_output(self):
        stream = b"pbzx" + struct.pack(">Q", 1024) + struct.pack(">QQ", 100, 40) + b"short"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Payload"
            output = root / "cpio"
            source.write_bytes(stream)
            with self.assertRaisesRegex(PBZX.PbzxError, "truncated"):
                PBZX.decode(source, output)
            self.assertFalse(output.exists())

    def test_refuses_to_overwrite_existing_output(self):
        stream = b"pbzx" + struct.pack(">Q", 16) + chunk(b"data", False)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Payload"
            output = root / "existing"
            source.write_bytes(stream)
            output.write_bytes(b"keep")
            with self.assertRaisesRegex(PBZX.PbzxError, "refusing to overwrite"):
                PBZX.decode(source, output)
            self.assertEqual(output.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
