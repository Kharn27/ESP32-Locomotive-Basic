# CI-PAPER-PERM-A1 — maintenance du sceau PAPER

Mandat : [issue #214](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/214). Correctif **CI uniquement** : aucun comportement BASIC, outil oracle ou fichier CPC modifié.

## Vérification permanente obligatoire

Le job `sealed-evidence` de `.github/workflows/ci-cpc-permanent.yml` s'exécute sur toute PR (y compris documentaire), et sur chaque push `main`, sans filtre de chemins ou de branche PR. Son étape PAPER est inconditionnelle, en bash fail-closed :

```bash
set -euo pipefail
python3 tools/j1_19_a_paper_oracle.py --check-sources
python3 tools/j1_19_a_paper_oracle.py \
  --evidence tests/fixtures/cpc6128/j1_19_a_paper \
  --permanent --self-test
```

Le vérificateur compare les 264 empreintes externes aux originaux, le SHA du manifeste, la provenance et l'ancêtre Git. Une archive absente ou falsifiée fait échouer le job. La chaîne n'acquiert aucune nouvelle session Caprice32.

## Acquisition CPC historique indépendante

Le job `paper-cpc-acquisition` du même workflow est inchangé. Son garde le réserve à `oracle/j1-19-a-paper-cpc` et aux conditions de provenance/fork d'origine. Les 24 sessions Caprice32, le pin ROM/GHCR/HEAD, la comparaison originale/répétition et la publication de l'archive continuent à relever **exclusivement** de ce job. Il est normalement `SKIPPED` sur une PR ordinaire, ce qui n'est ni un échec ni un PASS d'acquisition.

L'origine indépendante est documentée dans [J1.19-A-paper-cpc-oracle.md](J1.19-A-paper-cpc-oracle.md) et le [run Caprice32 #41137160254](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41137160254). Le contrôle permanent ne régénère ni manifeste ni sceaux.

## Maintenance, anti-contournement et preuves

`python3 tools/ci/opt3_routing.py --self-test` conserve les 32 workflows et cinq familles. Il exige les événements non filtrés, le job permanent non conditionnel et le script PAPER **exact** : aucune suppression, relocalisation dans le seul job spécialisé, condition `if`, `continue-on-error`, omission d'argument, faux chemin, faux outil ou `|| true` n'est autorisée.

Les 12 falsifications de routage PAPER préexistantes sont conservées. Les nouveaux contrôles simulent les attaques YAML en mémoire et vérifient également archive absente, manifeste modifié, mauvais ancêtre, altération coordonnée manifeste/fichier et mauvais sceau externe sur une copie temporaire ou des valeurs d'oracle modifiées uniquement en mémoire. Aucun fichier historique suivi par Git n'est modifié.

**Revue Pilotage :** vérifier les conclusions des workflows sur le SHA complet final et inspecter dans le log `sealed-evidence` l'étape `J1.19-A PAPER 264 external seals` effectivement exécutée en `success`. Ne jamais compter un workflow `SKIPPED` comme PASS, ni déduire d'un contrôle permanent une nouvelle acquisition indépendante.