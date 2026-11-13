# macOS Sonoma natif sur Xiaomi Pad 5 : état de la recherche

**État au 13 novembre 2026.** Cible : démarrer macOS Sonoma directement sur la Pad 5 (nabu / SM8150), sans QEMU. Je continue la piste macOS en priorité. À ce stade, il n’existe toujours pas d’image ni de procédure de démarrage natif validée pour cette tablette.

## Ce que le dépôt prouve aujourd’hui

Le journal du dépôt rapporte des démarrages de Recovery avec QEMU/TCG sur un hôte Linux x86-64. Le volume APFS formaté était un disque virtuel QEMU. Le téléchargement des composants a échoué faute de réseau dans le labo. Cela ne prouve ni une installation complète de Sonoma en VM, ni un démarrage natif sur la Pad 5.

Le port communautaire [UniXNU-nabu](https://github.com/zzweiqing/UniXNU-nabu) montre que du XNU recompilé peut démarrer sur cette carte. Son système testé est iPadOS 17.7. Ce code n’est pas une image macOS et n’est pas intégré à la procédure de ce dépôt.

## Piste Sonoma trouvée dans les sources Apple

Le tag public [XNU xnu-10002.81.5](https://github.com/apple-oss-distributions/xnu/tree/xnu-10002.81.5) correspond au noyau de macOS Sonoma 14.3 (Darwin 23.3.0). Cela fournit une base source Sonoma précise pour un futur noyau adapté.

La présence de `config/MASTER.arm64.MacOSX` dans ce tag ne constitue toutefois pas un profil matériel prêt à l’emploi : c’est un fichier de configuration des symboles/API exportés. Le guide de compilation XNU décrit un build Apple Silicon à partir d’un KDK et d’une configuration de plateforme Mac précise; il ne décrit aucune plateforme SM8150. Il faut encore créer et compiler une configuration nabu qui lie le noyau Sonoma au démarrage UEFI, à l’ADT, au stockage et aux pilotes de la tablette.

- [Code source XNU Sonoma 14.3](https://github.com/apple-oss-distributions/xnu/tree/xnu-10002.81.5)
- [Guide de compilation XNU](https://github.com/apple-oss-distributions/xnu/blob/main/README.md)
- [Périmètre du profil macOS dans UniXNU](https://unixnu.com/porting/macos)

## Premier verrou matériel : arm64e et PAC

Apple documente que les extensions noyau (kexts) sur Apple Silicon doivent prendre en charge l’architecture `arm64e`, qui utilise l’authentification de pointeurs (PAC). Le Snapdragon 860 de la Pad 5 utilise un CPU Qualcomm Kryo 485. L’architecture exacte et les fonctions PAC exposées par les cœurs de cette tablette doivent être mesurées sur l’appareil; je ne les déduis pas du seul nom du SoC.

Sous Android, ouvre Termux et lance cette lecture seule :

```sh
grep -E '^(processor|Features)' /proc/cpuinfo
```

Dans les lignes `Features`, relève si `paca` et `pacg` apparaissent. Linux définit ces indicateurs comme la présence de l’authentification de pointeurs. Colle la sortie complète dans la discussion : elle permettra de décider si le noyau Sonoma peut viser directement le CPU ou s’il faut traiter l’exécution des binaires `arm64e` comme un obstacle bloquant. L’absence des indicateurs est un signal fort, mais le test doit couvrir les huit cœurs et être recoupé avec les registres d’identification CPU avant toute tentative de démarrage.

- [Apple : kexts et arm64e sur Apple Silicon](https://developer.apple.com/documentation/kernel/implementing_drivers_system_extensions_and_kexts)
- [Linux : indicateurs HWCAP_PACA et HWCAP_PACG](https://docs.kernel.org/6.6/arch/arm64/elf_hwcaps.html)
- [Arm : extensions Armv8.x et capacités CPU](https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/Learn%20the%20Architecture/Understanding%20the%20Armv8.x%20extensions.pdf)

Même avec PAC disponible, il restera à vérifier les binaires du système Sonoma, la fermeture de démarrage APFS, l’ADT attendu par le noyau, puis à porter les pilotes nabu pour le tactile, l’affichage, l’UFS, le GPU, le réseau, l’audio et l’alimentation. Si PAC manque, le port ne peut pas simplement réutiliser les kexts arm64e d’Apple : il faudra démontrer une solution de compatibilité binaire avant de poursuivre vers un installateur.

## Prochaine séquence de travail

1. Relever les indicateurs PAC sur les cœurs nabu avec la commande ci-dessus.
2. Obtenir les entrées de restauration Sonoma 14.3 et inventorier les architectures des éléments nécessaires au démarrage, sans publier ni redistribuer l’image Apple.
3. Construire un noyau XNU Sonoma arm64 adapté à nabu et vérifier qu’il charge le noyau et les extensions requis.
4. Ajouter un profil de démarrage macOS au projet, puis valider chaque étape sur la tablette avant de publier une procédure d’installation.
5. Ne produire une procédure de flash qu’après avoir une image démarrable et une méthode de retour arrière vérifiée.

Le dépôt ne doit pas présenter la VM comme une installation native. Aucune partition de la tablette n’a été modifiée pendant cette recherche.

## Sources des essais existants

- [Journal des essais QEMU](https://github.com/Joss943/Macos-on-xiomi-pad-5/blob/main/lab/JOURNAL.md)
- [Script de VM](https://github.com/Joss943/Macos-on-xiomi-pad-5/blob/main/02-tablette-macos-vm.sh)
- [Fiche Xiaomi Pad 5 / Snapdragon 860](https://www.mi.com/global/support/faq/details/KA-07774/)
- [UniXNU-nabu, projet séparé orienté iPadOS 17.7](https://github.com/zzweiqing/UniXNU-nabu)
- [État du port nabu dans UniXNU](https://unixnu.com/devices/nabu-zzweiqing)
