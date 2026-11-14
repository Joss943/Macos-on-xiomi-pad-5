#!/usr/bin/env bash
# Build NabuNT36523HID.kext with Xcode on macOS. Usage: build.sh <output-dir> [arch]
# The kext is built against the SDK `xcrun --show-sdk-path` reports; the script
# prints that SDK so a result is never mistaken for a macOS 27 build.
set -euo pipefail
out="$1"
arch="${2:-arm64e}"
here="$(cd "$(dirname "$0")" && pwd)"
sdk="$(xcrun --sdk macosx --show-sdk-path)"
kernel_headers="$sdk/System/Library/Frameworks/Kernel.framework/Headers"
echo "SDK: $(xcrun --sdk macosx --show-sdk-version) ($sdk), arch $arch"
test -f "$kernel_headers/IOKit/hid/IOHIDDevice.h"
obj="$out/obj-$arch"
bundle="$out/NabuNT36523HID.kext"
mkdir -p "$obj" "$bundle/Contents/MacOS"
common=(-arch "$arch" -mkernel -nostdinc -isysroot "$sdk" -I "$kernel_headers" -DKERNEL
	-Wall -Wextra -Werror -O2 -fno-common)
for source in geni_spi nt36523 nabu_touch_hid; do
	xcrun clang -std=c11 "${common[@]}" -c "$here/../$source.c" -o "$obj/$source.o"
done
xcrun clang++ -std=c++17 -fapple-kext -fno-rtti -fno-exceptions "${common[@]}" -Wno-unused-parameter \
	-c "$here/NabuNT36523HID.cpp" -o "$obj/NabuNT36523HID.o"
xcrun clang++ -arch "$arch" -mkernel -nostdlib -isysroot "$sdk" -Xlinker -kext -Xlinker -export_dynamic \
	"$obj"/*.o -lkmodc++ -lkmod -lcc_kext -o "$bundle/Contents/MacOS/NabuNT36523HID"
cp "$here/Info.plist" "$bundle/Contents/Info.plist"
plutil -lint "$bundle/Contents/Info.plist"
file "$bundle/Contents/MacOS/NabuNT36523HID"
