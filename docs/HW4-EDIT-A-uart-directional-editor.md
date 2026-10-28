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

## Contrat de livrabilité PO — rectificatif Pilotage

La [décision Pilotage du 28 octobre 2026](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/127#issuecomment-6475689358)
remplace les instructions Git et `idf.py -B build-c2` précédemment
demandées au PO. **Son seul parcours requis** : sélectionner la branche
`feat/hw4-edit-a-cpc-cursor` dans son **VS Code existant**, puis lancer
sa commande habituelle de compilation / flash / monitor ESP-IDF pour
le projet existant `firmware/esp32_display_probe`, variante console
`HW4_C2_CONSOLE=ON`. **Aucun nouveau workspace, dossier `build-*`,
reconfiguration manuelle, purge de cache ou commande Git supplémentaire**
n'est requis du PO.

La [CI-XTENSA](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/workflows/ci-xtensa.yml)
ajoute le job `po-standard-build` : dans **le même** workspace, il compile
`main` puis bascule sur la branche PR et reconstruit le projet via
`idf.py build` avec le dossier standard `build/` conservé, sans purge.
Il vérifie `HW4_C2_CONSOLE=ON`, l'unicité de `app_main`, la présence
de l'image .bin et son descripteur embarqué `esp_app_desc_t` : le
champ `version` doit contenir le SHA court du HEAD compilé. Le run
[40735065920](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40735065920)
a établi `PO_STANDARD_ON=PASS` sur `7ae04f1`; la première validation
du descripteur au SHA `4303654` est traçable dans le
[run 40736077910](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40736077910).
Les preuves finales doivent être relues sur le **dernier HEAD**.

**Limite de provenance :** ceci simule le parcours de build ESP-IDF 5.5.6
dans GitHub Actions, **pas l'instance VS Code/Debian du PO**. L'échec
localement rapporté n'est pas reproduit sur cet environnement et sa
cause reste **indéterminée**. Aucun correctif hypothétique de cache n'est
appliqué. La branche ne doit pas être annoncée comme livrable au PO sans
nouvelle décision du Pilotage.

### Contrôle matériel ciblé, seulement après feu vert Pilotage

Une fois la branche déclarée livrable par le Pilotage, le PO n'a qu'à
flasher comme d'habitude puis donner son retour visuel explicite :
- sur une saisie `10 PRINT 2`, déplacer le curseur sur le `2` :
  le caractère reste lisible en vidéo inverse ;
- déplacer le curseur à droite : le `2` retrouve son affichage normal
  et la case vide montre le bloc du curseur ;
- confirmer absence de reboot, défauts ou timeouts DMA.

Pas de photo obligatoire, ni de collecte technique supplémentaire
imposée au PO. L'ancienne campagne fonctionnelle `9067e589...`
reste valable pour ce seul SHA : chaque nouveau HEAD est
`ON_DEVICE_UNVERIFIED` tant qu'un essai CYD n'est pas rapporté.

**Exclusions inchangées :** aucun changement du cœur `core/`, des
touches, de la ROM CPC, de LCD/SPI/DMA, du matériel ou d'EDIT-B1.
L'acceptation technique et la fusion appartiennent au Pilotage.

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

### Empreintes PPM C1 : re-scellage motivé

La CI C99 au SHA de diagnostic `4b4fc92896aa3c8ee28ee4391830d3c4ad4dd391`
([run #40721623224](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40721623224))
a généré les trois PPM complets après C1 : MODE0
`55e44da158c152d5d835332e4710352778c910355712f96564e69b6bb0b31940`,
MODE1 `17b8918a5289c2c98c47ab6f4fc7700d69df3f56953521468bbe481ee6b196e9`,
MODE2 `e3befe375e2454a7aaa6dac1d2b01ffb719f078bab1e70da7b9e055e70d7a439`.
Les anciens digests MODE0 et MODE1 (`9df98bd1...` et `64e512a5...`)
sont modifiés **exclusivement par le nouveau rendu de curseur** ;
le digest MODE2 OR_PAIR est identique à l'antérieur pour cette fixture.
Le contrôle conserve trois attentes SHA-256 explicites, deux exécutions
intégrales et la vérification de taille/entête des images ; aucune
tolérance ou suppression de test. Le test de scrolling [HW4-C3-B2]
consomme la bande dirty provoquée légitimement par un changement
de PAPER avant de vérifier que `scroll_up(0)` reste un no-op.
