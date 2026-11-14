import gzip
import hashlib
import importlib.util
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


MODULE = Path(__file__).with_name("xar_extract.py")
SPEC = importlib.util.spec_from_file_location("xar_extract", MODULE)
XAR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = XAR
SPEC.loader.exec_module(XAR)


def package_for(payload, name, encoding="application/octet-stream", compression="zlib"):
    if encoding == "application/x-gzip":
        archived = gzip.compress(payload) if compression == "gzip" else zlib.compress(payload)
    else:
        archived = payload
    archived_sha = hashlib.sha1(archived).hexdigest()
    extracted_sha = hashlib.sha1(payload).hexdigest()
    toc = (
        f'<?xml version="1.0"?><xar><toc><checksum style="sha1"><offset>0</offset><size>20</size></checksum>'
        f'<file id="1"><data>'
        f'<length>{len(archived)}</length><offset>20</offset><size>{len(payload)}</size>'
        f'<encoding style="{encoding}"/>'
        f'<archived-checksum style="sha1">{archived_sha}</archived-checksum>'
        f'<extracted-checksum style="sha1">{extracted_sha}</extracted-checksum>'
        f'</data><type>file</type><name>{name}</name></file></toc></xar>'
    ).encode()
    compressed_toc = zlib.compress(toc)
    header = struct.pack(">IHHQQI", XAR.XAR_MAGIC, XAR.XAR_HEADER_SIZE, 1,
                         len(compressed_toc), len(toc), 1)
    return header + compressed_toc + hashlib.sha1(compressed_toc).digest() + archived


class XarExtractTests(unittest.TestCase):
    def test_lists_and_extracts_raw_member(self):
        payload = b"sonoma shared support marker"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "input.pkg"
            package.write_bytes(package_for(payload, "SharedSupport.dmg"))
            archive = XAR.XarArchive(package)
            self.assertEqual(archive.list_members()[0]["name"], "SharedSupport.dmg")
            output = root / "SharedSupport.dmg"
            report = archive.extract("SharedSupport.dmg", output)
            self.assertEqual(output.read_bytes(), payload)
            self.assertEqual(report["extracted_bytes"], len(payload))

    def test_extracts_deflate_member_marked_as_gzip_and_checks_sha1(self):
        payload = b"compressed package metadata" * 128
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "input.pkg"
            package.write_bytes(package_for(payload, "PackageInfo", "application/x-gzip"))
            output = root / "PackageInfo"
            XAR.XarArchive(package).extract("PackageInfo", output)
            self.assertEqual(output.read_bytes(), payload)

    def test_accepts_gzip_header_in_encoded_member(self):
        payload = b"gzip metadata" * 32
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "input.pkg"
            package.write_bytes(package_for(payload, "PackageInfo", "application/x-gzip", "gzip"))
            output = root / "PackageInfo"
            XAR.XarArchive(package).extract("PackageInfo", output)
            self.assertEqual(output.read_bytes(), payload)

    def test_rejects_path_traversal(self):
        package = package_for(b"x", "../escape")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.pkg"
            path.write_bytes(package)
            with self.assertRaises(XAR.XarError):
                XAR.XarArchive(path)

    def test_rejects_corrupt_toc_checksum(self):
        package = bytearray(package_for(b"data", "item"))
        _, header_size, _, compressed_size, _, _ = struct.unpack(">IHHQQI", package[:28])
        package[header_size + compressed_size] ^= 0x01
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.pkg"
            path.write_bytes(package)
            with self.assertRaisesRegex(XAR.XarError, "TOC checksum mismatch"):
                XAR.XarArchive(path)

    def test_removes_partial_output_after_member_checksum_failure(self):
        package = bytearray(package_for(b"member data", "item"))
        package[-1] ^= 0x01
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "input.pkg"
            output = root / "out"
            path.write_bytes(package)
            with self.assertRaisesRegex(XAR.XarError, "archived SHA-1 mismatch"):
                XAR.XarArchive(path).extract("item", output)
            self.assertFalse(output.exists())

    def test_preserves_preexisting_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "input.pkg"
            output = root / "out"
            package.write_bytes(package_for(b"payload", "item"))
            output.write_bytes(b"keep")
            with self.assertRaisesRegex(XAR.XarError, "refusing to overwrite"):
                XAR.XarArchive(package).extract("item", output)
            self.assertEqual(output.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
