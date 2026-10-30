# HW4-DIAG-PEN-A — rattrapage diagnostique PEN natif

**Mandat :** [Pilotage #195, autorisation du 30/10/2026](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/195#issuecomment-6534067285).
**Base obligatoire :** `main@c24ee5859d5dc8a955f4a20fac266628133bcfc2` après fusion de la PR #190.
**Modification :** `io/cpc_diag_policy.[ch]`, propriétaire CONSOLE et tests C99 `test_hw4_pen_a`. Aucune modification de `core/`, des oracles ou de l'affichage matériel.

## Preuve indépendante et RED de départ

Le témoin historique archivé *avant ce correctif* dans `docs/J1.17-A-pen-cpc-oracle.md` et `tests/fixtures/cpc6128/j1_17_a_pen/` confirme deux acquisitions indépendantes pour `10 PEN 16` et `10 PEN -1` : **ERR=5, ERL=10**, aucun glyphe issu de la ligne fautive. La capture du **CPC physique** fournie par le PO complète les archives : `Improper argument in 10` puis `Ready`. On ne transforme pas cette observation L10 en preuve CPC indépendante L20 : L20 teste le *mécanisme natif* de sélection du numéro de ligne.

**RED sur `main` :** le retour CYD PO du 30/10 à la PR #190, préfixe `6c7df8d`, montre `BSR_STEP_FAIL BSR=7 BE=24`, `STEP_DIAG INVALID_PEN`, puis `ERROR` pour `10 PEN 16` ; jamais `PRINT "NEVER"`. Le code de base de `hw4_c2_console.c` appelle `display_error()` pour tout échec d'étape. Ceci est la preuve du défaut initial ; ne pas appeler ce RED une exécution locale de nouveaux tests si ce n'est pas le cas.

## Contrat et provenance

- Le résultat de `bsr_step_events()` est examiné **avant** `bsr_stop()`. `BSR_EXECUTOR_ERROR + BE_INVALID_PEN` provient, au HEAD de base, uniquement de `pen_argument()` sur les formes attestées `16` et `-1` ; ce n'est **pas** un numéro `ERR` CPC.
- Le sélecteur C99 `cpc_diag_policy_step()` vérifie **RUNNING**, les pointeurs `BasicExecutor.program` et `BasicSessionRuntime.program`, la validité de `bp_next(program, &cursor, &line)`, l'offset courant et l'offset de statement. Le numéro retourné est **`line.number`** réel, jamais `10` constant. Le diagnostic porte `CPC_DIAG_ORIGIN_NATIVE_PEN_CPC_ORACLE` et `CPC_DIAG_PEN_IMPROPER_ARGUMENT`.
- `cpc_diag_policy_format_step()` produit les octets ASCII `Improper argument in ` + décimal réel + `\\n`, sans heap ni `snprintf`. Le formatter refuse une provenance CPC invalide, une ligne zéro et toute capacité trop faible, sans sortie partielle. `cpc_diag_policy_write_step()` écrit au seul `CpcText` existant.
- Tout autre `BSRResult` retourne `CPC_DIAG_ORIGIN_HOST`, ligne 0, `ERROR\\n`. En particulier : `PEN 5..14` toujours `UNVERIFIED/UNSUPPORTED`, `BE_NO_EVENT_SPACE`, rejet renderer `SET_INK_UNSUPPORTED`, `RUN+`, commande directe, budget 256. Aucun `ERR/ERL` synthétique, aucune extension `INK`.
- Le `Ready` dépend **exclusivement** de `cpc_ready_policy_apply(... CPC_READY_RUN_RETURN)` après `basic_run()`, une fois, sans modification de la politique ou du curseur. Le formatage ne déclenche jamais `Ready`.

## Tests automatisés

Le CTest existant `hw4_pen_a_typed_events_mode1` couvre avec vrai `BasicSessionRuntime`, `bp_next`, `CpcText`, `CpcVideo` et adaptateur de diagnostic :
- L10 : `PEN 16`, `PEN -1` ; L20 : idem après un PEN valide L10 ;
- après `!CLS` réel, nouvelle exécution du même programme avec numéro conservé ;
- même ligne `PEN 2:PRINT "NEVER_BEFORE":PEN 16` : rejet atomique de toute la ligne ;
- comparaison **octet à octet** du message avec `\\n`, écriture et un `Ready` constaté à travers les glyphes ;
- préservation de l'état `BasicSessionRuntime`, des tampons d'événements, sortie, programme et VRAM avant diagnostic ;
- contre-exemples : `PEN 5/14`, saturation événements, `INK` non rendu, `RUN+`, direct non supporté, provenance fabriquée, ligne zéro ;
- maintien du test précédent sur l'ordre `PEN` / `PRINT` / `INK`, et de la politique `HOST_GENERIC` de `HW4-DIAG-A`.

L'archive CPC J1.17-A est reprise **en lecture seule** et ne certifie pas un test physique du nouveau binaire. Le test L20 est une extrapolation de présentation de la ligne native réelle, pas une acquisition CPC L20.

## Vérifications / livraison

Les preuves sur le **HEAD final** doivent être reportées ici ou dans la PR sans les anticiper : C99 GCC/Clang OFF/ON + ASan/UBSan, CI-ARCH, OPT3, CPC permanent/indépendant, Xtensa ESP-IDF 5.5.6 3 profils, mémoire CONSOLE vs `main`, code de `App version`. Un job SKIPPED ou en attente n'est pas un PASS. Aucun lancement matériel du développeur n'est revendiqué.

## Protocole de test physique PO (après revue préliminaire Pilotage)

Sur le poste Linux avec ESP-IDF v5.5.6, utiliser le **SHA complet de la PR** que le Pilotage aura figé et vérifier que `git rev-parse HEAD` correspond. Dans `firmware/esp32_display_probe` :

```bash
idf.py -DLOCO_CYD_PROFILE=CONSOLE build
idf.py -p /dev/ttyUSB0 flash
idf.py -p /dev/ttyUSB0 monitor
```

Dans le moniteur UART / sur l'écran MODE 1 :
1. `NEW` puis `10 PEN 16`, `20 PRINT "NEVER"`, `RUN` : **`Improper argument in 10`**, puis un seul `Ready`, aucun `NEVER`.
2. `!CLS` puis `RUN` : exactement le même diagnostic ; le programme est conservé.
3. `NEW`, `10 PEN 2`, `20 PEN -1`, `30 PRINT "NEVER"`, `RUN` : **`Improper argument in 20`** (le numéro n'est pas figé).
4. Contre-épreuve `NEW`, `10 PEN 5`, `RUN` : refus **hôte** restant `ERROR`, sans `Improper argument`. `10 INK 1,26` reste rejeté côté rendu, non reclassé CPC.
5. Capturer sortie UART `HW4-DIAG-PEN-A DIAG_POLICY`, `HW4-READY-A READY_POLICY`, `HW4-C2 DEVICE_MEMORY`, absence de `PRINT NEVER`, photo du TFT et vérifier le `App version` / SHA flashé.

Les tests doivent noter PASS/FAIL, position/scroll et mémoire (heap libre, bloc maximal, marge pile, DMA) sur **ce SHA**. Sans retour PO, classement `ON_DEVICE_UNVERIFIED`. Le Développeur remet au Pilotage ; seul Pilotage accepte et fusionne. #194 et #200 restent hors périmètre.
