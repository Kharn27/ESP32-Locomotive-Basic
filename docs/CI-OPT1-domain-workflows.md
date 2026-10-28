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

**Mesure finale post-consolidation :** à compléter par le verdict effectif des Actions pour le HEAD final de la PR. Ne pas confondre l'économie projetée (7 jobs de domaine, plus éventuel oracle isolé) avec la baisse mesurée réelle. Avant d'affirmer un gain de 35–40 %, consulter les dates `started_at`/`completed_at` et les runs GitHub du même commit ; comparer au HEAD #107 en distinguant les déclenchements différents (CI-OPT1 YAML-only versus PR C99 qui touche `core/`).

## 5. Intégration avec PR #115 et limites

La PR #115 ajoute `hw4_c3_b2_mode1_scroll_dma_retry` à la fin du `CMakeLists.txt` ; les labels CI-OPT1 sont appliqués par un appel CMake différé et incluront ce test quand la PR #115 sera intégrée, sans toucher à sa branche. Son workflow `hw4-c3-b2-scroll.yml` doit faire l'objet d'une revue de redondance lors de son intégration ultérieure ; CI-OPT1 **ne le modifie pas**.

La vérification des branch protections GitHub requiert un privilège d'administration non accessible à la connexion actuelle (`403`) ; le endpoint des repository rulesets renvoie `[]`. Pilotage doit vérifier les éventuels required-checks historiques après suppression des anciens noms, avant décision de fusion. Ceci est une réserve explicite, pas une preuve d'absence de protection.

Aucun essai CYD physique, conformément à la nature exclusivement CI de la mission. `ON_DEVICE_UNVERIFIED` demeure.
