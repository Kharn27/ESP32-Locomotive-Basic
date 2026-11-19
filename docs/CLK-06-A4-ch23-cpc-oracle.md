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
