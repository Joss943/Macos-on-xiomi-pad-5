# Chaîne de démarrage macOS 27.3 sur nabu : état et plan

Objectif : démarrer le noyau nabu de ce dépôt avec l'espace utilisateur de macOS 27.3 (26C5035r) sur la Xiaomi Pad 5. Ce document sépare ce qui est **vérifié**, ce qui est **connu chez d'autres ports**, et ce qui **reste à faire**. Aucune étape ne s'appuie sur un contournement du verrou Xiaomi ou d'une protection Apple.

## La chaîne (référence : UniXNU, `docs/concepts/boot-chain.md`)

| Étape | Rôle | État pour ce dépôt |
|---|---|---|
| 1. Bootloader Xiaomi → UEFI | Le bootloader charge un firmware UEFI | Non testé ici. Exige le **bootloader déverrouillé** ([MI-UNLOCK.md](MI-UNLOCK.md)) |
| 2. UEFI → UniXNU | `UniXNU.efi` lit `\EFI\UniXNU\unixnu.toml` sur l'ESP, charge les pilotes, construit le menu | Non testé ici |
| 3. UniXNU → DarwinBoot | Device tree, ramdisk, arguments, kexts | Non testé ici |
| 4. DarwinBoot → XNU | Charge `kernel.macho`, `kernel.macho.adt`, `kernel.macho.trustcache`, saute à l'entrée en EL1 | Non testé ici |
| 5. XNU → launchd | Plateforme, stockage, montage racine, launchd | Non testé ici |

### Ce que d'autres ports nabu ont déjà démontré

La fiche UniXNU `nabu-zzweiqing.toml` (profil **iPadOS 17.7 21H16, arm64**) documente sur une vraie Pad 5 :

- l'UEFI Xiaomi d'origine, rEFInd sur une ESP de 334 Mio, `UniXNU.efi` et `DarwinBoot.efi` dans `/EFI/UniXNU` ;
- le transfert DarwinBoot → XNU, une fenêtre contiguë de 1 Gio et le framebuffer 1600×2560 ;
- 8 cœurs Kryo 485 avec IPI SGI, des fenêtres racine UFS, le tactile NT36523, l'affichage A640 et SpringBoard interactif.

Les étapes 1 à 5 sont donc réalisables sur ce matériel. Le port `Lux12138/unixnu-nabu` (copie locale `work/unixnu-nabu-lux12138`) s'arrête à « launchd exec returns ENOENT ».

## Ce que ce dépôt a vérifié (14 novembre 2026)

| Niveau | État |
|---|---|
| Noyau XNU 12377 nabu (série 0001–0009) | Compile en CI. Split-seg vérifié, 0 instruction PAC |
| Prélink macOS 27.3, racine APFS | **0 référence manquante, 0 stub** (build 0009, run 26) |
| Kernelcache candidat écrit | **Oui, fermeture APFS seulement**, `5c57b034…`, non qualifié (étape A franchie) |
| ADT (device tree) Mac17,11 pour nabu | Non commencé |
| Trust caches, payload ESP, userdata macOS | Non commencés |
| Démarrage sur la tablette | Aucun |

## Le risque principal : macOS 27 est arm64e

UniXNU réserve ses profils arm64e (iPadOS 27, macOS 27.3) aux processeurs dotés du **PAC matériel** (`docs/porting/arm64e.md`). Le Kryo 485 est en ARMv8.2 et n'en a pas. Les ports nabu qui démarrent utilisent donc un profil arm64 (iPadOS 17). Ce dépôt tente l'émulation (patch 0002). Mais tout l'espace utilisateur de macOS 27 est en arm64e :

- les instructions PAC de l'espace « hint » (`PACIASP`, `AUTIASP`) s'exécutent comme des NOP sur ARMv8.2 ;
- les autres (`RETAA`, `BLRAA`, `LDRAA`…) sont indéfinies et doivent être émulées par trappe, une par exécution.

Aucun démarrage de macOS 27 sur un processeur sans PAC n'est connu. C'est une **inconnue de faisabilité**, pas un simple travail restant. La première chose à mesurer est le coût de ces trappes au démarrage de launchd.

## Plan, dans l'ordre

Chaque étape a un critère de réussite vérifiable. Aucune n'écrit sur la tablette avant l'étape F.

| # | Étape | Critère |
|---|---|---|
| A | Build CI de la série 0001–0009, puis émission stricte APFS | 0 référence non résolue, kernelcache candidat écrit et marqué non qualifié |
| B | Fermeture complète de démarrage macOS (racines du profil UniXNU `macos-27.3-26C5035r`) | Placement `__PRELINK_TEXT` réussi (il manquait 0x188680 octets contre 0x138000 libres) et 0 référence manquante |
| C | ADT Mac17,11 adapté à nabu (`/cpus`, `/arm-io`, `/chosen`, UFS, framebuffer), d'après `dts/nabu.dts` des ports existants | DarwinBoot accepte `kernel.macho.adt`, validation hors tablette |
| D | Payload ESP : `UniXNU.efi`, `DarwinBoot.efi`, `unixnu.toml`, kernelcache, ADT, trust cache | Démarrage complet sous QEMU (`docs/porting/bring-up.md`, « QEMU before hardware ») jusqu'au panic attendu « pas de stockage » |
| E | Userdata macOS (OS, SystemOS, App, seed Data) | `build userdata --dry-run` cohérent avec la capacité UFS |
| F | Sur la tablette **déverrouillée et sauvegardée** : `fastboot boot` d'abord (rien n'est écrit), puis l'ESP | Journal XNU visible à l'écran (`vc-text=1`) ou relu depuis l'ESP |
| G | launchd, puis WindowServer | Mesure du coût de l'émulation PAC, puis fenêtre de connexion |

Les étapes A à E se font sans la tablette. F demande le déverrouillage. G décidera de la faisabilité réelle.

## Remarques

- `fastboot boot <image>` démarre une image **sans l'écrire** : c'est le premier essai à privilégier. En cas d'échec, un redémarrage rend la tablette dans son état précédent.
- Les pilotes tactile (`lab/nabu/touch/`) et Wi-Fi (`lab/nabu/wifi/`) ne sont validés qu'en tests hors matériel.
