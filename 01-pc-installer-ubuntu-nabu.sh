#!/usr/bin/env bash
# =============================================================================
#  Étape 1 (à lancer sur le PC, Linux ou macOS) : installer Ubuntu 26.04 LTS
#  sur la Xiaomi Pad 5 (nabu, SM8150-AC / Snapdragon 860).
#
#  Source : https://github.com/Kumar-Jy/xiaomi-nabu-ubuntu  (release 08/11/2026,
#  noyau 7.3.3-krjy, GPU Adreno 640 accéléré via Mesa Turnip/Freedreno).
#
#  PRÉREQUIS
#   - Bootloader déverrouillé (Mi Unlock, délai Xiaomi de 7 jours en général).
#   - Sauvegarde complète : le mode "single" EFFACE Android (userdata).
#   - fastboot + adb installés (android-tools / platform-tools), câble USB-C.
#   - Batterie > 50 %.
#
#  MODES
#   single : Ubuntu seul (le plus simple, pas de repartitionnement) — efface MIUI.
#   dual   : Android + Ubuntu. Il faut D'ABORD créer les partitions "linux" et
#            "esp" avec le TWRP modifié (voir fonction dual_prepare_instructions).
# =============================================================================
set -euo pipefail

MODE="${1:-}"
WORK="${WORK:-$HOME/nabu-ubuntu}"
REL="https://github.com/Kumar-Jy/xiaomi-nabu-ubuntu/releases/download/ubuntu-nabu"
NIGHTLY="https://nightly.link/Kumar-Jy/xiaomi-nabu-ubuntu/workflows/build/main/ubuntu-nabu-installer.zip"
TWRP="https://github.com/Kumar-Jy/twrp_device_xiaomi_nabu/releases/tag/mod-hybrid"

usage() {
  cat <<USAGE
Usage : $0 single | dual | download

  download : télécharge seulement l'installeur et alohauefi.img dans $WORK
  single   : flashe Ubuntu seul (efface Android)
  dual     : flashe Ubuntu dans les partitions linux/esp (Android conservé)
USAGE
  exit 1
}

need() { command -v "$1" >/dev/null 2>&1 || { echo "Il manque : $1"; exit 1; }; }

download() {
  need curl; need unzip
  mkdir -p "$WORK"; cd "$WORK"
  echo ">> Téléchargement de l'installeur Ubuntu nabu (plusieurs Go)…"
  [ -f ubuntu-nabu-installer.zip ] || curl -L --fail --retry 4 -o ubuntu-nabu-installer.zip "$NIGHTLY"
  [ -f alohauefi.img ] || curl -L --fail --retry 4 -o alohauefi.img "$REL/alohauefi.img"
  [ -d images ] || unzip -o ubuntu-nabu-installer.zip
  echo ">> Contenu :"; ls -la "$WORK" "$WORK/images" 2>/dev/null || true
}

wait_fastboot() {
  need fastboot
  echo ">> Mets la tablette en mode Fastboot : éteinte, puis Power + Volume BAS."
  until fastboot devices | grep -q .; do sleep 2; done
  echo ">> Appareil détecté : $(fastboot devices)"
  fastboot getvar product 2>&1 | grep -qi nabu || { echo "Ce n'est pas une nabu, arrêt."; exit 1; }
}

confirm() {
  read -r -p "$1 Tape OUI pour continuer : " a; [ "$a" = "OUI" ] || { echo "Annulé."; exit 1; }
}

flash_single() {
  download; wait_fastboot
  confirm "ATTENTION : cela EFFACE Android et toutes les données."
  cd "$WORK"
  fastboot flash boot_ab images/alohauefi.img 2>/dev/null || fastboot flash boot images/alohauefi.img
  fastboot flash cust    images/esp.img
  fastboot flash userdata images/rootfs.img
  fastboot reboot
  echo ">> Premier démarrage : assistant GNOME (langue, Wi-Fi, utilisateur)."
}

dual_prepare_instructions() {
  cat <<TXT
>> Préparation dual-boot (une seule fois) :
   1. Télécharge le TWRP modifié "mod-hybrid" : $TWRP
   2. fastboot boot twrp.img
   3. Dans TWRP : Advanced > Terminal, tape :  partition
      puis choisis la disposition "Dual-boot (Android + Ubuntu)".
   4. Reboot > Recovery, puis reviens en Fastboot et relance :  $0 dual
TXT
}

flash_dual() {
  download; wait_fastboot
  if ! fastboot getvar partition-type:linux 2>&1 | grep -qi "partition-type"; then
    dual_prepare_instructions; exit 1
  fi
  confirm "Flash d'Ubuntu dans les partitions linux + esp (Android conservé)."
  cd "$WORK"
  fastboot flash esp   images/esp.img
  fastboot flash linux images/rootfs.img
  fastboot reboot
  cat <<TXT
>> Le menu rEFInd apparaît au démarrage : Android ou Ubuntu.
   Si Android ne démarre plus : flashe l'installeur ZIP depuis TWRP (méthode A
   du README), elle patche le boot Android avec DualBootKernelPatcher.
TXT
}

case "$MODE" in
  download) download ;;
  single)   flash_single ;;
  dual)     flash_dual ;;
  *) usage ;;
esac
