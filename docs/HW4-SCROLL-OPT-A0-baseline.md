# HW4-SCROLL-OPT-A0 — baseline MODE 1 (instrumentation uniquement)

Mandat Pilotage : [#156 / commentaire 6501773436](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/156#issuecomment-6501773436). Base imposée : `main@319e8872c88842840e0992f305ec047fe516cb38`. Branche : `feat/hw4-scroll-opt-a0-baseline`. **Aucune optimisation implémentée** ; pas de changement de VRAM, BASIC, E2, scrolling, DMA, orientation ou curseur.

## 1. Ce qui est mesuré

`repaint_dirty()` garde exactement un appel à `cpc_video_flush_dirty` par image dirty ; l'horloge est toujours `esp_cpu_get_cycle_count()` divisée par `CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ`. L'instrumentation A0 est réalisée **après** l'appel de transfert, sans UART par bande. Les statistiques comptent les bandes **envoyées avec succès** par le callback, chacune de `CYD_LCD_DMA_BYTES=5120` octets (320×8×2). Les transferts boot de `repaint_full` (30 bandes) ne sont pas comptés dans cette baseline dirty.

- `ordinary` : flush sans événement de scroll observé depuis le dernier flush ;
- `scroll_associated` : au moins un scroll depuis le dernier flush, **même si d'autres mutations ou un !CLS ont eu lieu**. Ne jamais interpréter `us_total`, bandes ou SPI comme coût exclusif du scrolling ;
- `up` : défilements de `s_text.scrolls` (texte, édition et ENTER E1) plus défilements de navigation bas-de-page `DOWN` ; `down` : navigation `UP` au bord haut. L'unité est une **rangée déplacée** dans le scénario actuel, pas un événement clavier ;
- `reset_tagged` : nombre de flushs dans lesquels un `!CLS` a eu lieu depuis le dernier flush. `resets` est cumulatif et n'efface **jamais** les séries A0 : l'ancien compteur `s_text.scrolls` revient, lui, à zéro. Un scroll précédant `!CLS` est encore associé au flush qui suit, mais le contenu a pu être détruit : collision explicite ;
- un scroll sans dirty ne fabrique pas de flush ; les `pending_up/down` signalent les événements non encore classés au moment du rapport. Sur un journal final, exiger 0 si l'on prétend avoir mesuré tous les scrolls.

`SAMPLE` et les deux lignes `CLASS` sont émises uniquement **après** les rapports `LCD_METRICS` existants `after_line` et `after_rejected`. Les compteurs sont cumulatifs depuis le boot. `seq` relie les lignes ; deux classes toujours présentes (zéro inclus). `hist` : douze effectifs dans les intervalles `[0,500]`, `(500,1000]`, …, `(256000,512000]`, `(512000,UINT32_MAX]` microsecondes. `p50_upper_us` et `p95_upper_us` sont **des bornes supérieures d'histogramme** par rang le plus proche, non des quantiles exacts. `min_us`, `max_us` et `us_total` sont mesurés à la résolution entière µs ; `max` ne décrit pas la durée de chaque scroll. Les mesures incluent rendu RGB565 et attente DMA, hors composition BASIC antérieure.

Coût statique de la nouvelle structure : `sizeof(Hw4ScrollMetrics)` borné **à la compilation à 256 octets** (216 octets attendus sous ABI Xtensa 32-bit avec alignement 8, à vérifier dans le map/nm). Aucun malloc, framebuffer, tâche, driver ni deuxième compteur d'horloge. L'ajout de code compilé et le coût **réel** en BSS/IRAM seront établis depuis les rapports Xtensa base vs PR ; le plafond de taille C ne remplace pas cette preuve.

Le protocole A0 mesure **le chemin instrumenté**, pas un contrôle « instrumentation OFF » sur le même firmware : comparer plus tard sa distorsion avec la base non instrumentée sur des scénarios identiques. Les émissions UART de bilan (`SAMPLE`/`CLASS`) sont hors zone chronométrée, mais prolongent la pause de commande entre deux échantillons.

## 2. Baseline analytique (pas une mesure CYD A0)

| Élément | Valeur du code de base | Nature |
|---|---:|---|
| VRAM MODE 1 | 16 000 octets | disposition logique existante |
| Déplacement mémoire haut/bas 1 rangée | 15 360 octets `memmove` + 640 effacés ; E2 déplacé aussi | code existant ; **durée CPU non mesurée** |
| Dirty mask après scroll | 25 bandes | code existant |
| Bande LCD | 320×8×2 = 5 120 octets RGB565 | code existant |
| Flush intégral après scroll | 25 × 5 120 = **128 000 octets RGB565** | plafond par flush complet ; pas du débit SPI exclusif par événement |
| Horloge SPI du pilote | **20 000 000 Hz** (`LCD_CLOCK_HZ`) | configuration du pilote, pas fréquence mesurée à l'oscilloscope |
| Durée théorique minimale pour 128 000 octets à 20 MHz | **51,2 ms** de bits utiles | **borne théorique**, exclut commandes, rendu CPU, attente DMA |
| Session antérieure J1.15-C-C1 | `flushes=111 bands=433 spi_bytes=2216960 scrolls=24 repaint_max_us=187635` | observation PO **sur ancien SHA**, pas preuve A0 |

**Aucune ligne ci-dessus ne constitue une mesure physique A0**. En particulier `187635 µs` est un maximum historique toutes classes confondues. Les octets SPI A0 sont dérivés du nombre de bandes confirmées ; ils ne comptent pas les commandes SPI de fenêtre ou le protocole LCD.

## 3. Protocole PO sur CYD physique

Matériel : ESP32-2432S028R sans PSRAM, ILI9341, orientation case 9, marges 20+20, mode CONSOLE. **Après CI sur le SHA final communiqué dans la remise**, synchroniser la branche, puis depuis le dépôt :

```bash
git fetch origin
git switch feat/hw4-scroll-opt-a0-baseline
git pull --ff-only
git rev-parse HEAD          # comparer exactement au SHA transmis
cd firmware/esp32_display_probe
idf.py -DLOCO_CYD_PROFILE=CONSOLE build
idf.py -p /dev/ttyUSB0 flash
idf.py -p /dev/ttyUSB0 monitor
```

Enregistrer **toute** la sortie UART depuis le redémarrage (ligne `HW4-C2 START` et `ORIENTATION_PASS case=9`) jusqu'au dernier `DEVICE_MEMORY after_line`. Pour capturer avec l'outil système sans autre pilote série, un terminal Linux peut utiliser `script -q -f -c 'idf.py -p /dev/ttyUSB0 monitor' ../../hw4-scroll-a0.uart.log`, après le flash. Presser EN/RESET sur le CYD **une fois le monitor actif** pour capturer le boot. Arrêter le monitor avec Ctrl+]. Capturer également une photo MODE 1 après les scrolls et une après `!CLS`.

**Manipulations contrôlées (un seul propriétaire du port série).** Sur terminal connecté à l'UART :

1. Vérifier `START version`, IDF v5.5.6, `LCD_INIT_PASS dma_bytes=5120`, `VIDEO_READY mode=1 logical=320x200`, `ORIENTATION_PASS case=9`, et les deux classes après la première commande.
2. Entrer `!CLS`, `NEW`. Saisir vingt-cinq lignes numérotées `10 PRINT "A0"`, `20 PRINT "A0"`, …, `250 PRINT "A0"` puis `LIST` et `RUN`. **Ne pas envoyer tout le programme en un seul bloc sans observer les fins de ligne**. La saisie/LIST/RUN doit provoquer de nombreux scrolls vers le haut ; vérifier le compteur `up`, et ne revendiquer 20 que si `up` a effectivement progressé de 20 sur la fenêtre choisie.
3. Laisser l'écho se vider (>100 ms), puis entrer une commande vide (ENTER) pour déclencher `LCD_METRICS` et `SAMPLE`. Ce rapport cumule toutes les actions précédentes : soustraire **des snapshots consécutifs**, jamais les valeurs cumulées comme une seule commande.
4. Entrer `!CLS` : vérifier `resets` +1, `text_scrolls` revenu à 0 et total A0 **non remis à zéro**. Envoyer une flèche HAUT `ESC [ A` jusqu'au bord haut (au plus 24 déplacements), puis une flèche supplémentaire, attendre 100 ms et relever une ligne vide : vérifier une hausse **d'une rangée `down`**. Ensuite envoyer au moins **20 flèches HAUT supplémentaires** lorsque le curseur est au bord supérieur, attendre >100 ms et relever une ligne vide : vérifier `down` +20. S'il n'est pas possible d'envoyer des séquences CSI depuis le terminal ou d'observer la borne, marquer **DOWN NON TESTÉ**, jamais PASS.
5. Refaire `LIST` puis `RUN` pour vérifier que `!CLS` a préservé le programme BASIC, et terminer par une commande vide pour obtenir un snapshot final complet et `DEVICE_MEMORY after_line`.
6. Contrôler visuellement les marges, cellules E2 (aucun texte fantôme), curseur, une rangée effacée par scroll, aucun panic/redémarrage, `dma_fault=0`, `dma_timeouts=0`, `lcd_error=ESP_OK` et marge de pile positive. Communiquer log UART brut, photos, sortie `git rev-parse HEAD` et résultat de flash.

Le sentier de navigation bas est **une politique HOST**, pas une preuve de conformité des flèches à la ROM CPC. Un `!CLS` en cours d'intervalle introduit une collision : `reset_tagged` en indique la présence. Éviter les impressions intermédiaires pendant un test mono-scroll ; la composition de l'écran après ENTER peut toutefois ajouter des écritures, d'où la classe « associée » et non « exclusive ».

**Audit hors carte** depuis la racine du dépôt, après copie du log :

```bash
python3 -m unittest tests/test_hw4_scroll_metrics_parser.py
python3 tools/hw4_scroll_a0_uart.py hw4-scroll-a0.uart.log \
  --sha <SHA_COMPLET_FLASHÉ> --idf v5.5.6 --profile CONSOLE \
  --spi-hz 20000000 --cpu-mhz 240 --orientation 9 \
  --require-bidirectional --out hw4-scroll-a0-audited.json
```

Le parseur exige un vrai SHA 40 hex, la version de boot compatible, la fréquence SPI du pilote (**20 MHz**), au moins un `DEVICE_MEMORY after_line` sain, et des snapshots complets. Il vérifie la somme des deux classes contre les compteurs `LCD_METRICS`, histogrammes, échantillons, octets/bandes, quantiles, monotonie, remises à zéro, collision et manifeste. `--require-bidirectional` exige au moins 20 rangées dans **chaque** sens et un `!CLS`. Le log synthétique positif est un **test de parseur**, jamais un relevé matériel. Si la fréquence CPU diffère du manifeste de la carte, utiliser la valeur effectivement compilée et documentée, et ne pas altérer arbitrairement le log.

## 4. Matrice de mesures physiques — à remplir uniquement après retour PO

| Même CYD / même fréquence SPI et CPU | Nombre flushs | Nombre scrolls ↑ / ↓ | Bandes | Octets RGB565 | Min µs | p50/p95 borne sup. µs | Max µs | Réserves |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| A0 : ordinaire | NON MESURÉ | 0 / 0 | NON MESURÉ | NON MESURÉ | — | — | — | pas un contrôle OFF |
| A0 : associé au scroll | NON MESURÉ | NON MESURÉ | NON MESURÉ | NON MESURÉ | — | — | — | mélanges possibles |
| A0 : collision !CLS | NON MESURÉ | NON MESURÉ | NON MESURÉ | NON MESURÉ | — | — | — | `reset_tagged` |
| Base `319e8872`, scénario identique | NON MESURÉ | NON MESURÉ | NON MESURÉ | NON MESURÉ | — | — | — | anciens compteurs non classés |

### Budget Xtensa : comparer les rapports CI de deux SHA effectivement compilés

| Profil | Base Flash code / BIN | PR Flash code / BIN | Base IRAM | PR IRAM | Base DRAM/BSS | PR DRAM/BSS | Delta |
|---|---|---|---|---|---|---|---|
| CONSOLE | À ACQUÉRIR | À ACQUÉRIR | À ACQUÉRIR | À ACQUÉRIR | À ACQUÉRIR | À ACQUÉRIR | NON VÉRIFIÉ |
| HW3 | À ACQUÉRIR | À ACQUÉRIR | À ACQUÉRIR | À ACQUÉRIR | À ACQUÉRIR | À ACQUÉRIR | NON VÉRIFIÉ |
| BASIC_PROBE | À ACQUÉRIR | À ACQUÉRIR | À ACQUÉRIR | À ACQUÉRIR | À ACQUÉRIR | À ACQUÉRIR | NON VÉRIFIÉ |

Recueillir les artefacts `arch-hw4-u1-b-{console,hw3,basic}` de la CI Xtensa pour **le base exact et le PR HEAD exact** ; comparer `size.txt`, `size-components.txt`, BIN, ABI (`xtensa-abi.txt` BASIC_PROBE), symboles et `memory-parity.txt`. Ne pas remplacer ces résultats par la taille du type C. Aucun `SKIPPED` ne compte comme PASS.

## 5. Pistes A/B/C et recommandation au Pilotage

- **A, VSCR ILI9341** : gain SPI potentiellement important si paysage case 9 et marges 20+20 permettent un remappage sans perte. Risques : MADCTL, haut/bas, curseur/E2, écriture ultérieure et réinitialisation. A0 ne l'implémente pas.
- **B, anneau CPU VRAM** : pourrait éviter environ 15 360 octets de `memmove` par rangée, mais n'évite **aucun** des 128 000 octets RGB565 du flush complet existant. Complexité de pixel/E2 supérieure ; non justifié sans durée CPU isolée.
- **C, regroupement de bandes** : 25 bandes exigées par le dirty mask complet ; aucune bande ne peut être supprimée sans équivalence démontrée. Risque fail-stop DMA.

**Seule prochaine expérience proposée, sous nouveau mandat Pilotage (pas démarrée)** : *étude de faisabilité instrumentée VSCR sur case 9 avec retour déterministe au rendu existant*, si les statistiques PO montrent que les flushs associés dominent le coût en bandes et temps. En cas de preuve contraire ou de risque orientation/fiabilité, conserver l'implémentation actuelle. Aucun seuil de gain ni acceptation A1 anticipé.

**Statut provisoire** : code et outillage en PR A0 ; `ON_DEVICE_UNVERIFIED` tant qu'aucun log CYD A0 sur SHA final n'est produit et audité. La décision d'acceptation/fusion appartient au Pilotage.
