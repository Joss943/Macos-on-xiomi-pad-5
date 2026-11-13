#!/usr/bin/env python3
"""Download an owner-selected Apple IPSW with HTTP range resume support.

The restore image is written outside the Git repository and is never uploaded.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


CHUNK_SIZE = 8 * 1024 * 1024
REPORT_INTERVAL = 256 * 1024 * 1024


def head(url: str) -> tuple[int, str | None]:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "nabu-macos27-lab/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"unexpected HEAD status: {response.status}")
        return int(response.headers["Content-Length"]), response.headers.get("Accept-Ranges")


def download(url: str, destination: Path) -> int:
    total, ranges = head(url)
    if ranges is None or "bytes" not in ranges.lower():
        raise RuntimeError("Apple CDN did not advertise byte-range support")
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + ".part")

    if destination.exists():
        if destination.stat().st_size != total:
            raise RuntimeError(f"existing destination has wrong size: {destination.stat().st_size} != {total}")
        downloaded = total
    else:
        downloaded = part.stat().st_size if part.exists() else 0
        if downloaded > total:
            raise RuntimeError("partial download is larger than the advertised IPSW")
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "nabu-macos27-lab/1.0", "Range": f"bytes={downloaded}-{total - 1}"},
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            if downloaded and response.status != 206:
                raise RuntimeError(f"resume requested but server returned HTTP {response.status}")
            if not downloaded and response.status not in (200, 206):
                raise RuntimeError(f"unexpected download status: {response.status}")
            content_range = response.headers.get("Content-Range")
            if response.status == 206 and (not content_range or not content_range.startswith(f"bytes {downloaded}-")):
                raise RuntimeError(f"unexpected Content-Range: {content_range!r}")
            mode = "ab" if downloaded else "wb"
            last_report = downloaded
            started = time.monotonic()
            with part.open(mode) as output:
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    if downloaded - last_report >= REPORT_INTERVAL or downloaded == total:
                        elapsed = max(time.monotonic() - started, 0.001)
                        rate = (downloaded - (part.stat().st_size if mode == "ab" else 0)) / elapsed
                        print(f"Downloaded {downloaded:,}/{total:,} bytes ({downloaded * 100 / total:.1f}%), {rate / (1024 * 1024):.1f} MiB/s", file=sys.stderr, flush=True)
                        last_report = downloaded
        if downloaded != total:
            raise RuntimeError(f"short IPSW: {downloaded} bytes, expected {total}; rerun to resume")
        os.replace(part, destination)

    with zipfile.ZipFile(destination) as archive:
        names = set(archive.namelist())
        if "BuildManifest.plist" not in names:
            raise RuntimeError("download is not an IPSW: BuildManifest.plist is missing")
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="official Apple restore IPSW URL")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        size = download(args.url, args.destination)
    except (OSError, urllib.error.URLError, zipfile.BadZipFile, RuntimeError, KeyError) as error:
        parser.error(str(error))
    print(f"Verified IPSW container: {args.destination} ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
