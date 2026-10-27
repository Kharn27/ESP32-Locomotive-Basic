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

## Où en sommes-nous ? — 27 octobre 2026

**J0 est clos (J0.28). J1 est en cours : J1.1, J1.2-A/B/C et J1.2-HW2 ont été acceptés et fusionnés.** Nous réimplémentons nativement en C99 **Locomotive BASIC 1.1 du CPC 6128** : la compatibilité visée est historique mais **reste partielle et délimitée par les preuves**.

| Domaine | Capacité effectivement démontrée |
| --- | --- |
| Programme BASIC, tokens, LIST et RUN | Numérotation et stockage des lignes, import/export CPC, LIST et RUN sur le sous-ensemble testé ; confrontations CPC indépendantes |
| INTEGER natif | Littéraux signés `-32768..32767`, stockage et PRINT INTEGER ; addition simple `B%=A%+n` (n de 0 à 255) et diagnostics bornés |
| Soustraction binaire `B%=A%-n` | **Non implémentée dans le C99** ; l'oracle CPC indépendant [J1.3-A / PR #63](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/63) est accepté et archivé ; J1.3-B est l'incrément suivant |
| Linux et Caprice32 | CI C99 sans/avec ASan/UBSan ; Caprice32 CPC 6128 via image GHCR au digest immuable |
| ESP32 CYD réel | Deux sondes ciblées exécutées ; J1.2-HW2 confirme les frontières INTEGER, la tokenisation NMIN et la stabilité apparente des ressources |
| Écran BASIC, tactile, microSD | **Non intégrés / non validés** ; l'écran TFT n'est pas encore un terminal BASIC utilisable |

**Validation matérielle J1.2-HW2 :** [PR #61](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/61) fusionnée dans `main` au commit `d9aeb39863391d95df3a79c7192b353e7ade1230` après revue Pilotage et UART réel fourni par le Product Owner. `ON_DEVICE_TEST_PASS`, cas INTEGER `255`, `256`, `-256`, `32767`, `-32768`, NMIN `IMAGE_MATCH_EXACT` (36 octets), rejet atomique de `+32768`. Pas de panic/reboot observé ; heap 8 bits libre de **285 988 octets** et plus grand bloc **155 648 octets** stables, stack HWM minimale **2 800 octets**. SHA-256 du firmware ELF exécuté : `96db76d92949ec36cd7c2eeb97ca55ed057e522d2770410940edd3d23e9dee54`. Les CI validées du HEAD HW2 : [Linux #40492465009](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40492465009), [GHCR #40492465252](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40492465252), [Xtensa #40492465140](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40492465140). **Ce test n'est pas une validation globale des périphériques ou du langage.**

Les **quatre B1 historiquement UNSUPPORTED** et les **18 LIST/RUN historiques UNVERIFIED** restent documentés comme observations à leur date, sans réécriture rétroactive. Voir [PROJECT_STATUS](docs/PROJECT_STATUS.md), [ROADMAP_GATES](docs/ROADMAP_GATES.md) et le [protocole J1.3-A](docs/J1.3-A-integer-subtraction-oracle.md).

## Sonde ESP-IDF J0.25 — exécutée sur CYD physique

La [PR #44](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/44)
a été **acceptée et fusionnée** (squash `865a4cd1`). Elle introduit un projet distinct `firmware/esp32_probe/` pour la **première
compilation croisée Xtensa du cœur C99 réel** sur ESP32 classique,
Flash 4 Mo, sans PSRAM et sans périphériques. Le scénario
`A%=2; B%=A%+3; PRINT B%; END` utilise les API du cœur, et non une
sortie simulée. **`TARGET_BUILD_VERIFIED`** : la [CI réelle Xtensa finale #40303901028](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40303901028)
a réussi (ESP-IDF v5.5.6, ELF Xtensa et binaire de 153 360 octets,
IRAM 51 807, DRAM 30 396). **`ON_DEVICE_VERIFIED PASS`** après flash réel sur CYD par le Product Owner :
le programme BASIC a émis `5`, avec **285 988 octets** de heap 8 bits libre avant et après, **155 648 octets** de plus grand bloc, et **2 976 octets** de marge pile restante après exécution. Provenance : transcription série fournie par le PO, [rapport matériel J0.25-HW1](docs/J0.25-HW1-cyd-physical-validation.md). Les périphériques écran/tactile/SD restent non testés.
Voir [J0.25](docs/J0.25-esp32-xtensa-feasibility.md). **Cette sonde a également passé le test matériel ; depuis J0.28, J0 est clos. Les limites de couverture restent documentées.**

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

Après J0.24-C7 (PR #43), les **25 suites CTest** sont réussies sous Linux et ASan/UBSan. Les [images CPC tokenisées](tests/fixtures/cpc6128/token_ram/) couvrent huit cas exacts indépendants ; les [sondes comportementales C/D](tests/fixtures/cpc6128/run_behavior/) disposent d'un SHA d'acquisition historique épinglé et d'une barrière de non-régression. La capture imprimante n'est **pas** une capture byte-à-byte de l'écran CPC. Les [preuves de listing CPC imprimante](tests/fixtures/cpc6128/list_printer/) révèlent deux différences exactes de fin de ligne avec stdout Linux, sans modification du cœur C99. La compilation ESP-IDF/Xtensa est désormais démontrée par J0.25 ; son exécution sur CYD physique et les mesures heap/pile sont désormais [documentées](docs/J0.25-HW1-cyd-physical-validation.md). Les sorties écran CPC restent à homologuer.

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


## J1.3-B — soustraction INTEGER acceptée (27 octobre 2026)

La soustraction INTEGER native bornée `B%=A%-n` (`n` décimal non signé 0..255) est **acceptée/fusionnée via [PR #67](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/67)** : six images tokenisées CPC indépendantes `MATCH_EXACT`, cinq résultats exécutables et un dépassement atomique natif. Le dossier [J1.3-B](docs/J1.3-B-integer-subtraction-native.md) conserve la distinction avec les preuves historiques J1.3-A. CI C99 OFF/ON 38/38, oracle GHCR et Xtensa vérifiés ; **nouvelle opération ON_DEVICE_UNVERIFIED** tant qu'aucun test physique spécifique n'est fourni. [J1.4-A #68](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/68) lance uniquement l'oracle CPC de multiplication ; le spike [HW3 écran / PR #66](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/66) reste indépendant et en attente de retest matériel. Écran/tactile/microSD non intégrés au firmware BASIC.


## J1.4-A — multiplication : oracle CPC mesuré (27 octobre 2026)

L'oracle CPC6128 pour la multiplication INTEGER `B%=A%*n` est désormais capturé pour **8 programmes authentiques** (issue [#68](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/68)). L'opérateur binaire est le token CPC mesuré **`F6`** ; six exécutions `ERR=0`, deux dépassements `Overflow in 20`, `ERR=6`. Le cœur C99 **ne prend pas encore en charge** cette multiplication : les huit expressions ont le statut natif `UNSUPPORTED`. [Corpus, provenance et limitations](docs/J1.4-A-integer-multiplication-oracle.md). L'archive et son sceau sont en attente de revue Pilotage, **J1.4-B n'est pas autorisé**. HW3 reste indépendant et la couverture physique CYD de cette opération n'existe pas.


### J1.4-B — multiplication INTEGER native (27 octobre 2026 ; en revue Pilotage)

- J1.4-A **acceptée et fusionnée** via PR #69 ; merge commit `49586583ef0b877798837bd9b894be666afb3f29`. Ses huit preuves CPC authentiques restent immuables, y compris la classification C99 **historique** `UNSUPPORTED`.
- J1.4-B (#70) : opérateur `*` CPC `F6` pour une unique affectation `destination%=source%*n`, entier littéral non signé `0..255`, avec calcul `int32_t`, vérification INT16 et commit atomique. Le nouvel oracle live est indépendant de l'archive J1.4-A.
- Validation requise : 8/8 images RAM MATCH_EXACT, 6/6 produits CPC, 2/2 débordements sans mutation, CI Linux ASan/UBSan + GHCR + Xtensa IDF v5.5.6. Les résultats de CI du **HEAD final** doivent être attestés dans la PR.
- **En revue, non fusionnée** ; pas de J1.5, pas de graphique ni de HW3 / PR #66. `ON_DEVICE_UNVERIFIED` tant qu'un test physique CYD n'a pas été réalisé.
- Rapport dédié : [J1.4-B-integer-multiplication-native.md](docs/J1.4-B-integer-multiplication-native.md).



### J1.5-A — oracle CPC indépendant pour division INTEGER (27 octobre 2026)

- **J1.4-B est accepté et fusionné** via PR #71 ; `main=420735eb87d69ad1bc195fe18be68e56fcd756f9`.
- J1.5-A (#72) est **probatoire uniquement** : douze programmes CPC 6128, **deux sessions Caprice32 GHCR indépendantes par cas**, images RAM tokenisées avant RUN, captures LIST/RUN, imprimante directe `ERR` et `B%`, archive SHA provisoirement scellée ; source `B%=A%\\n`.
- Opcode, règle d'arrondi, erreurs et numéros sont **à mesurer sur CPC**, jamais supposés. `\\` diffère de la division réelle `/`. Les anciens manifestes, classifications et archives sont intacts. C99 `core/` et firmware inchangés.
- [Rapport et protocole J1.5-A](docs/J1.5-A-integer-division-oracle.md) ; PR dédiée non fusionnée, J1.5-B non autorisé, `ON_DEVICE_UNVERIFIED`.

