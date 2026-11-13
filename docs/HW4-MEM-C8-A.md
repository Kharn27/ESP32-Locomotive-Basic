# HW4-MEM-C8-A — attribution et blocage sûr (Issue #380)

**Mandat :** [#380 commentaire #6849397028](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/380#issuecomment-6849397028). **Base mandatée :** `main@4f8264c5b1fd370c185d687f5e03e92fe4c8f1e2`, après fusion C7 / PR #381. **Statut proposé : BLOCKED — NO SAFE PATCH**, non une récupération mémoire. `ROOT_CAUSE_UNVERIFIED` maintenu.

## Attribution reproductible, sans approximation

L'archive [C6-B2-B run #42660089530, artifact #13693788432](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42660089530/artifacts/13693788432) a été téléchargée et vérifiée indépendamment : ZIP SHA256 `29b8f28c7fcaadd808c3f0ce339ea2a3c18331154a1da08f9116c6ac2c067777`, manifeste SHA256 `0d5011d103cde1ea6429a4d4edbad8ba6a72aefab02cba1b71c6c242dd014c0b`, **134/134 membres SHA256 OK**. Source historique B `4d261f2a76374ab99a4dd7415cae7a097330c46b`, H `64b0087d5087903fee175c4f149c65a65bb43fe6` (ce ne sont **pas** les SHAs du nouveau main). Les maps B/H SPI40 et SPI20 ont été repassées par un parseur indépendant : la somme des contributions couvre toute la section `.iram0.text`, pour chacun des quatre ELF.

| Mesure mémoire (octets) | B SPI40/20 | H SPI40/20 | Delta |
|---|---:|---:|---:|
| `.iram0.vectors` | 1 028 | 1 028 | 0 |
| `.iram0.text` | 66 303 | 66 523 | **+220** |
| IRAM, hors `.iram0.text_end=1` | 67 331 | 67 551 | **+220** |
| DRAM | 54 864 | 54 864 | 0 |
| BSS | 43 792 | 43 792 | 0 |

Contributions exactes : **+88 code +128 littéraux +4 `*fill*` = +220 octets**. **16 objets** de `esp_system`, `freertos`, `spi_flash`, `esp_hw_support` et `log` présentent les différences post-relaxation, **aucun** `loco_core`. Plus gros contributeurs : `cpu_start.c.obj +48`, `tasks.c.obj +23`, `spi_flash_os_func_app.c.obj +23`, `debug_helpers.c.obj +20`, `cache_utils.c.obj +20`. Résultat identique pour les deux horloges.

La contre-épreuve des véritables objets **avant lien** de [C6-B2-D1, run #42781263551, artifact #13746720518](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42781263551/artifacts/13746720518) donne ZIP SHA256 `c12bf46013d91cb7ba0389388fa9523a460623944b44e2b8bb2c8c828f61fadc`, manifeste `c70a6095a9b9622881a868ee40c80c8fd5653360e6083075940a365bcafe311a`, **228/228 membres intègres**. Les **16 objets système ont toutes leurs sections `SHF_ALLOC` identiques octet par octet** entre B et H. Seuls `loco_core/basic_executor.c.obj` et `loco_core/basic_session_runtime.c.obj` changent dans leurs sections allouées ; cela ne les désigne **pas** comme cause prouvée des 220 octets. L'augmentation apparaît en sortie du linker Xtensa ; le mécanisme déclencheur précis de relaxation reste **non identifié**.

## Deux hypothèses ciblées, refusées au filtre sécurité avant modification

1. **Optimiser directement le code/littéraux dans les objets `esp_system`, `spi_flash`, `freertos`, `log`.** Attribution de la *sortie* démontrée, mais les objets `SHF_ALLOC` en entrée sont byte-identical : les changer signifierait patcher ESP-IDF, le traitement des interruptions, le flash-cache ou le linker. Ce n'est pas une modification source applicative ciblée démontrablement sûre ; **REJETÉE** (mandat interdit ISR/IRAM_ATTR/HAL/politique linker).
2. **Réécrire du code C99 côté `io/cpc_diag_policy.c` / CORE pour déplacer le layout final et inverser les relaxations.** Le premier saut historique suit bien une évolution C99/diagnostics, mais le diagnostic D1 ne prouve aucun appel ou relocation causale unique. Retoucher les diagnostics CPC scellés ou la sémantique CORE pour obtenir une taille favorable serait une optimisation de layout **spéculative et fragile**, non une récupération IRAM attribuée à un objet applicatif. **REJETÉE** (conformité CPC et interdiction des hacks d'alignement). Pas de troisième hypothèse.

**Décision de l'agent :** **aucun patch de production sûr démontré dans le mandat**, pas de modification de fréquence SPI, DMA, ISR, CORE, CMake, flags, budget ou comparateur C7. Ne pas confondre un résultat sous `67551` obtenu par simple relayout accidentel avec une économie sûre et maintenable.

## Qualification sur le véritable main après C7

La PR documentaire C8 garde uniquement cette preuve, un script d'audit facultatif et deux renvois documentaires. Elle déclenche explicitement les workflows **C7 RENDER-A** (par `docs/HW4-DISP-RENDER-A.md`) et **C7 SPI-C3** (par `firmware/esp32_display_probe/HW4-MEM-C8-A.md`) **sans toucher à leurs gates**. Ces deux workflows doivent reconstruire depuis les SHAs GitHub réels `base@4f8264c5b1fd370c185d687f5e03e92fe4c8f1e2` → `HEAD` et vérifier les deux fréquences, sans confondre les anciens ELF avec la base actuelle. Les CI Linux/Xtensa/OPT3/ARCH/CPC restent autoritatives sur leurs statuts réels.

**Pas de croissance DRAM/BSS attendue car aucun code exécutable ne change ; ce n'est pas un gain.** La qualification devra enregistrer les métriques réelles des deux builds. **Budget exploratoire : 0/6 builds Xtensa**, hors builds automatiques CI requis. **Bénéfice IRAM revendiqué : 0 octet ; cible 220 non atteinte.** Si les CI du HEAD ne prouvent pas les mesures, statut `BASE/HEAD MEASUREMENT_UNVERIFIED` et non PASS implicite.

## Risque, suite et autorité

Pas de code embarqué modifié, donc aucune réception CYD lancée ; `ON_DEVICE_UNVERIFIED` pour le SHA C8 et aucune extrapolation de #370. Les anciens LAB C6 restent rouges en raison des références épinglées obsolètes : dette séparée, **hors mission**.

Ce rapport **n'établit pas qu'une réduction est physiquement impossible** : il établit qu'avec les preuves autorisées, aucune des deux remédiations candidates n'a une attribution source sûre. **REMISE C8-A : BLOCKED — NO SAFE PATCH / ROOT_CAUSE_UNVERIFIED**, arbitrage exclusivement par Pilotage. Ne pas fusionner la PR documentaire comme une « résolution » de la dette +220.
