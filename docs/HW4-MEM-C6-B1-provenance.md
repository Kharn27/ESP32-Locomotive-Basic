# HW4-MEM-C6-B1 — Provenance GitHub M/B/H/MB/C (prototype non-gate)

**Mandat :** [#345](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/345), GO repris sur `main@0c9326bbea46fcd593c122633f0fbbbdb020b2d3` après décision Pilotage. Projet `Kharn27/ESP32-Locomotive-Basic` **uniquement**, PR OPEN, base ref `main`. **Aucun build Xtensa, aucun ELF/BIN, aucune modification des budgets ou required checks.** Ce module n'est connecté à **aucun workflow**.

## Mode opératoire (read-only)

Sur **code de confiance** (branche contrôlée, et non exécution arbitraire de fichiers de PR non revue), Python 3 stdlib avec accès HTTPS sortant à `api.github.com` :

```sh
python3 -m unittest discover -s tests -p 'test_hw4_mem_c6_refs.py' -v
python3 -m py_compile tools/ci/hw4_mem_c6_refs.py tests/test_hw4_mem_c6_refs.py
python3 tools/ci/hw4_mem_c6_refs.py --pr 330 --output /tmp/c6-b1-330.json
python3 tools/ci/hw4_mem_c6_refs.py --pr 339 --output /tmp/c6-b1-339.json
```

`GH_TOKEN` ou `GITHUB_TOKEN` **facultatif** (jeton read-only) pour quota API ; aucune écriture, aucun redirect suivi. Éviter de publier jetons/en-têtes. **Pas de paramètre modifiable de dépôt ou de branche** : le dépôt et la ref `main` sont fixés par contrat ; aucune donnée métrique injectée. Le CLI capture les objets via **GET GitHub API**, valide deux fois indépendamment puis écrit JSON atomiquement (horodatages UTC, SHA complets, arbres, motifs machine-readable et résultats séparés). Les tests hôte injectent des réponses **synthétiques**, pas des observations GitHub.

Le CLI retourne **0** uniquement si la double capture de provenance est cohérente ; ce zéro **ne signifie jamais PASS mémoire**. Il retourne **2** si requête refusée/incomplète, mauvaise identité/ancêtre, parents/arbre falsifiés, dérive entre captures, réponse inconnue ou écriture du rapport impossible. Le JSON invalidé reste `snapshot_status=MEASUREMENT_INVALID`, `PR_INCREMENTAL_VERDICT=MEASUREMENT_INVALID`, `INTEGRATION_READINESS=MEASUREMENT_INVALID`, `INTEGRATION_MEMORY_VERDICT=UNVERIFIED`. Ne PAS utiliser ce code retour comme CI gate de mémoire. Une indisponibilité de **C seulement** laisse `preview.status=UNVERIFIED`, jamais READY ; une indisponibilité de M/B/H/graph invalide la capture.

## Contrat et décisions fail-closed

`M` : SHA `main` GitHub ; `B` : `PR.base.sha` **réel**, jamais remplacé par M ni merge-base ; `H` : `PR.head.sha` ; `MB` : vrai merge-base de M/H ; `MB_BH` : vrai merge-base de B/H pour vérifier la branche, avec objets Git commits/trees et graphes d'ancêtres. Le code refuse dépôt/base ref différents, PR non OPEN, SHA malformés, base non ancêtre du main, HEAD pas en avance, compare incohérent, tree/commit faux. `B != M` : **base stale observée**, distincte d'un graphe invalide.

`C` : objet Git brut à SHA égal à `PR.merge_commit_sha`, tree existant/vérifié, parents ordonnés **exactement `(M,H)`** pour `preview.status=VERIFIED` ; même alors, **aucune mesure**. Si C absent/refusé : `UNVERIFIED` avec motif. Si C a des parents `(M_ancien,H)` et que la réponse GitHub prouve `M_ancien` ancêtre strict de M : `preview.status=UNVERIFIED`, motif `PREVIEW_STALE_MAIN`, non une preuve de M/C. Parents inversés, parent inconnu, faux arbre, replay, preuve d'ascendance manquante/incohérente sont rejetés avec code 2. `mergeable=true` et `mergeable_state=unstable` sont une **information UI**, pas un verdict.

**Canaux indépendants, sans moteur mémoire en B1 :**

- `PR_INCREMENTAL_VERDICT=UNVERIFIED` pour la vraie paire B/H, faute des **4 builds comparables** SPI40/SPI20 ; `INTEGRATION_MEMORY_VERDICT=UNVERIFIED` pour M/C.
- `INTEGRATION_READINESS=BLOCKED_STALE_BASE` si B≠M (même si preview présente, stale ou absente) ; sinon `UNVERIFIED` faute de builds et de contrôles applicables. Jamais `READY_FOR_PILOTAGE_REVIEW` en B1.
- Champ séparé historique : `HISTORICAL_UNCHANGED_NOT_REEVALUATED` ; RENDER-A et C3 `HISTORICAL_FAILURE` sur témoins connus, A0 `HISTORICAL_DEBT` ; `ROOT_CAUSE_UNVERIFIED`, `ON_DEVICE_UNVERIFIED`. Ces libellés ne sont pas une réévaluation des gates.

La double capture conserve M, B, H, MB, arbres, C, parents, réf et état PR, et invalide toute dérive observée. Les réponses GitHub/API ne sont pas un moteur de métrique ; aucune inférence de PASS à partir de commits/mergeable/CI verte.

## Captures GitHub read-only (09 novembre 2026, témoin à réactualiser)

La capture faite par l'agent avec le connecteur GitHub (réponses **réelles**, distinctes des fixtures de tests) à **15:11:54 UTC** a constaté :

| Champ | PR #330 | PR #339 |
|---|---|---|
| M | `0c9326bbea46fcd593c122633f0fbbbdb020b2d3` | identique |
| B | `4d261f2a76374ab99a4dd7415cae7a097330c46b` | `ae07e039a08f6fff66f752228dc2ebed3fcf4220` |
| H | `64b0087d5087903fee175c4f149c65a65bb43fe6` | `1b16c32ee4968100fcc46d876e7cdf095ea43798` |
| MB(M,H) et MB(B,H) | `4d261f2a76374ab99a4dd7415cae7a097330c46b` | `ae07e039a08f6fff66f752228dc2ebed3fcf4220` |
| C (preview SHA non utilisable sur M actuel) | `28e0a1585b204c55e533c284328e9bc797b23492` | `d4f2c29216717b796b54bd3cb1b7433acdb1754c` |
| Parents C (Git brut) | `(e620c3b1a180a68b02dd251c13f1f99590f31635, H)` | idem `(e620… , H)` |
| Arbre C (Git brut et objet tree contrôlé) | `7e60916f6de47c789bb581464b65d8ee66f69f1b` | `d5458c2a94bdaea44c3392f14f82008fc7bc45d2` |
| `B != M`, `mergeable=true` | OUI ; **non ready** | OUI ; **non ready** |
| Résultat à ce stade | `PR_INCREMENTAL_VERDICT=UNVERIFIED`, `INTEGRATION_READINESS=BLOCKED_STALE_BASE`, `INTEGRATION_MEMORY_VERDICT=UNVERIFIED`, preview `PREVIEW_STALE_MAIN` | identique |

L'objet `e620…` est ancêtre direct du `main@0c9326…` (compare GitHub `ahead_by=1, behind_by=0`, MB=e620…). `M` tree : `7cf855492d2d232bb23e667d876a478ce7b610aa`. `B` trees : #330 `d74061cb975981aafb022409cf1e9682f934235d`, #339 `553f1800816e67f512f549df4beeb279c592dc2d`. `H` trees : #330 `ed23017e46a7f54c76447bdb77937de540588ea8`, #339 `5f60fececc842d3fa78d716305ae1a3a7b61945b`.

**Limite :** la capture du connecteur n'est pas le rapport JSON de l'exécutable CLI réseau dans cet environnement (le conteneur hôte ne résout pas `github.com`/`api.github.com`). Pour utiliser cette preuve comme programme, relancer le CLI sur un hôte avec accès API et conserver les deux relevés JSON horodatés. En B1 **aucun test mémoire n'a été fait** ; la compilation et la promotion de gates restent hors mandat. La comparaison du second relevé est indiquée dans la remise Pilotage, pas dans cette photographie datée.

## Limites et prochaine barrière

Cette PR Draft n'ajoute **aucun** job required, ne réécrit pas les scripts C5 et leurs `EXPECTED_BASE/C5_MAIN/policy_main` scellés, ne change ni `opt3_routing.py`, ni A0/RENDER-A/C3, ni firmware/CORE/HAL/VIDEO. Le Pilotage seul décide de la réception C6-B1 et d'un mandat **C6-B2** séparé (4 builds B/H et 4 builds M/C, vrais artefacts Xtensa et mémoire). En attendant : **non-fusionné, non-ready, ON_DEVICE_UNVERIFIED**.
