# HW4-RUN-BREAK-B — RUN coopératif CONSOLE / BREAK UART0

Mandat Pilotage : [#200 / #issuecomment-6543975346](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/200#issuecomment-6543975346).
**Base source obligatoire** : `main@104852526e818dc992a280857aa0a74337548b80` (fusion de #223).
**Branche** : `feat/hw4-run-break-b-console-uart`, PR #226.
**Périmètre** : vrai CONSOLE seulement. Aucun changement du coeur BASIC, d'oracle, de tâche FreeRTOS, de framebuffer, de profil HW3/BASIC_PROBE. Une capture SHOT n'est pas exécutée simultanément avec RUN.

## Architecture et contrat

- `bsr_submit("RUN")` place le runtime en `BSR_RUNNING`. Le CONSOLE appelle **une seule fois** `hw4_run_scheduler_init` ; aucune ligne BASIC n'est exécutée dans `execute_line`. Le prompt n'est plus réémis à l'entrée de RUN. Le `!DEMO` existant emprunte également cette voie.
- À chaque itération de l'unique `app_main` : `touch_poll()` puis jusqu'à **16 octets UART0** non bloquants examinés par `hw4_run_break_input_feed`, puis `basic_run_slice` d'au plus **8 pas BASIC**. `YIELDED` signifie continuation, maintien du curseur, aucun `bsr_stop`, aucun `Ready`; `repaint_dirty()` transmet les bandes VRAM par le DMA existant. `vTaskDelay(1)` laisse FreeRTOS et les autres pilotes fonctionner après chaque quantum.
- `integration/hw4_run_break_input.[ch]` est C99 pur sans mémoire dynamique : commande exactement `!BREAK` insensible à la casse, terminée par `CR` ou `LF`, `CRLF` coalescé, segmentation quelconque, longueur 6 et refus borné de toute autre ligne/overflow. Aucun de ces octets n'est envoyé à E1/E3, au BASIC, à l'écran ou à SHOT. `!BREAK` saisi au prompt est un **no-op hôte**. Le BREAK par Ctrl+C/ESC CPC et son diagnostic ne sont pas implémentés (**CPC_DIAG_UNVERIFIED**).
- La commande complète appelle `hw4_run_scheduler_request_break` : le scheduler arrête via `bsr_stop` **une seule fois avant le prochain pas**. Tous les octets PRINT et PEN déjà validés/rejoués restent sur VRAM ; aucune nouvelle instruction n'est exécutée. `uart_flush_input` rejette les octets déjà mis en file, et le `LF` tardif d'un `CRLF` est ignoré à la reprise de l'éditeur. BREAK ne détruit jamais le programme. Aucun RUN fautif ou terminé ne redémarre tout seul.
- Chaque ligne de RUN utilise le **vrai** `hw4_pen_preflight` (aucune mutation) puis `hw4_pen_replay` avec `BEVideoEvent.print_offset`. `DISPLAY_ERROR` arrête immédiatement sans nouvelle instruction ni reprise implicite ; **pas de rollback garanti** si le replay a partiellement peint. `BSR_EXECUTOR_ERROR` est diagnostiqué par `cpc_diag_policy_step` **avant** l'arrêt pour conserver la vraie ligne `PEN 16`. Les erreurs de contrat `BSR_OVERLAP/BSR_INVALID_ARGUMENT` restent hôte, jamais CPC `ERR/ERL`.
- La seule transition terminale `ENDED`, `BROKEN`, `EXECUTOR_ERROR`, `DISPLAY_ERROR` ou `INVALID_ARGUMENT` déclenche un seul `apply_ready_policy` puis `prompt()`. `!SHOT` et `HOME E3` ne sont accessibles que par le chemin prompt existant. Le curseur et l'éditeur ne reçoivent aucun octet pendant RUN.
- Traces UART **bornées** : `HW4-RUN-B RUN_START quantum=8 ... sha=...`, puis une ligne `YIELD quanta=... steps=...` toutes les 64 tranches (=512 pas), puis `RUN_TERMINAL state=... quanta=... steps=... break_source=... stop_calls=... latency_us=... sha=...`. `memory_report("run_running")` toutes les 512 tranches et à la transition terminale ; aucune trace par pas BASIC ni par PRINT. Le log de scroll est regroupé sans changer la fréquence des flush DMA.

**Limites :** quantum compté en pas BASIC, non en millisecondes ; une ligne très coûteuse, une opération DMA ou un tactile long peut retarder le service d'un BREAK jusqu'au prochain polling. Latence réelle à mesurer sur CYD par le PO. Le flux UART0 est le même que stdout (115200), donc ne pas inonder de logs ; ne jamais lancer deux lecteurs simultanément. Une commande incomplète ne provoque aucune interruption. Après une interruption effective, tout octet saisi pendant RUN est rejeté, pas rejoué.

## Preuves hôte et CI

Le CTest `hw4_run_break_b_uart_console_contract` compile et exécute le parser, le vrai `BasicSessionRuntime`, le scheduler A, le sink CPC réel et les callbacks PEN/INK ; il teste **4160 pas en 130 quanta**, séquences de BREAK fragmentées CR/LF/CRLF et cas négatifs, `LIST/RUN/NEW` après BREAK, diagnostic `PEN 16` ligne 20, préflight INK/renderer fail-stop, END différé, Ready terminal, ainsi qu'un contrôle de l'intégration réelle à la source CONSOLE. Les anciens tests de C1/C3 ont été adaptés pour contrôler les **deux callbacks bool** `run_preflight/run_replay`, avec les quatre mutants négatifs conservés. Le garde-fou existant CI-ARCH exige désormais le chemin `CONSOLE hw4_run_scheduler_slice` → `integration hw4_run_scheduler.c bsr_step_events` plutôt que l'ancien appel direct. Aucun workflow supplémentaire n'a été créé.

Les statuts exacts sont publiés avec le **SHA final** dans la [PR #226](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/226). Ne jamais attribuer à cette PR les succès d'un ancien SHA. La suite ARCH/OPT3/CPC scellée, les trois Xtensa et le différentiel A0 doivent tous être vérifiés indépendamment.

## Procédure physique PO — NON RÉALISÉE PAR LE DÉVELOPPEUR

Prérequis : CYD ESP32-2432S028R, USB UART0 `/dev/ttyUSB0`, ESP-IDF v5.5.6, un seul programme de monitor par port, photos TFT. Ne pas fusionner tant que cette procédure n'a pas été exécutée par le PO sur le SHA exact de la PR.

1. Sur le poste du PO, effectuer un vrai `git fetch` puis un checkout propre de la PR et vérifier le **SHA complet** indiqué en remise Pilotage :

   ```sh
   git clone https://github.com/Kharn27/ESP32-Locomotive-Basic.git
   cd ESP32-Locomotive-Basic
   git fetch origin feat/hw4-run-break-b-console-uart
   git switch --detach origin/feat/hw4-run-break-b-console-uart
   git rev-parse HEAD
   git status --porcelain
   cd firmware/esp32_display_probe
   idf.py --version
   idf.py -B build -DLOCO_CYD_PROFILE=CONSOLE set-target esp32
   idf.py -B build -DLOCO_CYD_PROFILE=CONSOLE build
   idf.py -p /dev/ttyUSB0 -B build flash
   ```

   L'assertion `git rev-parse HEAD == SHA complet de la remise` est **obligatoire**. La sortie `HW4-RUN-B RUN_START sha=...` doit afficher le même SHA. Après flash, utiliser **soit** `idf.py -p /dev/ttyUSB0 monitor` pour un essai manuel, **soit** le script Python ci-dessous, jamais les deux simultanément.

2. Au prompt, saisir successivement (Entrée après chaque ligne) :

   ```text
   NEW
   10 PEN 3:PRINT "SCROLL GREEN"
   20 GOTO 10
   RUN
   ```

   Attendu : lettres vertes / défilement visible, **aucun `ERROR`** à 256 pas, aucune ligne `Ready` entre quanta. Capturer l'UART et une photo avant BREAK. Observer une trace `YIELD ... steps=4608` ou davantage, preuve de dépassement des **4096 pas**.

3. Pendant le RUN, envoyer `!BREAK` suivi de `CR` ou `LF` par UART0 ; pour le fragmenté, envoyer `!Br`, attendre, puis `EaK\\r\\n`. Attendu : `RUN_TERMINAL state=4 ... break_source=UART_CR stop_calls=1`, pas de nouveaux PRINT après ce marqueur, `HW4-READY-A READY_POLICY transition=RUN_RETURN emitted=1` une seule fois et prompt opérationnel. Relever `latency_us` (du dernier octet complet BREAK au terminal), mémoire et DMA `DEVICE_MEMORY`. Photographie après arrêt.

4. Au prompt, faire `LIST` (les 2 lignes doivent être identiques), `RUN` (redémarrage explicite seulement), `!BREAK` par `LF` après redémarrage, `NEW`, `LIST` (vide). Ensuite saisir `10 PEN 2`, `20 PEN 16`, `30 PRINT "NEVER"`, `RUN` : diagnostic attesté `Improper argument in 20`, aucun `NEVER`, un Ready. Tester `!BREAK` hors RUN : aucun BASIC soumis. Tester `!DEMO` pour une fin normale. Vérifier un aller-retour `HOME E3` et les flèches de l'éditeur. Exécuter `!SHOT` **exclusivement au prompt**, jamais dans la boucle infinie.

5. Test semi-automatisé facultatif, après flash et fermeture du monitor. Revenir à la racine du dépôt (`cd ../..` depuis `firmware/esp32_display_probe`) :

   ```sh
   python3 -m pip install pyserial
   python3 tools/hw4_run_break_b_po.py --port /dev/ttyUSB0 \
       --log hw4-run-break-b-po-uart.log --timeout 600
   ```

   Le script envoie NEW/programme/RUN, détecte **steps>4096 dans le vrai UART**, envoie un BREAK fragmenté, attend un seul terminal et la transition Ready, puis vérifie une nouvelle interaction LIST/NEW. Le script ne remplace pas la photo ni le contrôle de la régularité du scroll, du délai, des anomalies LCD/DMA et de l'absence de reboot.

**Preuves à remettre au Pilotage par le PO :** SHA exact flashé, logs UART115200 bruts (dont RUN_START, YIELD>4096, RUN_TERMINAL, READY_POLICY, diagnostic PEN L20, DEVICE_MEMORY), photos écran avant/pendant/après BREAK, notes sur défilement vert, délais BREAK, erreurs/reboots, valeurs heap8_free/heap8_largest/stack_margin_bytes, compteur DMA et temps de transfert. Chaque résultat doit être explicitement PASS ou FAIL ; un échec bloque la fusion.

**État tant que les preuves PO ne sont pas fournies :** `ON_DEVICE_UNVERIFIED`, sans sémantique BREAK CPC revendiquée.
