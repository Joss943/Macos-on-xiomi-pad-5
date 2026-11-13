#!/bin/bash
# get_recovery.sh <board-id> <mlb> <os_type default|latest> <outdir>
# Télécharge BaseSystem.dmg + chunklist depuis les serveurs Internet Recovery d'Apple
# (même protocole que macrecovery.py d'OpenCorePkg), sans Mac.
# Board IDs : catalina Mac-00BE6ED71E35EB86 | big-sur Mac-2BD1B31983FE1663 | monterey Mac-B809C3757DA9BB8D (latest)
#             ventura Mac-4B682C642B45593E (latest) | sonoma Mac-827FAC58A8FDFA22 | sequoia Mac-7BA5B2D9E42DDD94 | tahoe Mac-CFF7D910A743CAAF (latest)
# Derrière un proxy HTTP CONNECT (labo), ajouter : -p -x "$HTTPS_PROXY" aux appels curl.
set -euo pipefail
BID=$1; MLB=${2:-00000000000000000}; OS=${3:-default}; OUT=${4:-recovery}; mkdir -p "$OUT"
P=(-sS -A "InternetRecovery/1.0")
SESS=$(curl "${P[@]}" -D - -o /dev/null http://osrecovery.apple.com/ | grep -i '^set-cookie' | sed 's/.*\(session=[^;]*\).*/\1/')
rid() { openssl rand -hex "$1" | tr a-f A-F; }
printf 'cid=%s\nsn=%s\nbid=%s\nk=%s\nfg=%s\nos=%s' "$(rid 8)" "$MLB" "$BID" "$(rid 32)" "$(rid 32)" "$OS" > "$OUT/post.txt"
curl "${P[@]}" -o "$OUT/info.txt" -H "Cookie: $SESS" -H "Content-Type: text/plain" --data-binary @"$OUT/post.txt" http://osrecovery.apple.com/InstallationPayload/RecoveryImage
grep '^AP: ' "$OUT/info.txt" || { cat "$OUT/info.txt"; exit 1; }
AU=$(grep '^AU: ' "$OUT/info.txt" | cut -d' ' -f2); AT=$(grep '^AT: ' "$OUT/info.txt" | cut -d' ' -f2-)
CU=$(grep '^CU: ' "$OUT/info.txt" | cut -d' ' -f2); CT=$(grep '^CT: ' "$OUT/info.txt" | cut -d' ' -f2-)
curl "${P[@]}" -H "Cookie: AssetToken=$CT" -o "$OUT/BaseSystem.chunklist" "$CU"
curl "${P[@]}" -H "Cookie: AssetToken=$AT" -C - --retry 10 -o "$OUT/BaseSystem.dmg" -w "downloaded %{size_download} bytes in %{time_total}s\n" "$AU"
# Vérification des blocs SHA-256 contre la chunklist signée Apple
python3 - "$OUT" <<'EOF'
import struct, hashlib, sys
out = sys.argv[1]
hdr = struct.Struct('<4sIBBBxQQQ'); ch = struct.Struct('<I32s')
data = open(f'{out}/BaseSystem.chunklist','rb').read()
magic, hsize, ver, cmeth, smeth, count, coff, soff = hdr.unpack_from(data); ok = 0
with open(f'{out}/BaseSystem.dmg','rb') as d:
    for i in range(count):
        size, sha = ch.unpack_from(data, coff + i*ch.size)
        ok += hashlib.sha256(d.read(size)).digest() == sha
print(f'chunklist {ok}/{count} OK'); sys.exit(0 if ok == count else 1)
EOF
