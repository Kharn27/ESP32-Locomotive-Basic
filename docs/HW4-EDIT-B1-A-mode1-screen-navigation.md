# HW4-EDIT-B1-A — MODE1 E1/E2/E3 navigation

**Mandat :** [#149](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/149), base `main@e019a0cdd67730df21b8737d62e32fb6f1ffe2ea`. Politique hôte distincte de la fidélité exacte CPC.

## Contrat

E1 = `CpcVideo.cursor_row/column/visible` (grille 40×25), overlay inverse *sans écriture raster*. E2 = les cellules sémantiques MODE1 **existantes** `cell_char[1000]` et `cell_valid[125]`, jamais reconstruites depuis les pixels. E3 = `UartLine.data[121]`, longueur, position d'édition, **seule** source remise à `bsr_submit`. Le BASIC en mémoire ne dépend d'aucun de ces déplacements.

Le collecteur existant `uart_line_feed` conserve son contrat EDIT-A ; `uart_line_feed_screen` est la variante du produit. Dans le focus E3, ←/→ éditent la saisie jusqu'à ses bornes (insertion/BS/Suppr comme EDIT-A) ; ↑/↓ ou ←/→ à une borne E3 activent la navigation libre E1. Pendant E1 libre, les quatre flèches bougent l'overlay, les frappes ASCII/BS/Suppr sont ignorées ; aucune ancienne cellule E2 ne devient une saisie. Aucun retour automatique au focus E3 par seule coïncidence row/col.

**Correctif C1 — ENTER depuis E1 :** la frappe Enter renvoie `UART_LINE_RETURN_EDIT` sans soumettre ; le curseur reprend l'édition **à colonne 0 de la rangée immédiatement au-dessous de sa position physique E1 pré-Enter** (0,21 → 1,0 ; 12,20 → 13,0). À la rangée 24, un scroll destructif **vers le haut d'une rangée** libère 24,0 (pas hôte provisoire). Une source E3 vide reste vide ; une source non vide, y compris 120 octets, est redessinée exclusivement depuis son propre buffer E3 (sans lire l'ancienne grille E2). Home (`ESC[H`) conserve distinctement l'ancien **retour à l'ancre E3** sans retour chariot. Depuis E3, **un seul Enter soumet normalement**, sans double Enter imposé. Depuis E1, l'Enter de retour ne soumet jamais la ligne E2 survolée. La CSI inconnue/paramétrée/malformée ne pollue jamais BASIC ; en E1 libre, Enter avec CSI incomplète consomme celle-ci sans effacer E3. Le CRLF reste unique. C'est une politique conservatrice **hôte**, pas une revendication sur Enter historique U05.

↑/↓ conservent la colonne. Au bord supérieur, ↑ fait descendre pixels+E2, effaçant définitivement la rangée inférieure. Au bord inférieur, ↓ fait monter pixels+E2, perdant définitivement la rangée supérieure. Les nouvelles rangées sont PAPER et cellules E2 **inconnues**, pas des espaces valides. Le pas **une rangée par flèche** est provisoire : `CPC_STEP_QUANTITY_UNVERIFIED`. ←/→ franchissent les frontières horizontales intérieures ; aux coins extrêmes restent bornées (U01 non caractérisé). La colonne 40 de `CpcText` demeure un *wrap différé*, jamais une colonne physique E1.

Un scroll de navigation décale la position de sortie `CpcText` et l'ancre `CpcUartEditor` si toujours représentables. Si tout ou partie de la ligne E3 sort, `anchor_valid=false` ; au retour explicite à E3, l'éditeur réaffiche **son buffer propre** sur la rangée vierge exposée, sans lire E2 ni perdre ses 120 octets. Aucun second framebuffer/allocateur/driver/DMA.

## Corpus et statut

- **PO CPC 6128 réel** : U02 cycle ↑/↓ colonne conservée = rapport physique ; U03 vidéo = directions et destruction des lignes qualitativement observées.
- **NON observés** : quantité historique de scroll par appui, comportement exact des coins U01, traversée E3 U04, Enter historique U05, COPY U06–U12 (COPY hors mission).
- **Hôte** : suite C99 `hw4_edit_b1_a_screen_navigation` : bornes, wrap, overlay, E2 et raster identiques sur déplacement hors scroll, scroll vers le haut/bas avec 1000 cellules/validité, disparition irréversible, PAPER 0..3, invalides/canaris, CSI fragmentées/rejetées, overflow 120, reconstitution exclusivement E3. EDIT-A et EDIT-P1, LIST/RUN/NEW/!CLS sont gardés par les suites préexistantes. CI cible 3 Xtensa, Linux 4 matrices, CPC permanent, ARCH/HW4.
- **Mémoire** : tableau VRAM 16 000 et E2 1125 octets réutilisés, nouveau `CpcScreenNavigation` = bool statique et code C99. Delta Flash/IRAM/DRAM à mesurer par CI ; aucune mesure heap/pile déduite du build.


## Matrice P0 T01–T18 et traçabilité

| P0 | État B1-A | Preuve ou limite |
|---|---|---|
| T01 — grille/coins | **TEST HÔTE** | `arrows`, bornes 0,0 et 24,39 ; comportement CPC extrême U01 non revendiqué |
| T02 — wrap ←/→ | **TEST HÔTE** | `arrows`, row5 col0 vers row4 col39 et retour ; R02/R03 partiels |
| T03 — ↑/↓ colonne | **TEST HÔTE** | `arrows`, col20 préservée ; CPC U02 rapporté |
| T04 — débordement haut/bas | **TEST HÔTE** | `scroll` dans les deux sens ; **pas=1 hôte** et CPC U03 quantité inconnue |
| T05 — curseur inverse | **TEST HÔTE** | `overlay`, rendu RGB change, raster inchangé, restauration |
| T06 — E2 immuable | **TEST HÔTE** | `same` compare 1000 caractères et 125 octets de validité après déplacement |
| T07 — E3 immuable | **TEST HÔTE** | `e3_and_ansi` compare data, longueur/cursor ; 120 octets testés en overflow |
| T08 — retour focus E3 | **TEST HÔTE** | `e3_and_ansi` Enter safe, `arrows` Home, puis commande séparée ; U05 historique non revendiqué |
| T09 — ancienne ligne affichée | **GARDE ARCHI + TEST PARTIEL** | E2 jamais lue par routeur ; test de non-soumission en navigation, pas d'oracle historique d'Enter |
| T10 — LIST/RUN/NEW | **RÉGRESSION EXISTANTE** | `hw4_edit_a_cursor_source_vram`, `hw4_c2_native_uart_runtime_tft` (pas de nouveau programme ROM) |
| T11 — 39/40/41/120 | **RÉGRESSION EXISTANTE + PARTIEL** | EDIT-A wrap/120 + B1 source conservée ; U04 navigation physique repliée non observée |
| T12 — CSI fragmentées | **TEST HÔTE** | `e3_and_ansi`, ESC puis '[' puis A ; CRLF |
| T13 — CSI invalides | **TEST HÔTE + RÉGRESSION** | `e3_and_ansi`, CSI paramétrée/incomplète, overflow, canaris ; autres CSI longues par `hw4_c2_uart_line_boundaries` |
| T14 — 16 Ko VRAM identiques | **TEST HÔTE** | `same` compare les 16000 octets durant la navigation sans scroll |
| T15 — !CLS et modes | **RÉGRESSION EXISTANTE** | `hw4_edit_p1_mode1_semantic_cells`, `hw4_c2_native_uart_runtime_tft` |
| T16 — scroll sortie et navigation | **TEST HÔTE + RÉGRESSION** | `scroll`, `expelled_e3` + `hw4_c3_b2_mode1_scroll_dma_retry`; pas de flush DMA réel en C99 |
| T17 — invalides/canaris | **TEST HÔTE + RÉGRESSION** | `invalid_and_paper`, `guards` et suite historique LCD fail-stop |
| T18 — nouvelle invite Ready | **RÉGRESSION EXISTANTE ; CYD À VALIDER** | `hw4_c2_native_uart_runtime_tft`; esthétique et position historique READY restent non observées |

Ces catégories ne sont **pas des PASS CPC ROM**. Le contrat hôte impose zéro soumission d'une ligne visible survolée ; les comportements U01/U04/U05/COPY restent non caractérisés. Chaque `TEST HÔTE` n'est PASS qu'après CI verte sur HEAD final.

## Protocole PO CYD obligatoire — SHA final de PR, avant fusion

Dans le VS Code habituel `firmware/esp32_display_probe/`, sélectionner la branche, **Build / Flash / Monitor** standard, sans fullclean ni nouvelle racine. Vérifier `App version`, LCD, curseur inverse, ←/→, ↑/↓ avec colonne constante (colonne 20), navigation libre jusqu'aux deux bords : disparition irréversible du bandeau initial vers le haut ET vers le bas ; comparaison de la vitesse/quantité de scrolling sans revendication d'exactitude historique. Pour quitter la navigation, appuyer Enter : la saisie E3 revient à **colonne 0 de la ligne immédiatement sous le curseur E1 observé**, sans soumettre d'ancienne cellule E2 ; en bas, vérifier le scroll destructif d'**une** rangée et l'ancrage (24,0). Depuis E3, **un seul Enter suffit à soumettre**. Home reste un retour séparé à l'ancre d'édition antérieure. Corriger `10 PRNT 2` en `10 PRINT 2` par ←/insertion, puis `LIST`, `RUN`, `NEW`, `LIST` vide, `!CLS`. Renvoyer PASS/FAIL, UART `NAV`/`RETURN_EDIT`, `version`, `dma_fault/timeouts`, heap libre, marge pile, anomalie LCD éventuelle. **Sans preuve matérielle sur le SHA exact : `ON_DEVICE_UNVERIFIED`.** Pilotage seul accepte/fusionne.

## HW4-EDIT-B1-A-C1 — provenance ciblée

Révision Pilotage [#150, review 5691474413](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/150#pullrequestreview-5691474413) fondée sur le CYD PO : `NAV row=0 col=21` puis ancien `RETURN_EDIT row=24 col=0` invalide. La nouvelle position CR/LF relative E1 correspond à une **observation qualitative réelle** du CPC. Les autres détails d'ENTER historique U05, COPY et le pas exact de scroll restent hors du mandat. Le test C99 C1 couvre ligne 1, ligne 13, bord inférieur, ancre expulsée/non expulsée, 120 octets, HOME et CRLF. PASS physique obligatoire sur le **nouveau** HEAD ; aucun PASS d'un HEAD précédent n'est transférable.
