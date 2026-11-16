# CLK-06-A1 — Oracle CPC6128 indépendant `AFTER` / `REMAIN(0)`

**Mandat exclusivement oracle PC :** [#314, GO Pilotage du 13 novembre 2026](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/314#issuecomment-6851391655). **Base exacte** : `main@4f8264c5b1fd370c185d687f5e03e92fe4c8f1e2`, vérifiée sur GitHub avant branchement. **Branche** : `oracle/clk-06-a1-after-remain` ; les chantiers HW4-MEM-C8-A (#380), BASIC natif et firmware CYD sont strictement hors périmètre. Le Développeur ne fusionne pas.

## État de preuve initial (ne pas confondre préparation et observations)

L'existence du programme BASIC, la reconnaissance statique d'un token dans `basic.asm`, un test hôte avec PNG synthétique et une commande Caprice32 configurée **NE démontrent PAS** le comportement du CPC6128. Les qualifications `OBSERVED` exigent des processus CPC ROM-backed effectivement exécutés, deux sessions indépendantes, des archives intègres et une inspection des écrans. Tant que ces éléments manquent, la case reste `UNVERIFIED` ou `INCONCLUSIVE`, **jamais `CPC_ORACLE_VERIFIED` par anticipation**.

**Références CLK-03 lues, non modifiées :** `docs/CLK-03-cpc-time-oracle.md`, `tools/clk_03_cpc_time.py`, son sous-module `tests/oracles/caprice32`, son parseur de RAM SNA et ses fonctions de configuration, exécution `xvfb-run`, contrôle de vitesse et vérification des PNG. Épingles héritées **à revérifier au runtime** : Caprice32 commit `8c778bf072a06fb7c23b9cccd179041db7f79a52`, ROM CPC6128 `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562`, image GHCR `ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c` ; binaire `/usr/local/bin/cap32` SHA-256 `5170b3fc68ab116e7698e6e68a742e324d0e9dbfd87eeb7b2090e13c639f73eb` observé au premier essai réel du workflow #43836366998. Ces valeurs sont un **contrat de provenance**, pas une déclaration qu'une acquisition A1 a déjà été exécutée.

La référence ROM `basic.asm` a été inspectée : la routine `AFTER` à `&CA22` prépare un ticker par `KL ADD TICKER` (`&BCE9`) ; `REMAIN` à `&CA50` utilise `KL DEL TICKER` (`&BCEC`), avec validation de canal à `&CA62` ; tokens `AFTER=&80`, `REMAIN=FF 13`, `GOSUB=&9F`, `RETURN=&C9` (ce dernier corrigé après examen des octets RAM acquis à la première tentative). Ce sont des **indices de ROM statiques**, non une preuve de cadence, d'ordre d'exécution ou de valeur de retour à l'écran. Aucun `TIME` **natif** n'est ajouté ; le garde d'émulation CLK-03 observe `TIME` CPC seulement pour détecter une vitesse hôte incohérente. Aucune fréquence 1/50 s n'est présupposée.

## Huit expériences BASIC distinctes, finies et ré-acquérables

Sources ASCII exactes : `tests/fixtures/cpc6128/clk_06_a1_after_remain/sources/*.bas`. Un manifeste JSON fixe l'ordre et les fenêtres de capture **sans contenir de sortie attendue** : `tests/fixtures/cpc6128/clk_06_a1_after_remain/corpus.json`, SHA-256 `4f1120f76ff52f9cab67a83da82623a6e6fd23711db432eec3622a38c187d443`. L'outil vérifie aussi l'égalité octet-pour-octet de chaque fichier `.bas` et de son tableau `lines`.

| Sonde | Question historique à observer, sans verdict anticipé | État avant acquisition |
|---|---|---|
| `A01_NEVER_ARMED` | `REMAIN(0)` avant tout armement et après une boucle bornée | `UNVERIFIED` |
| `A02_ARM_FIRE` | `AFTER 10,0 GOSUB` ; événement et `RETURN` puis continuité du main | `UNVERIFIED` |
| `A03_ONESHOT` | `AFTER 1,0 GOSUB` : absence ou présence de livraisons multiples pendant une boucle longue mais finie | `UNVERIFIED` |
| `A04_CANCEL_EARLY` | `REMAIN(0)` aussitôt après `AFTER 250,0` ; annulation/délai retourné, puis handler éventuel | `UNVERIFIED` |
| `A05_REMAIN_AFTER_FIRE` | `REMAIN(0)` après fenêtre d'exécution d'un timer court | `UNVERIFIED` |
| `A06_REARM_SAME_CHANNEL` | Deux `AFTER` successifs sur le canal 0 vers deux handlers distincts | `UNVERIFIED` |
| `A07_NESTED_RETURN` | Handler du timer avec `GOSUB` imbriqué, deux `RETURN`, puis marqueur du main | `UNVERIFIED` |
| `A08_BAD_ARGUMENT` | `AFTER -1,0` : diagnostic **réel** à relever sur capture écran, sans présumer de l'erreur | `UNVERIFIED` |

Chaque programme se termine par `END` ou une sous-routine `RETURN` ; tous les `FOR ... NEXT` ont une borne fixe. La longueur des fenêtres d'automatisation `CAP32_DELAY` est fixée avant capture, non convertie artificiellement en ticks CPC ; un `RUN` interrompu/non terminé doit être déclaré `INCONCLUSIVE`, jamais comptabilisé dans 8 cas qualifiés. L'état de `ERR/ERL` reste `UNVERIFIED` tant qu'il n'a pas été réellement acquis.

## Acquisition en deux sessions CPC fraîches

La session `original` et la session `repeat` exécutent chacune **un boot indépendant**, deux gardes de vitesse `TIME` host/CPC empruntés à CLK-03, puis les huit cas. **Chaque sonde** lance **deux processus Caprice32 distincts** : `list` pour saisir le programme, acquérir `LIST` à l'écran, `LIST #8` dans `printer.dat`, une SNA **temporaire** et le `program.bin` réellement extrait de RAM ; `run` pour saisir à nouveau le même programme, `RUN`, capturer l'écran final et le flux brut de l'imprimante. Des commandes et temps de début/fin de chaque processus sont enregistrés. Aucune SNA complète ni ROM n'est archivée. Il n'y a ni exécuteur BASIC local, ni génération d'une réponse attendue depuis Python.

```bash
# Préflight hôte : aucune preuve CPC ne sort de ces commandes.
python3 tools/clk_06_a1_oracle.py --check-sources
python3 tools/clk_06_a1_oracle.py --self-test
python3 -m unittest discover -s tests -p 'test_clk_06_a1_oracle.py' -v

# À exécuter UNIQUEMENT dans la chaîne Caprice32/ROM épinglée et
# sur un checkout propre du HEAD exact (ou workflow isolé de cette PR) :
python3 tools/clk_06_a1_oracle.py --acquire \
  --caprice tests/oracles/caprice32 \
  --output /chemin/ABSENT/clk06-a1-raw \
  --head "$(git rev-parse HEAD)"
sha256sum /chemin/ABSENT/clk06-a1-raw/manifest.json
# Sceau EXTERNE obligatoire, publié dans logs GitHub acquisition et artefact séparé :
python3 tools/clk_06_a1_oracle.py --verify /chemin/ABSENT/clk06-a1-raw \
  --head "$(git rev-parse HEAD)" --seal SHA256_DU_MANIFEST_PUBLIE_HORS_ARCHIVE
```

L'acquisition CI est proposée dans le workflow isolé `.github/workflows/clk-06-a1-acquisition.yml` (déclencheurs limités à ses cinq routes). Elle échoue **sans** commit Caprice32 correct, sans ROM exacte, sans binaire Caprice disponible, sans corpus conforme, sans snapshot RAM exploitable, sans PNG intègre ou sans copie complète des seize processus. Les fichiers partiels sont conservés avec `status=ACQUISITION_PARTIAL`, **pas un PASS**. La publication externe du SHA manifeste est indépendante de l'archive téléchargée par un second job et liée au HEAD de la PR. Le coffre d'artefacts de GitHub Actions est provisoire (rétention 90 jours) : sa présence n'est pas un scellement permanent en dépôt.

## Replay, falsifications et limites strictes

Le vérificateur exige un `--head` 40 hex, un **sceau SHA-256 externe** 64 hex et leur accord avec le manifeste. Il exige le corpus fixe, la chaîne Caprice32/ROM/GHCR épinglée, deux sessions fraîches, 8 × 2 pièces LIST+RUN, fichiers d'automatisation et config, timestamps de processus distincts, logs `returncode=0`, les 16 `program.bin` et leurs tokens CPC issus de SNA, les listes réelles `LIST #8`, les fichiers imprimante RUN, PNG structurellement complets (chunks CRC et flux zlib) et l'inventaire intégral taille+SHA-256. Il refuse les sources mutées, observations auto-déclarées comme écran déjà interprété, absence ou ajout de fichier, insertion `.sna`/`.rom`, mauvais HEAD, manifeste/signature modifiés et paramètres de provenance incorrects. Les **fixtures falsifiées des tests unitaires sont exclusivement temporaires et marquées synthétiques**, jamais archivées comme sessions Caprice32.

**Frontière résiduelle :** un en-tête PNG et une archive correctement hachée ne prouvent pas que l'écran affiche le programme attendu ; le contrôle visuel des `boot/list/run` (BASIC 1.1, `LIST`, erreurs, `Ready` final), les valeurs affichées et l'ordre exact des messages restent indispensables. `RAW_REPLAY_PASS` n'est pas le verdict sémantique `CPC_ORACLE_VERIFIED`. Une sonde absente, non interprétable ou en cours d'exécution = `INCONCLUSIVE` ou `UNVERIFIED`. Ni type numérique ni cadence timer ne seront extrapolés des nombres imprimés sans expériences supplémentaires.

## CI, conflits et remise

Les workflows historiques, `tools/clk_03_cpc_time.py`, les sceaux CPC, `core/`, `firmware/`, `integration/`, `video/`, `hal/`, `io/`, CMake et tous les scripts de RAM/IRAM sont **inchangés**. `HW4-MEM-C8-A` n'est ni lu ni modifié. **Point de décision CI :** le routeur `CI-OPT3` possède une liste fermée de workflows. Le GO A1 autorise un workflow isolé additif, mais l'enregistrement de ce nouveau workflow dans le routeur partagé `tools/ci/opt3_routing.py` est une modification commune nécessitant un arbitrage Pilotage si le gate la refuse. Ne pas élargir soi-même le routeur ni toucher à un workflow historique. En cas de CI-OPT3 rouge, **noter le blocage, ne pas prétendre la CI verte**.

**Qualification finale à compléter seulement avec les vrais artefacts acquis :** URL du run sur HEAD, SHA externe, inventaire, vérification séparée, inspection humaine des PNG, table des octets d'imprimante originaux/repeat et conclusion distincte pour chaque cas. Tout élément non acquis reste `UNVERIFIED`. **Oracle PC uniquement : `ON_DEVICE_NOT_APPLICABLE_A1` ; aucun test CYD ni passage à CLK-06-A2/CLK-07.**

### Première acquisition réelle partielle — preuve de falsification négative

[Workflow #43836366998](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/43836366998) : Caprice32, ROM et binaire GHCR ont passé les vérifications, et le collecteur a capturé des octets `program.bin` et des sorties `printer.dat` originaux. L’acquisition s’est interrompue **avant 8 × 2** avec `CPC_RAM_TOKEN_MISSING_RETURN` : un contrôle local avait confondu le token `RETURN=&C9` avec `&1D` présent dans un message d’erreur ROM. L’artefact partiel [#14210788068](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/43836366998/artifacts/14210788068) reste non qualifié. Les vrais octets de la ligne 1020 du `program.bin` A02 finissent par `C9 00`, confirmant le token à vérifier ; la première ligne `REMAIN(0)` de A01 contient `FF 13`. Aucune conclusion globale du timer n’est tirée de cette tentative. Les vérifications ont été renforcées avec la véritable empreinte du binaire du conteneur.

## Acquisition CPC indépendante du 16 novembre 2026 — observations effectivement inspectées

**Ce tableau qualifié prévaut sur les états « avant acquisition » de la matrice préparatoire, pour ces seules exécutions.** Le [run GitHub Actions #43837046769](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/43837046769) a achevé trois jobs **SUCCESS** (11 tests hôte, acquisition ROM-backed, rejeu indépendant dans un autre job). HEAD d'acquisition exact : `e7510944edbdbe2438d0209e5ae695f9ed1e5ec7`.

**Copie permanente neuve en dépôt (aucun ancien sceau modifié)** : `tests/fixtures/cpc6128/clk_06_a1_after_remain/evidence/run-43837046769-e751-raw.zip` (290 306 octets, SHA-256 `d672ac02f20a27df514a616bf1ed65d9769781a7fcfad8217a9866a64de67981`) et `evidence/run-43837046769-e751-external-seal.json` (sceau initialement publié hors ZIP dans le log du job d’acquisition). L’archive enregistrée contient les 206 pièces d’observation plus le manifeste, et **aucun fichier ROM ou SNA complet**. Les preuves référencent toujours le HEAD expérimental `e751…`, qui ne sera pas artificiellement réécrit au nouveau HEAD documentaire.

**Pièces brutes authentifiées** : [archive RAW #14211733565](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/43837046769/artifacts/14211733565), ZIP SHA-256 `d672ac02f20a27df514a616bf1ed65d9769781a7fcfad8217a9866a64de67981` ; [sceau externe #14212865137](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/43837046769/artifacts/14212865137), ZIP SHA-256 `bd88ab0c1e710a4f5352d15a57f27d912daa57bfb6d2c62bd513e1b4ff577dce`. **SHA-256 externe du manifeste, identique au SHA recalculé localement :** `6a3b880d33f67ef03f244615353205de8a828e6dbbbf663f27bc04adc8288319`. Relecture indépendante locale : ZIP valide, **207 fichiers**, manifeste + **206/206 pièces** avec tailles et SHA-256 exacts. Aucune ROM ni SNA complète archivée ; tous les `program.bin` proviennent de captures RAM/SNA temporaires et sont vérifiés par le rejeu. Les 16 LIST écran, 16 LIST imprimante, 16 RAM et 16 RUN écran/imprimante sont présents ; les huit programmes ont les mêmes octets `LIST`, `program.bin` et `printer.dat` entre les deux sessions indépendantes.

**Chaîne vérifiée pendant l'exécution** : Caprice32 version `v4.6.0-8c778bf…`, commit `8c778bf072a06fb7c23b9cccd179041db7f79a52`, binaire SHA `5170b3fc68ab116e7698e6e68a742e324d0e9dbfd87eeb7b2090e13c639f73eb`, ROM CPC6128 SHA `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562`, image GHCR à digest inchangé. J'ai ouvert les boot PNG des deux sessions : **« Amstrad 128K Microcomputer », « BASIC 1.1 », « Ready »**. J'ai également inspecté manuellement les 16 PNG LIST et les 16 PNG RUN. Les programmes normaux se terminent sur `Ready`; A08 affiche l'erreur décrite ci-dessous. Les gardes de cadence CLK-03 (lecture de **TIME CPC**, pas mesure du timer AFTER) sont `300.38811720582254` et `300.362248414765` ticks par seconde hôte pour les sessions `original` et `repeat`. **Aucune fréquence AFTER (notamment 1/50 s) n'est déduite de ces chiffres.**

### Résultats CPC strictement bornés aux programmes finis

Dans chaque ligne du tableau, les octets `printer.dat` de `original` et `repeat` sont **identiques** ; les espaces de mise en forme numérique sont simplifiés ci-dessous pour la lecture, les originaux intacts restant dans les archives. Les sorties sont indiquées dans l'ordre de capture.

| Sonde | Sortie imprimante observée dans les deux sessions | Classification et conclusion limitée |
|---|---|---|
| `A01_NEVER_ARMED` | `A01:BEGIN`; `A01:R0= 0`; `A01:R1= 0` | **OBSERVED** : deux lectures `REMAIN(0)` valent zéro sans armement dans cette fenêtre |
| `A02_ARM_FIRE` | `A02:BEGIN`; `A02:HANDLER= 1`; `A02:COUNT= 1` | **OBSERVED** : handler livré une fois, `RETURN` suivi de la reprise du flot principal |
| `A03_ONESHOT` | `A03:BEGIN`; `A03:HIT= 1`; `A03:COUNT= 1` | **OBSERVED** : une seule livraison pendant les 7 500 tours de la boucle bornée, pas une preuve de cadence universelle |
| `A04_CANCEL_EARLY` | `A04:CANCEL= 250`; `A04:COUNT= 0`; `A04:R2= 0` | **OBSERVED** : `REMAIN(0)` immédiatement après `AFTER 250,0` a retourné 250 ; aucun handler servi avant `END`; seconde lecture zéro. L'unité/durée de 250 n'est pas déduite |
| `A05_REMAIN_AFTER_FIRE` | `A05:HIT= 1`; `A05:R= 0`; `A05:COUNT= 1` | **OBSERVED** : après livraison du handler, `REMAIN(0)` vaut zéro dans cette fenêtre |
| `A06_REARM_SAME_CHANNEL` | `A06:SECOND= 1`; `A06:A= 0`; `A06:B= 1` | **OBSERVED** : seul le nouveau handler de ce canal a été servi dans la fenêtre bornée ; l'ancien n'est pas observé |
| `A07_NESTED_RETURN` | `A07:HANDLER_BEGIN`; `A07:NESTED`; `A07:HANDLER_END`; `A07:MAIN= 1` | **OBSERVED** : ordre du handler, du `GOSUB` imbriqué, des `RETURN` et de la reprise du main |
| `A08_BAD_ARGUMENT` | `A08:BEGIN` uniquement | **OBSERVED_SCREEN_DIAGNOSTIC** : les deux PNG RUN affichent exactement **`Improper argument in 20`**, puis `Ready`, pour `AFTER -1,0 GOSUB 1000`. Aucun `A08:AFTER` imprimé. `ERR`/`ERL` **UNVERIFIED** (non sondés) |

**Portée et limites :** Les archives contiennent les sources, commandes d'automatisation, `LIST #8`, flux imprimante, `program.bin` RAM original (`AFTER=80`, `REMAIN=FF 13`, `GOSUB=9F`, `RETURN=C9` lorsque présents), captures boot/LIST/RUN, logs, horodatages indépendants, empreintes et sceau. Les **8/8 sondes** sont `OBSERVED` pour ces *deux* sessions et leurs fenêtres finies uniquement. L'absence de deuxième événement, l'annulation ou le remplacement de handler sont des observations dans ces exécutions, pas des garanties de comportement hors fenêtre. `ERR/ERL`, fréquence et granularité du timer AFTER, autres canaux, `EVERY`, `DI/EI`, ordre de priorité multi-canaux et runtime ESP32 restent **UNVERIFIED / hors périmètre**. `ON_DEVICE_NOT_APPLICABLE_A1`.

### CI sur le HEAD d'expérience et limite de la présente mise à jour documentaire

Sur `e7510944edbdbe2438d0209e5ae695f9ed1e5ec7`, [CI-C99](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/43837046720), [CI-ARCH](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/43837046650), [CI-CPC-PERMANENT](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/43837046603), et [CPC oracle historique](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/43837046618) sont **SUCCESS** ; CLK-06-A1 est aussi **SUCCESS 3/3 jobs**. [CI-OPT3](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/43837046627) reste **FAILURE `UNKNOWN_OR_MISSING_WORKFLOW`**, car l'inventaire du routeur partagé n'inclut pas le workflow nouveau. Un arbitrage est demandé au Pilotage ; le Développeur ne modifie pas ce gate sans mandat.

**IMPORTANT :** Cette note change à son tour le HEAD Git. Les preuves ci-dessus restent les preuves **du HEAD d'expérience e751**, non du nouveau HEAD documentaire. Le HEAD final de la PR doit faire l'objet d'une acquisition et d'un scellement indépendants renouvelés ; les liens et le sceau du HEAD final seront consignés dans la remise GitHub sans falsifier le présent historique.
