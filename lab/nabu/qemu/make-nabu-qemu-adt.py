#!/usr/bin/env python3
"""Apple-format device tree that lets the NABU kernel run under QEMU virt.

Host-side test fixture only, never tablet data. It follows UniXNU's
scripts/qemu-entry/make-dt.py (BSD-2-Clause-Patent) and changes what the NABU
kernel matches and reads:
  - root compatible "xiaomi,nabu" (NabuPlatformExpert IONameMatch);
  - cpu compatible "qcom,kryo485" (NabuCPU), QEMU cortex-a76 cores, which like
    the tablet's Kryo 485 implement ARMv8.2 without pointer authentication;
  - /arm-io/gic reg = GICD offset, size, GICR offset, size (pexpert pe_fiq.c),
    relative to the QEMU virt peripheral window at 0x08000000;
  - /arm-io/gic "vtimer-intid" = 27, the QEMU virt virtual timer PPI
    (patch 0011; the tablet keeps its default 19).
One CPU by default: the NABU kernel starts secondaries with PSCI over SMC,
which QEMU virt without EL3 firmware does not provide.

Usage: make-nabu-qemu-adt.py --unixnu PATH --output FILE [--dram-size N] [--owned-memory-size N]
"""
import argparse
import os
import struct
import sys
from pathlib import Path

QEMU_PERIPH_BASE = 0x08000000
QEMU_PERIPH_SIZE = 0x04000000
QEMU_TIMEBASE = 62500000          # QEMU virt generic timer frequency
QEMU_VTIMER_PPI = 27


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--unixnu', type=Path, required=True, help='UniXNU checkout (scripts/unixnu/devicetree.py)')
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--dram-size', type=lambda v: int(v, 0), default=0x80000000)
    ap.add_argument('--owned-memory-size', type=lambda v: int(v, 0), default=0x40000000,
                    help='DarwinBoot window (chosen/darwinboot-memory-size), 256 MiB to 4 GiB in 2 MiB steps')
    args = ap.parse_args()
    if not 0x10000000 <= args.owned_memory_size <= 0x100000000 or args.owned_memory_size % 0x200000:
        ap.error('owned memory must be 256 MiB to 4 GiB, aligned to 2 MiB')
    sys.path.insert(0, str(args.unixnu / 'scripts'))
    from unixnu.devicetree import node, empty_nvram_proxy

    u32 = lambda v: struct.pack('<I', v)
    u64 = lambda v: struct.pack('<Q', v)
    cpu0 = node('cpu0', [('state', b'running\0'), ('reg', u32(0)), ('device_type', b'cpu\0'),
                         ('compatible', b'qcom,kryo485\0'), ('timebase-frequency', u32(QEMU_TIMEBASE)),
                         ('clock-frequency', u32(1000000000))])
    tree = node('device-tree', [('model', b'nabu-qemu-fixture\0'), ('compatible', b'xiaomi,nabu\0')], [
        node('chosen', [('random-seed', os.urandom(256)),
                        ('darwinboot-memory-size', u64(args.owned_memory_size)),
                        ('dram-base', u64(0x40000000)),
                        ('dram-size', u64(args.dram_size)),
                        *empty_nvram_proxy()],
             [node('memory-map'), node('manifest-properties')]),
        node('cpus', children=[cpu0]),
        node('defaults', [('vmm-present', u32(1))]),
        node('options'),
        node('product', [('product-name', b'QEMU virt (nabu fixture)\0'), ('model', b'xiaomi,nabu\0')]),
        node('arm-io', [('device_type', b'qemu-virt\0'),
                        ('ranges', struct.pack('<QQQ', 0, QEMU_PERIPH_BASE, QEMU_PERIPH_SIZE))],
             [node('gic', [('compatible', b'arm,gic-v3\0'),
                           ('reg', struct.pack('<4Q', 0, 0x10000, 0xa0000, 0xf60000)),
                           ('vtimer-intid', u32(QEMU_VTIMER_PPI))])]),
    ])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(tree)
    print(f'nabu QEMU ADT: {len(tree)} bytes -> {args.output}')


if __name__ == '__main__':
    main()
