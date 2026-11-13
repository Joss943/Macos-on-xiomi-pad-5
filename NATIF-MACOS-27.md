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

Le profil macOS 27.3 épingle XNU `12377.121.6` (`ac9718fb1af618d5ce8678d0dc6e8a58f252216f`). Le patch [`0002-emulate-pauth-el0-el1-without-pac.patch`](lab/compat/patches/xnu-12377/0002-emulate-pauth-el0-el1-without-pac.patch) ajoute un émulateur des instructions PAC non-HINT au chemin d'instruction illégale de XNU. Il est activé par `nabu-pauthemu=1` et traite EL0 et EL1, dont les chargements `LDRAA/LDRAB` qui bloquaient une réécriture de largeur fixe. La série complète s'applique proprement à la révision XNU épinglée. Le modèle conserve des pointeurs VA non signés et n'offre aucune protection PAC.

L'émulateur est encore expérimental : seul le modèle C portable a été compilé sur l'hôte. Le patch XNU, son chemin EL0/EL1 et son intégration au profil macOS 27.3 ne sont pas compilés ni validés par un démarrage.

Le kernelcache Mac17,11 mesuré ici compte 370 membres Mach-O et 18 650 258 mots d'instructions; le réécriveur statique refuse toujours la sortie face à 643 chargements qui exigeraient une expansion et quatre segments exécutables non couverts. L'émulateur XNU vise à traiter ces instructions à l'exécution sans agrandir le code. Treize scénarios C hôte passent, mais le code XNU n'a pas été compilé et aucun kernelcache n'a été démarré avec lui. Le profil public macOS reste `arm64e`; il faut encore produire un profil nabu qui construit XNU sans `HAS_APPLE_PAC`, puis valider l'exécution arm64e et les règles dyld/AMFI de macOS 27.3.

Les fixups de données confirment l'ampleur du travail : le kernelcache racine contient 1 017 384 pointeurs chaînés, dont 898 429 authentifiés PAC dans `__DATA_CONST` et `__DATA` (clé IA : 895 390; clé DA : 3 039). Le tactile seul dépend de 334 entrées authentifiées. Le scanner [`lab/compat/scan_kernelcache_fixups.py`](lab/compat/scan_kernelcache_fixups.py) a parcouru les 672 chaînes sur trois segments; son résultat [`lab/results/macos27-kernelcache-fixup-summary.json`](lab/results/macos27-kernelcache-fixup-summary.json) confirme que l'IPSW n'a pas été modifié. Une passe de résolution calcule les 1 017 384 adresses cibles depuis la base `0xfffffe0007004000` : toutes sont au niveau de cache 0 et tombent dans les segments racine ([rapport](lab/results/macos27-kernelcache-fixup-resolution.json)). XNU `dyld_kernel_fixups.h` arrêtait explicitement le démarrage lorsqu'un build sans PAC rencontrait une entrée authentifiée. Le patch [`0001-accept-authenticated-fixups-without-pac.patch`](lab/compat/patches/xnu-12377/0001-accept-authenticated-fixups-without-pac.patch) retire ce refus dans le chemin non-PAC : XNU écrit l'adresse cible résolue comme pointeur ordinaire. Le patch [`0002-emulate-pauth-el0-el1-without-pac.patch`](lab/compat/patches/xnu-12377/0002-emulate-pauth-el0-el1-without-pac.patch) traite ensuite les instructions non-HINT au moment où elles piègent. Les deux patches ont été appliqués au commit XNU exact; le fixture C passe, mais XNU n'a pas été compilé ni démarré sur la tablette.

Les 13 scénarios reproductibles du modèle comprennent aussi un balayage des 1 024 valeurs d'immédiat signées LDRAA/LDRAB. Le rapport est dans [`lab/results/macos27-pauth-emulator-fixtures.json`](lab/results/macos27-pauth-emulator-fixtures.json), avec le code et le fixture C dans `lab/compat/`.

Mesures publiées : [`lab/results/nabu-macos27-pacemu-reference.json`](lab/results/nabu-macos27-pacemu-reference.json) et [`lab/results/macos27-kernelcache-pac-scan-summary.json`](lab/results/macos27-kernelcache-pac-scan-summary.json). Aucun fichier Apple n'a été inclus dans ce dépôt.

## Pilote tactile et Wi-Fi nabu

Le dépôt matériel public [UniXNU-nabu](https://github.com/zzweiqing/UniXNU-nabu) rapporte un écran interactif et un pilote NT36523 tactile fonctionnel sur nabu, avec iPadOS 17.7. Il indique que le Wi-Fi n'est pas implémenté. Ce dépôt sert ici de référence de carte uniquement; la cible reste macOS 27.3.

Le pilote tactile de référence est lié à `IOHIDFamily` du build 21H16 et à une table `IOHIDDevice` de 207 entrées. Sur le kernelcache macOS 27.3, l'étendue entre les symboles de la vtable et de la métaclasse est de 2 696 octets : 335 cellules de 8 octets après l'en-tête ABI de 16 octets. Le décodage du `LC_DYLD_CHAINED_FIXUPS` du kernelcache racine confirme 334 entrées de fonction authentifiées avec la clé IA et une dernière cellule nulle d'alignement. En rapprochant les pointeurs des symboles de tous les 370 membres Mach-O, les 334 fonctions ont un symbole exact. `handleStart` est au slot 272 et `handleReport` au slot 285, alors que le binding iPadOS 17.7 les place aux slots 168/181. Le binding ancien ne peut donc pas être réutilisé; il faut reconstruire le sous-classement macOS avec cette ABI et traiter ses pointeurs PAC.

L'outil [`lab/compat/inspect_iohid_vtable.py`](lab/compat/inspect_iohid_vtable.py) décode les chaînes de pointeurs du kernelcache sans le modifier. Son test synthétique couvre les pointeurs format 8 authentifiés. Le résultat [`lab/results/macos27-iohid-vtable-report.json`](lab/results/macos27-iohid-vtable-report.json) ne contient que des adresses, des noms de symboles et des métadonnées de fixup; aucun code Apple n'est copié.

## Travail restant vers le démarrage natif

1. Confirmer le support PAC avec les registres architecturaux et les tests EL1/EL0 de UniXNU sur les huit cœurs. Si le processeur ne possède pas PAC, il faut d'abord concevoir et valider une voie de compatibilité arm64e complète ; des pilotes Wi-Fi/tactile ne peuvent pas résoudre ce verrou CPU.
2. Adapter le noyau et les pilotes nabu à la collection de noyau macOS 27.3, puis construire le payload et les volumes depuis un Mac/Xcode avec l'IPSW fourni par le propriétaire.
3. Qualifier un démarrage sans écriture, puis seulement installer après création d'une image et d'un retour arrière vérifiés. L'installation ne doit pas commencer par un flash à l'aveugle.

L'objectif reste macOS natif. Les essais Sonoma en QEMU sont de l'historique et ne constituent pas une installation macOS 27.3.

