# macOS Sonoma natif sur Xiaomi Pad 5 (nabu)

**État vérifié le 13 novembre 2026 : aucune installation macOS native n'a été faite.** La cible demandée reste Sonoma, aujourd'hui en version 14.8.9. macOS 27 Golden Gate est une autre version et ne résout pas les dépendances matérielles du Snapdragon 860.

## État réel de la tablette

La tablette branchée est détectée par ADB comme Xiaomi Pad 5 `nabu` / modèle `21051182G`, Android 13, build `V816.0.6.0.TKXMIXM`. Le bootloader est verrouillé. Aucun partitionnement, déverrouillage ou flash n'a été effectué.

Sur les huit cœurs, les lignes `Features` de `/proc/cpuinfo` ne publient ni `paca` ni `pacg`. Ce sont les indicateurs Linux d'authentification de pointeurs. C'est une observation du noyau Android; elle seule ne permet pas de lire les registres matériels d'identification EL1 et ne prouve donc pas que le firmware ne masque rien. La microarchitecture Armv8.2 du Cortex-A76 n'inclut pas l'extension Pointer Authentication d'Armv8.3-A. Apple indique que les kexts macOS sur Apple silicon doivent prendre en charge `arm64e` avec PAC. Un noyau et des binaires `arm64e` Sonoma inchangés ne sont donc pas un chemin de démarrage validé pour nabu.

`dumpsys input` sur la tablette révèle `NVTCapacitiveTouchScreen` (event3) et `NVTCapacitivePen` (event4). Les arbres Linux nabu identifient le contrôleur NT36523 sur SPI QUPv3 SE18, avec IRQ GPIO39 et fréquence 9,6 MHz; ils documentent aussi le panneau NT36523 double-DSI et son rétroéclairage KTZ8866. C'est une base concrète pour le tactile, mais aucun pilote macOS n'est écrit.

ADB voit `wlan0` et `wlan1` sous `platform/soc/18800000.qcom,icnss`, avec le module noyau `wlan`. Le fichier lisible `/vendor/etc/wifi/WCNSS_qcom_cfg.ini` a été copié dans la sauvegarde locale et son SHA-256 est `aa132665230107d3bbecb6f2d2a3e9a11e372bde5846e6d1becefd4dadd1c670`. Les propriétés du device tree et les fichiers firmware refusent l'accès ADB non root. Les intégrations Linux nabu identifient le chemin Wi-Fi comme WCN3990/ath10k-SNOC; leur état varie entre branches et builds communautaires. Le profil UniXNU cite WCN3998, suffixe que cette session ne peut pas confirmer sans accès root. Le pilote macOS et les données calibration/firmware restent à développer.

## Outils de compatibilité ajoutés

`lab/compat/inspect_macho_arch.py` inventorie les tranches Mach-O d'un volume monté et distingue `arm64` de `arm64e`. Il lit les en-têtes uniquement et écrit un rapport JSON sans modifier le volume.

`lab/compat/arm64e_pauth.py` traduit plusieurs formes PAC vers des instructions compatibles sans PAC, dont `PACIASP/PACIBSP/AUTIASP/AUTIBSP`, `XPACLRI` et des chargements `LDRAA/LDRAB` à grands offsets. Certains chargements deviennent deux instructions. Deux formes acceptent un registre temporaire fourni par l'appelant, qui doit d'abord prouver qu'il est libre. Les chargements pré-indexés dont base et destination se chevauchent restent refusés. Ce module ne relocalise pas les branches et ne produit pas une image de démarrage.

`lab/compat/scan_arm64e_pauth.py` suit les 362 membres du fileset noyau et parcourt les sections marquées comme code sans modifier les binaires. L'analyse du `kernelcache.mac15j` Sonoma a trouvé 887 368 mots candidats connus : 144 demandent une séquence de deux instructions et 7 sont refusés pour préserver les registres en alias. Capstone 5.0.9 décode correctement les 144 séquences en `ADD/SUB` puis `LDR`; cela reste une validation statique, pas un essai d'exécution.

`lab/nabu/nt36523_touch.py` décode les paquets SPI NT36523 de 66 octets en dix slots tactiles, coordonnées, largeur, pression et motifs de réinitialisation. Quatre tests synthétiques passent. Ce code n'accède pas encore au contrôleur SPI et ne publie pas les contacts dans IOHID/macOS.

`lab/compat/xar_extract.py` lit les archives XAR Apple, contrôle le hash du TOC comprimé et les hashes des membres, puis extrait un membre demandé sans écraser de fichier existant. `lab/compat/pbzx_extract.py` décode les blocs XZ ou bruts du flux `pbzx` de l'installateur.

L'installateur Apple officiel préparé pour examiner les binaires est Sonoma `14.8.9` / build `23J631`; les métadonnées du paquet confirment l'XNU Sonoma `xnu-10063.141.1`. Le paquet système reste sur le PC et ne fait pas partie du dépôt.

Commandes de laboratoire:

```powershell
python -m unittest discover -s lab\compat -p 'test_*.py' -v
python -m unittest discover -s lab\nabu -p 'test_*.py' -v
python lab\compat\inspect_macho_arch.py --root <volume-Sonoma-monte> --output <rapport.json>
python lab\compat\arm64e_pauth.py 0xdac10041 0xd61f089f
python lab\compat\scan_arm64e_pauth.py kernelcache.mac15j.decoded --output scan.json
python lab\compat\xar_extract.py InstallAssistant.pkg --list
python lab\compat\xar_extract.py InstallAssistant.pkg --extract Payload --output Payload
python lab\compat\pbzx_extract.py Payload InstallAssistant.cpio
```

L'installateur officiel Apple Sonoma 14.8.9 (build 23J631) a été entièrement extrait localement. Le `kernelcache.release.mac15j` décodé fait 104 972 288 octets et son en-tête Mach-O indique `arm64e`, type `MH_FILESET`. C'est le noyau Apple d'un modèle Mac ciblé, pas un noyau nabu. Les métadonnées confirment XNU `xnu-10063.141.1`. Les images système restent sur le PC et ne sont pas dans le dépôt.

Le `SharedSupport.dmg` de 13 643 079 050 octets et l'archive de mise à jour sont extraits; leurs tailles et hashes XAR ont été vérifiés. Cette extraction fournit les binaires à analyser, pas un installateur pour la Pad 5.

## Pourquoi aucun flash Sonoma n'est lancé

Un IPSW ou un installateur macOS pour Mac Apple silicon n'est pas une image universelle à écrire sur la Xiaomi. Il contient un démarrage et un noyau prévus pour les plateformes Apple. Il manque encore un chargeur de démarrage compatible, un XNU macOS adapté au SoC et à l'ADT nabu, un système de fichiers/racine amorçable, ainsi que les pilotes macOS propres à l'écran, au tactile, à l'UFS, au GPU Adreno 640 et au Wi-Fi Qualcomm. Aucun de ces éléments ne forme aujourd'hui une image Sonoma testée sur cette tablette.

Les preuves publiques récentes changent nettement l'évaluation du matériel : des équipes font démarrer XNU directement sur nabu. Le dossier [UniXNU Xiaomi Pad 5](https://unixnu.com/devices/nabu-zzweiqing) décrit un espace utilisateur **iPadOS 17.7**, SpringBoard interactif, tactile NT36523, affichage/GPU vérifiés, mais réseau non commencé et blocage d'affichage encore signalé. La configuration documentée utilise une Pad 5 modifiée à 12 Go; ses mesures mémoire ne sont pas copiables telles quelles sur une tablette de série. Un autre journal [Lux12138/unixnu-nabu](https://github.com/Lux12138/unixnu-nabu/blob/main/CURRENT-STATE.md) indique launchd et les services iPadOS démarrés, avec un provider d'affichage encore manquant. Ce sont des preuves de démarrage XNU natif et de progrès sur le tactile, **pas une image macOS** ni une démonstration du Wi-Fi sur cette tablette.

UniXNU publie aussi un profil de construction macOS 27, mais son guide précise que ce profil est **arm64e** et que l'appareil doit satisfaire les exigences arm64e; aucun profil macOS 27 prêt pour nabu n'est documenté. Notre observation Android ne voit pas `paca`/`pacg` sur nabu, et le Snapdragon 860 utilise des Cortex-A76 antérieurs à Armv8.3-A/PAC : macOS 27 ne contourne donc pas le problème par son seul numéro de version. Le port macOS demande en plus ses propres racines système, pilotes, services réseau et intégrations graphiques. En conséquence, démarrer XNU natif sur nabu est devenu crédible grâce à ces ports; obtenir **macOS** natif sur cette Pad 5 avec tactile et Wi-Fi reste un objectif difficile et non démontré. Le Wi-Fi et la compatibilité arm64e constituent les plus gros écarts documentés.

Le projet [Snapintosh](https://github.com/Snapintosh/Snapintosh) fait démarrer macOS 27 sur un Snapdragon X2 Elite récent avec un moniteur EL2 et des pilotes dédiés. Sa cible et sa chaîne de démarrage sont propres à cette machine; elles ne fournissent pas une image installable pour le Snapdragon 860 de nabu. Le résultat ne se transpose pas par simple changement de version.

## Sauvegarde avant toute écriture

Une copie locale de `/sdcard` a été faite dans `outputs/Pad5/sdcard`. Elle contient 9 201 fichiers (4 482 781 497 octets). Les 9 201 sommes SHA-256 du manifeste `outputs/Pad5/SHA256SUMS.txt` ont toutes été vérifiées. Le dossier de sauvegarde MIUI est aussi dans cette copie.

Cette copie n'inclut pas les partitions Android (boot, vendor, firmware, userdata brut) ni les données privées d'applications que la sauvegarde MIUI ne sait pas exporter. Elle n'est donc pas un paquet de restauration complète. Le contenu personnel de cette sauvegarde reste local et n'est pas ajouté à GitHub.

## Prochaine étape technique

1. Partir du port XNU nabu qui a déjà atteint l'espace utilisateur et comparer ses patches/ADT aux exigences du profil macOS 27; éviter de traiter la traduction PAC du kernelcache Sonoma comme si elle suffisait à produire un noyau.
2. Vérifier la compatibilité du profil macOS cible avec le SM8150 et ses binaires arm64e, puis établir un premier démarrage Mac jusqu'à launchd avant de toucher au stockage Android.
3. Réutiliser le protocole NT36523 et le chemin d'affichage déjà validés côté XNU, en portant leurs interfaces vers le profil macOS.
4. Inventorier le Wi-Fi nabu, son firmware et sa séquence d'alimentation; développer le pilote et tester association/transmission sur nabu.
5. Produire une image amorçable depuis l'ESP sans effacer Android, qualifier démarrage, tactile et Wi-Fi, puis préparer une installation persistante.

**Ne pas déverrouiller le bootloader et ne pas effacer Android pour l'instant :** il n'existe pas d'image native Sonoma à installer, et la sauvegarde disponible ne permet pas de restaurer toutes les partitions ni toutes les données privées.

## Sources

- Apple, versions macOS actuelles : <https://support.apple.com/en-us/109033>
- Apple, support `arm64e`/PAC pour les kexts sur Apple silicon : <https://developer.apple.com/documentation/kernel/implementing_drivers_system_extensions_and_kexts>
- Arm, extensions de l'architecture Armv8.x (PAC introduit avec Armv8.3-A) : <https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/Learn%20the%20Architecture/Understanding%20the%20Armv8.x%20extensions.pdf>
- Sources XNU Apple, tag Sonoma 14.8 / Darwin 23.6 : <https://github.com/apple-oss-distributions/xnu/tree/xnu-10063.141.1>
- Dossier UniXNU nabu, état XNU/iPadOS et matériels vérifiés : <https://unixnu.com/devices/nabu-zzweiqing>
- Journal XNU nabu de Lux12138, mesures launchd/SpringBoard et limite mémoire : <https://github.com/Lux12138/unixnu-nabu/blob/main/CURRENT-STATE.md>
- Guide du profil macOS 27 UniXNU (procédure générique, pas une image nabu) : <https://unixnu.com/porting/macos>
- Arbre Linux nabu, tactile NT36523 SPI et état matériel : <https://github.com/SeimoDev/linux-xiaomi-nabu>
- Device tree nabu détaillant le contrôleur Novatek et son bus SPI : <https://github.com/AwakenOS-Devices/android_kernel_xiaomi_nabu/blob/triton/arch/arm64/boot/dts/qcom/nabu-sm8150.dtsi>
- Port Ubuntu nabu et état annoncé du Wi-Fi WCN3990 : <https://github.com/Kumar-Jy/xiaomi-nabu-ubuntu>
- Format de rapport NT36523, référence d'implémentation Linux : <https://github.com/Xander-trav/linux-nabu/blob/main/0005-Input-Add-nt36523-touchscreen-driver.patch>
- Projet Linux, référence de bus ath10k SNOC/WCN3990 sur une autre carte Qualcomm : <https://github.com/torvalds/linux/blob/master/drivers/net/wireless/ath/ath10k/Kconfig>
- Linux ath10k SNOC, référence indépendante de bus et firmware : <https://github.com/torvalds/linux/blob/master/drivers/net/wireless/ath/ath10k/snoc.c>
- UniXNU-zeta, recherche de traduction arm64e pour SoC sans PAC : <https://github.com/none24smu/UniXNU-zeta>
- Port macOS Snapdragon X2, architecture spécifique : <https://github.com/Snapintosh/Snapintosh>
- Format XAR, dépôt et spécification communautaire du projet `mackyle/xar` : <https://github.com/mackyle/xar/wiki/xarformat>
- Format PBZX et cadrage d'une implémentation libarchive : <https://github.com/libarchive/libarchive/issues/2849>

