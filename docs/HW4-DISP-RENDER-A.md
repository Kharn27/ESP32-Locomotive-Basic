# HW4-DISP-RENDER-A — Optimisation CPU MODE1 bit-exacte

- Mandat : [Issue #303](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/303).
- Base immuable : `main@21e95a7197413923bb5976067a0419bc729c20c1` (après fusion #297).
- Portée : **uniquement** `video/cpc_video.c` (lecture MODE1), tests/benchmark et vérification de budget. Pas de refonte HAL, cadence, DMA, scroll, BASIC, fréquence SPI ou framebuffer supplémentaire.
- Statut de réception du nouveau HEAD : **ON_DEVICE_UNVERIFIED** jusqu'à essai PO expressément autorisé par le Pilotage.

## Choix technique

Avant : `cpc_video_render_row` appelle `sampled_pen` pour chacun des **320 pixels** visibles, qui appelle `cpc_video_get` et calcule coordonnées, décalages, masque puis convertit l'encre CPC en RGB565 pour chaque pixel.

Après, exclusivement en MODE1 : calcul initial des **quatre RGB565** de la palette active ; boucle sur **80 octets VRAM contigus par ligne**, chacun décodé en **quatre indices 2 bits** (de gauche à droite, bits 7-6, 5-4, 3-2, 1-0). La superposition de curseur est appliquée ensuite sur au plus huit pixels du rang de curseur, sans toucher la VRAM ; échange uniquement PEN/PAPER, jamais une troisième encre graphique. Le rendu bordure et MODE0/MODE2 empruntent la même voie générique qu'avant.

Cette variante évite les allocations, les tables permanentes et les recalculs par pixel : aucun framebuffer complet supplémentaire, aucune mémoire PSRAM, **zéro allocation dynamique**. Le tableau local `uint16_t colour[4]` représente au plus **8 octets de stockage source transitoire**, pas une nouvelle donnée globale ; son implantation effective dans la pile ou les registres dépend du compilateur Xtensa. La quantité `CpcVideo`, la VRAM 16000 octets, les dirty bands et la taille de DMA unique (5120 octets) ne changent pas.

## Oracle différentiel RGB565

La référence de `tests/hw4_render_a_reference.c` est une copie **figée** des routines génériques `sampled_pen` et `cpc_video_render_row` de la base `21e95a7197413923bb5976067a0419bc729c20c1` ; elle est compilée indépendamment et ne rappelle **jamais** la nouvelle fonction de rendu. Les primitives `cpc_video_get` et `cpc_video_palette_rgb565` qu'elle réutilise sont inchangées sur cette branche.

`tests/test_hw4_render_a.c` compare chaque `uint16_t` sur **320×240** (les zones bordure incluses), avec sentinelles de dépassement et contrôle de l'immuabilité VRAM ; cas de rejet des arguments invalides, 27 correspondances d'encre CPC, 256 valeurs VRAM, images uniformes, graphismes mélangés, texte dense via `put_cell`, curseur de bord, PEN=PAPER, 30 motifs pseudo-aléatoires par MODE, trois visualisations MODE2 et offsets extrêmes, dirty bands complètes/partielles avec échec de callback, scroll up/down/25. **Critère : 0 pixel différent** ; aucun rendu graphique supprimé.

```bash
cmake -S . -B build-render-test -DCMAKE_C_COMPILER=gcc -DBUILD_TESTING=ON -DBP_SANITIZERS=ON
cmake --build build-render-test --target test_hw4_render_a
ctest --test-dir build-render-test --output-on-failure -R '^hw4_disp_render_a_rgb565_exact$'
# Répéter avec -DCMAKE_C_COMPILER=clang, puis sans BP_SANITIZERS.
```

## Benchmark CPU hôte — avant/après comparables

`tests/bench_hw4_render_a.c` mesure sur Linux `CLOCK_MONOTONIC` les deux fonctions sur **le même état CpcVideo et les mêmes lignes**, avant toute mesure avec vérification pixel par pixel. Chaque cas effectue **15 répétitions échantillons de 24 rendus de l'image demandée**, en alternant l'ordre référence/optimisée d'un échantillon au suivant. Les conversions RGB565 demandées sont exécutées intégralement ; pas de `sleep`, de skip de pixels ou de cache pré-calculé hors de ce que fait le renderer lui-même. Résultat par cas : minimum/médiane/maximum **ns par rafraîchissement demandé** et gain sur les médianes ; agrégat de sommes de médianes explicitement identifié.

Corpus : uniform_full25, dense_text_full25, four_inks_full25, graphic_full25, border_cursor_full240, partial_cursor_band8. Pour `full25`, les **200 lignes utiles** sont mesurées ; `border_cursor_full240` couvre aussi 40 lignes de bordure. `partial_cursor_band8` couvre huit lignes. Le composant `render_pack` réel inclut en plus la copie des RGB565 vers le tampon DMA, qui n'est pas mesurée ici : **ne pas confondre benchmark renderer et chronométrage CYD complet**.

```bash
for cc in gcc clang; do
  cmake -S . -B "build-render-$cc" -DCMAKE_C_COMPILER="$cc" \
    -DCMAKE_C_FLAGS="-O3 -fno-lto" -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTING=ON
  cmake --build "build-render-$cc" --target test_hw4_render_a bench_hw4_render_a
  ctest --test-dir "build-render-$cc" --output-on-failure -R '^hw4_disp_render_a_rgb565_exact$'
  "./build-render-$cc/bench_hw4_render_a"
done
```

Le workflow [HW4-DISP-RENDER-A](../.github/workflows/hw4-disp-render-a.yml) publie les journaux et le tableau de mesures GCC/Clang sur son HEAD exact. **La cible ≥15 % est un critère à mesurer**, pas une hypothèse ni une promesse de durée CYD. Ne pas cacher les cas inférieurs.

## Budget mémoire Xtensa / qualité

Le même workflow compile *deux* exécutables CONSOLE **SPI40 demandé**, l'un depuis `main@21e95a...` et l'autre depuis le HEAD de la PR, avec **le même ESP-IDF 5.5.6**. Les sections `xtensa-esp-elf-size -A` (DRAM incl. BSS, BSS, IRAM utile, flash text, rodata) sont comparées par `tools/ci/hw4_render_a_memory.py`. La base C3 est attendue à **54864 octets DRAM / 67331 octets IRAM utile**, et le HEAD ne peut pas augmenter ces deux budgets. Le garde global A0 reste inchangé ; son FAIL CONSOLE historique de **+1136 octets** est **une dérogation de #297 seulement**, jamais un PASS ni une permission d'ajout. Les mesures de pile cible et de heap restent à confirmer par l'UART PO ; aucune revendication matérielle par le simple build.

Les CI existantes C99 GCC/Clang × ASan+UBSan OFF/ON, ARCH, OPT3, CPC permanente, HW4-C3-B2, HW4-EDIT-P1, Xtensa CONSOLE/HW3/BASIC_PROBE doivent rester PASS sur le HEAD proposé. Les comparaisons de pixels ne constituent pas un oracle CPC ROM externe, seulement une preuve de non-régression face au renderer antérieur.

## Protocole de réception CYD destiné au PO — **uniquement après GO Pilotage**

Le SHA **exact du HEAD à flasher** est communiqué dans la REMISE DÉVELOPPEUR de la PR Draft. Ne pas flasher une branche mouvante sans vérifier `git rev-parse HEAD`. Pré-requis : CYD ESP32-2432S028R, ESP-IDF 5.5.6, câble UART à 115200, **CONSOLE SPI40**, aucun essai SPI20 ni A/B.

```bash
git fetch origin
git switch feat/hw4-disp-render-a
git pull --ff-only
git rev-parse HEAD     # doit être égal au SHA complet de la REMISE Pilotage
idf.py --version       # ESP-IDF v5.5.6
cd firmware/esp32_display_probe
idf.py -B build-hw4-render-a -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=40000000 set-target esp32
idf.py -B build-hw4-render-a -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=40000000 build
idf.py -p /dev/ttyUSB0 -B build-hw4-render-a flash
script -q -f -c 'idf.py -p /dev/ttyUSB0 -B build-hw4-render-a monitor' hw4-render-a-spi40.uart.log
```

Au démarrage contrôler `HW4-DISP-PROFILE BOOT` avec `sha=<HEAD>`, `spi_request_hz=40000000`, `variant=SPI40`, `LCD_INIT_PASS dma_bytes=5120`, `ORIENTATION_PASS case=10`. L'affichage SCLK LCD demandé **n'est pas une mesure électrique**.

Envoyer **une commande par ligne** et attendre `RUN_TERMINAL` entre les trois `RUN` :

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
LIST
!CLS
```

Conserver **un seul UART brut complet** : 3 `RUN_DURATION`, `RUN_TERMINAL`, `SUMMARY`, `CLASS`, `TRACE_INFO/TRACE`, `LCD_METRICS`, `DEVICE_MEMORY`, heap8_free/largest, stack_margin_bytes, dma_timeouts, dma_fault et lcd_error. Ajouter constat visuel PEN rouge/jaune, glyphes et bordure, défilement, absence de pauses/résidus et reset. **Arrêt immédiat en cas de LCD/DMA fault**, sans retry automatique.

Comparateur historique *seulement indicatif et non A/B chronométrique contrôlé*, PO ancien SHA `68488bb0f3a6ffe075fdf28303f64c13247ac420` : `RUN_DURATION` **2409604 / 2407691 / 2411329 µs**, `full25 ≈162 ms`, `render_pack ≈132 ms`, `sem_wait ≈26 ms`, `submit ≈4 ms`, `stack_margin_bytes=4240`, zéro faute/timeout DMA. Analyser le nouveau SHA indépendamment, médiane de trois RUN, stabilité heap/pile, cohérence UI ; **aucun ON_DEVICE_PASS avant retour PO et revue Pilotage**.

## Barrière

PR Draft `Refs #303`. Le développeur ne fusionne pas, ne s'auto-approuve pas, ne modifie pas le calendrier ni le transport SPI/DMA et n'engage pas DMA/PACING. La décision technique et l'éventuelle campagne CYD appartiennent au **PILOTAGE**.
