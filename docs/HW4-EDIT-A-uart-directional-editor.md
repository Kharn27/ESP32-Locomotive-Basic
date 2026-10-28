# HW4-EDIT-A — Éditeur de ligne BASIC à curseur mobile (C99)

Mandat : [#96, décision Pilotage du 28/10/2026](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/96#issuecomment-6466560935).
Base initiale : \`main@c3d00cd8995ecf3e63631177e761806dcc6bc405\`.
Ce jalon concerne **l'éditeur UART/écran**, et ne modifie pas les commandes
ou la syntaxe de Locomotive BASIC.

## Contrat des touches

| Flux UART brut | Événement | Effet source/cursor | Effet visible |
|---|---|---|---|
| ASCII \`0x20..0x7e\` | \`APPEND\` | insertion à \`cursor_pos\`, suffixe décalé, position +1 | rafraîchissement suffixe |
| \`ESC[D\` (gauche) | \`LEFT\` | position -1 si possible | curseur seul |
| \`ESC[C\` (droite) | \`RIGHT\` | position +1 si possible | curseur seul |
| \`0x08\` ou \`0x7f\` | \`DELETE\` (Backspace) | efface avant curseur, position -1 | suffixe + cellule finale effacée |
| \`ESC[3~\` (Suppr) | \`DELETE_FORWARD\` | efface sous curseur, position inchangée | suffixe + cellule finale effacée |
| Suppr à fin de ligne, flèche en butée | \`NONE\` | aucune mutation | aucun dessin |
| \`CR\`, \`LF\`, \`CRLF\` | \`READY\` | soumet exactement \`data[0..length)\` | saut physique de ligne |
| Séquence CSI inconnue/intégralement close | \`IGNORED\` | aucun octet BASIC | aucun dessin |
| CSI interrompue par \`CR/LF\`, ou overflow 121 | \`REJECTED\` | soumission interdite | ligne refusée puis nouveau prompt |

Invariant logique : \`data[121]\`, \`0 <= cursor_pos <= length <= 120\`
et \`data[length] == 0\` ; aucune allocation. Les paramètres de CSI sont
limités à 16 octets. Seules les formes **exactes** \`ESC[D\`, \`ESC[C\`
et \`ESC[3~\` sont des commandes d'édition ; les formes avec paramètres
(\`ESC[1;2D\`, par exemple) sont ignorées. Les séquences inconnues sont
consommées, sans devenir des caractères BASIC.

## Affichage

\`CpcUartEditor\` ne conserve que la position du premier caractère
et le nombre de cellules précédemment peintes. Il prend les octets et
la position du curseur **directement depuis** \`UartLine\`, puis actualise
les seules cellules affectées dans la même VRAM MODE1 de 16 000 octets.
Le curseur est un overlay ; il ne modifie pas la VRAM. Un effacement
réécrit aussi l'ancienne dernière cellule avec PAPER, sans traces
fantômes. Les lignes de 40 colonnes sont parcourues par indices
bornés ; à la ligne 25 le scroll natif réajuste l'ancre, sans
second framebuffer ni nouvelle tâche LCD. \`CpcText\` reste le
récepteur du flux de sortie BASIC et du \`Ready\` ; au CR, sa position
correspond à la **fin** du buffer, pas à la position momentanée de
l'éditeur. \`dirty_bands\` et le DMA fail-stop existants sont réutilisés.

Ce modèle est dérivé des **observations en émulateur CPC fournies par le
PO**. Il ne constitue pas une mesure indépendante effectuée sur un
Amstrad CPC 6128 physique. Aucun bip, Home/End, rappel de lignes ou
éditeur multi-lignes de programme en mémoire n'est ajouté.

## Tests Linux

La nouvelle suite \`hw4_edit_a_cursor_source_vram\` exécute le vrai
\`uart_line_feed\`, le vrai rendu MODE1, le vrai moteur \`bsr_submit\` /
\`bsr_step\`, et vérifie :
- la correction de \`10 PRNT 2\` en \`10 PRINT 2\` et de \`20 PRIXNT 3\`
  en \`20 PRINT 3\` avant la soumission ; \`LIST\` littéral et \`RUN\`;
- la non-mutation du programme pendant l'affichage et \`!CLS\`, et \`NEW\`;
- l'absence de pixels résiduels après suppressions, canaris de la VRAM,
  positions du curseur (overlay, sans écrasement de pixels) ;
- les 120 octets, le 121e refusé même après Backspace,
  les déplacements près de 40/80, le scroll au bas de la fenêtre,
  et les CSI tronquées.
Les anciennes suites \`test_uart_line\`, \`test_cpc_uart_console\`,
\`test_hw4_c2_integration\` sont adaptées à la distinction BS/Suppr.

Vérifier Linux GCC/Clang OFF/ON ASan/UBSan, CI-CPC-PERMANENT,
CI-ARCH, HW4-C3-B2 et les trois variantes Xtensa ESP-IDF v5.5.6
au **même HEAD**. Les suites conditionnelles SKIPPED ne sont pas
des succès. Flash, IRAM et DRAM doivent provenir des sorties du
workflow final, pas d'estimations.

## Essai physique PO obligatoire

Depuis le dépôt/VSCode existant, sur **la branche et le SHA intégral
de la PR remis après CI** (pas \`main\` si non fusionnée) :

\`\`\`sh
git fetch origin
git switch --track origin/feat/hw4-edit-a-cpc-cursor
# Si la branche existe déjà : git switch feat/hw4-edit-a-cpc-cursor
git pull --ff-only
git rev-parse HEAD
cd firmware/esp32_display_probe
idf.py -B build-c2 -DHW4_C2_CONSOLE=ON set-target esp32
idf.py -B build-c2 -DHW4_C2_CONSOLE=ON build
idf.py -B build-c2 -p /dev/ttyUSB0 flash monitor
\`\`\`

1. Noter \`START ... version=...\` et le SHA. Saisir \`10 PRNT 2\`,
   appuyer **4 fois sur ←** pour revenir avant \`N\`, insérer \`I\`,
   voir \`10 PRINT 2\`, Entrée. Ensuite \`LIST\` doit contenir
   \`10 PRINT 2\` et \`RUN\` afficher \`2\`.
2. Saisir \`20 PRIXNT 3\`, appuyer **5 fois sur ←**, puis Suppr
   (\`ESC[3~\`) pour retirer \`X\`. \`LIST\` doit donner
   \`20 PRINT 3\` ; \`RUN\` affiche successivement \`2\` puis \`3\`.
3. Tester Backspace au milieu (retire à gauche en reculant) contre
   Suppr au milieu (retire sous curseur sans reculer), Suppr en bout
   (aucune mutation), et ←/→ aux bornes.
4. Saisir plus de 40 caractères (repli), modifier un caractère avant
   et après la colonne 40, surveiller les traces visuelles ; parcourir
   une longue saisie et le bas de l'écran (scroll).
5. Vérifier \`NEW\`, \`LIST\` vide, \`!CLS\` et le bandeau au redémarrage.
   Aucune erreur DMA ou reset ne doit apparaître.

**Précaution terminal :** il doit réellement envoyer les octets
\`1b 5b 44\`, \`1b 5b 43\` et \`1b 5b 33 7e\` en UART brut.
L'ESP32 journalise les événements \`HW4-EDIT-A UART_EDIT\` avec le
\`sequence_hex\`. Un terminal qui intercepte les flèches et ne les
transmet pas ne permet pas de conclure à un défaut de l'éditeur.

Preuves : log \`version\` du HEAD flashé, séquences UART en hexadécimal,
photo écran avant Entrée / après correction, \`LIST\`, \`RUN\`, \`NEW\`,
\`!CLS\` et compteurs \`DEVICE_MEMORY\` / DMA. En l'absence de ce test
sur le nouveau HEAD : \`ON_DEVICE_UNVERIFIED\`.

**Hors périmètre :** \`core/\`, ROM/fixtures CPC, SPI, DMA,
orientation, tactile, SD, MODE2, pagination et architecture #112/#117.
Validation/fusion de la PR réservée au Pilotage.

## C1 — Curseur vidéo inverse non destructif (28 octobre 2026)

Verdict Pilotage : [PR #127, mission HW4-EDIT-A-C1](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/127#issuecomment-6473714211).
Sur le CYD au SHA `9067e589`, le PO avait validé l'édition et signalé
qu'un curseur plein recouvrait et **masquait** le glyphe (ex. `Ready`).
Ce correctif vise la cellule du curseur **au rendu**, pas sa VRAM.

Pour les pixels du curseur, une fois le MODE0 ×2 / MODE2 OR_PAIR,
EVEN ou VIEWPORT échantillonné, le rendu permute **uniquement**
les indices logiques `PEN` et `PAPER`. Ainsi une cellule vide (PAPER)
devient un bloc PEN ; un glyphe de saisie MODE1 en PEN conserve sa forme
en PAPER sur fond PEN. Les autres indices d'encre sont inchangés :
pas de généralisation à une inversion arbitraire de pixels graphiques.
`PEN==PAPER` est non distinguable et ne peut produire un curseur
visiblement inversé. L'effet ne dépend d'aucun second framebuffer,
ne modifie pas les 16 000 octets de VRAM et ne crée pas de heap.

`cpc_video_set_text_colors` marque maintenant la bande du curseur comme
dirty si **PEN ou PAPER** change ; `set_ink` conserve son invalidation totale.
Les transitions de position restaurent la cellule précédente par simple
nouvel échantillonnage. Tests : reproduction **RED sur l'ancien overlay**
(le pixel PEN d'un `R` devenait un bloc PEN et non PAPER), assertions
RGB565 glyphes/vides, mode 0 ×2, mode 1, mode 2 OR_PAIR/EVEN/VIEWPORT,
encre tierce préservée, PAPER seul, PEN seul, PEN==PAPER, déplacements,
restauration visuelle, `dirty_bands`, canaris et invariance bit-à-bit VRAM ;
intégration éditeur `PRINT` au-dessus du caractère `N`.

Limites : règle CPC physique observée en MODE1 par le PO, sans oracle
ROM exhaustif ni promesse de fidélité de l'édition plein écran MODE0/2.
Le SHA de C1 doit être revalidé sur CYD après CI, avec un contrôle visuel
simple (glyphe sous curseur lisible, restauration au départ, case vide
opaque, pas de fault DMA), sans photo obligatoire.
