# CLK-04-A4 — Pipeline numérique minimal REAL5 / PRINT pour TIME

**Mission Pilotage [#359](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/359), parent [#312](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/312).**
Expérimentation isolée ; aucun GO CORE, aucune politique wrap/reset/origine ni moteur REAL5 général.

## Gel des entrées (précède l'acquisition)

- Base imposée et contrôlée : `main@c4e4ad889fe3bf1a97f1070553bc0ba15a55c8f0`.
- Branche : `oracle/clk-04-a4-real5-numeric-pipeline`.
- Corpus : `tests/fixtures/cpc6128/clk_04_a4_numeric/corpus.json`, **6650 octets**.
- SHA-256 externe : **`e9fd767a394d7717816fe537695bf09bc5e40a2a5198f338d5c5e4aa42d1c79d`**.
- Commit de gel : `bfdd1300db452d3bfe0f5a6649abd93911e2f968`.
- Publication avant acquisition : [commentaire #6763921353](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/359#issuecomment-6763921353).
- 25 valeurs obligatoires, 7 lots (4/4/4/4/4/4/1) ; 8 contre-constructions par puissances de deux et sondes =, +1, -1.
- 7 sources BASIC intégrales et cardinalités des impressions dans le corpus ; aucune donnée observée CPC incluse au gel.

## Chaîne d'observation disjointe du candidat

Le collecteur `tools/clk_04_a4_oracle.py` s'appuie **en lecture seule** sur le pilote ROM-backed A2 et la capture CLK-03, sans démarrer le code C99. Image immuable :
`ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c`.
Caprice32 : `8c778bf072a06fb7c23b9cccd179041db7f79a52` ; ROM : SHA-256
`31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562`.

Deux boots `original` et `repeat`, avec contrôles cadence, acquièrent chaque lot.
La source BASIC affecte les réels explicitement (`T!` à `W!`, et `P!` à `S!` pour méthodes alternatives), exécute `STOP`, déclenche un SNA transitoire et conserve les **cinq octets REAL5 originaux** de chaque scalaire type `04` selon RAM &AE68/&AE6A et `PRINT #8,@variable!`. `CONT` sort dans l'imprimante d'origine l'adresse, `T!`, `T!*2`, `T!>=0`, `T!>32767`, puis les témoins de construction alternative. Les lignes de sortie sont enregistrées **octet pour octet**, avec espaces, CR/LF et notation exponentielle, sans reconstruction depuis `Decimal`.

Les sorties RAW `printer.dat`, RAM `window.bin`, `stop.json` (métadonnées de session), `program.bin` et `stop_program.bin`, `LIST #8`, commandes exactes, `cap32.cfg`, boot/STOP/CONT PNG et logs sont inventoriés (taille et SHA256 par fichier) dans `manifest.json`. SNA et ROM ne sont **jamais** archivés ; seules leurs métadonnées/hachages nécessaires restent. Le manifeste est scellé par SHA256 **hors RAW** dans les logs et l'artefact séparé. Le replay impose SHA, HEAD, ROM/Caprice, deux sessions, inventaire, identité des noms et adresses/type, cadence, programmes, cardinalité et valeurs brutes.

**Statut de preuve :** une image PNG de STOP/CONT doit encore être inspectée humainement, y compris si la CI passe. Un job interrompu et son artefact partiel ne sont pas une acquisition qualifiée.

## Frontières du prototype C99 (CANDIDATE, jamais un oracle)

`tools/clk_04_a4_numeric_lab.{c,h}` est compilable en C99 seul, sans `float`, `double`, `malloc`, système de temps ou code CORE. Aucune dépendance autre que `stdint.h`, `stddef.h`, `string.h`, `limits.h`. Les buffers appartiennent à l'appelant ; les refus laissent buffers inchangés.

| Fonction | Contrat **candidat** | Hors couverture |
|---|---|---|
| `a4_integer_to_real5(uint64_t, uint8_t[5])` | entier non négatif exact jusqu'à 2 × UINT32_MAX ; mantisse de 32 bits utiles, exposant biaisé ; zéro spécial ; cinq octets le/byte 4 exponent | négatifs, fractions, entiers au-delà de cette borne, incohérents/non exactement représentables |
| `a4_times_two(uint32_t, uint64_t*)` | multiplication 64 bits vérifiable et sans overflow de la plage d'entrée | débordement du domaine, calcul CPC général |
| `a4_ge_zero`, `a4_gt_32767` | résultats *candidats* BASIC -1/0, séparés de l'imprimante | valeurs négatives, comparateurs généraux |
| `a4_print_candidate(int64_t, bytes, cap, used)` | **hypothèse explicite** pour -1..999999 : espace éventuel de signe, chiffres décimaux, espace, CR LF | décimal/exponentiel CPC général, arrondi, valeurs au-delà ; renvoie `UNSUPPORTED` |

L'encodage d'entiers `uint32` est hypothèse A2, **pas** assertion universelle sur la ROM. À `×2`, le prototype recalcule l'octet d'exposant en gardant un entier 64 bits ; cela ne démontre pas l'implémentation interne CPC. Pour de grands entiers, une impression exponentielle/arrondie ne prouve pas l'identité numérique : les cinq octets RAM et les alternatives CPC restent primaires. La conversion texte C99 ne peut jamais servir de source d'octets `RAW_REAL5_CPC` ou `RAW_PRINT_CPC`.

Le pilote `tests/test_clk_04_a4_numeric_cli.c` émet dix colonnes ASCII séparées par tabulation (entier, REAL5, double, REAL5 du double, deux booléens, quatre PRINT candidats hex ou UNSUPPORTED). Ce format est **un protocole de comparaison hôte**, pas l'imprimante CPC.

À l'analyse A4, chaque valeur × session reçoit indépendamment un `RAW_REAL5_CPC`, quatre `RAW_PRINT_CPC`, une observation `EXPRESSION_CPC` et `C99_CANDIDATE`. Les statuts sont `VERIFIED_CPC_SAMPLE`, `CANDIDATE_MATCH`, `CPC_MISMATCH_STOP`, `INPUT_UNVERIFIED`, `UNSUPPORTED`. Une discordance de présentation ne modifie jamais les preuves originales et entraîne STOP sur la zone, même si la mantisse concorde. L'absence de candidat PRINT sur les grands exposants reste UNSUPPORTED. **Aucune équivalence de formatage générale n'est revendiquée.**

## Tests, coûts, reproductibilité

Hôte local (avant publication, distinct de GitHub Actions) : GCC C99 `-Wall -Wextra -Werror -pedantic -O2` et `-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined` exécutés sur les 25 valeurs ; tests de sorties inchangées sur erreurs, limites, doubles, relations, PRINT borné et refus. À mesurer de nouveau sur HEAD final (et avec Clang) ; ne pas transposer ces métriques à Xtensa.

Mesure indicative GCC `-O2 -fstack-usage` du laboratoire C99 isolé : **874 octets** de section text de l'objet, data/bss 0, plus grands coûts de pile statiques locaux estimés par compilateur **16 octets** pour formatage, **8 octets** pour chaque autre helper (architecture hôte, non budget Xtensa et hors appelants). Pas de code ajouté à l'image firmware.

```sh
python3 -m unittest discover -s tests -p 'test_clk_04_a4_numeric.py' -v
python3 tools/clk_04_a4_oracle.py --self-test
for cc in gcc clang; do
  "$cc" -std=c99 -Wall -Wextra -Werror -pedantic -O2 \
    tools/clk_04_a4_numeric_lab.c tests/test_clk_04_a4_numeric_lab.c -o /tmp/a4test
  /tmp/a4test
done
# Oracle CPC exige Caprice32/ROM épinglés dans le job CI :
# --acquire --caprice ... --output ... --head HEAD
# puis SHA256(manifest) publié hors RAW, puis --verify ... --seal SHA --candidate ...
```

Workflow dédié `.github/workflows/clk-04-a4-numeric-pipeline.yml` : hôte/négatifs/sanitizers → capture CPC → replay scellé, artefacts RAW, sceau et rapport candidat distincts. Routes CI-OPT3 A4 exclusivement dans CPC_ACQUISITION : 45 workflows/5 familles **si main ne diverge pas**. CI transverses requises au HEAD final : C99 (4 cellules), ARCH, OPT3, CPC historique, CPC permanent et Xtensa trois profils. Tout `SKIPPED` reste `SKIPPED`.

## Registre de vérification et décision demandée au Pilotage

| Domaine | Statut avant preuves GitHub du HEAD final |
|---|---|
| Source corpus et SHA publiés avant run | **SEALED_PRE_ACQUISITION**, voir commit et Issue |
| Hôte C99 local | **HOST_VERIFIED** (machine d'exécution, pas HEAD Actions) |
| Deux sessions CPC indépendantes, RAM/PRINT et sceau externe | **UNVERIFIED** jusqu'aux jobs et à la revue des PNG |
| Comparaison octet / PRINT candidat | **UNVERIFIED** jusqu'au rejeu authentifié |
| Domaine étendu REAL5, décimal général, TIME native, wrap/reset | **UNSUPPORTED / RANGE_UNVERIFIED** |
| CI GitHub transverses sur HEAD final | **NON VÉRIFIÉ** avant exécution |
| Matériel CYD | **ON_DEVICE_UNVERIFIED** (hors mandat) |

**Verdict proposé : attente de preuve CPC et des CI au HEAD final ; aucun GO CORE implicite.** Les résultats scientifiques et échecs éventuels demeurent recevables mais l'intégration de TIME nécessite une **autre** décision Pilotage et une PR CORE distincte.
