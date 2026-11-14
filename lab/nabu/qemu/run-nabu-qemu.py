#!/usr/bin/env python3
"""Run a staged nabu ESP under QEMU virt (cortex-a76, GICv3, ramfb).

Records the UEFI serial log and takes framebuffer screenshots through QMP at
the given times (XNU on NABU has no PL011 console, so its verbose output is
only on the framebuffer). Host-side test only.

Usage: run-nabu-qemu.py ESP_DIR --out DIR [--qemu EXE] [--firmware FD]
                        [--shots 10,30,60] [--cpus 1] [--mem 2048]
"""
import argparse
import json
import socket
import subprocess
import time
from pathlib import Path


def qmp(port):
    s = socket.create_connection(('127.0.0.1', port), timeout=10)
    f = s.makefile('rw')
    f.readline()
    def cmd(name, **arguments):
        f.write(json.dumps({'execute': name, 'arguments': arguments} if arguments else {'execute': name}) + '\n')
        f.flush()
        while True:
            reply = json.loads(f.readline())
            if 'return' in reply or 'error' in reply:
                return reply
    cmd('qmp_capabilities')
    return cmd


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('esp', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--qemu', default=r'C:\Program Files\qemu\qemu-system-aarch64.exe')
    ap.add_argument('--firmware', default=r'C:\Program Files\qemu\share\edk2-aarch64-code.fd')
    ap.add_argument('--shots', default='10,30,60')
    ap.add_argument('--cpus', type=int, default=1)
    ap.add_argument('--mem', type=int, default=2048)
    ap.add_argument('--port', type=int, default=4447)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    serial = args.out / 'serial.log'
    command = [args.qemu, '-machine', 'virt,gic-version=3', '-cpu', 'cortex-a76', '-smp', str(args.cpus),
               '-m', str(args.mem), '-bios', args.firmware,
               '-drive', f'if=none,id=esp,format=raw,readonly=on,file=fat:{args.esp.resolve()}',
               '-device', 'virtio-blk-pci,drive=esp', '-device', 'ramfb',
               '-device', 'qemu-xhci', '-device', 'usb-kbd', '-nic', 'none',
               '-display', 'none', '-no-reboot', '-serial', f'file:{serial}',
               '-qmp', f'tcp:127.0.0.1:{args.port},server=on,wait=off']
    (args.out / 'command.txt').write_text(' '.join(command))
    proc = subprocess.Popen(command)
    start = time.time()
    time.sleep(2)
    cmd = qmp(args.port)
    shots = sorted(int(x) for x in args.shots.split(','))
    taken = []
    for t in shots:
        delay = start + t - time.time()
        if delay > 0:
            time.sleep(delay)
        if proc.poll() is not None:
            break
        ppm = args.out / f'screen-{t:03d}s.ppm'
        reply = cmd('screendump', filename=str(ppm.resolve()))
        if 'return' in reply:
            try:
                from PIL import Image
                png = ppm.with_suffix('.png')
                Image.open(ppm).save(png)
                ppm.unlink()
                taken.append(png.name)
            except Exception as e:  # keep the PPM if PIL is missing
                taken.append(f'{ppm.name} ({e})')
        status = cmd('query-status').get('return', {}).get('status')
        print(f'{t:4d}s status={status} shot={taken[-1] if taken else None}', flush=True)
    if proc.poll() is None:
        cmd('quit')
        proc.wait(timeout=10)
    print('exit code', proc.returncode)
    print('serial tail:')
    print('\n'.join(serial.read_text(errors='replace').splitlines()[-25:]))


if __name__ == '__main__':
    main()
