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

**Jalons J0.1 à J0.23 et sous-missions J0.24-C1 à C7 acceptés et fusionnés (PR #43 comprise).** Le cœur C99 exécute la tranche arithmétique témoin ; **un programme CPC 6128 arbitraire reste hors périmètre**. Huit images mémoire tokenisées ont été comparées avec succès à des acquisitions CPC indépendantes, deux sondes numériques après `RUN` confirment C=5/D=2 et deux captures d'imprimante CPC pour `LIST` documentent une différence `CRLF`/`LF` avec la console Linux. **J0 reste ouvert :** la sortie écran byte-à-byte de `LIST` et `RUN` n'est pas homologuée, et aucune compilation/marge RAM/Flash/pile ESP-IDF/Xtensa réelle n'est démontrée.

| Domaine | État vérifié sur `main` |
| --- | --- |
| Programme et représentation CPC | Stockage, édition de lignes numérotées, import/export tokenisé, tokeniseur, détokéniseur, `LIST` et `NEW` pour un **sous-ensemble** (J0.1–J0.6) |
| Exécution BASIC native | `PRINT` littéral ou constante simple, `GOTO`, `END`, `REM`, apostrophe ; `RUN` piloté pas à pas et arrêt externe (J0.7–J0.11) |
| Environnement de test | Console Linux `loco_basic_cli` avec `:help`, `:step`, `:stop`, `:quit`, exclusivement pour le développement (J0.9) |
| Types, références et magasin | Décodage CPC borné, types implicites, clés canoniques et magasin scalaire INT16 / REAL5 / STRING vide (J0.12–J0.15, J0.17) ; lecture/écriture INTEGER raccordées à `RUN` en J0.19/J0.20 |
| Variables dans `PRINT` | Références `%`, `$`, `!` tokenisées et listables (J0.16) ; les INTEGER explicites `%` existants sont **désormais lus et affichés par `RUN`** (J0.20) ; STRING/REAL5 non exécutables et rendu numérique CPC non encore validé |
| Affectations INTEGER | `A%=2` et `LET A%=2` : représentation CPC et `LIST` (J0.18), **exécutables dans `RUN`** (J0.19), avec création/réaffectation en magasin borné, constantes 0 à 255 et une seule affectation par ligne |
| Expression INTEGER simple | `B%=A%+3` et `LET B%=A%+255` : représentés en tokens CPC (J0.21), **exécutables** en `RUN` via addition INTEGER bornée (J0.22), variables explicitement typées, écriture atomique et diagnostic interne de dépassement |
| Évaluateur complet, nombres CPC5, autres commandes | **Non implémentés** ; ni expressions générales, ni priorités/opérateurs complexes, ni exécution des références STRING/REAL5 dans `PRINT`, ni support intégral du dialecte |
| Écran et périphériques ESP32 CYD | **Non intégrés** : pas encore de firmware autonome, graphismes CPC, tactile ou microSD |
| Audit mémoire CYD | J0.23 : tailles ABI et réservations mesurées sous Linux, estimation d'affichage, risque de pile CLI hôte de 170 256 octets ; faisabilité ESP32 **plausible mais non démontrée** |
| Oracle CPC 6128 | Caprice32 v4.6.0 à commit figé ; **8 images RAM tokenisées historiques** (`MATCH_EXACT`), **2 sondes `PRINT #8,B%` après `RUN`** (`MATCH_SEMANTIC`, valeurs 5 et 2), et **2 sorties `LIST` CPC sur imprimante** (`DIFF` vs CLI Linux, CRLF/LF), archives permanentes à provenance contrôlée ; [CI oracle #40285325700](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40285325700) |
| Compatibilité historique validée sur CPC indépendant | **Partielle** : 8 tokenisations exactes, 2 observations comportementales numériques et 2 comparaisons brutes `LIST` en `DIFF` (fin de ligne imprimante/CLI) ; 18 comparaisons `LIST`/`RUN` non vérifiées, formatage écran et compatibilité générale non homologués |

Au dernier HEAD C7 validé puis fusionné par [PR #43](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/43), la CI a réussi **25/25 suites Linux et 25/25 ASan/UBSan** ([run #40285325699](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40285325699)). Le banc différentiel J0.24 réunit **8 `MATCH_EXACT` de tokenisation, 2 `MATCH_SEMANTIC` sur INTEGER post-`RUN`, et 2 `DIFF` de listing imprimante CPC contre CLI Linux** (CRLF/LF) ; **18 observations restent `UNVERIFIED`**. La fidélité écran byte-à-byte et la faisabilité ESP32 restent à vérifier. Ces preuves ciblées ne démontrent pas une compatibilité CPC 6128 complète.

Voir le [suivi des jalons et des risques](docs/PROJECT_STATUS.md), les [barrières J0 → J1](docs/ROADMAP_GATES.md) et les spécifications dans `docs/J0.*` pour la portée exacte et les preuves de chaque mission.

## Sonde ESP-IDF J0.25 (acceptée, test matériel à réaliser)

La [PR #44](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/44)
a été **acceptée et fusionnée** (squash `865a4cd1`). Elle introduit un projet distinct `firmware/esp32_probe/` pour la **première
compilation croisée Xtensa du cœur C99 réel** sur ESP32 classique,
Flash 4 Mo, sans PSRAM et sans périphériques. Le scénario
`A%=2; B%=A%+3; PRINT B%; END` utilise les API du cœur, et non une
sortie simulée. **`TARGET_BUILD_VERIFIED`** : la [CI réelle Xtensa finale #40303901028](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40303901028)
a réussi (ESP-IDF v5.5.6, ELF Xtensa et binaire de 153 360 octets,
IRAM 51 807, DRAM 30 396). **`ON_DEVICE_UNVERIFIED`** :
aucun journal d'exécution sur CYD physique, aucune mesure de heap/pile.
Voir [J0.25](docs/J0.25-esp32-xtensa-feasibility.md). **Le test série réel sur CYD est maintenant la prochaine validation ; J0 reste ouvert.**

## Architecture du dépôt

```text
core/                 # Bibliothèques du cœur BASIC, indépendantes du matériel
host/                 # Console Linux native (outil de développement J0.9)
firmware/esp32_probe/ # Sonde ESP-IDF Xtensa native (J0.25 acceptée)
tests/                # Tests unitaires et d'intégration CTest
docs/                 # Spécifications, validations, décisions et suivi
CMakeLists.txt        # Construction C99 et CTest sur Linux
```

La console Linux, puis la future couche matérielle ESP32, **appellent** le cœur BASIC ; ils ne doivent pas redéfinir la syntaxe ou contourner ses règles pour faciliter une démonstration.

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

**La console hôte Linux est désormais disponible**, mais ce n'est pas encore un ordinateur CPC complet. Après compilation :

```sh
./build/loco_basic_cli
```

Ce prototype accepte les lignes numérotées, `LIST`, `NEW`, `RUN`, `PRINT` sur littéral ou constante simple, `GOTO`, `END`, `REM` et l'apostrophe (`'`). Les références de variables explicites dans `PRINT` sont tokenisées et listables ; celles de type INTEGER `%` peuvent désormais être **lues et affichées pendant `RUN`**, si la variable existe (J0.20). Les affectations `INTEGER` avec/sans `LET` sont exécutables pour les constantes 0..255 (J0.19) **ou** une référence `%` existante additionnée d'une constante 0..255 (J0.22), à raison d'une affectation autonome par ligne. Le format numérique actuel est provisoire et les variables absentes déclenchent un diagnostic interne. Les méta-commandes Linux (`:help`, `:step`, `:stop`, `:quit`) ne font **pas** partie du Locomotive BASIC historique ; `RUN` est piloté explicitement par `:step`.

Après J0.24-C7 (PR #43), les **25 suites CTest** sont réussies sous Linux et ASan/UBSan. Les [images CPC tokenisées](tests/fixtures/cpc6128/token_ram/) couvrent huit cas exacts indépendants ; les [sondes comportementales C/D](tests/fixtures/cpc6128/run_behavior/) disposent d'un SHA d'acquisition historique épinglé et d'une barrière de non-régression. La capture imprimante n'est **pas** une capture byte-à-byte de l'écran CPC. Les [preuves de listing CPC imprimante](tests/fixtures/cpc6128/list_printer/) révèlent deux différences exactes de fin de ligne avec stdout Linux, sans modification du cœur C99. La compilation ESP-IDF/Xtensa est désormais démontrée par J0.25 ; le prochain contrôle est son exécution sur la CYD physique, avec mesure heap/pile. Les sorties écran CPC restent à homologuer.

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
