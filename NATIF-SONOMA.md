# macOS Sonoma natif sur Xiaomi Pad 5 (nabu)

**État vérifié le 13 novembre 2026 : aucune installation macOS native n'a été faite.** La cible demandée reste Sonoma, aujourd'hui en version 14.8.9. macOS 27 Golden Gate est une autre version et ne résout pas les dépendances matérielles du Snapdragon 860.

## État réel de la tablette

La tablette branchée est détectée par ADB comme Xiaomi Pad 5 `nabu` / modèle `21051182G`, Android 13, build `V816.0.6.0.TKXMIXM`. Le bootloader est verrouillé. Aucun partitionnement, déverrouillage ou flash n'a été effectué.

Sur les huit cœurs, les lignes `Features` de `/proc/cpuinfo` ne publient ni `paca` ni `pacg`. Ce sont les indicateurs Linux d'authentification de pointeurs. C'est une observation du noyau Android; elle seule ne permet pas de lire les registres matériels d'identification EL1 et ne prouve donc pas que le firmware ne masque rien. La microarchitecture Armv8.2 du Cortex-A76 n'inclut pas l'extension Pointer Authentication d'Armv8.3-A. Apple indique que les kexts macOS sur Apple silicon doivent prendre en charge `arm64e` avec PAC. Un noyau et des binaires `arm64e` Sonoma inchangés ne sont donc pas un chemin de démarrage validé pour nabu.

L'inventaire réseau Android montre `wlan0` et `wlan1` sous `platform/soc/18800000.qcom,icnss`, avec le module noyau `wlan`. Le fichier lisible `/vendor/etc/wifi/WCNSS_qcom_cfg.ini` a été copié dans la sauvegarde locale et son SHA-256 est `aa132665230107d3bbecb6f2d2a3e9a11e372bde5846e6d1becefd4dadd1c670`. Les dossiers firmware et propriétés du device tree refusent l'accès ADB non root. La piste matérielle WCN3998 provient du profil nabu UniXNU, qui la marque encore à inventorier; le pilote nabu et ses entrées calibration/firmware restent à développer.

## Outils de compatibilité ajoutés

`lab/compat/inspect_macho_arch.py` inventorie les tranches Mach-O d'un volume monté et distingue `arm64` de `arm64e`. Il lit les en-têtes uniquement et écrit un rapport JSON sans modifier le volume.

`lab/compat/arm64e_pauth.py` traduit plusieurs formes PAC vers des instructions compatibles sans PAC, dont `PACIASP/PACIBSP/AUTIASP/AUTIBSP` et `XPACLRI`. Les formes sans traduction exacte lèvent une erreur. C'est un module de traduction d'instructions, pas encore un réécrivain de noyau : il ne trouve pas les frontières de fonctions, ne traite pas toutes les opérations PAC ni les ABI `arm64e`, et ne produit pas une image de démarrage.

`lab/compat/xar_extract.py` lit les archives XAR Apple, contrôle le hash du TOC comprimé et les hashes des membres, puis extrait un membre demandé sans écraser de fichier existant. `lab/compat/pbzx_extract.py` décode les blocs XZ ou bruts du flux `pbzx` de l'installateur.

L'installateur Apple officiel préparé pour examiner les binaires est Sonoma `14.8.9` / build `23J631`; les métadonnées du paquet confirment l'XNU Sonoma `xnu-10063.141.1`. Le paquet système reste sur le PC et ne fait pas partie du dépôt.

Commandes de laboratoire:

```powershell
python -m unittest discover -s lab\compat -p 'test_*.py' -v
python lab\compat\inspect_macho_arch.py --root <volume-Sonoma-monte> --output <rapport.json>
python lab\compat\arm64e_pauth.py 0xdac10041 0xd61f089f
python lab\compat\xar_extract.py InstallAssistant.pkg --list
python lab\compat\xar_extract.py InstallAssistant.pkg --extract Payload --output Payload
python lab\compat\pbzx_extract.py Payload InstallAssistant.cpio
```

L'installateur officiel Apple Sonoma 14.8.9 (build 23J631) a été entièrement extrait localement. Le `kernelcache.release.mac15j` décodé fait 104 972 288 octets et son en-tête Mach-O indique `arm64e`, type `MH_FILESET`. C'est le noyau Apple d'un modèle Mac ciblé, pas un noyau nabu. Les métadonnées confirment XNU `xnu-10063.141.1`. Les images système restent sur le PC et ne sont pas dans le dépôt.

Le `SharedSupport.dmg` de 13 643 079 050 octets et l'archive de mise à jour sont extraits; leurs tailles et hashes XAR ont été vérifiés. Cette extraction fournit les binaires à analyser, pas un installateur pour la Pad 5.

## Pourquoi aucun flash Sonoma n'est lancé

Un IPSW ou un installateur macOS pour Mac Apple silicon n'est pas une image universelle à écrire sur la Xiaomi. Il contient un démarrage et un noyau prévus pour les plateformes Apple. Il manque encore un chargeur de démarrage compatible, un XNU macOS adapté au SoC et à l'ADT nabu, un système de fichiers/racine amorçable, ainsi que les pilotes macOS propres à l'écran, au tactile, à l'UFS, au GPU Adreno 640 et au Wi-Fi Qualcomm. Aucun de ces éléments ne forme aujourd'hui une image Sonoma testée sur cette tablette.

Le projet public [UniXNU-nabu](https://github.com/zzweiqing/UniXNU-nabu) confirme un port source-construit de XNU sur nabu avec **l'espace utilisateur iPadOS 17.7**. Il rapporte un écran et le tactile fonctionnels, mais liste le Wi-Fi comme non implémenté. Ce travail prouve des avancées réutilisables au niveau carte/XNU, pas un système macOS. Son code et ses résultats ne sont pas présentés ici comme une installation Sonoma.

Le projet [Snapintosh](https://github.com/Snapintosh/Snapintosh) fait démarrer macOS 27 sur un Snapdragon X2 Elite récent avec un moniteur EL2 et des pilotes dédiés. Sa cible et sa chaîne de démarrage sont propres à cette machine; elles ne fournissent pas une image installable pour le Snapdragon 860 de nabu. Le résultat ne se transpose pas par simple changement de version.

## Sauvegarde avant toute écriture

Une copie locale de `/sdcard` a été faite dans `outputs/Pad5/sdcard`. Elle contient 9 201 fichiers (4 482 781 497 octets). Les 9 201 sommes SHA-256 du manifeste `outputs/Pad5/SHA256SUMS.txt` ont toutes été vérifiées. Le dossier de sauvegarde MIUI est aussi dans cette copie.

Cette copie n'inclut pas les partitions Android (boot, vendor, firmware, userdata brut) ni les données privées d'applications que la sauvegarde MIUI ne sait pas exporter. Elle n'est donc pas un paquet de restauration complète. Le contenu personnel de cette sauvegarde reste local et n'est pas ajouté à GitHub.

## Prochaine étape technique

1. Cartographier les instructions PAC et les dépendances `arm64e` dans le noyau et les composants extraits; le décodeur d'instructions est le premier outil de cette étape.
2. Construire un XNU Darwin 23 adapté au SM8150, puis qualifier les ABI et pilotes de stockage, écran et tactile.
3. Implémenter le pilote WCN3998 de nabu et intégrer l'interface réseau attendue par macOS.
4. Produire l'image, démarrer depuis l'ESP sans effacer Android, puis qualifier le tactile et le Wi-Fi avant de préparer une installation persistante.

**Ne pas déverrouiller le bootloader et ne pas effacer Android pour l'instant :** il n'existe pas d'image native Sonoma à installer, et la sauvegarde disponible ne permet pas de restaurer toutes les partitions ni toutes les données privées.

## Sources

- Apple, versions macOS actuelles : <https://support.apple.com/en-us/109033>
- Apple, support `arm64e`/PAC pour les kexts sur Apple silicon : <https://developer.apple.com/documentation/kernel/implementing_drivers_system_extensions_and_kexts>
- Arm, extensions de l'architecture Armv8.x (PAC introduit avec Armv8.3-A) : <https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/Learn%20the%20Architecture/Understanding%20the%20Armv8.x%20extensions.pdf>
- Sources XNU Apple, tag Sonoma 14.8 / Darwin 23.6 : <https://github.com/apple-oss-distributions/xnu/tree/xnu-10063.141.1>
- Projet nabu XNU/iPadOS, état matériel et limites : <https://github.com/zzweiqing/UniXNU-nabu>
- Projet Linux, référence de bus ath10k SNOC/WCN3990 sur une autre carte Qualcomm : <https://github.com/torvalds/linux/blob/master/drivers/net/wireless/ath/ath10k/Kconfig>
- Linux ath10k SNOC, référence indépendante de bus et firmware : <https://github.com/torvalds/linux/blob/master/drivers/net/wireless/ath/ath10k/snoc.c>
- UniXNU-zeta, recherche de traduction arm64e pour SoC sans PAC : <https://github.com/none24smu/UniXNU-zeta>
- Port macOS Snapdragon X2, architecture spécifique : <https://github.com/Snapintosh/Snapintosh>
- Format XAR, dépôt et spécification communautaire du projet `mackyle/xar` : <https://github.com/mackyle/xar/wiki/xarformat>
- Format PBZX et cadrage d'une implémentation libarchive : <https://github.com/libarchive/libarchive/issues/2849>

