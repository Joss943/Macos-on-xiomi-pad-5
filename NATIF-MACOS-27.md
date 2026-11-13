# macOS 27.3 sur Xiaomi Pad 5 (nabu / SM8150)

La cible demandée est **macOS 27.3, build 26C5035r**. Le profil public UniXNU pour macOS 27.3 cible `Mac17,11` et compile XNU en **arm64e**. Il exige le Pointer Authentication matériel (PAC) sur chaque cœur. Le dépôt UniXNU indique que les appareils sans PAC restent sur les profils arm64, jusqu'à iPadOS 17 pour cette génération. Références : [profil macOS](https://unixnu.com/porting/macos), [prérequis arm64e](https://unixnu.com/porting/arm64e).

## Mesure réelle sur la tablette — 13 novembre 2026

La Pad 5 était connectée en ADB. La collecte ci-dessous n'a lu que les propriétés Android, `/proc/cpuinfo` et les fichiers d'identification CPU déjà exposés en lecture seule par Linux. Elle n'a écrit aucune partition.

| Champ | Résultat observé |
|---|---|
| Modèle / produit | `21051182G` / `nabu_global` (`nabu`) |
| SoC | `SM8150` |
| Android | `V816.0.6.0.TKXMIXM` |
| Cœurs CPU | 8 |
| `paca` et `pacg` dans les lignes `Features` | absents sur les 8 cœurs |
| `ID_AA64ISAR1_EL1`, lu directement à EL0 sur chaque cœur | `0x0000000000100001` ; APA/API/GPA/GPI = 0 |
| `ID_AA64ISAR2_EL1`, lu directement à EL0 sur chaque cœur | `0x0000000000000000` ; APA3/GPA3 = 0 |
| Instructions `PACIA` + `AUTIA`, processus épinglé sur chaque cœur | `Illegal instruction` sur CPU 0–7 |
| `MIDR_EL1` exposé par sysfs | `0x51df805e` sur CPU 0–3 ; `0x51df804e` sur CPU 4–7 |
| Bootloader | verrouillé (`ro.boot.flash.locked=1`) |
| Écriture ou flash | aucun |

Les registres d'identification ont été lus directement par de petits exécutables ARM64 générés localement puis supprimés de `/data/local/tmp`. Le test `PACIA` a été lancé séparément sur chaque cœur avec l'affinité CPU de Toybox. Le contrôle clé côté matériel a échoué : les champs PAC sont nuls et l'instruction piège sur les huit cœurs. L'écriture des clés PAC à EL1 n'a pas été testée ; les exigences arm64e de UniXNU ne sont donc pas satisfaites par l'état mesuré. Résultats bruts sans numéro de série : [`lab/results/nabu-macos27-pac.json`](lab/results/nabu-macos27-pac.json).

Reproduire la lecture depuis un PC équipé d'ADB :

```powershell
./lab/probe_nabu_macos27.ps1 -AdbPath adb -OutputPath ./lab/results/nabu-macos27-pac.json
```

## État d'avancement et blocages

* **Aucun port macOS 27.3 nabu prêt à construire ou à installer n'est actuellement présent dans ce dépôt.** Le profil UniXNU macOS réclame aussi l'IPSW `UniversalMac_27.3_26C5035r_Restore.ipsw`, son kernelcache et ses trust caches, ainsi qu'un build sur macOS avec Xcode et une intégration de pilotes adaptée à la carte.
* Le dépôt public nabu référencé par UniXNU cible iPadOS 17.7, pas macOS 27.3. Le profil macOS 27.3 n'est pas un simple changement de version : il sélectionne arm64e, des interfaces Darwin 26 et un kernelcache Mac17,11.
* Le bootloader de cette tablette est encore verrouillé. Aucun binaire de démarrage macOS 27.3 pour nabu n'a été produit ni validé ; il n'y a donc rien de sûr à flasher à ce stade.
* Le dépôt contient un abaisseur expérimental de quelques instructions arm64e vers ARM64, mais il ne couvre pas toute l'ABI arm64e, ne relocalise pas les branches, ne reconstruit pas les caches dynamiques et ne rend pas un système démarrable. Il ne suffit pas à contourner le prérequis PAC de macOS 27.3.

## Émulation PAC : piste vérifiée sur la version XNU ciblée

Le profil macOS 27.3 épingle XNU `12377.121.6` (`ac9718fb1af618d5ce8678d0dc6e8a58f252216f`). Le projet public [Bergamota](https://github.com/ry-diffusion/Bergamota) fournit un [correctif d'émulation PAC](https://github.com/ry-diffusion/Bergamota/blob/develop/xnu/patches-12377/1019-sweet-pac-emulation.patch) pour cette génération de XNU. J'ai vérifié localement que ce correctif s'applique à cette révision après son prérequis `0141-sweet-fjcvtzs-emulation.patch`.

Cette implémentation intercepte certaines instructions PAC arm64e en mode utilisateur 64 bits et les émule dans XNU. Le rapport du projet décrit des vérifications du décodeur et une compilation CI, mais indique qu'aucun démarrage sur l'appareil n'a encore été réalisé. Cette piste n'est donc pas encore validée en démarrage natif, ni adaptée au profil macOS 27.3.

La portée reste insuffisante pour le kernelcache Mac17,11 mesuré ici : 370 membres Mach-O, 18 650 258 mots d'instructions scannés, 643 formes PAC à relocaliser, 24 formes refusées par l'abaisseur expérimental et 4 segments exécutables non couverts. La version actuelle du réécriveur refuse donc la sortie. L'émulation EL0 seule ne traite pas les instructions PAC dans le noyau et les kexts EL1.

Mesures publiées : [`lab/results/nabu-macos27-pacemu-reference.json`](lab/results/nabu-macos27-pacemu-reference.json) et [`lab/results/macos27-kernelcache-pac-scan-summary.json`](lab/results/macos27-kernelcache-pac-scan-summary.json). Aucun fichier Apple n'a été inclus dans ce dépôt.

## Travail restant vers le démarrage natif

1. Confirmer le support PAC avec les registres architecturaux et les tests EL1/EL0 de UniXNU sur les huit cœurs. Si le processeur ne possède pas PAC, il faut d'abord concevoir et valider une voie de compatibilité arm64e complète ; des pilotes Wi-Fi/tactile ne peuvent pas résoudre ce verrou CPU.
2. Adapter le noyau et les pilotes nabu à la collection de noyau macOS 27.3, puis construire le payload et les volumes depuis un Mac/Xcode avec l'IPSW fourni par le propriétaire.
3. Qualifier un démarrage sans écriture, puis seulement installer après création d'une image et d'un retour arrière vérifiés. L'installation ne doit pas commencer par un flash à l'aveugle.

L'objectif reste macOS natif. Les essais Sonoma en QEMU sont de l'historique et ne constituent pas une installation macOS 27.3.
