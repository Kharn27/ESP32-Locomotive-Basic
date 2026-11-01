# J1-DIAG-RETRO-O2-B — GOTO / IF missing-target CPC diagnostics

Mandat : [#246](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/246). Base initiale : `main@5d43a9c7f1ebe6e8bea4af5285327c104831603e`. Base de réconciliation A2 : `main@f3d11eb8a8723a85f08bb5317852a594780c831a` (#243 fusionnée). PR : [#247](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/247), **non fusionnée**. Le Pilotage est seul responsable de la revue et de la fusion.

## Périmètre livré

- `io/cpc_diag_policy.[ch]` : en cas de `BSR_EXECUTOR_ERROR + BE_MISSING_TARGET` et `BSR_RUNNING`, diagnostic historique GOTO (`0xA0`) ou IF (`0xA1`) uniquement pour une ligne numérotée valide, un curseur réel et un opcode atteint par le flot, dont la cible tokenisée (`0x1E`) est effectivement absente.
- Pour IF, contrôle en **lecture seule** des INTEGER existants (incluant une relation INTEGER/INTEGER) et de `THEN` ; si condition fausse, pas de diagnostic. Aucun code BASIC exécuté par la politique, aucune écriture dans l'exécuteur ou le store ; sur les cas ambigus, `HOST_GENERIC`.
- `cpc_diag_policy_format_step` : catégories et provenances GOTO/IF distinctes ; texte exact `Line does not exist in <numéro>\n` ; pas de `Ready` embarqué. Vérification de capacité avant écriture, aucun heap, aucun formatage printf.
- Tests : six témoins O2, GOSUB/PEN/RETURN/NEXT, `AFTER` IF faux, `LIST` intact, atomicité, `Ready` unique, erreurs falsifiées, chaînes/REM/références opaques, origine/curseur invalide, buffer trop court.
- Aucun changement `core/`, firmware, CMake, workflow, archives CPC ou `screen_review.json`. Le raccord CONSOLE existant avant `bsr_stop()` est conservé.

**Réserve UART :** le logger firmware existant reconnaît les provenances PEN, GOSUB et RETURN, mais pas encore les provenances GOTO/IF. Les catégories `GOTO_MISSING_TARGET_CPC` et `IF_TAKEN_MISSING_TARGET_CPC` et le texte écran sont discriminants ; le champ log historique `origin` peut afficher `HOST_NOT_CPC_ERR` à tort. Le fichier firmware est laissé intact conformément au mandat ; demander au Pilotage si une dérogation doit être envisagée.

## Matrice oracle imposée

Chaque programme est précédé de `NEW`, puis exécuté avec `RUN`. Résultats issus de #246 / [#237](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/237) ; captures CPC ROM/Caprice32 acquises, **revue humaine formelle encore en attente**.

| Programme | Sortie après RUN (avant Ready unique) | ERR/ERL oracle |
|---|---|---|
| `10 GOTO 999` ; `20 PRINT "NEVER"` | `Line does not exist in 10` | 8 / 10 |
| `10 A%=1` ; `20 IF A% THEN 999` ; `30 PRINT "NEVER"` | `Line does not exist in 20` | 8 / 20 |
| `10 A%=0` ; `20 IF A% THEN 999` ; `30 PRINT "AFTER"` | `AFTER`, aucune erreur | 0 / 0 |
| `10 GOSUB 999` ; `20 PRINT "NEVER"` | `Line does not exist in 10` | 8 / 10 |
| `370 GOTO 999` ; `400 PRINT "NEVER"` | `Line does not exist in 370` | 8 / 370 |
| `510 A%=1` ; `520 IF A% THEN 999` ; `530 PRINT "NEVER"` | `Line does not exist in 520` | 8 / 520 |

`NEVER` peut apparaître dans `LIST` / écho de saisie, mais ne doit jamais être **exécuté**. Aucune implémentation native de ERR/ERL dans cette PR.

## Preuves

- **RED** : [CI-C99 #41358818183](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41358818183) au SHA `78b6f40b1276e5bc9c4c4d31768271e0a314d3d5` : 4/4 jobs GCC/Clang OFF/ON compilés ; échec attendu de `test_j1_diag_retro_a1a`, 113/114 autres CTest passés, car GOTO/IF ne produisaient encore que `ERROR`.
- **GREEN** : consulter les jobs au **HEAD final** de #247. Ne pas attribuer des résultats antérieurs au HEAD mis à jour.
- Tests négatifs : erreur `BE_MISSING_TARGET` falsifiée sur instruction étrangère, IF faux, GOTO à cible **existante**, continuation à l'intérieur de texte, commentaire REM, code illisible, numéro/cursor non valide, BSR_SESSION_ERROR, non-RUNNING, entrée directe et paire catégorie/provenance fabriquée ; formatage atomique en capacité insuffisante.
- Contrôles requis : CI-C99 GCC/Clang OFF/ON + sanitizers, CI-CPC-PERMANENT, CI-ARCH, CI-OPT3, CI-XTENSA ESP-IDF 5.5.6 (BASIC_PROBE, CONSOLE, HW3), `python3 tools/j1_diag_retro_a0_verify.py --self-test`. Vérificateur O2 seulement après disponibilité/relecture de l'archive dans la base finale.

## Mémoire / risques

Comparer à configuration et toolchain identiques les `idf.py size` CONSOLE de `main@5d43a9c7…` et de la PR au HEAD exact (Flash Code, image, IRAM, DRAM) avec liens vers les jobs. Heap, marge pile, DMA, LCD requièrent des preuves **physiques** ; ne pas inventer de nombres.

A2 [#243](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/243) intégrée à `main@f3d11eb8a8723a85f08bb5317852a594780c831a`. Réconciliation non destructive par commit à deux parents sur branche O2-B : conserver F9/FB et valeurs historiques des catégories/provenances ; revérifier le corpus F9/MOD et les cinq CI sur ce HEAD. Oracle #237 toujours distinct, en attente de revue humaine et fusion Pilotage.

## Protocole PO — après gel SHA et feu vert Pilotage exclusivement

1. Après autorisation Pilotage, checkout de `feat/j1-diag-retro-o2b-goto-if-cpc` au **SHA complet gelé**, noter le SHA.
2. Avec ESP-IDF 5.5.6, depuis le dépôt :
   ```sh
   cd firmware/esp32_display_probe
   idf.py -DLOCO_CYD_PROFILE=CONSOLE build
   idf.py size
   idf.py -p /dev/ttyUSB0 -b 115200 flash monitor
   ```
3. Log UART complet par boot au débit 115200 ; reproduire les six cas de la matrice, en insérant `NEW` avant chaque programme, plus `LIST` après erreurs et contrôle GOSUB. `Ready` doit apparaître une seule fois par RUN ; l'instruction `PRINT "NEVER"` ne doit pas être exécutée. Fournir photos lisibles, logs et SHA affiché.
4. Relever si disponibles heap libre, plus grand bloc DMA, watermark pile et erreurs LCD dans le log, sans assimiler ces valeurs aux tailles ELF. **PASS** si six sorties et les contrôles correspondent ; sinon **FAIL** avec traces.

Barrières avant fusion : revue/certification humaine de l'oracle O2 #237, intégration A2 ou résolution validée, CI HEAD final, test CYD PO probant. **Aucune auto-approbation / fusion Développeur.**
