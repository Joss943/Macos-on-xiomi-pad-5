# macOS 27.3 sur Xiaomi Pad 5 (nabu / SM8150)

La cible demandée est **macOS 27.3, build 26C5035r**. Le profil public UniXNU pour macOS 27.3 cible `Mac17,11` et compile XNU en **arm64e**. Il exige le Pointer Authentication matériel (PAC) sur chaque cœur. Le dépôt UniXNU indique que les appareils sans PAC restent sur les profils arm64, jusqu'à iPadOS 17 pour cette génération. Références : [profil macOS](https://unixnu.com/porting/macos), [prérequis arm64e](https://unixnu.com/porting/arm64e).

## Résultats vérifiés le 14 novembre 2026

Ce qui suit a été exécuté, pas seulement écrit. Tout le reste de ce document est à lire avec ce tableau en tête.

| Vérification | Où | Résultat |
|---|---|---|
| Compilation de XNU `12377.121.6` non patché, carte VMAPPLE (témoin de la chaîne d'outils) | CI `xnu-build.yml`, runner macOS 15, Xcode 26.3, SDK 26.2, KDK 26.5, recette `blacktop/darwin-xnu-build@6639065` | **Réussie** (15 min). La chaîne de compilation est donc valide. |
| Compilation de la série nabu, carte NABU, 1re passe | même CI | **Échec, 7 erreurs**, toutes corrigées depuis : compteurs CPMU d'Apple activés pour toute carte non virtuelle, constantes de barrière absentes d'IOKit. |
| Compilation NABU, passes 2 à 16 | même CI | Erreurs corrigées une à une, toutes dans la série 0003/0004 : sources ouvertes `osfmk/arm/pmap` et assembleur arm64 compilés à la place de l'archive Apple précompilée, fichiers et en-têtes non publiés écartés (`amcc_rorgn_*`, `sart.h`, `uat.h`, `tunables.s`), Tightbeam retiré, `libkern/os/firehose_nabu.c` à la place de `libfirehose_kernel`, PPL neutralisé, `CPU_OVRD` d'Apple écarté (`NO_CPU_OVRD`), immédiat ARM64 invalide corrigé dans `start.s`, 4 symboles fournis par `osfmk/arm64/nabu_platform_stubs.c`, 67 exports Apple (SPTM, DART/SART/UAT, `IOUnifiedAddressTranslator`) retirés des listes de NABU (`config/nabu_unavailable.exports`). |
| **Compilation et liaison NABU, passe 17** (`1fce703`, run 43559846888) | même CI | **Réussie.** `kernel.development.nabu` : Mach-O 64 bits exécutable **arm64**, `__TEXT_EXEC` 9 502 720 octets, SHA-256 `2e600eca53abd407c6eb8b1a24022cdcfa013358b11143eac84f5a563b620820`. Le témoin VMAPPLE réussit aussi. Le binaire n'a pas été conservé par ce run ; les runs suivants le joignent à l'artefact CI (14 jours). Il n'est jamais versionné. |
| Analyse ISA du noyau NABU contre Kryo 485 | `scan_isa_level.py` | 2 374 676 instructions, **0 instruction PAC**, **24 instructions que le Kryo ne peut pas exécuter** : 19 SVE/SME, 4 registres système Apple, 1 MTE (v8.5). Elles doivent être retirées ou rendues inatteignables avant tout essai. À comparer avec VMAPPLE (arm64e) : 56 292 PAC, 322 SVE/SME, 52 registres Apple. |
| Détail des 24 instructions signalées (run 18, symbolisées par `atos`) | `xnu-build.yml` | **4 réelles** : `mrs`/`msr S3_5_C15_C2_6` (WatchdogDiag0 d'Apple) dans `awl_mark_hv_entry` et `awl_pm_state_change_cbk` (`osfmk/kern/debug.c`), atteignables seulement si l'ADT annonce le registre ; retirées du build NABU dans 0003. **20 fausses alertes** : des données dans `__text` décodées comme instructions, vérifiées une par une — chaînes `.asciz` de panique après `fleh_irq_sp1`, `fleh_fiq_sp1`, `preempt_underflow`, `preempt_count_notzero`, `update_mdscr` (`locore.s`), table de constantes `K256` (`sha256_compress_arm64.s`), tables de `lz4_decode_asm`/`lz4_encode_2gb`. |
| Analyse ISA après correction (run 19, `a172ef2`) | `xnu-build.yml` | Compilation NABU et témoin VMAPPLE réussis. **0 PAC, 0 registre Apple** ; restent exactement les 20 fausses alertes de données listées ci-dessus. Aucune instruction de code connue que le Kryo 485 ne peut pas exécuter. Noyau dans l'artefact CI 14101323023. |
| Ce que ce noyau n'est pas | — | **Pas amorçable en l'état** : aucune chaîne de démarrage nabu (UEFI → chargeur → ADT) n'existe, firehose `os_log` n'est qu'un substitut, et les 24 instructions ci-dessus planteraient. Il n'a jamais tourné sur la tablette. |
| Défauts trouvés à la relecture | patches 0003 et 0004 | Label `nabu_irq_epilogue` défini hors carte NABU, qui cassait les autres configurations avec `-Werror`. Symbole `sysreg_restore` inexistant dans XNU 12377. Champs masquant des membres hérités. Tous corrigés. |
| Série 0001 à 0004 | `lab/compat/xnu-build/apply_series.sh` | S'applique sur `ac9718fb` et produit exactement l'arbre de travail vérifié. |
| Pile tactile portable (NT36523, GENI SPI, HID) | `lab/nabu/touch/`, CI `touch-kext.yml` | Décodeur C identique au parseur Python sur 20 000 paquets. Moteur SPI testé contre un modèle GENI sur toutes les longueurs de 1 à 120 octets, erreurs et délais. ASan et UBSan propres. |
| Kext tactile `NabuNT36523HID` | CI `touch-kext.yml` | **Compilé et lié** en arm64e et arm64 contre le SDK 26.2. `kmutil` résout tous ses symboles, IOHIDFamily compris, dans le kernelcache du runner (macOS 15.6). **Ce n'est pas le SDK ni le kernelcache macOS 27** : aucun Xcode 27 n'est installé sur les runners. |
| Wi-Fi | `lab/nabu/wifi/` | Matériel réidentifié (WCN3990 intégré, pas QCA6390). Codec QRTR/QMI indépendant testé octet par octet. Rien n'est envoyé à un modem. |
| Sources Apple de macOS 27 | `apple-oss-distributions` | **Non publiées** : le dernier manifeste est macOS 26.5 (IOHIDFamily-2238.120.5). Les interfaces macOS 27 ne se confirment donc qu'avec le SDK Xcode 27 ou les symboles du kernelcache 27.3 local (outil `lab/compat/check_kext_symbols.py`). |
| Démarrage sur la tablette | — | **Aucun.** Un noyau nabu est compilé et lié, mais il n'est pas amorçable ; rien n'a été déverrouillé ni flashé. |

### Prélink macOS 27.3 — premier essai

Le noyau du run 19 a été téléchargé depuis l'artefact CI et confronté au kernelcache `Mac17,11` exact. Après une petite correction locale du matcher XnuPrelink pour accepter un fixture macOS 27.3 sans liste de fonctions, l'appariement a trouvé 5 634 fonctions sur 23 976, 36 objets de données et 530 noms sur 3 856 références noyau utilisées par les kexts. Aucun conflit n'a été trouvé, mais la couverture reste insuffisante pour émettre un kernelcache amorçable.

L'émission s'est arrêtée sur la liaison AMFI vers `_unixnu_kernel_stack_shift`, symbole absent du premier noyau nabu. Le patch [`0005-macos27-coreentitlements-stack-shift.patch`](lab/compat/patches/xnu-12377/0005-macos27-coreentitlements-stack-shift.patch) ajoute la valeur 13 correspondant aux piles alignées sur 8 Kio du noyau 4 Kio. Il s'applique après les patches nabu 0001–0004. Le build de ce noyau corrigé et un nouvel essai de prélink sont en cours; aucun fichier amorçable n'a encore été produit. Rapport : [`lab/results/macos27-prelink-readiness-2026-11-14.json`](lab/results/macos27-prelink-readiness-2026-11-14.json).

Les résultats de la compilation NABU suivante sont dans l'onglet Actions du dépôt, workflow « XNU 12377 compile (macOS runner) », avec le journal complet et un résumé des erreurs en artefact.

### Prélink macOS 27.3 — métadonnées split-segment (patch 0006, 14 novembre 2026)

Le noyau du run 20 contient `_unixnu_kernel_stack_shift`, mais la relocalisation du prélink échoue : le Mach-O nabu ne porte pas d'information split-segment. Cause trouvée dans `makedefs/MakeInc.def` : `-Wl,-add_split_seg_info` n'est ajouté que par `LDFLAGS_KERNEL_ONLY_SUBARCH_arm64e` et `..._x86_64`. Le profil NABU garde `ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG=arm64` (patch 0003), et `LDFLAGS_KERNEL_ONLY_SUBARCH_arm64` n'existe pas : le flag n'atteint jamais le link final. Le patch [`0006-nabu-link-kernel-with-split-seg-info.patch`](lab/compat/patches/xnu-12377/0006-nabu-link-kernel-with-split-seg-info.patch) définit cette variable uniquement quand `CURRENT_MACHINE_CONFIG=NABU`, avec `-Wl,-add_split_seg_info -Wl,-kernel` comme les règles arm64e et x86_64.

Résultats :

- **Run 22** (`-add_split_seg_info` seul) : flag présent sur la ligne de link, `LC_SEGMENT_SPLIT_INFO` présent, 441 825 références lues par `split_references()` sans hors-plage ni doublon. L'émission échoue ensuite (`Split-segment pointer disagrees with fixup`) : le noyau n'a pas de chained fixups mais 115 805 relocations locales classiques.
- **Run 23** (`-kernel` ajouté) : flag présent, mais ld n'émet toujours pas de chained fixups pour arm64. Le contrôle CI échoue volontairement sur ce point. Les 115 805 relocations sont toutes `ARM64_RELOC_UNSIGNED` 64 bits, base = premier segment, et coïncident une à une avec les enregistrements split-seg de type 2.
- **XnuPrelink** ([`arm64-local-relocations.patch`](lab/compat/patches/xnu-prelink/arm64-local-relocations.patch), sur `440589b`) : lecture stricte de ces relocations comme rebases simples ; l'en-tête de l'entrée noyau ne les annonce plus une fois converties en chaînes racine ; resscellement HMAC du noyau sauté seulement si ni le noyau natif ni le noyau d'origine ne portent `__fips_hmacs` (macOS 27.3 scelle corecrypto dans `com.apple.kec.corecrypto`). 69 tests OK.
- **Émission stricte, racine APFS** : toutes les étapes structurelles passent (fermeture de 9 kexts, placement, relocalisation, chaînes, en-tête, scellement). Arrêt au contrôle final : **7 455 références non résolues** (APFS 2 404, IOStorageFamily 2 305, CoreAnalyticsFamily 853, IOCryptoAcceleratorFamily 614, AppleImage4 442, Image4 417, AppleEffaceableStorage 408, corecrypto 11, CoreTrust 1). Aucune image écrite. `--allow-missing` n'est pas utilisé : il exige un symbole piège dans le noyau.

| Niveau | État |
|---|---|
| 1. Code modifié | **Fait.** Série 0001–0008 reproductible sur `ac9718fb` ; patches XnuPrelink (relocations locales, vtables arm64) appliqués sur `440589b` propre, 73 tests OK. |
| 2. Noyau compilé | **Fait** (run 25, série 0001–0008, `2ee5523b…`) : split-seg vérifié ; relocations locales lues par XnuPrelink ; les 4 KPI macOS 27 des patches 0007–0008 sont définis. |
| 3. Prélink émis | **Non.** Toutes les étapes structurelles passent. Appariement par noms (le kernelcache 27.3 porte les symboles du noyau) : 3 417 fonctions et 287 données sur 3 856 cibles, 0 conflit. Émission stricte APFS : **4 références non résolues** (7 455 → 1 001 → 8 → 4), toutes dans `com.apple.security.Image4` (`image4_v2_set_nonce_digest`, `_roll_nonce`, `_load_diavlo_root_ca`, `_load_local_policy`). Ces quatre fonctions passent par le moniteur d'exécution de confiance d'Apple et ne sont pas réimplémentées ici. APFS lui-même est entièrement résolu. Aucune image écrite. |
| 4. Image amorçable | **Non.** |
| 5. Démarrage sur la tablette | **Aucun.** Bootloader observé verrouillé, rien flashé. |
| 6. Tactile et Wi‑Fi sur matériel | **Non testés.** |

Rapports : [`macos27-split-seg-0006-2026-11-14.json`](lab/results/macos27-split-seg-0006-2026-11-14.json), [`macos27-prelink-run22-2026-11-14.json`](lab/results/macos27-prelink-run22-2026-11-14.json), [`macos27-prelink-run23-2026-11-14.json`](lab/results/macos27-prelink-run23-2026-11-14.json)., [`macos27-prelink-run23-vtables-2026-11-14.json`](lab/results/macos27-prelink-run23-vtables-2026-11-14.json), [`macos27-prelink-run25-names-2026-11-14.json`](lab/results/macos27-prelink-run25-names-2026-11-14.json).

### Compiler XNU nabu soi-même

Sur un Mac avec Xcode 26 (SDK macOS 26) :

```bash
git clone https://github.com/blacktop/darwin-xnu-build dxb
git -C dxb checkout --detach 663906528d1cd5ea8fde7de6f16de73db9511549
git clone --branch xnu-12377.121.6 https://github.com/apple-oss-distributions/xnu.git dxb/xnu
bash lab/compat/xnu-build/apply_series.sh dxb/xnu
cd dxb && MACOS_VERSION=26.5 KERNEL_CONFIG=DEVELOPMENT ARCH_CONFIG=ARM64 MACHINE_CONFIG=NABU bash build.sh
```

La recette télécharge le KDK 26.5 depuis le manifeste `dortania/KdkSupportPkg` ; il n'est jamais versionné ici.

### Références externes contrôlées

- [`Lux12138/unixnu-nabu`](https://github.com/Lux12138/unixnu-nabu) existe. Il construit XNU **8796** (famille iOS 16), et non iPadOS 17.7.11 comme écrit plus bas. Il annonce SpringBoard en espace utilisateur le 28/10/2026 sur une Pad 5 modifiée à 12 Gio, sans affichage (`IOMobileFramebuffer` sans fournisseur), sans mention du tactile ni du Wi-Fi. Sa chaîne de démarrage (Mu UEFI, puis le chargeur DarwinBoot depuis `cust`, puis `kernel.macho`) est la référence pour l'artefact amorçable nabu.
- `unixnu.com` n'était pas joignable depuis l'environnement de cette vérification. Les affirmations qui s'y réfèrent (profil 27.3 sur base 12377, prérequis arm64e) restent **non vérifiées**.

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

Le quatrième patch [`0004-nabu-psci-smp-and-platform-expert.patch`](lab/compat/patches/xnu-12377/0004-nabu-psci-smp-and-platform-expert.patch) ajoute l'expert ADT nabu, un driver `IOCPU` et le démarrage PSCI `CPU_ON64` via SMC. Le DT SM8150 public décrit huit CPU `qcom,kryo485` et la méthode PSCI SMC; les capacités distinguent quatre A55, trois A76 intermédiaires et le cœur principal ([source Linux](https://gbmc.googlesource.com/linux/+/9f2f6316d753fe80c764e924cee475306f38ceb6/arch/arm64/boot/dts/qcom/sm8150.dtsi#L51), [spécification Arm PSCI](https://documentation-service.arm.com/static/5f905b78f86e16515cdc1fca)). Le patch ajoute un trampoline EL2→EL1 et lance les CPU dans l'ordre en vérifiant les SGI. La série nabu a maintenant compilé et lié le noyau arm64 dans les runs CI 17–19; PSCI n'a pas été exécuté et aucun démarrage tablette n'a été observé. CPU_OFF, veille, tactile et Wi-Fi restent à faire.

Les 13 scénarios reproductibles du modèle comprennent aussi un balayage des 1 024 valeurs d'immédiat signées LDRAA/LDRAB. Le rapport est dans [`lab/results/macos27-pauth-emulator-fixtures.json`](lab/results/macos27-pauth-emulator-fixtures.json), avec le code et le fixture C dans `lab/compat/`.

Mesures publiées : [`lab/results/nabu-macos27-pacemu-reference.json`](lab/results/nabu-macos27-pacemu-reference.json) et [`lab/results/macos27-kernelcache-pac-scan-summary.json`](lab/results/macos27-kernelcache-pac-scan-summary.json). Aucun fichier Apple n'a été inclus dans ce dépôt.

### Revue des patches PAC, GIC et PSCI (14 novembre 2026)

Relecture ligne à ligne contre les sources de `xnu-12377.121.6` et la description matérielle du SM8150.

- **PAC (0001, 0002).** Les encodages décodés sont conformes à l'ARM ARM : `PACIA…XPACD` (`0xDAC1xxxx`, opcodes 0 à 17, Rn=31 imposé à partir de 8), `PACGA`, les huit formes `BRAA…BLRABZ`, `RETAA/RETAB`, `LDRAA/LDRAB` avec immédiat signé de 10 bits multiplié par 8. Les formes HINT (`PACIBSP`, `AUTIBSP`…) s'exécutent comme NOP sur ARMv8.2 et ne piègent pas. Limites constatées : chaque `RETAB` d'un kext Apple déclenche un piège, donc un coût par retour de fonction ; `ERETAA/ERETAB` ne sont pas émulés ; les instructions ARMv8.3+ qui ne sont pas du PAC (par exemple `LDAPUR`, `SB`, `FJCVTZS`) piègent aussi et ne sont pas émulées. Leur présence dans le kernelcache 27.3 se mesure avec `lab/compat/scan_isa_level.py`, à lancer en local sur le kernelcache extrait.
- **GIC (0003).** Les offsets `GICR_IGROUPR0` `0x10080`, `ISENABLER0` `0x10100` et `IPRIORITYR0` `0x10400` sont corrects. L'INTID 19 est bien le timer virtuel sur Qualcomm (PPI 3), et XNU programme `CNTV_*` hors carte Apple. Le registre `CNTVCTSS_EL0` (ARMv8.6) n'est lu que si la carte définit `__ARM_ARCH_8_6__`, ce que `NABU.h` ne fait pas. Reste ouvert : aucun `IOInterruptController` ne distribue les SPI du GIC aux pilotes, donc aucune interruption de périphérique n'atteint un pilote.
- **PSCI (0004).** `CPU_ON64` (`0xC4000003`), l'encodage de `ICC_SGI1R_EL1` et la recherche de l'entrée CPU par MPIDR dans le vecteur de reset sont corrects. Sur nabu, l'hyperviseur Qualcomm occupe EL2 : le trampoline EL2→EL1 ne sera pas emprunté, le chemin EL1 le sera.

## Pilote tactile et Wi-Fi nabu

Le dépôt matériel public [UniXNU-nabu](https://github.com/zzweiqing/UniXNU-nabu) cible iPadOS 17.7 (21H16), avec un pilote tactile NT36523 lié à l'ancienne ABI IOHID. Il indique que le Wi-Fi n'est pas implémenté. Une nouvelle lecture ADB en lecture seule sur la tablette identifie le nœud Wi-Fi `qcom,cnss-qca6390@a0000000`, l'interface `wlan0` reliée à `qcom,icnss@18800000`, et le module Android `wlan`; Bluetooth apparaît séparément comme `vendor:bt_wcn3990`. Le rapport sans adresse MAC ni numéro de série est [`lab/results/nabu-macos27-radio-hardware.json`](lab/results/nabu-macos27-radio-hardware.json).

**Correction du 14 novembre 2026 : le Wi-Fi n'est pas un QCA6390 en PCIe.** La mesure ADB ci-dessus rattache `wlan0` à `qcom,icnss@18800000`, le pilote du Wi-Fi intégré au SoC, et l'arbre matériel nabu public active `wifi@18800000` (`qcom,wcn3990-wifi`) sans aucun contrôleur PCIe. Le nœud `cnss-qca6390@a0000000` est générique à l'arbre Android du SM8150. Le Wi-Fi est donc le WLAN intégré de la famille WCN3990, avec la radio WCN3991, piloté sous Linux par `ath10k_snoc` (licence ISC) via le modem et le service QMI WLFW, pas par `ath11k`, MHI et PCIe. Preuves, pile requise et premier code : [`lab/nabu/wifi/WIFI.md`](lab/nabu/wifi/WIFI.md).

Le pilote tactile de référence est lié à `IOHIDFamily` du build 21H16 et à une table `IOHIDDevice` de 207 entrées. Sur le kernelcache macOS 27.3, l'étendue entre les symboles de la vtable et de la métaclasse est de 2 696 octets : 335 cellules de 8 octets après l'en-tête ABI de 16 octets. Le décodage du `LC_DYLD_CHAINED_FIXUPS` du kernelcache racine confirme 334 entrées de fonction authentifiées avec la clé IA et une dernière cellule nulle d'alignement. En rapprochant les pointeurs des symboles de tous les 370 membres Mach-O, les 334 fonctions ont un symbole exact. `handleStart` est au slot 272 et `handleReport` au slot 285, alors que le binding iPadOS 17.7 les place aux slots 168/181. Le binding ancien ne peut donc pas être réutilisé; il faut reconstruire le sous-classement macOS avec cette ABI et traiter ses pointeurs PAC.

Le pilote Linux nabu confirme le format des rapports NT36523 : 66 octets SPI, dix contacts et coordonnées/pression encodées sur six octets par contact ([source](https://github.com/SeimoDev/linux-xiaomi-nabu/blob/4e6d08bb1b467c721e19cd693e4ec7388d982d73/drivers/input/touchscreen/nt36523/nt36xxx.c)). Le parseur portable [`lab/nabu/nt36523_touch.py`](lab/nabu/nt36523_touch.py) suit maintenant aussi la règle watchdog de cette référence : le marqueur `0xFD/0xFE` doit apparaître sur onze trames consécutives avant de demander une récupération. Six tests synthétiques passent. Cela valide seulement le décodage logiciel; aucun accès SPI macOS, événement IOHID, écran tactile ou démarrage sur la tablette n'a été testé. Le tactile natif reste non fonctionnel tant que le pilote SPI et le pont IOHID macOS 27.3 ne sont pas intégrés.

**Pile tactile macOS (14 novembre 2026).** [`lab/nabu/touch/`](lab/nabu/touch/) contient une implémentation indépendante, en C portable : protocole SPI du NT36523 (sélection de page, lecture avec octet factice, informations firmware, rapports de 65 octets, surveillance), moteur SPI GENI en mode FIFO, et descripteur HID multitouch de dix contacts. Le kext [`NabuNT36523HID`](lab/nabu/touch/kext/NabuNT36523HID.cpp) se branche sur IOHIDFamily par héritage C++ normal de `IOHIDDevice` : c'est le compilateur qui place les entrées de vtable pour le SDK utilisé, sans numéro de slot écrit à la main. Faits matériels utilisés : moteur QUPv3 wrapper 2 SE1 à `0x00C84000` (GIC SPI 583, GPIO 23 à 26), SPI mode 0 à 9,6 MHz, interruption tactile sur la GPIO 39 du TLMM. Manque encore, dans l'ordre : le téléversement du firmware du contrôleur à la mise sous tension (blob Xiaomi, à extraire de la tablette), l'horloge GCC du moteur série et le multiplexage des broches, l'alimentation, et un contrôleur d'interruptions GPIO (TLMM/PDC). En attendant ce dernier, le kext interroge le contrôleur par minuterie. Rien n'a tourné sur la tablette.


L'outil [`lab/compat/inspect_iohid_vtable.py`](lab/compat/inspect_iohid_vtable.py) décode les chaînes de pointeurs du kernelcache sans le modifier. Son test synthétique couvre les pointeurs format 8 authentifiés. Le résultat [`lab/results/macos27-iohid-vtable-report.json`](lab/results/macos27-iohid-vtable-report.json) ne contient que des adresses, des noms de symboles et des métadonnées de fixup; aucun code Apple n'est copié.

## Port nabu existant : référence, pas solution macOS 27.3

Le port public [Lux12138/unixnu-nabu](https://github.com/Lux12138/unixnu-nabu) est configuré sur iPadOS 17.7.11 (`21H461`, `iPad7,1`). Son état daté du 28 octobre 2026 indique que XNU atteint SpringBoard et les services utilisateur; il reste un provider d'affichage à attacher. Le port utilise une Pad 5 modifiée à 12 Gio. La tablette mesurée dans ce dépôt expose `MemTotal = 5 633 852 kio`; ses réglages mémoire ne peuvent donc pas être repris tels quels. Cette avancée confirme qu'une chaîne UEFI/XNU nabu est possible sur cette famille, mais elle ne constitue pas un démarrage de macOS 27.3.

UniXNU précise par ailleurs que les profils macOS 27 sont arm64e et nécessitent du PAC natif ([prérequis arm64e](https://unixnu.com/porting/arm64e)). Les mesures de cette Pad 5 montrent l'absence de PAC sur huit cœurs. Le noyau nabu arm64 compilé contient une émulation logicielle, mais elle n'a pas encore été validée avec le kernelcache macOS 27.3 ni sur la tablette; le port iPadOS 17.7.11 ne ferme pas cet écart.

## Travail restant vers le démarrage natif

1. Obtenir une compilation NABU complète (la CI la relance à chaque changement de série) et scanner le noyau produit avec `scan_isa_level.py`.
2. Construire l'artefact amorçable : chaîne Mu UEFI et DarwinBoot (référence `Lux12138/unixnu-nabu`), arbre ADT nabu, kernelcache combinant ce noyau et les kexts du 27.3. Mesurer d'abord, en local sur le kernelcache 27.3, les instructions hors ARMv8.2 avec `scan_isa_level.py` et les symboles du kext tactile avec `check_kext_symbols.py`.
3. Ajouter un `IOInterruptController` pour les SPI du GIC, puis un pilote TLMM/PDC pour les GPIO.
4. Affichage : aucun pilote d'écran nabu n'existe pour XNU (le port iOS 16 de référence est bloqué au même endroit, `IOMobileFramebuffer`).
5. Tactile : téléversement du firmware NT36523, horloges, broches et alimentation (voir plus haut).
6. Wi-Fi : démarrage du modem, SMEM/GLINK/QRTR, poignée de main WLFW, moteurs de copie, puis interface réseau macOS (voir `lab/nabu/wifi/WIFI.md`).
7. Valider l'image et un chemin de retour (sauvegarde `outputs/pad5-backup-20261113`, image Android d'origine) **avant** tout déverrouillage ou flash. Le déverrouillage Xiaomi passe par le compte de l'utilisateur et l'outil Mi Unlock, avec le délai imposé par Xiaomi.

L'objectif reste macOS natif. Les essais Sonoma en QEMU sont de l'historique et ne constituent pas une installation macOS 27.3.
