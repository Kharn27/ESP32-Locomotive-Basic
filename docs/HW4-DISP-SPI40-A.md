# HW4-DISP-SPI40-A — Qualification SPI LCD 40 MHz / repli 20 MHz

**Mandat Pilotage :** [Issue #286](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/286) ; **Parent :** [EPIC #285](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/285). Branche `feat/hw4-disp-spi40-safe`, base exacte `origin/main@355b9bd67ba8970abafcf67978854cebcb878273` (J1.23-C1). Les PR #274 (VSCR) et #281 (DMA 16 px) sont fermées **sans fusion** : aucun cherry-pick ni reprise.

**Statut de la mission : EN REVUE PILOTAGE / ON_DEVICE_UNVERIFIED tant que le PO n'a pas exécuté le protocole physique sur le HEAD exact.** Aucun gain de débit ou de rendu physique n'est revendiqué par les seuls builds.

## 1. Diff et architecture

- `CYD_LCD_SPI_HZ` : choix **CMake au build**, valeur **20000000** par défaut ; **40000000** uniquement si `LOCO_CYD_PROFILE=CONSOLE`. Rejet explicite des autres chaînes/valeurs (dont 55 MHz) et de 40 MHz sous HW3 ou BASIC_PROBE. Un garde préprocesseur du HAL répète la restriction à 20/40, même si l'option CMake était contournée.
- Le driver garde `LCD_HOST=SPI2_HOST`, broches MOSI13/CLK14/CS15/DC2/BL21, SPI mode 0, `trans_queue_depth=2` mais pipeline séquentiel par sémaphore, `cyd_lcd_send()` et `esp_lcd_panel_draw_bitmap()` inchangés. `CYD_LCD_DMA_BYTES=5120`, **un seul** buffer `MALLOC_CAP_INTERNAL|MALLOC_CAP_DMA` ; `max_transfer_sz=CYD_LCD_DMA_BYTES+16`, `LCD_TILE=8`, 320×8, même nombre de transactions et mêmes pixels.
- **Aucun changement runtime de fréquence** ; fallback uniquement par flash/reboot en **20 MHz** (nouvelle image du **même HEAD**). Une erreur LCD/DMA reste fail-stop, `s_fault` persistant, rétroéclairage éteint et buffer retenu ; **zéro retry / zéro reconfiguration après faute**.
- UART avant initialisation LCD : `HW4-SPI40 BOOT requested_spi_hz=... variant=SPI20|SPI40 ... effective_spi_hz=UNMEASURED electrical_spi_hz=UNMEASURED ... build_sha=<40 hex> build_version=... idf=... cpu_mhz=... dma_bytes=5120`. La fréquence `requested_spi_hz` est **le champ `io_cfg.pclk_hz` demandé à ESP-IDF**, **ni** une lecture du diviseur hardware **ni** une fréquence électrique mesurée. Sans analyseur logique, `EFFECTIVE/électrique = UNMEASURED` ; l'estimation temporelle ne confirme pas le SCLK électrique.
- Diagnostics minimaux CONSOLE : **8 octets** pour l'horodatage de début de RUN, **4 octets** pour le nombre de dirty flushes `sent==25` réussis (alignement BSS à mesurer dans ELF). Un `HW4-SPI40 RUN_DURATION elapsed_us=...` sort à la fin du RUN (temps wall ESP-IDF incluant le travail RUN, les repaints et leur UART ; hors saisie et prompt final). Un `HW4-SPI40 FULL25_COUNT` sort seulement à l'affichage des `LCD_METRICS` existants, **pas dans le hot-path DMA**.
- Le chemin `repaint_dirty()`, `cpc_video_flush_dirty()`, VRAM 16000, E2, palette, MODE0/1/2, marges 20+20, curseur, BASIC, BREAK, RUN quantum 8 et navigation restent inchangés. Pas de logger par pixel/bande, framebuffer, VSCR, 16px, nouvelle tâche ou profilage.

## 2. Référence analytique et limites d'interprétation

| Un repaint MODE1 complet (25 bandes) | SPI20 — contrôle | SPI40 — candidat |
|---|---:|---:|
| Fréquence LCD **demandée** dans `io_cfg.pclk_hz` | 20 000 000 Hz | 40 000 000 Hz |
| Fréquence **électrique constatée** | NON MESURÉE | NON MESURÉE |
| Bandes / DMA physiques | 25 × 320×8 | 25 × 320×8 |
| Pixels SPI utiles | **128 000 octets** | **128 000 octets** |
| Buffer DMA interne unique | 5 120 octets | 5 120 octets |
| Temps théorique de **bits utiles seuls** | 51,2 ms | 25,6 ms |
| Repaint observé p50/p95/max | **NON MESURÉ** | **NON MESURÉ** |
| RUN complet moyen / min / max | **NON MESURÉ** | **NON MESURÉ** |
| Défauts DMA, heap/pile, scintillement | **NON TESTÉ CYD** | **NON TESTÉ CYD** |

La borne théorique ne comprend ni commandes SPI, ni rendu CPU RGB565, ni attente FreeRTOS, ni transmission de logs. Il **ne faut pas** conclure à un gain ×2. Les mesures historiques de PR #281 (20 MHz, ancien HEAD, p50 187780 µs / p95 187940 µs OFF) ne sont **pas** une cellule de comparaison du présent A/B.

**Métriques réellement disponibles** : `HW4-C3-B2-C1 LCD_METRICS` contient `flushes`, `bands`, `spi_bytes`, `repaint_us_total`, `repaint_max_us` et **p50/p95 bornes supérieures de l'histogramme, sur TOUS les flushes** ; pas des quantiles exacts full25. `HW4-SCROLL-A0 CLASS` distingue `ordinary` / `scroll_associated` (association non exclusive avec d'autres mutations), avec compteurs/histogrammes analogues. `HW4-SPI40 FULL25_COUNT` compte les flushes dirty complets **réussis**, exclut les 30 bandes du boot. Aucun vrai p50/p95 full25 n'est exposé : ne pas étiqueter les bornes globales comme « full25 exactes ». `RUN_DURATION` relève le wall time jusqu'au terminal du RUN. `spi_bytes` est **le volume de pixels attribué aux bandes confirmées**, hors commandes de fenêtre LCD.

Pour comparer des fenêtres, privilégier un **reboot contrôlé avant chaque variante**, la même série de commandes et un nombre de flushes/bandes/scrolls comparable. Calculer le temps moyen d'affichage global comme `repaint_us_total / flushes`, en étiquetant cette moyenne **tous flushes** ; le full25 reste une classe observée par *compteur*, pas par latences dédiées.

## 3. Tests et preuves à vérifier sur HEAD final

La CI historique requise est **CI-C99** GCC/Clang × ASan/UBSan OFF/ON, **CI-ARCH**, **CI-OPT3**, **CI-CPC-PERMANENT** et **CI-XTENSA** ESP-IDF 5.5.6 **CONSOLE/HW3/BASIC_PROBE**. Les oracles CPC scellés sont utilisés **sans modification**, leur PASS ne qualifie pas le matériel.

Test hôte dédié, sans compilateur Xtensa :

```sh
python3 tools/ci/hw4_spi40_policy.py
```

Il exécute la **vraie** politique CMake avec `cmake -P` : CONSOLE défaut/20/40, HW3/BASIC_PROBE défaut/20, refus de 13 valeurs invalides (dont 55 MHz) et refus de 40 pour HW3/BASIC_PROBE. Les assertions statiques protègent les broches, 5120 o, SPI2, DMA, sémaphore/fail-stop, 8 px, aucun VSCR, etc. Cela ne reproduit **pas** une horloge physique.

Jobs de qualification dédiés dans le workflow existant [CI-XTENSA : jobs spi40-host-policy et spi40-dual-console](../.github/workflows/ci-xtensa.yml) : **deux véritables compilations Xtensa CONSOLE**, 20 et 40 MHz sous **le même SHA** et mêmes version/CPU, avec CMakeCache, compile flag `LCD_CLOCK_HZ=...`, ELF, `size`, SHA-256 du binaire et manifeste. La CI trois profils indépendante utilise toujours **20 MHz par défaut** ; elle ne remplace pas les deux variantes explicites. Les artefacts de ces jobs et les résultats de la comparaison mémoire DRAM/BSS/IRAM/Flash sont à coller dans la PR sur HEAD final, sans inventer de métriques de carte.

**Preuves binaires effectivement observées sur le HEAD code `f88ac5cd62cf6a8d6ce117419c9bc910744bf4cf` :** [CI-XTENSA #41627910770](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41627910770), CONSOLE/HW3/BASIC_PROBE 3/3 PASS et CONSOLE SPI20/SPI40 2/2 PASS ; [garde A0 #41627910691](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41627910691) 3/3 PASS. La base du tableau est **la référence historique A0 `5799c774...`**, pas `main@355b9bd...`. Le HEAD final (après documentation) doit confirmer ces mêmes sections et produire ses propres hashes/identités.

| Sections ESP-IDF ou BIN (octets) | A0 historique | SPI20 f88 | SPI40 f88 |
|---|---:|---:|---:|
| Flash code | 123166 | **157594** | **157590** |
| Flash rodata | 50340 | **54260** | **54260** |
| IRAM `size -A` | 67332 | **67332** | **67332** |
| DRAM incl BSS | 53728 | **53984** | **53984** |
| BSS | 42656 | **42912** | **42912** |
| Binaire `.bin` | 252320 | **290656** | **290656** |
| Delta DRAM vs A0 / budget | référence | **+256 / +256 : PASS, marge 0** | **+256 / +256 : PASS, marge 0** |
| Heap libre/largest/min + pile (CYD) | N/A | **NON MESURÉ** | **NON MESURÉ** |

Le faible écart de Flash code (4 octets) est une **observation de build**, pas une mesure de fréquence électrique. `idf.py size` affiche IRAM 67331 alors que la somme des sections `size -A` affiche 67332 : ne pas confondre les méthodes. Le binaire change de SHA-256 avec `HW4_SHOT_GIT_SHA` au nouveau commit ; consulter les manifestes **HEAD final** de la PR, ne pas flasher les anciens artefacts f88.

**Contrôle de configuration des deux variantes après les builds :**

```sh
sha256sum sdkconfig.hw4-spi20 sdkconfig.hw4-spi40
diff -u sdkconfig.hw4-spi20 sdkconfig.hw4-spi40
grep -F 'CYD_LCD_SPI_HZ:STRING=' build-hw4-spi20/CMakeCache.txt build-hw4-spi40/CMakeCache.txt
```

Les deux sdkconfig devraient être identiques : la seule sélection de la fréquence LCD est le `-DCYD_LCD_SPI_HZ=...` CMake, non une configuration ESP-IDF. Toute autre différence doit être expliquée et soumise au Pilotage. Les `*.bin` produits depuis le même HEAD diffèrent normalement par le paramètre compilé, mais cela ne prouve pas une fréquence électrique effectivement atteinte.

La HAL alloue toujours **un seul buffer DMA interne de 5120 o** ; la mémoire heap libre/plus grand bloc et la marge pile seront mesurées exclusivement sur le CYD.

## 4. Protocole reproductible PO : deux firmwares, même HEAD

**Matériel** : même ESP32-2432S028R **sans PSRAM**, ILI9341, même câble/alimentation, même terminal série, ESP-IDF **v5.5.6**, CPU **160 MHz** (vérifier UART `cpu_mhz=160`), même orientation/case10, essais à température et luminosité similaires. Conserver les logs **depuis RESET/EN**, la sortie console et les vidéos/photo du vrai écran.

**Exiger le SHA final complet communiqué dans la REMISE DÉVELOPPEUR**, puis vérifier :

```sh
git fetch origin
git switch feat/hw4-disp-spi40-safe
git rev-parse HEAD             # DOIT être le SHA figé communiqué
idf.py --version              # ESP-IDF v5.5.6
cd firmware/esp32_display_probe
```

**Variante SPI20 — contrôle et fallback** (dossier, sdkconfig et artefact dédiés) :

```sh
idf.py -B build-hw4-spi20 -DSDKCONFIG="$PWD/sdkconfig.hw4-spi20" \
  -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=20000000 set-target esp32
idf.py -B build-hw4-spi20 -DSDKCONFIG="$PWD/sdkconfig.hw4-spi20" \
  -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=20000000 build
sha256sum build-hw4-spi20/loco_esp32_display_probe.bin
idf.py -p /dev/ttyUSB0 -B build-hw4-spi20 flash
script -q -f -c 'idf.py -p /dev/ttyUSB0 -B build-hw4-spi20 monitor' spi20.uart.log
```

Vérifier `BOOT requested_spi_hz=20000000 variant=SPI20 ... electrical_spi_hz=UNMEASURED ... build_sha=<HEAD>`. Après démarrage du moniteur, presser **EN/RESET** une fois pour inclure la totalité du boot. Enregistrer le log et les photos, sortir avec **Ctrl+]**.

**Variante SPI40 — candidat** (depuis le **même SHA**, sans changer aucune source ; ne pas effacer les logs précédents) :

```sh
idf.py -B build-hw4-spi40 -DSDKCONFIG="$PWD/sdkconfig.hw4-spi40" \
  -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=40000000 set-target esp32
idf.py -B build-hw4-spi40 -DSDKCONFIG="$PWD/sdkconfig.hw4-spi40" \
  -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=40000000 build
sha256sum build-hw4-spi40/loco_esp32_display_probe.bin
idf.py -p /dev/ttyUSB0 -B build-hw4-spi40 flash
script -q -f -c 'idf.py -p /dev/ttyUSB0 -B build-hw4-spi40 monitor' spi40.uart.log
```

Vérifier `requested_spi_hz=40000000 variant=SPI40` et le **même `build_sha`**. Cela prouve le *paramètre compilé*, pas la fréquence électrique. Reproduire **exactement** la même suite fonctionnelle que SPI20 :

1. Après boot, relever `HW4-C2 DEVICE_MEMORY stage=interactive_ready` et `LCD_INIT_PASS dma_bytes=5120`. Vérifier écran, palette, alignement, **marges 20+20**, texte et curseur, pas de reset/panic ni backlight irrégulier.
2. Saisir **une ligne à la fois**, en observant la réponse après chaque ligne : `!CLS`, `NEW`, puis le programme témoin ci-dessous et `LIST`. S'assurer de sa fidélité via UART et inspection de l'écran.
3. Lancer **trois RUN complets au minimum** avec le **même programme**, un RUN par ligne UART et la fin `RUN_TERMINAL` avant le suivant. Sauvegarder les trois `HW4-SPI40 RUN_DURATION elapsed_us` et les états `LCD_METRICS`, `FULL25_COUNT`, `HW4-SCROLL-A0 CLASS`. Distinguer scroll/dirty partiel/full25 ; ne pas inférer un full25 à chaque scroll.
4. Faire `LIST`, `!CLS`, `LIST`, `RUN` et un long défilement dans les deux sens (UP/DOWN CSI ESC[A / ESC[B, franchissement bord haut et bas documenté). Tester le curseur, l'E2, le texte, `BREAK` sur un RUN prolongé approprié, la rotation courte 10↔9 et le retour au prompt. **Aucun scintillement, tearing, ghosting, bord cassé ou corruption intermittente**.
5. Relever `DEVICE_MEMORY stage=after_line/run_terminal` : `heap8_free`, `heap8_largest`, `heap8_min`, `stack_margin_bytes`, `dma_fault=0`, `dma_timeouts=0`, `lcd_error=ESP_OK` ; vérifier répétitions et reboot. Photographier/filmer pendant les scrolls, pas uniquement au repos.

Programme historique (si `CLS` natif diffère sur ce HEAD, documenter précisément l'échec et ne pas le masquer par un remplacement silencieux) :

```basic
5 CLS
10 FOR I%=1 TO 40
20 PEN 3:PRINT "ROUGE"
30 PEN 1:PRINT "JAUNE"
40 NEXT I%
50 END
RUN
```

**Retour sûr 20 MHz après SPI40** : arrêter le monitor (Ctrl+]), exécuter **de nouveau** `idf.py -p /dev/ttyUSB0 -B build-hw4-spi20 flash` puis `script -q -f -c 'idf.py -p /dev/ttyUSB0 -B build-hw4-spi20 monitor' spi20-return.uart.log`, appuyer sur RESET/EN et vérifier BOOT SPI20, image et console. Une faute DMA SPI40 **ne déclenche jamais** de fallback automatique dans la même session.

**Remise au Pilotage** : les trois logs UART bruts, la sortie `git rev-parse HEAD`, les SHA-256 des deux fichiers `.bin`, IDs des builds/artefacts CI, versions IDF/CPU, tableau OFF20/ON40/RETOUR20 des flushes/bandes/pixels, stats histogrammes avec **bornes supérieures** correctement nommées, nombre réel full25, moyennes des RUN (≥3) et dispersion, anomalies visuelles horodatées, photos/vidéos, heap/largest/min, stack, fautes/timeouts. Ni `!SHOT` ni un CRC logique ne prouvent la GRAM physique.

## 5. Verdict différé au Pilotage

| Critère | Pré-CYD | Après essais PO |
|---|---|---|
| 20/40 seulement, défaut 20, profil CONSOLE uniquement | À vérifier CI | — |
| CI Linux + Xtensa 3/3 et CONSOLE 20/40 | À vérifier HEAD | — |
| Diff transport 5120/8px/fail-stop inchangé | À vérifier source & test | — |
| Qualité physique SPI40 | **ON_DEVICE_UNVERIFIED** | À renseigner PO |
| Fallback après flash/reboot SPI20 | **ON_DEVICE_UNVERIFIED** | À renseigner PO |
| Repaint/RUN p50/p95/temps, bénéfice perceptible | **NON MESURÉ** | À renseigner PO |
| GO 40 / NO-GO 40 | **AUCUNE DÉCISION DEV** | **PILOTAGE SEUL** |

**STOP** : scintillement, tearing, corruption, DMA fault/timeout, heap ou pile insuffisants, fallback défaillant, régression de programme/curseur/BREAK, ou SHA différent. Ne pas fusionner une configuration douteuse. Ce mandat ne permet aucun profilage avancé, double buffering, DMA 16px, accélération de rendu ou lancement d'un autre enfant de l'EPIC.
