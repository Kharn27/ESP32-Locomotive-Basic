# CI-A4-FAST — politique de routage sans réacquisition CPC inutile

**Mandat Pilotage :** #363 (GO exécution du 10/11/2026). Références : #359, #360, #364, #366. Travail CI uniquement ; pas de modification du CORE, de TIME, du collecteur, du corpus, des archives historiques ou du candidat REAL5 C99.

## Qualité des deux chemins

- **FAST_HOST_ONLY_NO_CPC_EVIDENCE_REUSE** : tests Python négatifs/falsificateurs, auto-test du collecteur et matrice GCC/Clang optimisé/ASan-UBSan. `cpc-acquire` et `sealed-replay` sont **SKIPPED** (et jamais traités comme SUCCESS). Aucune nouvelle acquisition CPC et aucune nouvelle comparaison de l'exécutable candidat avec les octets CPC ne sont revendiquées sur ce HEAD. Les anciennes preuves demeurent sur leurs HEAD historiques ; **aucune** étiquette `EVIDENCE_REUSED_INPUT_IDENTICAL` n'est émise tant qu'une réutilisation d'archives avec authentification indépendante n'est pas implémentée.
- **HEAD_EXACT_INPUT_CHANGED** ou **HEAD_EXACT_MANUAL_FULL** : acquisition CPC ROM-backed à deux sessions sur le HEAD courant, sceau SHA256 indépendant, RAW horodatés et inventoriés, rejeu fail-closed et rapport candidat. Les 50 observations et les PNG nécessitent toujours les contrôles humains du Pilotage. Un échec bloque ; un artefact partiel n'est jamais un PASS.

**Règle de décision :** les entrées CPC sont représentées par une empreinte SHA256 sur les objets Git (modes + identifiants des blobs ou gitlink) du corpus A4 entier, du générateur/collecteur/replay A4, de ses helpers CLK-03/CLK-04 et du pin du sous-module Caprice32. On y ajoute **exactement** le contenu des jobs `cpc-acquire` et `sealed-replay` du workflow, à l'exception contrôlée des deux propriétés de routage `needs`/`if` de niveau job. Le contrôle de sécurité refuse toute altération des conditions obligatoires de ces jobs sur le HEAD.

Pour une PR, le script compare cette empreinte du HEAD au **merge-base** de la branche et de la base GitHub (pas aux seuls paths de PR ni au commit de synchronisation) ; si différente, **FULL**. Si identique, **FAST**. Une base Git indisponible, un fichier manquant, un objet Git de type inattendu, un checkout HEAD divergent ou un câblage de jobs invalide produit une erreur non masquée. `workflow_dispatch` force toujours **FULL**.

Les changements du **candidat C99**, de ses tests, de la documentation, d'OPT3 ou du contrôleur de routage seul sont **FAST** tant qu'ils ne modifient pas les entrées ci-dessus. Ils ne deviennent pas, par ce seul fait, des preuves CPC sur ce nouveau HEAD. Toute évolution du format de mesure, de la ROM/Caprice32, d'un pin, du collecteur ou de la logique de rejeu impose FULL. Le workflow A4 reste un unique membre de la famille `CPC_ACQUISITION` CI-OPT3, avec déclencheurs explicites pour chaque helper ou pin.

### Limite prudente, sans waiver

Une PR qui *modifie réellement* des entrées A4 par rapport au merge-base exige encore **FULL à chaque synchronisation** de son HEAD. La route ne tente pas de réemployer automatiquement un RAW précédent, car cela imposerait de retrouver et d'authentifier les trois artefacts liés à l'ancienne acquisition, avec vérification du pin et du sceau externe, sans inventer une preuve HEAD_EXACT. Il ne s'agit pas d'une optimisation de cache des acquisitions à HEAD différents. Cette restriction évite de convertir une ancienne acquisition interrompue ou non authentifiée en validation de la dernière synchronisation.

### Tests et recette

```sh
python3 -m unittest discover -s tests -p 'test_clk_04_a4_fast_route.py' -v
python3 -m unittest discover -s tests -p 'test_clk_04_a4_numeric.py' -v
python3 tools/clk_04_a4_oracle.py --self-test
python3 tools/ci/opt3_routing.py --self-test
```

Les tests de routage créent des dépôts Git synthétiques et vérifient : workflow routage seul → FAST ; OPT3 seul → FAST ; candidat seul → FAST sans prétention CPC ; simple merge de `main` → FAST ; corpus / collecteur / helpers / gitlink / image / protocole / vérificateur modifiés → FULL ; `workflow_dispatch` → FULL ; fichier absent / faux HEAD / mauvais ref / condition CPC ou replay contournée → FAIL. Les falsifications A4 historiques (`test_clk_04_a4_numeric.py`) conservent les négatifs SHA/scellé/RAW. Un CI-A4-FAST rouge n'est jamais déguisé en jaune ou vert.

### Durées et validation GitHub

Référence historique : [A4 #42810185987](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42810185987) (ancien HEAD, acquisition en dizaines de minutes ; limite de sécurité 100 minutes). Le temps FAST doit être **mesuré sur la PR CI-A4-FAST réelle** ; ne pas confondre plafond de timeout et durée observée. Pour faire la démonstration full, choisir `Run workflow` sur la branche à qualifier : cela provoque une acquisition CPC complète et sa comparaison avec ses propres RAW, sans altérer #360/#366. La décision de lancer une campagne complète supplémentaire sur la seule modification CI appartient au Pilotage.

**Bornes de preuve maintenues :** `CANDIDATE_PARTIAL_MATCH` et `twice_real5_status=UNVERIFIED` (C2), 10 `UNSUPPORTED`, `RANGE_UNVERIFIED` ; aucune qualification CORE/TIME. `ON_DEVICE_UNVERIFIED` pour le CYD physique (CI seulement).