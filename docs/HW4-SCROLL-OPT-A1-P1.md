# HW4-SCROLL-OPT-A1-P1 — sonde VSCR ILI9341 case10 (expérimentale)

**Mandat :** [Pilotage #156 / #6588107754](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/156#issuecomment-6588107754). Base **main@3c9d3a679d5c5d9db4d659e7d2e1367914d7b7d8** après #270 fusionnée. **Statut à livraison : ON_DEVICE_VSCR_UNVERIFIED**. **Pas de A1-P2/A1-C, aucun gain revendiqué.** Le verdict binaire physique dépend de l'observation PO sur CYD, pas de ce code seul.

## Architecture, bornes et limitations

- `firmware/components/cyd_ili9341/cyd_ili9341.c` est **l'unique propriétaire** SPI2 à 20 MHz et du buffer DMA **5120 o**. Commandes `esp_lcd_panel_io_tx_param(s_io,...)` et transfert marqueur `esp_lcd_panel_io_tx_color(s_io,...)` passent par les mêmes IO/callback `s_done` que les bandes normales. Aucun nouveau bus, tâche, framebuffer, allocation ou PSRAM.
- **OFF au boot** : les chemins normaux `cyd_lcd_send`, `repaint_dirty`, RUN, E2, palette **{1,24,20,6}**, `!CLS`, `!SHOT`, BREAK restent utilisés tels quels. Aucun registre VSCR n'est envoyé sauf commande hôte explicite `!VPROBE`. Le diagnostic monopolise temporairement l'affichage et n'exécute jamais BASIC.
- `s_fault` sticky sur échec d'une commande ou du DMA, rétroéclairage éteint, **aucun retry** : après timeout, aucune commande de restauration sur un état de bus ambigu. Rejeter aussi les écritures normales et la rotation tant que la sonde VSCR est active ; le mode diagnostic bloque les repaints ordinaires et les gestes tactiles, sans effacer les dirty. Sur `!VPROBE OFF` (uniquement sans fault), remettre VSP à l'ancre, `VSCRDEF=(0,320,0)`, `VSCRSADD=0`, puis réafficher **les 240 lignes** depuis la VRAM logique. Toute erreur stoppe le firmware.
- **Inconnu matériel critique** : dans le case10 actuel, `swap_xy=0 mirror_x=0 mirror_y=1`, l'axe VSCR peut ne PAS correspondre à Y physique sur la dalle. La GRAM expose potentiellement **320 lignes** pour **240 visibles** ; `MISO=-1`, pas de readback autoritatif. Le modèle P0 (PR #272) suppose une tranche [0..239] ou [80..319] et MY inversé. Aucun état automatique ne dit `VSCR_CONTROLLER_FEASIBLE`.
- Registres hypothétiques ([datasheet ILI9341](https://cdn-shop.adafruit.com/datasheets/ILI9341.pdf)) : `VSCRDEF(0x33)` 6 octets big-endian (TFA/VSA/BFA) de somme 320 ; `VSCRSADD(0x37)` 2 octets VSP. Cas A: (20,200,100) = `00 14 00 C8 00 64` ; B: (100,200,20) = `00 64 00 C8 00 14`. Déplacement vers le haut **hypothétique** : `offset=(offset-8)%200`. `MARK` écrit des pixels blancs sur 8 rasters à la destination modélisée `Y=208..215`, **à tester visuellement après T1**. Ne jamais extrapoler le test P0 à des pixels physiques.

## Protocole UART PO — NE PAS FLASHER avant feu vert Pilotage

**Préconditions :** Pilotage fige le HEAD complet P1, autorise explicitement le flash sur CYD classique sans PSRAM. Le PO vérifie que le Git checkout est le HEAD approuvé, IDF 5.5.6, 20 MHz SPI, CPU identique à la référence, USB /dev/ttyUSB0. Depuis la racine du dépôt :

```sh
git fetch origin
git switch feat/hw4-scroll-a1-p1-vscr-probe
git rev-parse HEAD
git status --short
cd firmware/esp32_display_probe
idf.py -DLOCO_CYD_PROFILE=CONSOLE reconfigure build
idf.py -p /dev/ttyUSB0 flash monitor
```

**OFF (T0) :** laisser démarrer sans commande. Noter `HW4-VSCR-P1 BOOT state=OFF`, `INK_CONTEXT` bleu/jaune/cyan/rouge, SHA firmware, `DEVICE_MEMORY`, `LCD_METRICS`. Exécuter le témoin borné du mandat pour vérifier absence de régression :

```basic
5 CLS
10 FOR I%=1 TO 40
20 PEN 3:PRINT "ROUGE"
30 PEN 1:PRINT "JAUNE"
40 NEXT I%
50 END
RUN
```

P1 n'altère ni le quantum RUN ni le nombre de bandes dans ce mode : `HW4-SCROLL-A0` doit conserver sa qualification **scroll_associated, non-exclusive**. Un repaint classique complet de 25 bandes envoie **128000 o** (payload pixels seulement). Relever les deltas de classe à chaque RUN, pas les cumuls bruts. Ne pas confondre repaint_us avec durée RUN.

**T1, prioritaire et bloquant :** entrer `!VPROBE PATTERN`, photographier un motif **sans VSCR** : 20 lignes bleues en haut, 25 bandes utiles de 8 px avec couleurs/barcodes numérotés, 20 lignes magenta en bas. L'écran est figé pour photo ; les saisies ne changent pas l'affichage. Entrer `!VPROBE OFF` pour restaurer complètement. Puis `!VPROBE T1A` : la sonde redessine le motif, écrit 0x33/0x37 pour **tranche A**, déplace le VSP de 8 px selon le modèle. Photographier direction et marges, lire `HW4-VSCR-P1 T1 candidate=A ... controller=UNVERIFIED`. **Si l'axe n'est pas Y physique, si une marge bouge, ou si l'image se corrompt : `!VPROBE OFF`, STOP PoC, renvoyer preuve négative au Pilotage.** Si T1A inapte mais la tranche 240/320 reste plausible, le Pilotage arbitre un essai séparé `!VPROBE T1B` après `OFF`, sans transformer une géométrie inconnue en un PASS. `!VPROBE T1B` emploie la tranche B. Pas de T2/T3 avant observation T1 acceptée par le PO.

**T2/T3 conditionnels :** seulement si la photo T1 indique un axe vertical, des marges fixes et une tranche plausible, saisir **manuellement** `!VPROBE ACK` (le log dit `operator_claim=1 physical_pass=UNVERIFIED`, pas une certification), puis `!VPROBE UP`, `!VPROBE DOWN`, `!VPROBE WRAP` (26 déplacements de 8 px), `!VPROBE MARK` (8 écritures RAMWR après rotation VSP). Photographier chaque étape, observer wraps, direction, bande blanche aux rasters prévus, bords et ghosting. `!VPROBE OFF` restitue ensuite le rendu logique **entier**. `!SHOT` n'est autorisé qu'une fois OFF ; confronter capture logique et **photo TFT physique**, et tester curseur / `!CLS` / orientation tactile 10↔9↔10 / LIST / RUN. Les commandes BASIC normales sont **rejetées** pendant un diagnostic figé sans muter le programme. `!VPROBE OFF` peut être utilisé à n'importe quelle étape non-faulted.

**T4/T5/T6 et falsifications :**
| Test | Action | PASS/FAIL |
|---|---|---|
| T0 OFF | Boot sans commandes VSCR, benchmark FOR/NEXT | Même rendu/INK/BUILD que base, aucun écran figé |
| T1 A/B | `PATTERN` puis `T1A` (B seulement après arbitrage et OFF) | Y physique 20..219 uniquement, marges fixes, sinon STOP |
| T2 | ACK, UP, DOWN, WRAP | Ordre/sens/motif et VSP conformes aux photos ; toute altération = FAIL |
| T3 | MARK après VSP | Pixels blancs à la bonne ligne sans casser les marges ; sinon FAIL |
| T4 | OFF, rotation, !SHOT, curseur, !CLS, LIST/RUN/BREAK | VSP normalisé, repaint plein, aucune perte de programme, aucun ghosting ; capture logique ≠ preuve TFT |
| T5 | Policy hôte + commandes inconnues/invalides, ACK sans T1, MARK avant ACK, orientation non10, 0/26 lignes (C99) | Reject fail-closed et aucune commande LCD sans état valide ; faute injectée en mock uniquement ; DMA réel fault ⇒ STOP sans retry |
| T6 | OFF/ON, mêmes CPU/SPI/HEAD, `HW4-SCROLL-A0`, photos/vidéos UART | Journaliser bandes/bytes/latence vs CPU/BASIC. **P1 n'est PAS un benchmark d'accélération P2** |

Sauvegarder logs bruts UART 115200 avec SHA, commandes, `HW4-VSCR-P1`, `DEVICE_MEMORY` (heap libre/largest/minimum, stack margin, dma_transfers, dma_fault, dma_timeouts, lcd_error), `HW4-SCROLL-A0`, `LCD_METRICS`, plus photos du motif OFF/T1/T2/T3/T4. Toute faute DMA interrompt les tests : aucun retry. Exiger `dma_fault=0 dma_timeouts=0 lcd_error=ESP_OK` pour les étapes PASS. Pile et heap doivent être comparées au même profil CONSOLE et à la base.

## Preuves logicielles et CI

```sh
bash tools/test_hw4_vscr_p1.sh  # GCC/Clang C99 OFF/ON ASan/UBSan, politique pure
python3 -m unittest discover -s tests -p 'test_hw4_vscr_case10_model.py' -v
# Linux projet complet : CMake/CTest GCC+Clang OFF/ON avec BP_SANITIZERS.
```

Le test C99 autonome couvre les deux triplets 320, les avances et wraps modulo 200, les erreurs de case/orientation/tailles, les marges et les rangées hors plage ; aucune fonction matérielle n'est prétendue testée sur hôte. Les suites CI standards doivent exécuter C99, ARCH, OPT3, CPC permanent, et Xtensa ESP-IDF 5.5.6 **BASIC_PROBE/CONSOLE/HW3 (3/3)** sur le HEAD **exact**. Reporter les liens, statuts, et tailles Flash/IRAM/DRAM. Une compilation Xtensa n'est pas une validation physique.

**Bilan de référence PO B1 sans VSCR :** FOR/NEXT 40 : 58 scrolls logiques, 13 flushes associés, 325 bandes, 1 664 000 o SPI et 2 455 690 µs repaint cumulé (~189 ms/flush associé). Agrégat A0 non exclusif au scroll, non chronométrage du RUN. **Seuil ×3 ni fluidité CPC exigés/enregistrés en P1.**

**Décision au Pilotage :** après preuve PO, verdict `VSCR_CONTROLLER_FEASIBLE` si l'axe et marges, wraps, RAMWR/restauration sont effectivement observés, sinon `VSCR_CONTROLLER_NOT_FEASIBLE` avec STOP et preuve négative. Jusque-là : `ON_DEVICE_VSCR_UNVERIFIED`. PR DRAFT, sans auto-approbation, sans fusion et sans engagement A1-P2/A1-C.
