# CI-OPT2 — Couloirs fonctionnels et budget de validation

**Statut :** proposition de revue Pilotage, PR CI dédiée (pas une modification de `main` tant que la PR n'est pas acceptée). **Base étudiée :** `main@2191363f0d8d78b7c7f34ed734b85b981c06baaf`.

## Audit contradictoire : référence PR #170

L'API Actions de GitHub présente **28 workflows** actifs. Sur la PR #170 (HEAD `c86f8b47f17ebc6242dc0c209d1692c04668002e`), les durées **murales par workflow** étaient d'environ :
- C99, 4 cellules / 98 CTests par cellule : 1,3 min (run 40914655484).
- CPC indépendant (Caprice32 GHCR épinglé) : 1,6 min (40914655688).
- CPC permanent scellé : 0,5 min (40914655680).
- CI-ARCH : 0,4 min (40914655510).
- HW4-C3-B2 : 0,4 min (40914655380).
- HW4-EDIT-P1 : 1,0 min (40914655485).
- Xtensa 3 profils : 2,6 min (40914655571).

Ces workflows sont concurrents : **leurs durées ne s'additionnent pas** pour obtenir le temps par PR. Les plafonds `timeout-minutes` ne sont pas des temps observés. Une boucle de commits et de captures de nouveaux oracles historiques peut néanmoins immobiliser plusieurs jobs coûteux successifs.

## Répartition fonctionnelle — propriétaire de chaque couverture

| Couloir | Propriétaire | Contrôle garanti |
|---|---|---|
| **C99 portable** | `basic-program.yml` | **Suite CTest complète** en GCC/Clang × sanitizers OFF/ON (4 cellules) ; tests natifs, capteurs de non-régression |
| **CPC indépendant** | `cpc-oracle.yml` | Comparateur C99 et acquisitions Caprice32 spécifiques, preuve source historique, comparaison CPC ; **pas** de seconde suite CTest complète |
| **CPC archive permanente** | `ci-cpc-permanent.yml` | Provenance SHA, archives historiques, fraude/falsifications, y compris ancre D-A. Ne jamais assimiler un SKIPPED à un succès |
| **HW4 ciblé** | `hw4-edit-p1.yml`, `hw4-c3-b2-scroll.yml` | Matrices HW4 spécifiques, video/UART/scroll/éditeur, tests négatifs et dry-run. Ne pas relancer 98 tests génériques par cellule |
| **ESP32/Xtensa** | `ci-xtensa.yml` | Trois profils, ABI, partitions, taille, `one app_main` ; seulement si fichiers cible/build affectés sur une PR ; reconstruction normale sur `main` |
| **Acquisition d'oracle dédiée** | `j1-*.yml`, `hw4-diag-a.yml`, etc. | Captures CPC fraîches uniquement pour une mission d'oracle, si workflow/fixtures/outils pertinents touchés ou lancement manuel |

**Lecture des statuts :** `success` seulement lorsqu'un job a effectivement tourné ; `skipped` et `not_triggered` sont des états distincts, jamais des preuves. Une modification seulement documentaire/oracle ne constitue pas une nouvelle compilation Xtensa : réutiliser la preuve `main` antérieure en expliquant la portée de l'absence de changement cible.

## Mesures CI-OPT2 livrées dans la PR

1. Dans **HW4-EDIT-P1**, conserver la matrice ciblée et retirer **les quatre exécutions supplémentaires de la suite CTest entière** ; la matrice complète reste dans CI-C99.
2. Dans **CPC indépendant**, ne relancer qu'un petit sous-ensemble de CTests de comparaison (`cpc_*`, `basic_program_*`) en plus des vérifications et acquisitions CPC réellement propres au workflow. La suite complète est déjà assurée par CI-C99.
3. Retirer `docs/ROADMAP_GATES.md` du filtre de déclenchement de l'oracle CPC indépendant : un simple changement de feuille de route n'est pas une modification de l'oracle. Les scripts, données et modifications `core/basic_executor.c` restent couverts.
4. **Xtensa** : limiter les exécutions PR aux chemins de code embarqué, CMake/Kconfig, sdkconfig/partitions, outillage CI cible ou au propre workflow ; **push main inchangé**. Le test reste obligatoire dès que le firmware ou un composant compilé a changé.
5. **Acquisitions historiques J1.16-A/D-A** : introduire des filtres de chemins spécifiques et remplacer la concurrence par SHA par une concurrence par PR avec annulation des runs PR obsolètes ; `workflow_dispatch` demeure disponible.
6. **HW4** : annuler les matrices des vieux HEAD quand la PR reçoit un nouveau commit.

## Points de vigilance avant fusion

- Les changements de `CMakeLists.txt` ou `tools/ci/**` déclenchent toujours Xtensa ; la réduction n'élimine pas les compilations nécessaires.
- Les scripts de preuve scellée, les fixtures historiques et les oracles historiques restent inchangés.
- Les workflows de captures non modifiés peuvent encore créer des runs SKIPPED ; leur consolidation future doit être une mission distincte, avec tests de sécurité du routage.
- La vérification finale doit comparer nombre et identité des CTests de la matrice complète, les checks obligatoires sur le HEAD, le comportement sur un diff oracle/doc-only et sur un diff firmware, les erreurs négatives, et mesurer les temps **sur une PR après modification**. Ne pas déclarer un gain chronométrique avant cette mesure.
- **Ne pas supprimer des required checks de protection** sans prévoir une porte obligatoire stable équivalente. Vérifier d'éventuels rulesets/protections avant d'étendre les filtres.

## Étape future (hors PR, non autorisée implicitement)

Regrouper les workflows historiques `J1.*-A` dans une famille **CPC-ACQUISITION** pilotée par contrat déclaratif (cas/oracle/filtres/réacquisition), et distinguer `PR_FAST` d'une `REACQUIRE` volontaire. Conserver le binaire Caprice32 GHCR/ROM épinglés, la provenance des archives et les garde-fous contre écriture sur branche dépassée. Ne pas fusionner un tel chantier avec les changements de l'oracle J1.16-E-A en cours.
