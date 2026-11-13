# Journal du labo (13 novembre 2026)

Hôte : conteneur Linux x86-64, 4 cœurs, 16 Go, **sans /dev/kvm** (émulation TCG pure, comme sur la Pad 5). QEMU 8.2.2, OpenCore REL-106 (OSX-KVM), OVMF 1024x768.

## Chronologie

1. OpenCore seul sous TCG : menu affiché en 60 s. Commande validée.
2. Catalina (BaseSystem 10.15.7, 48/48 blocs vérifiés) avec `-cpu Penryn` + flags OSX-KVM : **figé sur la pomme 36 min**, mémoire du guest immobile à 547 Mo. Pas de progression.
3. Activation de `-v debug=0x100 serial=3` dans les boot-args OpenCore (édition de `config.plist` dans `OpenCore.qcow2` via `qemu-img convert` + `mtools`). Le journal série révèle : `panic ... type 6=invalid opcode` dans `com.apple.kec.corecrypto : _gcm_init`, appelé par `_fipspost_post_aes_gcm` au démarrage de corecrypto (StartIOKit).
4. Diagnostic : corecrypto utilise PCLMULQDQ dès qu'AES-NI est présent ; Penryn (QEMU) n'expose pas PCLMULQDQ. Sous KVM le CPU hôte masque le problème.
5. Variantes testées en parallèle (1 vCPU) : `-hypervisor` (idem), `hpet=off` (idem), `-cpu max` (bloqué dans boot.efi au chargement du prelinkedkernel), `Skylake-Client` (**passe**, arrive à l'espace utilisateur).
6. `Penryn,+pclmulqdq` 1 vCPU et 4 vCPUs : **passent**. Language Chooser à 4 min, fenêtre macOS Utilities à 17 min.
7. Sonoma 14.6 (76/76 blocs vérifiés), `Skylake-Client,-hle,-rtm`, 4 Go, 4 vCPUs : noyau Darwin 23.6.0, espace utilisateur à 4 min, écran Recovery à 16 min. Clavier opérationnel après association HID (~1 min). Terminal de récupération ouvert.
8. Réseau : carte `virtio-net` sous Catalina = pas d'IPv4 (DHCP « no server ») ; carte `e1000-82545em` = lien monté (AppleIntel8254XEthernet). Dans le conteneur de test, le guest n'a pas de DNS ni de sortie Internet (réseau filtré par proxy), donc « Reinstall macOS » n'a pas pu télécharger : étape à faire sur la tablette, avec le Wi-Fi.
9. Sonoma, formatage du disque virtuel depuis le Terminal de récupération, au clavier seul :

   ```bash
   D=$(diskutil list | awk '/\*68\.7 GB/{print $NF; exit}'); echo DISK=$D
   diskutil eraseDisk APFS macOS GPT $D && diskutil list $D
   ```

   Résultat : `DISK=disk0`, « Finished erase on disk0 », schéma GUID, partition EFI 209,7 Mo, conteneur APFS 68,5 Go contenant le volume `macOS`. Le disque est prêt pour « Reinstall macOS Sonoma ». Durée : moins d'une minute même en émulation.

## Pièges notés

- `Misc > Debug > Target = 9` (journal série OpenCore) : écran noir et boucle de redémarrage. Garder 0.
- Tablette USB : les déplacements absolus envoyés par le moniteur QEMU ne bougent pas le curseur macOS ; le clic tombe à la position courante. Le clavier marche : Ctrl-F2 (barre de menus), flèches, Entrée, Tab.
- Le menu OpenCore attend indéfiniment : envoyer Flèche droite + Entrée (ou régler `Timeout`).
- La capture `screendump` ne reflète la bascule graphique de macOS qu'à l'apparition de WindowServer (quelques minutes après « Language Chooser »).
