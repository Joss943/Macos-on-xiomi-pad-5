# macOS 27.3 sur Xiaomi Pad 5 (nabu / SM8150)

La cible demandée est **macOS 27.3, build 26C5035r**. Le profil public UniXNU pour macOS 27.3 cible `Mac17,11` et compile XNU en **arm64e**. Il exige le Pointer Authentication matériel (PAC) sur chaque cœur. Le dépôt UniXNU indique que les appareils sans PAC restent sur les profils arm64, jusqu'à iPadOS 17 pour cette génération. Références : [profil macOS](https://unixnu.com/porting/macos), [prérequis arm64e](https://unixnu.com/porting/arm64e).

## Base XNU macOS 27.3

L'IPSW macOS 27.3 embarque XNU `13432.60.57`. Le profil UniXNU public de cette version choisit délibérément les sources XNU `12377.121.6`, puis ajoute les appels Darwin 26, les KPI macOS et les adaptations macOS 27.3. La base 12377 n'est donc pas une erreur de version : c'est la base de compilation publiée tant que les sources Darwin 26 ne sont pas disponibles. Le port nabu doit étendre ce profil et son prélink, pas attendre un tag 13432. Références : [profil macOS 27.3](https://unixnu.com/porting/macos), [profil arm64e](https://unixnu.com/porting/arm64e).

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

* **Aucun port macOS 27.3 nabu prêt à construire ou à installer n'est actuellement présent dans ce dépôt.** L'IPSW exact est déjà présent dans le labo local; le profil UniXNU Mac 27.3 existe, mais son chemin de build reste configuré pour sa carte de référence et l'architecture arm64e.
* Le dépôt historique [UniXNU-nabu de zzweiqing](https://github.com/zzweiqing/UniXNU-nabu) cible iPadOS 17.7 (21H16), pas macOS 27.3. Un port plus récent, [Lux12138/unixnu-nabu](https://github.com/Lux12138/unixnu-nabu), configure iPadOS 17.7.11 (21H461) et rapporte un démarrage XNU jusqu'à SpringBoard; son affichage attend encore un provider `IOMobileFramebuffer`. Le mainteneur précise que ses mesures viennent d'une Pad 5 modifiée à 12 Gio, alors que la tablette reliée ici expose 5 633 852 kio. Ce travail fournit des références de démarrage nabu, mais ne prouve ni macOS 27.3, ni le tactile et le Wi-Fi sous ce noyau.
* Le profil public macOS 27.3 utilise XNU 12377 comme base publiée et prélinke le kernelcache Mac17,11. L'override nabu sélectionne arm64 parce que le SM8150 n'a pas PAC matériel; cela exige d'émuler toute l'ABI PAC des binaires arm64e du kernelcache.
* Le bootloader de cette tablette est encore verrouillé. Aucun binaire de démarrage macOS 27.3 pour nabu n'a été produit ni validé ; il n'y a donc rien de sûr à flasher à ce stade.
* Le dépôt contient un abaisseur expérimental de quelques instructions arm64e vers ARM64, mais il ne couvre pas toute l'ABI arm64e, ne relocalise pas les branches, ne reconstruit pas les caches dynamiques et ne rend pas un système démarrable. Il ne suffit pas à contourner le prérequis PAC de macOS 27.3.

## Émulation PAC : piste vérifiée sur la version XNU ciblée

Le profil de travail épingle XNU `12377.121.6` (`ac9718fb1af618d5ce8678d0dc6e8a58f252216f`), la base publiée par UniXNU pour macOS 27.3. Le patch [`0002-emulate-pauth-el0-el1-without-pac.patch`](lab/compat/patches/xnu-12377/0002-emulate-pauth-el0-el1-without-pac.patch) ajoute un émulateur des instructions PAC non-HINT au chemin d'instruction illégale de cette base XNU. Il s'active automatiquement sous `NABU` et traite EL0 et EL1, dont les chargements `LDRAA/LDRAB` qui bloquaient une réécriture de largeur fixe. Le modèle conserve des pointeurs VA non signés et n'offre aucune protection PAC.

L'émulateur est encore expérimental : seul le modèle C portable a été compilé sur l'hôte. Le patch XNU, son chemin EL0/EL1 et son intégration au profil macOS 27.3 ne sont pas compilés ni validés par un démarrage.

Le kernelcache Mac17,11 mesuré ici compte 370 membres Mach-O et 18 650 258 mots d'instructions; le réécriveur statique refuse toujours la sortie face à 643 chargements qui exigeraient une expansion et quatre segments exécutables non couverts. L'émulateur XNU vise à traiter ces instructions à l'exécution sans agrandir le code. Treize scénarios C hôte passent, mais le code XNU n'a pas été compilé et aucun kernelcache n'a été démarré avec lui. Le profil public macOS reste `arm64e`; le patch [`nabu-macos27-arm64-profile.patch`](lab/compat/patches/unixnu/nabu-macos27-arm64-profile.patch) ajoute une sélection `arm64` propre à l'override nabu, sans modifier le profil Mac. Le fragment [`lab/nabu/macos-27.3/arm64-override.toml`](lab/nabu/macos-27.3/arm64-override.toml) cible uniquement le profil Apple 27.3. Le profil de build complet, XNU compilé et le démarrage nabu restent à valider.

Les fixups de données confirment l'ampleur du travail : le kernelcache racine contient 1 017 384 pointeurs chaînés, dont 898 429 authentifiés PAC dans `__DATA_CONST` et `__DATA` (clé IA : 895 390; clé DA : 3 039). Le tactile seul dépend de 334 entrées authentifiées. Le scanner [`lab/compat/scan_kernelcache_fixups.py`](lab/compat/scan_kernelcache_fixups.py) a parcouru les 672 chaînes sur trois segments; son résultat [`lab/results/macos27-kernelcache-fixup-summary.json`](lab/results/macos27-kernelcache-fixup-summary.json) confirme que l'IPSW n'a pas été modifié. Une passe de résolution calcule les 1 017 384 adresses cibles depuis la base `0xfffffe0007004000` : toutes sont au niveau de cache 0 et tombent dans les segments racine ([rapport](lab/results/macos27-kernelcache-fixup-resolution.json)). XNU `dyld_kernel_fixups.h` arrêtait explicitement le démarrage lorsqu'un build sans PAC rencontrait une entrée authentifiée. Le patch [`0001-accept-authenticated-fixups-without-pac.patch`](lab/compat/patches/xnu-12377/0001-accept-authenticated-fixups-without-pac.patch) retire ce refus dans le chemin non-PAC : XNU écrit l'adresse cible résolue comme pointeur ordinaire. Le patch [`0002-emulate-pauth-el0-el1-without-pac.patch`](lab/compat/patches/xnu-12377/0002-emulate-pauth-el0-el1-without-pac.patch) traite ensuite les instructions non-HINT au moment où elles piègent. Le troisième patch ajoute la carte SM8150 et GICv3. Le quatrième patch ajoute l'ADT et le démarrage PSCI; la série de quatre patchs s'applique au commit XNU exact, mais XNU n'a pas été compilé ni démarré sur la tablette.

Le nouveau patch [`0003-nabu-sm8150-machine-and-gic.patch`](lab/compat/patches/xnu-12377/0003-nabu-sm8150-machine-and-gic.patch) déclare la carte nabu ARM64, le cache 64 octets, les huit affinités MPIDR, le timer INTID 19, le SGI 1 et les IRQ Group 1 non sécurisées. Il corrige aussi le nettoyage des IRQ spurious. Il passe une application de série à blanc sur XNU 12377, mais il reste non compilé. Le profil de build UniXNU suppose encore le nom de répertoire BCM2837; [`nabu-machine-flags.patch`](lab/compat/patches/unixnu/nabu-machine-flags.patch) et [`arm64-machine.config`](lab/nabu/macos-27.3/arm64-machine.config) ajoutent un override minimal des flags sans déplacer ses artefacts existants.

Le quatrième patch [`0004-nabu-psci-smp-and-platform-expert.patch`](lab/compat/patches/xnu-12377/0004-nabu-psci-smp-and-platform-expert.patch) ajoute l'expert ADT nabu, un driver `IOCPU` et le démarrage PSCI `CPU_ON64` via SMC. Le DT SM8150 public décrit huit CPU `qcom,kryo485` et la méthode PSCI SMC; les capacités distinguent quatre A55, trois A76 intermédiaires et le cœur principal ([source Linux](https://gbmc.googlesource.com/linux/+/9f2f6316d753fe80c764e924cee475306f38ceb6/arch/arm64/boot/dts/qcom/sm8150.dtsi#L51), [spécification Arm PSCI](https://documentation-service.arm.com/static/5f905b78f86e16515cdc1fca)). Le patch ajoute un trampoline EL2→EL1 et lance les CPU dans l'ordre en vérifiant les SGI. La série complète s'applique à XNU 12377 dans un worktree propre et le diff passe `git diff --check`; aucun build, lancement PSCI ou démarrage tablette n'a encore été validé. CPU_OFF, veille, tactile et Wi-Fi restent à faire.

Les 13 scénarios reproductibles du modèle comprennent aussi un balayage des 1 024 valeurs d'immédiat signées LDRAA/LDRAB. Le rapport est dans [`lab/results/macos27-pauth-emulator-fixtures.json`](lab/results/macos27-pauth-emulator-fixtures.json), avec le code et le fixture C dans `lab/compat/`.

Mesures publiées : [`lab/results/nabu-macos27-pacemu-reference.json`](lab/results/nabu-macos27-pacemu-reference.json) et [`lab/results/macos27-kernelcache-pac-scan-summary.json`](lab/results/macos27-kernelcache-pac-scan-summary.json). Aucun fichier Apple n'a été inclus dans ce dépôt.

## Pilote tactile et Wi-Fi nabu

Le dépôt matériel public [UniXNU-nabu](https://github.com/zzweiqing/UniXNU-nabu) cible iPadOS 17.7 (21H16), avec un pilote tactile NT36523 lié à l'ancienne ABI IOHID. Il indique que le Wi-Fi n'est pas implémenté. Une nouvelle lecture ADB en lecture seule sur la tablette identifie le nœud Wi-Fi `qcom,cnss-qca6390@a0000000`, l'interface `wlan0` reliée à `qcom,icnss@18800000`, et le module Android `wlan`; Bluetooth apparaît séparément comme `vendor:bt_wcn3990`. Le rapport sans adresse MAC ni numéro de série est [`lab/results/nabu-macos27-radio-hardware.json`](lab/results/nabu-macos27-radio-hardware.json).

La documentation Linux indique que QCA6390 est pris en charge par `ath11k` sur PCI, avec firmware et MSI spécifiques ([ath11k](https://wireless.docs.kernel.org/en/latest/en/users/drivers/ath11k.html), [pilote PCI QCA6390](https://github.com/torvalds/linux/blob/master/drivers/net/wireless/ath/ath11k/pci.c)). Cela sert de référence au matériel; aucun code Linux n'est utilisable directement comme pilote macOS. Il manque toujours une implémentation XNU/macOS 27.3 du bus, du chargement firmware, du transport MHI, de l'interface IO80211, ainsi que l'adaptation tactile à l'ABI 27.3.

Le pilote tactile de référence est lié à `IOHIDFamily` du build 21H16 et à une table `IOHIDDevice` de 207 entrées. Sur le kernelcache macOS 27.3, l'étendue entre les symboles de la vtable et de la métaclasse est de 2 696 octets : 335 cellules de 8 octets après l'en-tête ABI de 16 octets. Le décodage du `LC_DYLD_CHAINED_FIXUPS` du kernelcache racine confirme 334 entrées de fonction authentifiées avec la clé IA et une dernière cellule nulle d'alignement. En rapprochant les pointeurs des symboles de tous les 370 membres Mach-O, les 334 fonctions ont un symbole exact. `handleStart` est au slot 272 et `handleReport` au slot 285, alors que le binding iPadOS 17.7 les place aux slots 168/181. Le binding ancien ne peut donc pas être réutilisé; il faut reconstruire le sous-classement macOS avec cette ABI et traiter ses pointeurs PAC.

L'outil [`lab/compat/inspect_iohid_vtable.py`](lab/compat/inspect_iohid_vtable.py) décode les chaînes de pointeurs du kernelcache sans le modifier. Son test synthétique couvre les pointeurs format 8 authentifiés. Le résultat [`lab/results/macos27-iohid-vtable-report.json`](lab/results/macos27-iohid-vtable-report.json) ne contient que des adresses, des noms de symboles et des métadonnées de fixup; aucun code Apple n'est copié.

## Port nabu existant : référence, pas solution macOS 27.3

Le port public [Lux12138/unixnu-nabu](https://github.com/Lux12138/unixnu-nabu) est configuré sur iPadOS 17.7.11 (`21H461`, `iPad7,1`). Son état daté du 28 octobre 2026 indique que XNU atteint SpringBoard et les services utilisateur; il reste un provider d'affichage à attacher. Le port utilise une Pad 5 modifiée à 12 Gio. La tablette mesurée dans ce dépôt expose `MemTotal = 5 633 852 kio`; ses réglages mémoire ne peuvent donc pas être repris tels quels. Cette avancée confirme qu'une chaîne UEFI/XNU nabu est possible sur cette famille, mais elle ne constitue pas un démarrage de macOS 27.3.

UniXNU précise par ailleurs que les profils macOS 27 sont arm64e et nécessitent du PAC natif ([prérequis arm64e](https://unixnu.com/porting/arm64e)). Les mesures de cette Pad 5 montrent l'absence de PAC sur huit cœurs. Les patches de ce dépôt explorent une émulation, sans build ni démarrage; le port iPadOS 17.7.11 ne ferme pas cet écart.

## Travail restant vers le démarrage natif

1. Compiler XNU 12377 avec les quatre patchs et corriger les erreurs de compilation ou de liens; le code PSCI/GIC n'a pas été exécuté.
2. Qualifier le démarrage SMP et l'émulation PAC, puis adapter le tactile à l'ABI IOHID macOS 27 et écrire un pilote XNU pour QCA6390.
3. Faire valider l'image de démarrage et le retour arrière avant tout déverrouillage ou flash. La tablette mesurée a encore un bootloader verrouillé et aucun binaire de démarrage n'a été produit.

L'objectif reste macOS natif. Les essais Sonoma en QEMU sont de l'historique et ne constituent pas une installation macOS 27.3.

\n
