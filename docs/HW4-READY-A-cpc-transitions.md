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


## A1 — branchement de la vraie politique de production

Implémentation minimale : \`io/cpc_ready_policy.h\` / \`.c\` définissent \`CpcReadyTransition\`, \`cpc_ready_policy_emit()\`, \`cpc_ready_policy_apply()\` (écriture \`"Ready\n"\` dans le vrai \`CpcText\`) et les libellés de trace. \`hw4_c2_console.c\` choisit explicitement la transition **après le résultat réel** de \`bsr_submit()\`, et après la fin d'un \`basic_run()\` quand \`RUN\` est démarré. Le \`prompt()\` existant n'affiche jamais \`Ready\` ; le boot \`cpc_boot_console()\` reste propriétaire de son propre texte. \`UART_LINE_REJECTED\` passe également par cette politique. Pas de modification de \`core/\`, \`video/cpc_boot.c\`, éditeur E1/E3, HAL LCD/DMA ou anciennes archives.

| Transition de la console | \`Ready\` | Justification |
|---|---|---|
| \`BOOT_ALREADY_PAINTED\` | Non (déjà peint) | Boot A0 |
| \`NUMBERED_STORED\`, \`EMPTY_ENTER\` | Non | A0 lignes numérotées et Enter vide |
| \`LIST_RETURN\`, \`NEW_RETURN\`, \`RUN_RETURN\` | Oui | A0-v2 indépendant |
| \`BASIC_DIAGNOSTIC\` | Oui | Erreur ROM A0-v2 ; texte natif \`ERROR\` préservé, issue #159 hors périmètre |
| \`HOST_REJECTED\` | Oui | Maintien explicite du diagnostic hôte \`ERROR\` + \`Ready\` ; NON CPC |
| \`HOST_CLS\` | Non | Choix hôte explicite : \`!CLS\` efface seulement l'écran, ne réinjecte aucun bandeau ; NON CPC |
| \`HOST_DEMO\` | Oui | Maintien du retour de la démo hôte ; NON CPC |
| \`DIRECT_UNKNOWN\` | Non | Non observé historique ; les entrées réellement refusées prennent \`BASIC_DIAGNOSTIC\` |

\`STOP\` ne devient pas une commande native par cette mission : seule son observation sur le CPC historique est prouvée. Les lignes non numérotées non caractérisées ne sont pas promues par conjecture.

### Tests réellement exécutés avant la fin de la documentation

Sur le commit \`8df45e728112469d5da17b9532e91c36a94c3c6f\`, [CI Linux C99 #40883406368](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40883406368) : GCC/Clang × OFF/ON (ASan/UBSan) **4×92/92 CTest PASS**, y compris \`hw4_ready_a_real_policy_vram_runtime\` et \`j1_15_b_native_string_cpc_partial\` qui teste \`BONJOUR\`. La suite dédiée vérifie deux lignes numérotées, Enter vide, LIST, RUN, NEW, erreur, rejets/diagnostics hôtes, compteur d'émissions de \`Ready\`, prompt conservé, absence de double Ready, rejet des événements invalides, intégrité du programme et scroll MODE 1 en bas d'écran.

[CI Xtensa #40883406335](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40883406335) : ESP-IDF **v5.5.6**, profils **CONSOLE/HW3/BASIC_PROBE : 3/3 PASS** ; \`po-standard-build\` **SKIPPED**, non compté comme PASS. [CI-ARCH #40883406316](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40883406316) PASS. [Oracle CPC permanent #40883406375](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40883406375) PASS. [E2 éditeur #40883406279](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40883406279) 4/4 PASS. [Oracle indépendant #40883406364](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40883406364) PASS. La première CI scrolling sur ce HEAD a échoué **uniquement** sur la garde textuelle préexistante qui exigeait \`return display_ready() && prompt()\` ; les 7 tests fonctionnels de scrolling étaient tous PASS. La garde a été ajustée pour exiger \`return apply_ready_policy(transition) && prompt()\` et interdire l'ancien couplage : [CI scrolling corrigée #40883852326](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40883852326) **PASS**. Cette adaptation d'infrastructure ne modifie aucune fonction de scrolling.

### Budget mémoire — comparaison sur les mêmes trois profils ESP-IDF v5.5.6

Mesures extraites des logs GitHub Actions de \`main@399cdf412b019dcba2ae0c6c0b8c699ebf01812f\` ([run #40878142299](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40878142299)) et de la branche \`8df45e728112469d5da17b9532e91c36a94c3c6f\` ([run #40883406335](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40883406335)). Les valeurs \`BASE\` imprimées par U1-B sont un seuil historique, **pas** le \`main\` actuel ; les deltas ci-dessous sont bien recalculés entre les deux runs :

| Profil | Flash_Code main → A1 (Δ) | IRAM main → A1 (Δ) | DRAM main → A1 (Δ) | Image main → A1 (Δ) |
|---|---|---|---|---|
| CONSOLE | 116426 → 116946 (+520 o) | 67331 → 67331 (0) | 53480 → 53480 (0) | 243809 → 244585 (+776 o) |
| HW3 | 82878 → 82878 (0) | 67279 → 67279 (0) | 31520 → 31520 (0) | inchangée selon diff de sources / profil, taille image exacte non reprise ici |
| BASIC_PROBE | 77542 → 77542 (0) | 51807 → 51807 (0) | 31028 → 31028 (0) | inchangée selon diff de sources / profil, taille image exacte non reprise ici |

Le stockage de chaînes J1.15-C conserve \`CONSOLE_STORAGE_ELF_BSS_BYTES=22668\`, arène 4096 o ; preuve PASS dans les logs Xtensa. Le choix Ready n'alloue aucune mémoire à l'exécution.

## Protocole de validation physique — PO, obligatoire avant revue finale

**Le HEAD à flasher sera le SHA complet du dernier commit de cette PR** (voir Remise GitHub). Une nouvelle modification, même documentaire, invalide toute ancienne preuve \`App version\` et impose un nouveau contrôle SHA/CI. Sur le poste Linux Debian avec ESP-IDF v5.5.6 actif :

\`\`\`bash
git fetch origin feat/hw4-ready-a-cpc-transitions
git switch feat/hw4-ready-a-cpc-transitions
git pull --ff-only origin feat/hw4-ready-a-cpc-transitions
git rev-parse HEAD
cd firmware/esp32_display_probe
idf.py -DLOCO_CYD_PROFILE=CONSOLE build
idf.py -p /dev/ttyUSB0 flash
idf.py -p /dev/ttyUSB0 monitor
\`\`\`

Après le boot dans \`monitor\`, relever \`App version\` et le comparer au préfixe exact du commit testé ; **ne pas valider sur une version différente**. En cas de cache ESP-IDF précédemment configuré pour HW3/BASIC_PROBE, utiliser un build CONSOLE propre/isolé avant de flasher ; ne pas associer des profils contradictoires.

Faire saisir successivement : \`10 PRINT 2\` → \`20 END\` → Enter vide → \`LIST\` → \`RUN\` → \`NEW\` → \`GOTO 999\` (ou autre diagnostic hôte si la commande n'est pas reconnue) → \`!CLS\`. Puis tester le rejet d'une entrée UART incomplète/overflow si possible. Noter **PASS/FAIL pour chaque étape**, compter les \`Ready\` et relever la ligne/colonne de reprise, à comparer à la matrice CPC A0-v2 ; ignorer le texte exact \`Line does not exist\` tant que #159 reste ouvert. Vérifier un \`Ready\` unique au démarrage, aucun à l'Enter vide ni après les lignes numérotées, un après LIST/RUN/NEW/diagnostic, aucun après \`!CLS\`.

Fournir au Pilotage des **photos/constats visuels** du boot, de chaque transition et de la reprise curseur, les **traces UART \`HW4-READY-A READY_POLICY\`** (événement + \`emitted=0/1\` + ligne/colonne), \`App version\`, \`DEVICE_MEMORY\` avant et après, métriques DMA/LCD (\`dma_fault=0\`, \`dma_timeouts=0\`, \`lcd_error=ESP_OK\` si exposées), absence de panic, ghosting et double Ready. Pour la démo hôte \`!DEMO\` : facultatif en complément, sans la classer CPC. Faire confirmer \`ON_DEVICE_PO_REPORTED_PASS\` seulement avec SHA, photo/log et tableau PASS/FAIL. Tant que le PO n'a pas fourni ces preuves : **ON_DEVICE_UNVERIFIED — PR NON FUSIONNÉE**.
