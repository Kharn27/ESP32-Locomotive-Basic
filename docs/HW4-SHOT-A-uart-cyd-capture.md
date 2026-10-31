# HW4-SHOT-A — capture UART CYD de la vidéo logique (HOME E3 / !SHOT)

**Mandat Pilotage :** [#194](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/194#issuecomment-6536538002). **Base :** `main@13545e41be2d171bd3274c041e6ebbae5f4cda4b`. Gate initial vérifié sur les cinq workflows `push` : C99, CPC permanent, ARCH, OPT3, Xtensa = SUCCESS. PR #219 (oracle CLS) indépendante et non incluse. Aucun changement des oracles CPC ni des politiques PEN/INK/BASIC.

## Architecture et frontière de preuve

Le propriétaire unique `hw4_c2_console.c` appelle `cpc_video_render_row()` pour chaque ligne logique TFT absolue `0..239` avec un seul tampon `uint16_t[320]` **640 octets**. Le module C99 portable `io/hw4_shot_uart.c` crée 242 lignes ASCII v1, **sans heap/PSRAM**, sans framebuffer complet, sans lecture GRAM LCD ni modification VRAM :

- `@CYDSHOT:1|BEGIN|id=...|seq=...|w=320|h=240|pix=RGB565LE|orient=...|fw=...|sha=...` ;
- exactement 240 `ROW` indexés, 640 octets/pixels encodés en **856 caractères base64 canoniques** par ligne, CRC32/ISO-HDLC par ligne, ordre **little-endian** (distinct de l'ordre d'envoi DMA écran) ;
- `DONE` avec CRC32 global sur 153 600 octets, ou `ABORT` au premier échec d'encodage/rendu ou de transmission quand le transport reste disponible.

Un seul tampon ASCII `char[1024]` contient la trame UART d'une ligne ; aucun tampon raster de 153 600 octets. Les callbacks `send` (UART0) et `yield` sont synchrones dans l'unique tâche application. `uart_write_bytes` doit confirmer l'écriture complète ; le transfert peut être tronqué en cas de panne, mais **le décodeur P0 refuse tout PNG incomplet**. `vTaskDelay(1)` après chaque ligne permet au scheduler/idle/watchdog de tourner. Le transfert base64 seul exige 17,83 s théoriques à 115200 8N1 ; comptez davantage avec surcharge et yields : cela suspend volontairement l'entrée console pendant la capture. L'UART peut produire d'autres logs périphériques ; le décodeur ignore uniquement les préfixes monitor connus et refuse toute trame malformée.

La métadonnée `sha` est calculée par CMake **depuis le `git rev-parse --verify HEAD` réel** (40 caractères hex) ; sans dépôt Git, le build CONSOLE échoue explicitement plutôt que d'inventer une identité. `fw` vient de `esp_app_get_description()->version`. `seq` est croissant pendant le boot, `id` combine un marqueur d'amorçage (cycles CPU XOR temps depuis le boot), non cryptographique, et ce compteur. Ce marqueur ne garantit pas l'unicité entre deux redémarrages : utiliser un nouveau fichier monitor par session si plusieurs boots peuvent produire les mêmes ID ; P0 refuse strictement les doublons plutôt que de produire un PNG trompeur. L'orientation lue chez le driver est émise comme `LCD10_UNVERIFIED`, `LCD9_UNVERIFIED` ou `LCD_UNKNOWN` : **le décodeur ne transforme jamais les pixels**.

### Contrôles utilisateur et non-mutation

- `HOME` simple ANSI `ESC[H` en **E3**, y compris une ligne partiellement saisie, émet `UART_LINE_SCREENSHOT` : préservation des octets/cursor/source, pas de `READY`, pas de `RUN`, pas de `bsr_submit`. Le dernier echo écran en attente est vidé *avant* la capture, sans mutation du programme.
- `HOME` en navigation **SCREEN/E1** conserve **prioritairement** `UART_LINE_RETURN_HOME` et `cpc_screen_nav_home`. Les `CSI` paramétrées ne déclenchent pas la capture.
- `!SHOT` au prompt, insensible à la casse comme les autres commandes hôtes, fait un `end_line` / Ready / prompt normal puis capture. **Aucune soumission au BASIC**. `!CLS`, `!DEMO`, RUN/LIST/NEW et l'éditeur sont inchangés.
- Échec UART/RENDER pendant la capture : le programme et l'édition restent conservés ; ne jamais qualifier une trame incomplète de capture valide. En cas de faute UART, un ABORT est tenté, mais son échec est normal et le contrôle EOF/CRC du décodeur reste la garantie.

### Limites visuelles

Le PNG reproduit exactement les lignes **logiques** de `cpc_video_render_row` : fond/bordures, pixels PEN/INK, texte et curseur logiciel. La projection orientation 10, les marges physiques TFT, les overlays matériels (s'il en existe), la temporisation du curseur et la correspondance colorimétrique LCD **restent à démontrer sur CYD par le PO**. Il ne s'agit pas d'un screenshot SPI GRAM du panneau réel.

## Tests host reproductibles

```bash
cmake -S . -B build-shot -DBUILD_TESTING=ON
cmake --build build-shot --target test_hw4_shot_uart
ctest --test-dir build-shot -R 'hw4_shot_a_' --output-on-failure
python3 -m unittest discover -s tests -p 'test_hw4_shot_decode.py' -v
```

Le premier CTest teste le générateur C99 utilisant **le vrai CpcVideo** et le routeur `UartLine` : HOME E3/SCREEN, conservation d'une édition partielle et du curseur, sortie pure en 240 lignes, CRC calculé en flux, non-mutation intégrale de `CpcVideo` et VRAM, `ABORT` si le rendu échoue, transport partiel et metadata invalide. Le deuxième CTest exécute **le binaire C réel**, crée un journal UART complet, le passe au **décodeur P0 non modifié** `tools/hw4_shot_decode.py` et relit le PNG RGB8 (320×240) : fond bleu, bordures, PEN rouge/vert, curseur jaune. Il falsifie ensuite CRC global, manque de ligne, EOF, mélange d'IDs, largeur et endianness et exige l'absence d'écrasement d'un PNG préexistant. Ces observations sont **HOST_SYNTHETIC**, pas des pixels d'un CYD réel.

## Protocole PO physique — **uniquement après ordre du Pilotage**

1. Le Pilotage gèle un **HEAD complet** de la PR. Sur le poste du PO, extraire précisément ce SHA (`git checkout <SHA_COMPLET>`, `git rev-parse HEAD`). Ne pas tester le `main` fluctuant ni #219.
2. Depuis `firmware/esp32_display_probe` avec **ESP-IDF 5.5.6**, cible ESP32 classique et profil CONSOLE, construire puis flasher :
   ```bash
   idf.py -DLOCO_CYD_PROFILE=CONSOLE build
   idf.py -p /dev/ttyUSB0 flash
   idf.py -p /dev/ttyUSB0 monitor 2>&1 | tee /tmp/hw4-shot-a-uart.log
   ```
   Conserver sortie build et SHA réel. Si le profil nécessite une configuration dédiée déjà documentée, appliquer celle du projet ; ne pas flasher HW3/BASIC_PROBE.
3. Au prompt E3, saisir une édition **partielle** telle que `10 PRINT "AVANT"` **sans Entrée**, appuyer `HOME` (touche émettant `ESC[H`). Attendre `@CYDSHOT:1|DONE` ; vérifier la ligne E3 préservée et poursuivre avec Entrée/ `LIST`. Réitérer après une édition contenant des déplacements de curseur gauche/droite.
4. Depuis la navigation SCREEN (flèche Haut/Bas ou écran), appuyer `HOME` ; vérifier **RETURN_HOME et aucun BEGIN** ; revenir à l'éditeur normalement.
5. Au prompt, saisir `!SHOT` puis Entrée ; noter `id=` dans BEGIN. Vérifier DONE et reconstruire :
   ```bash
   python3 tools/hw4_shot_decode.py /tmp/hw4-shot-a-uart.log \
      --id <ID_DE_BEGIN> -o /tmp/hw4-shot-a.png
   ```
   Avec plusieurs captures dans le log, `--id` est **obligatoire**. Vérifier dimensions 320×240 et comparer le PNG au TFT/photo d'appui (fond bleu, bordures 20+20, PEN rouge/jaune/vert, position du curseur). Les couleurs quantifiées RGB565 peuvent différer des photographies ; noter orientation exacte et tout écart LCD.
6. Refaire `!CLS`, `NEW / 10 PEN 2 / RUN`, `LIST`, retour de curseur, puis `!SHOT`, sans altération BASIC ou perte de DMA. Collecter les journaux `DEVICE_MEMORY` avant/après, `dma_transfers`, `dma_fault`, `stack_margin_bytes`, `heap8_free`, `heap8_largest` et les erreurs/timings UART. Indiquer explicitement quel SHA a été flashé et joindre journal **brut**, PNG décodé et photo contextuelle si nécessaire.

**Critères matériels FAIL :** pas de DONE, CRC invalide, blocage watchdog, corruption console, cursor/édition/VRAM altérés, HOME SCREEN réaffecté, mémoire insuffisante, DMA fault, écart d'orientation non expliqué. Ne jamais forcer le décodeur à produire un PNG à partir d'un ABORT ou d'une capture partielle.

## Décision

La CI Linux/ARM/ESP-IDF et les métriques d'image/IRAM/DRAM/BSS seront reportées depuis **le HEAD final de la PR**, pas déduites de ce document. Aucun test CYD physique revendiqué. **Pilotage seul autorise le flash/test PO puis décide l'acceptation et la fusion.**
