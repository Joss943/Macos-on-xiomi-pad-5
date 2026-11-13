# macOS Sonoma natif sur Xiaomi Pad 5 : état de la recherche

**État au 13 novembre 2026.** Objectif : démarrer macOS Sonoma 14.6 directement sur la Pad 5 (nabu), sans QEMU.

## Ce que les essais de ce dépôt prouvent

Le journal décrit des démarrages de Recovery avec QEMU/TCG sur un hôte Linux x86-64. Sonoma a atteint Recovery; le volume formaté APFS était le disque virtuel QEMU. L’installation n’a pas été terminée, car la VM du labo n’avait pas Internet pour télécharger les composants macOS. Aucun de ces résultats ne prouve un démarrage natif, ni même une installation complète de Sonoma en VM sur la Pad 5.

La fiche Xiaomi identifie le processeur de la Pad 5 comme un Snapdragon 860. Le script QEMU de ce dépôt émule un processeur Intel x86-64 : il ne transforme pas ce test en installation native.

## Résultat de la recherche sur le démarrage natif

Je n’ai trouvé ni profil macOS Sonoma pour nabu, ni image native prête à installer, ni preuve d’un démarrage de macOS Sonoma sur la Pad 5.

Il existe un projet communautaire UniXNU qui démarre XNU sur nabu, mais son objectif documenté est iPadOS 17.7, pas macOS. C’est une piste distincte; ses instructions ne sont pas intégrées ici afin de garder ce dépôt centré sur macOS.

Le profil macOS publié par UniXNU cible macOS 27.3 en arm64e et impose des exigences matérielles de PAC. La documentation consultée ne propose pas ce profil pour la Pad 5/SM8150. Elle ne fournit donc pas un chemin Sonoma pour cette tablette. Cela décrit l’état des projets disponibles, pas une preuve mathématique qu’aucun port futur ne puisse exister.

## Travail nécessaire pour atteindre l’objectif

Il faut créer un nouveau port macOS pour SM8150, établir que le noyau et l’espace utilisateur de Sonoma peuvent fonctionner sur cette plateforme, adapter la chaîne de démarrage et les volumes APFS, puis développer et valider les pilotes nécessaires à l’écran, au tactile, au stockage, au GPU, au réseau, à l’audio et à l’alimentation. Ces étapes demandent des essais sur une vraie Pad 5; changer un paramètre du script QEMU ne suffit pas.

Le dépôt reste donc un banc d’essai de macOS **en VM** jusqu’à ce qu’un démarrage natif soit observé et documenté sur le matériel cible. Aucun flash ni changement de partition n’a été effectué dans cette recherche.

## Sources

- [Journal des essais QEMU de ce dépôt](https://github.com/Joss943/Macos-on-xiomi-pad-5/blob/main/lab/JOURNAL.md)
- [Script de VM de ce dépôt](https://github.com/Joss943/Macos-on-xiomi-pad-5/blob/main/02-tablette-macos-vm.sh)
- [Fiche Xiaomi Pad 5 : Snapdragon 860](https://www.mi.com/global/support/faq/details/KA-07774/)
- [UniXNU-nabu : projet distinct visant iPadOS 17.7](https://github.com/zzweiqing/UniXNU-nabu)
- [État du port nabu dans le registre UniXNU](https://unixnu.com/devices/nabu-zzweiqing)
- [Profil macOS UniXNU](https://unixnu.com/porting/macos)
- [Exigences arm64e et PAC](https://unixnu.com/porting/arm64e)
