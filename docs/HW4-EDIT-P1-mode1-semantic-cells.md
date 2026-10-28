# HW4-EDIT-P1 — Grille E2 sémantique MODE1

**Mandat :** [issue #136](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/136) — base autorisée `main@ab55ec8e15fcffabb63529c4b063ffb27bfb7833`.
**Statut :** implémentation proposée, PR en revue Pilotage ; décision matérielle et fusion non acquises.

## Contrat E1 / E2 / E3

- **E1 :** position curseur vidéo ; rendu inverse transitoire, sans écriture dans les 16 000 octets VRAM.
- **E2 :** exclusivement dans `CpcVideo`, 25 lignes × 40 colonnes MODE1, coordonnées 0..24 / 0..39. `cell_char[1000]` contient les octets dessinés par `cpc_video_put_cell`, `cell_valid[125]` a un bit par cellule. Un espace écrit explicitement est **connu** ; une case effacée ou jamais écrite est **inconnue**. La lecture `cpc_video_read_cell` n'infère rien depuis les pixels, n'altère aucun état et ne modifie pas `*character` si `*known == false`. Elle rejette les arguments invalides et les modes 0/2 sans toucher les sorties.
- **E3 :** octets de la ligne source (`UartLine`) et état de l'éditeur ; E2 ne modifie jamais E3, ne soumet rien au BASIC et ne traite aucune touche COPY.

## Propriétaire unique et synchronisation

`cpc_video_put_cell` dessine les 64 pixels par `cpc_video_put`, lequel invalide la cellule MODE1 touchée. Seulement **après** le dernier pixel, `put_cell` écrit l'octet et rétablit sa validité : un glyphe ne s'auto-invalide donc pas. Les erreurs de coordonnées, de callback ou de PEN/PAPER sont rejetées avant mutation.

`cpc_video_put` graphique invalide uniquement le bit correspondant à son pixel MODE1. Le `scroll_up(rows)` vérifie les paramètres avant mutation, puis déplace les rangées de 640 octets raster, les groupes de 40 caractères et les groupes de 5 octets de validité, et invalide les rangées exposées. `rows=0` ne modifie rien ; 1, 24, 25 sont couverts par tests. `set_mode` (y compris `!CLS`) met les caractères/validités à zéro. MODE0/MODE2 conservent le rendu historique mais aucune lecture E2 n'y est exposée.

Tous les chemins console visés utilisent cette surface : boot `cpc_boot_console`, flux `CpcText` (dont `LIST/RUN` et LF/wrap), édition HW4-EDIT-A, backspace et `!CLS`. Aucun hook dans le pilote LCD/SPI/DMA ni copie de framebuffer ; pas d'allocation, de tâche ni de cache historique secondaire. Les allocations raster `pixels` restent fournies par l'appelant.

## Tests et limites des preuves

- `test_hw4_edit_p1` : 1000 cases par position, espaces explicites, remplacement/écrasement, lecture pure, invalidation graphique, canaris des buffers, rejets sans mutation, scrolling 0/1/24/25 et rejet 26, boot, CR/LF, wrap, éditeur, clear et changement de mode.
- `hw4_edit_p1_mutation.py` : baseline GREEN réelle puis deux modifications temporaires des sources réelles : suppression du mouvement des validités au scroll et omission de l'invalidation d'un pixel graphique. Une détection RED par assertion est exigée ; aucun oracle CPC n'est modifié.
- Les suites CTest historiques `cpc_video`, PPM, B2, HW4-EDIT-A et CPC permanent restent des gardes de non-régression ; **aucune empreinte d'image n'est re-scellée**.
- Les assertions E2 sont un contrat interne de portage, **pas** une observation historique CPC de COPY. Les transitions U02/U03/U06/U07/U08 restent NON_OBSERVÉES ; **B1/COPY non autorisé**.

## Budget et mesures

Stockage : 1000 + 125 = **1125 octets utiles** dans `CpcVideo`, et éventuel alignement de fin de structure. Mesure hôte LP64 selon les champs actuels : `sizeof(CpcVideo)` passe de 48 à 1176 octets, soit +1128 octets ; **ce n'est pas une mesure de DRAM Xtensa**. La mesure finale `idf.py size` du même HEAD doit établir Flash, IRAM et DRAM réellement consommés ; le plafond P1 est +2048 octets de DRAM console. Aucune mesure de heap/pile CYD n'est inférée d'un build.

## Test PO — seulement après CI 100 % verte

Sur la **branche P1 au SHA communiqué** : dans le VS Code ESP-IDF habituel, choisir la branche, utiliser Build / Flash / Monitor standard (projet existant `firmware/esp32_display_probe`). Vérifier boot/Ready ; `10 PRINT 2`, flèche gauche sur `2` (inverse lisible), flèche droite (restauration) ; `LIST/RUN/NEW` ; scroll texte ; `!CLS`. Renvoyer `PASS` ou `FAIL`, la version et le journal pertinent (avec `dma_fault`, `dma_timeouts`, heap et marge de pile **s'ils sont émis**). Pas de photo ni commande Git extraordinaire. **Avant cette preuve, ON_DEVICE_UNVERIFIED.**

**Remise :** le développeur propose ; le Pilotage examine, accepte/fusionne ; le PO réalise uniquement les tests matériels.
