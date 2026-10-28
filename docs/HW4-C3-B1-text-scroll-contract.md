# HW4-C3-B1 — Oracle CPC et contrat de scrolling MODE1

Mission : [issue #108](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/108).
Base B1 initiale : main `1e6dc4ae7974b32423a9511fa761d292876784fd`, après [PR #103](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/103).
Base intégrée en **HW4-C3-B1-C1** : main `d7a291283630a2b1a21cc145beb3d1d5a9e467a9`, comprenant J1.10-B [PR #107 fusionnée](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/107).
Statut : **B1-C1, sans code runtime B1 ; B2 non autorisé**. Liens : moteur [#74](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/74), éditeur [#96](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/96), police [#97](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/97).

## État de preuve et provenance

- CODE_OBSERVED : lecture de l'implémentation de main au SHA ci-dessus ; tests Linux B1 host = observation **du code actuel**, non du CPC.
- FIRMWARE_DOCUMENTED : CPC Firmware Guide décrit TXT_OUTPUT &BB5A, TXT_VALIDATE &BB87 (validation de curseur, fenêtre/scroll) et TXT_GET_CURSOR &BB78. Le fichier joint 'basic.asm', désassemblage BASIC 1.1, montre LIST e1cd/e214, sortie texte c3e9 -> &BB5A, CLS c284 -> &BB6C, WINDOW c323 -> &BB66. C'est une analyse de trajet ROM, pas une capture de scroll.
- CPC_SCREEN_CAPTURED : PNG original généré par Caprice32/ROM authentique ; son SHA et sa provenance peuvent être vérifiés. **Pas une preuve de caractères écran octet pour octet**, pas une preuve de pixels TFT.
- CPC_ORACLE_VERIFIED : réservé à un cas effectivement acquis **et inspecté** pour la propriété «scroll» ; ne pas appliquer cette classe automatiquement sur un simple succès CI. Au démarrage B1, tous les cas restent **UNVERIFIED**.
- Sources documentaires : https://www.cantrell.org.uk/david/tech/cpc/cpc-firmware/txtvdu.htm et https://cpcwiki.eu/index.php/BIOS_Text_Functions .
- [J0.24-C8](J0.24-C8-list-screen-evidence.md) a deux PNG authentiques pour LIST de 3 et 4 lignes, **insuffisants pour le débordement**. Ne pas modifier les archives C8 ni les 18 classes LIST/RUN historiques UNVERIFIED.

## Diagnostic précis du défaut sur main

1. 'io/cpc_uart_console.c' : 'cpc_uart_console_prompt' teste column != 0 et row < 25 pour LF ; quand **row > 20** il appelle 'cpc_uart_console_clear', signale 'reset_page = true'. 'clear' appelle 'cpc_video_set_mode' : efface **toute** VRAM, initialise les couleurs et réinitialise 'CpcText' ; rien à voir avec un scroll.
2. 'video/cpc_text.c' : column = 40 signifie «wrap en attente» jusqu'au prochain caractère affichable. Un LF augmente row jusqu'à 25. À row==25 les caractères sont **clippés**, non défilés et le curseur devient invisible.
3. 'io/cpc_uart_console.c' : le gardien d'append rejette row>=25 et même row==24 && column>=39 ; l'ultime colonne de saisie de la rangée basse est empêchée. Distinct du clip de sortie.
4. 'firmware/esp32_display_probe/main/hw4_c2_console.c' : 'display_bytes' transmet LIST au 'cpc_text_write', puis 'repaint_dirty'; il peut donc **clipper avant de rappeler prompt()**. 'SCREEN_FULL_OUTPUT_CLIPPED' et ensuite 'SCREEN_PAGE_RESET ... reason=no_room_for_120_byte_input' / 'INPUT_READY ... policy=auto_page_non_cpc' diagnostiquent deux effets distincts.
5. 'tests/test_cpc_uart_console.c' vérifie déjà l'ancienne pagination (saturation). 'tests/test_hw4_c2_integration.c' vérifie LIST/NEW/erreurs/atomicité BASIC. **La nouvelle sonde B1** 'tests/test_hw4_c3_b1_baseline.c' couvre exclusivement le défaut connu : row21->reset, row25->clip, wrap 40, CR, canaris. Ne pas la présenter comme test de scrolling natif.

Reproduction sur l'image console ON : saisir les 26 lignes '10 REM L01', ... '260 REM L26', puis LIST ; observer les diagnostics UART et le contenu écran ; refaire avec 32 lignes, puis LIST encore, NEW et LIST. Le résultat varie avec la position initiale du curseur (boot HW4-C3-A). Un effacement vidéo n'est jamais à interpréter comme un NEW implicite. L'état programme BASIC doit être vérifié séparément par LIST après le reset ; les octets de LIST ne sont pas une archive d'écran CPC.

## Matrice reproductible : 12 cas ROM-backed

Script : 'tools/hw4_c3_b1_scroll_oracle.py', un **processus CPC6128 neuf par cas**, Caprice32 4.6.0 commit 8c778bf072a06fb7c23b9cccd179041db7f79a52 ; ROM BASIC 1.1 SHA-256 31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562 ; AMSDOS SHA-256 ea65e0fb44ee93ede4b6c507509b7e5ddf497fb7155023bea91ef229469fa04d. Les instructions numérotées sont envoyées en premier, puis CLS avant le LIST écran, et capture des PNG. Pas de PRINT #8, SNA/ROM archivé ou OCR. La macro capture peut modifier le contexte vidéo (overlay Caprice32), ce qui doit être annoté lors de la lecture.

| ID | Entrée / opération CPC | Question à examiner dans le PNG | Classe initiale |
| --- | --- | --- | --- |
| list_26 | 26 lignes REM distinctes, CLS, LIST | franchissement des 25 rangées, première/dernière rangée, Ready | UNVERIFIED |
| list_32 | 32 lignes, CLS, LIST | plusieurs défilements successifs, ordre restant | UNVERIFIED |
| wrap_40 | ligne numérotée totale de 40 caractères ; LIST | wrap exactement colonne 40 | UNVERIFIED |
| wrap_80 | ligne totale de 80 ; LIST | 2 rangées, wrap et curseur | UNVERIFIED |
| wrap_120 | ligne totale de 120 ; LIST | 3 rangées, continuation et Ready | UNVERIFIED |
| input_after_list | 26 lignes ; LIST puis PRINT 7 direct | saisie/sortie après dépassement | UNVERIFIED |
| cursor_edges | CLS ; `LOCATE 1,1:PRINT "FIRST";` ; `LOCATE 1,25:PRINT "LAST";` (deux commandes atomiques) | haut/bas, dernière rangée avant nouveau Ready | UNVERIFIED avant inspection C1 |
| cr_last_row | CLS ; `LOCATE 1,25:PRINT "ABCDE";CHR$(13);"Z";` (une commande atomique) | CR sans LF dans la même commande, puis effet du Ready final | UNVERIFIED avant inspection C1 |
| repeat_list_once | 27 lignes ; LIST ; capture | première sortie, référence du cas répété | UNVERIFIED |
| repeat_list_twice | 27 lignes ; LIST ; LIST ; capture | comparaison à repeat_list_once, sans capture écrasée | UNVERIFIED |
| new_after_list | 27 lignes ; LIST ; NEW ; LIST | programme effacé par NEW et écran courant | UNVERIFIED |
| window_default | WINDOW 1,40,1,25 ; CLS ; LIST | fenêtre par défaut explicitée | UNVERIFIED |

Préparer une inspection par cas : vérifier visuellement positions/texte des rangées 0 et 24, texte central restant, Ready, curseur, ordre, marges/overlay émulateur ; noter si une macro est refusée ou une ligne de 120 caractères tronquée. Un PNG original et hashé permet 'SCREEN_CAPTURED_VISUAL_REVIEW_PENDING' mais ne démontre pas encore le déplacement des lignes. Les sorties attendues ne sont **pas codées en dur comme prétendus résultats de la ROM**. Aucun comportement de sous-fenêtre BASIC ne sera implémenté en B2 sans mandat.

CI dédiée : '.github/workflows/hw4-c3-b1-scroll.yml', GCC C99 strict OFF/ON + capture Caprice32 image GHCR immuable et artéfact 'hw4-c3-b1-scroll-cpc'. Les archives courantes restent inchangées et la CI Linux générale (OFF/ON) reste indépendante.

~~~sh
python3 tools/hw4_c3_b1_scroll_oracle.py \
  --caprice tests/oracles/caprice32 \
  --output /tmp/hw4-b1-unique
# Examiner manifest.json et chaque PNG original avec SHA-256 horodaté.
~~~

L'inspection manuelle doit publier : run ID + HEAD + cas + nom du PNG + SHA-256 + auteur de l'inspection + observation exacte + ambiguïtés. Sans ces informations : 'UNVERIFIED'. Les images C8 ne seront pas recyclées comme preuve B1.

## Contrat proposé pour B2, à arbitrer par le Pilotage

### Surface logique et mémoire

'CpcVideo.pixels' occupe **16000 octets utiles** (80 octets de raster × 200), même si on parle couramment d'une carte CPC de 16 Ko (16384). **Ce n'est pas la carte VRAM entrelacée du Z80.** MODE1 = 320×200×2 bpp = 40×25 cellules de 8×8 ; une rangée texte = 640 octets, chaque cellule de 8 pixels = 2 octets par ligne raster. Surface existante exclusivement, pas de tableau séparé de 1000 glyphes ni de framebuffer RGB565 de 153600 octets.

Contrat sémantique 'scroll_up(window, rows)' **sans figer de signature incompatible avec CpcVideo/CpcText**. Seule fenêtre par défaut : colonnes [0,40), rangées [0,25). Avant mutation : valider pointeurs, MODE1, grille et offsets, fenêtre non vide, et valeur 'rows' sans overflow. 'rows=0' no-op; '>25' rejet atomique ; 'rows=25' efface le contenu de fenêtre à PAPER si ce cas est retenu, à différencier de l'événement standard scroll d'une seule rangée. Toute fenêtre partielle est hors B2 et doit être explicitement rejetée/indiquée comme non prise en charge, sans scroll générique spéculatif.

Pour k dans [1,25] : copier en chevauchement via 'memmove(pixels, pixels+640*k, 16000-640*k)' ; vider les 640*k octets bas au motif PAPER 2 bits répété (PAPER 0=0x00, 1=0x55, 2=0xaa, 3=0xff). Ne jamais déplacer l'overlay du curseur dans les octets VRAM. Marquer **les 25 bandes sales** (bits 0..24) du viewport après mutation ; replacer le curseur sans col hors [0,39] ni row hors [0,24] après résultat stable, sauf état d'attente de wrap explicitement documenté en 'CpcText'. Les conditions précises de déclenchement LF/CR/wrap et de Ready **restent sujettes à l'inspection CPC**. 'CpcText' doit conserver le digest FNV/compteurs d'entrée, pas de reset de session lors d'un défilement.

Le scroll ne modifie jamais 'BasicProgram', ses bytes/capacité, variables, source UART, PEN, PAPER, palette INK, BORDER, dimensions MODE0/2 ni les glyphes historiques. 'NEW' doit rester l'unique action BASIC prévue pour effacer le programme, pas un effet secondaire graphique. 'cpc_uart_console_prompt' doit perdre la politique arbitraire de réserve de quatre lignes, sous réserve de conserver l'atomicité des saisies.

### Dirty bands / TFT / DMA

Viewport y TFT=20..219, les marges 0..19 et 220..239 restent BORDER. Une bande logique de 8 lignes est rendue en 320×8×2 = **5120 octets** dans le **tampon DMA déjà détenu par le pilote**, une ligne RGB565 transitoire sur pile = 640 octets. Le pilote CYD bloque jusqu'à fin de 'cyd_lcd_send'. Après un scroll plein écran, produire le masque '0x01ffffff', transférer **25 bandes ordonnées** y=20,28,...,212, sans débordement ni bit 25..31; ne jamais recréer un DMA buffer ou une tâche.

**Danger actuel** : 'repaint_dirty' utilise 'cpc_video_take_dirty' avant le transfert. Si la bande N échoue, le masque déjà consommé peut perdre le rafraîchissement ; B2 doit prévoir la revalidation des dirty bands après erreur DMA, et le tester. Ne pas détruire les couleurs/canaris ; marquer ancienne et nouvelle bande de curseur lors d'un déplacement ; préserver le comportement PEN corrigé par HW4-A-C2. Les Golden PPM existants sont immuables.

### Plan de tests et négatifs B2, pas d'exécution prématurée

- C99 : chaque rangée initialement distincte, vérifier les **15360 octets déplacés pour k=1**, les 640 derniers à PAPER, deux scrolls successifs, motif PAPER 1/2/3, overlay curseur non destructif, caractères partiels et 40e colonne.
- Canaris : 8 octets avant/après les 16000, masque dirty, palette, curseur et store intacts ; aucun malloc/PSRAM/framebuffer RGB565.
- Atomique en rejet : pointeur nul, mode non MODE1, rows>25, fenêtre vide/inversée, row25/col40 physiques hors borne, SIZE_MAX/overflow d'indexation, curseur (0,0)/(39,24), pending-wrap col40/row24, LF en bas, et DMA simulé en échec ; vérifier snapshot complet avant/après (sauf erreur de transport où dirty doit être maintenu).
- Oracle CPC : mettre en correspondance **les 12 cas acquis et inspectés** ; s'interdire de convertir un cas image ambigu en MATCH_EXACT. Dans la CI : OFF/ON ASan/UBSan, oracles permanents inchangés, Xtensa 3/3 pour **B2**.
- **Essai PO B2 obligatoire sur CYD** : fournir branche, SHA exact, commandes 'idf.py' build/flash/monitor ; dérouler LIST>25, répéter LIST, 40/80/120 caractères, entrée après LIST, NEW, Ready/curseur, mesurer DEVICE_MEMORY, log DMA/timeouts et photos avant/après. B1 n'exige pas de test matériel CYD.

## Exclusions / frontières

B1 livre uniquement documents, diagnostic de base, sonde C99 hôte et acquisition CPC indépendante. Aucune modification fonctionnelle de 'core/', 'io/', 'video/', 'firmware/', police, HAL, LCD, bandeau, CMake ou fixtures historiques. Pas de MODE/WINDOW/CLS BASIC natif, éditeur #96, police #97, scroll arbitraire ou B2 démarré. La matrice est conditionnelle à des **captures réelles et lisibles** ; en l'absence de telles preuves, le verdict honnête reste 'UNVERIFIED'. La décision d'acceptation B1 et le déblocage B2 appartiennent exclusivement au Pilotage.


## Observations indépendantes examinées sur l'acquisition initiale (28 octobre 2026)

**Provenance du relevé :** [Actions #40612563135](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40612563135), HEAD source `84431f2706b30a6e4557cc97a177177e244db4d6`, artifact `12783329305`, archive ZIP SHA-256 `bf97cfe343fcbbe63bb131fc6697a901728a84a2a228956327fad3dee1eb0c8e`. Examen visuel manuel des PNG originaux ; les empreintes par cas sont dans `manifest.json`. La surimpression FPS en haut à gauche appartient à Caprice32, pas au BASIC. L'image du cas répété dans ce run n'était pas discriminante ; le script est modifié ensuite pour afficher `AFTER2` après le second LIST, **sans prédéclarer le résultat de cette nouvelle acquisition**.

| Scénario | Relevé sur PNG original | Classification strictement visuelle |
| --- | --- | --- |
| list_26 | Les rangées affichent 40 REM L04 à 260 REM L26, suivies de Ready/curseur ; les trois premières lignes du LIST ne sont plus à l'écran | OBSERVED_VISUAL (scroll à gauche de la zone, aucune page vide) |
| list_32 | Première ligne encore affichée 100 REM L10, dernière 320 REM L32, Ready/curseur ensuite | OBSERVED_VISUAL (défilement répété, pas de reset page) |
| wrap_40 | Une rangée avec 40 caractères de source numérotée | OBSERVED_VISUAL |
| wrap_80 | Deux rangées pour 80 caractères de source | OBSERVED_VISUAL |
| wrap_120 | Trois rangées pour 120 caractères de source | OBSERVED_VISUAL |
| input_after_list | La sortie de LIST continue avec la commande directe PRINT 7, la valeur 7 puis Ready ; la liste visible remonte à partir de 80 REM L08 | OBSERVED_VISUAL |
| cr_last_row | Ancienne saisie : `LOCATE 1,25` et `PRINT` étaient deux commandes distinctes ; « ZBCDE » était lisible mais **ne prouvait pas** un CR exécuté en rangée 25 | **UNVERIFIED** pour l'opération à la rangée 25 ; capture invalidée pour cette inférence |
| new_after_list | NEW et LIST s'affichent avec Ready après le long LIST ; aucune ligne numérotée dans la sortie du LIST suivant | OBSERVED_VISUAL (effet de NEW, non mutation BASIC par scroll) |
| repeat_list_once / twice | Captures de l'ancien run visuellement identiques : pas de preuve discriminante du nombre d'exécutions malgré les commandes JSON | UNVERIFIED sur ce run ; reprise avec marqueur |
| cursor_edges, window_default | Captures valides, mais le `LOCATE` ancien de `cursor_edges` était suivi d'un Ready intermédiaire ; fenêtre et limites non isolées | **UNVERIFIED** pour les propriétés de position au bord, et fenêtre |

Cette qualification **OBSERVED_VISUAL** est bornée aux textes et positions effectivement lisibles dans une image Caprice32 obtenue avec ROM authentique ; pas de preuve d'égalité octet ou pixel, pas de validation de fenêtre personnalisée ni de timing. Les suites C99 du moteur de notre dépôt n'acquièrent aucun statut CPC par ces observations.


## HW4-C3-B1-C1 — correction de l'oracle et rattrapage de main

Mandat : [verdict Pilotage C1, PR #109](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/109#issuecomment-6458067208) ; revue P2 [thread](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/109#discussion_r4395862520). Avant C1, les captures `cursor_edges` et `cr_last_row` laissaient `Ready` déplacer le curseur **entre** `LOCATE` et `PRINT`. Ces fichiers restent des archives B1, mais **ne sont pas des oracles de la position de la rangée 25**.

C1 remplace les séquences séparées par les commandes atomiques `LOCATE 1,1:PRINT "FIRST";`, `LOCATE 1,25:PRINT "LAST";` et `LOCATE 1,25:PRINT "ABCDE";CHR$(13);"Z";`. Le `Ready` **final**, après le PRINT direct, peut encore défiler : sa présence rend les effets exacts sur la dernière rangée non inférables sans une inspection spécifique des captures originales. Les deux classes resteront **UNVERIFIED** pour toute propriété qu'une capture terminale ne distingue pas.

Fusion de la base `main` `d7a291283630a2b1a21cc145beb3d1d5a9e467a9` requise en commit à deux parents, sans modification de J1.10-B. Exécutions C1 sur le **nouveau** HEAD à renseigner à partir de GitHub Actions : 12 cas CPC/PNG et empreintes, 2/2 banc B1, au moins 61/61 CTest OFF/ON, autres workflows SUCCESS ou SKIPPED légitime. Pas de nouveau firmware ni test sur CYD.

**Acquisition C1 : EN ATTENTE DE RÉEXÉCUTION ET INSPECTION — aucune valeur CPC ajoutée par anticipation.**
