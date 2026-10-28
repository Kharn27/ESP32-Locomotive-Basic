# HW4-EDIT-B1-A — MODE1 E1/E2/E3 navigation

**Mandat :** [#149](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/149), base \`main@e019a0cdd67730df21b8737d62e32fb6f1ffe2ea\`. Politique hôte distincte de la fidélité exacte CPC.

## Contrat

E1 = \`CpcVideo.cursor_row/column/visible\` (grille 40×25), overlay inverse *sans écriture raster*. E2 = les cellules sémantiques MODE1 **existantes** \`cell_char[1000]\` et \`cell_valid[125]\`, jamais reconstruites depuis les pixels. E3 = \`UartLine.data[121]\`, longueur, position d'édition, **seule** source remise à \`bsr_submit\`. Le BASIC en mémoire ne dépend d'aucun de ces déplacements.

Le collecteur existant \`uart_line_feed\` conserve son contrat EDIT-A ; \`uart_line_feed_screen\` est la variante du produit. Dans le focus E3, ←/→ éditent la saisie jusqu'à ses bornes (insertion/BS/Suppr comme EDIT-A) ; ↑/↓ ou ←/→ à une borne E3 activent la navigation libre E1. Pendant E1 libre, les quatre flèches bougent l'overlay, les frappes ASCII/BS/Suppr sont ignorées ; aucune ancienne cellule E2 ne devient une saisie. Aucun retour automatique au focus E3 par seule coïncidence row/col.

**Retour explicite :** Enter ou Home (\`ESC[H\`) revient à E3 sans soumettre ; un Enter **ultérieur** valide seulement E3. La CSI inconnue/paramétrée/malformée ne pollue jamais BASIC ; en E1 libre, Enter avec CSI incomplète consomme celle-ci sans effacer E3. Le CRLF reste unique. C'est une politique conservatrice **hôte**, pas une revendication sur Enter historique U05.

↑/↓ conservent la colonne. Au bord supérieur, ↑ fait descendre pixels+E2, effaçant définitivement la rangée inférieure. Au bord inférieur, ↓ fait monter pixels+E2, perdant définitivement la rangée supérieure. Les nouvelles rangées sont PAPER et cellules E2 **inconnues**, pas des espaces valides. Le pas **une rangée par flèche** est provisoire : \`CPC_STEP_QUANTITY_UNVERIFIED\`. ←/→ franchissent les frontières horizontales intérieures ; aux coins extrêmes restent bornées (U01 non caractérisé). La colonne 40 de \`CpcText\` demeure un *wrap différé*, jamais une colonne physique E1.

Un scroll de navigation décale la position de sortie \`CpcText\` et l'ancre \`CpcUartEditor\` si toujours représentables. Si tout ou partie de la ligne E3 sort, \`anchor_valid=false\` ; au retour explicite à E3, l'éditeur réaffiche **son buffer propre** sur la rangée vierge exposée, sans lire E2 ni perdre ses 120 octets. Aucun second framebuffer/allocateur/driver/DMA.

## Corpus et statut

- **PO CPC 6128 réel** : U02 cycle ↑/↓ colonne conservée = rapport physique ; U03 vidéo = directions et destruction des lignes qualitativement observées.
- **NON observés** : quantité historique de scroll par appui, comportement exact des coins U01, traversée E3 U04, Enter historique U05, COPY U06–U12 (COPY hors mission).
- **Hôte** : suite C99 \`hw4_edit_b1_a_screen_navigation\` : bornes, wrap, overlay, E2 et raster identiques sur déplacement hors scroll, scroll vers le haut/bas avec 1000 cellules/validité, disparition irréversible, PAPER 0..3, invalides/canaris, CSI fragmentées/rejetées, overflow 120, reconstitution exclusivement E3. EDIT-A et EDIT-P1, LIST/RUN/NEW/!CLS sont gardés par les suites préexistantes. CI cible 3 Xtensa, Linux 4 matrices, CPC permanent, ARCH/HW4.
- **Mémoire** : tableau VRAM 16 000 et E2 1125 octets réutilisés, nouveau \`CpcScreenNavigation\` = bool statique et code C99. Delta Flash/IRAM/DRAM à mesurer par CI ; aucune mesure heap/pile déduite du build.

## Protocole PO CYD obligatoire — SHA final de PR, avant fusion

Dans le VS Code habituel \`firmware/esp32_display_probe/\`, sélectionner la branche, **Build / Flash / Monitor** standard, sans fullclean ni nouvelle racine. Vérifier \`App version\`, LCD, curseur inverse, ←/→, ↑/↓ avec colonne constante (colonne 20), navigation libre jusqu'aux deux bords : disparition irréversible du bandeau initial vers le haut ET vers le bas ; comparaison de la vitesse/quantité de scrolling sans revendication d'exactitude historique. Pour revenir de navigation à la saisie, appuyer une fois Enter : **aucun BASIC n'est alors soumis**, la saisie existante revient ; Enter suivant la soumet. Corriger \`10 PRNT 2\` en \`10 PRINT 2\` par ←/insertion, puis \`LIST\`, \`RUN\`, \`NEW\`, \`LIST\` vide, \`!CLS\`. Renvoyer PASS/FAIL, UART \`NAV\`/\`RETURN_EDIT\`, \`version\`, \`dma_fault/timeouts\`, heap libre, marge pile, anomalie LCD éventuelle. **Sans preuve matérielle sur le SHA exact : \`ON_DEVICE_UNVERIFIED\`.** Pilotage seul accepte/fusionne.
