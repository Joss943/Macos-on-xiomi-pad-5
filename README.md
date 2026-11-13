# macOS sur Xiaomi Pad 5 (nabu, Snapdragon 860 / SM8150-AC)

Recherche prioritaire : démarrer macOS Sonoma directement sur la Pad 5. La version courante est Sonoma 14.8.9. Les seuls essais macOS déjà consignés dans ce dépôt sont des démarrages QEMU/TCG jusqu'à Recovery; **aucune image native Sonoma n'existe encore et rien n'a été flashé sur la tablette**.

Le bootloader de la tablette était verrouillé lors de la dernière lecture ADB. Une copie locale du stockage partagé a été vérifiée avant toute écriture. Elle ne remplace pas une sauvegarde brute des partitions Android; ne lance pas les commandes `single`, `fastboot flashing unlock` ou un script de flash sans image native installable et procédure de retour arrière vérifiée. Le suivi et les résultats mesurés sont dans [NATIF-SONOMA.md](NATIF-SONOMA.md).

## Conclusion en 30 secondes

| Objectif | Faisable ? | Comment |
|---|---|---|
| macOS Sonoma **natif** sur nabu | **Non démarré** | Aucun profil ou image Sonoma native prêt à installer n'a été trouvé pour la Pad 5. Voir [NATIF-SONOMA.md](NATIF-SONOMA.md); les essais QEMU ne constituent pas une installation native. |
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
| `lab/compat/arm64e_pauth.py` | PC | Première table de traductions PAC/PAUTH; formes inconnues refusées. |

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

## État du port natif Sonoma

1. Les essais Sonoma décrits ici utilisent QEMU/TCG et un CPU Intel émulé; ils ne démarrent pas macOS directement sur le Snapdragon.
2. Aucun profil ou paquet macOS Sonoma prêt pour nabu n'a été trouvé.
3. Le projet UniXNU-nabu vise iPadOS 17.7, pas macOS; il reste hors du périmètre de ce dépôt.
4. Le seul port XNU public pour nabu trouvé vise l'espace utilisateur iPadOS 17.7; le Wi-Fi y est encore indiqué comme non implémenté.
5. ADB a mesuré l'absence des indicateurs PAC `paca`/`pacg` sur les huit cœurs; cela constitue un verrou arm64e à étudier, pas encore une preuve tirée des registres CPU.

Voir [NATIF-SONOMA.md](NATIF-SONOMA.md) pour les mesures, la sauvegarde et les verrous de démarrage. macOS 27 Golden Gate est une autre cible; elle n'est pas installable sur nabu par simple remplacement de Sonoma.

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
