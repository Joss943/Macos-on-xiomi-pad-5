# Test du noyau nabu sous QEMU (hôte uniquement)

Machine `virt`, GICv3, cœur **cortex-a76** (ARMv8.2 sans PAC, comme le Kryo 485), écran ramfb.
Chaîne : UEFI (edk2) → `UniXNU.efi` → `DarwinBoot.efi` (patch `darwinboot/0001`) → XNU.

| Fichier | Rôle |
|---|---|
| `make-nabu-qemu-adt.py` | Device tree Apple de test (`xiaomi,nabu`, `qcom,kryo485`, `cluster-type`, `/arm-io/gic`, `vtimer-intid` 27) |
| `run-nabu-qemu.py` | Lance QEMU, journal série UEFI, captures d'écran via QMP |
| `tools/backtrace.py` | Au panic : registres, chaîne des pointeurs de cadre, chaînes pointées |
| `tools/readsyms.py` | Lit des variables globales du noyau dans la VM |

Les binaires EFI viennent du workflow `uefi-build.yml`. Le kernelcache macOS contient des kexts Apple : il reste sur la machine locale et n'est jamais versionné.

## Journal des essais (14 novembre 2026)

| # | Noyau | Arrêt | Cause | Correction |
|---|---|---|---|---|
| 1 | run 26 | 1re instruction de `arm_init` (instruction indéfinie) | PA et VA congruents modulo 2 Mio seulement ; `start.s` 16 Kio arrondit à 32 Mio → +16 Mio | `darwinboot/0001` |
| 2 | run 26 | `Unexpected cluster type 0 @processor.c:1998` | pas de `cluster-type` dans le device tree | ADT de test |
| 3 | run 26, 28 | `arm_vm_init.c:1642` physmap | `ARM_LARGE_MEMORY` sans PPL : aucune marge d'alignement | patch XNU `0012` |
