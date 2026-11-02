# HW4-SCROLL-OPT-A1-P0 — faisabilité géométrique VSCR, sans firmware

**Mandat Pilotage :** [issue #156 / décision P0 du 02/11/2026](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/156#issuecomment-6581936685), tranche autonome de [A1-P](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/156#issuecomment-6573315273). Base figée : `main@e6ddd3be0b003f718cbcd1e49cbda85ea6cf20e0`. **Décision proposée : `MODEL_FEASIBLE_CONTROLLER_UNVERIFIED` uniquement sous hypothèses explicites ; aucun `VSCR_FEASIBLE` matériel.** Zéro commande LCD, zéro modification firmware ou des chemins réservés #250.

## 1. État du code examiné (base figée)

| Chemins réels consultés | Observations pertinentes |
| --- | --- |
| [`video/cpc_video.[ch]`](https://github.com/Kharn27/ESP32-Locomotive-Basic/blob/e6ddd3be0b003f718cbcd1e49cbda85ea6cf20e0/video/cpc_video.c) | CPC MODE1 320×200, VRAM linéaire **16 000 octets**, E2 1000 caractères et 125 validités. `scroll_up/down` déplace le raster et E2, met les 25 bandes dirty. `render_row` gère les marges à y=0..19 et 220..239, l'INK/BORDER et le curseur comme overlay non destructif. `flush_dirty` conserve les bandes restantes après échec de callback ; aucun retry DMA matériel. |
| [`video/hw4_scroll_metrics.[ch]`](https://github.com/Kharn27/ESP32-Locomotive-Basic/blob/e6ddd3be0b003f718cbcd1e49cbda85ea6cf20e0/video/hw4_scroll_metrics.c) | Classes `ordinary` / `scroll_associated` (incluant des writes non-scroll), reset `!CLS`, histogramme et p50/p95 en **bornes supérieures**, non quantiles exacts. |
| [`firmware/components/cyd_ili9341/cyd_ili9341.c`](https://github.com/Kharn27/ESP32-Locomotive-Basic/blob/e6ddd3be0b003f718cbcd1e49cbda85ea6cf20e0/firmware/components/cyd_ili9341/cyd_ili9341.c) et [son header](https://github.com/Kharn27/ESP32-Locomotive-Basic/blob/e6ddd3be0b003f718cbcd1e49cbda85ea6cf20e0/firmware/components/cyd_ili9341/include/cyd_ili9341.h) | Propriétaire SPI2 unique, horloge **20 MHz**, buffer DMA interne **5120 o**, `esp_lcd_panel_draw_bitmap`, callback et sémaphore **2 s**. `s_fault` sticky en erreur, rétroéclairage éteint, pas de hot-reinit. `cyd_lcd_orientation(10)` : `native_wide=1`, `swap_xy=0`, `mirror_x=0`, `mirror_y=1`, adressage 320×240 ; le code qualifie cette variante MV0 de **hypothèse matérielle distincte**. `clear_native_gram` avant MADCTL, rotation tactile 9↔10. Aucune API de commandes au niveau public. |
| [`firmware/esp32_display_probe/main/hw4_c2_console.c`](https://github.com/Kharn27/ESP32-Locomotive-Basic/blob/e6ddd3be0b003f718cbcd1e49cbda85ea6cf20e0/firmware/esp32_display_probe/main/hw4_c2_console.c) | Boot case10, bandes RGB565 **320×8**, `repaint_dirty` après `basic_run_slice` YIELDED, `!CLS` logique, `!SHOT` **LOGICAL_RGB565LE** et non lecture GRAM (`LCD10_UNVERIFIED`). Rotation tactile force full repaint. RUN/BREAK, E1/E3 restent propriétaires du code CONSOLE. |
| [`integration/hw4_pen_bridge.c`](https://github.com/Kharn27/ESP32-Locomotive-Basic/blob/e6ddd3be0b003f718cbcd1e49cbda85ea6cf20e0/integration/hw4_pen_bridge.c) | Écrit le raster CPC logique et ses cellules ; aucun changement P0. |

## 2. Point bloquant potentiel : contrôleur 320 lignes, écran paysage 240 lignes

La [datasheet ILI9341](https://cdn-shop.adafruit.com/datasheets/ILI9341.pdf) (§8.2.26 `VSCRDEF 33h`, §8.2.29 `MADCTL 36h`, §8.2.30 `VSCRSADD 37h`, §9.2.2) exige **TFA+VSA+BFA = 320** lignes de contrôleur ; une autre somme rend le scroll *undefined*. MY = ordre d'adressage des lignes ; ML = ordre de rafraîchissement. Les équivalences entre VSCR, orientation **case10** (MV/swap=0, MY/mirror_y=1) et axe vertical **physique** ne sont pas prouvées sur cette dalle. L'API ESP-IDF 5.5.x `esp_lcd_panel_io_tx_param` pourrait transmettre une commande, **mais pas sans sérialisation et intégration contrôlée au propriétaire DMA existant**.

Schéma de la fenêtre visible (320 colonnes ; chaque bande = 8 lignes) :

```text
TFT y 0..19     ┌──────────────────────────────┐ marge BORDER fixe (20)
TFT y 20..219   │ CPC 320×200 = 25 bandes × 8 │ raster + E2 logique
TFT y 220..239  └──────────────────────────────┘ marge BORDER fixe (20)

Hypothèse : 240 lignes contiguës visibles parmi 320 lignes GRAM,
             index Y physique inversé (non démontré).
- tranche visible scan[  0..239] -> VSCRDEF TFA= 20 VSA=200 BFA=100
- tranche visible scan[ 80..319] -> VSCRDEF TFA=100 VSA=200 BFA= 20
La zone fixe excédentaire cache les 80 lignes non visibles.
NE PAS utiliser TFA=20 VSA=200 BFA=20 : somme 240 invalide.
```

Sous **cette seule hypothèse**, `scan=visible_start+239-physical_y` ; dans la zone scroll `GRAM=TFA+((scan-TFA+offset)%200)`. Déplacer le contenu visuel CPC de 8 pixels vers le haut demande `offset = (offset - 8) % 200` ; vers le bas `offset = (offset + 8) % 200` ; les huit lignes nouvellement exposées sont repeintes avec PAPER (une autre valeur en cas de writes ultérieurs). Aucun registre ne doit être programmé sur cette base sans vérifier direction et axe réels. Un scroll le long de l'axe horizontal en case10 rendrait cette méthode **inapplicable**. Un dirty mask classique non remappé est incompatible avec un VSP actif : retrait du mode scroll + repaint intégral, ou transformation rigoureuse de TOUTES les écritures.

## 3. Modèle autonome et reproduction

Deux chemins **nouveaux** seulement : `tools/hw4_vscr_case10_model.py` et `tests/test_hw4_vscr_case10_model.py`, Python stdlib. Le modèle manipule **des étiquettes de raster**, pas des couleurs RGB565 ni des pixels réels. Il vérifie la permutation et les adresses écrites après scroll, sans prouver la capacité du contrôleur, la vitesse, RAMWR, tearing ou le sens MADCTL. En toutes circonstances le verdict porte `fallback=True` : **aucun code n'active le LCD**.

```sh
python3 -m unittest discover -s tests -p 'test_hw4_vscr_case10_model.py' -v
python3 tools/hw4_vscr_case10_model.py
python3 tools/hw4_vscr_case10_model.py --visible-start 0 --assume-vscr-is-physical-y
python3 tools/hw4_vscr_case10_model.py --visible-start 80 --assume-vscr-is-physical-y
```

Sans hypothèse explicite la CLI retourne `MODEL_NOT_FEASIBLE` et `fallback=true`. Avec les deux placements manuellement supposés, elle retourne `MODEL_FEASIBLE_CONTROLLER_UNVERIFIED` et les triplets (20,200,100)/(100,200,20), **jamais** `VSCR_FEASIBLE`. Les **13 tests locaux PASS** couvrent : scroll unitaire et 25 rangées ↑/↓, wraps et cadence alternée, écritures après scroll, 220 mutations déterministes pour chaque tranche comparées à un **oracle de liste indépendante du mapping GRAM**, état initial, marges, SHOT logique/curseur overlay, clear/disable/restart, rejet de writes dirty avec génération périmée. Falsifications nommées : marges altérées, géométrie et orientation non case10, swap/mirror faux, axe Y inconnu ou axe X, tranche visible non établie, scroll 0/26 ou direction invalide, écriture en marge, échec DMA et `s_fault` sticky sans retry. **Aucune assertion de succès physique**.

## 4. Risques et gardes de la véritable A1-P

| Risque matériel | État P0 | Condition de poursuite/fallback |
| --- | --- | --- |
| 240 lignes TFT vs 320 lignes GRAM | Incertain | Identifier avec tests PO tranche visible, 80 lignes cachées et axe VSCR physique. STOP si aucune géométrie 20+200+20 réelle |
| Case10, MY/MV/ML, sens réel ↑/↓ | Non testé | Vérification physique en cas 10, marge haute/basse, raster témoin, reset et rotation tactile 9↔10 |
| RAMWR/CASET/PASET après VSCR et wraps | Modèle seulement | Redirection prouvée de toute fenêtre d'écriture, dessin libre, PEN/PAPER, E2/unknown et overlay |
| Collision dirty / scroll et full redraw | Conflit prévisible | Unique propriétaire de l'écran, normalisation VSP avant fallback full repaint, pas de pixels sautés |
| Callback DMA, s_fault, timeout | Pas de test électronique | Ordonnancement commandes seulement après DMA fini ; faute sticky, STOP, aucun retry ni masquage |
| !CLS/MODE/rotation/restart/off | Modèle seulement | Désactivation explicite, VSP de repos, repaint complet et génération dirty invalidée |
| SHOT, BREAK, ghosting, image finale | Non vérifié | Comparer captures logiques et photos TFT, BREAK CR/LF, absence de tearing, budgets heap/pile |

## 5. Protocole **futur** PO, PAS de flash ni sollicitation en P0

**Seulement après mandat Pilotage distinct, réconciliation #250 et firmware A1-P OFF par défaut :** flasher un HEAD précis sur le même CYD, ESP-IDF **5.5.6**, CPU/SPI identiques, case10 et profil CONSOLE. Capturer un boot UART complet puis deux campagnes **OFF et ON isolées**, compteurs remis à zéro avant chacune. Enregistrer des fenêtres explicites de métriques `ordinary`/`scroll_associated` et des deltas non cumulés mélangés. Comparer sur même séquence : `!CLS`, programme `10 PEN 3:PRINT "SCROLL GREEN"`, `20 PEN 1:PRINT "SCROLL XXXXX"`, `30 GOTO 10`, `RUN` >4096 pas, `!BREAK` CR puis LF, scroll ↑/↓ 1 et ≥20 lignes, plusieurs wraps, retour `LIST/RUN`, navigation E1/E2/E3, curseur, graphiques/couleurs, `!SHOT`, reset/MODE/rotation. Photos marges/ghosting/tear et SHOT avec contexte synchronisé ; logs UART bruts avec `dma_fault=0`, `dma_timeouts=0`, `lcd_error=ESP_OK`, heap/pile et STOP exact. Échec DMA : FAIL/STOP, jamais retry.

**Baseline physique A0 C2 #226**, autre firmware/scénario : **579 flushs associés, 14 475 bandes, 74 112 000 o RGB565 SPI et 108 990 262 µs** cumulés, **188,24 ms en moyenne par flush associé**. Ce n'est **ni** un coût isolé de `memmove` **ni** une mesure A1 OFF/ON. Les 25 bandes × 5120 o représentent 128 000 o/flush complet. Cible *candidate* pour un même événement représentatif : ≥×3 de réduction, soit **≤42 666 o**, sans perte visuelle ni de BREAK. Le modèle idéal calcule **5120 o par scroll d'une rangée**, mais ignore commandes, dirty simultanés et contraintes physiques ; un scroll de 25 rangées coûte toujours **128 000 o** de pixels de remplacement. Aucun gain n'est revendiqué avant mesure PO.

## 6. Décision et chemins d'intégration proposés au Pilotage

**Proposition P0 : `MODEL_FEASIBLE_CONTROLLER_UNVERIFIED` sous les hypothèses `scan_axis_y=True`, `visible_start=0|80` ; `MODEL_NOT_FEASIBLE` par défaut et fallback obligatoire sans elles.** Si les observations hardware contredisent ces géométries, arrêt du PoC VSCR et rapport négatif. **Pas de A1-C coalescence sans nouveau mandat.**

Lors de l'**éventuelle** phase matérielle, après #250 : édition probablement nécessaire de `firmware/components/cyd_ili9341/cyd_ili9341.c` et `include/cyd_ili9341.h` (commandes ordonnées + fail-stop), puis `firmware/esp32_display_probe/main/hw4_c2_console.c` (état VSP, transferts remappés, rollback, métriques et navigation), nouveaux tests et documentation A1-P. Préférer laisser `video/cpc_video.[ch]` et `integration/hw4_pen_bridge.c` inchangés ; si nécessaire, demander arbitrage. **P0 ne touche aucun de ces fichiers, ni `core/`, `CMakeLists.txt`, pilotes, workflows, oracles, couleur #250, J1.22-B ou RUN/!BREAK.**
