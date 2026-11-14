# Mesures de la Pad 5 nabu

Lecture ADB en date du 13 novembre 2026. Ces commandes n'écrivent aucune partition.

| Propriété | Mesure |
|---|---|
| Modèle / produit | `21051182G` / `nabu_global` |
| Android | 13, `V816.0.6.0.TKXMIXM` |
| Cœurs visibles | 8 |
| `paca` / `pacg` dans `/proc/cpuinfo` | absents des 8 lignes `Features` |
| Bootloader | verrouillé (`ro.boot.flash.locked=1`) |
| Écriture ou flash | aucun |

Les indicateurs absents sont l'interface Linux exposée par Android; le contrôle n'a pas lu directement les registres d'identification du processeur. Arm situe l'extension PAC à partir d'Armv8.3-A, tandis que Cortex-A76 est documenté comme Armv8.2-A. Le matériel et son firmware doivent être vérifiés avant de transformer ce constat en preuve d'impossibilité matérielle absolue.

La copie locale du stockage partagé est séparée de ce dépôt : `outputs/Pad5/sdcard`. Elle compte 9 201 fichiers et 4 482 781 497 octets; les 9 201 entrées de `outputs/Pad5/SHA256SUMS.txt` ont été recalculées et correspondent toutes. Le dossier MIUI est inclus. La sauvegarde MIUI signale des applications non prises en charge; aucun dump brut des partitions n'a été effectué. Ni la copie ni ses sommes ne sont poussées sur GitHub.

Le démarrage natif macOS reste non réalisé. Les sources disponibles pour nabu portent le profil iPadOS 17.7, pas macOS Sonoma, et indiquent encore le Wi-Fi absent. La mesure matérielle n'est pas une validation d'installation.

## Reproduction des lectures

```powershell
adb shell getprop ro.product.device
adb shell getprop ro.product.model
adb shell getprop ro.build.version.release
adb shell getprop ro.build.version.incremental
adb shell getprop ro.boot.flash.locked
adb shell cat /proc/cpuinfo
```

## Références

- [Arm Cortex-A76 TRM](https://developer.arm.com/documentation/100798/latest/)
- [Armv8.x extensions](https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/Learn%20the%20Architecture/Understanding%20the%20Armv8.x%20extensions.pdf)
- [Apple arm64e/PAC requirement for kexts](https://developer.apple.com/documentation/kernel/implementing_drivers_system_extensions_and_kexts)
- [UniXNU-nabu current port and status](https://github.com/zzweiqing/UniXNU-nabu)
