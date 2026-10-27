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
- J1.5-A (#72) est **probatoire uniquement** : douze programmes CPC 6128, **deux sessions Caprice32 GHCR indépendantes par cas**, images RAM tokenisées avant RUN, captures LIST/RUN, imprimante directe `ERR` et `B%`, archive SHA scellée `af4b873f62e0fa8304f9389c149dcc6475463c498eea6834d4ce6ffda60ba5b9` (provisoire `PENDING_PILOTAGE`), 13 falsifications rejetées ; source `B%=A%\2`.
- Observations authentiques du CPC : opérateur `F9` sur 12/12 images RAM, **troncature vers zéro** sur ce corpus, `ERR=11` pour les deux divisions par zéro ; classification C99 actuelle `UNSUPPORTED` sur 12/12. L'opcode et les résultats ont été **mesurés**, jamais supposés. `\\` diffère de la division réelle `/`. Les anciens manifestes, classifications et archives sont intacts. C99 `core/` et firmware inchangés.
- [Rapport et protocole J1.5-A](docs/J1.5-A-integer-division-oracle.md) ; PR dédiée non fusionnée, J1.5-B non autorisé, `ON_DEVICE_UNVERIFIED`.



### Pilotage — J1.5-A accepté et fusionné (27 octobre 2026)

[PR #73](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/73) acceptée après revue contradictoire, squash 98700abd35b0a6fd23cce10fe6dc4badb159b61e. Oracle CPC6128 : 12 programmes, 24 sessions, token F9, troncature vers zéro et ERR=11 pour diviseur nul. 12/12 images RAM et sondes imprimante réacquises exactement ; 13 falsifications rejetées et fausse identité checkout rejetée. Archive et sceau historique PENDING_PILOTAGE préservés. [Revue Pilotage](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/73#issuecomment-6445724545). Suite autorisée : [J1.5-B, issue #75](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/75), division INTEGER native, sans support de la division réelle. TARGET_BUILD_VERIFIED ; ON_DEVICE_UNVERIFIED.


### J1.5-B — division INTEGER native F9 (27 octobre 2026)

- J1.5-A, [PR #73](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/73), **acceptée et fusionnée** ; base de travail `main=443a83460dc5d4ec10dfbf54b7ed9f16d0f5009b`.
- Natif C99 : `destination%=source%\n` avec références INTEGER explicites, diviseur 0..255 canonique, **F9** ; division signée tronquée vers zéro, diagnostic **`BE_DIVISION_BY_ZERO` interne** (non assimilé au `ERR=11` CPC).
- Oracle indépendant J1.5-A à douze cas en **lecture seule**, douze comparaisons RAM et LIST, dix quotients, deux erreurs, atomicité. Les classifications historiques `UNSUPPORTED` ne sont pas modifiées. Pas de division réelle `/`, de grammaire étendue ou de changement matériel.
- [Rapport et protocole J1.5-B](docs/J1.5-B-integer-division-native.md) ; PR développeur en revue non fusionnée ; `TARGET_BUILD_VERIFIED` uniquement si CI Xtensa, `ON_DEVICE_UNVERIFIED`.



### Pilotage — J1.5-B accepté et fusionné ; J1.6-A autorisé (27 octobre 2026)

**Décision Pilotage après revue contradictoire : J1.5-B ACCEPTÉ et FUSIONNÉ.** [PR #76](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/76), HEAD revu `bd574dac52c1fdfe5ee5fba33fa248b0f75eb68e`, **commit squash sur main `000210dacdb7098a7b6186c357a6f96754bd6541`**. [Issue #75](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/75) clôturée. L'opérateur CPC INTEGER `\` (F9) fonctionne dans le sous-ensemble strict `B%=A%\3` : **12/12 images RAM CPC MATCH_EXACT, 12/12 LIST, 10/10 quotients, 2/2 erreurs division par zéro**, atomicité **native** validée sans prétention sur celle du CPC historique. Archives originales et classifications J1.5-A inchangées. Le retour Codex antérieur, désormais obsolète et corrigé au HEAD, a été résolu.

**Preuves CI sur le HEAD revu :** [Linux C99 42/42 OFF/ON + sanitizers #40532502004](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40532502004), [régression INTEGER16 2/2 #40532501988](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40532501988), [oracle CPC historique GHCR #40532502066](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40532502066), [ESP32 Xtensa IDF v5.5.6 3/3 #40532502011](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40532502011) : **SUCCESS**. Vérification permanente J1.5-A incluse dans CTest malgré workflow d'acquisition dédié SKIPPED par filtre. IRAM 51 807 octets (39,53 %), DRAM 30 396 octets (16,82 %), Flash Code 66 186 octets, image mesurée 157 481 octets. **TARGET_BUILD_VERIFIED ; ON_DEVICE_UNVERIFIED.**

**Suite logique unique du cœur BASIC : [J1.6-A, issue #77 — oracle CPC indépendant pour MOD](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/77) AUTORISÉE.** Acquisition des encodages/valeurs/signes/erreurs par vraies sessions d'oracle ROM CPC, archive et falsifications indépendantes, **sans modifier le cœur C99 ni implémenter MOD**. J1.6-B ne démarrera qu'après revue et fusion de J1.6-A. Les travaux graphiques HW4 restent isolés du cœur BASIC.

### J1.6-A — Acquisition MOD indépendante (PR #79, en revue)

[PR #79](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/79) : 12 sources et 24 sessions ROM CPC, token `FB` mesuré en RAM, 12 images programme et 12 imprimantes reproductibles octet à octet ; `ERR=11` pour les deux diviseurs zéro ; 13 rejets de falsification, sceau provisoire `PENDING_PILOTAGE`. [Rapport et empreintes](docs/J1.6-A-integer-mod-oracle.md). **Pas de MOD natif**, pas de modifications des archives précédentes. Les [vérifications GHCR MOD](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40538665477), [Linux 42/42 OFF/ON](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40538664594), [oracle historique](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40538664815) et [Xtensa 3/3](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40538664734) ont été réussies sur le HEAD documentaire candidat `f07ee492`. **J1.6-B reste interdit** avant acceptation expresse par Pilotage. `TARGET_BUILD_VERIFIED ; ON_DEVICE_UNVERIFIED`.


### Pilotage — J1.6-A accepté et fusionné ; J1.6-B autorisé (27 octobre 2026)

**J1.6-A ACCEPTÉ / FUSIONNÉ** après revue contradictoire GitHub : [PR #79](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/79), HEAD revu `1e4f4515345651b62e36c1f9f676f2006b893cc8`, squash sur main **`954f07fe52e70844b7a6529009eda9e2f9a80681`** ; [issue #77](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/77) clôturée. Référence indépendante : oracle CPC 6128 BASIC 1.1, **MOD opcode FB**, 12/12 images RAM avant RUN, 12 LIST, 24 processus CPC distincts, 12/12 réacquisitions RAM et 12/12 imprimantes exactes, 13 falsifications et faux checkout refusés. Manifeste original `998c3768c61f8c2981ffabb8e138542fd575653b2f9a9c81f7919473f4cd9822`, sceau historique `J1.6-A-PROVISIONAL / PENDING_PILOTAGE` préservé **sans modification**. Les dix restes CPC observés sont `0,1,-1,-1,-1,0,-128,127,2,0`; diviseur zéro = `ERR=11` sur deux sondes. Pas de conclusion d'atomicité CPC issue de `B%=0` post-erreur. Les 12 classifications historiques natives `UNSUPPORTED` sont conservées (aucun code MOD ajouté en J1.6-A).

**Validation du HEAD final** : [Linux C99 42/42 OFF/ON ASan/UBSan #40539437477](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40539437477), [oracle historique GHCR #40539437394](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40539437394), [GHCR J1.6-A (24 sessions et 12/12 réacquisitions + falsifications) #40539437413](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40539437413), [ESP32 Xtensa IDF 5.5.6 (3/3) #40539437386](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40539437386) : **SUCCESS**. Flash Code 66 186 octets ; IRAM 51 807/131 072 (39,53 %) ; DRAM 30 396/180 736 (16,82 %) ; image `.bin` 157 600 octets. **TARGET_BUILD_VERIFIED ; ON_DEVICE_UNVERIFIED**.

**Suite cœur BASIC unique autorisée : [J1.6-B / issue #80 — MOD INTEGER natif FB](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/80).** Implémentation C99 strictement bornée de `B%=A% MOD n`, 12/12 RAM et LIST différentielles, 10/10 valeurs, 2/2 erreurs division par zéro natives atomiques, oracle original immuable. Le chantier graphique HW4 reste indépendant. Aucun autre jalon du cœur ne démarre avant PR J1.6-B examinée.

### HW4-A-C2 — moteur vidéo CPC natif portable (PR #78, en revue)

Moteur C99 indépendant de `core/` : MODE0 (160×200/16 encres), MODE1 (320×200/4 encres) et MODE2 (640×200/2 encres), surface compacte 16 000 octets, palette 27 couleurs, curseur overlay non destructif, PPM golden et sonde CYD sur écran ILI9341. Les cinq photographies du Product Owner confirment les mires initiales, le viewport MODE2 et le changement d'encre ; le correctif ultérieur du curseur de boot HW4-A-C1 **n'a pas encore de réacquisition UART/physique spécifique**. C2 invalide la bande du curseur à chaque changement effectif de PEN lorsqu'il est visible. PR #78 non fusionnée, [rapport vidéo](docs/HW4-A-cpc-video-contract.md), [issue #74](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/74). J1.6-A et la suite J1.6-B du cœur sont des travaux distincts.


### HW4-A — moteur vidéo CPC natif accepté (27 octobre 2026)

Le moteur vidéo C99 du projet est **accepté et intégré** via [PR #78](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/78), squash [`188e703ff965830b1a29629143844ef20c9f13a8`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/188e703ff965830b1a29629143844ef20c9f13a8). Les trois modes CPC existent en VRAM logique 16 Ko, palette 27 couleurs, curseur non destructif et prévisualisations PPM ; la sonde ILI9341 fonctionne sur le CYD physique d'après le retour PO et les journaux UART (`05bb0b4`). Linux 44/44 OFF/ON, Xtensa et oracles CPC verts. **Ce n'est pas encore une console BASIC avec écran intégré** : extraction du pilote en [HW4-B (issue #82)](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/82) puis raccord `PRINT` dans HW4-C, non lancé. Les 80 colonnes MODE2 sur TFT 320 px et la police historique CPC ne sont pas encore validées.

### J1.6-B — MOD INTEGER FB natif : PR #81 en revue (27 octobre 2026)

[PR #81](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/81) : implémentation C99 bornée de `destination%=source% MOD n`, token historique `FB`, `n=0..255`, reste signé selon l'oracle CPC, division par zéro interne `BE_DIVISION_BY_ZERO` avec atomicité native. Comparateur live à [preuves authentiques J1.6-A](tests/fixtures/cpc6128/j1_integer_mod/) ; 12 images RAM et SHA originaux de référence immuables, 12 LIST et 10 résultats + deux erreurs zéro contrôlés. Nouvelles suites CTest C99 `integer_mod_fb` et `j1_6_b_native_cpc_differential`, portant le total à 44. **Aucune extension MOD générique, aucun changement HW4/CYD ; PR non fusionnée en attente de décision Pilotage.** [Rapport technique](docs/J1.6-B-integer-mod-native.md).


### Décision Pilotage — J1.6-B accepté et fusionné ; J1.7-A autorisé (27 octobre 2026)

**J1.6-B = ACCEPTÉ / FUSIONNÉ** après revue contradictoire GitHub : [PR #81](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/81), HEAD final revu `15289bc05f365bc5182cd44a659db6988ca0e62e` ; squash `aa3e043d167471b7700b6ebabac52741e66aca2b` sur `main`. [Issue #80](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/80) clôturée. Intégration C99 native de l'opérateur INTEGER `MOD` (FB) limitée à `destination%=source% MOD n` avec n littéral décimal non signé 0..255, sans évaluateur général ni émulation Z80. **12/12 RAM CPC MATCH_EXACT, 12/12 LIST, 10/10 résultats, 2/2 erreurs BE_DIVISION_BY_ZERO, atomicité native validée**, aucune extrapolation sur l'atomicité du CPC. Toutes archives J1.6-A conservées, manifeste original `998c3768c61f8c2981ffabb8e138542fd575653b2f9a9c81f7919473f4cd9822` et 12 classifications historiques `UNSUPPORTED` inchangés.

**Preuves CI au HEAD final** : [Linux C99 OFF/ON 46/46 + ASan/UBSan #40546944954](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40546944954), [Oracle historique CPC GHCR #40546944125](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40546944125), [J1.6-A permanent + 13 falsifications #40546944320](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40546944320), [INTEGER16 #40546944272](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40546944272), [Xtensa ESP-IDF v5.5.6 3/3 #40546944121](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40546944121) : SUCCESS. Les anciennes acquisitions filtrées SKIPPED ne sont pas déclarées PASS. Flash Code 66 286 octets ; IRAM 51 807/131 072 (39,53 %) ; DRAM 30 396/180 736 (16,82 %) ; `loco_esp32_probe.bin` 157 712 octets. **TARGET_BUILD_VERIFIED ; ON_DEVICE_UNVERIFIED**. Les mentions historiques précédentes de PR « en revue » et 44 tests sont dépassées par la présente décision (46 tests, deux suites HW4-A sur main comprises).

**Suite autorisée pour le cœur BASIC : [J1.7-A — issue #84](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/84).** Acquisition CPC indépendante (12 cas, deux références INTEGER RHS) pour `C%=A%+B%`, enregistrement exact de cinq lignes BASIC et deux processus CPC frais par cas, archive scellée et CI. **Aucun code natif variable+variable dans J1.7-A ; J1.7-B bloqué jusqu'à revue et fusion.** Le développement du pilote partagé ILI9341 [HW4-B / PR #83](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/83) reste séparé, soumis à son propre test physique CYD au HEAD final.


### HW4-B — composant ILI9341 partagé (en revue)

Le pilote SPI2/ILI9341 DMA du CYD est désormais placé dans `firmware/components/cyd_ili9341/`, partagé entre la sonde HW3/HW4 et la compilation du firmware BASIC série. `core/` et `video/` restent autonomes, aucun `PRINT` vers l'écran. Voir [le contrat HW4-B](docs/HW4-B-ili9341-driver.md), [issue #82](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/82). CI et test physique PO au SHA de branche obligatoires avant fusion. HW4-C non autorisé.


### Décision Pilotage — HW4-B fusionné ; HW4-C1 autorisé (27 octobre 2026)

HW4-B **ACCEPTÉ ET FUSIONNÉ** — [PR #83](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/83), squash `6be495dca0a7fa768839960de661ece8dc58cea2`. Code pilote SPI2/ILI9341 partagé ; deux compilations Xtensa v5.5.6 et Linux 46/46 OFF + 46/46 ON ASan/UBSan, oracle CPC historique et J1.6-A verts sur HEAD de revue `594c8ec83ea09e1f6d6f48b2eed5155371ca0f91`. Essai PO sur vrai CYD au `7971d66eafec0bb590a28e890822d2826b21e71e` ; 19 fichiers firmware identiques après synchronisation, sans revendiquer de flash du nouveau SHA. [Issue HW4-C1 #86](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/86) : premier PRINT natif sur TFT, sans REPL tactile ni SD. J1.7-A reste indépendant.

### J1.7-A — Oracle CPC variable + variable (PR #85, en revue)

[PR #85](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/85) — douze sources originales à cinq lignes, 24 sessions indépendantes ROM CPC6128 BASIC 1.1, opérateur `F4` et trois références INTEGER explicites observées en RAM ; dix valeurs normales `ERR=0`, deux dépassements `ERR=6`. Manifeste historique `0608ba7d9548bae7972f02d0a929d0abde70fc325f49af97175f915aae08e2d5` et sceau provisoire `PENDING_PILOTAGE` conservés. Comparateur C99 historique : **12/12 UNSUPPORTED**, aucun ajout natif. [Rapport J1.7-A](docs/J1.7-A-integer-variable-addition-oracle.md). HW4-B demeure indépendant ; J1.7-B non autorisé avant décision du Pilotage.
