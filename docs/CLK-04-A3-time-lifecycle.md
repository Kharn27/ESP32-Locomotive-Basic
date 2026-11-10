# CLK-04-A3 — Oracle CPC6128 : cycle de vie de TIME

Mission [#355](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/355) — rattachée à [#312](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/312). **Oracle uniquement.** Phase B interdite avant verdict Pilotage ; aucun changement CORE, firmware ou codec REAL5 de production.

## Scellement antérieur à toute acquisition

Base GitHub : `main@3d7f1dc914324a846ff92ba3a33ab9e03916b076` ; branche `oracle/clk-04-a3-time-lifecycle`. `LOCAL_FETCH_UNAVAILABLE` : le fetch local échoue sur DNS ; aucun succès local fictif. Actions contrôle le SHA checkout exact avant le CPC.

- Protocole : `tests/fixtures/cpc6128/clk_04_a3_lifecycle/corpus.json` ; SHA256 **`7ad864070855715c3b004aed86546420b2f7149026b3a6ac6ab52f3dabde5631`**, créé par commit `c258a61a9e69364b2b45af50c4ae1129ef73e72b`.
- Publié dans l'Issue **avant exécution** : [commentaire de scellement #6762447226](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/355#issuecomment-6762447226).
- Image `ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c`, Caprice32 `8c778bf072a06fb7c23b9cccd179041db7f79a52`, ROM CPC6128 `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562`.
- BASIC ROM : TIME à &D139 appelle firmware KL TIME PLEASE à &BD0D puis &FEA5 ; cela ne prouve aucune politique BOOT/RESET/STOP.
- Antériorités A1 (REAL5 scalaire) et A2 (74 témoins numériques) **ne prouvent pas** le cycle de vie.

## Méthode, chronologie immuable

Deux sessions indépendantes `original` / `repeat`, chacune **un seul processus CPC6128** pour les sept étapes ci-dessous. Deux autres processus de garde de cadence par session (2 vs 18 CAP32_DELAY) ne servent pas d'oracle de lifecycle. Chaque processus a PID, heures UTC, commandes complètes, RC, stdout/stderr, cfg et imprimante originaux, snapshots éphémères et PNG datés.

1. **BOOT/DIRECT** : capture boot BASIC 1.1, deux `PRINT #8,TIME` séparés par six DELAY ; pas de présomption TIME zéro.
2. **IDLE** : quatre sondes TIME (deux rapprochées, huit DELAY, deux rapprochées), sans résolution sub-tick inférée.
3. **RUN #1** : TIME préalable, NEW, `run_stop.bas`, LIST #8, SNA pré-RUN ; RUN → STOP → PNG+SNA → CONT → PRINT #8,@T! / T! / TIME / TIME. Identité du programme et du scalaire vérifiées.
4. **RUN #2** : même processus et programme, deuxième RUN/STOP/CONT, nouveau SNA de T!, nouvelle suite d'impressions.
5. **NEW direct** : TIME avant, NEW, LIST #8 qui doit être vide, TIME après ; ne jamais placer NEW dans l'ancien programme.
6. **CLEAR direct** : `T!=777` et TIME avant ; CLEAR ; `T!` remis à zéro et TIME après, même processus.
7. **STOP/WAIT/CONT** : `stop_wait.bas`, LIST #8, SNA programme ; RUN → STOP+PNG+SNA, douze DELAY bornés en mode interactif → CONT+PNG, puis lectures TIME et sortie CAP32_EXIT explicite.

Timeout 240 s par session ; maximum 65 tokens DELAY ; deux sessions. Jamais de boucle non bornée ni d'attente du wrap 32 bits. S'il n'existe pas de commande RESET Caprice32 avec sémantique attestée et protocole préalablement scellé, `RESET_IN_PROCESS_UNSUPPORTED`.

## Preuves, replay, refus des falsifications

Workflow isolé `.github/workflows/clk-04-a3-lifecycle-oracle.yml` à trois jobs : `negative-tests`, `cpc-acquire`, `cpc-replay`. Cinq chemins PR : workflow A3, `tools/clk_04_a3_*`, `tests/test_clk_04_a3_lifecycle.py`, `tests/fixtures/cpc6128/clk_04_a3_lifecycle/**`, `docs/CLK-04-A3*`. Inventaire fermé sur base A3 seule : **43 workflows / 5 familles** ; si #354/D1 entre avant : 44/5, audit additif à réconcilier, jamais d'écrasement.

RAW : imprimante `printer.dat`, `cap32.cfg`, `autocmd.json`, `stdout.bin`, `stderr.bin`, `caprice.log`, 10 PNG/stade, `run_program.bin`, `stop_program.bin`, extraits `*_window.bin` et `*_ram.json` contenant les cinq octets REAL5 originaux avec vérification du nom T!, type 04 et adresse `@T!` après CONT sur le même processus. **Ni SNA intégral, ni ROM** dans les ZIP.

Le `manifest.json` énumère exactement chaque fichier relatif, taille et SHA256. Son **SHA256 externe** est imprimé dans les logs d'acquisition et stocké dans un artefact distinct. Le replay téléchargé dans un autre job exige sceau, HEAD identique, pins, source, ordre, cardinalité, PID/session, intégrité RAW, imprimante, LIST, RAM et liens REAL5. Les scripts rejettent les incohérences au lieu de compléter des mesures manquantes.

Tests synthétiques, **pas CPC** :

`python3 -m unittest discover -s tests -p 'test_clk_04_a3_lifecycle.py' -v`

`python3 tools/clk_04_a3_lifecycle.py --self-test`

Acquisition, uniquement conteneur épinglé et SHA checkout :

`python3 tools/clk_04_a3_lifecycle.py --acquire --caprice tests/oracles/caprice32 --output /tmp/clk04-a3-raw --head "$HEAD"`

Rejouer avec SHA externe indépendant :

`python3 tools/clk_04_a3_lifecycle.py --verify /tmp/clk04-a3-raw --head "$HEAD" --seal "$MANIFEST_SHA256" --report /tmp/clk04-a3-report.json`

## Matrice de résultats — aucune affirmation avant acquisition

| Dimension | Statut actuel | Preuve à obtenir |
|---|---|---|
| BOOT / DIRECT | UNVERIFIED | Deux TIME/session, delta, PNG boot |
| IDLE / non-décroissance | UNVERIFIED | Quatre TIME/session, garde de cadence |
| RUN et deuxième RUN | UNVERIFIED | Impressions et RAM REAL5 aux STOP, même PID |
| NEW direct | UNVERIFIED | Imprimante avant/après, LIST vidé, même PID |
| CLEAR direct | UNVERIFIED | Variable T! 777 → 0 distincte du TIME |
| STOP / WAIT / CONT | UNVERIFIED | SNA/PNG STOP, attente bornée, CONT et lectures |
| Origine initiale de TIME | TIME_ORIGIN_UNVERIFIED | Ne pas extrapoler le premier PRINT |
| RESET in-process | UNSUPPORTED | Aucun RESET instrumenté scellé |
| Seuil 32767 | UNVERIFIED | Non forcé, incident fortuit seulement |
| Wrap uint32 / reset matériel | UNSUPPORTED | Hors périmètre |

Les dates de captures PNG et les intervalles hôte n'établissent ni cadence absolue de BASIC ni précision sub-tick. **CPC_ORACLE_VERIFIED** ne peut être déclaré que sur les cas rejoués avec captures PNG manuellement inspectées. `ON_DEVICE_UNVERIFIED` non bloquant pour cet oracle-only. Aucun FAIL/SKIPPED historique HW4 ne devient PASS. PR Draft, revue, acceptation et fusion relèvent du seul Pilotage.
