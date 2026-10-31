# J1-DIAG-RETRO-A0 — inventaire des diagnostics du BASIC natif

**Mandat :** [issue #195, décision du 31/10/2026](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/195#issuecomment-6542572782). **Base contrôlée :** `main@ccdb4837278b8d8d56a19a858cd07d36dc40ec2a` (plus récent que `d9c42b5...` cité dans le mandat). **Périmètre A0 :** seulement nouveaux fichiers de preuves, inventaire et test ; aucun correctif dans `core/`, `io/`, `firmware/`, `video/` ou les oracles archivés. Ce rapport ne constitue pas une acceptation technique Pilotage.

## 1. Résultat concret — texte CPC retrouvé dans les écrans archivés

Les **captures RUN PNG de la ROM CPC6128 BASIC 1.1** ont été **relues visuellement** depuis les archives GitHub authentiques, et non reconstruits à partir de `basic.asm`, de `BEStatus` ou des sorties imprimante. Pour GOSUB/RETURN et NEXT, les captures original/repeat sont identiques octet pour octet ; pour J1.5-A, chaque cas comporte **une seule capture RUN** et une sonde imprimante ERR/B% (sans sonde ERL imprimante). Les sources/horodatages/ROM/Caprice32 sont décrits et ancrés dans les manifestes historiques inchangés. Les sept transcriptions exactes ci-dessous sont **nouvellement référencées** par SHA-256 PNG dans `tests/diag_retro_a0_matrix.json` et `tools/j1_diag_retro_a0_verify.py`.

| Archive/cas | ERR CPC mesuré | Ligne CPC | Texte sur l'écran ROM | Après erreur | Répétition |
|---|---:|---:|---|---|---|
| J1.11 `F_MISSING_TARGET` | 8 | 10 | `Line does not exist in 10` | `Ready` sur la ligne suivante | 2 PNG identiques |
| J1.11 `F_UNPAIRED_RETURN` | 3 | 10 | `Unexpected RETURN in 10` | `Ready` suivant | 2 PNG identiques |
| J1.11 `F_UNPAIRED_AFTER_CALL` | 3 | 20 | `Unexpected RETURN in 20` | `Ready` suivant | 2 PNG identiques |
| J1.12 `F_NEXT_ORPHAN` | 1 | 20 | `Unexpected NEXT in 20` | `Ready` suivant | 2 PNG identiques |
| J1.12 `F_NEXT_WRONG_VAR` | 1 | 30 | `Unexpected NEXT in 30` | `Ready` suivant | 2 PNG identiques |
| J1.5 `P1_ID0` | 11 | 20 (visible) | `Division by zero in 20` | `Ready` suivant | capture unique |
| J1.5 `P0_ID0` | 11 | 20 (visible) | `Division by zero in 20` | `Ready` suivant | capture unique |

Pour les cinq premiers, ERR/ERL **numériques** sont indépendamment attestés dans les traces de `PRINT #8,ERR` et `PRINT #8,ERL`. Pour les deux divisions, seul **ERR=11** provient de la sonde imprimante et **`in 20`** provient de l'écran ; ne pas présenter ERL comme une sonde historique supplémentaire. Les screenshots ont le curseur visuellement à la ligne après `Ready` ; aucune position XY pixel exacte ni chronologie d'animation du curseur n'a été extraite. La présence d'un `Ready` au démarrage est indépendante de celui qui suit l'erreur.

**Précision d'écran / sortie :** dans `F_UNPAIRED_AFTER_CALL`, `PRINT #8,101` a lieu dans la sous-routine, puis erreur à la ligne 20 ; dans `F_NEXT_ORPHAN`, `PRINT #8,77` précède l'échec. Ce sont des **octets imprimante CPC**, non des caractères peints sur l'écran et non une garantie pour l'imprimante non raccordée du CYD. La destination manquante empêche le `PRINT #8,21` qui suit. Les images seules ne prouvent pas l'atomicité de la RAM ; ne pas inventer une preuve de non-mutation CPC.

**Références en lecture seule :** `docs/J1.11-A-gosub-return-cpc-oracle.md`, `docs/J1.12-A-for-next-integer-cpc-oracle.md`, `docs/J1.5-A-integer-division-oracle.md`, avec leurs `tests/fixtures/cpc6128/j1_11_gosub_return/`, `j1_12_for_next/`, `j1_integer_division/`. Le corpus PNG et les SHA du manifeste ne sont jamais recréés ou remplacés par le vérificateur. L'assemblage `basic.asm` joint au projet est un **indice ROM statique**, et non une nouvelle acquisition indépendante.

## 2. Inventaire d'erreurs — moteur actuellement exécutable

La **matrice structurée** `tests/diag_retro_a0_matrix.json` couvre les **26 statuts d'erreur déclarés** dans `BEStatus` (hors `BE_OK/BE_END`) et **18 chemins supplémentaires**, avec formes positives et négatives, cause hôte/CPC/unsupported, numéro et texte **seulement quand attestés**, traitement actuel CONSOLE, priorité et lacunes. Son compte est **une couverture des catégories et branches examinées**, **pas 26 cas exécutés sur CYD**. La source d'autorité est le code, notamment `core/basic_executor.c` (exécuteur), `core/basic_tokenizer.c` (lexique), `core/basic_session_runtime.c` (état RUN), `io/cpc_diag_policy.c` (mapping), `firmware/esp32_display_probe/main/hw4_c2_console.c` (rendu).

| Famille/forme | Statuts natifs ou hôtes importants | Observation en console au HEAD audité | Niveau CPC / priorité |
|---|---|---|---|
| `GOTO`, `GOSUB`, `IF ... THEN` destination absente | **même** `BE_MISSING_TARGET` | `ERROR\n` puis transition `Ready` au RUN | texte attesté **GOSUB seulement** ; A1 doit conserver l'instruction d'origine |
| `RETURN` isolé | `BE_RETURN_WITHOUT_GOSUB` | `ERROR\n` puis `Ready` | `Unexpected RETURN in 10/20` attesté ; A1 |
| `NEXT` isolé, mauvaise variable | `BE_NEXT_WITHOUT_FOR`, `BE_NEXT_VARIABLE_MISMATCH` | `ERROR\n` puis `Ready` | `Unexpected NEXT in 20/30` attesté ; A1, réserve de localisation |
| `FOR`, profondeur/STEP zéro/paire introuvable | `BE_FOR_STACK_FULL`, `BE_UNSUPPORTED`, `BE_FOR_WITHOUT_NEXT` | `ERROR\n` puis `Ready` si rencontré | CPC non caractérisé, ou limite hôte ; **pas** de conversion implicite |
| Arithmétique INTEGER `+,-,*,\\,MOD` en affectation | `BE_INTEGER_OVERFLOW`, `BE_DIVISION_BY_ZERO` | `ERROR\n` puis `Ready` | `\\0` F9 attesté, MOD0 **non caractérisé textuellement** ; A2 |
| `PEN 16/-1` | `BE_INVALID_PEN` dans `pen_argument()` | déjà `Improper argument in <ligne>\n` | **corrigé par #203** ; ne pas refaire |
| `PEN 0..15` et `INK` | `BE_UNSUPPORTED`, `BE_INVALID_INK`, événement `BE_VIDEO_SET_INK` | validation native puis possible refus **host renderer** `SET_INK_UNSUPPORTED` | ERR5 bornes INK scellé mais texte non relu ici ; A2 |
| `PRINT` chaîne/INTEGER/REAL borné, `LET`, références scalaires, IF inline, commentaires | `BE_BAD_SEQUENCE`, `BE_VARIABLE_NOT_FOUND`, `BE_INVALID_TYPE`, `BE_TRUNCATED`, `BE_UNKNOWN_TOKEN` | `ERROR\n` si échec ; ne pas assimiler au CPC | **DIAG_CPC_UNVERIFIED** pour ces chemins |
| `CLS` stocké (token `8A`) / `ABS` LIST seulement | `BE_UNKNOWN_TOKEN` ou construction non exécutable | `ERROR\n` lors de RUN ; `LIST` possible | `UNSUPPORTED_NATIVE` ; **ni faux Syntax error ni faux CPC** |
| Mémoire, alias, sortie, événements, profondeur 8 | `BE_NO_SPACE`, `BE_STORE_FULL`, `BE_OVERLAP`, `BE_CALL_STACK_FULL`, `BE_FOR_STACK_FULL`, `BE_NO_EVENT_SPACE`, `BE_EVENT_RECEIVER_REQUIRED` | `ERROR\n` au point d'échec | **HOST_INFRA/HOST_LIMIT**, aucune équivalence ROM |
| Entrée `RUN+`, suppression numérotée absente, `!CLS`, `!SHOT`, boucle `GOTO 10` | `BSR_SESSION_ERROR`, `CPC_DIAG_LINE_DOES_NOT_EXIST`, catégorie HOST, budget 256 | diagnostic générique ou cas historique déjà mappé | suppression #159 et PEN #203 conservés ; budget #200 / capture #220 exclus |

Les formes *tokenisées et listables* ne sont pas toutes *exécutables*. La matrice classe séparément `CLS` (B1 lexical accepté), `ABS` (LIST uniquement), `MODE/PAPER` (non implémentées en instructions natives malgré les API vidéo) et les commandes du terminal préfixées `!`. Tout cas sans capture textuelle CPC est marqué `DIAG_CPC_UNVERIFIED` ou host, jamais inféré du mot « Overflow » du statut interne. Les chemins pré-RUN de `BSStatus/BTStatus/BPStatus/BLStatus` sont un second niveau **hôte**, non une liste de codes CPC.

### Point bloquant avant A1 : lieu réel de l'échec `NEXT`

Dans `core/basic_executor.c`, **`FOR` appelle `for_match()` avant l'exécution du corps** ; cette recherche peut renvoyer `BE_NEXT_VARIABLE_MISMATCH` dès la **ligne FOR 10**, alors que le CPC original a affiché **`Unexpected NEXT in 30`** pour la source scellée. L'actuel `runtime.executor.cursor` suffit à récupérer la ligne **courante**, mais pas nécessairement la ligne **fautive CPC**. Transformer simplement `BE_NEXT_VARIABLE_MISMATCH` en `Unexpected NEXT in <cursor>` afficherait faussement `in 10`. Le contrat de contexte A1 devra conserver un **locus fautif prouvé**, par exemple la ligne NEXT détectée lors du scan, ou une stratégie de détection dont la sémantique et l'atomicité sont revérifiées. A0 ne modifie pas `core/` ; toute adaptation d'interface demande la décision du Pilotage dans le mandat A1.

## 3. Contrat minimal proposé (documentaire, non implémenté)

```text
CpcNativeFailure {
    origin: NATIVE_EXECUTOR | HOST_INPUT | HOST_INFRA | HOST_RENDERER
    bsr_status: BSRStatus                 // statut hôte inchangé
    be_status: BEStatus                   // statut hôte inchangé
    instruction: TOKEN_REACHED + FORM     // depuis le record et la position réels
    current_line: uint16 | ABSENT         // curseur pré-bsr_stop
    fault_line: uint16 | ABSENT           // emplacement de faute, PAS supposé égal
    screen_oracle_case: CASE_ID | NONE    // preuve indépendante contrôlée
}
```

Un **adaptateur central** peut sélectionner et formater un diagnostic CPC **si et seulement si** le triplet `instruction + cause + locus` correspond à un cas screen-oraclé (avec traitement explicite de la ligne dynamique). Sinon retour de la catégorie hôte **sans ERR/ERL artificiel**. Ne pas coder `10`, `20` ou `30` comme lignes génériques. Ne pas exposer `ERR/ERL` en pseudo-registres BASIC ; ne pas déduire le code CPC de la valeur numérique de `BEStatus`. Dans le propriétaire CONSOLE, la prise de contexte doit se faire **avant `bsr_stop()`** ; le formatage ne doit pas engager de nouveaux effets d'exécution. Respecter le préflight `PRINT`/événements et le contrat d'atomicité ; `Ready` reste piloté par `cpc_ready_policy`, une seule fois par transition, jamais intégré dans la chaîne du diagnostic.

**Barrière de promotion :** les textes ci-dessus autorisent des **tests RED** distincts pour `GOSUB`, `RETURN`, `NEXT` et division par zéro. Ils ne permettent **pas** de mapper aveuglément `BE_MISSING_TARGET`, `BE_INTEGER_OVERFLOW`, `BE_INVALID_INK`, `BE_UNSUPPORTED` ou des refus renderer. En particulier, le numéro `10` d'un test ne vaut pas preuve d'une ligne variable au RUN, à revalider en A1.

## 4. Garde et mode de relecture

Dans un checkout complet :

```sh
python3 tools/j1_diag_retro_a0_verify.py
python3 tools/j1_diag_retro_a0_verify.py --self-test
```

Le test **échoue fermé** si l'inventaire des `BEStatus` dérive, si un témoin est ajouté sans ancrage indépendant, si le texte ou le code d'une transcription change, si le hash SHA-256 d'un PNG archivé diffère, si les nombres de l'ancienne sonde ont été modifiés, si la paire original/repeat diffère, ou si l'avertissement de localisation `NEXT` disparaît. **Cinq mutations négatives en mémoire**, sans toucher aux archives canoniques. Le test ne lit **aucun pixel par OCR** ; l'association « message retranscrit ↔ image » exige toujours une revue humaine des PNG. Les suites standards et le passage du nouveau script doivent être cités **au HEAD de la PR**, non hérités d'un commit ancien.

L'intégration dans le graphe CTest/workflows **n'a pas été modifiée**, pour éviter les travaux en cours #220 (CONSOLE/CMake) et #223 (scheduler). Aucune acquisition Caprice32 neuve, build Xtensa ou test CYD **n'est revendiqué par la création de cette documentation** ; les lectures d'archives ne remplacent pas un test de code futur.

## 5. Découpage maintenu et réserves

A0 ne livre **aucun correctif d'affichage**. A1 reste sous décision Pilotage avec priorité GOSUB/RETURN/NEXT après coordination avec la fusion #220. A2+ couvrira en lots resserrés division par zéro, overflow et arguments INK après preuve et causalité. Le correctif PEN #203 est conservé ; les travaux #200 et #223 sur le BREAK/yield et #220 sur capture UART sont indépendants. La #195 demeure ouverte jusqu'à extinction vérifiée de la dette, sans décision de fermeture par le développeur.
