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

**Hors perimetre :** canaux 2/3, DI/EI, priorite generale, EVENEMENT simultane force, interpretation 1/50 Hz, TIME natif, CYD. `ON_DEVICE_NOT_APPLICABLE_A3` ; aucun flash physique PO. Statut documentaire initial (avant acquisition) : `UNVERIFIED` jusqu'a audit contradictoire.

## Audit contradictoire POST-acquisition du HEAD historique `8b66637e8023f5632291a930fae92bd48333417b`

**Sondage authentique, non test synthetique.** La campagne [GitHub Actions #44510663988](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44510663988) s'est terminee par trois jobs `SUCCESS` (tests hote, huit RUN CPC ROM-backed et relecture separee). Cette observation correspond au HEAD **historique 8b66637e**, pas au HEAD du commit documentaire courant.

- [Artifact ZIP RAW #14522149201](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44510663988/artifacts/14522149201), SHA-256 du ZIP original `adc917e2f6f4eb5a25378a215cbea1499db63baf742c14994a0598dd36d7c6de`, 185245 octets.
- [Artifact ZIP sceau externe #14522653895](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44510663988/artifacts/14522653895), SHA-256 du ZIP original `cdc13cc0cac8f5ae9104dfb832e435d5b861de70369cba13a9151423c202d912`, 322 octets.
- SHA-256 des octets originaux `manifest.json` : `5d5a0356e6e912c1b6d050b4b3261e4003c87e058502bd5c05d691dc5c56eb8e`. Le sceau JSON **separe** refere le meme `mission=CLK-06-A3`, le meme HEAD historique et le meme SHA du manifeste.
- **118/118 fichiers originaux** conformes en taille et SHA-256, 119 entrees ZIP RAW incluant le manifeste, aucune ROM complete ni SNA archivee. Programme RAM tokenise, LIST imprime, captures LIST/RUN PNG et sortie RUN imprimante **identiques octet par octet** entre `original` et `repeat` pour chacun des quatre cas ; quatre paires de resultats.
- Les deux captures de boot affichent `Amstrad 128K Microcomputer`, `BASIC 1.1` et `Ready` ; boots distincts horodates `2026-11-19T10:59:48.088611+00:00` et `2026-11-19T11:05:12.266112+00:00`. Controle `TIME` CPC par seconde hote : `300.329382` et `300.392493`, sans inference sur la periode `EVERY`. L'operateur a examine les images reelles des deux boots et les quatre ecrans LIST/RUN ; les paires de PNG LIST/RUN sont byte-identiques.
- Le manifeste RAW reste `ACQUIRED_PENDING_SCREEN_REVIEW` et `screen_review=UNVERIFIED` **sans alteration**. L'audit ci-dessous est une interpretation documentaire independante des octets originaux ; le rejeu automatique seul ne prouve pas l'affichage.

| Sonde | Observations imprimante CPC, identiques dans les deux sessions | Qualification limitee |
| --- | --- | --- |
| `S01_CH1_RECUR_RETURN` | `S01:HIT=1..4` imprimes, `S01:MAIN=19`, `S01:CANCEL=2`; `Ready` a l'ecran RUN | **OBSERVED**, 19 livraisons comptees, RETURN et reprise du principal pendant la seule boucle de 8000 tours |
| `S02_CH1_REMAIN_CANCEL` | `S02:REMAIN=2`, `S02:MAIN=0`, `S02:R2=0`, aucun `S02:HIT` | **OBSERVED**, absence de livraison dans cette seule fenetre de 8500 tours avec desarmement immediat |
| `S03_CH01_COEXIST` | `S03:H0=1..4` / `S03:H1=1..4`, `S03:CH0=21`, `S03:CH1=18`, `R0=4`, `R1=12` | **OBSERVED**, deux canaux servis dans cette fenetre de 8500 tours, **pas** preuve d'ordre ou de priorite generale |
| `S04_CANCEL_CH1_KEEP_CH0` | `S04:REMAIN1=2`, `S04:CH0=21`, `S04:CH1=0`, `S04:REMAIN0=9`, `S04:R1AGAIN=0`; aucun `S04:H1` | **OBSERVED**, canal 0 maintenu et canal 1 desarme dans cette seule fenetre de 8500 tours |

Les `HIT/H0/H1` visibles sont plafonnes volontairement a quatre **lignes** ; les compteurs principaux restituent les nombres d'evenements. La comparaison est celle de fichiers binaires authentiques, non d'une sortie reconstruite a partir du corpus. **`UNVERIFIED`** : canaux 2/3, DI/EI, interruptions simultanees forcees, priorite universelle, vitesse absolue du ticker, erreurs non sondees, semantique native ESP32.

**Archivage permanent effectif sous le namespace A3 (deux ZIP originaux immuables) :** les deux artifacts GitHub ci-dessus ont ete copies **octet par octet** dans ce depot en tant que blobs Git, avec verification de leur Git blob SHA-1 contre `git hash-object` calcule sur les fichiers d'origine. Les deux archives conservees sont :

- `tests/fixtures/cpc6128/clk_06_a3_ch01/evidence/run-44510663988-8b66637e-raw.zip` — ZIP original, SHA-256 `adc917e2f6f4eb5a25378a215cbea1499db63baf742c14994a0598dd36d7c6de`, Git blob `497f2c5edfa00be0ae41f8efe7a9f4894ff13f61`.
- `tests/fixtures/cpc6128/clk_06_a3_ch01/evidence/run-44510663988-8b66637e-external-seal.zip` — sceau ZIP original, SHA-256 `cdc13cc0cac8f5ae9104dfb832e435d5b861de70369cba13a9151423c202d912`, Git blob `57e2c9203818a1762f70efcbbbdffcde50fdfc76`.

Verification depuis le checkout de la PR :

```sh
sha256sum tests/fixtures/cpc6128/clk_06_a3_ch01/evidence/*.zip
git hash-object tests/fixtures/cpc6128/clk_06_a3_ch01/evidence/*.zip
mkdir -p /tmp/clk06-a3-historical-raw
unzip -q tests/fixtures/cpc6128/clk_06_a3_ch01/evidence/run-44510663988-8b66637e-raw.zip -d /tmp/clk06-a3-historical-raw
python3 tools/clk_06_a3_oracle.py --verify /tmp/clk06-a3-historical-raw \
  --head 8b66637e8023f5632291a930fae92bd48333417b \
  --seal 5d5a0356e6e912c1b6d050b4b3261e4003c87e058502bd5c05d691dc5c56eb8e
```

Le contenu de chaque ZIP **reste attribue uniquement au HEAD historique d'acquisition `8b66637e...`**, pas au commit qui a archive les ZIP ; aucune piece interne ni sceau n'a ete modifie. Le HEAD courant doit conserver une campagne distincte, avec son propre sceau. Le pilote seul decide l'acceptation et la fusion ; **aucune auto-acceptation**.
