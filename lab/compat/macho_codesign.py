#!/usr/bin/env python3
"""Inspect and refresh embedded CodeDirectories in a thin 64-bit Mach-O.

This is the signature layer for a future arm64e compatibility rewriter. It
supports multiple CodeDirectories (for example SHA-1 and SHA-256), recomputes
their code-page hashes, can remove an Apple CMS wrapper that cannot survive a
local code change, and verifies the result. It does not translate instructions,
update bundle resource manifests or trust caches, rebuild APFS, or make an OS
image bootable. Callers must write to a new output and test the whole boot path.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct


MH_MAGIC_64 = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
LC_CODE_SIGNATURE = 0x1D
CSMAGIC_EMBEDDED_SIGNATURE = 0xFADE0CC0
CSMAGIC_CODEDIRECTORY = 0xFADE0C02
CSMAGIC_BLOBWRAPPER = 0xFADE0B01
CSSLOT_CODEDIRECTORY = 0
CSSLOT_SIGNATURESLOT = 0x10000
CS_ADHOC = 0x2


class SignatureError(ValueError):
    """The Mach-O signature is unsupported, malformed or unsafe to rewrite."""


@dataclass(frozen=True)
class SignatureLocation:
    command_offset: int
    data_offset: int
    data_size: int


@dataclass(frozen=True)
class Blob:
    slot: int
    data: bytes


@dataclass(frozen=True)
class CodeDirectory:
    slot: int
    offset: int
    length: int
    version: int
    flags: int
    hash_offset: int
    identifier_offset: int
    special_slots: int
    code_slots: int
    code_limit: int
    hash_size: int
    hash_type: int
    platform: int
    page_exponent: int
    page_size: int
    hash_name: str


def locate_signature(data: bytes) -> SignatureLocation:
    """Locate the unique LC_CODE_SIGNATURE in a thin little-endian ARM64 Mach-O."""
    if len(data) < 32:
        raise SignatureError("truncated Mach-O header")
    magic, cputype = struct.unpack_from("<II", data)
    if magic != MH_MAGIC_64 or cputype != CPU_TYPE_ARM64:
        raise SignatureError("expected a thin little-endian 64-bit ARM64 Mach-O")
    ncmds, sizeofcmds = struct.unpack_from("<II", data, 16)
    end = 32 + sizeofcmds
    if end > len(data):
        raise SignatureError("load commands extend past the file")
    cursor = 32
    found: SignatureLocation | None = None
    for _ in range(ncmds):
        if cursor + 8 > end:
            raise SignatureError("truncated load command")
        command, size = struct.unpack_from("<II", data, cursor)
        if size < 8 or cursor + size > end:
            raise SignatureError("invalid load-command size")
        if command == LC_CODE_SIGNATURE:
            if found is not None or size != 16:
                raise SignatureError("duplicate or malformed LC_CODE_SIGNATURE")
            data_offset, data_size = struct.unpack_from("<II", data, cursor + 8)
            if data_offset < end or data_size < 12 or data_offset + data_size > len(data):
                raise SignatureError("code-signature range is outside the Mach-O")
            found = SignatureLocation(cursor, data_offset, data_size)
        cursor += size
    if cursor != end:
        raise SignatureError("load-command sizes do not match sizeofcmds")
    if found is None:
        raise SignatureError("LC_CODE_SIGNATURE is missing")
    return found


def parse_superblob(signature: bytes) -> tuple[int, list[Blob]]:
    """Return the declared SuperBlob length and its validated child blobs."""
    if len(signature) < 12:
        raise SignatureError("truncated embedded signature SuperBlob")
    magic, length, count = struct.unpack_from(">III", signature)
    if magic != CSMAGIC_EMBEDDED_SIGNATURE or not 12 <= length <= len(signature):
        raise SignatureError("invalid embedded signature SuperBlob")
    table_end = 12 + count * 8
    if table_end > length:
        raise SignatureError("SuperBlob index table exceeds its declared length")
    children: list[Blob] = []
    intervals: list[tuple[int, int]] = []
    seen_slots: set[int] = set()
    for index in range(count):
        slot, offset = struct.unpack_from(">II", signature, 12 + 8 * index)
        if slot in seen_slots:
            raise SignatureError(f"duplicate SuperBlob slot {slot:#x}")
        seen_slots.add(slot)
        # Apple-produced SuperBlobs can contain unaligned child offsets (the
        # Sonoma installer uses offsets 0xa75, 0xad1 and 0x1af6). The index
        # table is authoritative; only bounds and overlap are safety checks.
        if offset < table_end or offset + 8 > length:
            raise SignatureError(f"invalid child offset for SuperBlob slot {slot:#x}")
        child_magic, child_length = struct.unpack_from(">II", signature, offset)
        if child_length < 8 or offset + child_length > length:
            raise SignatureError(f"invalid child length for SuperBlob slot {slot:#x}")
        interval = (offset, offset + child_length)
        if any(interval[0] < prior_end and prior_start < interval[1] for prior_start, prior_end in intervals):
            raise SignatureError("overlapping SuperBlob child blobs")
        intervals.append(interval)
        children.append(Blob(slot, signature[offset:offset + child_length]))
    return length, children


def _hash_info(hash_type: int, hash_size: int) -> str:
    supported = {1: ("sha1", 20), 2: ("sha256", 32), 3: ("sha256", 20), 4: ("sha384", 48)}
    if hash_type not in supported:
        raise SignatureError(f"unsupported CodeDirectory hash type {hash_type}")
    name, expected_size = supported[hash_type]
    if hash_size != expected_size:
        raise SignatureError(f"hash type {hash_type} requires {expected_size} bytes, got {hash_size}")
    return name


def parse_code_directory(blob: bytes, slot: int, offset: int = 0) -> CodeDirectory:
    if len(blob) < 40:
        raise SignatureError("truncated CodeDirectory header")
    magic, length, version, flags, hash_offset, ident_offset, special_slots, code_slots, code_limit32 = \
        struct.unpack_from(">9I", blob)
    if magic != CSMAGIC_CODEDIRECTORY or length < 40 or length > len(blob):
        raise SignatureError("invalid CodeDirectory blob")
    hash_size, hash_type, platform, page_exponent = struct.unpack_from(">4B", blob, 36)
    header_size = 40
    scatter_offset = 0
    if version >= 0x20100:
        if length < 48:
            raise SignatureError("CodeDirectory version requires scatterOffset field")
        scatter_offset = struct.unpack_from(">I", blob, 44)[0]
        header_size = 48
    if version >= 0x20200:
        if length < 52:
            raise SignatureError("CodeDirectory version requires teamOffset field")
        header_size = 52
    if version >= 0x20300:
        if length < 64:
            raise SignatureError("CodeDirectory version requires 64-bit code limit fields")
        code_limit64 = struct.unpack_from(">Q", blob, 56)[0]
        if code_limit32 == 0xFFFFFFFF:
            code_limit = code_limit64
        else:
            if code_limit64 not in (0, code_limit32):
                raise SignatureError("CodeDirectory 32-bit and 64-bit code limits disagree")
            code_limit = code_limit32
        header_size = 64
    else:
        code_limit = code_limit32
    if version >= 0x20400:
        if length < 88:
            raise SignatureError("CodeDirectory version requires executable segment fields")
        header_size = 88
    if scatter_offset:
        raise SignatureError("scattered CodeDirectory page hashes are unsupported")
    if ident_offset < header_size or ident_offset >= length or b"\0" not in blob[ident_offset:length]:
        raise SignatureError("invalid CodeDirectory identifier offset")
    hash_name = _hash_info(hash_type, hash_size)
    if page_exponent > 30:
        raise SignatureError("unreasonable CodeDirectory page-size exponent")
    page_size = (1 << page_exponent) if page_exponent else max(1, code_limit)
    expected_slots = (code_limit + page_size - 1) // page_size if code_limit else 0
    if code_slots != expected_slots:
        raise SignatureError(f"CodeDirectory has {code_slots} code slots, expected {expected_slots}")
    if hash_offset < header_size + special_slots * hash_size:
        raise SignatureError("CodeDirectory special hashes overlap its header")
    if hash_offset + code_slots * hash_size > length:
        raise SignatureError("CodeDirectory code hashes exceed its declared length")
    return CodeDirectory(
        slot=slot, offset=offset, length=length, version=version, flags=flags,
        hash_offset=hash_offset, identifier_offset=ident_offset,
        special_slots=special_slots, code_slots=code_slots, code_limit=code_limit,
        hash_size=hash_size, hash_type=hash_type, platform=platform,
        page_exponent=page_exponent, page_size=page_size, hash_name=hash_name,
    )


def _digest(name: str, payload: bytes) -> bytes:
    return hashlib.new(name, payload).digest()


def _directory_hash(blob: bytes, directory: CodeDirectory) -> str:
    return _digest(directory.hash_name, blob[:directory.length])[:20].hex()


def _verify_directory_hashes(data: bytes, signature: bytes, children: list[Blob], location: SignatureLocation) -> None:
    directories = [(child, parse_code_directory(child.data, child.slot)) for child in children
                   if len(child.data) >= 4 and struct.unpack_from(">I", child.data)[0] == CSMAGIC_CODEDIRECTORY]
    if not directories:
        raise SignatureError("SuperBlob contains no CodeDirectory")
    for child, directory in directories:
        if directory.code_limit > location.data_offset:
            raise SignatureError("CodeDirectory hashes extend into the code signature")
        source = data[:directory.code_limit]
        for index in range(directory.code_slots):
            start = index * directory.page_size
            actual = _digest(directory.hash_name, source[start:min(start + directory.page_size, directory.code_limit)])
            actual = actual[:directory.hash_size]
            at = directory.hash_offset + index * directory.hash_size
            expected = child.data[at:at + directory.hash_size]
            if actual != expected:
                raise SignatureError(f"CodeDirectory slot {directory.slot:#x} page {index} hash mismatch")


def _build_superblob(children: list[Blob]) -> bytes:
    table_end = 12 + 8 * len(children)
    cursor = (table_end + 3) & ~3
    offsets: list[int] = []
    for child in children:
        if len(child.data) < 8:
            raise SignatureError("cannot serialize truncated child blob")
        offsets.append(cursor)
        cursor = (cursor + len(child.data) + 3) & ~3
    result = bytearray(cursor)
    struct.pack_into(">III", result, 0, CSMAGIC_EMBEDDED_SIGNATURE, cursor, len(children))
    for index, (child, offset) in enumerate(zip(children, offsets)):
        struct.pack_into(">II", result, 12 + 8 * index, child.slot, offset)
        result[offset:offset + len(child.data)] = child.data
    return bytes(result)


def resign_signature(
    original: bytes,
    *,
    platform: int | None = None,
    add_flags: int = CS_ADHOC,
    clear_flags: int = 0,
    strip_cms: bool = True,
) -> tuple[bytes, dict[str, object]]:
    """Refresh every CodeDirectory and return a new Mach-O plus an audit report.

    The code bytes are left untouched. `add_flags` defaults to CS_ADHOC because
    no Apple private signing key is available after a local binary rewrite.
    A CMS signature is removed by default; leaving a now-invalid CMS wrapper in
    a modified image is refused.
    """
    if platform is not None and not 0 <= platform <= 0xFF:
        raise SignatureError("platform identifier must fit one byte")
    if add_flags & ~0xFFFFFFFF or clear_flags & ~0xFFFFFFFF:
        raise SignatureError("CodeDirectory flags must fit uint32")
    result = bytearray(original)
    location = locate_signature(original)
    raw_signature = original[location.data_offset:location.data_offset + location.data_size]
    superblob_length, children = parse_superblob(raw_signature)
    cms = [child for child in children if child.slot == CSSLOT_SIGNATURESLOT]
    if cms and not strip_cms:
        raise SignatureError("cannot preserve a CMS signature after changing CodeDirectories")
    directories = [child for child in children if len(child.data) >= 4 and
                   struct.unpack_from(">I", child.data)[0] == CSMAGIC_CODEDIRECTORY]
    if not any(child.slot == CSSLOT_CODEDIRECTORY for child in directories):
        raise SignatureError("primary CodeDirectory slot is missing")
    updated_children: list[Blob] = []
    report_rows: list[dict[str, object]] = []
    for child in children:
        if child.slot == CSSLOT_SIGNATURESLOT and strip_cms:
            if struct.unpack_from(">I", child.data)[0] != CSMAGIC_BLOBWRAPPER:
                raise SignatureError("signature slot is not a CMS BlobWrapper")
            continue
        if child not in directories:
            updated_children.append(child)
            continue
        directory = parse_code_directory(child.data, child.slot)
        if directory.code_limit > location.data_offset:
            raise SignatureError("CodeDirectory hashes extend into the code signature")
        if directory.hash_offset + directory.code_slots * directory.hash_size > directory.length:
            raise SignatureError("CodeDirectory hashes exceed the blob")
        updated = bytearray(child.data)
        flags = (directory.flags | add_flags) & ~clear_flags
        struct.pack_into(">I", updated, 12, flags)
        if platform is not None:
            updated[38] = platform
        for index in range(directory.code_slots):
            start = index * directory.page_size
            end = min(start + directory.page_size, directory.code_limit)
            digest = _digest(directory.hash_name, original[start:end])[:directory.hash_size]
            at = directory.hash_offset + index * directory.hash_size
            updated[at:at + directory.hash_size] = digest
        updated_bytes = bytes(updated[:directory.length])
        updated_children.append(Blob(child.slot, updated_bytes))
        report_rows.append({
            "slot": f"0x{child.slot:x}",
            "hash_type": directory.hash_type,
            "hash_name": directory.hash_name,
            "code_slots": directory.code_slots,
            "old_cdhash": _directory_hash(child.data, directory),
            "new_cdhash": _directory_hash(updated_bytes, directory),
            "flags": f"0x{flags:08x}",
            "platform": updated_bytes[38],
        })
    rebuilt = _build_superblob(updated_children)
    if len(rebuilt) > location.data_size:
        raise SignatureError("updated SuperBlob does not fit in the original signature range")
    result[location.data_offset:location.data_offset + location.data_size] = b"\0" * location.data_size
    result[location.data_offset:location.data_offset + len(rebuilt)] = rebuilt
    # Keep LC_CODE_SIGNATURE.datasize unchanged: the load command itself is in
    # the CodeDirectory code range, so shrinking it would invalidate its own
    # page hash. The existing range already contains padding after the
    # SuperBlob, and the rebuilt blob must fit within that reserved range.
    output = bytes(result)
    new_location = locate_signature(output)
    new_raw = output[new_location.data_offset:new_location.data_offset + new_location.data_size]
    _, new_children = parse_superblob(new_raw)
    _verify_directory_hashes(output, new_raw, new_children, new_location)
    report: dict[str, object] = {
        "schema": "macho-codedirectory-refresh-v1",
        "input_sha256": hashlib.sha256(original).hexdigest(),
        "output_sha256": hashlib.sha256(output).hexdigest(),
        "signature_bytes_before": superblob_length,
        "signature_bytes_after": len(rebuilt),
        "cms_removed": bool(cms and strip_cms),
        "code_bytes_modified": False,
        "code_directories": report_rows,
        "verified": True,
        "bootable_image": False,
    }
    return output, report

