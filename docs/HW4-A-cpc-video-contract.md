# HW4-A — moteur vidéo CPC portable C99 (issue #74)

## Périmètre
Composant `video/cpc_video.[ch]` + `video/cpc_palette.c`. Aucune modification `core/`, aucun Z80, aucune commande BASIC graphique et aucun nouveau `app_main` produit. Réutilisation **diagnostique** du seul banc `firmware/esp32_display_probe/` HW3, en conservant le pilote ILI9341 et le cas d'orientation **9** validé physiquement par le PO.

### Surface et contrat
| Mode | Pixels logiques | Bits/pixel | Encres simultanées | Grille caractères |
|---|---|---:|---:|---|
| 0 | 160 × 200 | 4 | 16 | 20 × 25 |
| 1 | 320 × 200 | 2 | 4 | 40 × 25 |
| 2 | 640 × 200 | 1 | 2 | 80 × 25 |

Les trois modes consomment **16 000 octets** = 80 octets par ligne logique × 200 lignes, raster compact linéaire, **pas l'organisation mémoire réelle des 16 Ko du CPC**. Le stockage appartient à l'appelant ; init refuse un buffer trop petit. Aucun `malloc` ni dépendance autre que C99 dans `video/`. `CpcVideo` occupe 48 octets sur Linux x86_64 GCC 14.2.0 **mesurés localement**, mais son `sizeof` sur Xtensa doit être relevé séparément avant d'en tirer un budget cible. Les 25 dirty bands sont représentées par un `uint32_t` de 4 octets inclus dans le contexte (une bande = 8 lignes logiques). Changement de `INK` invalide tout le contenu ; les marges de `BORDER` exigent leur propre repaint.

Les accès par pixel prennent des coordonnées **raster logiques**, et non les unités graphiques de `PLOT`/`DRAW` du BASIC : cette conversion dépendra de l'oracle CPC. L'appel `cpc_video_put_cell` dessine directement dans la surface ; aucun cache de glyphes distinct n'est nécessaire pour synchroniser caractères et pixels. Le dessin reçoit une fonction utilisateur `CpcGlyphRow` : la sonde matérielle emploie les glyphes originaux simplifiés de HW3, couvrant encore seulement un sous-ensemble ASCII. Ni ROM CPC ni police historique intégrées. **Pas de fidélité bit-à-bit revendiquée.**

### Couleurs et TFT
Les indices de couleurs CPC 0 à 26 sont convertis vers des intensités nominales RGB888 à niveaux 0/128/255, puis par décalage entier vers RGB565. Ce choix reproductible ne constitue **pas** une calibration colorimétrique d'écran physique. Par exemple : CPC 1 bleu = RGB565 `0x0010`, CPC 24 jaune vif = `0xFFE0`. Les valeurs par défaut du tableau INK sont un preset logiciel du prototype (en particulier les entrées rarement utilisées **non caractérisées indépendamment**), sans affirmer leur identité historique complète. Le rendu TFT est : y=0..19 BORDER, y=20..219 surface, y=220..239 BORDER ; x=0..319.

MODE 0 : duplication horizontale de chaque pixel logique ; MODE 1 : 1:1. MODE 2 : le stockage conserve 640 × 200 ; en plein écran, OR logique de chaque paire horizontale de pixels monochromes (une ligne brillante étroite reste visible, une perte de détails est inévitable) ; option diagnostic `CPC_MODE2_EVEN` (échantillon gauche) ou `CPC_MODE2_VIEWPORT` (fenêtre logique 320 px à échelle 1:1, décalage 0..320). Ces modes de sortie ne prétendent pas reproduire le tube cathodique du CPC, ni garantir la lisibilité des 80 colonnes sur 320 px.

### Curseur
Superposition non destructive sur une cellule logique 8 × 8 (8 × 8 en MODE1, 16 × 8 en MODE0 et 4 × 8 en MODE2 réduit). L'affichage/retrait n'altère aucun octet du framebuffer. Visibilité commandée explicitement ; **aucune cadence historique n'est supposée**. Le clignotement de 500 ms reste uniquement la fonctionnalité diagnostique ancienne de la sonde HW3 ; HW4-A ne le réutilise pas pour la nouvelle surface.

### Tests Linux
```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug -DBP_SANITIZERS=OFF
cmake --build build --parallel
ctest --test-dir build --output-on-failure
cmake -S . -B build-san -DCMAKE_BUILD_TYPE=Debug -DBP_SANITIZERS=ON
cmake --build build-san --parallel
ctest --test-dir build-san --output-on-failure
./build/cpc_video_ppm ./cpc
```
Trois fichiers `cpc-mode0.ppm`, `cpc-mode1.ppm`, `cpc-mode2.ppm` sont créés en P6 320×240 (non committés). SHA-256 de l'exécution locale GCC 14.2.0 : MODE0 `9df98bd1b71c1040d1859023deb14760d30b2c5bacdf7aa43de993c881596da5` ; MODE1 `64e512a59a6f33e15c1cbeb6f0062dae958f33d08ec6040e31d27908d66f1641` ; MODE2 `e3befe375e2454a7aaa6dac1d2b01ffb719f078bab1e70da7b9e055e70d7a439`. Les SHA sont uniquement des preuves de déterminisme local du prototype ; comparer la reproduction CI séparément.

### Mémoire ESP32
Prévision **non instrumentée sur CYD** : VRAM 16 000 + structure vidéo (~48 sur hôte) + HW3 DMA 5 120 + HW3 grille 1 000 + ligne RGB565 HW4 640 octets sur pile = environ **22 808 octets** sans intégrer piles FreeRTOS, files, allocations IDF et mémoire vidéo du pilote. L'incrément principal par rapport à HW3 est VRAM+contexte et 640 octets transitoires de pile. Les données antérieures HW3 concernent **un autre binaire** et ne doivent pas être ajoutées naïvement aux données du BASIC. Mesurer sur CYD `HW3 DEVICE_MEMORY` libre/largest/min, stack headroom, image, DRAM/IRAM et cas 9 au HEAD HW4-A final. Aucun framebuffer RGB565 153 600 octets et aucune PSRAM.

### Essai matériel PO obligatoire
Sur Debian avec ESP-IDF v5.5.6, dans le worktree de la branche et après le feu vert de CI :
```sh
git switch feat/hw4-a-cpc-video-contract
git rev-parse HEAD
cd firmware/esp32_display_probe
idf.py set-target esp32
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```
Vérifier le SHA exact de la PR, et n'utiliser que la révision physique CYD approuvée orientation cas 9. Le démarrage affiche encore le banc HW3 habituel avec `Ready` ; rien n'est lancé automatiquement dans le BASIC.
- Envoyer `v` : mire MODE0, bandes et grand pavé de couleur, texte `MODE 0` et curseur bloc 16 px de large.
- Renvoyer `v` : MODE1 à résolution horizontale 320, texte `MODE 1`, curseur 8 px.
- Renvoyer `v` : MODE2, logique 640 réduite à 320, texte `MODE 2`, curseur 4 px. La qualité est diagnostique ; pertes horizontales attendues.
- En MODE2, envoyer `w` pour viewport 1:1 sur la moitié droite ; `w` de nouveau pour revenir à OR plein écran.
- `z` masque/montre le curseur, sans effacer le motif sous-jacent ; `p` fait avancer la couleur CPC de l'encre 1 modulo 27 (grand rectangle central), journaux `HW4 PALETTE`.
- `r` retourne à la sonde HW3 initiale, qui doit conserver la possibilité de répéter le cas `9`, puis `b` pour le boot CPC.

Renvoyer **photos de chacun des trois modes**, de la démonstration couleur/curseur et du MODE2 viewport si possible, ainsi que les journaux complets UART comprenant `HW4 MODE_READY`, `HW4 MODE_DRAWN`, `HW4 PALETTE`, `HW4 CURSOR`, `HW3 DEVICE_MEMORY`, et les éventuels erreurs/timeouts. Sans cet essai **statut ON_DEVICE_UNVERIFIED**, même si la CI Xtensa est verte. La PR reste **ouverte, non fusionnée** et doit revenir en revue Pilotage seulement après correction des anomalies et retour explicite PO `ON_DEVICE_PO_REPORTED_PASS`.

## Limites et jalons suivants
HW4-B (extraction du pilote), HW4-C (BASIC + écran), MODE2 fidèle 80-colonnes en sortie physique et caractères CPC complets restent **hors périmètre** de HW4-A. Ne pas confondre capture PPM, compilation Xtensa et validation matérielle.
