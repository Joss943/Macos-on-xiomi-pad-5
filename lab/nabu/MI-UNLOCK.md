# Déverrouiller le bootloader de la Xiaomi Pad 5 (nabu)

Ce guide décrit la seule voie officielle : l'outil Mi Unlock de Xiaomi, avec votre propre compte. Aucune étape ne contourne le verrou. Rien dans ce dépôt ne le fait à votre place.

## État observé le 14 novembre 2026 (adb, lecture seule)

| Propriété | Valeur | Sens |
|---|---|---|
| `ro.product.mod_device` | `nabu_global` | ROM globale |
| `ro.mi.os.version.name` / `incremental` | `OS1.0` / `V816.0.6.0.TKXMIXM` | HyperOS 1.0, Android 13 |
| `ro.boot.flash.locked` | `1` | **Bootloader verrouillé** |
| `ro.secureboot.lockstate` | `locked` | Idem |
| `sys.oem_unlock_allowed` | `1` | « Déverrouillage OEM » déjà autorisé |
| options développeur | activées | |
| `/data` | 56 Go utilisés sur 107 Go | **Tout sera effacé** |

## 0. Sauvegarder (obligatoire)

Le déverrouillage **efface entièrement la tablette**. Copiez sur le PC photos, documents et sauvegardes d'applications. Le script `lab/backup_nabu_shared_storage.ps1` copie le stockage partagé par adb. Vérifiez la copie avant de continuer.

## 1. Associer le compte (sur la tablette)

1. Connectez-vous à votre compte Xiaomi dans Paramètres et activez la synchronisation.
2. Réseau **mobile ou Wi-Fi actif** : l'association passe par les serveurs Xiaomi.
3. Paramètres > Paramètres supplémentaires > Options pour les développeurs > **Statut Mi Unlock** > « Ajouter un compte et un appareil ».
4. Xiaomi impose ensuite un **délai d'attente** (souvent 168 h, parfois plus). Il démarre à l'association. Ne vous déconnectez pas du compte pendant l'attente.

## 2. Déverrouiller (sur le PC, après le délai)

1. Téléchargez Mi Unlock **depuis le site officiel de Xiaomi** et vérifiez la provenance. Le dossier `work/mi-unlock` de ce poste contient une copie récupérée lors d'une session précédente, dont l'origine n'a pas été vérifiée : préférez un téléchargement officiel.
2. Tablette éteinte, puis **Power + Volume bas** : mode Fastboot. Branchez-la au PC.
3. Lancez Mi Unlock, connectez-vous avec **le même compte**, puis cliquez sur « Unlock ».
4. Si l'outil affiche un nouveau délai, attendez-le sans changer de compte.
5. La tablette redémarre, effacée. `ro.boot.flash.locked` doit alors valoir `0`. On peut le vérifier avec `adb shell getprop ro.boot.flash.locked` après la configuration initiale.

## 3. Ensuite

Ne flashez rien tant que les étapes de qualification de [CHAINE-DEMARRAGE.md](CHAINE-DEMARRAGE.md) ne sont pas franchies. Un bootloader déverrouillé rend aussi la tablette plus facile à compromettre en cas de vol : gardez un code de verrouillage d'écran.
