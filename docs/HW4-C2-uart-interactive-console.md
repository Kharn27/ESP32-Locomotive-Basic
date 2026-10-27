# HW4-C2 — BASIC interactif dans le projet ESP32 existant

## Organisation corrigée après retour utilisateur

**AUCUN nouveau projet VSCode, AUCUN worktree, AUCUN dossier local à créer.**
Le répertoire de compilation est **`firmware/esp32_display_probe/`**, celui du banc matériel déjà présent dans l'espace de travail. Le firmware C2 est maintenant dans **`firmware/esp32_display_probe/main/hw4_c2_console.c`**. L'ancien `main.c` de ce même projet reste **intact** pour les essais HW3/HW4. La sélection d'un et un seul `app_main` est faite par CMake :
- par défaut : `HW4_C2_CONSOLE=ON` = BASIC interactif sur LCD ;
- `idf.py -DHW4_C2_CONSOLE=OFF reconfigure build` = ancien banc de calibration sans BASIC.

La duplication **`firmware/esp32_loco/` est supprimée de l'arbre source** à la demande du PO. Les capacités utiles C1 (source BASIC réelle, `cpc_text`, VRAM, pilote partagé) sont déjà **intégrées dans `esp32_display_probe` en variante ON** ; le scénario `!DEMO` conserve le test fonctionnel C1. Les documents et suites C1 restent des preuves historiques mais ne définissent plus un troisième projet à construire.

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

Les suites Linux C99 incluent trois modules nouveaux : entrée UART et 100 lignes/canaris, gestion VRAM/canaris et pagination, intégration réelle `bsr_submit` / `bsr_step` / `LIST` / `NEW` / erreur atomique. Objectif : **53/53 OFF/ON** ASan+UBSan sur la base J1.7-B. **Deux projets ESP-IDF** : `esp32_display_probe` compilé **ON (console)/OFF (HW3)** séparément, et `esp32_probe` (cœur indépendant). Trois **variantes de build**, pas trois projets. L'ancienne image de calibration doit rester compilable via `HW4_C2_CONSOLE=OFF`. Aucune modification `core/`, CPC fixtures/oracles, ancien moteur vidéo ou pilote DMA.

Jalon **HW4-C3 bloqué**, PR non fusionnée ; essai physique PO et revue/fusion réservées à Pilotage. CI des anciennes configurations *avant déplacement* ne valide pas automatiquement ce nouvel agencement.

## HW4-C2-C1 — correction finale de Suppr avant revue (27 octobre 2026)

**Objet :** le terminal du PO semble envoyer `ESC [ 3 ~` (hex `1b 5b 33 7e`) lors de **Suppr**. Dans l'éditeur actuel placé en bout de ligne, seul le dernier caractère peut être retiré : Suppr est donc **assimilée temporairement à Backspace**. Ceci est une adaptation de l'éditeur hôte, **pas** une revendication de fidélité au CPC.

Le collecteur **C99** `io/uart_line` traite les octets avant la source BASIC :
- `0x08`, `0x7F` : effacement historique conservé ; `ESC[3~` : **un seul événement UART_LINE_DELETE** après quatre octets complets.
- Autres CSI `ESC[...<final>` consommées entièrement sans atteindre ni la source BASIC ni l'écho TFT. Paramètres bornés à **16 octets** ; au-delà, l'état ignore jusqu'à l'octet final `0x40..0x7e`, sans allocation, aucune écriture VRAM.
- Réception fragmentée : aucun caractère partiel n'est émis en attente de `~`. `ESC` seul ou CSI incomplète suivi de CR/LF entraîne **UART_LINE_REJECTED et aucun appel bsr_submit()** ; l'éditeur revient à la prochaine invite. `ESC` suivi d'un caractère autre que `[` consomme ce caractère et ne le transmet pas. Ces choix sont documentés comme politique conservatrice non CPC. L'octet final `~` seul n'est pas traité comme suppression.
- Une ligne trop longue reste empoisonnée, y compris après Delete/Backspace. Aucun événement `DELETE` n'est envoyé au TFT si la source est déjà vide (ne pas effacer l'invite).
- Trace physique `UART_EDIT sequence_hex=1b5b337e key=ANSI_DELETE action=backspace` quand le décodage est réellement observé ; `key_hex=08/7f` pour la touche simple. `UART_LINE_REJECTED reason=incomplete_ansi` distingue le diagnostic d'un overflow.

**Tests supplémentaires** dans les trois suites Linux C2 : `ESC[3~` exactement un effacement, BS/DEL inchangés, CSI inconnues et surlongues sans pollution, séquences fragmentées, incomplètes/malformées, canaris, source/VRAM synchronisées et entrée rejetée sans mutation BASIC. Les suites historiques C1 restent inchangées.

**Preuve Xtensa demandée :** `esp32_display_probe` compilé deux fois depuis le **même dossier** avec `HW4_C2_CONSOLE=ON` puis `OFF` (dossiers de sortie `build-c2`/`build-hw3` isolés), plus `esp32_probe` indépendant, sous ESP-IDF **v5.5.6**. Vérifier **un seul symbole `app_main` défini par image** avec `xtensa-esp-elf-nm`; logs et budgets des trois variantes archivés par CI. Le workflow HW3 autonome passe explicitement `HW4_C2_CONSOLE=OFF`. Pas de nouveau dossier de code ou nouveau projet VSCode.

**Validation PO à refaire après CI verte au nouveau SHA de branche :** tester Backspace + Suppr sur une ligne visible ; ressaisir quatre lignes BASIC, `RUN`, `LIST` ; refuser `PRINT 2` puis `LIST` inchangé ; `NEW` puis `LIST` vide. Fournir journal UART avec `version=<SHA court>`, `UART_EDIT`, `BASIC_SUBMIT`, `PRINT_BYTES=2035200a`, marges heap/pile, DMA errors/timeouts et observation visuelle. Les photos de HW4-C2 précédent attestent le premier scénario, **pas** la correction C1. Un cas Suppr sans caractère éligible ne déclenche actuellement aucun bip (bip et boot CPC volontairement hors jalon).

**Interdiction de fusion automatique**, HW4-C3 toujours bloqué ; décision finale Pilotage.
