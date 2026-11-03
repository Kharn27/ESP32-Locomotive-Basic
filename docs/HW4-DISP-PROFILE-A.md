# HW4-DISP-PROFILE-A — profilage MODE1 reproductible (#295)

**C3 RECTIFICATIF PILOTAGE 03/11/2026 : la campagne CYD SPI20 de C2 est ANNULÉE. Ne pas flasher de firmware SPI20 pour cette campagne. CONSOLE vise SPI40 ; repli SPI20 constructible seulement. Se reporter à `docs/HW4-DISP-PROFILE-A-C3.md` pour la seule fiche opératoire actuellement en vigueur. Aucune mesure SPI40 réelle n'a encore été obtenue.**


**Statut : mesure logicielle instrumentée, réception CYD NON VÉRIFIÉE.** Parent #285.
Base GitHub de départ : `main@9f19e500a9a46f1e16121ebc5c678202d7e52d82` (03/11/2026).
Référence exclusivement **main à SPI 20 MHz**. #286 / PR #289 fermée sans fusion, pas de reprise du 40 MHz. HEAD de livraison = HEAD de la PR (à vérifier au flash).
ESP-IDF v5.5.6, ESP32 CYD classique sans PSRAM, CPU 160 MHz, un buffer DMA de 5120 octets, 320×200 MODE1.

## 1. Mesures, frontières et vérité des libellés

La boucle vidéo / le plan de contrôle BASIC ne sont **pas optimisés** ; quantum RUN=8, 25 bandes de 8 px, ESP-LCD, sémaphore et fail-stop restent identiques.

| Champ UART | Mesure | Limite de l'interprétation |
|---|---|---|
| `render_pack_us` | Horloge wall de la construction RGB565 d'une bande : `cpc_video_render_row`, palette et repack octets | **Pas** du CPU pur : préemption possible ; exclut le scroll logique |
| `submit_us` | Wall autour de `esp_lcd_panel_draw_bitmap` | Soumission côté driver ; pas la durée physique des bits SPI |
| `sem_wait_us` | Wall entre retour de `draw_bitmap` et retour de l'attente du sémaphore | Peut inclure l'attente DMA, l'ordonnanceur et la signalisation ISR ; **pas** un débit SPI |
| `other_us` | Total repaint wall moins somme des trois phases précédentes | Orchestration + horodatages non attribués ; non assimilable à CPU |
| `scroll_wall_outside_repaint_us` | Wall autour de `cpc_video_scroll_up` (VRAM + E2 + dirty) dans la sortie texte | Survient **avant** le repaint ; **NE PAS additionner** au repaint |
| `wall_us` | `esp_timer_get_time` avant/après `cpc_video_flush_dirty` | Retour de l'attente DMA, **pas** une preuve optique de GRAM visible |
| `completion_gap_us` | Intervalle entre deux retours de flush réussis, y compris calcul BASIC entre les deux | Proxy de cadence de `repaint_completed`, **pas FPS physique** |
| `scrolls` | `pending_up + pending_down` de HW4-SCROLL-A0 à la fin d'un repaint | Cumul depuis le repaint précédent ; 0, 1 ou plusieurs ; inclut navigation ; ne garantit pas autant d'images distinctes |

Le temps du repaint est **non recouvert** au niveau de notre boucle synchrone ; le driver peut effectuer du travail interne dans la soumission. Les groupes `full25` (exactement 25 bandes) et `partial` (1–24 bandes) sont disjoints. `scroll_associated` est **une vue filtrée recouvrante** de ces deux catégories, pas une troisième contribution à sommer. Les bandes des marges lors de `repaint_full` au boot/rotation ne sont pas comptées comme `full25`.

La distribution classe `n`, `min_us`, `mean_us`, `p50_upper_us`, `p95_upper_us`, `max_us` utilise 12 **intervalles bornés** (500, 1000, 2000, 4000, 8000, 16000, 32000, 64000, 128000, 256000, 512000, +∞ µs). Les percentiles sont **bornes supérieures**, jamais des p50/p95 exacts ; la dernière borne est `UINT32_MAX` (overflow/saturation : ne pas lire comme une durée précise). `bands`, `bytes`, `wall_us`, les phases et `scrolls` sont des **sommes**. `zero/one/multi` sont les fréquences de scrolls logiques par repaint. Le ring `TRACE` conserve au plus les **16 derniers repaints terminés** dans l'ordre, avec troncation signalée. Tout ajout hors borne échoue sans modifier une statistique précédemment acceptée ; `rejected` signale un rejet d'échantillon.

Les groupes sont remis à zéro **au démarrage de chaque RUN** ; la trace de `LIST/!CLS` après un RUN reflète les interactions supplémentaires, sans constituer un nouveau RUN. `RUN_DURATION core_us` couvre les slices BASIC/RUN et les repaints des yields, **pas** le prompt final ni les impressions terminales ; `run_terminal_after_prompt` inclut un éventuel repaint final. Ne pas comparer cette fenêtre au chronométrage expérimental de #289 comme un A/B.

## 2. Surcoût et budget

Instrumentation uniquement CONSOLE pour l'agrégation et le journal : `Hw4DispProfile` statique, ≤896 octets, ring de 16 samples, aucune allocation dynamique, aucune ligne UART par pixel, bande ni quantum RUN. `CpcText` porte un horodatage facultatif en cas de scroll (2 lectures d'horloge par scroll) ; les appelants C99 non instrumentés ne l'activent pas. Le pilote LCD garde l'API d'origine `cyd_lcd_send()`; la nouvelle `cyd_lcd_send_profiled()` mesure la soumission et l'attente sans remplacer le protocole, ni le buffer.

Par bande : **2 appels** `esp_timer_get_time` autour du rendu + **3 appels** au pilote pour soumission/attente ; par repaint : **2 appels** ; par scroll : **2 appels**. Un full25 coûte donc environ **127 appels d'horloge**, hors scrolls. La ligne `CLOCK_OVERHEAD_ESTIMATE` calibre un surcoût approximatif au boot (boucle témoin soustraite) ; son `net_upper_us_per_call` est une **estimation haute bruyante**, pas un étalonnage garanti. `bench_hw4_disp_profile` imprime une estimation **hôte seulement**, non transférable à Xtensa. Il n'y a pas d'A/B physique instrumenté/OFF exigé du PO. Si l'overhead estimé devient une part importante des 189 ms, **interdire une conclusion causale sans nouvelle qualification**.

Suivre dans la CI Xtensa les deltas **CONSOLE/HW3/BASIC_PROBE** de DRAM, BSS, IRAM et FLASH, et sur CYD les `heap8_free`, `heap8_largest`, `heap8_min`, `stack_margin_bytes`, `dma_fault`, `dma_timeouts`. Le garde historique HW4-A0 (`tools/ci/hw4_a0_compare_memory.py`) possède une limite de +256 octets DRAM par rapport à une ancienne base ; ce contrôle peut **bloquer une instrumentation additionnelle même modeste**. Ne pas l'assouplir sans arbitrage Pilotage. Toute régression réelle ou dépassement reste un STOP.

## 3. Tests hôte et barrières CI

Depuis la racine du dépôt :

```sh
cmake -S . -B build-profile -DCMAKE_BUILD_TYPE=Debug -DBP_SANITIZERS=OFF
cmake --build build-profile --parallel
ctest --test-dir build-profile --output-on-failure
ctest --test-dir build-profile --output-on-failure -R hw4_disp_profile
```

Répéter en `BP_SANITIZERS=ON`, compilateurs GCC et Clang. Le test `hw4_disp_profile_accounting` couvre full25 vs partial, 3 scrolls pour 0 flush puis 1 flush, scroll unique, 0 scroll, vues recouvrantes, quartiles bornés et inclusivité, chronologie/ring 16, séquence tronquée, durées et bandes incohérentes, timestamps régressifs et overflow des compteurs. `hw4_disp_profile_host_overhead` n'impose **aucun seuil de vitesse hôte**.

CI requises sur **HEAD final** : CI-C99 4 cellules, CI-ARCH, CI-OPT3, CI-CPC-PERMANENT, CI-XTENSA 3/3 (CONSOLE/HW3/BASIC_PROBE) ; vérification additionnelle du garde mémoire A0. **Les résultats ne sont pas présumés verts avant publication des runs du HEAD.** Aucun oracle CPC nouveau : aucune règle/token BASIC modifiée.

## 4. Protocole PO — UNE variante SPI 20 MHz, UNE courte session

**Ne flasher que le HEAD exact publié dans la REMISE DÉVELOPPEUR / PR**, et seulement après préparation du binaire. L'utilisateur n'a pas à inventer le programme. Depuis la racine du dépôt cloné :

```sh
git fetch origin
git switch feat/hw4-disp-profile-a
git pull --ff-only
git rev-parse HEAD        # doit être le HEAD complet annoncé par le développeur
idf.py --version          # attendre ESP-IDF v5.5.6
cd firmware/esp32_display_probe
idf.py -B build-profile -DLOCO_CYD_PROFILE=CONSOLE set-target esp32
idf.py -B build-profile -DLOCO_CYD_PROFILE=CONSOLE build
idf.py -p /dev/ttyUSB0 -B build-profile flash
script -q -f -c 'idf.py -p /dev/ttyUSB0 -B build-profile monitor' hw4-profile-spi20.uart.log
```

Adapter uniquement le port série si besoin ; **pas de build 40 MHz, pas de deuxième flash, pas de vidéo**. Appuyer une fois sur EN/RESET pendant la capture du monitor. Vérifier `HW4-DISP-PROFILE BOOT spi_request_hz=20000000 ... sha=<HEAD>`, `LCD_INIT_PASS dma_bytes=5120`, `ORIENTATION_PASS case=10`, puis entrer **exactement**, une ligne à la fois, les commandes BASIC/UART :

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

Ensuite, pour l'état après RUN : `LIST` puis `!CLS`. Attendre `RUN_TERMINAL` avant chaque RUN suivant. Aucun RUN infini dans cette fiche ; **aucun BREAK nécessaire**. Si un RUN infini est volontairement ajouté dans une campagne distincte autorisée, la seule entrée reconnue actuellement est `!BREAK` puis Entrée (ni ESC ni Entrée seule).

Conserver **le seul fichier UART brut** contenant pour chaque RUN : `RUN_DURATION`, `SUMMARY`, les trois `CLASS`, `TRACE_INFO` et les `TRACE`, `HW4-SCROLL-A0 CLASS`, `LCD_METRICS`, `DEVICE_MEMORY`, `CLOCK_OVERHEAD_ESTIMATE`, `dma_fault=0`, `dma_timeouts=0`, `lcd_error=ESP_OK`. Noter simplement si le défilement ressemble à la « guirlande » connue, sans vidéo. **Pas** de comparaison 20/40.

Le programme alterne volontairement **PEN3 rouge / PEN1 jaune**. Le clignotement peut donc venir du contenu BASIC, des repaints intermédiaires et de la coalescence. Ce n'est pas une preuve de défaut du SPI.

## 5. Tableau de restitution après UART (ne pas remplir avec les mesures #289)

| Mesure (3 RUN sur le HEAD instrumenté) | RUN 1 | RUN 2 | RUN 3 |
|---|---:|---:|---:|
| `RUN_DURATION core_us` | NON MESURÉ | NON MESURÉ | NON MESURÉ |
| `full25 n / mean / p50_upper / p95_upper` | NON MESURÉ | NON MESURÉ | NON MESURÉ |
| `partial n / mean / p50_upper / p95_upper` | NON MESURÉ | NON MESURÉ | NON MESURÉ |
| `scroll_associated n / p50_upper / p95_upper` | NON MESURÉ | NON MESURÉ | NON MESURÉ |
| scrolls total / 0,1,≥2 scrolls par repaint | NON MESURÉ | NON MESURÉ | NON MESURÉ |
| % rendu-pack / submit / attente / other sur le total `full25 wall_us` | NON MESURÉ | NON MESURÉ | NON MESURÉ |
| intervalle entre repaints terminés (`gap_avg_us`) | NON MESURÉ | NON MESURÉ | NON MESURÉ |
| temps scroll+E2 hors repaint (`scroll_wall_outside_repaint_us`) | NON MESURÉ | NON MESURÉ | NON MESURÉ |

Le calcul des % d'une classe utilise **les sommes de ses phases / `wall_us` de la même classe** (pas des moyennes de pourcentages par frame). Les 3 phases + `other` font 100 % par construction. Le scroll logique est hors dénominateur ; la classe `scroll_associated` recouvre `full25/partial` : **ne jamais additionner ses sommes à celles des deux autres**.

## 6. Hypothèses falsifiables (choix réservé au Pilotage)

| Hypothèse | Mesure discriminante | Condition de décision proposée, pas seuil d'acceptation |
|---|---|---|
| **RENDER** peut être le premier levier | part `render_pack_us / wall_us` sur full25 | Part substantielle et stable sur 3 RUN ; réduction CPU potentielle, à vérifier sans changer les couleurs |
| **DMA/pipeline** peut masquer des phases | parts `render_pack_us` et `sem_wait_us`, état séquentiel | Les deux doivent être significatives pour espérer recouvrir ; gain maximal non garanti, attente ≠ débit SPI |
| **PACING/coalescence** explique une partie de la guirlande | `scrolls` par repaint, distributions `zero/one/multi`, gaps et alternance rouge/jaune | Répétition de plusieurs scrolls par repaint avec cadence irrégulière ; distinguer coût de calcul et quantum RUN |
| **Arrêt** de la piste optimisation basse couche | faible part rendre/attente, overhead dominant, incohérences ou défauts | Ne pas choisir un levier tant que mesures ou sûreté ne sont pas probantes |

Au **03/11/2026**, aucun de ces arbitrages n'est conclu par la présente PR : mesures CYD et réception Pilotage restent nécessaires.
