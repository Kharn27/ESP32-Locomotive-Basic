# HW4-MEM-C6-B2-A — CI GitHub live (hôte, preuve de provenance uniquement)

**Périmètre : Issue #348. NON-REQUIRED, NON-MEMORY-GATE, jamais un verdict Xtensa.**
Cette preuve lève *LIVE_CLI_UNVERIFIED* et *HOST_TESTS_CI_UNVERIFIED* uniquement
après l'obtention d'un run GitHub Actions réel avec jobs et artefacts vérifiés.
La réussite locale ne remplace pas ces éléments GitHub.

## Enracinement de confiance et coût

Workflow lab `.github/workflows/hw4-mem-c6-b2-a-live.yml`, uniquement
`pull_request.paths` borné (six chemins explicites) et `workflow_dispatch`
manuel. Permissions d'ensemble `contents: read`, `GITHUB_TOKEN` en lecture
seule, **pas de `pull_request_target` ni de secret externe**. Aucun push ni
publication dans le dépôt.

- `host-adversarial` : checkout du SHA **HEAD PR** correspondant à l'événement,
  `persist-credentials: false`, aucun token dans les étapes de tests, `py_compile`,
  `python3 -m unittest discover -s tests -p 'test_hw4_mem_c6_refs.py' -v`
  et `python3 -m unittest discover -s tests -p 'test_hw4_mem_c6_b2_a_live.py' -v`.
- `live-github-provenance` (dépend du succès du job hôte) : interroge l'API GET
  pour contrôler **main** et le HEAD/baseref du PR à l'origine de la CI ;
  vérifie que `main` est exactement le témoin mandaté
  `0d5315be79262bb0355f8141a351937272f548fd` ; checkout par ce SHA
  (`persist-credentials: false`) et contrôle `git rev-parse HEAD`. Exécute
  **seulement le module fusionné sur main**
  `tools/ci/hw4_mem_c6_refs.py`, jamais un script provenant de #330 ou #339,
  ni le module éventuellement changé dans la PR de cette CI.
- Les deux commandes `--pr 330 --output .../pr-330.json` et
  `--pr 339 --output .../pr-339.json` effectuent chacune **deux lectures live**,
  avec M/B/H/MB, arbres, parents et état C. Après les commandes, le workflow
  **revérifie live** `main`, les PR B/H/C et les objets bruts de C. Tout mouvement
  est une erreur, pas une mise à jour silencieuse des références.
- Le job écrit `source-provenance.json` (source Git SHA, arbre, SHA256 du Python
  réellement exécuté, run ID, attempt, SHA d'événement et HEAD PR),
  `SHA256SUMS.txt` ainsi que les deux JSON. `sha256sum --check` est obligatoire.
  Upload `actions/upload-artifact@v4` **uniquement après succès intégral** ;
  artefact absent, rejet API/rate-limit, preview refusé, sortie vide, perte de
  preuves ou main changé = **échec du job** et **pas de PASS**.

Consommation : deux jobs Linux `ubuntu-24.04`, uniquement Python stdlib et
GitHub API GET, **aucune campagne Xtensa** et aucun nouveau budget mémoire.
Le déclenchement normal d'autres CI déjà existantes (CI-XTENSA, par exemple)
ne constitue pas une mesure HW4-MEM-C6.

## Contrats sémantiques stricts

CLI B1 : `rc=0` vaut **PROVENANCE_VERIFIED seulement**, même avec
`PREVIEW_STALE_MAIN`. `rc=2` signifie échec fail-closed ; il empêche l'upload.
Le workflow vérifie au minimum :

- `snapshot_status=PROVENANCE_VERIFIED`, deux observations stables et datées ;
- `PR_INCREMENTAL_VERDICT=UNVERIFIED` et `INTEGRATION_MEMORY_VERDICT=UNVERIFIED` ;
- `INTEGRATION_READINESS=BLOCKED_STALE_BASE` si `B != M`, sinon `UNVERIFIED` ;
- `preview.reason=PREVIEW_STALE_MAIN` si le premier parent de C est un ancien
  main dont l'ascendance vers M est vérifiée. **Jamais une preuve d'intégration** ;
- un preview absent ou refusé ne crée **aucun candidat M/C** ; en B2-A, le
  workflow rejette ce manque de preuve au lieu de le présenter comme succès.

RENDER-A et C3 conservent `HISTORICAL_FAILURE`, A0 `HISTORICAL_DEBT` :
`HISTORICAL_UNCHANGED_NOT_REEVALUATED`, `ROOT_CAUSE_UNVERIFIED`,
`ON_DEVICE_UNVERIFIED`. Pas de `continue-on-error`, ni de `required` créé.

## Preuves attendues et authentification

Lien vers **run** (HEAD intégral / workflow / event / attempt), jobs hôte et
live terminés SUCCESS, logs détaillant le nombre de tests et les commandes,
ID d'artefact, 4 fichiers retrouvables et SHA256 vérifiables, sortie des deux
PR authentiques, deux canaux de mémoire `UNVERIFIED`. Le succès du run
indique seulement qu'un enregistrement GitHub API cohérent a été produit.

Pour retrouver les éléments : GitHub → PR Draft → Checks →
`HW4-MEM-C6-B2-A PROVENANCE_ONLY — NOT_MEMORY_GATE` → job live → Artifacts.
Vérifier localement l'archive :

```bash
sha256sum --check SHA256SUMS.txt
python3 -m json.tool pr-330.json >/dev/null
python3 -m json.tool pr-339.json >/dev/null
```

L'horodatage et les SHA présents dans les JSON sont ceux de la capture, pas une
assertion statique. L'identité du preview peut évoluer : **ne pas réutiliser
les SHA de l'étude C6-A comme valeurs courantes**. La CI échoue en cas de
drift pendant le run ; il faut une nouvelle exécution explicite.

## Candidat #330 actuel : uniquement une proposition pour B2-B

Si la PR #330 conserve son ancien `B`, son test-merge GitHub C initial peut
avoir des parents `(ancien-main, H)` et donc être marqué `PREVIEW_STALE_MAIN`.
Ne jamais présenter ce C comme `(M,H)`. Le futur mandat **B2-B**, après
autorisation séparée du Pilotage, pourrait construire un *test-merge local*
reproductible en partant des objets exacts `M` et `H`, avec deux parents
ordonnés et arbre contrôlé. Il serait identifié comme **candidat synthétique
reproductible, DISTINCT d'un preview GitHub** : son identité, son code exécuté,
sa reproductibilité et les mesures Xtensa devraient être prouvées séparément.
**B2-A ne crée pas ce commit et ne mesure pas la mémoire.**

## Routage fermé CI-OPT3

Inventaire **40 workflows / 5 familles**, nouvelle entrée dans `HW4`.
Les six chemins de la nouvelle CI sont exacts et sans wildcard : workflow,
routeur OPT3, module C6-B1, test C6-B1, test C6-B2-A, présente documentation.
Négatifs routage : ajout d'un workflow inconnu, suppression ou duplication
d'un chemin, extension à `docs/**`, événement `push`/`pull_request_target`,
jeton d'écriture, HEAD proposé falsifié, checkout source non trusted,
neutralisation des échecs, artefact manquant. Les contrats des 39 anciens
workflows, leurs filtres et budgets restent inchangés.

**Livraison en PR Draft `Refs #348` pour décision Pilotage.** Aucun changement
des protections/required checks, aucune fusion #330/#339, aucun test physique CYD.