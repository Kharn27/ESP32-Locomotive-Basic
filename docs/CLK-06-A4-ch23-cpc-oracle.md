# CLK-06-A4 — Oracle CPC6128 EVERY canaux 2 et 3

**GO Pilotage** : https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/314#issuecomment-7008430215

**Base exacte** : `main@67f71c87c7218c7052304402e0b8cd36ce51a58c` ; branche `oracle/clk-06-a4-ch23`. A1/A2/A3 en lecture seule. **ORACLE-ONLY**.

## Quatre sondes discriminantes (entrees, jamais valeurs attendues)

| Sonde | Programme fini | Observation a rechercher |
| --- | --- | --- |
| S01 | `EVERY 10,2 GOSUB 1000` ; 8500 tours ; handler/RETURN ; `REMAIN(2)` | Au moins deux livraisons du canal 2 et reprise du principal |
| S02 | `EVERY 12,3 GOSUB 1000` ; 9000 tours ; handler/RETURN ; `REMAIN(3)` | Au moins deux livraisons du canal 3 et reprise du principal |
| S03 | `EVERY 10,2` et `EVERY 12,3` ; handlers distincts ; 9000 tours | Compteurs de livraisons sur les deux canaux, **sans priorite universelle** |
| S04 | `EVERY 10,2` et `EVERY 2,3` ; `REMAIN(3)` immediat ; 9000 tours ; `REMAIN(2)` puis `REMAIN(3)` | Canal 2 continue-t-il alors que canal 3 reste sans callback dans cette fenetre ? |

`tests/fixtures/cpc6128/clk_06_a4_ch23/corpus.json` et `sources/S0*.bas` conservent les lignes ASCII numerotees. Toutes les boucles sont finies. Les lignes `PRINT #8` sont des questions mesurees sur CPC ; les marqueurs `HIT/H2/H3` impriment au plus quatre traces par handler mais les compteurs ne sont pas plafonnes. Les intervalles 10 et 12 sont intentionnellement distincts ; ne pas en deduire une priorite, une simultaneite forcee ni une cadence 1/50s.

## Protocole et classement provisoire

`python3 tools/clk_06_a4_oracle.py --self-test`, `--check-sources`, puis `python3 -m unittest discover -s tests -p 'test_clk_06_a4_oracle.py' -v` testent la source et les falsifications **HOST_ONLY**. Le workflow `.github/workflows/clk-06-a4-acquisition.yml` execute les jobs host, acquisition, replay sur un job distinct. Il exige deux vrais boots `original/repeat`, LIST ecran et `LIST #8`, RAM tokenisee, RUN PNG et imprimante brute, horodatages, inventaire et sceau SHA-256 externe, et vitesse `TIME` CPC comme **controle d'emulation uniquement**. ROM et SNA complets jamais archives. Le manifeste RAW restera `ACQUIRED_PENDING_SCREEN_REVIEW`, avec `UNVERIFIED` pour les ecrans.

Pins provenance, controles au runtime : Caprice32 `8c778bf072a06fb7c23b9cccd179041db7f79a52` ; cap32 SHA256 `5170b3fc68ab116e7698e6e68a742e324d0e9dbfd87eeb7b2090e13c639f73eb` ; ROM CPC6128 SHA256 `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562` ; image `ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c`.

**PREPARATION / UNVERIFIED** jusqu'aux huit runs independants, inspection des PNG boot/LIST/RUN et sorties imprimante byte-exact, et archivage permanent des deux ZIP originaux (RAW et sceau) avec SHA et HEAD precis ; nouvelle acquisition au HEAD final si different. Les absences de callbacks sont bornees a la fenetre du programme ; une anomalie = `INCONCLUSIVE`.

## Barriere de coordination obligatoire #396

La PR concurrente [#396](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/396) est active au demarrage. **DEV1 ne touche ni `tools/ci/opt3_routing.py` ni les gardes CI-ARCH**, ni les chemins de #396. Le workflow A4 n'est pas enregistre dans l'inventaire OPT3 pendant cette phase ; **un echec/absence d'OPT3 est un blocage d'integration et non une derogation**. Apres fusion #396 **par PILOTAGE** seulement : lire le nouveau SHA de main, synchroniser **sans force-push**, puis ajouter l'unique route nominative A4 avec contre-exemples. Si #396 reste bloquee : STOP sur integration finale et remise d'etat.

Aucun changement `core/`, `firmware/`, `integration/`, HAL, Xtensa, CMake, ROM/Caprice32, TIME natif, canaux 0/1, CLK-07/08, DI/EI, ESC/BREAK. `ON_DEVICE_NOT_APPLICABLE_A4`, aucun flash physique.

## Campagne CPC authentique initiale — audit contradictoire, HEAD historique

**Run GitHub Actions** : [#44520757976](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44520757976), trois jobs `SUCCESS` : tests hote (12 adversariaux), acquisition `4 programmes x 2 sessions`, replay scelle dans un job distinct. **HEAD d'acquisition exact : `39da63f7b6448fba608e40f34fbdbf122749148c`**. Cette identite doit rester differente de celle du commit archiveur ; ne jamais requalifier le manifeste brut.

**Deux ZIP originaux conserves bit-a-bit dans Git**, namespace A4 exclusivement :

- `tests/fixtures/cpc6128/clk_06_a4_ch23/evidence/run-44520757976-39da63f7-raw.zip` : 184335 octets ; SHA256 original `b14549480a4f9f33aca531f83391103c7cbc71a826d38ab64903b130284335ba` ; Git blob SHA1 `bc78946f224507f0228edd041546aa70b3e76de1`. [Artifact RAW d'origine #14527989287](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44520757976/artifacts/14527989287).
- `tests/fixtures/cpc6128/clk_06_a4_ch23/evidence/run-44520757976-39da63f7-external-seal.zip` : 322 octets ; SHA256 original `1aa4541c7131e032b4b8f31e24c067bd293ece7ac43f2d9477077e30acbf412a` ; Git blob SHA1 `0e149523dd5684f7ddfdad4988b2d2df80210a90`. [Artifact sceau d'origine #14528201828](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44520757976/artifacts/14528201828).

Le sceau **hors archive RAW** declare `mission=CLK-06-A4`, `head=39da63f7b6448fba608e40f34fbdbf122749148c`, `manifest_sha256=19d3ea0b5b873adf97d8131fb2d07df5828c8fe6f63ba437c48c898a791cee18`. Verifie sur les **octets originaux** du manifeste : SHA256 identique. Inventaire RAW valide `118/118` fichiers en taille et SHA256 (119 membres ZIP avec `manifest.json`) ; aucun `.rom/.sna/.dsk` archive. Paires `LIST #8` et RAM tokenisee byte-identiques entre sessions pour chaque cas ; tous les `run/printer.dat` strictement byte-identiques entre sessions, et conformes a leurs SHA256 de manifeste. Deux boots distincts (UTC `2026-11-19T12:06:54.355966+00:00`, `2026-11-19T12:12:16.163149+00:00`), ecrans **Amstrad 128K / BASIC 1.1 / Ready** inspectes ; controles de vitesse TIME `300.306801` et `300.345489` ticks par seconde hote, **sans** inference de frequence d'evenement. Les captures LIST et RUN des huit executions ont ete inspectees ; pour chacun des quatre cas, original/repeat sont **identiques pixel par pixel ET octet par octet** sur LIST et RUN. Fin des RUN visible par `Ready`.

| Sonde | Reponse imprimante originale et repeat, octets identiques | Qualification bornee |
| --- | --- | --- |
| S01 | `S01:HIT=1..4`, `S01:MAIN=21`, `S01:CANCEL=10` | **OBSERVED** : au moins 2 callbacks canal 2, `RETURN` et reprise principale pendant 8500 iterations |
| S02 | `S02:HIT=1..4`, `S02:MAIN=18`, `S02:CANCEL=6` | **OBSERVED** : au moins 2 callbacks canal 3, `RETURN` et reprise principale pendant 9000 iterations |
| S03 | `S03:H2=1..4`, `S03:H3=1..4`, `S03:CH2=22`, `S03:CH3=19`, `S03:R2=2`, `S03:R3=12` | **OBSERVED** : coexistence de livraisons sur les deux canaux pendant 9000 iterations, pas preuve de priorite universelle |
| S04 | `S04:REMAIN3=2`, `S04:H2=1..4`, `S04:CH2=22`, `S04:CH3=0`, `S04:REMAIN2=7`, `S04:R3AGAIN=0`, aucune ligne `H3` | **OBSERVED** : canal 2 continue, canal 3 sans livraison seulement dans la fenetre de 9000 iterations |

Les `HIT/H2/H3` sont volontairement limites aux quatre **premiers messages** de chaque handler, pas aux compteurs reels `MAIN/CH2/CH3`. Deux LIST sources de 12 lignes chacune, une de 19 et une de 20, imprimees integralement et tokenisees en RAM. **Aucune affirmation** de cadence absolue, de livraison simultanee forcee ou de priorite generale, ni de fidelite native ESP32. Le manifeste archive est **toujours** `ACQUIRED_PENDING_SCREEN_REVIEW` avec `screen_review=UNVERIFIED` ; c'est cette revue documentaire exterieure qui qualifie l'observation bornee, sans mutation des donnees brutes.

### Controle local reproducible (HEAD historique distinct)

```sh
sha256sum tests/fixtures/cpc6128/clk_06_a4_ch23/evidence/*.zip
git hash-object tests/fixtures/cpc6128/clk_06_a4_ch23/evidence/*.zip
mkdir -p /tmp/clk-06-a4-initial-raw
unzip -q tests/fixtures/cpc6128/clk_06_a4_ch23/evidence/run-44520757976-39da63f7-raw.zip -d /tmp/clk-06-a4-initial-raw
python3 tools/clk_06_a4_oracle.py --verify /tmp/clk-06-a4-initial-raw \
  --head 39da63f7b6448fba608e40f34fbdbf122749148c \
  --seal 19d3ea0b5b873adf97d8131fb2d07df5828c8fe6f63ba437c48c898a791cee18
```

**Dependance non levee** : PR #396 active. Les preuves ROM-backed historiques A4 sont archivees ; **CI-OPT3 A4 reste `UNKNOWN_OR_MISSING_WORKFLOW`** jusqu'a fusion effective #396 et ajout de route A4 exclusivement par DEV1. Toute acquisition sur le futur HEAD de remise devra utiliser son propre sceau et ses propres ZIP, distincts des fichiers historiques.

## CLK-06-A4-C1 — reconciliation A5 et provenance du nouveau HEAD

Le [verdict Pilotage C1 du 19/11/2026](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/397#issuecomment-7010489474) autorise la reconciliation de cette branche avec `main@09036faf4b64e2b281d3d961ff5f48b389c75985`, **apres** la fusion de [#396](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/396). Le STOP precedent et ses anciennes acquisitions sont conserves comme historique, et **ne constituent pas la preuve du nouveau HEAD**. Les deux ZIP `evidence/run-44520757976-39da63f7-*.zip` demeurent rigoureusement inchanges avec leurs blob SHA1/sha256 precedemment consignes.

Sur C1, la nouvelle route `.github/workflows/clk-06-a4-acquisition.yml` est enregistree **uniquement** dans `CPC_ACQUISITION`, avec cinq filtres nominatifs et la meme liste de familles. Les falsifications `tools/ci/opt3_routing.py` refusent insertion de filtres larges, events/permissions, cancellation, skip de job, defaut d'empreinte HEAD, ROM, commit Caprice32 et image GHCR, absence de sceau hors RAW, et replay non chaine. Aucun filtre A5 n'est modifie ; les protections A4 numeriques et A5 fusionnees restent intactes. `49 workflows / 5 familles` uniquement si main ne change pas de nouveau.

**Re-acquisition requise au HEAD exact final C1** : ne pas assimiler le ZIP historique ni les campagnes intermediaires a ce HEAD. Pour chaque S01-S04, deux boots frais (original, repeat), ROM/Caprice/image epingles, LIST/STOP/RUN et sources RAM/imprimante/PNG, provenance signees par un sceau de manifeste **hors** RAW, puis rejeu en job different. Les captures et les huit CI doivent etre verifies sur le SHA final et lies dans la remise de PR #397. `OBSERVED` reste strictement limite aux quatre fenetres finies ; cadence absolue, priorite universelle, DI/EI et TIMER natif restent `UNVERIFIED`. `ON_DEVICE_NOT_APPLICABLE_A4`.
