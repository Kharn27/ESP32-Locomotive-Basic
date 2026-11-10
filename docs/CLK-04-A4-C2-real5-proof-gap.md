# CLK-04-A4-C2 — correction du faux MATCH sur REAL5 du produit ×2

Mandat Pilotage : [#364](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/364#issuecomment-6768090004). PR Draft [#366](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/366). Correction post-fusion #360 **sans** réviser A4 ni ses preuves historiques.

## Observation et frontière de preuve

Le corpus A4 scellé (SHA256 `e9fd767a394d7717816fe537695bf09bc5e40a2a5198f338d5c5e4aa42d1c79d`) capture en RAM **les cinq octets REAL5 de la variable d'entrée** `T!` au STOP, et collecte les octets imprimante de `PRINT #8,T!*2` au CONT. Aucun dump RAM scellé des cinq octets **du résultat** `T!*2` n'est identifié dans cette acquisition. Une valeur entière correcte et le texte PRINT exact ne prouvent **pas** son encodage REAL5.

L'ancien classifieur décodait `fields[3]` (`twice_real5_hex`) mais l'omettait de la décision de statut. Une sortie `0000000000` pour `T!=1`, avec le REAL5 d'entrée, l'entier ×2, les deux booléens et les quatre RAW PRINT inchangés, était classée `CANDIDATE_MATCH`.

**RED observé** : [workflow #42822071897](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42822071897), HEAD `e17dccc0f3f8ea383560e931673e72aeb365cc31`, 16 tests Python, 14 PASS et 2 FAIL attendus ; échec exact `'CANDIDATE_MATCH' == 'CANDIDATE_MATCH'` pour le champ produit falsifié. L'acquisition CPC de ce run RED a été SKIPPED et ne constitue aucune preuve CPC.

## Politique B — qualification après correction

`classify_sample` est appelée **après** validation d'authenticité RAW, avant publication des comparaisons C99. Elle conserve cinq frontières distinctes :

| Composante | Source de comparaison | Qualification |
| --- | --- | --- |
| `cpc_real5_hex` (entrée) | 5 octets de la variable CPC au STOP vs candidat | Comparaison réelle ; divergence = `CPC_MISMATCH_STOP` |
| `twice_integer` | `T!*2` observé numériquement pour cas PRINT exact, et calcul entier C99 `n*2` | Contrôle numérique borné, **pas preuve des octets RAM du produit** |
| `twice_real5_hex` (produit) | Candidat C99 seulement ; **aucun** RAW CPC indépendant correspondant | **`twice_real5_status=UNVERIFIED`** pour tous les échantillons |
| `ge_zero_integer`, `gt_32767_integer` | Valeurs observées CPC -1/0 vs candidat | Comparées séparément ; discordance = STOP |
| `raw_print_candidates` | Octets de `printer.dat` originaux | Comparaison octet à octet ; `print_comparison` individuel `CANDIDATE_MATCH`, `CPC_MISMATCH_STOP` ou `UNSUPPORTED` |

Le statut **global d'échantillon** `CANDIDATE_PARTIAL_MATCH` signifie : les composantes **effectivement comparables** sont concordantes, **hors** les cinq octets du REAL5 produit. Le statut global `CANDIDATE_MATCH` n'est plus émis sous cette politique et son compteur reste explicitement **0**. Un produit falsifié tel que `0000000000` et un produit plausible reçoivent **tous deux** `twice_real5_status=UNVERIFIED` ; un produit non prouvé n'est ni certifié ni assimilé à une discordance CPC mesurée.

Les priorités `INPUT_UNVERIFIED` et `CPC_MISMATCH_STOP` restent identiques. Les dix occurrences de PRINT étendu restent `UNSUPPORTED` (candidat hors couverture), **non promues**. Le rapport ajoute `unverified_candidate_components=["twice_real5_hex"]` et `match_scope="CANDIDATE_PARTIAL_MATCH_EXCLUDES_PRODUCT_REAL5_BYTES"`.

**Métriques attendues sur le même corpus, si le rejeu complet du HEAD final réussit** : 50 échantillons CPC (25 valeurs × original/repeat), 40 `CANDIDATE_PARTIAL_MATCH`, 10 `UNSUPPORTED`, 0 `CANDIDATE_MATCH`, 0 STOP et 0 `INPUT_UNVERIFIED`. Ces comptes doivent être confirmés par le rapport GitHub du **nouveau** run ; ils ne sont **pas** requalifiés rétroactivement sur le run A4 [#42810185987](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42810185987).

## Tests et dette hors périmètre

La suite `tests/test_clk_04_a4_numeric.py` contient des tests **synthétiques**, non des observations CPC : falsification isolée du REAL5 du produit, encodage plausible non certifié, REAL5 d'entrée erroné (STOP), et RAW PRINT falsifié (STOP). La suite existante de falsifications, les contrôles SHA/ROM/Caprice32 et l'inventaire RAW sont conservés.

Le workflow `clk-04-a4-numeric-pipeline.yml` doit effectuer **une nouvelle acquisition à deux sessions et un rejeu scellé liés au HEAD final** ; son coût n'autorise ni waiver ni réemploi abusif des RAW historiques. L'optimisation CI est une **dette distincte #363**, hors de cette PR. Sont aussi requis les six CI transverses (C99 4 cellules, ARCH, OPT3, CPC historique, CPC permanent, Xtensa 3 profils) sur le HEAD exact, avec GCC/Clang et ASan/UBSan dans A4. PNG CPC à revoir humainement : `human_png_review=REQUIRED_NOT_AUTOMATED`.

Aucune modification du CORE, TIME, du firmware/HAL, du modèle REAL5 de production, du corpus ni des preuves historiques. CYD physique : **ON_DEVICE_UNVERIFIED** (hors mission).
