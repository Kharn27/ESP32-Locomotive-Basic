# HW4-C3-B2 — Défilement texte MODE1 natif sur CYD

Mission autorisée : [issue #114](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/114). Base acceptée : `main` `85ad98ec83f6066fd15fe341d2a54594efb795ec`, après B1-C1 [PR #109](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/109). Branche : `feat/hw4-c3-b2-mode1-text-scroll`. **Aucune validation PO physique ou acceptation Pilotage ne découle de cette note.**

## Comportement et source de preuve

La console ON n'efface plus automatiquement l'écran quand il reste moins de quatre rangées. En MODE1 (40×25), LF sur la rangée 24 et le prochain caractère après une colonne 40 « wrap pending » déplacent le texte de **une** rangée vers le haut. Un CR sans LF réinitialise la colonne sans provoquer un scroll ; la saisie de 120 octets est répartie sur trois rangées par wrap, et les LIST/PRINT longs enchaînent les scrolls nécessaires. `Ready`, nouvelle saisie et curseur restent disponibles ; `!CLS` est seul responsable d'un effacement explicite. Le programme, les variables et les erreurs BASIC restent sous le contrôle du runtime initial.

Les [observations B1](HW4-C3-B1-text-scroll-contract.md) sont `OBSERVED_VISUAL` avec images originales Caprice32, pas des valeurs de pixels transférables directement ; la position exacte avant `Ready` pour les cas `LOCATE` reste `UNVERIFIED`. Aucun oracle historique, `core/`, saisie directionnelle ou police générale n'est modifié.

## Mémoire vidéo et curseur

`video/cpc_video.c` utilise la VRAM **linéaire** existante de 16 000 octets (80 octets × 200 lignes), **pas** la VRAM Z80 entrelacée. `cpc_video_scroll_up(video,1)` déplace `16000 - 640 = 15360` octets par `memmove` et remplit les 640 octets du bas avec `0x00`, `0x55`, `0xaa` ou `0xff` selon PAPER 0..3. Les 25 bandes du viewport deviennent sales `0x01ffffff`. L'API accepte 0 (no-op), 1..25 et rejette >25, modes autres que MODE1, surface ou palette/curseur invalides sans mutation. Aucun malloc, PSRAM, buffer de 1000 glyphes, framebuffer RGB565 ni nouvelle tâche.

`CpcText` conserve les octets reçus, le digest FNV-1a, les compteurs et une position dans `row=0..24`, `column=0..40`. La valeur 40 représente seulement le wrap différé ; elle n'entraîne pas de scroll à elle seule. En bas à droite, le curseur overlay est masqué pour ne pas effacer visuellement le dernier glyphe jusqu'à la progression suivante. `scrolls` compte les déplacements effectifs ; un écran effacé volontairement réinitialise la session d'affichage, pas le programme BASIC. Le cursor overlay n'est jamais copié dans `pixels`.

## Rendu LCD / reprise sur erreur

La surface garde la même organisation ; la fenêtre TFT reste `y=20..219`, les marges BORDER sont `y=0..19` et `220..239`. `cpc_video_flush_dirty` transmet seulement les bandes sales dans l'ordre 0..24 via un callback vers `render_band` existant : un DMA **unique de 5120 octets** (320×8×2) appartenant à `cyd_lcd_band()`, avec 640 octets RGB565 transitoires sur pile. Sur échec de la bande N, les bandes N..fin qui n'ont pas abouti sont restituées au masque, en conservant les éventuelles invalidations nouvelles. Le firmware signale `LCD_DMA`, effectue **un seul retry borné**, puis conserve la remontée d'erreur si l'échec persiste. Un test C99 peut injecter un échec synthétique à N=0,12,24 ; ce n'est pas une expérience de panne SPI physique.

Logs nouveaux : `HW4-C3-B2 SCREEN_SCROLL rows=... total=... policy=mode1_vram program_preserved=1`, `HW4-C3-B2 LCD_DMA_RETRY pending=...`, `HW4-C3-B2 INPUT_READY capacity=120 screen_row=... policy=mode1_scroll`. Le log `SCREEN_PAGE_RESET policy=auto_page_non_cpc` ne doit plus apparaître en console ON ; `!CLS` conserve son log volontaire. Les messages d'erreur `HW4-C2 FAIL` restent explicites.

## Tests hôtes et correspondance

- `tests/test_hw4_c3_b2_scroll.c` : octets déplacés comparés, PAPER 0/1/2/3, second scroll, clear 25, canaris, rejets atomiques, 100 scrolls, CR et pending-wrap bas/droite, digest, 120 octets d'édition, erreur de bande 0/12/24 suivie de retry et masque exact.
- Les suites `test_cpc_text.c`, `test_cpc_uart_console.c`, `test_hw4_c3_boot.c` et la sonde B1 sont **migrées de l'ancien reset/clip** vers les nouveaux critères. Les références CPC authentiques et fixtures scellées sont intactes. `test_hw4_c2_integration.c` saisit des lignes BASIC réellement supportées (`PRINT 7` numérotées), exerce LIST répété, RUN, NEW et conservation du programme.
- Workflow B2 et Linux général : GCC/Clang OFF/ON ASan/UBSan, plus workflows ESP32 existants. Au moins 3 images Xtensa distinctes attendues avant la remise : `firmware/esp32_probe`, console ON et HW3 OFF à `firmware/esp32_display_probe`. Le résultat sur carte reste `ON_DEVICE_UNVERIFIED` jusqu'au rapport PO.
- Aucune assertion de `MATCH_EXACT` écran CPC : on compare uniquement progression des lignes et préservation des textes accessibles à notre runtime.

## Protocole de test physique PO — obligatoire, sur HEAD final

Le PO utilise le **dossier VSCode courant**, sans nouveau worktree :

~~~sh
git fetch origin
git switch feat/hw4-c3-b2-mode1-text-scroll
git pull --ff-only
git rev-parse HEAD
cd firmware/esp32_display_probe
idf.py -DHW4_C2_CONSOLE=ON reconfigure build
idf.py -p /dev/ttyUSB0 flash monitor
~~~

Le SHA affiché par `git rev-parse HEAD` doit correspondre **exactement** au HEAD de la PR finale (et à l'application flashée). Dans le monitor UART 115200 : vérifier le bandeau C3-A, l'invite initiale sans chevron, soumettre 26 lignes `10 PRINT 7` à `260 PRINT 7` numérotées puis `LIST`, continuer à 32 lignes et refaire `LIST` deux fois. Vérifier visuellement que les anciennes lignes montent au lieu d'effacer toute la page ; `Ready` et la saisie restent visibles ; exécuter `RUN`, `NEW`, puis `LIST` vide ; `!CLS` ne doit effacer **que** l'écran. Tester une ligne de 40 caractères et des saisies de 80/120 octets, selon le comportement effectivement accepté par la saisie/runtimes, sans présumer que tout BASIC de cette longueur est valide.

Le script `tools/hw4_c3_b2_uart_po.py` fournit une séquence reproductible et une option de journal. **Ne pas ouvrir le port simultanément avec `idf.py monitor`** : arrêter le monitor avant la capture par script, puis relancer le monitor si désiré. Conserver le journal UART complet, les messages `SCREEN_SCROLL`, `INPUT_READY`, `DEVICE_MEMORY`, `dma_timeouts`, `dma_fault`, stack/heap, ainsi que des photos (avant/après LIST long, après NEW et après !CLS si possible). Signaler pour chaque étape PASS/FAIL, corruption, clipping, timeout ou retour au boot, et **SHA exact de la carte**.

**Gate :** sans test PO positif sur ce même SHA, la PR reste en revue, `ON_DEVICE_UNVERIFIED`. Seul Pilotage peut accepter et fusionner. Aucun B3, #96 ou #97 anticipé.
