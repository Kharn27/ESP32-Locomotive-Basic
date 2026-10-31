# HW4-RUN-BREAK-A — cooperative C99 runtime host driver

Mandat: [#200, décision Pilotage 31/10/2026](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/200#issuecomment-6537786880).
Base initiale : `main@16f26cf69a9a1343a33cd93b0d6f46fc63c0fec0`.
Après fusion vérifiée de #220 : resynchronisation avec `main@ccdb4837278b8d8d56a19a858cd07d36dc40ec2a`. Les deux CMakeLists sont désormais modifiés uniquement pour enregistrer le module/test hôte et **compiler** l'objet dans le profil CONSOLE sans aucune invocation. Les fichiers CONSOLE, UART, outil screenshot, `core/` et oracles restent intacts.

## Contrat du pilote

- `integration/hw4_run_scheduler.[ch]` n'alloue rien, n'utilise aucun matériel ou FreeRTOS, conserve un seul `BasicSessionRuntime` réel. Le client a déjà soumis `RUN`. `init` attache un exécuteur `BSR_RUNNING`. `slice` appelle `bsr_step_events` au plus `quantum` fois (1..128). `YIELDED` ne fait **aucun** `bsr_stop`, ne modifie ni le programme ni le curseur; le slice suivant reprend à la même position. Le total de pas est un **compteur saturant**, pas un budget terminal 256/4096.
- Le caller fournit des buffers non recouvrants et **deux callbacks obligatoires**: `preflight` sans effet de bord sur **toute** la ligne (y compris les futurs événements INK), et `replay` qui traite en ordre les tranches PRINT et les événements PEN/INK avec `print_offset`. Un refus du préflight supprime toute sortie visible de cette ligne. Une erreur du replay est **fail-stop** : le scheduler n'essaie pas la ligne suivante ni ne prétend annuler des pixels déjà affichés. Le receiver doit assurer lui-même l'atomicité du replay, ou documenter son échec matériel partiel. L'exécuteur a consommé la ligne sur `BSR_OK`, donc une ligne non affichée n'est jamais rejouée automatiquement.
- `BSR_END` donne `ENDED`; les vrais échecs `BSR_EXECUTOR_ERROR` donnent `EXECUTOR_ERROR` avec leur `BSRResult` intégral en `last_result`, conservant `BSR_RUNNING` et `BasicExecutor.cursor` pour le diagnostic #195 **avant** `bsr_stop`. Un refus du renderer donne `DISPLAY_ERROR` et sa phase exacte. Un `BSR_OVERLAP` ou `BSR_INVALID_ARGUMENT` est un **échec de contrat hôte** (`HW4_RUN_INVALID_ARGUMENT`, `BSRResult` inchangé), jamais une erreur BASIC/CPC; aucune étape n'est comptée. **Après `DISPLAY_ERROR`, le BSR peut rester `BSR_RUNNING`, mais la reprise implicite du scheduler est interdite** : le propriétaire examine l'état, arrête explicitement avec `bsr_stop` puis soumet un nouveau `RUN` avant toute nouvelle session. Même en cas de replay partiellement appliqué, le pilote ne revendique **aucun rollback vidéo**. Aucun `ERROR` artificiel lors d'une cession de quantum, aucun texte `ERR/ERL` ou `Ready` inventé.
- BREAK est une demande booléenne synchrone `request_break` ou un `poll_break` avant chaque instruction. Une demande du callback termine l'instruction déjà validée/affichée, puis empêche toute instruction suivante; un BREAK effectif appelle `bsr_stop` une seule fois et rend `BROKEN`, conservant les lignes. Le runtime ne peut pas être partagé entre threads C99/ISR sans synchronisation extérieure. Après `BROKEN` ou `ENDED`, seul un **nouveau RUN explicite** suivi d'un nouvel `init` redémarre.
- Quantum en **nombre de lignes**, pas en millisecondes : le traitement UART/tactile, le délai FreeRTOS et la politique de latence réelle appartiennent à la future tranche B, pas au module host. Pas de nouvelle tâche, heap, PSRAM, framebuffer, DMA ni modification du coeur. Le message CPC historique de BREAK reste `CPC_DIAG_UNVERIFIED`. Le CYD de cette tranche est **ON_DEVICE_UNVERIFIED**.

## Tests intégrés à CTest après fusion #220

```sh
CC=gcc   SANITIZERS=  sh tests/run_hw4_run_scheduler.sh
CC=clang SANITIZERS=  sh tests/run_hw4_run_scheduler.sh
CC=gcc   SANITIZERS=1 sh tests/run_hw4_run_scheduler.sh
CC=clang SANITIZERS=1 sh tests/run_hw4_run_scheduler.sh
```

La suite est maintenant inscrite dans le CMake racine (`hw4_run_break_a_cooperative_bsr`, exécutable C99 lié à `hw4_run_scheduler` et au vrai `basic_session_runtime`). La cible ESP-IDF CONSOLE compile aussi `integration/hw4_run_scheduler.c` dans la bibliothèque du composant, **sans** raccord de boucle UART/LCD. HW3 et BASIC_PROBE doivent continuer à compiler inchangés. Le shell autonome compile toujours **tous les fichiers core/*.c réels** avec le nouveau module et `tests/test_hw4_run_scheduler.c`. Quatre exécutions GitHub Actions GCC/Clang × sanitizers OFF/ON sur les sources réelles ont été obtenues par un workflow éphémère, au SHA f338cf86e45455a4368b2a31b3f839609b606e46 (SUCCESS : https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41160632831). Le workflow éphémère a ensuite été **retiré du diff**, car le garde-fou CI-OPT3 refuse toute famille de workflows non déclarée (UNKNOWN_OR_MISSING_WORKFLOW). Le script autonome reste exécutable. Cela ne constitue pas un CTest intégré à la CI historique. Tests :

- `10 PEN 3:PRINT "SCROLL GREEN" / 20 GOTO 10` : **4160 pas** répartis en 130 quanta de 32, sans `ERROR` artificiel, sans `bsr_stop`, programme inchangé, ordre PEN/PRINT et octets vérifiés.
- BREAK externe sur `YIELDED`, demande pendant callback au troisième pas, BREAK par poll avant exécution, absence de PRINT après interruption, `bsr_stop` une fois, reprise par nouveau `RUN` seulement.
- `PEN 2:PRINT "A":PEN 1:PRINT "B"` puis `END` : ordre exact, `BSR_END` distinct, `NEVER` non exécuté.
- `PEN 16` L20 : `BE_INVALID_PEN`, conservation de `BSRResult`, de `BSR_RUNNING`, de la vraie ligne 20 et des buffers/du programme avant diagnostic; aucun faux code CPC.
- Entrée `RUN+`, quantum nul et supérieur à 128, receiver nul, manque d'espace événements/PRINT, refus de préflight, échec replay, préflight INK rejetant la ligne entière sans PRINT partiel.
- Réserve Pilotage #5722431501 : `PRINT "AVANT":END:PRINT "INVISIBLE"` et version `PEN 2:PRINT "AVANT":END:PEN 3:PRINT "INVISIBLE"` : préfixe PRINT/PEN unique conservé, suffixe invisible, `BSR_END` différé au pas suivant.
- Buffer de PRINT recouvrant la mémoire du programme : `BSR_OVERLAP` préservé, état hôte `INVALID_ARGUMENT`, aucune mutation du programme, aucune émission et aucun comptage d'étape.

## Barrières explicites

Le CTest est désormais inscrit; le statut `HOST_VERIFIED` requiert la réussite effective des 4 cellules C99 au nouveau SHA. Confirmer séparément CI-ARCH, OPT3, CPC permanent, les 3 profils Xtensa et la mémoire A0 vs le `main@ccdb4837278b8d8d56a19a858cd07d36dc40ec2a` réellement intégré. **Compilation du module en CONSOLE** ne signifie pas liaison de fonctions à l'application ni BREAK actif. Le raccord CONSOLE, le BREAK UART, le `Ready` visuel, le traitement LCD/FreeRTOS et l'essai physique PO sont **exclus de A**; ne pas lancer B sans mandat Pilotage.
