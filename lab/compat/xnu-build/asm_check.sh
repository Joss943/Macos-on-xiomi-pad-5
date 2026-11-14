#!/usr/bin/env bash
# Assemble XNU arm64 .s files for NABU on Linux (clang-18 + llvm-mc) to catch
# system-register and immediate errors before a 15-minute CI build.
# Generated headers (assym.s, option headers) are stubbed empty, so errors on
# assym constants are noise: only system-register, logical-immediate and
# "requires" (missing CPU feature) errors are reported.
# Usage: asm_check.sh <patched-xnu-tree> [file.s ...]
set -u
xnu=$(cd "$1" && pwd); shift
files=("$@"); [ ${#files[@]} -eq 0 ] && files=(start locore cswitch machine_routines_asm pinst caches_asm)
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
mkdir -p "$work/inc"; : > "$work/inc/assym.s"; echo '#define MACH_ASSERT 1' > "$work/inc/mach_assert.h"
pp() {
  clang-18 --target=arm64-apple-macos13 -march=armv8.2-a+crypto -E -x assembler-with-cpp \
    -DKERNEL -DKERNEL_PRIVATE -DMACH_KERNEL_PRIVATE -DXNU_KERNEL_PRIVATE -DPRIVATE \
    -DARM64_BOARD_CONFIG_NABU -D__arm64__ -DDEVELOPMENT=1 -DXNU_TARGET_OS_OSX=1 \
    -DCONFIG_PMAP_PPL=1 -DCONFIG_SCHED_CLUTCH=1 -DCONFIG_SCHED_TIMESHARE_CORE=1 \
    -I"$work/inc" -Iosfmk -Ipexpert -IEXTERNAL_HEADERS -Ibsd -Ilibkern -Iosfmk/arm64 "$1" -o "$2"
}
status=0
cd "$xnu"
for f in "${files[@]}"; do
  src=osfmk/arm64/${f%.s}.s; out=$work/${f%.s}.i
  for _ in $(seq 1 40); do
    err=$(pp "$src" "$out" 2>&1 | grep -m1 "file not found") || true
    [ -z "$err" ] && break
    h=$(sed -nE "s/.*'([^']+)' file not found.*/\1/p" <<<"$err")
    mkdir -p "$work/inc/$(dirname "$h")"; : > "$work/inc/$h"
  done
  found=$(llvm-mc -triple=arm64-apple-macos13 -mattr=+v8.2a,+crypto,+lse,+rcpc,+fp16,+dotprod \
      -filetype=obj "$out" -o /dev/null 2>&1 | grep -A1 "system register\|logical immediate\|requires" \
      | grep -v '^--' | paste - - | sed -E 's/^[^:]*:[0-9]+:[0-9]+: //' | sort -u)
  if [ -n "$found" ]; then status=1; sed "s|^|$f: |" <<<"$found"; else echo "$f: clean"; fi
done
exit $status
