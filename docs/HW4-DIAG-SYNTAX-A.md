# HW4-DIAG-SYNTAX-A-C1 — Diagnostic des mots directs inconnus, via CORE

- Mandats : [#288](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/288), [#292](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/292), [ordre C1](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/291#issuecomment-6604453315).
- PR reprise : [#291](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/291), branche `fix/hw4-diag-syntax-unknown-command`.
- Synchronisation de base : `main@9f19e500a9a46f1e16121ebc5c678202d7e52d82` (fusion CORE #294 puis J1.24-B1 #293), commit de merge de branche `5604752452978362449a8bc58c790327ee53a34f`. La PR reste une **PR IO/test/docs autonome** ; les changements CORE sont hérités de `main`.
- Barrière : aucune modification des sources `core/`, `integration/`, `firmware/`, `video/`, `CMakeLists.txt`, CI ou captures CPC scellées. Aucun test physique CYD demandé.

## Causalité et frontière de confiance

Le CORE fusionné dans `main` livre `BS_UNKNOWN_DIRECT=11`, un statut **hôte lexical typé** émis par `bs_process_line` pour un mot direct isolé, composé exclusivement de lettres ASCII (au moins deux) et absent du lexique positif de la ROM CPC 1.1. La classification et ses limites sont documentées dans `docs/HW4-DIAG-SYNTAX-CORE-A.md` ; **elle ne signifie pas à elle seule que CPC aurait rendu ERR=2**. `BS_UNSUPPORTED_DIRECT` continue de regrouper les commandes connues non exécutables et les formes ambiguës : **ne jamais l'assimiler à une faute de syntaxe CPC**.

Dans `io/cpc_diag_policy_select(source,length,r)`, la catégorie
`CPC_DIAG_DIRECT_UNKNOWN_SYNTAX` est choisie **uniquement** si :

- `source != NULL` et `length != 0` ;
- `r.status == BSR_SESSION_ERROR` ;
- `r.session.status == BS_UNKNOWN_DIRECT` ;
- les trois détails sont cohérents : `BT_OK`, `BP_OK`, `BL_OK`.

Il n'existe **plus aucun test littéral de `LISTT` dans la politique IO** ni reconnaissance indépendante de mots clés dans IO. Les situations non qualifiées restent `CPC_DIAG_HOST_GENERIC` / `ERROR\n`. Les absences d'une ligne numérotée valides conservent `Line does not exist\n`.

La catégorie et le domaine d'origine ont été renommés `CPC_DIAG_DIRECT_UNKNOWN_SYNTAX` / `CPC_DIRECT_DIAG_ORIGIN_CORE_UNKNOWN_LEXICAL`. Il s'agit d'une provenance **CORE**, pas d'un témoin CPC. Le domaine de provenance des diagnostics d'exécution `CpcDiagOrigin` reste inchangé : les switches exhaustifs des consumers RUN demeurent compatibles. La catégorie est ajoutée à la fin des anciennes catégories, sans renuméroter les valeurs précédentes. Le formateur `cpc_diag_policy_format_direct` écrit exactement `Syntax error\n` pour cette catégorie, ou `ERROR\n` pour le diagnostic hôte, sans allocation et sans effet sur le buffer ni `written` en cas de refus de formatage.

Le firmware CONSOLE utilise déjà `bsr_submit → cpc_diag_policy_select → cpc_diag_policy_write → CPC_READY_BASIC_DIAGNOSTIC → prompt` : il n'a pas été modifié. Le texte `Ready` provient toujours uniquement de la politique Ready existante, sans `Ready` intégré au message d'erreur. Les erreurs de transport, les rejets des ressources, les rejets du renderer et les erreurs d'exécution ne reçoivent aucune origine CPC inventée.

## Matrice de tests de production

`tests/test_hw4_diag_a.c` traverse le vrai chemin UART simulé / BSR / writer / Ready et vérifie la peinture octet par octet des glyphes, la stabilité du programme **sur sa capacité complète**, l'absence de modification de `basic.output`, `written` et du contexte `BasicSessionRuntime` sur chaque rejet, ainsi que les canaris de VRAM. Les tests incluent :

| Type | Saisies | Texte attendu |
|---|---|---|
| inconnues lexicales | `LISTT`, `LiStT`, `RUNN`, `rUnN`, `PRONT`, `CLSS`, `WHILLE`, `LISTTT` | `Syntax error\n` + `Ready` |
| mots CPC connus non exécutables | `GOTO 999`, `MODE 1`, `PAPER 2`, `AUTO`, `CONT`, `GRAPHICS`, `READ`, `WHILE`, `ON` | `ERROR\n` + `Ready` |
| formes ambiguës | `LISTT:RUN`, `LISTT 1`, `RUNN 5`, `LISTT=1`, `GOTO999`, `A$`, `A`, `GO TO 10`, `LISTT?`, `RUN 10` | `ERROR\n` + `Ready` |
| transport UART en amont | tabulation `\t` ignorée sans insertion ; CSI incomplet `ESC [` puis CR refusé par UART | aucun diagnostic BASIC, aucune émission Ready par la politique |\n| refus de contexte synthétiques | `BSR_BUSY`, `BSR_OVERLAP`, `BSR_EXECUTOR_ERROR`, `BS_UNSUPPORTED_DIRECT`, `BS_TOKENIZER_ERROR`, BT/BP/BL non OK, source nulle ou vide | `HOST_GENERIC` |
| historique | `10` absent, `NEW`, `LIST`, `RUN`, `GOTO 999`, chaîne `BONJOUR`, scroll | comportement antérieur |

Le programme `10 PRINT 2` est stocké avant les essais et son `LIST` final doit reproduire exactement `10 PRINT 2\n`. Le formatage direct est testé avec capacité insuffisante, sortie gardée par canaris et compteur inchangé.

## Provenance CPC, preuve et limites

La ROM `basic.asm` fournie par le PO indique `cb49: ld a,$02` (erreur syntaxique) et la table de messages à `cd98` (« Syntax » + suffixe compressé « error »). **Cette lecture statique prouve la graphie d'une erreur ROM, pas la trajectoire réelle d'une saisie inconnue vers cette erreur sur CPC**. Aucune capture indépendante de `LISTT` / `RUNN` n'a été acquise au titre de C1 : statut **`CPC_ORACLE_NOT_ACQUIRED` pour la correspondance comportementale**. Ne jamais annoncer `CPC_ORACLE_VERIFIED` ou un code `ERR/ERL` comme prouvé. La correspondance `BS_UNKNOWN_DIRECT → Syntax error` est un mapping d'affichage hôte explicitement demandé par Pilotage.

**Preuves attendues pour le HEAD de livraison :** GCC/Clang OFF/ON, ASan/UBSan, CI-ARCH, CI-OPT3, CI-CPC-PERMANENT scellé, trois builds Xtensa ESP-IDF, mémoire comparée au `main@9f19e500` exact. Les éventuels jobs SKIPPED ne comptent pas comme preuves d'exécution. Les résultats effectifs sont consignés dans la REMISE DÉVELOPPEUR sur la PR.

**CYD physique : `ON_DEVICE_UNVERIFIED`. PR #291 Draft, non fusionnée ; revue et fusion exclusivement par le Pilotage.**
