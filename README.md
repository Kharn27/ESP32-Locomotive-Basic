# LOCO-CYD — Locomotive BASIC 1.1 pour ESP32 CYD

> **Objectif : recréer fidèlement, à terme avec une compatibilité complète, le véritable Locomotive BASIC 1.1 de l’Amstrad CPC 6128 sur ESP32 — en C natif, sans émulation Z80.**
>
> **Ce projet n’est pas un interpréteur BASIC générique.** Il vise précisément le dialecte, les tokens, la syntaxe, les règles d’exécution et les comportements historiques du **Locomotive BASIC 1.1 livré avec l’Amstrad CPC 6128**.
>
> **Project goal (English):** a native-C, ultimately fully compatible reimplementation of the **Amstrad CPC 6128 Locomotive BASIC 1.1** — not a generic BASIC interpreter and not a Z80 emulator.

**État : développement en cours — compatibilité CPC complète NON encore atteinte.** La fidélité au CPC 6128 est l’**objectif de référence**, pas une certification de la version actuelle. Voir le [suivi des jalons](docs/PROJECT_STATUS.md).

## Le BASIC que nous voulons retrouver

Le modèle est **l’Amstrad CPC 6128 et son Locomotive BASIC 1.1**, pas un BASIC simplifié, ni une adaptation libre partageant quelques mots-clés.

Notre définition de la compatibilité cible notamment :

- **Syntaxe et tokenisation CPC** : mots-clés, abréviations et formes lexicales acceptées/refusées, lignes numérotées, chaînes, constantes, variables, références de lignes et représentation interne.
- **Comportement de l’interpréteur** : ordre d’exécution, instructions et fonctions d’origine, expressions, précédence, conversions, tableaux, boucles, sous-programmes et commandes directes.
- **Sémantique et diagnostics historiques** : résultats, formatage, arrondis et nombres CPC (dont le format réel sur 5 octets), limites et erreurs observables du BASIC 1.1.
- **Graphismes et environnement CPC** : `MODE`, `INK`, `PEN`, `PAPER`, `PLOT`, `DRAW`, `LOCATE`, `WINDOW`, etc., avec adaptation de l’affichage à l’écran CYD **sans changer la sémantique BASIC**.
- **Programmes d’époque** : saisie, listing, chargement, sauvegarde et, à terme, exécution de programmes historiques CPC 6128 aussi fidèlement que possible, y compris leur représentation tokenisée.

**Objectif final :** un programme écrit pour **Locomotive BASIC 1.1 sur CPC 6128** doit pouvoir s’exécuter ici **sans réécriture**, dans les limites des périphériques effectivement pris en charge. Toute différence connue avec le CPC doit être **documentée, testée et traitée comme un écart à résorber**, et non devenir un nouveau dialecte BASIC.

Nous distinguons donc toujours trois niveaux : **implémenté**, **validé par les tests internes**, et **confirmé compatible avec un CPC 6128 de référence**. Une suite de tests Linux verte ne démontre pas, à elle seule, une compatibilité historique totale.

## Pourquoi une réimplémentation native ?

Nous **ne lançons ni ROM Locomotive BASIC d’origine ni machine Z80 émulée**. Le firmware réimplémente en **C99** les mécanismes du langage après étude des sources de référence (désassemblage et documentation), tout en restant indépendant des pilotes matériels.

Cela permet de :

- faire fonctionner le cœur sur Linux pour le tester de façon reproductible ;
- le porter ensuite sur l’ESP32 CYD, avec un budget mémoire contraint ;
- isoler le moteur BASIC du rendu écran, du tactile et du stockage ;
- avancer vers une fidélité mesurable, instruction par instruction.

Le code Z80 sert de **spécification comportementale historique**, pas de code à exécuter sur ESP32.

**Référence technique principale :** [désassemblage Locomotive BASIC 1.1 (`basic.asm`)](http://cpctech.cpc-live.com/docs/basic.asm). Les observations issues du désassemblage doivent être distinguées des hypothèses et confirmées, lorsque c’est nécessaire, par des programmes ou dumps CPC indépendants.

## Matériel cible

| Élément | Cible |
| --- | --- |
| Carte | **ESP32-2432S028R (CYD / Cheap Yellow Display)** |
| Microcontrôleur | ESP32 dual-core |
| Mémoire | Flash 4 Mo, **sans PSRAM** |
| Écran | ILI9341 TFT, 320 × 240 |
| Tactile | XPT2046 |
| Stockage externe | microSD |
| Moteur BASIC | C99 natif, indépendant de la HAL |

L’écran 320 × 240 de la CYD n’est pas un écran CPC d’origine : les modes et coordonnées CPC devront être **reproduits logiquement**, puis adaptés au matériel. La même séparation s’applique au clavier, aux fichiers, au son et aux autres périphériques.

## Où en sommes-nous ?

Les **jalons J0.1 à J0.8 sont acceptés et fusionnés**. Ils constituent un **socle minimal**, pas encore le langage complet :

| Domaine | État du projet |
| --- | --- |
| Analyse du BASIC 1.1, format des lignes et tokens | Documentation et spécification de travail disponibles |
| Stockage de programme, tokeniseur, détokéniseur et `LIST` | Sous-ensemble implémenté, testé sous Linux |
| Édition des lignes et `NEW` | Sous-ensemble implémenté |
| `PRINT` (formes simples) et `GOTO` | Exécuteur natif pas-à-pas implémenté |
| `RUN`, reprise depuis le début, arrêt externe et état de session | Orchestration native non bloquante implémentée |
| Console de démonstration Linux | **J0.9 prévu / en développement** |
| Variables, expressions générales, autres commandes, nombres réels CPC | **À développer** |
| Graphismes CPC, interface CYD, microSD et firmware autonome | **À développer** |
| Validation différentielle complète face au CPC 6128 | **À réaliser** |

Le projet **ne peut pas encore faire tourner arbitrairement un programme CPC 6128**. Certains formats et comportements sont des hypothèses de travail à confirmer sur une référence indépendante.

Consulter les [décisions, PR fusionnées, risques et jalons](docs/PROJECT_STATUS.md) et les spécifications `docs/J0.*` pour connaître le périmètre exact de chaque livraison.

## Architecture du dépôt

```text
core/                 # Bibliothèques du cœur BASIC, indépendantes du matériel
tests/                # Tests automatisés du cœur
docs/                 # Spécifications, validations, décisions et suivi
CMakeLists.txt        # Construction C99 et CTest sur Linux
```

Le futur hôte Linux, puis la couche matérielle ESP32, **appellent** le cœur BASIC ; ils ne doivent pas redéfinir la syntaxe ou contourner ses règles pour faciliter une démonstration.

**Contraintes structurantes :** C99 strict, allocation maîtrisée (pas de tas dynamique dans le cœur actuel), pas de dépendance Arduino/ESP-IDF dans `core/`, contrats mémoire explicites, tests de non-régression et validation systématique des changements.

## Compiler et tester le cœur sous Linux

Prérequis : compilateur C99, CMake et CTest.

```sh
cmake -S . -B build -DBP_SANITIZERS=OFF
cmake --build build
ctest --test-dir build --output-on-failure
```

Avec AddressSanitizer et UndefinedBehaviorSanitizer (sur un compilateur compatible) :

```sh
cmake -S . -B build-asan -DBP_SANITIZERS=ON
cmake --build build-asan
ctest --test-dir build-asan --output-on-failure
```

**À ce stade, ces commandes construisent et testent les bibliothèques ; elles ne démarrent pas encore un ordinateur CPC interactif.** La console hôte est le jalon suivant. Les tests de J0.8 ont validé six suites dans chacune des deux configurations CI ([GitHub Actions](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40081828507)).

## Ligne directrice du projet

1. **Fidélité au Locomotive BASIC 1.1 du CPC 6128 avant les fonctionnalités de confort.**
2. **Pas de BASIC « presque compatible » présenté comme équivalent** : une instruction absente ou divergente reste identifiée comme telle.
3. **Pas d’émulation Z80** : implémentation native, modulaire et testable.
4. **Petits jalons vérifiables** : spécification → développement → PR → revue technique → intégration.
5. **Compatibilité prouvée, et non supposée** : tests Linux pour la sûreté, confrontation au CPC pour la fidélité.
6. **Cœur portable d’abord**, intégration ESP32 CYD et périphériques ensuite.

### Gouvernance

Le **Product Owner** fixe la vision et les priorités. **ChatGPT Pilotage** assure la conception, les revues techniques et l’intégration des PR après validation. **ChatGPT Développeur** réalise les jalons sur branches dédiées. Les décisions et l’avancement restent documentés dans le dépôt.

---

**En une phrase : ce projet veut transformer une ESP32 CYD en ordinateur exécutant le véritable Locomotive BASIC 1.1 du CPC 6128, avec pour cible une compatibilité complète — pas inventer un BASIC supplémentaire.**
