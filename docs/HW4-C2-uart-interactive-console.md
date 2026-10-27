# HW4-C2 — BASIC interactif dans le projet ESP32 existant

## Organisation corrigée après retour utilisateur

**AUCUN nouveau projet VSCode, AUCUN worktree, AUCUN dossier local à créer.**
Le répertoire de compilation est **`firmware/esp32_display_probe/`**, celui du banc matériel déjà présent dans l'espace de travail. Le firmware C2 est maintenant dans **`firmware/esp32_display_probe/main/hw4_c2_console.c`**. L'ancien `main.c` de ce même projet reste **intact** pour les essais HW3/HW4. La sélection d'un et un seul `app_main` est faite par CMake :
- par défaut : `HW4_C2_CONSOLE=ON` = BASIC interactif sur LCD ;
- `idf.py -DHW4_C2_CONSOLE=OFF reconfigure build` = ancien banc de calibration sans BASIC.

Le répertoire historique `firmware/esp32_loco/` était créé et fusionné **en HW4-C1**. Il est **restauré exactement à sa version `main`**, n'héberge plus HW4-C2, n'est plus à ouvrir ni à flasher pour C2. Il subsiste seulement pour préserver le jalon C1 accepté, pas comme nouvel environnement de travail.

## Comment tester directement la branche, sans recréer de dossier

Depuis **le dépôt habituel déjà ouvert dans VSCode** (terminaux du dépôt, état `git status` propre ; sauvegarder/stasher son travail local si nécessaire) :

```bash
git fetch origin
git switch --track origin/feat/hw4-c2-uart-console
cd firmware/esp32_display_probe
idf.py -DHW4_C2_CONSOLE=ON reconfigure build
idf.py -p /dev/ttyUSB0 flash monitor
```

Si la branche locale existe déjà, remplacer `git switch --track origin/...` par `git switch feat/hw4-c2-uart-console`. Le `git rev-parse HEAD` doit correspondre au **SHA HEAD C2 final communiqué** ; aucun `git worktree add`, aucun VSCode « nouveau projet ». Le flash remplace évidemment le programme actuellement sur la carte.

## Chaîne technique et limites de C2

```text
UART0 115200 => io/uart_line (C99, 120 caractères, CR/LF/CRLF, BS/DEL)
             => bsr_submit()/bsr_step() NATIFS (store original)
             => octets LIST/PRINT réels
             => cpc_text/cpc_uart_console => CPC VRAM MODE1 16 Ko
             => cpc_video_render_row => cyd_ili9341 DMA (buffer pilote 5120 o)
```

Les diagnostics série `UART_LINE`, `BASIC_SUBMIT`, `LIST_BYTES`, `PRINT_BYTES`, `BSR_END` sont distincts de l'écho écran et des octets BASIC. Seul le `main` interactif compile par défaut dans l'image `loco_esp32_display_probe`, et un seul propriétaire manipule l'affichage/DMA.

Entrée statique de 120 octets ASCII 0x20..0x7e. Le 121e octet poison et rejette la ligne entièrement, sans appeler le runtime ; retour arrière BS (0x08)/DEL (0x7f), validation CR/LF/CRLF unique. Ligne saisie et écho TFT sont séparés. Programme 8192 o, variables 64 entrées, temporary 2048 o, output 4096 o, VRAM 16000 o statiques ; pas de framebuffer RGB565, PSRAM, allocation de heap par frappe/rendu ni second pilote SPI.

Écran 40×25 : sans scrolling CPC, les sorties LIST/PRINT qui dépassent sont clippées **avec diagnostic**, la prochaine invite efface automatiquement la surface lorsqu'il reste moins de quatre lignes (`SCREEN_PAGE_RESET`) mais ne modifie pas le programme. `!CLS` efface **uniquement l'écran**, `!DEMO` exécute les lignes BASIC originales C1 via le vrai runtime après NEW (et écrase volontairement le programme). Ces commandes sont diagnostics **hôte**, pas du BASIC CPC. `RUN` maximum 256 appels `bsr_step`, puis `bsr_stop` ; diagnostic erreur hôte, pas code `ERR` CPC. Police originale HW3 complétée par quelques glyphes de syntaxe ; police ROM CPC non revendiquée.

## Test matériel PO obligatoire après CI sur HEAD final

Saisir dans le terminal série (configurer 115200 8N1 et l'envoi de CR/LF) :
```basic
10 A%=2
20 B%=A%+3
30 PRINT B%
40 END
RUN
LIST
NEW
LIST
```

Attendre `PRINT_BYTES length=4 hex=2035200a`, `BSR_END status=BE_END steps=4`, `LIST_BYTES` authentique avant NEW, vide après NEW, et constater visuellement `5` sur fond bleu, texte de saisie/curseur. Tester une faute corrigée avec Backspace/DEL, une commande volontairement refusée (`PRINT 2` direct), `!CLS`, `!DEMO` et au moins une pagination ; noter `DEVICE_MEMORY`, heap libre/mini/plus grand bloc, stack et DMA/timeouts. Photo souhaitée, dérogation documentaire C1 NON transférable.

## Preuves et interdictions

Les suites Linux C99 incluent trois modules nouveaux : entrée UART et 100 lignes/canaris, gestion VRAM/canaris et pagination, intégration réelle `bsr_submit` / `bsr_step` / `LIST` / `NEW` / erreur atomique. Objectif : **51/51 OFF/ON** ASan+UBSan. Trois firmwares ESP-IDF 5.5.6 : C2 **dans `esp32_display_probe`**, banc BASIC `esp32_probe`, historique C1 `esp32_loco` inchangé. L'ancienne image de calibration doit rester compilable via `HW4_C2_CONSOLE=OFF`. Aucune modification `core/`, CPC fixtures/oracles, ancien moteur vidéo ou pilote DMA.

Jalon **HW4-C3 bloqué**, PR non fusionnée ; essai physique PO et revue/fusion réservées à Pilotage. CI des anciennes configurations *avant déplacement* ne valide pas automatiquement ce nouvel agencement.
