# CI-OPT1 — Orchestration par domaine et vérification de parité

**Mandat :** [#113](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/113), autorisé par Pilotage, 28/10/2026.  
**Branche :** `ci/opt1-domain-workflows` — [PR #116](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/116) (en revue, non fusionnée).  
**Base vérifiée :** `main` = `a7f49329d581aa26522ace888f1374ba1e6d8307`.  
**Chantier parallèle :** PR #115 HW4-C3-B2, sans modification de sa branche ni de ses sources.  
**Périmètre :** uniquement GitHub Actions, labels et rapport ; aucun changement du langage, HAL, vidéo, archives CPC, ROM ou des moteurs d'oracle.

## 1. Baseline GitHub mesurée avant CI-OPT1

PR [#107](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/107), HEAD `166454e249cf98f7b7dd0170e6f6212de0dd1105`, exécutions du 28/10/2026 vers 00:58 UTC :

- **28 jobs exécutés**, avec 11 workflows SUCCESS ; trois workflows d'acquisition SKIPPED, état normal.
- **25,53 minutes-jobs** : somme des `completed_at - started_at` des 28 jobs, extraite de l'API GitHub `/actions/runs/{run_id}/jobs` ; pas une facture de runner arrondie.
- **7,07 minutes** de latence approximative jusqu'à la fin du dernier workflow (`00:58:43Z` → `01:05:47Z`). Les jobs étaient parallèles.
- Les cinq jobs Xtensa redondants totalisaient déjà environ **16,57 minutes-jobs** : J1.8-A (4,12), J1.9-A (3,77), HW4-C1 (3,18), HW4-C2 (3,13), J0.25 (2,37). Même triple jeu de profils reconstruit plusieurs fois.

Références API vérifiables : exécutions `40612187487`, `40612187453`, `40612187614`, `40612187495`, `40612187456`, `40612187458`, `40612187492`, `40612187493`, `40612187510`, `40612187476`, `40612187490`. Le nombre de workflows est celui réellement déclenché pour CE HEAD, pas toutes les 20 définitions disponibles dans le dépôt.

## 2. Matrice exhaustive ancien → nouveau

| Workflow ancien | Destin | Contrôle maintenu |
|---|---|---|
| `basic-program.yml` | Conservé, renommé CI-C99 | Quatre configurations GCC/Clang × ASan/UBSan OFF/ON ; tous les CTest, audit mémoire, J0.26/28 et J1.1 ; J1.2-B et baseline HW4-C3-B1 |
| `j1-2-b-integer16.yml` | Retiré | CTest `integer16_literals` et différentiel CPC J1.2-B dans CI-C99 + seal dans CI-CPC |
| `esp32-xtensa-j025.yml` | Retiré | Probe autonome dans CI-XTENSA ; rapport ABI et partition |
| `hw3-display.yml` | Retiré | Affichage `HW4_C2_CONSOLE=OFF` dans CI-XTENSA |
| `hw4-b-shared-driver.yml` | Retiré | Propriétaire SPI/LCD dans CI-ARCH ; Linux dans CI-C99 ; deux projets dans CI-XTENSA |
| `hw4-c1-integrated.yml` | Retiré | CTest intégration TFT dans CI-C99 ; frontière core/HW4 CI-ARCH ; Xtensa CI-XTENSA |
| `hw4-c2-interactive.yml` | Retiré | UART/ANSI/heap/entry point CI-ARCH ; CTest et seuil min 62 CI-C99 ; 3 profils CI-XTENSA |
| `hw4-c3-b1-scroll.yml` | Acquisition CPC conservée | Test autonome C99 OFF/ON déplacé dans les deux cellules GCC CI-C99, acquisition ROM non modifiée |
| `j1-6-a-mod.yml` | Acquisition CPC conservée | Vérification permanente FB et mutations dans CI-CPC |
| `j1-7-a-add-vars.yml` | Acquisition CPC conservée | Vérification permanente F4 et mutations dans CI-CPC |
| `j1-8-a-sub-vars.yml` | Acquisition CPC conservée | Scellement dans CI-CPC, architecture CI-ARCH, builds CI-XTENSA |
| `j1-9-a-binary-family.yml` | Acquisition CPC conservée | Scellement dans CI-CPC, architecture CI-ARCH, builds CI-XTENSA |
| `j1-10-a-if-then.yml` | Acquisition J1.10 seule conservée | Archives et faux HEAD via CI-CPC/CI-ARCH ; retrait du doublon J1.11-A |
| `j1-11-a-gosub-return.yml` | Acquisition J1.11 seule conservée | Archives/falsifications via CI-CPC, isolation via CI-ARCH ; correction YAML dupliqué qui empêchait le workflow de se charger |
| `j1-2-a-boundaries.yml` | Acquisition originale conservée | Captures ROM/Caprice32 et privilèges d'acquisition inchangés |
| `j1-3-a-subtraction.yml` | Acquisition originale conservée | Captures ROM/Caprice32 inchangées |
| `j1-4-a-multiplication.yml` | Acquisition originale conservée | Captures ROM/Caprice32 inchangées |
| `j1-5-a-division.yml` | Acquisition originale conservée | Captures ROM/Caprice32 inchangées |
| `cpc-oracle-image.yml` | Conservé intégralement | GHCR pinned, permissions propres, publication uniquement sur main |
| `cpc-oracle.yml` | Conservé intégralement | Oracle Caprice32 historique indépendant et acquisitions C6/C7/C8/J0.27/J1.1 |

## 3. Contrats permanents, sécurité, déclenchements

- **CI-C99** s'exécute sur tout `pull_request` et `push: main` (sans filtre de chemins) ; compile quatre fois une fois par configuration ; lance `ctest --output-on-failure` sans `-L` ni restriction, exige `>=62` tests au niveau de la baseline de main J1.11-A ; Clang garde les deux exceptions warning déjà documentées. Les labels dynamiques sont définis dans `cmake/CTestLabels.cmake` et posés **en fin de configuration** via `cmake_language(DEFER)` avec CMake >=3.19. Les CMake 3.13–3.18 exécutent tous les tests mais ne fournissent pas les labels optionnels.
- **CI-CPC-PERMANENT** (tout PR et `push: main`) vérifie les manifestes, empreintes, provenance, impressions, faux archives, faux HEAD, captures J0 et J1.2 à J1.11, via `--permanent --self-test`. Il ne lance pas Caprice32 et ne possède pas de droits d'écriture ; toute erreur Python arrête le job (`set -euo pipefail`). Les comparaisons natives utilisant CLI restent dans les CTest des quatre cellules.
- **CI-XTENSA** (tout PR et `push: main`) vérifie le vrai commit de tête PR (ou SHA du push), l'image officielle `espressif/idf:v5.5.6`, les deux projets : `esp32_probe` ; `esp32_display_probe` console ON et historique HW3 OFF. Trois builds, deux répertoires distincts pour ON/OFF ; contrôle `app_main` unique, ELF/BIN, rapports d'occupation, sections Xtensa, ABI et partition.
- **CI-ARCH** (tout PR et `push: main`) vérifie le propriétaire unique du transport LCD, UART/ANSI, absence d'allocations dynamiques dans les chemins concernés, `app_main`, domaine core/HW4. Les archives CPC **existantes** ne peuvent être modifiées ni prolongées ; une acquisition de dossier **nouveau** peut ajouter des fixtures sous son nouveau préfixe, sans modifier les répertoires historiques.
- **Acquisitions GHCR originales** : les déclenchements, conditions de branches, empreintes ROM, droits `contents:write` strictement au niveau de chaque job et vérifications `REMOTE_HEAD` restent isolés. Les groupes de `concurrency` sont désormais spécifiques au workflow, dépôt, PR/réf et SHA ; `cancel-in-progress: false` pour les acquisitions. Les seules annulations autorisées concernent les gates de validation de PR obsolètes, jamais les push main ni les acquisitions.
- Les workflows de validation n'ont **aucun filtre `paths`**, notamment pour les éditions YAML et documentation structurante. Les workflows d'acquisition conservent leurs filtres/conditions d'origine. Aucune archive, image ROM, donnée CPC source ni outil d'acquisition n'est réécrit.

## 4. Parité et mesures

**Phase de comparaison avant désactivation :** HEAD `1d071e94d79db51fa4136ea9adc7ad20cb5a83da` :
- CI-C99 : [4/4 SUCCESS](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40618372855), inventaire complet de 62 suites.
- CI-CPC-PERMANENT : [SUCCESS](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40618372872), falsifications `--self-test` et faux HEAD.
- CI-ARCH : [SUCCESS](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40618372822).
- CI-XTENSA : [build des 3 images et contrôles ABI réussis, JOB FAIL](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40618372772). Cause précise : refus de permission `tee` lors de l'écriture d'un rapport supplémentaire dans un dossier créé par Docker root ; correction du rapport déplacée vers la sortie du job et la preuve du SHA vers le checkout explicite. Cette phase ne constitue PAS une CI verte.
- J1.11-A : anomalie de YAML doublé préexistante restaurée, validité du workflow à confirmer via Actions.

**Mesure effective post-consolidation (GitHub API, HEAD 9718be1764c25f180445828665330d03515e9a75, 28 octobre 2026 02:07–02:11 UTC) :**

| Mesure | Baseline #107 | CI-OPT1 #116 | Différence |
|---|---:|---:|---:|
| Jobs réellement exécutés | 28 | **8** | **-71,4 %** |
| Minutes-jobs cumulées (`completed_at-started_at`) | 25,53 | **7,05** | **-72,4 %** |
| Latence jusqu'à la fin des runs (`run_started_at→updated_at`) | 7,07 min | **3,75 min** | **-47,0 %** |
| Builds C99 complets sur PR comparable | 12 | **4** | **-66,7 %** |
| Pipelines Xtensa complets redondants | 5 | **1** | **-80 %** |
| Images Xtensa distinctes demandées | 3 | **3/3 SUCCESS** | **couverture conservée** |
| Suites CTest distinctes (par configuration) | 62 | **62/62 dans chacune des 4 cellules** | **couverture conservée** |

Les **8/8 jobs** sont SUCCESS sur le HEAD mesuré :
- [CI-C99 — 4/4, 62 CTest par configuration + test standalone HW4-C3-B1](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40619094744) : 2,15 minutes-jobs.
- [CI-CPC-PERMANENT](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40619094739) : 0,32 minute-job. Les logs incluent MANIFEST_MISMATCH, FILE_DIGEST_CHANGED et fausses empreintes SHA/HEAD explicitement rejetées, notamment 10 falsifications et faux HEAD J1.11-A.
- [CI-ARCH](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40619094761) : 0,08 minute-job.
- [CI-XTENSA](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40619094710) : 3,67 minutes-jobs ; commit PR explicitement vérifié ; 3 variantes physiques compilées, ABI et partition PASS, rapports/ELF/BIN en artefact.
- [HW4-C3-B1 authentique CPC](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40619094764) : 0,83 minute-job ; cette acquisition était déclenchée par le changement de son YAML, sans réécriture de son corpus.

**Méthode de mesure :** somme des durées des jobs non SKIPPED sur les cinq runs ci-dessus ; borne temporelle des runs de `02:07:42Z` à `02:11:27Z`. Jobs en parallèle, minutes-jobs ≠ wall-time et ≠ facture arrondie de runner. Les workflows d'acquisition déclenchés mais SKIPPED ne sont pas comptés comme des contrôles exécutés. La comparaison avec #107 est informative, mais les chemins modifiés diffèrent (code et oracles auparavant, fichiers CI ici) : les quatre nouveaux gates **sans path filter** assurent leur exécution sur une future PR `core/` également, tandis que `cpc-oracle.yml` continuera à ajouter sa propre exécution lorsque ses paths spécifiques sont touchés. La réduction observée satisfait l'objectif d'au moins 35–40 % dans cet échantillon, sans prétendre prédire la consommation de toute PR.

**Barrière finale :** l'ajout de cette section de mesures constitue un commit documentaire ultérieur ; les quatre gates CI-OPT1 doivent **également** finir SUCCESS sur ce nouveau SHA avant remise finale. Ne jamais reprendre les réussites du SHA précédent comme résultats de HEAD final.


## 5. Intégration avec PR #115 et limites

La PR #115 ajoute `hw4_c3_b2_mode1_scroll_dma_retry` à la fin du `CMakeLists.txt` ; les labels CI-OPT1 sont appliqués par un appel CMake différé et incluront ce test quand la PR #115 sera intégrée, sans toucher à sa branche. Son workflow `hw4-c3-b2-scroll.yml` doit faire l'objet d'une revue de redondance lors de son intégration ultérieure ; CI-OPT1 **ne le modifie pas**.

La vérification des branch protections GitHub requiert un privilège d'administration non accessible à la connexion actuelle (`403`) ; le endpoint des repository rulesets renvoie `[]`. Pilotage doit vérifier les éventuels required-checks historiques après suppression des anciens noms, avant décision de fusion. Ceci est une réserve explicite, pas une preuve d'absence de protection.

Aucun essai CYD physique, conformément à la nature exclusivement CI de la mission. `ON_DEVICE_UNVERIFIED` demeure.

## 6. CI-OPT1-C1 — Correction du choix de base diff (mandat Pilotage)

**Cause indépendante trouvée par Pilotage** : les deux steps CI-ARCH prenaient `git merge-base origin/main HEAD` ; après un `push: main`, `origin/main == HEAD` et les deux diffs étaient vides. Le succès historique de CI-ARCH ne prouvait donc pas le rejet d'une modification interdite lors de cet événement. Verdict précédent : **CORRECTIONS_REQUISES**, ne pas présenter l'ancien 8/8 comme une acceptation.

**Correction** : `tools/ci/ci_arch_base.sh` calcule une base unique vérifiée, exposée par `steps.diff_base.outputs.base` et consommée par `tools/ci/ci_arch_changes.sh` et le contrôle statique du propriétaire LCD. Checkout explicite du SHA de tête PR ou du SHA du push avec historique complet. Aucun cas ne retombe silencieusement sur `base=HEAD` :
- `push: main` : utiliser **`github.event.before`**, vérifier 40 caractères hexadécimaux, objet commit local présent, stricte antériorité et ancêtre du HEAD ; fail-closed si nul, manquant, différent de la branche attendue, inaccessible, ou après force-push non fast-forward ;
- `pull_request` : comparer le HEAD réel de la PR au `git merge-base refs/remotes/origin/main HEAD`, en exigeant une base `main` accessible et distincte du HEAD ;
- `workflow_dispatch` : sur `main`, contrôler le premier parent `HEAD^1` ; sur une autre branche, utiliser le merge-base avec `origin/main`. Refuser un ref inattendu, un premier commit sans parent, un branchement sans merge-base, un diff nul ;
- dans tous les cas, valider le SHA du checkout, l'existence locale de la base, sa relation d'ascendance et la non-égalité avec HEAD.

**Preuve contradictoire exécutable** : `bash tools/ci/test_ci_arch.sh` crée des dépôts Git temporaires distincts, avec un bare remote local, les modifie et appelle **les mêmes scripts de sélection et de politique que CI-ARCH**. Il reproduit explicitement `origin/main == HEAD` après un push, contrôle `base == before`, puis exige des exit codes non nuls et diagnostics stables sur les modifications interdites. Cas positifs : documentation seule, nouveau dossier de capture CPC, PR documentation, dispatch sur branche avec modification core seule. Cas négatifs : ancien binaire CPC modifié, nouvel élément dans archive historique, ancien oracle modifié, code core ET HW4 modifiés, base before absente, nulle, non locale, égale à HEAD, non ancêtre, mismatch HEAD, PR mauvaise base, dispatch main corrompu, dispatch tag/non-main invalide, dispatch sans premier parent, branche sans modifications.

**Preuve initiale sur HEAD `1618a626ce16ef2945d48f9d5179f85c5e3e3882`** : [CI-ARCH #40622324920](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40622324920) SUCCESS, logs `CI_ARCH_C1_SELF_TEST_PASS cases=17`, `PUSH_BEFORE_*` rejetés, `EXISTING_CPC_PROOF_CHANGED`, `CORE_AND_HW4_CHANGED_TOGETHER`, `CI_ARCH_BASE_VERIFIED event=pull_request`. Tests élargis dans le dernier commit, résultats du HEAD final à lire sur GitHub avant remise.

Le but de C1 est de restaurer la sûreté des comparaisons, pas de changer les chiffres de référence ni les corpus CPC. Les économies mesurées avant C1 restent informatives ; les nouvelles durées du HEAD final doivent être publiées séparément. Le déclenchement des acquisitions originales reste isolé et leurs runs SKIPPED ne comptent pas comme SUCCESS.
