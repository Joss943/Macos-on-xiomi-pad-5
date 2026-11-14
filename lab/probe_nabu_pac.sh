#!/bin/sh
# Read-only probe for Linux/Android arm64 CPU capability reporting.
# It does not change boot, storage, partitions, or firmware.
set -eu

cpu=unknown
seen=0
missing=0

while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
        processor*)
            cpu=${line#*:}
            cpu=$(printf '%s' "$cpu" | tr -d '[:space:]')
            [ -n "$cpu" ] || cpu=unknown
            ;;
        Features*)
            features=${line#*:}
            paca=no
            pacg=no
            case " $features " in *" paca "*) paca=yes ;; esac
            case " $features " in *" pacg "*) pacg=yes ;; esac
            printf 'CPU %s: paca=%s pacg=%s\n' "$cpu" "$paca" "$pacg"
            seen=$((seen + 1))
            if [ "$paca" != yes ] || [ "$pacg" != yes ]; then
                missing=$((missing + 1))
            fi
            ;;
    esac
done < /proc/cpuinfo

if [ "$seen" -eq 0 ]; then
    echo 'Résultat indéterminé : aucune ligne Features trouvée dans /proc/cpuinfo.' >&2
    exit 2
fi

if [ "$missing" -eq 0 ]; then
    printf 'Résultat : PACA et PACG annoncés sur les %s lignes CPU lues.\n' "$seen"
    echo 'Ceci est un prérequis à vérifier, pas une validation de démarrage macOS.'
    exit 0
fi

printf 'Résultat : PACA et/ou PACG non annoncés sur %s ligne(s) CPU.\n' "$missing"
echo 'Linux peut masquer une capacité; recouper avec les registres CPU avant toute conclusion.'
exit 1
