#!/usr/bin/env python3
"""Stop the nabu QEMU fixture at a kernel symbol and read its arguments.

Minimal GDB remote-protocol client for QEMU's gdbstub (TCG): sets a hardware
breakpoint at SYMBOL (resolved from the kernel's symbol table), continues,
and at the stop prints x0-x7, lr, sp, the C strings x0..x3 point to and the
symbolized frame-pointer chain. Host-side diagnostics only.

Usage: gdb_break.py ESP KERNEL SYMBOL [--xnuprelink DIR] [--timeout S]
"""
import argparse
import os
import socket
import struct
import subprocess
import sys
import time
from bisect import bisect_right
from pathlib import Path


class Gdb:
    def __init__(self, port):
        for _ in range(50):
            try:
                self.s = socket.create_connection(('127.0.0.1', port), timeout=5)
                break
            except OSError:
                time.sleep(0.2)
        self.buf = b''

    def _recv(self, timeout=None):
        self.s.settimeout(timeout)
        while True:
            i = self.buf.find(b'$')
            j = self.buf.find(b'#', i + 1) if i >= 0 else -1
            if i >= 0 and j >= 0 and len(self.buf) >= j + 3:
                body = self.buf[i + 1:j]
                self.buf = self.buf[j + 3:]
                self.s.sendall(b'+')
                return body.decode(errors='replace')
            chunk = self.s.recv(65536)
            if not chunk:
                raise EOFError
            self.buf += chunk

    def cmd(self, body, timeout=10):
        pkt = body.encode()
        self.s.sendall(b'$' + pkt + b'#' + b'%02x' % (sum(pkt) & 0xff))
        return self._recv(timeout)

    def regs(self):
        raw = bytes.fromhex(self.cmd('g'))
        return struct.unpack_from('<33Q', raw)  # x0-x30, sp, pc; cpsr (32-bit) follows

    def mem(self, addr, n):
        reply = self.cmd(f'm{addr:x},{n:x}')
        return bytes.fromhex(reply) if not reply.startswith('E') else b''


def cstr(g, addr):
    if not addr:
        return None
    data = g.mem(addr, 160)
    s = data.split(b'\0')[0]
    return s.decode(errors='replace') if s and all(32 <= c < 127 or c in (9, 10) for c in s) else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('esp', type=Path)
    ap.add_argument('kernel', type=Path)
    ap.add_argument('symbol')
    ap.add_argument('--xnuprelink', default=os.environ.get('XNUPRELINK', 'work/XnuPrelink-source'))
    ap.add_argument('--timeout', type=float, default=180)
    ap.add_argument('--qemu', default=r'C:\Program Files\qemu\qemu-system-aarch64.exe')
    ap.add_argument('--firmware', default=r'C:\Program Files\qemu\share\edk2-aarch64-code.fd')
    ap.add_argument('--port', type=int, default=1234)
    args = ap.parse_args()
    sys.path.insert(0, args.xnuprelink)
    from kc_image import Image
    syms = Image(args.kernel.read_bytes()).symbols()
    addrs = sorted(syms)
    by = {n: a for a, ns in syms.items() for n in ns}
    if args.symbol not in by:
        sys.exit(f'symbol {args.symbol} not found')
    target = by[args.symbol]

    def nm(a):
        i = bisect_right(addrs, a) - 1
        return f'{min(syms[addrs[i]])}+{a - addrs[i]:#x}' if i >= 0 and a >= 0xfffffe0000000000 else hex(a)

    q = subprocess.Popen([args.qemu, '-machine', 'virt,gic-version=3', '-cpu', 'cortex-a76', '-smp', '1', '-m', '2048',
                          '-bios', args.firmware,
                          '-drive', f'if=none,id=esp,format=raw,readonly=on,file=fat:{args.esp.resolve()}',
                          '-device', 'virtio-blk-pci,drive=esp', '-device', 'ramfb', '-device', 'qemu-xhci',
                          '-device', 'usb-kbd', '-nic', 'none', '-display', 'none', '-no-reboot',
                          '-gdb', f'tcp:127.0.0.1:{args.port}', '-S'])
    try:
        g = Gdb(args.port)
        g.cmd('?')
        print('Z1', target and hex(target), g.cmd(f'Z1,{target:x},4'))
        g.s.sendall(b'$c#63')
        try:
            stop = g._recv(args.timeout)
        except socket.timeout:
            print(f'no stop at {args.symbol} within {args.timeout}s')
            return
        r = g.regs()
        x, sp, pc = r[:31], r[31], r[32]
        print('stop', stop, 'pc', nm(pc))
        print('lr ', nm(x[30]))
        for i in range(8):
            s = cstr(g, x[i]) if x[i] >= 0xfffffe0000000000 else None
            print(f'x{i} = {x[i]:#018x}' + (f'   "{s}"' if s else ''))
        stack = g.mem(sp, 96)
        if len(stack) == 96:
            vals = struct.unpack('<12Q', stack)
            print('stack args:', ' '.join(f'{v:#x}' for v in vals))
            for v in vals:
                s = cstr(g, v) if v >= 0xfffffe0000000000 else None
                if s: print(f'   {v:#x} -> "{s[:120]}"')
        fp = x[29]
        print('frames:')
        for _ in range(16):
            if not fp or fp & 7:
                break
            data = g.mem(fp, 16)
            if len(data) < 16:
                break
            fp, lr = struct.unpack('<QQ', data)
            print('   ', nm(lr))
    finally:
        q.kill()


if __name__ == '__main__':
    main()
