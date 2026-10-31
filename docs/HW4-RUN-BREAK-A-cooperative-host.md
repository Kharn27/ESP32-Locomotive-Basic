# HW4-RUN-BREAK-A — cooperative C99 runtime host driver

Mandat: [#200, décision Pilotage 31/10/2026](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/200#issuecomment-6537786880).
Base exacte: `main@16f26cf69a9a1343a33cd93b0d6f46fc63c0fec0`.
La PR #220 modifie CONSOLE, UART et les deux CMakeLists : **aucun de ces fichiers n'est touché** dans cette tranche.

## Contrat du pilote

- `integration/hw4_run_scheduler.[ch]` n'alloue rien, n'utilise aucun matériel ou FreeRTOS, conserve un seul `BasicSessionRuntime` réel. Le client a déjà soumis `RUN`. `init` attache un exécuteur `BSR_RUNNING`. `slice` appelle `bsr_step_events` au plus `quantum` fois (1..128). `YIELDED` ne fait **aucun** `bsr_stop`, ne modifie ni le programme ni le curseur; le slice suivant reprend à la même position. Le total de pas est un **compteur saturant**, pas un budget terminal 256/4096.
- Le caller fournit des buffers non recouvrants et **deux callbacks obligatoires**: `preflight` sans effet de bord sur **toute** la ligne (y compris les futurs événements INK), et `replay` qui traite en ordre les tranches PRINT et les événements PEN/INK avec `print_offset`. Un refus du préflight supprime toute sortie visible de cette ligne. Une erreur du replay est **fail-stop** : le scheduler n'essaie pas la ligne suivante ni ne prétend annuler des pixels déjà affichés. Le receiver doit assurer lui-même l'atomicité du replay, ou documenter son échec matériel partiel. L'exécuteur a consommé la ligne sur `BSR_OK`, donc une ligne non affichée n'est jamais rejouée automatiquement.
- `BSR_END` donne `ENDED`; les vrais échecs `BSR_EXECUTOR_ERROR` donnent `EXECUTOR_ERROR` avec leur `BSRResult` intégral en `last_result`, conservant `BSR_RUNNING` et `BasicExecutor.cursor` pour le diagnostic #195 **avant** `bsr_stop`. Un refus du renderer donne `DISPLAY_ERROR` et sa phase exacte. Aucun `ERROR` artificiel lors d'une cession de quantum, aucun texte `ERR/ERL` ou `Ready` inventé.
- BREAK est une demande booléenne synchrone `request_break` ou un `poll_break` avant chaque instruction. Une demande du callback termine l'instruction déjà validée/affichée, puis empêche toute instruction suivante; un BREAK effectif appelle `bsr_stop` une seule fois et rend `BROKEN`, conservant les lignes. Le runtime ne peut pas être partagé entre threads C99/ISR sans synchronisation extérieure. Après `BROKEN` ou `ENDED`, seul un **nouveau RUN explicite** suivi d'un nouvel `init` redémarre.
- Quantum en **nombre de lignes**, pas en millisecondes : le traitement UART/tactile, le délai FreeRTOS et la politique de latence réelle appartiennent à la future tranche B, pas au module host. Pas de nouvelle tâche, heap, PSRAM, framebuffer, DMA ni modification du coeur. Le message CPC historique de BREAK reste `CPC_DIAG_UNVERIFIED`. Le CYD de cette tranche est **ON_DEVICE_UNVERIFIED**.

## Tests indépendants de CMake avant fusion #220

```sh
CC=gcc   SANITIZERS=  sh tests/run_hw4_run_scheduler.sh
CC=clang SANITIZERS=  sh tests/run_hw4_run_scheduler.sh
CC=gcc   SANITIZERS=1 sh tests/run_hw4_run_scheduler.sh
CC=clang SANITIZERS=1 sh tests/run_hw4_run_scheduler.sh
```

Le shell compile **tous les fichiers core/*.c réels** avec le nouveau module et `tests/test_hw4_run_scheduler.c`. Quatre exécutions GitHub Actions GCC/Clang × sanitizers OFF/ON sur les sources réelles ont été obtenues par un workflow éphémère, au SHA f338cf86e45455a4368b2a31b3f839609b606e46 (SUCCESS : https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41160632831). Le workflow éphémère a ensuite été **retiré du diff**, car le garde-fou CI-OPT3 refuse toute famille de workflows non déclarée (UNKNOWN_OR_MISSING_WORKFLOW). Le script autonome reste exécutable. Cela ne constitue pas un CTest intégré à la CI historique. Tests :

- `10 PEN 3:PRINT "SCROLL GREEN" / 20 GOTO 10` : **4160 pas** répartis en 130 quanta de 32, sans `ERROR` artificiel, sans `bsr_stop`, programme inchangé, ordre PEN/PRINT et octets vérifiés.
- BREAK externe sur `YIELDED`, demande pendant callback au troisième pas, BREAK par poll avant exécution, absence de PRINT après interruption, `bsr_stop` une fois, reprise par nouveau `RUN` seulement.
- `PEN 2:PRINT "A":PEN 1:PRINT "B"` puis `END` : ordre exact, `BSR_END` distinct, `NEVER` non exécuté.
- `PEN 16` L20 : `BE_INVALID_PEN`, conservation de `BSRResult`, de `BSR_RUNNING`, de la vraie ligne 20 et des buffers/du programme avant diagnostic; aucun faux code CPC.
- Entrée `RUN+`, quantum nul et supérieur à 128, receiver nul, manque d'espace événements/PRINT, refus de préflight, échec replay, préflight INK rejetant la ligne entière sans PRINT partiel.

## Barrières explicites

La matrice autonome ne vaut **ni** CTest de la CI historique **ni** build ESP-IDF. Dès fusion de #220 et mandat conservé, synchroniser la branche A avec `main`, enregistrer module et CTest sans conflit dans CMake, relancer GCC/Clang OFF/ON + ASan/UBSan, CI-ARCH, OPT3, CPC permanent, Xtensa 3 profils, comparaison mémoire exacte A0 avant remise finale. Le raccord CONSOLE, le BREAK UART, le `Ready` visuel, le traitement LCD/FreeRTOS et l'essai physique PO sont **exclus de A**; ne pas lancer B sans mandat Pilotage.
