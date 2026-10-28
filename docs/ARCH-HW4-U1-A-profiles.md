# ARCH-HW4-U1-A — Trois profils, une seule racine ESP-IDF

**Mandat Pilotage :** [issue #140](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/140) ; architecture parente [#112](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/112). Branche de livraison `feat/arch-hw4-u1-a-unified-profiles`. Base réelle **`main@0072b8400379ebb52c93a0c1ea45c4c5a53e0dd8`** (inclut J1.14-B). **U1-B interdit.**

## Contrat : pas de nouvelle racine PO

Le seul projet **de référence** reste `firmware/esp32_display_probe/`. Son `project(loco_esp32_display_probe)`, `sdkconfig.defaults` (ESP32 classique, 4 Mio Flash, sans PSRAM, tâche principale 6 144 octets), `partitions.csv` (factory à 0x10000, 3 Mio) et le `build/` VS Code restent inchangés. Le PO sélectionne seulement la branche dans VS Code et utilise ses boutons **Build / Flash / Monitor** habituels. Sans `-D`, la console est sélectionnée : aucun `set-target`, `fullclean`, `-B` ou workspace nouveau n'est requis.

| Profil `LOCO_CYD_PROFILE` | `app_main` compilé (un seul) | Composants et source | Sens |
| --- | --- | --- | --- |
| `CONSOLE` **défaut** | `firmware/esp32_display_probe/main/hw4_c2_console.c` | vidéo CPC, UART, `loco_core`, LCD partagé | Produit BASIC 1.1 sur LCD/UART |
| `HW3` | `firmware/esp32_display_probe/main/main.c` | vidéo CPC, police, `loco_core`, LCD partagé | Diagnostics des MODE 0/1/2 et de l'orientation |
| `BASIC_PROBE` | **source originale** `firmware/esp32_probe/main/main.c` | `loco_core` original, LCD partagé, sans écran activé | Diagnostic C99 ABI, NMIN/REAL5 et valeurs limites |

Le composant C99 unique demeure dans `firmware/esp32_probe/components/loco_core/CMakeLists.txt` : les deux projets continuent de pointer sur les dix sources **`core/*.c` identiques** et leur `-std=c99`. La sonde BASIC utilise son **fichier source d'origine directement**, pas une copie. Le pilote `firmware/components/cyd_ili9341` demeure propriétaire unique SPI2/LCD/DMA. `firmware/esp32_probe/` est **conservé fonctionnel pour rollback** ; le supprimer, déplacer son descripteur ou renommer la racine PO relève d'U1-B ou d'une décision séparée.

## Sélection / compatibilité

Pour des caches isolés de CI (jamais exigés du PO) :

```sh
cd firmware/esp32_display_probe
idf.py -B build-u1-console -DLOCO_CYD_PROFILE=CONSOLE build
idf.py -B build-u1-hw3 -DLOCO_CYD_PROFILE=HW3 build
idf.py -B build-u1-basic -DLOCO_CYD_PROFILE=BASIC_PROBE build
```

Compatibilité historique : `-DHW4_C2_CONSOLE=ON` sélectionne `CONSOLE` ; `OFF` sélectionne `HW3` dans un cache neuf. La variable canonique est `LOCO_CYD_PROFILE`. Si les **deux** options existent, elles doivent correspondre exactement (`CONSOLE/ON` ou `HW3/OFF`) ; `BASIC_PROBE` et une option `HW4_C2_CONSOLE` simultanée sont incompatibles. Le cache est un choix persisté : changer de profil dans un cache existant réclame de mettre à jour les options cohérentes ou d'utiliser un cache distinct. Les noms inconnus, valeurs vides et ambiguïtés sont **rejetés explicitement** (aucun fallback vers un faux firmware). Les valeurs sont sensibles à la casse.

## Baseline au même `main` de départ

[CI Xtensa main @0072b840](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40772491538), ESP-IDF v5.5.6 ; ordre console historique / HW3 historique / sonde BASIC autonome :

| Ancienne image | Flash Code | IRAM | DRAM | Taille image ESP-IDF |
| --- | ---: | ---: | ---: | ---: |
| Console `HW4_C2_CONSOLE=ON` | 111 082 | 67 279 | 49 368 | 237 533 |
| HW3 `HW4_C2_CONSOLE=OFF` | 82 878 | 67 279 | 31 520 | 208 753 |
| `firmware/esp32_probe` autonome | 74 990 | 51 807 | 31 020 | 166 477 |

Les nouvelles variantes doivent être mesurées **dans la même matrice U1-A**, avec comparaison au témoin ancien sur la même branche et aux chiffres ci-dessus. Un écart de **plus de 2 048 octets DRAM ou IRAM console** bloque la livraison sans nouvel arbitrage Pilotage. Les ELF/BIN ne sont **pas** supposés identiques bit à bit si chemins de liaison et descripteurs diffèrent.

## Portes de preuve

Le workflow Xtensa permanent conserve le job historique `three-variants` (console/HW3 + sonde autonome) ; le job `u1-a-profile-parity` ne s'exécute que sur la branche U1-A. Il teste :
- 15 sélections positives/négatives réelles dans `profile_select.cmake` (dont options contradictoires et valeurs inconnues) et les symboles `app_main` uniques ; tests négatifs d'un zéro/double symbole ;
- compilations de **trois images dans trois caches de la racine actuelle**, traces `idf.py size` et `size-components`, contrôle appdesc du SHA Git courant pour les trois, ABI `loco_probe_abi_sizes`, invariants 4 Mio / partitions / absence PSRAM ;
- compilation de l'**ancienne sonde** pour rollback et comparaison **octet pour octet des sorties de l'extracteur ABI**, pas des images ;
- refus de configurer un profil inconnu ou un mélange de sélecteurs.
Le job `po-standard-build` réalise le scénario Git `main → branche` dans **le même `firmware/esp32_display_probe/build/`**, avec `idf.py build` seul, puis `verify_esp_app_version.py` pour rejeter un appdesc périmé. La CI C99 (GCC/Clang, OFF/ON ASan-UBSan), CPC permanente et indépendante, CI-ARCH et scrolling demeure inchangée.

## Barrières et essai matériel

Le logiciel `core/`, les entrées UART et BASIC, la vidéo E2, la police, l'écran et la politique DMA **ne sont pas modifiés** par cette migration. Le profil HW3 porte les modes 0/1/2 historiques ; leur compilation ne vaut pas un test de la carte sur chacun. La nouvelle sonde conserve l'ABI NMIN/REAL5 ; son `sdkconfig` utilise la pile 6144 du projet partagé, versus 4096 dans le projet historique distinct (aucune diminution du budget console).

**CYD : `ON_DEVICE_UNVERIFIED` jusqu'au nouveau PASS PO sur le HEAD final.** Une fois la CI complète verte, demander exclusivement la sélection de branche, Build/Flash/Monitor sur le projet actuel ; vérifier `version=<HEAD>`, `BASIC 1.1` / `Ready`, curseur inverse, éditions gauche/Backspace/Suppr, `10 PRINT 2` / `20 PRINT 3`, `LIST`/`RUN`/`NEW`, quelques scrolls et `!CLS`. Relever `dma_fault=0`, `dma_timeouts=0`, heap libre/largest et marge pile si imprimées. Le PO transmet `PASS/FAIL` et un extrait UART, sans photo obligatoire et sans manipulations Git.

**Portes maintenues :** U1-B, COPY, F1 DMA et nouveau projet `firmware/locomotive_cyd` **non autorisés**. La revue, l'acceptation et la fusion dans `main` appartiennent exclusivement au Pilotage.
