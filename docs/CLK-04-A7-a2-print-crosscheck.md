# CLK-04-A7 — Audit croisé des `PRINT #8` REAL5 A2 contre le C99 A6

**Mandat :** [#402](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/402), `GO PILOTAGE` 19/11/2026. **Base exacte :** `main@902f3abeaf6fc9244236b397ddd1f278cf545b09` (A6-C1, PR #399). Branche `lab/clk-04-a7-a2-print-crosscheck`, PR Draft vers `main`. Le HEAD final A7 est celui publié par GitHub dans la PR ; aucune capture A2 n'est imputée à A7.

## Provenance et frontière des preuves

Les trois ZIP originaux sont les artefacts du [run A2 #42653720557](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42653720557), **HEAD A2 historique** `a9355e507ad17531163c8d578cc3f451c63f5dad` :

| Artefact | ID et lien | SHA-256 du ZIP (GitHub, recalcul local) |
|---|---|---|
| RAW | [#13692283699](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42653720557/artifacts/13692283699) | `d0316f543834206166e1db46cd26a2d005e9b98be74df1bbb39f65bab66117b6` |
| Sceau indépendant | [#13692103933](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42653720557/artifacts/13692103933) | `3cb7ce6e99a192baff11626c218df8104219e0d75efb47735727d0f8e3c9af30` |
| Comparaison A2 historique | [#13693078282](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42653720557/artifacts/13693078282) | `3c0ad4bf15abe91403c544653661b2cc8b9b4df87a8d51566743504cabbc0807` |

Sceau externe SHA-256 **sur `manifest.json` brut** : `aaa77eed457f51d28e7eee7d06e17d2457cf3c5fb95ae6bfafabbe2db2202014`. Inventaire : **360/360** membres avec taille et SHA-256, plus manifeste ; aucune ROM ni SNA complète dans le ZIP. Corpus A2 `tests/fixtures/cpc6128/clk_04_a2_numeric/corpus.json` SHA-256 `9c36655e872f0a4d2af423f242c8185dfb7053fa418bf81e4ac608f1b5588d53` ; **11 lots / 37 valeurs différentes / 2 boots / 14 constructions alternatives par boot**. Le rapport historique A2 déclare 74/74 identités REAL5 RAM ; le présent audit **recontrôle** les 5 octets de `window.bin` aux offsets/adresses/type de `stop.json`, indépendamment des lignes `PRINT`.

Pins manifestés : Caprice32 commit `8c778bf072a06fb7c23b9cccd179041db7f79a52`, ROM CPC6128 SHA-256 `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562` et image GHCR `sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c`. L'audit authentifie ces **métadonnées scellées**, pas une nouvelle exécution de la ROM. Le replay de capture A2 et l'inspection PNG sont historiques ; aucun boot CPC ni essai physique CYD n'est exécuté par A7. Les sessions `original`/`repeat` ont des timestamps de démarrage distincts ; leurs **11 fichiers `run/printer.dat` sont respectivement identiques byte à byte**.

## Périmètre des champs observés et résultat différentiel

La source d'autorité PRINT est exclusivement `original|repeat/<lot>/run/printer.dat` dans le RAW. Elle est découpée en **CRLF littéraux `0D0A`**, et chaque ligne est associée à l'expression `PRINT #8` exacte du corpus et à l'adresse de la variable sur le STOP. Les lignes `@A!`/`@E!`… sont des **adresses** à contrôler, non des valeurs à faire formatter. Les octets `window.bin` sont une autre preuve : **jamais utilisés pour reconstruire `cpc_hex`**. Les comparaisons des valeurs et adresses avec le JSON historique sont des vérifications secondaires, pas une génération d'attendu. `LIST #8` et les commandes réellement saisies sont séparés : le CPC réécrit certains littéraux longs lors de LIST.

| Rôle (deux sessions) | Lignes | `C99_CANDIDATE_MATCH` | `C99_UNSUPPORTED` | `C99_CANDIDATE_MISMATCH` |
|---|---:|---:|---:|---:|
| Valeur principale (37 × 2) | **74** | **54** | **20** | **0** |
| Construction alternative (14 × 2) | 28 | 8 | 20 | 0 |
| Sondes CPC égalité et ±1 (3 × 14 × 2) | 84 | 84 | 0 | 0 |
| Adresses `@variable!` (non comparées au formateur) | 102 | — | — | — |
| **Total** | **288** | **146** | **40** | **0** |

Les 186 champs numériques sont comparés **octet à octet au C99 A6 inchangé**, avec signe initial, espace final et `CRLF` inclus. Toutes les sorties acceptées par A6 concordent. Les 40 `UNSUPPORTED` sont des refus explicites de la **couverture A6**, pas des contradictions CPC et jamais des `MATCH` fabriqués. Les 102 adresses sont classées `RAW_CPC_OBSERVED` (avec vérification d'adresse), non promues à la validation du formatage REAL5. L'intégralité des **288 lignes (offset, hex réel, classification, hex candidat si applicable)** est publiée dans [`CLK-04-A7-a2-print-matrix.csv`](CLK-04-A7-a2-print-matrix.csv), générable aussi en JSON local.

## Matrice primaire par valeur — `original` et `repeat` séparés

Les hexadécimaux ci-dessous sont **les octets véritables du `run/printer.dat` original**, non issus de Decimal, du REAL5 RAM ou d'une table de sorties. La session `repeat` a été comparée séparément et partage les mêmes octets pour chaque champ. `M` = `C99_CANDIDATE_MATCH`, `U` = `C99_UNSUPPORTED` ; aucun `C99_CANDIDATE_MISMATCH`.

| Valeur demandée | Tier | PRINT CPC original en hex (signe/espace/CRLF inclus) | original | repeat |
|---:|:---:|---|:---:|:---:|
| 0 | D0 | `2030200D0A` | M | M |
| 1 | D0 | `2031200D0A` | M | M |
| 2 | D0 | `2032200D0A` | M | M |
| 3 | D0 | `2033200D0A` | M | M |
| 7 | D0 | `2037200D0A` | M | M |
| 8 | D0 | `2038200D0A` | M | M |
| 9 | D0 | `2039200D0A` | M | M |
| 127 | D0 | `20313237200D0A` | M | M |
| 128 | D0 | `20313238200D0A` | M | M |
| 129 | D0 | `20313239200D0A` | M | M |
| 255 | D0 | `20323535200D0A` | M | M |
| 256 | D0 | `20323536200D0A` | M | M |
| 257 | D0 | `20323537200D0A` | M | M |
| 5256 | D0 | `2035323536200D0A` | M | M |
| 32767 | D0 | `203332373637200D0A` | M | M |
| 32768 | D0 | `203332373638200D0A` | M | M |
| 32769 | D0 | `203332373639200D0A` | M | M |
| 50375 | D0 | `203530333735200D0A` | M | M |
| 50376 | D0 | `203530333736200D0A` | M | M |
| 50377 | D0 | `203530333737200D0A` | M | M |
| 65535 | D0 | `203635353335200D0A` | M | M |
| 65536 | D0 | `203635353336200D0A` | M | M |
| 65537 | D1 | `203635353337200D0A` | M | M |
| 8388607 | D1 | `2038333838363037200D0A` | U | U |
| 8388608 | D1 | `2038333838363038200D0A` | M | M |
| 8388609 | D1 | `2038333838363039200D0A` | U | U |
| 16777215 | D1 | `203136373737323135200D0A` | U | U |
| 16777216 | D1 | `203136373737323136200D0A` | M | M |
| 16777217 | D1 | `203136373737323137200D0A` | U | U |
| 1073741823 | D1 | `20312E3037333734452B3039200D0A` | U | U |
| 1073741824 | D1 | `20312E3037333734452B3039200D0A` | U | U |
| 1073741825 | D1 | `20312E3037333734452B3039200D0A` | U | U |
| 2147483647 | D1 | `20322E3134373438452B3039200D0A` | U | U |
| 2147483648 | D2 | `20322E3134373438452B3039200D0A` | M | M |
| 2147483649 | D2 | `20322E3134373438452B3039200D0A` | U | U |
| 4294967294 | D2 | `20342E3239343937452B3039200D0A` | U | U |
| 4294967295 | D2 | `20342E3239343937452B3039200D0A` | M | M |

## Interprétation bornée, falsifiabilité et décision A7

Les voisins des seuils sont instructifs : `8388607` et `8388609` entourent le `8388608` déjà couvert en décimal par A6 ; `16777215` et `16777217` entourent `16777216`. Ces **quatre voisins restent `UNSUPPORTED`**, bien que la capture révèle leur représentation décimale. `1073741823`, `1073741824`, `1073741825`, `2147483647`, `2147483649`, `4294967294` ont une forme scientifique à six chiffres significatifs / `E+09` observée mais non prise en charge. Les mêmes caractères visibles peuvent représenter **des valeurs RAM distinctes** (`1073741823`, `1073741824` et `1073741825` donnent `1.07374E+09`) : on ne peut ni inverser `PRINT` pour en déduire l'entier exact, ni en déduire une règle d'arrondi universelle. Le signe positif `20`, l'espace terminal `20` et `0D0A` sont attestés sur ces cas ; aucun nombre négatif autre que les sondes `-1` n'entre dans le corpus uint32.

**Aucune extension C99 proposée.** L'ensemble A2 est probant pour les cas capturés mais insuffisant pour fixer une transition décimal/scientifique universelle, la durée des intervalles, les ex aequo d'arrondi et les comportements sur des entrées absentes du corpus. Étendre vers un intervalle au motif que ses extrémités sont observées serait non falsifié pour ses valeurs internes. En particulier, la répétition de deux boots reproduit les mêmes entrées, pas une preuve d'exhaustivité. La règle décisionnelle reste **`UNSUPPORTED` hors prédicat A6**, avec `RANGE_UNVERIFIED`. Aucune table `valeur → chaîne`, aucun `float`/`double`, aucune allocation dynamique, aucun changement de source C99.

## Reproduction et essais négatifs

À partir de la **branche A7** et des trois ZIP Actions téléchargés indépendamment (ne pas modifier/extraire dans les sources), exécuter :

```sh
python3 -m unittest discover -s tests -p 'test_clk_04_a7_a2_print_audit.py' -v
python3 tools/clk_04_a7_a2_print_audit.py \
  --raw /tmp/a2-13692283699.zip \
  --seal /tmp/a2-13692103933.zip \
  --comparison /tmp/a2-13693078282.zip \
  --corpus tests/fixtures/cpc6128/clk_04_a2_numeric/corpus.json \
  --source tools/clk_04_a4_numeric_lab.c \
  --header tools/clk_04_a4_numeric_lab.h \
  --output /tmp/clk04-a7-matrix --cc gcc
# puis --cc clang : résultat attendu identique
```

L'auditeur rejette avant comparaison : substitution des ZIP (SHA-256 externe), réécriture du manifeste, divergence de l'inventaire 360/360, sceau/HEAD/ROM/Caprice/GHCR/corpus, sessions manquantes ou confondues, source BASIC/ordre des impressions, adresse `@`, offset/type/5 octets RAM, manque/ajout de lignes et CRLF corrompus, ou candidat A6 `.c/.h` dont le **blob SHA Git** n'est plus celui de `main@902f3abe...`. Les tests de falsification exécutés avec des données **HOST_ONLY** ne constituent jamais des observations CPC. La comparaison C99 active `used`/sentinelle et vérifie l'absence de mutation sur `UNSUPPORTED`.

**État des preuves A7 :** `HOST_VERIFIED` pour les tests de l'outil et les compilations hôte GCC/Clang ; `CPC_ORACLE_VERIFIED` uniquement pour la **réutilisation authentifiée des 74 observations A2 historiques** (aucune acquisition nouvelle) ; `ON_DEVICE_NOT_APPLICABLE_A7`. Le C99 A6 `.c/.h` reste bit-identique à la base, donc **A5 FAST** attendu : aucun A5 FULL frais nécessaire. Les CI et le SHA de la PR A7 doivent être appréciés **au HEAD GitHub final** ; un job `SKIPPED` n'est pas un `SUCCESS`. **Aucune modification** de CI-OPT3, des routeurs A4/A5, de `core/`, `firmware/`, des workflows ni du namespace CLK-06-A5 de DEV1 (#401). **Livraison pour revue contradictoire du Pilotage, non auto-approuvée/non fusionnée.**
