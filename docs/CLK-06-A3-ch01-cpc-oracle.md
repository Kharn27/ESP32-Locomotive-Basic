# CLK-06-A3 — oracle CPC6128 des canaux 0 et 1 (GO #314)

**Mandat Pilotage :** https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/314#issuecomment-7006954822

**Base de branche :** `main@5bead95481d062cba2c1003a78226ad9a752eb64` ; branche `oracle/clk-06-a3-ch01`. Les oracles A1 (#383) et A2 (#393) sont des acquis fusionnes **en lecture seule**. Aucun changement du BASIC C99, du runtime ESP32, du firmware, du moteur Caprice32 ou de la ROM.

## Questions experimentales (entrees, non resultats)

| Sonde | Operation | Signal a observer, sans presumer la reponse |
| --- | --- | --- |
| S01 | `EVERY 10,1 GOSUB 1000`, 8 000 tours finis, `RETURN`, puis `REMAIN(1)` | compteur canal 1 et reprise du programme principal ; au moins deux livraisons pour conclure |
| S02 | `EVERY 2,1` suivi immediatement de `REMAIN(1)`, 8 500 tours finis | valeur REMAIN, puis presence ou absence bornee de callback canal 1 |
| S03 | `EVERY 10,0` et `EVERY 12,1`, deux handlers distincts, 8 500 tours finis | compteurs des canaux 0/1 et premiere trace de chaque handler, sans deduction de priorite |
| S04 | `EVERY 10,0` et `EVERY 2,1`, puis `REMAIN(1)`, 8 500 tours finis | poursuite eventuelle du canal 0, absence eventuelle du canal 1, valeurs REMAIN |

Les quatre programmes sont dans `tests/fixtures/cpc6128/clk_06_a3_ch01/{corpus.json,sources/}`. Les lignes `PRINT #8` sont les mesures ; les `HIT/H0/H1` sont plafonnes a quatre **traces**, pas les compteurs reels. Le controle `TIME` de l'emulateur borne sa vitesse ; il ne mesure pas la periode de `EVERY`. Les absences ne valent que dans les fenetres de boucle executees. Une collision de handlers n'est pas une preuve de priorite.

## Collecte, falsification et provenance

`python3 tools/clk_06_a3_oracle.py --check-sources` et `--self-test` controlent les entrees. `python3 -m unittest discover -s tests -p 'test_clk_06_a3_oracle.py' -v` execute les faux negatifs, **sans** observations CPC. Le workflow nouveau `clk-06-a3-acquisition.yml` execute trois jobs : tests de garde, capture ROM-backed avec deux boots CPC distincts (`original/repeat`), puis rejeu en job separe. Il conserve les LIST a l'ecran et sur imprimante, RAM tokenisee, PNG RUN, sorties imprimante binaires, traces de commandes exactes et SHA-256 des fichiers. Les SNA temporaires et la ROM complete ne sont pas archivees. La route CI-OPT3 A3 est limitee a ses cinq chemins A3.

**Provenance epinglee :** Caprice32 commit `8c778bf072a06fb7c23b9cccd179041db7f79a52`, binaire SHA-256 `5170b3fc68ab116e7698e6e68a742e324d0e9dbfd87eeb7b2090e13c639f73eb`, ROM SHA-256 `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562`, image GHCR digest `7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c`. Ces empreintes doivent etre **recontrolees pendant** l'acquisition et non simplement recopiees.

### Qualification encore absente

`UNVERIFIED` avant acquisition independante, inventaire/scellement, comparaison des huit sorties et inspection des PNG boot/LIST/RUN. `RAW_REPLAY_PASS` n'autorise pas a lui seul `OBSERVED`. Toute capture invalide ou contradictoire demeure `INCONCLUSIVE`. L'archivage perenne des **deux ZIP originaux** (RAW et sceau externe) avec leur SHA-256 et **HEAD d'acquisition distinct** est obligatoire avant acceptation Pilotage.

**Hors perimetre :** canaux 2/3, DI/EI, priorite generale, EVENEMENT simultane force, interpretation 1/50 Hz, TIME natif, CYD. `ON_DEVICE_NOT_APPLICABLE_A3` ; aucun flash physique PO. Statut documentaire initial : `UNVERIFIED` jusqu'a audit contradictoire.
