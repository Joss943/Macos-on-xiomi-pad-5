#!/usr/bin/env python3
"""Run an EL0 arm64e probe on every nabu CPU using temporary ADB storage.

Only a tiny executable in /data/local/tmp is written; it is removed in a
finally block. No partition, boot setting, or firmware command is issued.
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import tempfile
import uuid
from pathlib import Path

from build_arm64e_probe import PROBES, make_elf


def run(command: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, timeout=timeout, check=False)


def output_text(result: subprocess.CompletedProcess) -> str:
    return result.stdout.decode("utf-8", "replace").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=sorted(PROBES))
    parser.add_argument("--adb", default="adb", help="path to adb executable")
    parser.add_argument("--serial", help="ADB serial; auto-selected only when exactly one device is connected")
    args = parser.parse_args()

    devices = run([args.adb, "devices", "-l"])
    if devices.returncode:
        parser.error(f"adb devices failed: {output_text(devices)}")
    connected = []
    for line in devices.stdout.decode("utf-8", "replace").splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "device":
            connected.append(fields[0])
    serial = args.serial
    if serial is None:
        if len(connected) != 1:
            parser.error(f"expected exactly one authorized ADB device, found {len(connected)}")
        serial = connected[0]
    if serial not in connected:
        parser.error("the selected ADB device is not connected and authorized")

    def adb_read(*argv: str) -> str:
        result = run([args.adb, "-s", serial, *argv])
        if result.returncode:
            raise RuntimeError(f"adb {' '.join(argv)} failed: {output_text(result)}")
        return output_text(result)

    def adb_read_optional(*argv: str) -> str | None:
        result = run([args.adb, "-s", serial, *argv])
        return output_text(result) if result.returncode == 0 else None

    model = adb_read("shell", "getprop", "ro.product.model")
    product = adb_read("shell", "getprop", "ro.product.device")
    soc = adb_read("shell", "getprop", "ro.soc.model")
    if model != "21051182G" or product != "nabu":
        parser.error(f"refusing non-target hardware model={model!r}, product={product!r}")
    cpuinfo = adb_read("shell", "cat", "/proc/cpuinfo")
    cpu_ids = []
    for line in cpuinfo.splitlines():
        if line.startswith("processor") and ":" in line:
            cpu_ids.append(int(line.split(":", 1)[1].strip()))
    if not cpu_ids:
        parser.error("no processor entries found in /proc/cpuinfo")
    midr = {
        cpu: adb_read_optional(
            "shell", "cat", f"/sys/devices/system/cpu/cpu{cpu}/regs/identification/midr_el1"
        )
        for cpu in cpu_ids
    }

    remote = f"/data/local/tmp/nabu-arm64e-{uuid.uuid4().hex}"
    temporary_file_removed = False
    with tempfile.TemporaryDirectory(prefix="nabu-arm64e-probe-") as temp_dir:
        local = Path(temp_dir) / "probe"
        local.write_bytes(make_elf(PROBES[args.kind]["words"]))
        os.chmod(local, 0o755)
        pushed = run([args.adb, "-s", serial, "push", str(local), remote])
        if pushed.returncode:
            parser.error(f"temporary ADB push failed: {output_text(pushed)}")
        chmod = run([args.adb, "-s", serial, "shell", "chmod", "700", remote])
        if chmod.returncode:
            run([args.adb, "-s", serial, "shell", "rm", "-f", remote])
            parser.error(f"could not mark temporary probe executable: {output_text(chmod)}")

        cpu_results = []
        try:
            for cpu in cpu_ids:
                mask = format(1 << cpu, "x")
                result = run([
                    args.adb,
                    "-s",
                    serial,
                    "exec-out",
                    "/system/bin/toybox",
                    "taskset",
                    mask,
                    remote,
                ])
                row = {
                    "cpu": cpu,
                    "midr_el1": midr[cpu],
                    "process_exit_code": result.returncode,
                    "stderr": result.stderr.decode("utf-8", "replace").strip(),
                    "stdout_hex": result.stdout.hex(),
                }
                if args.kind == "pac" and len(result.stdout) == 16:
                    restored, signed = struct.unpack("<QQ", result.stdout)
                    row.update({
                        "restored_pointer": f"0x{restored:016x}",
                        "signed_pointer": f"0x{signed:016x}",
                        "auth_round_trip": restored == 0x1234,
                        "signature_changed_pointer": signed != 0x1234,
                        "pac_passed": restored == 0x1234 and signed != 0x1234,
                    })
                elif args.kind == "isar1" and len(result.stdout) == 8:
                    value = struct.unpack("<Q", result.stdout)[0]
                    apa = (value >> 4) & 0xF
                    api = (value >> 8) & 0xF
                    gpa = (value >> 24) & 0xF
                    gpi = (value >> 28) & 0xF
                    row.update({
                        "id_aa64isar1_el1": f"0x{value:016x}",
                        "apa": apa,
                        "api": api,
                        "gpa": gpa,
                        "gpi": gpi,
                        "address_pac": apa != 0 or api != 0,
                        "generic_pac": gpa != 0 or gpi != 0,
                    })
                elif args.kind == "isar2" and len(result.stdout) == 8:
                    value = struct.unpack("<Q", result.stdout)[0]
                    apa3 = (value >> 4) & 0xF
                    gpa3 = (value >> 8) & 0xF
                    row.update({
                        "id_aa64isar2_el1": f"0x{value:016x}",
                        "apa3": apa3,
                        "gpa3": gpa3,
                        "address_pac": apa3 != 0,
                        "generic_pac": gpa3 != 0,
                    })
                elif args.kind == "pac" and b"illegal instruction" in (result.stdout + result.stderr).lower():
                    row["result"] = "sigill_illegal_instruction"
                else:
                    row["result"] = "no_probe_output_or_wrong_size"
                cpu_results.append(row)
        finally:
            removed = run([args.adb, "-s", serial, "shell", "rm", "-f", remote])
            absent = run([args.adb, "-s", serial, "shell", "test", "!", "-e", remote])
            temporary_file_removed = removed.returncode == 0 and absent.returncode == 0

    print(json.dumps({
        "schema": "nabu-arm64e-el0-probe-result-v1",
        "kind": args.kind,
        "hardware_tested": True,
        "device": {"model": model, "product": product, "soc": soc},
        "cpu_count": len(cpu_ids),
        "cpus": cpu_results,
        "temporary_device_file_removed": temporary_file_removed,
        "partitions_or_boot_state_modified": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
