# État du projet — ESP32 Locomotive BASIC

**Mis à jour :** 24 octobre 2026. **Branche de référence :** `main`. Les jalons marqués « en revue » ne sont pas acquis avant revue/merge du chef de projet.

## Suivi des jalons

| Jalon | Périmètre | État | Livrable |
|---|---|---|---|
| **J0.1** | Cartographie statique des sous-systèmes Locomotive BASIC 1.1 | **Accepté et intégré dans `main` via [PR #1](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/1)** | [J0.1](J0.1-architecture-locomotive-basic-1.1.md) |
| **J0.2** | Format binaire lignes numérotées, tokens, références, flux, erreurs et vecteurs | **Accepté et intégré dans `main` via [PR #2](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/2)** | [J0.2](J0.2-format-binaire-tokens.md) |
| **J0.3** | Module `basic_program` C99 portable : stockage, validation, mutations, import/export d'images tokenisées et tests Linux ; sans tokenizer | **Accepté et intégré dans `main` via [PR #3](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/3)** | [J0.3](J0.3-basic-program.md) |
| **J0.4** | Tokeniseur natif C99, mots-clés/chaînes/entiers/références GOTO, tests et intégration `basic_program` | **Accepté et intégré dans `main` via [PR #4](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/4)** (squash `c774a700`)  | [J0.4](J0.4-basic-tokenizer.md) |
| **J0.5** | Détokéniseur et listing C99 du sous-ensemble J0.4, sans exécution ni firmware | **Accepté et intégré dans `main` via [PR #5](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/5)** (squash `d25cc9ad`) | [J0.5](J0.5-basic-listing.md) |
| **J0.6** | Saisie et édition minimales de lignes BASIC ; commandes directes LIST/NEW, sans RUN | **Accepté et intégré dans `main` via [PR #6](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/6)** (squash `486db356`) | [J0.6](J0.6-basic-session.md) |
| **J0.7** | Exécuteur pas-à-pas C99 de `PRINT` littéral/entier et `GOTO`, sortie atomique et diagnostic des erreurs ; `RUN` direct différé | **Accepté et intégré dans `main` via [PR #7](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/7)** (squash `8bb1060e`) | [J0.7](J0.7-basic-executor.md) |
| **J0.8** | Orchestration native `RUN`, `bsr_step` non bloquant, arrêt explicite, LIST/NEW pendant exécution, sixième suite CTest | **Accepté et intégré dans `main` via [PR #8](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/8)** (squash `d21af73d`) ; CI 6/6 Linux + 6/6 ASan/UBSan | [J0.8](J0.8-session-runtime.md) |
| **J0.9** | CLI Linux `loco_basic_cli` : édition/LIST/RUN, pilotage borné `:step`/`:stop`, erreurs et 7e suite CTest | **Accepté et fusionné via [PR #9](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/9)** (squash `2cb55757`) ; CI 7/7 Linux + 7/7 ASan/UBSan | [J0.9](J0.9-host-cli.md) |
| **J0.10** | Commentaires `REM` et apostrophe : flux tokenizeur → LIST → exécuteur, tests d'intégration natifs + CLI | **Accepté et fusionné via [PR #10](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/10)** (squash `0b2e66ed`) ; CI 8/8 Linux + 8/8 ASan/UBSan | [J0.10](J0.10-comments.md) |
| **J0.11 (proposé)** | `END` : arrêt explicite du programme, token CPC `98`, LIST/RUN/CLI et tests | **À développer — non lancé** | Prompt Pilotage à transmettre au développeur |
| Étapes ultérieures | Expressions et variables BASIC, console série embarquée, puis écran CYD | **Non lancées** | Aucun |

## Décisions techniques actées

1. Projet = **réimplémentation native en C**, pas d'émulation CPC ou Z80.
2. Le **cœur BASIC est indépendant du matériel** et validé sous Linux avant ESP32 ; architecture en composants tokenizer, programme, interpréteur, runtime, graphique, stockage et HAL.
3. **Mode de référence** : Locomotive BASIC 1.1 ; le désassemblage `basic.asm` est la source primaire. Les adaptations ESP32 doivent être explicitement séparées des comportements CPC.
4. **J0.2 valide comme spécification de travail** un flux tokenisé canonique : longueur `u16 LE`, numéro `u16 LE`, corps tokenisé, `00`, puis sentinelle `00 00`, sans sauvegarder l'octet de garde RAM. La compatibilité binaire exacte des variantes lexicales reste à confirmer par des captures CPC.
5. **Décision J0.2 :** conserver les références de ligne sous forme `1E` dans le format persistant et gérer les résolutions par offsets/caches invalidables, sans y placer des pointeurs C.
6. Pas d'optimisation de références `1D` historique tant que le comportement `record_begin-1` n'est pas validé sur CPC/émulateur de référence.
7. Dans les docs, séparer preuve directe du code Z80 **[C]**, déduction **[D]**, point à vérifier **[V]**, blocage **[B]**. Aucun vecteur déduit du désassemblage n'est automatiquement une « golden reference ».

## Risques / inconnues restantes

| Importance | Risque ou incertitude | Mesure prévue |
|---|---|---|
| **P0** | Emission lexicale exacte (espaces, variable I, constante 10, `GOTO`) encore non confrontée à un dump indépendant | Capture RAM ou fichiers tokenisés sur CPC/émulateur de référence, comparer aux vecteurs J0.2 |
| **P0** | Pointeurs temporaires `1D` et inversion en `1E` lors des modifications | Comparer dump avant/après RUN, remplacement et suppression |
| P1 | Numérotation 0 / 65535 / débordements et code d'erreur associé | Matrice de tests limites sur référence |
| P1 | Contextes complexes REM/DATA/ELSE/ON, suffixes de variables et noms collés | Tests différentiels de tokenisation et LIST |
| P1 | RAM ESP32 classique sans PSRAM, fragmentation, taille des structures BASIC | Budget RAM/SRAM mesuré à chaque version |
| P1 | Reproduction des réels CPC sur 5 octets et de l'arrondi | Jalon ultérieur de rétro-ingénierie numérique |
| P1 | Imprécisions/transcriptions dans le listing Z80 | Vérifier les octets source avant toute conclusion fragile |

## Barrières de livraison et plan pressenti

**J0.2 accepté via PR #2 :** revue technique réalisée, correction des chaînes non fermées intégrée, fil Codex résolu. L'absence de validation matérielle reste signalée ; les vecteurs déduits ne sont pas des références CPC indépendantes.

**J0.3 accepté via PR #3 :** revue des modifications réelles, CI Linux standard et ASan/UBSan réussies, tests d'invariants et de corruption vérifiés. Le module `basic_program` est intégré à `main`, sans tokenizer, firmware ni exécuteur. **J0.4 accepté et fusionné via PR #4 :** revue du code, intégration `basic_program` et CI Linux standard + ASan/UBSan (2/2 tests pour chaque job). Merge squash `c774a70085bbf46ed288998e6fe85d3442191918`. Fidélité binaire toujours à vérifier sur CPC. **J0.5 accepté et fusionné via PR #5 :** revue du code et CI Linux standard + ASan/UBSan (3/3 tests par job) ; merge squash `d25cc9ad4958787e1a3811f2ec29b8fa52e2c849`. Décodage des formes J0.4 et listing ordonné, sans exécution. Les tests aller-retour prouvent une cohérence interne, pas une fidélité CPC indépendante. **J0.6 accepté et fusionné via PR #6 :** revue des six fichiers modifiés, contrôle des API, contrats d'atomicité et buffers disjoints, CI Linux standard et ASan/UBSan (4/4 tests par job) ; merge squash `486db356117cb36a7533b7477e37f78fe2c34e6f`. Commandes directes `LIST`/`NEW` intégrées, sans exécution. **J0.7 accepté et fusionné via PR #7 :** moteur `basic_executor` C99 pas-à-pas (`PRINT` et `GOTO`), revue corrective des chaînes comportant `0x01` littéral, nouveaux tests validés par Pilotage, discussion Codex résolue, CI Linux standard et ASan/UBSan réussies (5/5 chacune) ; merge squash `8bb1060eb0a52b7644ee9c5c179f4e6b7d68bce4`. Le cœur reste indépendant du matériel, sans `RUN` direct. **J0.8 accepté et fusionné via PR #8 :** nouveau module `basic_session_runtime` C99, revue du diff réel, CI [#40081828507](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40081828507) validée (6/6 Linux + 6/6 ASan/UBSan), aucun défaut bloquant ; merge squash `d21af73d8e03326ec9fdb10060350955c9886c45`. **J0.9 accepté et fusionné via PR #9 :** CLI Linux native en C99, contrôle borné des pas, gestion fiable de stdin, sortie BASIC isolée sur stdout, septième suite CTest. Revue correctrice CMP0053 effectuée : `cmake_minimum_required(VERSION 3.13)` dans le script et expansions `${step1}` explicites ; [CI #40083698694](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40083698694) 7/7 Linux et 7/7 ASan/UBSan ; squash `2cb55757d887c07447217386a16d362e53591b19`. **J0.10 accepté et fusionné via PR #10 :** revue technique des 8 fichiers modifiés, du token `C5` pour `REM`, du marqueur `01 C0` pour l'apostrophe, de la conservation littérale et de LIST/RUN. Deux remarques Codex initiales corrigées et fils résolus. [CI #40085113134](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40085113134) réussie : 8/8 CTest Linux et 8/8 ASan/UBSan. Squash `0b2e66ed80fe78099f41d9ffae595626dee5a29a`. Réserve non bloquante : comportement binaire non encore confronté à une capture CPC indépendante. **J0.11 proposé, non lancé :** support étroit de la commande historique `END` ; son émission binaire et son comportement restent à valider contre `basic.asm` avant toute modification.

## Gouvernance GitHub

- **Développeur :** investigation et implémentation sur branche dédiée, commits et PR vers `main`, sans fusion autonome.
- **Pilotage :** revue technique des critères, demandes de corrections, acceptation/fusion selon autorisation et rédaction du prochain prompt.
- **Garde-fou :** ne pas enchaîner automatiquement sur le jalon suivant.
