# HW4-C3-B2 — Défilement texte MODE1 natif sur CYD

Mission autorisée : [issue #114](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/114). Base acceptée : `main` `85ad98ec83f6066fd15fe341d2a54594efb795ec`, après B1-C1 [PR #109](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/109). Branche : `feat/hw4-c3-b2-mode1-text-scroll`. Base intégrée J1.11-A : `main` `a7f49329d581aa26522ace888f1374ba1e6d8307` ; oracles historiques inchangés. **Aucune validation PO physique ou acceptation Pilotage ne découle de cette note.**

## Comportement et source de preuve

La console ON n'efface plus automatiquement l'écran quand il reste moins de quatre rangées. En MODE1 (40×25), LF sur la rangée 24 et le prochain caractère après une colonne 40 « wrap pending » déplacent le texte de **une** rangée vers le haut. Un CR sans LF réinitialise la colonne sans provoquer un scroll ; la saisie de 120 octets est répartie sur trois rangées par wrap, et les LIST/PRINT longs enchaînent les scrolls nécessaires. `Ready`, nouvelle saisie et curseur restent disponibles ; `!CLS` est seul responsable d'un effacement explicite. Le programme, les variables et les erreurs BASIC restent sous le contrôle du runtime initial.

Les [observations B1](HW4-C3-B1-text-scroll-contract.md) sont `OBSERVED_VISUAL` avec images originales Caprice32, pas des valeurs de pixels transférables directement ; la position exacte avant `Ready` pour les cas `LOCATE` reste `UNVERIFIED`. Aucun oracle historique, `core/`, saisie directionnelle ou police générale n'est modifié.

## Mémoire vidéo et curseur

`video/cpc_video.c` utilise la VRAM **linéaire** existante de 16 000 octets (80 octets × 200 lignes), **pas** la VRAM Z80 entrelacée. `cpc_video_scroll_up(video,1)` déplace `16000 - 640 = 15360` octets par `memmove` et remplit les 640 octets du bas avec `0x00`, `0x55`, `0xaa` ou `0xff` selon PAPER 0..3. Les 25 bandes du viewport deviennent sales `0x01ffffff`. L'API accepte 0 (no-op), 1..25 et rejette >25, modes autres que MODE1, surface ou palette/curseur invalides sans mutation. Aucun malloc, PSRAM, buffer de 1000 glyphes, framebuffer RGB565 ni nouvelle tâche.

`CpcText` conserve les octets reçus, le digest FNV-1a, les compteurs et une position dans `row=0..24`, `column=0..40`. La valeur 40 représente seulement le wrap différé ; elle n'entraîne pas de scroll à elle seule. En bas à droite, le curseur overlay est masqué pour ne pas effacer visuellement le dernier glyphe jusqu'à la progression suivante. `scrolls` compte les déplacements effectifs ; un écran effacé volontairement réinitialise la session d'affichage, pas le programme BASIC. Le cursor overlay n'est jamais copié dans `pixels`.

## Rendu LCD / reprise sur erreur

La surface garde la même organisation ; la fenêtre TFT reste `y=20..219`, les marges BORDER sont `y=0..19` et `220..239`. `cpc_video_flush_dirty` transmet seulement les bandes sales dans l'ordre 0..24 via un callback vers `render_band` existant : un DMA **unique de 5120 octets** (320×8×2) appartenant à `cyd_lcd_band()`, avec 640 octets RGB565 transitoires sur pile. Sur échec de la bande N, les bandes N..fin qui n'ont pas abouti sont restituées au masque, en conservant les éventuelles invalidations nouvelles. Le firmware signale `LCD_DMA` puis **`LCD_FAIL_STOP retry=0` et s'arrête sans second appel**. Le pilote ILI9341 conserve `s_fault` latché et coupe le rétroéclairage après erreur matérielle : les dirty bands restent mémorisés, **mais aucune reprise DMA réelle n'est revendiquée**. Les tests C99 conservent séparément un essai de reprise conditionnelle après rétablissement du callback synthétique ; B2-C1 injecte un transport *sticky* aux bandes 0/12/24 et vérifie qu'aucune relance n'est programmée. Il ne s'agit jamais d'une panne SPI physique provoquée.

Logs : `HW4-C3-B2 SCREEN_SCROLL rows=... total=... policy=mode1_vram program_preserved=1`, `HW4-C3-B2-C1 LCD_FAIL_STOP pending=... sent=... dma_fault=... retry=0`, `HW4-C3-B2 INPUT_READY capacity=120 screen_row=... policy=mode1_scroll`, `HW4-C3-B2-C1 LCD_METRICS ...`. Le précédent `LCD_DMA_RETRY` est supprimé. Le log `SCREEN_PAGE_RESET policy=auto_page_non_cpc` ne doit plus apparaître en console ON ; `!CLS` conserve son log volontaire. Les messages d'erreur `HW4-C2 FAIL` restent explicites.

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

Le script `tools/hw4_c3_b2_uart_po.py` fournit une séquence reproductible et une option de journal. **Le script est facultatif** : les tests manuels du PO avec vidéo et logs UART restent recevables. **Ne pas ouvrir le port simultanément avec `idf.py monitor`** : arrêter le monitor avant la capture par script, puis relancer le monitor si désiré. Conserver le journal UART complet, les messages `SCREEN_SCROLL`, `INPUT_READY`, `DEVICE_MEMORY`, `dma_timeouts`, `dma_fault`, stack/heap, ainsi que des photos (avant/après LIST long, après NEW et après !CLS si possible). Signaler pour chaque étape PASS/FAIL, corruption, clipping, timeout ou retour au boot, et **SHA exact de la carte**.

**Gate :** sans test PO positif sur ce même SHA, la PR reste en revue, `ON_DEVICE_UNVERIFIED`. Seul Pilotage peut accepter et fusionner. Aucun B3, #96 ou #97 anticipé.

### Ready après chaque commande

Le `Ready` du bandeau C3-A est conservé au démarrage. Une fois une ligne UART traitée, la console ON imprime maintenant `Ready\n` **avant** de positionner le curseur pour l'édition suivante ; le prompt visuel ne contient pas de chevron artificiel. Les chemins d'erreur de saisie et de BASIC affichent aussi un diagnostic puis `Ready`. Le test d'intégration B2 couvre explicitement le LIST sur 26 lignes, son extension à 32 lignes, deux autres LIST, 32 étapes RUN avant NEW et le LIST vide après NEW. Ce READY de la console n'est pas un nouveau token BASIC.

## HW4-C3-B2-C1 — optimisation LCD autorisée par le Pilotage

**Mandat** : [arbitrage du Pilotage PR #115](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/115#issuecomment-6459307954), réserves visuelles PO et CI-OPT1 #116. Le scrolling logique VRAM, le noyau BASIC, les archives CPC et `firmware/components/cyd_ili9341/cyd_ili9341.c` sont **inchangés**. `VSCRDEF` et `VSCRSADD` demeurent **hors mandat**. Les corrections C1 ne sont ni une approbation ni une fusion.

**Problème observé sur CYD B2** : `cc6ae50` présente 45 scrolls dans le journal, 0 défaut DMA et heap libre stable, mais le PO voit des vagues/dédoublements. À 20 MHz, un scroll doit encore envoyer 25 × 5120 = **128 000 octets** (51,2 ms de transfert brut minimum, sans rendu ni commandes). L'ILI9341 reçoit les bandes séquentiellement, **pas un frame atomique** : B2-C1 réduit les frames intermédiaires mais ne garantit pas l'absence de tearing.

**Changements C1 du firmware** :
- Les caractères UART sont répercutés dans la VRAM immédiatement ; un burst est rafraîchi à l'arrivée de CR ou après **20 ms d'inactivité UART** (timeout FreeRTOS de granularité par tick), avec une limite dure de **120 événements d'édition consécutifs** avant flush. Un utilisateur tapant lentement conserve l'écho ; un collage rapide est regroupé. L'entrée et le débordement restent gérés par `uart_line`, sans perte d'octets.
- Pendant une commande, *entrée + LF + LIST ou PRINT/RUN/ERROR + Ready + prompt* sont composés **en VRAM avant un unique `repaint_dirty`**. Un nombre quelconque de scrolls logiques consécutifs ne déclenche donc plus des images LCD transitoires par sortie ; la bande `dirty` réunit les modifications. `Ready` est **conservé**, conformément à l'état connu de notre console (sa position CPC reste partiellement UNVERIFIED).
- `repaint_dirty` fait **une seule** tentative de flush avec capture `esp_cpu_get_cycle_count()` divisée par `CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ` (hypothèse fréquence CPU fixe du CYD, wrap 32 bits géré) ; sur échec LCD : `LCD_FAIL_STOP`, dirty bands restants conservés, sortie sécurisée du firmware, **pas de retry** ni de désarmement de `s_fault`.
- Télémétrie cumulative `LCD_METRICS` après chaque commande : `flushes`, `bands`, `spi_bytes`, `scrolls`, `repaint_us_total`, `repaint_max_us`, `echo_idle_batches`, `echo_command_batches`, `echo_batch_max`. Les métriques `repaint_p50_upper_us` et `repaint_p95_upper_us` sont **bornes supérieures d'histogramme**, pas des percentiles exacts ; l'échantillonnage est limité aux flushes de bandes sales, hors repaint de boot. Aucune allocation dynamique supplémentaire.

**Comparaison reproductible avant/après sur HÔTE :** `tests/test_hw4_c3_b2_c1_batch.c` exécute le même flux imprimable de **53 octets** à la dernière rangée, LF, `Ready\n`, prompt, avec flush **par caractère** (chemin B2 historique simulé) puis avec flush **après composition** (B2-C1). Le test comptabilise *bandes × 5120 octets*, vérifie que le cas final fait 25 bandes, impose un gain d'au moins 2×, et compare **toute la VRAM de 16 Ko**, curseur, position, nombre de scrolls et digest FNV. Le même test simule une faute de transport latchée aux bandes 0/12/24 ; le garde-fou de workflow vérifie l'absence de seconde tentative dans le *firmware*. **Ce test ne mesure pas le temps SPI réel, ni un effet de vague filmé.**

Résultat C99 observé pour ce flux strictement identique : **B2 simulé : 56 flushes, 128 bandes, 655 360 octets ; B2-C1 : 1 flush, 25 bandes, 128 000 octets**, soit **-80,47 % d'octets transférés**, avec **3 scrolls des deux côtés et VRAM identique**. [Run B2-C1 de mesure avant documentation finale](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40624299792) (GCC/Clang OFF/ON). Les pourcentages dépendent du scénario et ne prédisent pas la vitesse du TFT sur tous les programmes.

**GATE PO indispensable sur le nouveau HEAD** : ne pas réutiliser l'observation `cc6ae50` comme PASS de C1. Après flash, demander une **vidéo du scroll** au même cadrage et, si possible, la même séquence de 26 puis 32 lignes `PRINT 7` et `LIST` répété ; vérifier l'écho lent, la frappe/collage rapide, le `Ready` après chaque commande, RUN valide (programme `10 PRINT 7`, `20 END`), NEW puis LIST vide, `!CLS` sans effacement du programme et contrôles mémoire/défaut DMA. Relever les `LCD_METRICS` aux mêmes bornes du script sur l'ancien et le nouveau HEAD quand cela est possible, sans confondre le test hôte chiffré avec une mesure avant/après physique. Noter le jugement **PASS/FAIL visuel** des vagues ; aucun script UART ne peut le remplacer. Garder le monitor fermé si le script est exécuté sur le même port.

**CI et intégration** : CI-OPT1 PR #116 est une correction indépendante des gates historiques. Le HEAD final de #115 doit inclure les changements réellement fusionnés dans `main` sans affaiblir les gardes core/oracles, puis refaire Linux GCC/Clang OFF/ON et trois images Xtensa. Si l'optimisation ne suffit pas visuellement, la PR reste en revue et le Pilotage décide d'une sonde matérielle distincte.
