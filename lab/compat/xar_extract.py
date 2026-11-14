#!/usr/bin/env python3
"""List or extract a single file from an Apple XAR package.

The reader handles XAR version 1 with a zlib-compressed TOC, raw members, and
gzip/zlib encoded members. Stored lengths and extracted sizes follow the XAR
format definition; available TOC and member checksums are verified. Output
files are created exclusively and input packages are never modified.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass
from pathlib import Path


XAR_MAGIC = 0x78617221
XAR_HEADER_SIZE = 28
MAX_TOC_COMPRESSED = 64 * 1024 * 1024
MAX_TOC_UNCOMPRESSED = 256 * 1024 * 1024
COPY_CHUNK = 4 * 1024 * 1024


class XarError(ValueError):
    pass


@dataclass(frozen=True)
class Member:
    name: str
    offset: int
    archived_size: int
    extracted_size: int
    encoding: str
    archived_sha1: str | None
    extracted_sha1: str | None


class XarArchive:
    def __init__(self, path: Path):
        self.path = path.resolve(strict=True)
        if not self.path.is_file():
            raise XarError(f"not a file: {self.path}")
        self.file_size = self.path.stat().st_size
        self.heap_offset, self.header_checksum = self._read_header_and_toc()
        self.members = self._read_members()

    def _read_header_and_toc(self) -> tuple[int, int]:
        with self.path.open("rb") as stream:
            header = stream.read(XAR_HEADER_SIZE)
            if len(header) != XAR_HEADER_SIZE:
                raise XarError("truncated XAR header")
            magic, header_size, version, compressed_size, uncompressed_size, checksum = struct.unpack(
                ">IHHQQI", header
            )
            if magic != XAR_MAGIC or header_size < XAR_HEADER_SIZE or version != 1:
                raise XarError("unsupported XAR header")
            if header_size > 4096:
                raise XarError("XAR header exceeds safety limit")
            if compressed_size > MAX_TOC_COMPRESSED or uncompressed_size > MAX_TOC_UNCOMPRESSED:
                raise XarError("XAR TOC exceeds safety limits")
            extra = stream.read(header_size - XAR_HEADER_SIZE)
            if len(extra) != header_size - XAR_HEADER_SIZE:
                raise XarError("truncated extended XAR header")
            if checksum == 0:
                self._toc_checksum_name = None
            elif checksum == 1:
                self._toc_checksum_name = "sha1"
            elif checksum == 2:
                self._toc_checksum_name = "md5"
            elif checksum == 3:
                raw_name = extra.split(b"\0", 1)[0]
                try:
                    self._toc_checksum_name = raw_name.decode("ascii")
                    hashlib.new(self._toc_checksum_name)
                except (UnicodeDecodeError, ValueError) as error:
                    raise XarError("unsupported XAR TOC checksum algorithm") from error
                if not self._toc_checksum_name:
                    raise XarError("missing extended XAR checksum algorithm")
            else:
                raise XarError(f"unsupported XAR TOC checksum identifier: {checksum}")
            heap_offset = header_size + compressed_size
            if heap_offset > self.file_size:
                raise XarError("XAR TOC leaves package bounds")
            compressed_toc = stream.read(compressed_size)
            if len(compressed_toc) != compressed_size:
                raise XarError("truncated compressed XAR TOC")
            try:
                toc = zlib.decompress(compressed_toc)
            except zlib.error as error:
                raise XarError(f"invalid compressed XAR TOC: {error}") from error
            if len(toc) != uncompressed_size:
                raise XarError(f"XAR TOC length mismatch: expected {uncompressed_size}, got {len(toc)}")
            self._toc_xml = toc
            self._compressed_toc = compressed_toc
            return heap_offset, checksum

    def _read_members(self) -> list[Member]:
        try:
            root = ET.fromstring(self._toc_xml)
        except ET.ParseError as error:
            raise XarError(f"invalid XAR TOC XML: {error}") from error
        if root.tag != "xar":
            raise XarError("XAR TOC has no xar root element")
        toc = root.find("toc")
        if toc is None:
            raise XarError("XAR TOC has no toc element")
        self._verify_toc_checksum(toc)
        result = []
        for item in toc.findall("file"):
            name = item.findtext("name")
            data = item.find("data")
            if not name or data is None:
                continue
            if name.startswith(("/", "\\")) or ".." in Path(name).parts:
                raise XarError(f"unsafe package member name: {name!r}")
            offset = self._integer(data, "offset")
            # XAR's <length> is bytes stored in the heap; <size> is bytes after
            # decoding. Apple installer packages use this distinction for
            # PackageInfo and Bom members.
            archived_size = self._integer(data, "length")
            extracted_size = self._integer(data, "size")
            if offset + archived_size > self.file_size - self.heap_offset:
                raise XarError(f"member leaves package bounds: {name}")
            encoding = data.find("encoding")
            style = encoding.get("style") if encoding is not None else "application/octet-stream"
            if style not in ("application/octet-stream", "application/x-gzip"):
                continue
            result.append(Member(
                name=name,
                offset=offset,
                archived_size=archived_size,
                extracted_size=extracted_size,
                encoding=style,
                archived_sha1=self._checksum(data, "archived-checksum"),
                extracted_sha1=self._checksum(data, "extracted-checksum"),
            ))
        return result

    def _verify_toc_checksum(self, toc: ET.Element) -> None:
        checksum = toc.find("checksum")
        if self._toc_checksum_name is None:
            if checksum is not None:
                raise XarError("TOC contains a checksum but header disables checksums")
            return
        if checksum is None:
            raise XarError("XAR header requires a TOC checksum but none is present")
        style = checksum.get("style")
        if style != self._toc_checksum_name:
            raise XarError("XAR header and TOC checksum algorithms disagree")
        offset = self._integer(checksum, "offset")
        size = self._integer(checksum, "size")
        try:
            digest = hashlib.new(style, self._compressed_toc).digest()
        except ValueError as error:
            raise XarError(f"unsupported TOC checksum: {style}") from error
        if size != len(digest) or offset + size > self.file_size - self.heap_offset:
            raise XarError("invalid XAR TOC checksum bounds")
        with self.path.open("rb") as stream:
            stream.seek(self.heap_offset + offset)
            actual = stream.read(size)
        if actual != digest:
            raise XarError("XAR compressed TOC checksum mismatch")

    @staticmethod
    def _integer(parent: ET.Element, key: str) -> int:
        raw = parent.findtext(key)
        try:
            value = int(raw) if raw is not None else -1
        except ValueError as error:
            raise XarError(f"invalid integer for {key}: {raw!r}") from error
        if value < 0:
            raise XarError(f"missing or invalid integer for {key}")
        return value

    @staticmethod
    def _checksum(parent: ET.Element, name: str) -> str | None:
        element = parent.find(name)
        if element is None:
            return None
        if element.get("style") != "sha1":
            return None
        value = (element.text or "").strip().lower()
        if len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
            raise XarError(f"invalid SHA-1 in {name}")
        return value

    def list_members(self) -> list[dict]:
        return [
            {
                "name": member.name,
                "archived_size": member.archived_size,
                "extracted_size": member.extracted_size,
                "encoding": member.encoding,
            }
            for member in self.members
        ]

    def extract(self, name: str, destination: Path) -> dict:
        matches = [member for member in self.members if member.name == name]
        if len(matches) != 1:
            raise XarError(f"expected one member named {name!r}, found {len(matches)}")
        member = matches[0]
        if member.encoding != "application/octet-stream" and (
            member.archived_size > 64 * 1024 * 1024 or member.extracted_size > 256 * 1024 * 1024
        ):
            raise XarError(f"compressed member exceeds extraction limit: {name}")
        destination = destination.resolve()
        if destination.exists():
            raise XarError(f"refusing to overwrite {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)

        archived_digest = hashlib.sha1()
        extracted_digest = hashlib.sha1()
        archived_count = 0
        extracted_count = 0
        heap_at = self.heap_offset + member.offset
        created = False

        try:
            with self.path.open("rb") as source, destination.open("xb") as output:
                created = True
                source.seek(heap_at)
                if member.encoding == "application/octet-stream":
                    while archived_count < member.archived_size:
                        block = source.read(min(COPY_CHUNK, member.archived_size - archived_count))
                        if not block:
                            raise XarError(f"truncated member data: {name}")
                        archived_count += len(block)
                        extracted_count += len(block)
                        if extracted_count > member.extracted_size:
                            raise XarError(f"raw member exceeds declared size: {name}")
                        archived_digest.update(block)
                        extracted_digest.update(block)
                        output.write(block)
                else:
                    source.seek(heap_at)
                    first = source.read(min(COPY_CHUNK, member.archived_size))
                    if len(first) != min(COPY_CHUNK, member.archived_size):
                        raise XarError(f"truncated compressed member data: {name}")
                    # Apple XAR files commonly use zlib framing under this
                    # MIME label; accept a real gzip stream as well.
                    source.seek(heap_at)
                    if first.startswith(b"\x1f\x8b"):
                        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
                    else:
                        decompressor = zlib.decompressobj()
                    remaining = member.archived_size
                    while remaining:
                        block = source.read(min(COPY_CHUNK, remaining))
                        if not block:
                            raise XarError(f"truncated compressed member data: {name}")
                        remaining -= len(block)
                        archived_count += len(block)
                        archived_digest.update(block)
                        pending = block
                        while pending:
                            decoded = decompressor.decompress(
                                pending, member.extracted_size - extracted_count + 1
                            )
                            pending = decompressor.unconsumed_tail
                            if decoded:
                                extracted_count += len(decoded)
                                if extracted_count > member.extracted_size:
                                    raise XarError(f"compressed member exceeds declared size: {name}")
                                extracted_digest.update(decoded)
                                output.write(decoded)
                            if pending and not decoded:
                                raise XarError(f"compressed member decoder made no progress: {name}")
                    tail = decompressor.flush()
                    if tail:
                        extracted_count += len(tail)
                        if extracted_count > member.extracted_size:
                            raise XarError(f"compressed member exceeds declared size: {name}")
                        extracted_digest.update(tail)
                        output.write(tail)
                    if not decompressor.eof or decompressor.unused_data:
                        raise XarError(f"invalid compressed stream boundary: {name}")

            if archived_count != member.archived_size or extracted_count != member.extracted_size:
                raise XarError(
                    f"member length mismatch for {name}: archived {archived_count}/{member.archived_size}, "
                    f"extracted {extracted_count}/{member.extracted_size}"
                )
            if member.archived_sha1 and archived_digest.hexdigest() != member.archived_sha1:
                raise XarError(f"archived SHA-1 mismatch for {name}")
            if member.extracted_sha1 and extracted_digest.hexdigest() != member.extracted_sha1:
                raise XarError(f"extracted SHA-1 mismatch for {name}")
        except Exception:
            if created:
                try:
                    destination.unlink()
                except FileNotFoundError:
                    pass
            raise
        return {
            "name": name,
            "output": str(destination),
            "archived_bytes": archived_count,
            "extracted_bytes": extracted_count,
            "archived_sha1": archived_digest.hexdigest(),
            "extracted_sha1": extracted_digest.hexdigest(),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--list", action="store_true", help="list supported package members")
    parser.add_argument("--extract", metavar="MEMBER", help="extract one member by exact name")
    parser.add_argument("--output", type=Path, help="new output path for --extract")
    args = parser.parse_args()
    if bool(args.extract) != bool(args.output):
        parser.error("--extract and --output must be used together")
    if not args.list and not args.extract:
        parser.error("choose --list or --extract")
    try:
        archive = XarArchive(args.package)
        if args.list:
            print(json_dumps(archive.list_members()))
        if args.extract:
            print(json_dumps(archive.extract(args.extract, args.output)))
        return 0
    except (OSError, XarError, struct.error) as error:
        print(f"xar_extract: {error}", file=sys.stderr)
        return 2


def json_dumps(value) -> str:
    import json
    return json.dumps(value, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
