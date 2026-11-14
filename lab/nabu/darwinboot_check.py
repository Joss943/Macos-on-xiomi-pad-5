#!/usr/bin/env python3
"""Offline replica of DarwinBoot's kernel acceptance checks.

Mirrors ParseKernelHeader() and ParseKernel() of UniXNU/DarwinBoot
(DarwinBootPkg/Driver/DarwinBoot.c, revision 3c75734) so a kernel or
MH_FILESET kernel collection can be checked on the host before any QEMU or
device run. Every rejection names the rule that failed. Passing these checks
only means the loader would accept the file; it says nothing about boot.

Usage: darwinboot_check.py KERNEL [--json REPORT]
"""
import argparse
import json
import struct
import sys

SIZE_2MB = 2 << 20
WINDOW_SIZE = 256 << 20
MAX_SEGMENTS = 64
MAX_UINT64 = (1 << 64) - 1
EFI_PAGE_MASK = 0xfff


class Reject(Exception):
    pass


def u32(d, o):
    return struct.unpack_from('<I', d, o)[0]


def u64(d, o):
    return struct.unpack_from('<Q', d, o)[0]


def parse_header(d, size, header):
    if (header > size or size - header < 32 or u32(d, header) != 0xfeedfacf
            or u32(d, header + 4) != 0x100000c
            or (u32(d, header + 8) & 0xffffff) not in (0, 2)
            or (u32(d, header + 12) != 2 and (header != 0 or u32(d, header + 12) != 12))):
        raise Reject('unsupported header (magic, cputype, subtype or filetype)')
    if u32(d, header + 20) > size - header - 32:
        raise Reject('sizeofcmds exceeds the file')
    count = u32(d, header + 16)
    end = header + 32 + u32(d, header + 20)
    off = header + 32
    segs, entry = [], None
    for _ in range(count):
        if end - off < 8:
            raise Reject('truncated load command')
        cmd, length = u32(d, off), u32(d, off + 4)
        if length < 8 or length & 7 or length > end - off:
            raise Reject(f'bad load command length {length} at {off:#x}')
        if cmd == 0x19:
            if length < 72 or u32(d, off + 64) > (length - 72) // 80 or len(segs) == MAX_SEGMENTS:
                raise Reject('bad LC_SEGMENT_64 or more than 64 mapped segments')
            if u64(d, off + 32) != 0:
                name = d[off + 8:off + 24].rstrip(b'\0').decode(errors='replace')
                s = dict(name=name, address=u64(d, off + 24), size=u64(d, off + 32),
                         fileoff=u64(d, off + 40), filesize=u64(d, off + 48), prot=u32(d, off + 60))
                if (s['size'] > WINDOW_SIZE or s['address'] > MAX_UINT64 - s['size']
                        or s['filesize'] > s['size'] or s['fileoff'] > size
                        or s['filesize'] > size - s['fileoff']):
                    raise Reject(f"segment {name} out of bounds")
                segs.append(s)
        elif cmd == 5:
            if entry is not None or length != 288 or u32(d, off + 8) != 6 or u32(d, off + 12) != 68:
                raise Reject('bad or duplicate LC_UNIXTHREAD')
            entry = u64(d, off + 272)
        off += length
    if off != end or entry is None or not segs:
        raise Reject('no entry point or no mapped segment')
    base = min(s['address'] for s in segs)
    top = max(s['address'] + s['size'] for s in segs)
    executable = any(s['address'] <= entry < s['address'] + s['filesize'] and s['prot'] & 4 for s in segs)
    for i, a in enumerate(segs):
        for b in segs[:i]:
            if a['address'] < b['address'] + b['size'] and b['address'] < a['address'] + a['size']:
                raise Reject(f"segments {b['name']} and {a['name']} overlap")
    if not executable:
        raise Reject(f'entry {entry:#x} is not in an executable, file-backed segment')
    if entry & 3 or base & EFI_PAGE_MASK or base > MAX_UINT64 - WINDOW_SIZE:
        raise Reject('misaligned entry or base')
    if top - base > WINDOW_SIZE - SIZE_2MB:
        raise Reject(f'span {top - base:#x} exceeds the {WINDOW_SIZE - SIZE_2MB:#x} window')
    return dict(segments=segs, entry=entry, base=base, end=top)


def parse_kernel(d):
    size = len(d)
    kernel = parse_header(d, size, 0)
    kernel['filetype'] = u32(d, 12)
    if kernel['filetype'] != 12:
        return kernel
    off, end, found, entries = 32, 32 + u32(d, 20), False, 0
    while off < end:
        length = u32(d, off + 4)
        if u32(d, off) == 0x80000035:
            entries += 1
            if length < 40:
                raise Reject('short LC_FILESET_ENTRY')
            name_at = u32(d, off + 24)
            if name_at < 32 or name_at >= length:
                raise Reject('bad fileset entry name offset')
            stop = d.find(b'\0', off + name_at, off + length)
            if stop < 0:
                raise Reject('unterminated fileset entry name')
            name = d[off + name_at:stop].decode(errors='replace')
            header = u64(d, off + 16)
            if header > size or size - header < 32 or header & 7:
                raise Reject(f'{name}: bad header offset')
            va = u64(d, off + 8)
            if not any(p['fileoff'] <= header and header - p['fileoff'] <= p['filesize']
                       and 32 <= p['filesize'] - (header - p['fileoff'])
                       and va == p['address'] + header - p['fileoff'] for p in kernel['segments']):
                raise Reject(f'{name}: header not loaded at its advertised address')
            if name == 'com.apple.kernel':
                if (found or u32(d, header + 12) != 2 or u32(d, header + 8) != u32(d, 8)
                        or not u32(d, header + 24) & 0x80000000):
                    raise Reject('com.apple.kernel: not MH_EXECUTE, subtype mismatch or no MH_DYLIB_IN_CACHE')
                found = True
                member = parse_header(d, size, header)
                if member['entry'] != kernel['entry']:
                    raise Reject('com.apple.kernel entry differs from the collection entry')
                for c in member['segments']:
                    if not any(p['address'] <= c['address'] and c['address'] - p['address'] <= p['size']
                               and c['size'] <= p['size'] - (c['address'] - p['address'])
                               and not c['prot'] & ~p['prot']
                               and (c['filesize'] == 0 or (
                                   c['address'] - p['address'] <= p['filesize']
                                   and c['filesize'] <= p['filesize'] - (c['address'] - p['address'])
                                   and c['fileoff'] == p['fileoff'] + c['address'] - p['address']))
                               for p in kernel['segments']):
                        raise Reject(f"com.apple.kernel segment {c['name']} not covered by a root segment")
        off += length
    if not found:
        raise Reject('no com.apple.kernel entry')
    kernel['fileset_entries'] = entries
    return kernel


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('kernel')
    ap.add_argument('--json')
    args = ap.parse_args()
    d = open(args.kernel, 'rb').read()
    try:
        k = parse_kernel(d)
        rep = {'accepted': True, 'filetype': k['filetype'], 'entry': hex(k['entry']), 'base': hex(k['base']),
               'span': hex(k['end'] - k['base']), 'window_limit': hex(WINDOW_SIZE - SIZE_2MB),
               'mapped_segments': len(k['segments']), 'fileset_entries': k.get('fileset_entries')}
    except Reject as e:
        rep = {'accepted': False, 'reason': str(e)}
    print(json.dumps(rep, indent=2))
    if args.json:
        json.dump(rep, open(args.json, 'w'), indent=2)
    return 0 if rep['accepted'] else 1


if __name__ == '__main__':
    sys.exit(main())
