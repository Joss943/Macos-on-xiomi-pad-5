#!/usr/bin/env bash
# =============================================================================
#  Étape 2 (à lancer SUR LA TABLETTE, sous Ubuntu 26.04 arm64) :
#  créer une machine virtuelle macOS (x86-64) émulée avec QEMU/TCG + OpenCore.
#
#  Réalité technique : le Snapdragon 860 est un ARM sans KVM accessible
#  (Linux tourne en EL1, l'hyperviseur Qualcomm occupe EL2). macOS Intel est
#  donc ÉMULÉ instruction par instruction. Ça démarre, mais c'est lent :
#  comptez 2 à 5 min pour OpenCore, 15 à 40 min pour l'installeur, plusieurs
#  heures pour l'installation complète. C'est une preuve de concept.
#
#  Versions testées en émulation pure : Catalina (10.15) et Sonoma (14).
#   - catalina / big-sur / monterey / mojave / high-sierra : CPU "Penryn" émulé.
#   - sonoma / ventura / sequoia / tahoe : exigent AVX2 -> CPU "Skylake-Client"
#     émulé. Plus lourds (4 Go de RAM minimum : sur une Pad 5 à 6 Go, c'est
#     juste). Catalina reste le meilleur compromis pour la tablette.
#
#  Usage :  ./02-tablette-macos-vm.sh [catalina|big-sur|monterey|ventura|sonoma|sequoia|tahoe|mojave|high-sierra]
# =============================================================================
set -euo pipefail
VER="${1:-catalina}"
VM="${VM:-$HOME/macos-vm}"

echo ">> 1/6 Paquets (QEMU x86 émulé, dmg2img, outils)…"
sudo apt-get update -qq
sudo apt-get install -y -qq qemu-system-x86 qemu-utils dmg2img git python3 zram-tools

echo ">> 2/6 zram (compense les 6 Go de RAM de la Pad 5)…"
echo -e "ALGO=zstd\nPERCENT=50" | sudo tee /etc/default/zramswap >/dev/null
sudo systemctl restart zramswap || true

echo ">> 3/6 OSX-KVM (OpenCore + OVMF + script de téléchargement Apple)…"
mkdir -p "$VM"; cd "$VM"
[ -d OSX-KVM ] || git clone --depth 1 --recursive https://github.com/kholia/OSX-KVM.git
cd OSX-KVM

echo ">> 4/6 Image de récupération macOS ($VER) depuis les serveurs Apple…"
# fetch-macOS-v2.py = macrecovery.py d'OpenCorePkg (Acidanthera). -s choisit la version.
[ -f BaseSystem.dmg ] || python3 fetch-macOS-v2.py -s "$VER"
[ -f BaseSystem.img ] || dmg2img -i BaseSystem.dmg BaseSystem.img

echo ">> 5/6 Disque virtuel (qcow2 dynamique, 64 Go max)…"
[ -f mac_hdd_ng.img ] || qemu-img create -f qcow2 mac_hdd_ng.img 64G

case "$VER" in
  sonoma|ventura|sequoia|tahoe) CPUMODEL="Skylake-Client,-hle,-rtm"; DEFRAM=4096 ;;
  *)                            CPUMODEL="Penryn";                   DEFRAM=3072 ;;
esac
# Carte réseau : Intel e1000 (pilote Apple intégré, lien validé sous Catalina en TCG) ;
# virtio-net pour Sequoia/Tahoe qui n'ont plus le pilote Intel 8254x.
case "$VER" in sequoia|tahoe) NIC="virtio-net-pci" ;; *) NIC="e1000-82545em" ;; esac
echo ">> 6/6 Script de lancement optimisé TCG (CPU $CPUMODEL)…"
cat > run-macos.sh <<RUN
#!/usr/bin/env bash
# macOS x86-64 émulé (TCG) sur Xiaomi Pad 5.
# TESTÉ en TCG pur (sans KVM) : l'installeur graphique de Catalina et de Sonoma s'affiche.
# IMPORTANT : "+pclmulqdq" est obligatoire en émulation. Sans lui, corecrypto
# (gcm_init) exécute une instruction absente du modèle Penryn et le noyau
# panique "invalid opcode" juste après "kdp_core zlib memory" (écran figé sur
# la pomme). Sous KVM le vrai CPU masque ce problème, pas sous TCG.
cd "\$(dirname "\$0")"
RAM="\${RAM:-$DEFRAM}"      # MiB. Sur une Pad 5 (6 Go), ne pas dépasser 3 à 4 Go.
CORES="\${CORES:-4}"     # 4 gros cœurs (A76) ; TCG multi-thread les utilise.
INSTALLED="\${INSTALLED:-0}"  # INSTALLED=1 : macOS est installé, on retire l'installeur.
DISPLAY_ARGS=(-display gtk,gl=off,zoom-to-fit=on)
[ "\${HEADLESS:-0}" = 1 ] && DISPLAY_ARGS=(-display none -vnc 127.0.0.1:1)  # VNC sur :5901
INSTALL_ARGS=(-drive id=InstallMedia,if=none,file=BaseSystem.img,format=raw -device ide-hd,bus=sata.3,drive=InstallMedia)
[ "\$INSTALLED" = 1 ] && INSTALL_ARGS=()
exec qemu-system-x86_64 \\
  -accel tcg,thread=multi,tb-size=384 \\
  -m "\$RAM" -smp "\$CORES",cores="\$CORES",sockets=1 \\
  -cpu $CPUMODEL,vendor=GenuineIntel,vmware-cpuid-freq=on,+ssse3,+sse4.2,+popcnt,+avx,+aes,+pclmulqdq,+xsave,+xsaveopt \\
  -machine q35 \\
  -device qemu-xhci,id=xhci -device usb-kbd,bus=xhci.0 -device usb-tablet,bus=xhci.0 \\
  -device isa-applesmc,osk="ourhardworkbythesewordsguardedpleasedontsteal(c)AppleComputerInc" \\
  -drive if=pflash,format=raw,readonly=on,file=OVMF_CODE_4M.fd \\
  -drive if=pflash,format=raw,file=OVMF_VARS-1024x768.fd \\
  -smbios type=2 \\
  -device ich9-ahci,id=sata \\
  -drive id=OpenCoreBoot,if=none,snapshot=on,format=qcow2,file=OpenCore/OpenCore.qcow2 \\
  -device ide-hd,bus=sata.2,drive=OpenCoreBoot \\
  "\${INSTALL_ARGS[@]}" \\
  -drive id=MacHDD,if=none,file=mac_hdd_ng.img,format=qcow2 \\
  -device ide-hd,bus=sata.4,drive=MacHDD \\
  -netdev user,id=net0,hostfwd=tcp::2222-:22 -device $NIC,netdev=net0 \\
  -device vmware-svga \\
  "\${DISPLAY_ARGS[@]}" \\
  -monitor none -serial none \\
  "\$@"
RUN
chmod +x run-macos.sh

cat <<TXT

Terminé. Lancement :   $VM/OSX-KVM/run-macos.sh

Dans la VM :
  1. Menu OpenCore -> "macOS Base System" (installeur).
  2. Utilitaire de disque -> formater "QEMU HARDDISK" 64 Go en APFS, nom "macOS".
     Ou, au Terminal (menu Utilities) :  diskutil eraseDisk APFS macOS GPT disk0
  3. "Reinstall macOS" sur "macOS". Plusieurs redémarrages (choisir ensuite
     "macOS Installer" puis "macOS" dans OpenCore). Comptez plusieurs heures.
  4. Après installation :  INSTALLED=1 ./run-macos.sh  (retire l'installeur).
     Sans écran :  HEADLESS=1 INSTALLED=1 ./run-macos.sh  puis VNC sur localhost:5901.

Astuces :
  - Pas d'accélération graphique dans la VM (vmware-svga logiciel) : garder
    la résolution 1024x768 (OVMF_VARS-1024x768.fd).
  - RAM=2560 ./run-macos.sh  si Ubuntu swappe trop.
  - SSH dans la VM : ssh -p 2222 utilisateur@localhost (activer "Partage
    distant" dans macOS).
TXT
