# HW4-READY-A — Observations CPC6128 de `Ready` et politique de console

Issue [#151](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/151), PR [#161](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/161).
Base réelle vérifiée : `main@399cdf412b019dcba2ae0c6c0b8c699ebf01812f`, post-fusion de la PR REAL5 #158. A0 réalisé **avant** toute modification de la politique de production.

## A0 — ROM, outil et sessions indépendantes

- [Workflow A0-v2 #40882225719](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40882225719), checkout de capture `8605e54fbfc8ae1e86d68cf5b26bddf2b504b386`.
- Caprice32 `8c778bf072a06fb7c23b9cccd179041db7f79a52`, version observée `Caprice32 v4.6.0` ; ROM CPC6128/BASIC 1.1 SHA-256 `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562`.
- Conteneur GHCR à digest fixe `sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c`. Deux processus indépendants, depuis le démarrage original de chaque cas ; modèle 2, RAM 128 KiB. Conditions exactes et arguments de saisie dans `autocmd.json` + `cap32.cfg`.
- **20/20 PNG authentiques, dix paires d'images bit-à-bit identiques** ; 768×540 px. Captures, logs, manifestes et SHA-256 archivés dans `tests/fixtures/cpc6128/hw4_ready_a_v2/`. Les fichiers `tests/fixtures/cpc6128/hw4_ready_a/` restent la **première acquisition préliminaire**, non utilisable pour le curseur : la macro de capture contenait deux espaces hôtes tapés dans l'invite. Corrigé dans A0-v2 par juxtaposition des commandes CAP32, sans caractère de saisie parasite. Les archives J0/J1 et REAL5 n'ont pas été modifiées.
- Les captures sont des sorties **vidéo originales**, jamais le résultat d'un décodeur C99 ou d'une imprimante #8. Les nombres d'occurrences sont des constats visuels directs ; les coordonnées de curseur sont celles du bloc jaune solide de 16×16 pixels. La marge émulateur est comprise dans les coordonnées : elles sont données en pixels de PNG, pas en coordonnées E2 CYD.

## A0 — matrice effectivement observée

| Cas | Saisies exactes après boot | Occurrences totales de `Ready` | Curseur final (x,y PNG) | Statut | SHA-256 PNG original |
|---|---|---|---|---|---|
| `00_boot` | `(boot)` | 1 (boot) | 64,226 | OBSERVÉ | `44dd5c29d2278251ac244dd703fc205009728631c7965451f5c3e770cb8495b7` |
| `01_numbered_10` | `10 PRINT 2` | 1 (boot seul) | 64,242 | OBSERVÉ | `888cc0a3fc452b046fb32b3b35b3a0d64001adc0f86419199612df7ae7137bd8` |
| `02_numbered_20` | `10 PRINT 2 → 20 END` | 1 (boot seul) | 64,258 | OBSERVÉ | `3c820e99ce34ac907d1d3a8a2276001d9ec13a11c8fa669cc71b414e92373b57` |
| `03_empty_enter` | `10 PRINT 2 → 20 END → ` | 1 (boot seul) | 64,274 | OBSERVÉ | `dc351b8febe3d664b7376bd97497b97c5d7957dbd31cf36b909bf6f7679ef488` |
| `04_list` | `10 PRINT 2 → 20 END → LIST` | 2 (boot + LIST) | 64,322 | OBSERVÉ | `c27700573576eb91fae822c44c5c89b98317394730dac39c6f711f461b9169db` |
| `05_new` | `10 PRINT 2 → 20 END → NEW` | 2 (boot + NEW) | 64,290 | OBSERVÉ | `082ce1cb64bf854899ad20494c568c980fefc8dfc4d42f857d136b62ffa935ba` |
| `06_run_normal` | `10 PRINT 2 → 20 END → RUN` | 2 (boot + RUN) | 64,306 | OBSERVÉ | `ba89e2acdfdbce6d4d3b3687370b54abf1ebf1ca725cae7c0268721caff2bd83` |
| `07_stop` | `10 PRINT 2 → 20 STOP → RUN` | 2 (boot + Break) | 64,322 | OBSERVÉ CPC ; support natif NON TESTÉ | `ceca9c385a2574b37ff9730e1ad01677c29e8dbd90d60d96a0de3d9e969fc8e0` |
| `08_error` | `10 PRINT 2 → 20 END → GOTO 999` | 2 (boot + erreur) | 64,306 | OBSERVÉ CPC ; texte natif #159 exclu | `8148419764a3b71c0182b9917d9e2a9bb2dfc4823a6be2fd8b5c1a2944bc1e4a` |
| `09_run_new` | `10 PRINT 2 → 20 END → RUN → NEW` | 3 (boot + RUN + NEW) | 64,338 | OBSERVÉ | `3a59cbbab44dd43761f42f93328fc6b83630e007ebe2d13b5e6748455f55b26c` |

**Lecture des transitions :** l'ajout des deux lignes numérotées et Enter vide **n'ajoutent pas** de `Ready` ; le curseur reprend à la colonne gauche sur la ligne suivante. `LIST`, `NEW`, `RUN` normal, `STOP` et l'erreur CPC déclenchent chacun un `Ready` terminal unique, puis la reprise du curseur colonne 1 à la ligne suivante. Le cas `RUN → NEW` montre deux retours successifs, sans duplication supplémentaire. À `RUN`, la capture contient la valeur numérique `2`. À `STOP`, la ROM montre `Break in 20`. À `GOTO 999`, la ROM montre `Line does not exist` **(exactitude de ce texte hors mission #159)**.

**Limites :** l'émulateur est ROM-backed, pas un CPC physique. Le prompt jaune fixe capturé n'établit pas une chronologie de clignotement. Le comportement des commandes directes non listées, des erreurs internes non reproduites, de `STOP` sur moteur natif et d'une erreur sur ligne numérotée n'est **PAS TESTÉ** ici. `!CLS` et `!DEMO` sont **NON SUPPORTÉS par le CPC**, diagnostics propres à l'hôte CYD. Aucun statut d'oracle ne sera assigné à ces diagnostics.

## ROM — indice séparé des observations

`basic.asm` : `&C081` choisit l'affichage de la chaîne `Ready\n` à `&C0D7`, `&C087` reprend la saisie, et `&C0CB` boucle vers `&C087` pour les lignes numérotées. Ces éléments **expliquent** les images sans les remplacer : les verdicts de la matrice proviennent exclusivement des PNG A0-v2.

## A1 — périmètre limité autorisé par A0

La politique sera déterministe, sans temporisation et sans allocation ; elle choisira `Ready` pour les transitions **observées** de retour `LIST`, `NEW`, `RUN` et de diagnostic, et l'omettra après ligne numérotée/entrée vide. Le `Ready` initial reste la propriété de `video/cpc_boot.c`. Les diagnostics hôtes auront une classification autonome explicitement nommée. `STOP` historique n'autorise aucune extension du moteur BASIC.

**Barrière de livraison :** A1 doit encore être vérifiée en C99 GCC/Clang et ASan/UBSan, oracle permanent, CI architecture, Xtensa CONSOLE/HW3/BASIC_PROBE et CYD sur SHA final du PO. Sans ces preuves, ne pas conclure à une acceptation.
