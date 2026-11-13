# macOS Sonoma natif sur Xiaomi Pad 5 : état de la recherche

**État au 13 novembre 2026.** L’objectif demandé est macOS Sonoma 14.6 démarré directement sur la Pad 5 (nabu), sans QEMU.

## Résultat honnête

Je n’ai pas installé Sonoma nativement et ce dépôt ne contient pas d’image d’installation native vérifiée. Les essais documentés ici sont des démarrages de Recovery macOS **émulés par QEMU/TCG** sur un hôte Linux x86-64. Le disque APFS mentionné dans le journal est le disque virtuel QEMU, pas le stockage de la tablette.

Le dernier essai a atteint Recovery Sonoma et a formaté le disque virtuel en APFS. L’installation n’a pas été terminée : la VM du labo n’avait pas d’accès Internet pour télécharger les fichiers d’installation. Le journal ne prouve donc ni une installation complète de Sonoma en VM, ni un démarrage de macOS natif sur la Pad 5.

## Un vrai port natif Apple existe pour nabu, mais c’est iPadOS

La recherche a trouvé [UniXNU-nabu](https://github.com/zzweiqing/UniXNU-nabu), un port communautaire pour la Xiaomi Pad 5 (Snapdragon 860 / SM8150). Il démarre un XNU construit depuis les sources et l’espace utilisateur **iPadOS 17.7**, avec une démonstration de l’interface SpringBoard sur la tablette. C’est une avancée native importante, mais ce n’est pas macOS Sonoma.

Le port reste expérimental : le réseau Wi-Fi, l’audio, la gestion d’alimentation et le stockage Data persistant ne sont pas implémentés; un blocage d’affichage est encore signalé. Les instructions du projet demandent les images Apple et firmwares propres à l’utilisateur; aucune version prête à installer n’est publiée dans ses Releases. Voir [l’état détaillé du port nabu](https://unixnu.com/devices/nabu-zzweiqing).

## Pourquoi le port iPadOS ne devient pas Sonoma par un réglage

Le profil public nabu cible iPadOS 17.7 (21H16). Le profil macOS décrit actuellement par UniXNU cible macOS 27.3 en arm64e et requiert la prise en charge matérielle de PAC; la page des appareils ne donne pas ce profil au nabu. Cela ne fournit ni un profil Sonoma, ni les pilotes et l’espace utilisateur macOS nécessaires pour la Pad 5.

Pour viser Sonoma en natif, il faudrait donc développer et valider un nouveau port SM8150/macOS : chaîne de démarrage, profil XNU compatible, montage des volumes système, pilotes UFS/APFS, écran, tactile, GPU, réseau, audio et gestion d’alimentation. Les documents consultés ne présentent pas ce port comme disponible ou testé. Ce travail ne se réduit pas à changer le nom du CPU dans le script QEMU.

## Périmètre et prochaine vérification

- Le script `02-tablette-macos-vm.sh` reste la voie de ce dépôt pour tester macOS en VM.
- Le port UniXNU peut servir de base à une expérience native **iPadOS 17.7**, si cet objectif distinct est accepté; ce document ne présente pas cette expérience comme Sonoma.
- Aucun flash ni modification de partition n’a été effectué dans cette recherche. Avant tout essai natif, il faut vérifier le modèle exact, disposer d’une sauvegarde restaurable et suivre le préflight/retour arrière du projet choisi.

## Sources

- [Journal des essais QEMU de ce dépôt](https://github.com/Joss943/Macos-on-xiomi-pad-5/blob/main/lab/JOURNAL.md)
- [UniXNU-nabu : sources, construction et limites](https://github.com/zzweiqing/UniXNU-nabu)
- [État du port Xiaomi Pad 5 dans le registre UniXNU](https://unixnu.com/devices/nabu-zzweiqing)
- [Profil macOS UniXNU](https://unixnu.com/porting/macos)
- [Exigences arm64e et PAC](https://unixnu.com/porting/arm64e)
- [Fiche Xiaomi Pad 5 : Snapdragon 860](https://www.mi.com/global/support/faq/details/KA-07774/)
