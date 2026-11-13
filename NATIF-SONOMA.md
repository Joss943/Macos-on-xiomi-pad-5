# macOS Sonoma natif sur Xiaomi Pad 5 (nabu)

**État vérifié le 13 novembre 2026 : aucune installation macOS native n'a été faite.** La cible demandée reste Sonoma, aujourd'hui en version 14.8.9. macOS 27 Golden Gate est une autre version et ne résout pas les dépendances matérielles du Snapdragon 860.

## État réel de la tablette

La tablette branchée est détectée par ADB comme Xiaomi Pad 5 `nabu` / modèle `21051182G`, Android 13, build `V816.0.6.0.TKXMIXM`. Le bootloader est verrouillé. Aucun partitionnement, déverrouillage ou flash n'a été effectué.

Sur les huit cœurs, les lignes `Features` de `/proc/cpuinfo` ne publient ni `paca` ni `pacg`. Ce sont les indicateurs Linux d'authentification de pointeurs. C'est une observation du noyau Android; elle seule ne permet pas de lire les registres matériels d'identification EL1 et ne prouve donc pas que le firmware ne masque rien. La microarchitecture Armv8.2 du Cortex-A76 n'inclut pas l'extension Pointer Authentication d'Armv8.3-A. Apple indique que les kexts macOS sur Apple silicon doivent prendre en charge `arm64e` avec PAC. Un noyau et des binaires `arm64e` Sonoma inchangés ne sont donc pas un chemin de démarrage validé pour nabu.

## Pourquoi aucun flash Sonoma n'est lancé

Un IPSW ou un installateur macOS pour Mac Apple silicon n'est pas une image universelle à écrire sur la Xiaomi. Il contient un démarrage et un noyau prévus pour les plateformes Apple. Il manque encore un chargeur de démarrage compatible, un XNU macOS adapté au SoC et à l'ADT nabu, un système de fichiers/racine amorçable, ainsi que les pilotes macOS propres à l'écran, au tactile, à l'UFS, au GPU Adreno 640 et au Wi-Fi Qualcomm. Aucun de ces éléments ne forme aujourd'hui une image Sonoma testée sur cette tablette.

Le projet public [UniXNU-nabu](https://github.com/zzweiqing/UniXNU-nabu) confirme un port source-construit de XNU sur nabu avec **l'espace utilisateur iPadOS 17.7**. Il rapporte un écran et le tactile fonctionnels, mais liste le Wi-Fi comme non implémenté. Ce travail prouve des avancées réutilisables au niveau carte/XNU, pas un système macOS. Son code et ses résultats ne sont pas présentés ici comme une installation Sonoma.

Le projet [Snapintosh](https://github.com/Snapintosh/Snapintosh) fait démarrer macOS 27 sur un Snapdragon X2 Elite récent avec un moniteur EL2 et des pilotes dédiés. Sa cible et sa chaîne de démarrage sont propres à cette machine; elles ne fournissent pas une image installable pour le Snapdragon 860 de nabu. Le résultat ne se transpose pas par simple changement de version.

## Sauvegarde avant toute écriture

Une copie locale de `/sdcard` a été faite dans `outputs/Pad5/sdcard`. Elle contient 9 201 fichiers (4 482 781 497 octets). Les 9 201 sommes SHA-256 du manifeste `outputs/Pad5/SHA256SUMS.txt` ont toutes été vérifiées. Le dossier de sauvegarde MIUI est aussi dans cette copie.

Cette copie n'inclut pas les partitions Android (boot, vendor, firmware, userdata brut) ni les données privées d'applications que la sauvegarde MIUI ne sait pas exporter. Elle n'est donc pas un paquet de restauration complète. Le contenu personnel de cette sauvegarde reste local et n'est pas ajouté à GitHub.

## Prochaine étape technique

1. Examiner et exploiter les composants ouverts du port nabu uniquement comme références matérielles, sans réutiliser son espace utilisateur iPadOS dans ce dépôt.
2. Établir si un noyau et un espace utilisateur macOS Sonoma peuvent être rendus compatibles avec l'absence de PAC exposée par nabu. Sans réponse positive, le démarrage de Sonoma arm64e ne peut pas être annoncé.
3. Développer et valider séparément les chemins UEFI/ADT, stockage/racine, affichage/tactile, Wi-Fi et alimentation.
4. Produire une image de démarrage reproductible et vérifier un démarrage de test et un retour arrière avant toute suppression d'Android.

**Ne pas déverrouiller le bootloader et ne pas effacer Android pour l'instant :** il n'existe pas d'image native Sonoma à installer, et la sauvegarde disponible ne permet pas de restaurer toutes les partitions ni toutes les données privées.

## Sources

- Apple, versions macOS actuelles : <https://support.apple.com/en-us/109033>
- Apple, support `arm64e`/PAC pour les kexts sur Apple silicon : <https://developer.apple.com/documentation/kernel/implementing_drivers_system_extensions_and_kexts>
- Arm, extensions de l'architecture Armv8.x (PAC introduit avec Armv8.3-A) : <https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/Learn%20the%20Architecture/Understanding%20the%20Armv8.x%20extensions.pdf>
- Sources XNU Apple, tag Sonoma 14.8 / Darwin 23.6 : <https://github.com/apple-oss-distributions/xnu/tree/xnu-10063.141.1>
- Projet nabu XNU/iPadOS, état matériel et limites : <https://github.com/zzweiqing/UniXNU-nabu>
- Port macOS Snapdragon X2, architecture spécifique : <https://github.com/Snapintosh/Snapintosh>
