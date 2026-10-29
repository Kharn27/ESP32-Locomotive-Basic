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

## Validation CYD obligatoire par PO AVANT toute fusion

Même workspace VS Code, `firmware/esp32_display_probe`, ESP-IDF **v5.5.6**, profil `CONSOLE`, carte ESP32-2432S028R **sans PSRAM** :

```sh
cd firmware/esp32_display_probe
idf.py fullclean
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```

Vérifier **App version = les 7 premiers caractères du HEAD exact de cette PR** et noter le SHA flashé. Sur saisie vide, ↑ puis ↓ : événement `NAV` et mouvement autorisés. Taper `10` (sans Entrée), ↑ puis ↓ : deux logs `NAV_BLOCKED`, texte et curseur inchangés ; le terminal peut ou non rendre BEL audible. Compléter ` PRINT 2`, Entrée unique, puis `LIST` (ligne `10 PRINT 2`), `RUN` (affiche `2`). Dans une nouvelle saisie, taper puis supprimer tous les caractères par BS, vérifier ↑/↓ de nouveau autorisées. Contrôler `DEVICE_MEMORY`, `dma_fault=0`, `dma_timeouts=0`, `lcd_error=ESP_OK` et absence de panic. Fournir log UART brut avec App version, séquences, mémoire, PASS/FAIL et photo LCD nette ; toute anomalie est conservée avec logs.

Statut logiciel et budget à renseigner depuis **le HEAD final** après CI Xtensa 3/3, `po-standard-build`, guards et tests complets. Tant que le PO n'a pas flashé ce SHA et montré ses preuves : **`ON_DEVICE_UNVERIFIED` ; PR non fusionnée, décision réservée au Pilotage**. #153 / J1.15-C, READY #151, COPY et son matériel restent exclus.
