# CLK-02 — RUN phase telemetry (HW4-only, Issue #310)

**Mandat :** #310, EPIC #307. Base contrôlée au démarrage : `main@4d261f2a76374ab99a4dd7415cae7a097330c46b`. Branche `test/clk-02-run-phase-telemetry`. Le HEAD de livraison/flash est celui de la PR Draft et **doit être repris à l'identique** dans la campagne PO ; le HEAD CLK-01 n'est pas celui de ce firmware.

## Matrice des fenêtres, horloges et recouvrements

| Mesure | Frontière effective / horloge | Inclut | N'inclut pas ou ne démontre pas |
|---|---|---|---|
| `HW4-RUN-B RUN_START` | Log puis `s_run_profile_started_us=esp_timer_get_time()` | Identité HEAD, quantum=8, début de la fenêtre RUN | Saisie du RUN, `basic_submit`, rendu de l'écho et log RUN_START précédant le départ |
| `HW4-DISP-PROFILE RUN_DURATION core_us` | `esp_timer_get_time() - s_run_profile_started_us`, en branche terminale | Appels de pas, repaint intermédiaires, UART/touch et `vTaskDelay(1)` entre tranches | Traitement terminal après son horodatage, Ready et **repaint du prompt final** |
| `step_call_wall_us` CLK-02 | juste avant/après chaque `hw4_run_scheduler_slice`, même horloge murale | Interpréteur, préflight/replay vidéo logique et callbacks pendant cet appel | **Pas** « CPU BASIC pur » ; ni le TFT repaint exécuté séparément, ni la durée CPU de tâche |
| `repaint_call_wall_us` CLK-02 | juste avant/après chaque `repaint_dirty` d'un quantum YIELDED, et `repaint_full` lié à une rotation tactile pendant RUN | Rendu/pack logique, soumissions et attentes DMA synchrones, éventuels logs de scroll dans ces appels | Pas `GRAM_VISIBLE` ; repaint terminal du prompt exclu ; ni uniquement le temps DMA |
| `yield_call_wall_us` CLK-02 | juste avant/après le **`vTaskDelay(1)` existant** lorsque RUN demeure actif | Temps mur dans cet appel, réveil et coexistence FreeRTOS | Ne mesure ni « CPU idle », ni le temps d'attente total entre deux pas, ni le temps de scheduling pur |
| `other_wall_us` CLK-02 | **résiduel** `RUN_DURATION - step - repaint - yield` | UART poll, `touch_poll` hors full repaint, logs YIELD/mémoire, horodatages, bookkeeping, gaps inconnus | Ne doit pas être renommé « scheduler wait », « CPU BASIC » ou « travail TFT » |
| `LCD_METRICS` | Cumuls jusqu'à la ligne après commande | Flush, bands, histogrammes et DMA de la session | Non borné à un seul RUN ; ne pas soustraire directement |
| `SUMMARY/CLASS/TRACE` | `prompt()` après Ready + repaint final, `run_terminal_after_prompt` | Opérations de repaint y compris le prompt et classes `full25`, `partial`, `scroll_associated` | **Après** `RUN_DURATION` ; `scroll_associated` recouvre `full25`/ `partial` ; pas d'addition des classes |

**Partition sans recouvrement des appels observés :**

```text
RUN_DURATION = step_call_wall_us
             + repaint_call_wall_us
             + yield_call_wall_us
             + other_wall_us
```

Les quatre **segments de temps mur** sont exclusifs par construction au niveau du thread `app_main`. En revanche, **à l'intérieur** d'un appel, le CPU de la tâche, l'attente SPI/DMA et le scheduler ne sont pas démêlés. Un transfert DMA peut coexister avec une opération CPU ; aucun compteur ne transforme cette partition de temps mur en comptabilité CPU exclusive. Le temps physique de lumière des pixels dans la GRAM n'est pas observé.

`repaint_calls = yield_calls + full_repaints` pour les RUN terminés normalement du banc, `step_calls = quanta`, `yield_calls = quanta - 1`. `repaint_flushes` compte les vrais flushs dirty du RUN seulement, `repaint_bands` leurs bandes plus les 30 bandes de chaque full repaint tactile. Les mesures **n'utilisent pas** les classes post-prompt pour reconstruire une phase. Une panne de capture / compteur produit `valid=0` sans altérer la politique d'arrêt du firmware.

## Diff minimal et coût de l'instrumentation

- **Seul code matériel modifié :** `firmware/esp32_display_probe/main/hw4_c2_console.c` et un header C99 local `hw4_clk02_phase.h`. Aucune dépendance ou tâche créée, pas de DMA, framebuffer, heap ou buffer UART supplémentaire.
- Un struct **automatique** sur la pile existante de `app_main` CONSOLE (durées, appels, flushs/bands, garde de dépassement), transmis aux fonctions concernées par pointeur ; **0 octet BSS/DRAM supplémentaire** imputable au stockage, aucune allocation dynamique. Reset à `basic_run`; horodatages aux **frontières des appels existants**, pas dans la boucle d'interprétation BASIC ni par bande DMA. Vérifier la marge de pile réelle dans `DEVICE_MEMORY` lors du test PO.
- `probe_clock_reads=2*(step_calls+repaint_calls+yield_calls)` estime le **nombre de sondes supplémentaires**; leur coût mur réel et l'overhead de bookkeeping restent à mesurer sur CYD. Aucun `printf` dans la boucle chaude CLK-02. Le `vTaskDelay(1)`, le quantum 8, le toucher, UART, la configuration TFT SPI40, le nombre de flushs et les appels scheduler sont inchangés.
- `CMakeLists.txt` racine reçoit **uniquement deux ctests**, sans changement du target de production : test C99 du même accumulateur et parseur UART à falsifications.

### Contrat UART additif, versionné

Après `RUN_DURATION` et `RUN_TERMINAL`, **avant** `DEVICE_MEMORY stage=run_terminal` et le prompt :

```text
HW4-CLK02 RUN_PHASE_SUMMARY version=1 run=N duration_us=D
  step_call_wall_us=S repaint_call_wall_us=R yield_call_wall_us=Y
  other_wall_us=O step_calls=Q repaint_calls=P repaint_flushes=F
  repaint_bands=B full_repaints=H yield_calls=Q-1
  probe_clock_reads=K valid=1 unit=us clock=esp_timer_task_wall
  scope=RUN_slices_including_repaint_excluding_final_prompt
  step_scope=scheduler_slice_call
  repaint_scope=dirty_plus_touch_full_calls
  yield_scope=cooperative_vTaskDelay_call
  attribution=task_wall_not_cpu_or_gram sha=SHA_COMPLET
```

Le firmware écrit **une ligne physique** (l'exemple est retourné pour lecture) et conserve sans modification toutes les anciennes lignes, champs et scopes `RUN_DURATION`, `RUN_TERMINAL`, `SUMMARY`, `CLASS`, `TRACE`, `LCD_METRICS`. C'est une observation **append-only** : pas de changement BASIC/TIME/EVERY/AFTER/REMAIN, scheduler, renderer ou pacing.

## Validation sur hôte

```sh
python3 -m unittest discover -s tests -p test_clk_02_uart.py -v
cmake -S . -B build-clk02-host -DCMAKE_BUILD_TYPE=Debug -DBP_SANITIZERS=ON
cmake --build build-clk02-host -j2
ctest --test-dir build-clk02-host -R '^clk_02_' --output-on-failure
```

Le script `tools/clk_02_uart.py` **réutilise** `clk_01_uart.analyze` sans modifier CLK-01 : scellés du corpus, commandes TX/réception, démarrage/HEAD, IDF, SPI40, 15 RUN terminal state=5, santé DMA/heap/pile, SUMMARY/CLASS restent vérifiés. Le contrôle CLK-02 exige une unique ligne par RUN, version/scope/horloge/HEAD corrects, nombres non négatifs bornés (uint32/uint64), additivité exacte, ordre, compteurs et nombre de sondes, absence de double compte, et placement avant `DEVICE_MEMORY`. Les tests synthétiques falsifient ce contrat ; **aucun exemple test n'est une mesure CYD**.

## Baseline PO CLK-01 et dispersion : comparaison après GO

**Témoin physique accepté par Pilotage #308 :** flash `3c4b2289cf9e7e806402aa997d9a711003c19623`, UART brut **151 962 octets**, SHA-256 `38ba7108602e0a8424d0da90ccb6454c69307f977a5a197dd345497a11f4c586`, 15/15 RUN. Ce brut a été contrôlé par Pilotage mais son archivage GitHub reste une réserve ; il doit être fourni sans altération pour effectuer le comparatif.

| Profil | CLK-01 min / médiane / max (µs) — témoin PO |
|---|---:|
| 01_for | 1 597 889 / **1 598 018** / 1 598 271 |
| 02_integer | 1 971 916 / **1 972 102** / 1 972 439 |
| 03_gosub | 1 593 225 / **1 597 533** / 1 597 577 |
| 04_print_fixed | 116 622 / **116 919** / 116 978 |
| 05_print_scroll | 318 772 / **323 490** / 323 735 |

La campagne **CLK-02** réexécute ces cinq sources inchangées, **trois RUN chacune**, et rapporte min/médiane/max et dispersion `max-min`. Le parseur peut vérifier le RAW baseline à son empreinte exacte, le parser à nouveau et calculer `100*(médiane_CLK02/médiane_CLK01-1)`, avec le seuil de revue de **5 %** mais **sans** attribuer toute différence à la sonde (fluctuations, compilateur, état du système, ordonnancement). En absence de capture, **`OVERHEAD_UNVERIFIED`**, sans chiffres imaginés. Les fenêtres CPU CPC `TIME` restent **`NOT_COMPARABLE`**.

## Fiche PO — exécution physique seulement après **GO TEST PILOTAGE**

Conditions : revue Pilotage préalable sur **HEAD complet** de cette PR, carte CYD sans PSRAM, ESP-IDF v5.5.6, un seul UART0 à 115200, profil `CONSOLE`, SPI **demandé** 40 MHz (fréquence électrique non mesurée). Le script tient seul le port : **ne pas ouvrir `idf.py monitor` simultanément.**

Depuis la racine du clone, après validation du SHA de la remise :

```sh
git fetch origin test/clk-02-run-phase-telemetry
git switch --detach FETCH_HEAD
git rev-parse HEAD                   # doit être le HEAD autorisé par Pilotage
git status --porcelain                # doit être vide
idf.py --version                      # ESP-IDF v5.5.6
cd firmware/esp32_display_probe
idf.py -B build-clk02 -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=40000000 set-target esp32
idf.py -B build-clk02 -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=40000000 build
idf.py -p /dev/ttyUSB0 -B build-clk02 flash
cd ../..
python3 -m pip install pyserial
python3 tools/clk_01_po_capture.py --go-test-pilotage --port /dev/ttyUSB0 \
    --sha "$(git rev-parse HEAD)" --raw clk02-uart-raw.log
sha256sum clk02-uart-raw.log clk02-uart-raw.tx.jsonl
python3 tools/clk_02_uart.py clk02-uart-raw.log --sha "$(git rev-parse HEAD)" \
    --csv clk02-phases.csv --markdown clk02-phases.md
```

**Au lancement**, appuyer une fois sur RESET : le script capture le boot puis charge automatiquement les cinq programmes du manifeste CLK-01, `!CLS` hors timing puis trois RUN ; 63 commandes identiques au témoin, 15 lignes de phase attendues. Le script CLK-01 est réutilisé uniquement comme pilote UART ; sa classification brute ne remplace **pas** la validation CLK-02. La nouvelle sortie CSV conserve **15 lignes individuelles**, Markdown donne dispersion et compare les médianes.

**Pour activer le vrai comparatif**, fournir au PO le RAW original scellé de CLK-01 (sans le recopier ni le modifier dans le dépôt) et relancer l'analyse :

```sh
python3 tools/clk_02_uart.py clk02-uart-raw.log --sha "$(git rev-parse HEAD)" \
    --baseline-uart CHEMIN_DU_BRUT_ORIGINAL_CLK01.log \
    --csv clk02-phases.csv --markdown clk02-phases.md
```

Contrôles visuels simples : `04_print_fixed` 3 sorties sans scroll et `05_print_scroll` 30 sorties avec scroll (historique 8 scrolls/RUN), pas de reboot/artefact, TOUCH/ESC/BREAK réactifs sans actionner BREAK pendant les RUN mesurés. Transmettre à Pilotage : SHA flashé, logs build, RAW + SHA256, TX, CSV et Markdown, version IDF, `DEVICE_MEMORY`/erreurs DMA, résultat visuel et réception physique PASS/FAIL par profil. Aucun ratio CPC/CYD et aucune preuve `GRAM_VISIBLE` ne peuvent être déduits du journal.

**Barrières :** aucune validation matérielle sans GO Pilotage ; **`ON_DEVICE_UNVERIFIED`** avant réception PO. PR reste Draft ; seul Pilotage accepte et fusionne ; CLK-03 et autres jalons ne sont pas autorisés par cette livraison.
