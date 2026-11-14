# macOS 27.3 sur Xiaomi Pad 5 (nabu, Snapdragon 860 / SM8150)

**Cible unique : démarrer macOS 27.3 (26C5035r) nativement sur la Pad 5.** UniXNU construit actuellement ce profil à partir de XNU 12377.121.6 et prélinke le kernelcache 27.3. Le SM8150 ne présente pas de PAC matériel. La série locale explore un kernel ARM64 avec émulation PAC ; elle s'applique à XNU 12377 et sa compilation réelle tourne en CI sur macOS (le témoin non patché compile ; la série NABU a fait apparaître des erreurs corrigées depuis). Rien n'a démarré. Aucun flash n'a été effectué. Voir [NATIF-MACOS-27.md](NATIF-MACOS-27.md) pour les mesures et les blocages.

Le bootloader est toujours verrouillé (`ro.boot.flash.locked=1`). Aucune partition n'a été modifiée. Les essais Sonoma via QEMU décrits dans [NATIF-SONOMA.md](NATIF-SONOMA.md) sont historiques et ne constituent pas un port natif.

## Conclusion en 30 secondes

| Objectif | Faisable ? | Comment |
|---|---|---|
| macOS 27.3 **natif** sur nabu | **Non démarré; patches expérimentaux** | Le profil public cible le kernelcache 27.3 avec XNU 12377 comme base. Le PAC logiciel, le démarrage PSCI, les pilotes tactiles et Wi-Fi restent non validés. Voir [NATIF-MACOS-27.md](NATIF-MACOS-27.md). |
| Linux sur la Pad 5 (référence matérielle seulement) | **Oui** | Un port communautaire Ubuntu documente les pilotes et l'état du matériel nabu; ce n'est pas l'objectif d'installation de ce dépôt. |
| macOS **en VM émulée** | **Recovery testée; installation inachevée** | QEMU + TCG + OpenCore. Catalina atteint Utilities et Sonoma atteint Recovery dans le labo x86-64; le téléchargement/install n'a pas été terminé et aucun test sur Pad 5 n'est consigné. |
| macOS **ARM (Apple Silicon) en VM** | **Pas validé** | La Pad 5 expose 6 Go de RAM et n'expose pas `paca`/`pacg` dans Android; aucune VM Apple Silicon n'a été validée sur elle. |
| macOS **fluide au quotidien** sur l'écran de la Pad 5 | **Oui** | Déport d'écran vers un vrai Mac ou un Mac mini loué dans le cloud. |

## Contenu du dépôt

| Fichier | Où le lancer | Rôle |
|---|---|---|
| `01-pc-installer-ubuntu-nabu.sh` | PC (Linux/macOS) | Installe Ubuntu 26.04 sur la tablette (`single` ou `dual` avec Android). |
| `02-tablette-macos-vm.sh` | Tablette, sous Ubuntu | Télécharge macOS chez Apple, prépare OpenCore, génère `run-macos.sh` réglé pour l'émulation. Choisit le CPU émulé selon la version (`sonoma`, `catalina`, …). |
| `03-tablette-look-macos.sh` | Tablette | Habille Ubuntu en macOS (natif, accéléré GPU). Réversible. |
| `04-tablette-mac-distant.sh` | Tablette | Remmina + RustDesk pour afficher un vrai Mac sur la Pad 5. |
| `lab/get_recovery.sh` | Labo | Téléchargement d'une image de récupération Apple sans Mac (protocole Internet Recovery). |
| `lab/ctl.py` | Labo | Pilotage d'une VM QEMU sans écran (captures, clavier, souris) via le moniteur. |
| `lab/compat/xar_extract.py` | PC | Lecture/extraction XAR contrôlée avec vérification des checksums du TOC et des membres. |
| `lab/compat/pbzx_extract.py` | PC | Décodage des blocs XZ/raw `pbzx` utilisés dans les paquets Apple. |
| `lab/compat/inspect_macho_arch.py` | PC | Inventaire des tranches Mach-O `arm64` et `arm64e`. |
| `lab/compat/arm64e_pauth.py` | PC | Traduit des formes PAC/PAUTH, dont PACIASP/AUTIASP et certains LDRAA/LDRAB; cas risqués refusés. |
| `lab/compat/scan_arm64e_pauth.py` | PC | Repère les instructions PAC connues dans les régions exécutables d'un Mach-O `arm64e`, sans modifier le fichier. |
| `lab/compat/macho_codesign.py` | PC | Recalcule plusieurs CodeDirectories SHA-1/SHA-256, retire l'enveloppe CMS et vérifie les pages d'un Mach-O signé; ne construit pas d'image amorçable. |
| `lab/compat/rewrite_macho_pauth.py` | PC | Réécriture arm64e de largeur fixe avec rafraîchissement de signature; refuse les formes PAC qui exigent relocalisation ou sont inconnues. |
| `lab/probe_nabu_macos27.ps1` | PC Windows avec ADB | Collecte les indicateurs PAC Linux, MIDR, propriétés SoC et verrouillage du bootloader en lecture seule. |
| `lab/nabu/build_arm64e_probe.py`, `lab/nabu/run_arm64e_probe.py` | PC avec ADB | Génère et exécute sur chaque cœur les tests EL0 des instructions PAC et des registres ID_AA64ISAR. |
| `lab/results/nabu-macos27-pac.json` | Résultat matériel | Valeurs PAC lues et échecs PACIA observés sur les huit cœurs; numéro de série omis. |
| `lab/results/nabu-macos27-radio-hardware.json` | Matériel radio nabu | Nœuds radio observés par ADB en lecture seule ; `wlan0` est rattaché à `icnss@18800000`, le WLAN intégré WCN3990 (le nœud QCA6390 est générique et inactif, voir `lab/nabu/wifi/WIFI.md`). |
| `lab/results/macos27-kernelcache-pac-scan-summary.json` | Résultat du kernelcache 27.3 | Hash vérifié, comptage PAC, expansions et segments non couverts; aucun binaire Apple inclus. |
| `lab/compat/inspect_iohid_vtable.py` | Analyse IOHID 27.3 | Mesure la vtable `IOHIDDevice`, décode ses fixups du kernelcache racine et associe les pointeurs aux symboles exacts sans modifier l'IPSW. |
| `lab/results/macos27-iohid-vtable-report.json` | Résultat du tactile 27.3 | 334 slots fonctionnels authentifiés IA, une cellule nulle de fin, et 334 noms exacts retrouvés dans les 370 membres du kernelcache. `handleStart` est au slot 272 et `handleReport` au slot 285 (référence iPadOS 17.7 : slots 168/181). |
| `lab/compat/scan_kernelcache_fixups.py` | Analyse PAC 27.3 | Parcourt les chaînes format 8 et résout les cibles niveau 0 sans réécrire le kernelcache. |
| `lab/results/macos27-kernelcache-fixup-summary.json` | Résultat des fixups 27.3 | 898 429 pointeurs authentifiés sur 1 017 384 entrées; les clés IA et DA sont comptées par segment. |
| `lab/results/macos27-kernelcache-fixup-resolution.json` | Résolution des fixups 27.3 | Les 1 017 384 cibles sont résolues au niveau 0 et retombent dans les segments racine; aucun pointeur n'est réécrit. |
| `lab/compat/patches/xnu-12377/0001-accept-authenticated-fixups-without-pac.patch` | XNU 27.3 / nabu | Le chemin XNU sans PAC stocke les VA résolues comme pointeurs ordinaires au lieu d'arrêter sur les 898 429 fixups authentifiés; il ne simule pas les instructions PAC. Le patch n'a pas encore été compilé ni démarré. |
| `lab/compat/nabu_pauth_emu.h` | Modèle PAC ARM64 sans PAC | Décode et exécute en C les instructions PAC non-HINT, branches et chargements authentifiés pour le chemin de trappe XNU. |
| `lab/compat/patches/xnu-12377/0002-emulate-pauth-el0-el1-without-pac.patch` | XNU 27.3 / nabu | Ajoute l'émulation PAC à EL0 et EL1, activée par défaut sous la carte `NABU`; la série nabu est compilée et liée en noyau arm64 par la CI, sans validation de démarrage. |
| `lab/compat/patches/xnu-12377/0003-nabu-sm8150-machine-and-gic.patch` | XNU 27.3 / nabu | Ajoute la config SM8150, GICv3 Group 1, le timer 19, SGI 1 et le rangement des affinités CPU; appliqué à blanc, pas compilé. |
| `lab/compat/patches/xnu-12377/0004-nabu-psci-smp-and-platform-expert.patch` | XNU 27.3 / nabu | Ajoute l'ADT, le driver `IOCPU`, PSCI `CPU_ON` via SMC et le trampoline EL2→EL1. La série compile et lie un noyau arm64 en CI; PSCI et le démarrage restent à valider. |
| `lab/compat/patches/xnu-12377/0005-macos27-coreentitlements-stack-shift.patch` | Prélink macOS 27.3 | Fournit à AMFI l'alignement de pile nabu de 8 Kio (`shift=13`); rebuild CI en cours. |
| `lab/compat/patches/unixnu/nabu-machine-flags.patch` | UniXNU build | Permet au build XNU de remplacer les flags de carte de référence par les flags nabu tout en conservant ses chemins d'artefacts existants. |
| `lab/nabu/macos-27.3/arm64-machine.config` | Fragment build nabu | Sélectionne `ARM64_BOARD_CONFIG_NABU` et ARMv8.2 pour le noyau expérimental. |
| `lab/compat/test_nabu_pauth_emu.c` | Fixture C portable | 13 scénarios et les 1 024 immédiats LDRA compilés et exécutés sur l'hôte avec Zig/Clang; ce n'est pas un test de démarrage XNU. |
| `lab/results/macos27-pauth-emulator-fixtures.json` | Résultat fixture | Résume les cas passés et les validations qui restent à faire. |
| `lab/compat/patches/unixnu/nabu-macos27-arm64-profile.patch` | UniXNU resolver | Permet à l'override macOS 27.3 du seul appareil nabu de sélectionner ARM64 sans changer le profil Mac général. |
| `lab/nabu/macos-27.3/arm64-override.toml` | Fragment profil nabu | Sélectionne ARM64 dans l'override de macOS 27.3, nécessaire au Snapdragon 860 sans PAC. |
| `lab/nabu/nt36523_touch.py` | PC | Décode les rapports multitouch SPI du contrôleur Novatek NT36523; ce n'est pas encore son pilote macOS. |
| `lab/nabu/touch/` | Kext macOS / tests hôte | Pile tactile indépendante : protocole NT36523, moteur SPI GENI, HID multitouch, kext `NabuNT36523HID`. Compilé et lié contre le SDK 26.2 en CI ; non testé sur la tablette. |
| `lab/nabu/wifi/` | Étude et code | Réidentification du Wi-Fi (WCN3990 intégré), codec QRTR/QMI indépendant et premier message WLFW, testés octet par octet. |
| `lab/compat/xnu-build/` | CI / Mac | Application épinglée de la série XNU et résumé des journaux de compilation. |
| `lab/compat/scan_isa_level.py` | PC | Compte les instructions qu'un cœur Kryo 485 ne peut pas exécuter (PAC non-HINT, ARMv8.3+, registres système Apple). |
| `lab/compat/check_kext_symbols.py` | PC | Vérifie que chaque symbole importé par un kext existe dans un kernelcache fileset (à lancer sur le 27.3 local). |
| `.github/workflows/xnu-build.yml` | CI macOS | Compile XNU 12377 avec et sans la série nabu, avec un témoin VMAPPLE. |
| `.github/workflows/touch-kext.yml` | CI | Tests hôte du tactile, compilation du kext et résolution de ses symboles. |

Captures des tests (OpenCore, Catalina Recovery et Utilities, Sonoma Recovery) : dossier `xiaomi-pad5-macos/` du dépôt `fedora-config`, branche `ccr-475fd790-4b2n9n`.

---

## Procédure expérimentale : macOS Sonoma en VM via QEMU

Cette procédure démarre une VM et n'installe pas macOS en natif. Le script `01-pc-installer-ubuntu-nabu.sh` installe Linux; son mode `single` efface Android et ne doit pas être utilisé comme installateur Sonoma.

Cette procédure décrit une tentative depuis Ubuntu sur la tablette. Les tests consignés ont seulement validé Recovery sur un hôte x86-64 de labo; l'installation complète et les timings ci-dessous ne sont pas validés sur la Pad 5.

### Étape 0. Prérequis

- Xiaomi Pad 5 (nabu) **bootloader déverrouillé** (Mi Unlock, compte Xiaomi, attente d'environ 7 jours). Sauvegarde complète : le mode `single` efface Android.
- PC avec `adb`/`fastboot`, câble USB-C, batterie > 50 %.
- Pour Sonoma : la VM a besoin de **4 Go de RAM**. Sur une Pad 5 à 6 Go, Ubuntu doit rester léger pendant l'installation (fermer le navigateur, pas d'autres applications). Catalina se contente de 3 Go et reste le choix le plus confortable.
- Wi-Fi fonctionnel sous Ubuntu : la réinstallation télécharge environ 12 Go depuis les serveurs Apple.

### Étape 1. Ubuntu 26.04 sur la tablette (sur le PC)

```bash
chmod +x 01-pc-installer-ubuntu-nabu.sh
./01-pc-installer-ubuntu-nabu.sh single   # Ubuntu seul (efface Android)
./01-pc-installer-ubuntu-nabu.sh dual     # Android conservé (partitions linux/esp via TWRP mod-hybrid d'abord)
```

Équivalent manuel du mode `single` (tablette en Fastboot, Power + Volume bas) :

```bash
fastboot flash boot_ab images/alohauefi.img
fastboot flash cust    images/esp.img
fastboot flash userdata images/rootfs.img
fastboot reboot
```

Premier démarrage : assistant GNOME, Wi-Fi, utilisateur. Puis `sudo apt update && sudo apt upgrade`.

État matériel sous Ubuntu (release du 08/11/2026) : écran 120 Hz, tactile, stylet, GPU Vulkan/OpenGL, Wi-Fi, Bluetooth, son, batterie, veille, USB-C OTG : OK. Caméras : pas de pilote. DisplayPort USB-C : impossible (matériel).

### Étape 2. Créer la VM Sonoma (sur la tablette)

```bash
chmod +x 02-tablette-macos-vm.sh
./02-tablette-macos-vm.sh sonoma
```

Le script : installe `qemu-system-x86`, `dmg2img`, `zram-tools` (zram à 50 %) ; clone OSX-KVM (OpenCore + OVMF) ; télécharge `BaseSystem.dmg` de Sonoma chez Apple avec `fetch-macOS-v2.py -s sonoma` ; le convertit en `.img` ; crée un disque qcow2 de 64 Go ; génère `run-macos.sh` avec :

- `-accel tcg,thread=multi` : les 4 gros cœurs A76 traduisent en parallèle ;
- `-cpu Skylake-Client,-hle,-rtm,…,+pclmulqdq` : Sonoma exige AVX2 (Skylake) ; `+pclmulqdq` est **indispensable** en émulation (voir « Le piège ») ;
- `-m 4096`, `q35`, `isa-applesmc`, OpenCore sur SATA, carte réseau Intel `e1000-82545em` (pilote Apple intégré), affichage `vmware-svga` 1024x768.

### Étape 3. Démarrer l'installeur

```bash
~/macos-vm/OSX-KVM/run-macos.sh
```

1. Menu OpenCore : flèche droite jusqu'à **macOS Base System**, Entrée.
2. Pomme et barre de progression. En émulation sur la Pad 5 : 15 à 40 minutes jusqu'à l'écran **Recovery** (Restore from Time Machine / Reinstall macOS Sonoma / Safari / Disk Utility).

Mesuré en émulation pure sur un hôte x86 4 cœurs sans KVM : noyau Darwin 23.6.0 lancé à 1 min, espace utilisateur à 4 min, écran Recovery complet à 16 min. Pour la Pad 5 ARM, le dépôt estime 2 à 3 fois plus longtemps; ce facteur n'a pas été mesuré sur la tablette.

### Étape 4. Formater le disque virtuel en APFS

Deux façons.

**Utilitaire de disque (souris)** : Disk Utility, Continue, menu Présentation, « Afficher tous les appareils », sélectionner **QEMU HARDDISK** 68,7 Go, Effacer, nom `macOS`, format **APFS**, schéma **Table de partition GUID**, Effacer, Terminé, fermer la fenêtre.

**Terminal (clavier seul, plus fiable en émulation)** : menu Utilities, Terminal, puis

```bash
diskutil list physical            # repérer le disque QEMU HARDDISK de 68.7 GB (en général disk0)
diskutil eraseDisk APFS macOS GPT disk0
exit
```

### Étape 5. Réinstaller macOS Sonoma

1. Dans la fenêtre Recovery : **Reinstall macOS Sonoma**, Continue, Agree, Agree.
2. Choisir le volume **macOS**, Install.
3. Téléchargement d'environ 12 Go depuis Apple (`swcdn.apple.com`, `swscan.apple.com`), puis copie sur le disque. La VM redémarre plusieurs fois. À chaque redémarrage, OpenCore propose **macOS Installer** puis, à la fin, **macOS** : laisser le choix par défaut ou sélectionner avec les flèches.
4. Estimation non vérifiée sur la Pad 5 : **4 à 8 heures** en émulation, tablette branchée, écran laissé allumé ou `HEADLESS=1` (voir ci-dessous).

### Étape 6. Après l'installation

```bash
INSTALLED=1 ./run-macos.sh                  # retire le média d'installation
HEADLESS=1 INSTALLED=1 ./run-macos.sh       # sans fenêtre, VNC sur localhost:5901
RAM=3584 INSTALLED=1 ./run-macos.sh         # si Ubuntu swappe trop
```

Assistant de configuration macOS, compte local (pas de compte Apple nécessaire). Activer Partage > Session à distance pour `ssh -p 2222 utilisateur@localhost`.

Attentes : Finder, Terminal et réglages répondent avec des secondes de latence. Pas d'accélération graphique (vidéo, Xcode, jeux : non). C'est une preuve de concept fonctionnelle, pas un poste de travail.

---

## Le piège qui bloque tout le monde en émulation

Avec la ligne `-cpu Penryn` classique d'OSX-KVM, macOS reste figé sur la pomme, sans barre de progression. Le journal série du noyau (`-v debug=0x100 serial=3` dans les `boot-args` d'OpenCore, `-serial file:serial.log` côté QEMU) montre :

```
panic(cpu 0 caller ...): Kernel trap at ..., type 6=invalid opcode
com.apple.kec.corecrypto : _gcm_init + 0x8e
com.apple.kec.corecrypto : _fipspost_post_aes_gcm
```

Dès qu'AES-NI est annoncé, corecrypto utilise **PCLMULQDQ**, absente du modèle Penryn de QEMU. Sous KVM le vrai processeur exécute l'instruction quand même ; sous TCG l'émulateur la refuse. Correction : `+pclmulqdq` dans `-cpu`, ou un modèle qui l'inclut (`Skylake-Client`). Testé un cœur et quatre cœurs : identique.

Deuxième piège : `-cpu max` fait caler `boot.efi` dans le chargement du `prelinkedkernel`. Rester sur Penryn (+pclmulqdq) ou Skylake-Client.

Troisième point : activer le journal série d'OpenCore lui-même (`Misc > Debug > Target = 9`) a rendu l'écran noir dans nos tests. Laisser `Target = 0`, le `-v` du noyau suffit.

## Résultats des tests (émulation pure, hôte x86 4 cœurs sans /dev/kvm)

| Version | CPU émulé | Résultat |
|---|---|---|
| Catalina 10.15.7 | Penryn + pclmulqdq | OpenCore 40 s, noyau à 1 min, launchd à 2 min, « Launching the Language Chooser » à 4 min, fenêtre **macOS Utilities** (Reinstall macOS, Disk Utility) à 17 min. Lien Ethernet e1000 monté. |
| Sonoma 14.6 | Skylake-Client | Noyau Darwin 23.6.0, espace utilisateur à 4 min, écran **Recovery** complet à 16 min, Terminal de récupération ouvert et commandes tapées. |
| Catalina | Penryn (sans pclmulqdq) | Figé sur la pomme : panique corecrypto (voir ci-dessus). |
| Catalina | `-cpu max` | Bloqué dans boot.efi. |

Images téléchargées chez Apple et vérifiées bloc par bloc contre la liste de contrôle signée (Catalina 48/48, Sonoma 76/76).

Où le test s'est arrêté : l'environnement de test n'avait pas d'accès Internet depuis la VM (réseau de laboratoire filtré, DNS indisponible pour le guest), donc « Reinstall macOS Sonoma » ne pouvait pas télécharger le système. Sur la Pad 5 sous Ubuntu, QEMU partage le Wi-Fi de la tablette en NAT et cette étape passe normalement.

## Pourquoi pas plus rapide : pas de KVM sur un Snapdragon grand public

Le firmware Qualcomm démarre Linux en EL1 ; l'hyperviseur Qualcomm occupe EL2. `/dev/kvm` n'existe donc pas, même avec un noyau compilé avec KVM. Le remplacement d'hyperviseur `qhypstub` n'existe que pour MSM8916/8939. Toute VM passe par TCG, 10 à 30 fois plus lent que le natif.

## Anciennes pistes VM (elles ne réalisent pas l'objectif natif)

| Voie | Projets | Pourquoi non sur la Pad 5 |
|---|---|---|
| macOS ARM (vmapple) sous KVM | vmapple-cli, reims-vgpu | KVM impossible ; exige aussi Pointer Authentication (ARMv8.3), le Kryo 485 est ARMv8.2. |
| macOS ARM sous TCG | orchard, Ambrosia | 16 Go de RAM hôte, guest 10 Go, GPU Vulkan. Code de recherche. |
| macOS Intel + OpenCore sous TCG | OSX-KVM | Les essais consignés atteignent Recovery seulement; cette VM n'est pas une installation native. |

## Cible native actuelle : macOS 27.3

- Les registres PAC ont été lus directement sur les huit cœurs; les champs PAC sont nuls et PACIA/AUTIA lèvent une instruction illégale.
- Un correctif PAC de référence s'applique au XNU `12377.121.6` après son correctif JSCVT préalable. Il émule des instructions arm64e en mode utilisateur, mais n'a pas encore démontré de démarrage sur l'appareil.
- Le kernelcache officiel Mac17,11 a été vérifié par SHA-256. Le réécriveur actuel s'arrête sur 643 formes nécessitant une relocalisation, 24 formes non prises en charge et 4 segments exécutables qu'il ne couvre pas.
- Aucun noyau macOS 27.3 adapté à nabu n'a été compilé ni démarré. Aucun flash n'a été tenté.

Voir [NATIF-MACOS-27.md](NATIF-MACOS-27.md) pour les mesures, les vérifications XNU et l'avancement. Les essais Sonoma en QEMU dans ce README et [NATIF-SONOMA.md](NATIF-SONOMA.md) restent historiques.

## macOS fluide sur la Pad 5

- `03-tablette-look-macos.sh` : thème WhiteSur, icônes, curseurs, police Inter, dock en bas, boutons à gauche. `revert` pour revenir à Ubuntu.
- `04-tablette-mac-distant.sh` : Remmina (VNC vers le Partage d'écran d'un Mac en local) et RustDesk (à travers Internet). Sans Mac : Mac mini loué (Scaleway, MacStadium, MacinCloud, AWS EC2 Mac).

## Note légale

La licence macOS n'autorise son exécution que sur du matériel Apple, y compris en machine virtuelle. Les images sont téléchargées depuis les serveurs publics d'Apple sans contournement de DRM ; l'usage sur un appareil non-Apple relève de ta responsabilité.

## Sources

- Ubuntu 26.04 nabu : <https://github.com/Kumar-Jy/xiaomi-nabu-ubuntu> (release 08/11/2026) ; port d'origine : <https://github.com/TheMojoMan/Xiaomi-Nabu> ; wiki : <https://linux-on-nabu.gitbook.io/linux-for-mi-pad-5>
- postmarketOS nabu : <https://pkgs.postmarketos.org/package/master/postmarketos/aarch64/device-xiaomi-nabu> ; Arch Linux ARM : <https://github.com/ppanzenboeck/nabu-arch-linux>
- Windows on ARM sur Pad 5 : <https://renegade-project.tech/en/install/>
- EL2/KVM sur Snapdragon : <https://xdaforums.com/t/booting-in-el2-for-kvm-use.4215531/> ; qhypstub : <https://github.com/msm8916-mainline/qhypstub>
- OSX-KVM : <https://github.com/kholia/OSX-KVM> ; macrecovery (OpenCorePkg) : <https://github.com/acidanthera/OpenCorePkg>
- macOS émulé sous TCG : <https://github.com/utmapp/UTM/discussions/4349>
- macOS ARM en VM : <https://github.com/guoPhineas/vmapple-cli>, <https://github.com/yaelliethy/orchard>, <https://github.com/steelbrain/experiment-macOS-arm64-on-linux-x86>, <https://www.qemu.org/docs/master/system/arm/vmapple.html>

