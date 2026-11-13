#!/usr/bin/env python3
"""Read selected files from an Apple IPSW over HTTP ranges, without its full download."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import urllib.request
import zipfile
from collections import OrderedDict
from pathlib import Path


BLOCK_SIZE = 4 * 1024 * 1024
MAX_CACHED_BLOCKS = 8


class HTTPRangeReader:
    """Minimal seekable ZIP reader backed by verified HTTP byte ranges."""

    def __init__(self, url: str):
        self.url = url
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "nabu-macos27-lab/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            self.length = int(response.headers["Content-Length"])
            if "bytes" not in response.headers.get("Accept-Ranges", "").lower():
                raise RuntimeError("IPSW server does not advertise HTTP byte ranges")
        self.position = 0
        self.blocks: OrderedDict[int, bytes] = OrderedDict()

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            position = offset
        elif whence == 1:
            position = self.position + offset
        elif whence == 2:
            position = self.length + offset
        else:
            raise ValueError(f"invalid seek whence: {whence}")
        if position < 0:
            raise ValueError("negative seek position")
        self.position = position
        return position

    def _block(self, start: int) -> bytes:
        cached = self.blocks.get(start)
        if cached is not None:
            self.blocks.move_to_end(start)
            return cached
        end = min(start + BLOCK_SIZE, self.length) - 1
        request = urllib.request.Request(
            self.url,
            headers={
                "User-Agent": "nabu-macos27-lab/1.0",
                "Range": f"bytes={start}-{end}",
            },
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            content_range = response.headers.get("Content-Range", "")
            match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
            if response.status != 206 or not match:
                raise RuntimeError(f"range request was not honored: HTTP {response.status}, {content_range!r}")
            actual_start, actual_end, actual_total = map(int, match.groups())
            if actual_start != start or actual_end != end or actual_total != self.length:
                raise RuntimeError(f"unexpected Content-Range: {content_range!r}")
            payload = response.read()
        if len(payload) != end - start + 1:
            raise RuntimeError(f"short range response at {start}: {len(payload)} bytes")
        self.blocks[start] = payload
        self.blocks.move_to_end(start)
        while len(self.blocks) > MAX_CACHED_BLOCKS:
            self.blocks.popitem(last=False)
        return payload

    def read(self, size: int = -1) -> bytes:
        if self.position >= self.length:
            return b""
        if size < 0:
            size = self.length - self.position
        size = min(size, self.length - self.position)
        remaining = size
        chunks = []
        while remaining:
            block_start = (self.position // BLOCK_SIZE) * BLOCK_SIZE
            block = self._block(block_start)
            in_block = self.position - block_start
            amount = min(remaining, len(block) - in_block)
            chunks.append(block[in_block:in_block + amount])
            self.position += amount
            remaining -= amount
        return b"".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="official Apple IPSW URL")
    parser.add_argument("--list-kernel", action="store_true", help="list kernelcache and build-manifest members")
    parser.add_argument("--member", action="append", default=[], help="exact ZIP member to extract (repeatable)")
    parser.add_argument("--output-dir", type=Path, default=Path("ipsw-members"))
    args = parser.parse_args()
    if not args.list_kernel and not args.member:
        parser.error("choose --list-kernel or at least one --member")

    source = HTTPRangeReader(args.url)
    with zipfile.ZipFile(source) as archive:
        if args.list_kernel:
            matches = [info for info in archive.infolist() if "kernelcache" in info.filename.lower() or "buildmanifest" in info.filename.lower()]
            print(json.dumps([
                {"name": info.filename, "compressed_size": info.compress_size, "size": info.file_size}
                for info in matches
            ], indent=2))
        if args.member:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            infos = {info.filename: info for info in archive.infolist()}
            for name in args.member:
                info = infos.get(name)
                if info is None:
                    parser.error(f"IPSW member not found: {name}")
                destination = args.output_dir / Path(name).name
                with archive.open(info) as compressed, destination.open("xb") as output:
                    shutil.copyfileobj(compressed, output, length=1024 * 1024)
                print(json.dumps({"member": name, "bytes": destination.stat().st_size, "output": str(destination)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise SystemExit(f"ipsw_range: {error}")
