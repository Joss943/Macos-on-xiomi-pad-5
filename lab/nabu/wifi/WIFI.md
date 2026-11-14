# Wi-Fi de la Xiaomi Pad 5 sous macOS : étude et premier code

## Correction : ce n'est pas un QCA6390 en PCIe

Le dépôt et la feuille de route parlaient d'un Wi-Fi QCA6390 sur PCIe (CNSS, MHI, ath11k). Les preuves disponibles disent autre chose.

| Preuve | Ce qu'elle montre |
|---|---|
| Mesure ADB du 13/11/2026 ([`lab/results/nabu-macos27-radio-hardware.json`](../../results/nabu-macos27-radio-hardware.json)) | `wlan0` est rattaché à `18800000.qcom,icnss`. `icnss` est le pilote Qualcomm du Wi-Fi intégré au SoC. Le nœud `qcom,cnss-qca6390@a0000000` existe dans l'arbre Android générique du SM8150, mais aucune interface ne s'y rattache. |
| Arbre matériel nabu public ([`sm8150-xiaomi-nabu.dts`](https://github.com/SeimoDev/linux-xiaomi-nabu/blob/4e6d08bb1b467c721e19cd693e4ec7388d982d73/arch/arm64/boot/dts/qcom/sm8150-xiaomi-nabu.dts)) | Active `&wifi`, défini dans `sm8150.dtsi` comme `wifi@18800000`, compatible `qcom,wcn3990-wifi`. Aucun contrôleur PCIe n'est activé. Le Bluetooth est `qcom,wcn3991-bt` et partage les alimentations du Wi-Fi. |
| Nœud `wifi@18800000` (`sm8150.dtsi`) | Registres à `0x18800000`, 12 interruptions de moteurs de copie (GIC SPI 414 à 425), zone mémoire réservée `wlan_mem`, horloge `RPMH_RF_CLK2`, flux IOMMU `0x640`. |

**Conclusion** : le Wi-Fi est le cœur WLAN intégré au SM8150, de la famille WCN3990, avec la puce radio WCN3991. Son pilote de référence est `ath10k_snoc`, pas `ath11k`. Le chemin matériel réel est SNOC et moteurs de copie, pas PCIe et MHI.

## Ce que le Wi-Fi exige sous macOS

Aucune de ces briques n'existe dans XNU ni dans macOS pour un SoC Qualcomm.

1. **Le DSP modem doit tourner.** Le firmware WLAN (`wlanmdsp.mbn`) est chargé et exécuté par le sous-système modem (MPSS). Il faut un chargeur de sous-système qui authentifie les images auprès de TrustZone par appels SCM, puis démarre le Q6.
2. **Services de fichiers pour le modem.** Le modem demande ses fichiers à l'hôte par QMI : système de fichiers distant (`rmtfs`) et TFTP (`tqftpserv`). Sous Linux ce sont des démons en espace utilisateur.
3. **Transport IPC.** SMEM, puis GLINK sur SMEM, puis le routeur QRTR. C'est par QRTR qu'on joint le service QMI « WLFW » (identifiant `0x45`).
4. **Poignée de main WLFW.** Ordre relevé dans `ath10k/qmi.c` : enregistrement des indications, capacités de l'hôte, informations MSA, attribution de la mémoire MSA au firmware par l'hyperviseur (SCM `assign_mem`), MSA prêt, capacités, puis données de carte (BDF), rapport de calibration, indication « firmware prêt », configuration WLAN et mode WLAN.
5. **Cœur réseau.** Anneaux des moteurs de copie dans la fenêtre `0x18800000`, HTC, WMI pour le contrôle, HTT pour les données, gestion des trames 802.11.
6. **Intégration macOS.** `IO80211Family` est privé, sans en-têtes dans le SDK. Deux voies : rétro-ingénierie de l'interface privée pour chaque version de macOS (comme AirportItlwm pour Intel), ou exposition comme interface Ethernet via `IOEthernetController` (comme itlwm), avec une application séparée pour l'association. La seconde est la voie raisonnable pour commencer.
7. **Firmware propriétaire.** Images modem et WLAN, données de carte : à extraire par l'utilisateur de sa propre tablette. Jamais dans ce dépôt.

## Licences des références

| Code de référence | Licence (SPDX dans Linux v6.12) | Conséquence |
|---|---|---|
| `ath10k/snoc.c`, `ath10k/qmi.c`, `ath10k/qmi_wlfw_v01.{h,c}` | ISC | Adaptable dans un pilote macOS en conservant la notice ISC. |
| `soc/qcom/qmi_interface.c`, `soc/qcom/qmi_encdec.c`, `net/qrtr/af_qrtr.c` | GPL-2.0 | À réimplémenter indépendamment. C'est ce que fait `qmi_qrtr.c`. |

## Ce qui est implémenté ici

- [`qmi_qrtr.h`](qmi_qrtr.h), [`qmi_qrtr.c`](qmi_qrtr.c) : en-tête QRTR v1 (32 octets, charge alignée sur 4 octets), paquet de contrôle `NEW_LOOKUP` et lecture de `NEW_SERVER` (instance encodée `version | instance << 8`), en-tête QMI (7 octets), écriture et parcours de TLV, TLV de résultat, et le premier message WLFW (`IND_REGISTER`, `0x0020`) avec sa réponse.
- [`test_qmi_qrtr.c`](test_qmi_qrtr.c) : tests octet par octet, compilés avec ASan et UBSan.

Commande :

```bash
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
  lab/nabu/wifi/test_qmi_qrtr.c lab/nabu/wifi/qmi_qrtr.c -o /tmp/qmi-tests && /tmp/qmi-tests
```

## Limites

- Rien n'a été envoyé à un modem : aucun transport GLINK/SMEM n'existe encore, et le modem n'est pas démarré.
- Les octets attendus des tests sont dérivés des définitions publiques, pas capturés sur la tablette. Une capture QRTR sous Android (`qrtr-lookup`, traces `qmi`) sur la Pad 5 permettrait de les confirmer.
- Le Wi-Fi ne fonctionne pas sous macOS. Les étapes 1 à 6 restent à faire.
