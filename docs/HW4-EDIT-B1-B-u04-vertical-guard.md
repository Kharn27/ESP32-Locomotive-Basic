# HW4-EDIT-B1-B — U04 garde verticale E3 (29 octobre 2026)

Mandat Pilotage : [#154, commentaire officiel](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/154#issuecomment-6492803047) ; parent #96. Base : `main@91205a5c3336580c22273b54782ceb3388057d77` (PR #150 intégrée). Branche autonome : `feat/hw4-edit-b1-b-vertical-guard`.

## Provenance et limite

Le PO a observé directement sur **CPC 6128 BASIC 1.1 réel** que ↑/↓ après début d'une saisie (ex. `10`) refusent le mouvement et produisent le BIP historique. La capture WebM n'est pas archivée dans GitHub : **`U04_PARTIAL_PO_OBSERVED` seulement**. Ce n'est ni une validation ROM indépendante ni un oracle de hauteur/son ; `CPC_STEP_QUANTITY_UNVERIFIED` demeure.

## Sémantique implémentée

- Seul `uart_line_feed_screen` (routeur console) retourne `UART_LINE_NAV_BLOCKED` sur **CSI simple complète** `ESC[A` / `ESC[B`, lorsque `screen_navigation == false && length > 0 && !poisoned`. `uart_line_feed` historique n'est pas changé.
- Le refus conserve E3 (120 octets + NUL), curseur E3, état READY/poisoned, focus, E1/VRAM et E2 (1000 caractères + 125 validités) ; le parseur consomme et normalise la CSI, sans livrer ses octets à BASIC. Aucun scroll, rendu mutateur ni soumission.
- **E3 vide** : navigation verticale E1 et scroll B1-A conservés. **Focus E1 vrai avec E3 non vide** : navigation E1 préexistante conservée, mais **non caractérisée sur CPC**. Les tests C1 conservent ce cas via état hôte explicite, sans prétendre qu'il s'agit d'un trajet CPC observé. Flèches horizontales, BS, Delete, Home, Entrée unique et CRLF gardent leur comportement.
- La console écrit `HW4-EDIT-B1-B NAV_BLOCKED direction=UP|DOWN reason=E3_NONEMPTY source_bytes=N`. Elle émet une **unique tentative de BEL ASCII 0x07 sur UART0 par refus** via le transport UART existant. En cas d'échec, `BEL_UNAVAILABLE` est journalisé. L'audibilité dépend du terminal hôte ; **aucun BIP sonore matériel CYD garanti**, aucun GPIO/timer/PWM/I2S ou périphérique ajouté.

## Preuves automatisées et limites

`hw4_edit_b1_b_vertical_guard` couvre refus répétés avec `10`, `10 PRINT 2` et 120 octets, curseurs au milieu/en fin, CSI fragmentées/inconnues/longues, invariance de E1, VRAM 16 000 octets, E2 et E3 121 octets, source/programme canari, E3 vide puis vidé au BS, navigation E1 malgré E3 hôte non vide, Entrée E3, Home distinct d'Entrée, CRLF et `LIST`/`RUN` natifs (`2\n`). `hw4_edit_b1_a_screen_navigation` conserve explicitement les scénarios C1 de focus E1 avec E3 occupé. Les tests Linux ne remplacent pas une preuve CYD réelle.

## C1 correctif : première frappe E1 vide

Arbitrage Pilotage [revue #155](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/155#pullrequestreview-5696600561) et [issue #154](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/154#issuecomment-6494826469). Sur E1 en navigation libre **avec E3 vide**, le premier ASCII imprimable (0x20–0x7E) est inséré **une seule fois** par `uart_line_feed_screen` et notifié par `UART_LINE_E1_START_EDIT`. L'orchestrateur rebase l'ancre `CpcUartEditor` et `CpcText` aux **coordonnées E1 physiques** avant affichage, sans lire les anciens caractères E2. Un seul Entrée finalise ensuite E3. BS/DEL/CSI/non-imprimable ne démarrent aucun éditeur E1 ; une E3 non vide en focus E1 reste protégée selon la politique antérieure. Le retour C1 E1 vide via Entrée et Home restent distincts. **Politique UX hôte**, pas oracle CPC ajouté.

La régression C99 `c1_po_route` reproduit exactement ↑↑↓↓→→←← suivi de `10 PRINT 2` sans Entrée préalable, avec ancien texte E2 visible sous le curseur ; une seule Entrée, LIST = `10 PRINT 2`, RUN = `2`, puis NEW/LIST vide. La matrice `c1_first_key_filters` et `c1_edges` couvre contrôles, CSI fragmentées/paramétrées, retour E1/E3, haut/bas écran, colonne 39, wrap différé, scroll, 120/121 et canaris. `NAV_BLOCKED` en E3 occupée reste inchangé.

## Validation CYD obligatoire par PO AVANT toute fusion

Même workspace VS Code, `firmware/esp32_display_probe`, ESP-IDF **v5.5.6**, profil `CONSOLE`, carte ESP32-2432S028R **sans PSRAM** :

```sh
cd firmware/esp32_display_probe
idf.py fullclean
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```

Vérifier **App version = les 7 premiers caractères du HEAD exact de cette PR** et noter le SHA flashé. **Test C1 prioritaire après flash du nouveau HEAD** : E3 vide, ↑↑↓↓→→←←, puis taper **directement** `10 PRINT 2` sans Entrée préalable. Attendre `HW4-EDIT-B1-B-C1 E1_START_EDIT` dès `1`, texte visible à la position E1, `source_bytes=1`, `e2_copied=0`, puis **un seul** Entrée doit enregistrer la ligne ; LIST=`10 PRINT 2`, RUN=`2`. Contrôler aussi case historique E2 sous le curseur : elle ne doit pas alimenter la ligne BASIC. Sur saisie vide, ↑ puis ↓ : événement `NAV` et mouvement autorisés. Taper `10` (sans Entrée), ↑ puis ↓ : deux logs `NAV_BLOCKED`, texte et curseur inchangés ; le terminal peut ou non rendre BEL audible. Compléter ` PRINT 2`, Entrée unique, puis `LIST` (ligne `10 PRINT 2`), `RUN` (affiche `2`). Dans une nouvelle saisie, taper puis supprimer tous les caractères par BS, vérifier ↑/↓ de nouveau autorisées. Contrôler `DEVICE_MEMORY`, `dma_fault=0`, `dma_timeouts=0`, `lcd_error=ESP_OK` et absence de panic. Fournir log UART brut avec App version, séquences, mémoire, PASS/FAIL et photo LCD nette ; toute anomalie est conservée avec logs.

Statut logiciel et budget à renseigner depuis **le HEAD final** après CI Xtensa 3/3, `po-standard-build`, guards et tests complets. Tant que le PO n'a pas flashé ce SHA et montré ses preuves : **`ON_DEVICE_UNVERIFIED` ; PR non fusionnée, décision réservée au Pilotage**. #153 / J1.15-C, READY #151, COPY et son matériel restent exclus.

## C2 — borne horizontale E3 occupée (29 octobre 2026)

Mandat : [revue Pilotage #155](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/155#pullrequestreview-5697597311). Retour PO sur le **SHA C1 `0bf48df`** : reprise E1→E3 à la première frappe PASS, NAV_BLOCKED ↑/↓ PASS, mais `10` puis → au bout quittait E3 en focus écran ; Entrée repeignait `10` à la rangée suivante avant soumission. Statut de **l'ancien SHA** : `ON_DEVICE_PO_REPORTED_PARTIAL_PASS_WITH_HORIZONTAL_ESCAPE_FAIL`.

**Correctif hôte C2 :** avec `screen_navigation=false` et `length>0`, ← à `cursor_pos=0` et → à `cursor_pos=length` rendent `UART_LINE_NONE`, sans franchir vers E1, sans mutation visuelle, curseurs, E2/E3, VRAM ni programme. Déplacements intérieurs, édition/suppression et Enter unique inchangés. Avec E3 vide, déplacement E1 libre conservé ; E1+E3 occupé forcé par état hôte explicite préserve le comportement fail-closed. **Aucun BIP CPC horizontal revendiqué**, ni oracle CPC ajouté.

**Synchronisation prioritaire** avec `main@249725779005fcd57898104fc4a419a015ff2ac6` faite en amont : arène STRING 4096 octets, `j115c_init_store`, `BASIC_ARENA_READY`, test STRING et gardes Xtensa maintenus. Le correctif ne touche ni `core/` ni les formats STRING.

Test hôte `c2_horizontal_bounds` : huit → depuis `10` en fin de saisie, ← répétés depuis début de `10 PRINT 2`, déplacements intérieurs/DELETE/insertion, row24 col39 et scroll, tampon plein 120/121, canaris VRAM/E2/source/éditeur, effacement BS jusqu'à E3 vide puis navigation E1/C1, et ENTER unique READY. Les cas synthétiques E1+E3 sont explicités sans prétendre qu'ils sont physiquement accessibles après C2. Gardes U04, C1 première frappe, Home/CRLF, LIST/RUN/NEW et STRING restent dans les tests.

**Nouveau HEAD et nouveaux tests/CI requis** ; retest physique PO obligatoire sur ce nouveau SHA, sans transférer le PASS partiel C1. Scénario : `10` → RIGHT×3 (aucun NAV, sans changement du curseur), Enter unique → BASIC_SUBMIT sans RETURN_EDIT ; `10` → LEFT jusqu'à 0 puis LEFT supplémentaire sans sortie, RIGHT intérieur ; puis C1 première frappe, U04, et STRING A$=BONJOUR/PRINT A$ ; heap/stack, DMA, LCD, absence de panic.
