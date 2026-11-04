# HW4-DISP-PROFILE-A-C2 — Intégration main / réception CYD SPI20

**C3 RECTIFICATIF PILOTAGE 03/11/2026 : la campagne CYD SPI20 de C2 est ANNULÉE. Ne pas flasher de firmware SPI20 pour cette campagne. CONSOLE vise SPI40 ; repli SPI20 constructible seulement. Se reporter à `docs/HW4-DISP-PROFILE-A-C3.md` pour la seule fiche opératoire actuellement en vigueur. Aucune mesure SPI40 réelle n'a encore été obtenue.**


**Mandat :** [arbitrage Pilotage C1 et ordre C2 du 03/11/2026](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/297#issuecomment-6608050032) ; PR [#297](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/297) **Draft, non fusionnée**. Parent [#295](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/295). **La recette du PO ne commence que sur instruction du Pilotage, après réception de la CI et du budget du HEAD final.**

## 1. Sources GitHub et intégration sans conflit

| Provenance | SHA GitHub |
|---|---|
| Base initiale de la PR | `9f19e500a9a46f1e16121ebc5c678202d7e52d82` |
| C1 qualifié avant intégration | `006369ec2797fcb948cb9b5dfa8106dfadfee8c4` |
| Nouveau `main` mandaté | `2d0487338a50c8592a77d3b909bdb74618d3b778` |
| Commit d'intégration de `main` sur la branche PR | `60cf74658b56ca08fe23f46461e85c56a888c045` |

L'intégration GitHub est un merge à **deux parents** (`006369ec`, `2d048733`), sans rebase destructif : arborescence de `main@2d048733` plus les **14 fichiers modifiés par la PR**. Les quatre chemins modifiés par le nouveau `main` (`docs/HW4-DIAG-SYNTAX-A.md`, `io/cpc_diag_policy.{c,h}`, `tests/test_hw4_diag_a.c`) ne recoupent aucun chemin modifié par la PR. Les diagnostics BASIC sont conservés **à l'identique**, et l'instrumentation C1 aussi.

**HEAD à flasher :** celui vérifié par GitHub dans la PR après les commits de documentation C2, pas le SHA d'intégration intermédiaire ci-dessus. Le Pilotage le confirme dans sa transmission au PO.

## 2. Dérogation limitée, jamais présentée comme garde PASS

La limite d'origine du garde HW4 A0 est **DRAM ≤ A0 historique +256 octets**, mesurée par `tools/ci/hw4_a0_compare_memory.py`. Elle **n'est pas changée** : son échec CONSOLE reste explicitement `FAIL_A0_EXCEPTION_AUTHORIZED`, pas PASS.

**Arbitrage particulier uniquement pour ce profilage CONSOLE SPI 20 MHz** : `DRAM ≤ 54664` octets, `IRAM = 67331` octets. À titre de provenance : A0 `53728` ; base initiale main `53968` ; C1 `54664`, soit **+696 octets propres à l'instrumentation par rapport à main d'origine**, et +936 octets par rapport à A0 (dont +240 préexistants). La différence +680 par rapport à l'ancien plafond n'est pas une norme future.

Les **valeurs du firmware intégré** doivent provenir des artefacts Xtensa et A0 du *nouveau HEAD exact*. Ne pas copier les valeurs C1 : si DRAM dépasse 54664 ou si IRAM change, **SUSPENDRE** la dérogation et **NE PAS** flasher ni demander un test au PO avant un nouvel arbitrage.

C99 natif, 3 classes `full25` / `partial` / `scroll_associated`, 12 bins uint32, cumuls uint64, 16 traces, DMA **5120 octets** séquentiel, SPI **20 MHz**, fail-stop, CYD sans PSRAM. Aucun réglage RENDER/DMA/PACING/SPI40 ne relève de C2.

## 3. Contrôle CI préalable par le Pilotage

Sur le **HEAD final** : CI-C99 **4/4** GCC/Clang ASan-UBSan OFF/ON (plus négatifs), CI-ARCH, CI-OPT3, CI-CPC-PERMANENT, CI-XTENSA **3/3** CONSOLE/HW3/BASIC_PROBE, HW4-EDIT-P1, HW4-C3-B2 doivent être PASS. Le garde A0 original reste rouge en CONSOLE et son écart doit être expliqué. Recouper `xtensa-esp-elf-size -A` dans l'artefact CONSOLE : `.dram0.*`, `.dram0.bss`, `.iram0.*`, `.flash.text`, `.flash.rodata` ; archiver le binaire, hash et SHA.

**Pas de qualification physique à partir de CI.** Un build Xtensa et un test hôte n'établissent pas la marge réelle du CYD.

## 4. Opérations PO — UNE seule campagne, uniquement après GO Pilotage

Conditions : CYD ESP32-2432S028R, ESP-IDF **v5.5.6**, dépôt cloné et port série accessible ; pas de PSRAM. Le Pilotage fournit le **SHA complet final**. Adapter le port USB seulement ; ne modifier aucun paramètre SPI.

Depuis la racine du dépôt :

```sh
git fetch origin
git switch feat/hw4-disp-profile-a
git pull --ff-only
git rev-parse HEAD  # doit correspondre au SHA complet reçu du Pilotage
git merge-base --is-ancestor 2d0487338a50c8592a77d3b909bdb74618d3b778 HEAD
idf.py --version     # attendu ESP-IDF v5.5.6
cd firmware/esp32_display_probe
idf.py -B build-hw4-disp-c2 -DLOCO_CYD_PROFILE=CONSOLE set-target esp32
idf.py -B build-hw4-disp-c2 -DLOCO_CYD_PROFILE=CONSOLE build
idf.py -p /dev/ttyUSB0 -B build-hw4-disp-c2 flash
script -q -f -c 'idf.py -p /dev/ttyUSB0 -B build-hw4-disp-c2 monitor' hw4-disp-c2-spi20.uart.log
```

Dans le monitor, appuyer une fois sur **EN/RESET** pour inclure un boot complet. Confirmer `HW4-DISP-PROFILE BOOT spi_request_hz=20000000 ... sha=<SHA>`, `HW4-C2 LCD_INIT_PASS dma_bytes=5120` et `ORIENTATION_PASS case=10`. Observer l'écran : couleurs jaune/rouge, texte, lisibilité, défilement et éventuelle « guirlande » ; **aucune vidéo n'est demandée**.

Saisir littéralement les lignes suivantes dans l'ordre, entrée après chaque ligne :

```basic
!CLS
NEW
5 CLS
10 FOR I%=1 TO 40
20 PEN 3:PRINT "ROUGE"
30 PEN 1:PRINT "JAUNE"
40 NEXT I%
50 END
LIST
RUN
RUN
RUN
```

Attendre `RUN_TERMINAL` entre les RUN. Après le troisième : `LIST`, puis `!CLS`. Ne pas utiliser SPI40 ; pas de RUN infini, aucune commande BREAK nécessaire.

**Conserver la sortie UART brute** de la seule session, idéalement avec le SHA exact du commit, le résultat `git rev-parse HEAD` et la preuve build/flash. Elle doit inclure pour chacun des trois RUN : `RUN_DURATION`, `SUMMARY`, les 3 `CLASS`, `TRACE_INFO` et les `TRACE`, les rapports `HW4-SCROLL-A0 CLASS`, `LCD_METRICS`, `DEVICE_MEMORY`, `CLOCK_OVERHEAD_ESTIMATE`. Contrôler pour chaque stade pertinent :

- `dma_fault=0`, `dma_timeouts=0`, `lcd_error=ESP_OK` ;
- `heap8_free`, `heap8_largest`, `heap8_min`, `stack_margin_bytes` mesurés sur carte réelle ;
- le déroulement des 3 RUN, l'absence de reset inattendu/fail-stop, les observations visuelles de l'écran.

En cas d'erreur SPI/LCD, de WDT, de trace incohérente ou de marge insuffisante, arrêter : résultat **FAIL ou NON QUALIFIÉ** et joindre l'UART sans « corriger » la mesure sur place. Aucune comparaison 20/40.

Les statistiques de `scroll_associated` recouvrent `full25`/`partial` : **ne pas sommer** les trois vues. `p50_upper`/`p95_upper` sont des **bornes d'histogramme**, pas des percentiles optiques exacts. Les phases sont des durées *wall*, pas des cycles CPU isolés.

## 5. Critères de remise après la campagne

Réception par le Pilotage des 3 RUN (durée, classes, p50/p95 bornés, phases, coalescence et gaps), mesures de heap/pile/DMA/LCD, statut d'affichage visuel, fichier UART **brut**, SHA flashé, statut `ON_DEVICE_PO_REPORTED_PASS` seulement si toutes les preuves sont cohérentes. Aucun test sur un ancien SHA C1 ne qualifie C2. **Le Pilotage seul accepte et fusionne** ; la PR reste Draft et non fusionnée jusqu'à sa décision.
