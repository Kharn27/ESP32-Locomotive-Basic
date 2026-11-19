# HW4-ESC-BREAK-B1 — ESC CPC dans le vrai RUN CONSOLE

Mandat : [Issue #385](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/385) — GO Pilotage du 16/11/2026.
Base : `main@3f84b119c404b95f72eab3b7dd6f3034bfc7c959`; branche : `feat/hw4-esc-break-b1-console`.
Les preuves d'acquisition CPC R1 (`tests/fixtures/cpc6128/hw4_esc_r1/**`, 29 PNG et sceaux) demeurent **strictement en lecture seule**. Ce livrable B1 ne réimplémente ni CONT ni les interruptions CPC en CORE.

## Contrat d'entrée, sécurité et limites

- Un `0x1B` seul est ambigu tant que `ESC[` ou `ESC O` peut suivre. `Hw4EscRunControl` maintient l'état du décodeur entre tous les appels `uart_read_bytes`. L'ESC isolé est libéré seulement après **50 000 microsecondes** depuis le préfixe **et** un read UART vide ; jamais à chaque paquet ou quantum. Cette durée est une politique de transport bornée, **pas une mesure historique du CPC**. Après une vraie longue interruption entre ESC et `[`, l'ambiguïté intrinsèque du 0x1B ne peut être éliminée.
- Les CSI/SS3 complètes, les séquences fragmentées, les CSI corrompues/surlongues et les octets `Ctrl+C` restent distincts d'ESC individuel. La quarantaine d'une CSI corrompue dure jusqu'à son final, sans reprise/BREAK fantôme. Les séquences ANSI valides peuvent agir comme touche ordinaire de reprise, conformément à l'adaptateur C99 R1.
- ESC individuel pendant RUN : état PAUSED, **zéro nouvel appel au scheduler** jusqu'à la reprise, aucun Ready ni arrêt BSR. Touche imprimable (p. ex. `x`) : RESUME ; nouvel ESC individuel pendant PAUSED : `hw4_run_scheduler_request_break` puis `BROKEN` au début du prochain slice, **zéro pas supplémentaire**, `stop_calls=1`. Les octets entrés pendant RUN ne sont jamais livrés à l'éditeur BASIC.
- `!BREAK`+CR/LF (et CRLF fragmenté) conserve son rôle de secours HOST_ONLY même pendant PAUSED. Les préfixes du mot réservé ne deviennent pas des touches RESUME. La collecte bornée, le drainage terminal des octets UART et le traitement de LF après CR restent séparés du contrat ESC.
- `hw4_run_scheduler_statement_line` lit `BasicProgramLine.number` au curseur réel de l'exécuteur dans le callback de préflight ; CONSOLE ne retient la ligne comme authentiquement exécutée que si le callback replay après commit réussit. Ce n'est **ni** un numéro de quantum **ni** ERR/ERL ni une constante. Sur double ESC, texte `Break in N` uniquement si cette provenance existe, puis le seul `Ready` historique du RUN ; sans pas exécuté, repli textuel hôte `Break` et provenance UART `UNVERIFIED` (aucun `Break in N` fictif).
- R1 E03 a observé `Break in 10` et E05 `Break in 20` **uniquement dans leurs fenêtres CPC acquises**. Dans le programme A/B natif, le dernier statement effectivement validé peut être en ligne 10 ou 20 selon l'instant de pause. Le moteur ne force jamais 20 pour imiter la capture R1.
- CONSOLE conserve `RUN_QUANTUM=8`, `RUN_UART_POLL_BYTES=16`, le seul app_main, le tactile, la VRAM et le DMA existants, sans heap ni PSRAM ni nouvelle tâche. Pendant PAUSED le `vTaskDelay(1)` continue sans incrémenter les quanta ; CLK-02 classe l'attente dans son résiduel `other_wall_us`, pas comme pas CPU BASIC. Mesurer la réactivité et la marge de pile sur carte.

## Tests et preuves à joindre au HEAD final

CTest C99 `hw4_esc_break_a_transport_contract` : résolution ESC sur seuil d'idle, fragments de flèches, CSI/SS3 rejetées, Ctrl+C, second ESC distinct et aucune mutation d'état sur clé rejetée. CTest `hw4_run_break_b_uart_console_contract` : **vrai BasicSessionRuntime**, GOTO muet et A/B sur lignes 10/20, capture de ligne avant commit, conservation mémoire/programme, pas de pas ni Ready pendant PAUSED, RESUME puis DOUBLE ESC, `stop_calls=1`, `!BREAK` fragmenté et diagnostic non inventé. Les anciennes régressions C99 BSR/PEN/Ready restent actives. Contrôle source `CONSOLE` des symboles réellement appelés.

Vérifier sur le HEAD exact : CI-C99 GCC/Clang avec ASan/UBSan ON/OFF, ARCH, OPT3, CPC-PERMANENT et R1, Xtensa trois profils, les gates C7 déclenchés et comparatif des ELFs CONSOLE **SPI40/SPI20** (IRAM, DRAM, BSS). Mentionner explicitement `HISTORICAL_FAILURE` +220 IRAM s'il persiste et qualifier tout échec. Ni les tests hôte ni Xtensa ne démontrent le matériel.

## Protocole PO — **interdit avant GO FLASH explicite du Pilotage**

Cible : **ESP32-2432S028R classique**, ESP-IDF **5.5.6**, CONSOLE, SPI demandé 40 MHz, UART0 **115200**. Une seule carte et un seul terminal sur le port à la fois. Le Pilotage communique le **HEAD complet revu et approuvé**.

```sh
git fetch origin feat/hw4-esc-break-b1-console
git switch --detach FETCH_HEAD
git rev-parse HEAD             # EXACTEMENT le SHA GO FLASH communiqué
git status --porcelain         # vide
cd firmware/esp32_display_probe
idf.py --version
idf.py -B build-esc-b1 -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=40000000 set-target esp32
idf.py -B build-esc-b1 -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=40000000 build
idf.py -p /dev/ttyUSB0 -B build-esc-b1 flash
idf.py -p /dev/ttyUSB0 -B build-esc-b1 monitor
```

**Programme silencieux :** au prompt, saisie de `NEW`, `10 GOTO 10`, `RUN` (Entrée à chaque commande). Envoyer un ESC brut hex `1B`, attendre le marqueur `ESC_TRANSITION action=PAUSE` et l'absence de `Ready`. Attendre plusieurs secondes : aucun pas supplémentaire. Envoyer une seule touche `x` hex `78` : `RESUME`. Envoyer ESC, vérifier PAUSE, puis **un second ESC distinct** : `CPC_BREAK`, `RUN_TERMINAL state=4`, `stop_calls=1`, `Break in 10` puis un seul `Ready`. Saisir `LIST`, vérifier le programme intact.

**Programme visible :** `NEW`, `10 PRINT "A":GOTO 20`, `20 PRINT "B":GOTO 10`, `RUN`. Capturer TFT A/B pendant RUN. Envoyer ESC ; prendre deux photos de l'écran en pause séparées de plusieurs secondes (aucun A/B nouveau), puis `x` pour RESUME. Nouveau ESC→PAUSE→ESC→BREAK. Le numéro indiqué doit venir de la ligne exécutée, **10 ou 20**, sans forcer la capture E05. Tester flèches `ESC[D` et HOME `ESC[1~` fragmentées, Delete `ESC[3~`, CSI malformée/surlongue (pas de BREAK fictif), et les secours `!BREAK\r` et `!BREAK\n` fragmentés. Au prompt après arrêt, vérifier `!SHOT` exclusivement hors RUN et E3/HOME ; tester ESC hors RUN. Ne pas introduire de test `CONT`.

**Journal de preuve PO** : SHA firmware + version IDF/ELF, UART brut (TX hex, dates et écarts d'envoi ESC/ANSI), photos TFT RUN/PAUSED/BROKEN, Ready unique, `STOP_CALLS`, conservation après LIST, logs `HW4-CLK02`/heap libre/largest/stack/DMA, anomalies/tactile, résultat PASS ou FAIL par scénario. Si le terminal intercepte ESC, ne rien supposer : constater les octets reçus et utiliser un émetteur brut contrôlé, sans lancer deux lecteurs sur UART0.

**Statut matériel** : `ON_DEVICE_UNVERIFIED`, **test CYD nécessaire après GO FLASH**. PR Draft jusqu'à la revue Pilotage, aucune fusion par le Développeur.
