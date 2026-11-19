# CLK-04-A6 — Audit borné PRINT REAL5 / laboratoire C99 (DEV2)

**GO Pilotage :** [issue #398](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/398), rattachement [#312](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/312). **Branche :** `lab/clk-04-a6-real5-print`, base initiale `main@09036faf4b64e2b281d3d961ff5f48b389c75985`. Strictement LAB C99, pas de CORE/TIME/firmware/émulation/native Xtensa. Toutes les données historiques restent attribuées au **HEAD A5 original** `3fab7321653916c4838314a72ee99d26218ff5e9`, **jamais au HEAD A6**.

## Authentification indépendante des acquisitions A5 (avant le patch)

- [Run A5 authentique #44520635627](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44520635627), [artefact RAW #14528866213](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44520635627/artifacts/14528866213), [sceau #14528911175](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44520635627/artifacts/14528911175) et [comparaison C99 historique #14528701716](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44520635627/artifacts/14528701716).
- ZIP RAW original 372158 octets, SHA-256 `32f46a15e9f7906f083f6d8a634f6f214313725cb3a2e53967153e582b52f967`. ZIP sceau original 321 octets, SHA-256 `c3eeaeb273b33c37a2506d10acc93e74b5d217fa9304daac86b122e58e6f323e` ; ZIP comparaison originale 1758 octets, SHA-256 `362803a1cb9e9f55f6e28b8ea4c3e5b71a25bac8140f685b68dd7ff26b0d68cb`.
- Sceau externe (hors RAW) : `mission=CLK-04-A5`, `head=3fab7321653916c4838314a72ee99d26218ff5e9`, `manifest_sha256=e6af41ce2e6fcccee1446216bb5f9a1a44e5d21cf9a39f966cbf2d3943ae6b1a`. SHA256 recalculé **sur les octets du `manifest.json`** et identique. **270/270 fichiers** inventoriés RAW avec tailles et SHA256 vérifiés (271 entrées dont manifeste) ; aucune ROM/SNA archivée ; ROM CPC6128, Caprice32 et image GHCR correctement épinglés dans le manifeste.
- Le rapport C99 historique contient 16/16 `input_status=CANDIDATE_MATCH` et 16/16 `product_status=CANDIDATE_MATCH` sur les REAL5 T!/U! **RAM distinctes** ; ce sont des témoins indépendants du PRINT. Les sorties imprimante `run/printer.dat` ont été relues directement, pas reconstituées depuis `Decimal`/JSON ; chaque paire `original`/`repeat` est strictement identique. Aucune donnée de capture n'est reconstruite par le formateur.
- **« Six UNSUPPORTED » = 6 cellules distinctes P06–P08 × (T,U), répétées dans deux sessions, donc 12 occurrences effectives sur 32 cellules PRINT.** Historique : 20 `CANDIDATE_MATCH` + 12 `UNSUPPORTED`, aucune divergence mesurée. Ne pas confondre 6 cellules et 6 valeurs CPC différentes par session.

## Matrice authenticité + comparaison octet-exacte, **8 valeurs × 2 sessions**

Les hexadécimaux ci-dessous **incluent** l'espace initial de signe positif `20`, l'espace final `20`, et la terminaison `0D0A`. Toutes les lignes sont des **octets imprimante ROM CPC observés** (sélection de la ligne PRINT T! ou U!, pas d'adresse `@`). `A5` est la classification historique, non réécrite ; `A6` est la comparaison actuelle du candidat C99 après authentification, **non une nouvelle observation CPC**.

| Session | Cas | T! demandé | Champ | Hex CPC `run/printer.dat` | A5 historique | A6 C99 (local) |
| --- | --- | ---: | --- | --- | --- | --- |
| original | P01 | 0 | `print_t` | `2030200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| original | P01 | 0 | `print_u` | `2030200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| original | P02 | 1 | `print_t` | `2031200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| original | P02 | 1 | `print_u` | `2032200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| original | P03 | 32767 | `print_t` | `203332373637200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| original | P03 | 32767 | `print_u` | `203635353334200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| original | P04 | 32768 | `print_t` | `203332373638200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| original | P04 | 32768 | `print_u` | `203635353336200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| original | P05 | 65536 | `print_t` | `203635353336200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| original | P05 | 65536 | `print_u` | `20313331303732200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| original | P06 | 8388608 | `print_t` | `2038333838363038200D0A` | `UNSUPPORTED` | `CANDIDATE_MATCH` |
| original | P06 | 8388608 | `print_u` | `203136373737323136200D0A` | `UNSUPPORTED` | `CANDIDATE_MATCH` |
| original | P07 | 2147483648 | `print_t` | `20322E3134373438452B3039200D0A` | `UNSUPPORTED` | `CANDIDATE_MATCH` |
| original | P07 | 2147483648 | `print_u` | `20342E3239343937452B3039200D0A` | `UNSUPPORTED` | `CANDIDATE_MATCH` |
| original | P08 | 4294967295 | `print_t` | `20342E3239343937452B3039200D0A` | `UNSUPPORTED` | `CANDIDATE_MATCH` |
| original | P08 | 4294967295 | `print_u` | `20382E3538393933452B3039200D0A` | `UNSUPPORTED` | `CANDIDATE_MATCH` |
| repeat | P01 | 0 | `print_t` | `2030200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| repeat | P01 | 0 | `print_u` | `2030200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| repeat | P02 | 1 | `print_t` | `2031200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| repeat | P02 | 1 | `print_u` | `2032200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| repeat | P03 | 32767 | `print_t` | `203332373637200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| repeat | P03 | 32767 | `print_u` | `203635353334200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| repeat | P04 | 32768 | `print_t` | `203332373638200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| repeat | P04 | 32768 | `print_u` | `203635353336200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| repeat | P05 | 65536 | `print_t` | `203635353336200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| repeat | P05 | 65536 | `print_u` | `20313331303732200D0A` | `CANDIDATE_MATCH` | `CANDIDATE_MATCH` |
| repeat | P06 | 8388608 | `print_t` | `2038333838363038200D0A` | `UNSUPPORTED` | `CANDIDATE_MATCH` |
| repeat | P06 | 8388608 | `print_u` | `203136373737323136200D0A` | `UNSUPPORTED` | `CANDIDATE_MATCH` |
| repeat | P07 | 2147483648 | `print_t` | `20322E3134373438452B3039200D0A` | `UNSUPPORTED` | `CANDIDATE_MATCH` |
| repeat | P07 | 2147483648 | `print_u` | `20342E3239343937452B3039200D0A` | `UNSUPPORTED` | `CANDIDATE_MATCH` |
| repeat | P08 | 4294967295 | `print_t` | `20342E3239343937452B3039200D0A` | `UNSUPPORTED` | `CANDIDATE_MATCH` |
| repeat | P08 | 4294967295 | `print_u` | `20382E3538393933452B3039200D0A` | `UNSUPPORTED` | `CANDIDATE_MATCH` |

**Rejeu indépendant local A6 :** compilation GCC C99 stricte d'un candidat en `.so`, comparaison directe des octets émis par `a4_print_candidate` avec `run/printer.dat` pour chacun des 32 champs : **32/32 identiques** ; les 16/16 états RAM originaux restent des attestations inchangées du rapport A5 (ils ne sont pas recalculés par le formateur). Tests C99 fonctionnels exécutés sur GCC/Clang `-O2` et `-O1 -g -fsanitize=address,undefined` ; ces tests sont **HOST_VERIFIED**, non une acquisition CPC du HEAD A6.

## Règle de formatage déduite et limitation du domaine

**Ancienne couverture conservée** : entier signé `-1..999999` ; espace initial pour les positifs, `-` pour -1, chiffres décimaux, espace final et `CRLF`. 

**Extension bornée par les échantillons A5 attestés :**
- Forme décimale complète pour les deux puissances de 2 attestées `2^23` (`8388608`) et `2^24` (`16777216`). L'ancien domaine `-1..999999` n'est pas élargi arbitrairement aux valeurs intermédiaires non mesurées.
- Forme exponentielle **sur les quatre nombres issus de la construction A5** : `2^31`, `2^32`, `UINT32_MAX`, `2*UINT32_MAX`. Les octets CPC attestent une mantisse à 6 chiffres significatifs, `E+09`, et la même politique d'espaces/CRLF. Le candidat réalise une division décimale entière avec arrondi au plus proche pour ces échantillons ; aucun flottant (`float`/`double`) ni allocation dynamique ; aucune table `valeur -> octets imprimés`. Les valeurs éligibles sont gardées par un **prédicat de couverture** (pas une table de sorties).
- Observations d'arrondi : `2^31` → `2.14748E+09`, `2^32` et `UINT32_MAX` → `4.29497E+09`, `2*UINT32_MAX` → `8.58993E+09`. Il existe à la fois une diminution et une augmentation du dernier chiffre affiché. **Aucun cas à demi-unité n'est prouvé**, et aucune politique CPC pour les tie-breaks, nombres négatifs étendus, exposants différents, ni transition exacte décimal/scientifique n'est déduite. Le seuil réel est uniquement **encadré entre 16777216 (décimal) et 2147483648 (exponentiel)**. Toute valeur intermédiaire hors des classes attestées renvoie `A4_UNSUPPORTED`.
- **Atomicité** : `A4_UNSUPPORTED`, `A4_INVALID` et `A4_NO_SPACE` ne modifient ni les octets destination ni `*used`; la taille exacte est acceptée sans NUL terminal. Tests négatifs sur puissances voisines, voisins d'arrondi/seuil, intervalle inconnu, signe, `E+09`, espaces, `CRLF`, capacité insuffisante et `INT64_MIN/MAX`.

## Limites, CI et admission

**Classification séparée :** `OBSERVED` = seules sorties ROM authentifiées sur ces 8 valeurs × 2 sessions ; `CANDIDATE_MATCH` = concordance byte-exacte **hôte** pour 32 cellules PRINT, et 16/16 RAM authentiques inchangées ; `UNSUPPORTED` = toute entrée hors couverture explicitement justifiée ; `INCONCLUSIVE` = tout cas nouveau hors corpus sans oracle frais. Cela n'est ni un formateur CPC général ni une validation native de `TIME`.

L'ancien manifeste A5 et son rapport de comparaison sont **immuables** ; les anciennes 12 occurrences `UNSUPPORTED` restent 12 occurrences dans le rapport historique. Une nouvelle comparaison A5 sur HEAD A6 sera une preuve indépendante, avec son propre sceau et identité HEAD si le workflow permet un **A5 FULL**. Selon le routeur existant `tools/ci/clk_04_a4_fast_route.py`, la seule modification du candidat C99 entraîne normalement **A5 FAST** pour les pull requests, car elle ne modifie ni corpus/acquéreur ni la recette de capture. **Un A5 FAST ne prouve pas une acquisition/rejeu CPC du HEAD A6.** Si `workflow_dispatch` FULL ne peut être déclenché dans les outils autorisés, **STOP sur admission finale et arbitrage Pilotage, sans changer les workflows/routeurs partagés ou réétiqueter le HEAD historique**.

La PR #397 de DEV1, CI-ARCH, CI-OPT3, les workflows, le collecteur A5 et les RAW/sceaux A4/A5 sont en **lecture seule**. Pas de `core/`, `firmware/`, `integration/`, `TIME`, Xtensa productif, ROM ou Caprice32 modifiés. **CYD : `ON_DEVICE_NOT_APPLICABLE_A6`**. Décision d'acceptation et de fusion réservée au Pilotage.