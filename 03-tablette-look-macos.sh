#!/usr/bin/env bash
# =============================================================================
#  Étape 3 (optionnelle, SUR LA TABLETTE sous Ubuntu 26.04 GNOME) :
#  donner à Ubuntu l'apparence et les réflexes de macOS, en NATIF et accéléré
#  par l'Adreno 640. C'est la seule façon d'avoir une interface "macOS" fluide
#  directement sur la Pad 5.
#
#  Installe : thème WhiteSur (GTK, Shell, icônes, curseurs), police Inter,
#  dock en bas façon macOS (Ubuntu Dock), boutons de fenêtre à gauche,
#  GNOME Tweaks + Extension Manager.
#  Réversible : ./03-tablette-look-macos.sh revert
# =============================================================================
set -euo pipefail
SRC="${SRC:-$HOME/.local/src}"

if [ "${1:-}" = "revert" ]; then
  gsettings reset org.gnome.desktop.interface gtk-theme
  gsettings reset org.gnome.desktop.interface icon-theme
  gsettings reset org.gnome.desktop.interface cursor-theme
  gsettings reset org.gnome.desktop.interface font-name
  gsettings reset org.gnome.desktop.wm.preferences button-layout
  gsettings reset org.gnome.shell.extensions.dash-to-dock dock-position
  gsettings reset org.gnome.shell.extensions.dash-to-dock extend-height
  gsettings reset org.gnome.shell.extensions.dash-to-dock dash-max-icon-size
  gsettings reset org.gnome.shell.extensions.dash-to-dock dock-fixed
  gsettings reset org.gnome.shell.extensions.dash-to-dock intellihide
  gsettings reset org.gnome.shell.extensions.dash-to-dock show-apps-at-top
  gsettings reset org.gnome.shell.extensions.user-theme name 2>/dev/null || true
  ( cd "$SRC/WhiteSur-gtk-theme" 2>/dev/null && ./install.sh -r >/dev/null ) || true
  rm -rf ~/.config/gtk-4.0/gtk.css ~/.config/gtk-4.0/assets ~/.config/gtk-4.0/windows-assets
  echo "Apparence Ubuntu restaurée."; exit 0
fi

echo ">> 1/5 Paquets…"
sudo apt-get update -qq
sudo apt-get install -y -qq git sassc libglib2.0-dev-bin gnome-tweaks \
  gnome-shell-extension-manager gnome-shell-extensions fonts-inter \
  gnome-shell-extension-ubuntu-dock

echo ">> 2/5 Thème WhiteSur (GTK + Shell)…"
mkdir -p "$SRC"; cd "$SRC"
[ -d WhiteSur-gtk-theme ] || git clone --depth 1 https://github.com/vinceliuice/WhiteSur-gtk-theme.git
( cd WhiteSur-gtk-theme && ./install.sh -c light -c dark -m -N glassy >/dev/null && ./install.sh -l -c light >/dev/null )
# -m : style Monterey ; second appel -l : applis libadwaita (contournement, non parfait)

echo ">> 3/5 Icônes et curseurs WhiteSur…"
[ -d WhiteSur-icon-theme ] || git clone --depth 1 https://github.com/vinceliuice/WhiteSur-icon-theme.git
( cd WhiteSur-icon-theme && ./install.sh -a >/dev/null )
[ -d WhiteSur-cursors ] || git clone --depth 1 https://github.com/vinceliuice/WhiteSur-cursors.git
( cd WhiteSur-cursors && ./install.sh >/dev/null )

echo ">> 4/5 Réglages GNOME façon macOS…"
gsettings set org.gnome.desktop.interface gtk-theme 'WhiteSur-Light'
gsettings set org.gnome.desktop.interface icon-theme 'WhiteSur'
gsettings set org.gnome.desktop.interface cursor-theme 'WhiteSur-cursors'
gsettings set org.gnome.desktop.interface font-name 'Inter 11'
gsettings set org.gnome.desktop.interface color-scheme 'default'
gsettings set org.gnome.desktop.wm.preferences button-layout 'close,minimize,maximize:'
# Dock en bas, centré, auto-masqué, icônes 56 px, lanceur d'apps à gauche
gsettings set org.gnome.shell.extensions.dash-to-dock dock-position 'BOTTOM'
gsettings set org.gnome.shell.extensions.dash-to-dock extend-height false
gsettings set org.gnome.shell.extensions.dash-to-dock dock-fixed false
gsettings set org.gnome.shell.extensions.dash-to-dock intellihide true
gsettings set org.gnome.shell.extensions.dash-to-dock dash-max-icon-size 56
gsettings set org.gnome.shell.extensions.dash-to-dock show-apps-at-top true
gsettings set org.gnome.shell.extensions.dash-to-dock click-action 'minimize-or-previews'
# Thème Shell (barre du haut) : nécessite l'extension "User Themes"
gnome-extensions enable user-theme@gnome-shell-extensions.gcampax.github.com 2>/dev/null || true
gsettings set org.gnome.shell.extensions.user-theme name 'WhiteSur-Light' 2>/dev/null || true
# Tactile : 3 doigts = vue d'ensemble, natif GNOME. Gestes supplémentaires :
echo "   Extension conseillée (via Extension Manager) : 'Touchpad Gesture Improvements'"

echo ">> 5/5 Fin. Déconnecte-toi / reconnecte-toi pour appliquer le thème Shell."
cat <<TXT
Compléments possibles :
  - Spotlight-like : touche Super puis taper, natif GNOME.
  - Launchpad : bouton "Applications" du dock.
  - Fond d'écran : Paramètres > Apparence (les fonds Apple sont protégés,
    non inclus).
  - Dock plus proche de macOS : extension "Dash to Dock" (Extension Manager)
    remplace Ubuntu Dock avec plus d'options (transparence, animations).
TXT
