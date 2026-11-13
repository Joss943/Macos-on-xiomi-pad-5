#!/usr/bin/env bash
# =============================================================================
#  Étape 4 (SUR LA TABLETTE sous Ubuntu) : macOS fluide sur l'écran de la
#  Pad 5 en se connectant à un VRAI Mac (chez toi, ou un Mac mini loué).
#  C'est la seule voie qui donne un macOS utilisable au quotidien.
#
#  Installe Remmina (VNC/RDP, dans les dépôts arm64) et RustDesk (open source,
#  fonctionne à travers Internet sans ouvrir de ports, build arm64 officiel).
#  Usage : ./04-tablette-mac-distant.sh
# =============================================================================
set -euo pipefail

echo ">> Remmina (VNC vers le Partage d'écran macOS, RDP, SSH)…"
sudo apt-get update -qq
sudo apt-get install -y -qq remmina remmina-plugin-vnc remmina-plugin-rdp curl jq

echo ">> RustDesk (dernier .deb arm64 officiel)…"
API="https://api.github.com/repos/rustdesk/rustdesk/releases/latest"
URL="$(curl -fsSL "$API" | jq -r '.assets[].browser_download_url | select(test("aarch64\\.deb$"))' | head -1)"
if [ -n "$URL" ]; then
  TMP="$(mktemp -d)"; curl -fL --retry 3 -o "$TMP/rustdesk.deb" "$URL"
  sudo apt-get install -y "$TMP/rustdesk.deb" || sudo dpkg -i "$TMP/rustdesk.deb" || sudo apt-get -f install -y
  rm -rf "$TMP"
else
  echo "   (pas de .deb arm64 trouvé, voir https://github.com/rustdesk/rustdesk/releases)"
fi

cat <<'TXT'

CÔTÉ MAC (une fois) :
  Réglages Système > Général > Partage > "Partage d'écran" : activer, autoriser
  ton utilisateur, puis "i" > "Les utilisateurs VNC peuvent contrôler l'écran
  avec le mot de passe" : définir un mot de passe.
  Pour l'accès hors du réseau local : installer RustDesk sur le Mac, noter
  l'ID et le mot de passe permanent (Réglages > Sécurité).

CÔTÉ TABLETTE :
  - Réseau local : Remmina > Nouveau profil > Protocole VNC, serveur
    <IP-du-Mac>:5900, qualité "Meilleure", couleur 32 bits. Mode plein écran,
    la Pad 5 affiche le Mac en 2560x1600 avec le tactile comme souris.
  - Hors réseau local : RustDesk > entrer l'ID du Mac.
  - Clavier/souris Bluetooth ou le clavier Xiaomi : reconnus comme sur un Mac.

MAC DANS LE CLOUD (si tu n'as pas de Mac) :
  Mac mini Apple Silicon loués à l'heure ou au mois chez Scaleway (Europe),
  MacStadium, MacinCloud ou AWS EC2 Mac. Connexion identique (VNC/RustDesk).
  C'est la solution standard des développeurs iOS sans Mac.
TXT
