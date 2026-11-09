# CLK-04-A1 — Oracle CPC6128 du format REAL5 de `TIME`

Mission [#340](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/340), dépendance [CLK-04 #312](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/312). **Autorisation A1 : oracle seulement ; la phase B et tout codec REAL5 natif A2 restent BLOQUÉS.**

## Provenance, base, frontière

Base GitHub vérifiée avant branche : `main@03f83c39e6f9ed4daeddb1ed93a989a35d726e30`, PR #333 fusionnée. Branche `oracle/clk-04-a1-time-real5`. Clonage/fetch local impossible dans l'environnement du développeur : `LOCAL_FETCH_UNAVAILABLE` (DNS). L'acquisition doit prouver checkout au SHA exact et sous-module Caprice32 épinglé en CI ; aucun essai local n'est transformé en preuve CPC.

Le protocole réutilise sans modifier l'outil CLK-03 de pilotage Caprice32, avec image GHCR au digest `sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c`, Caprice32 `8c778bf072a06fb7c23b9cccd179041db7f79a52`, ROM `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562`. Les gardes de cadence 255–345 ticks/s restent des **contrôles de conditions expérimentales**, jamais une fréquence absolue démontrée.

Références en lecture seule : `basic.asm` (TIME `&D139` → `&BD0D` → `&FEA5`), `docs/CLK-03-cpc-time-oracle.md`, `docs/J1.16-*` et `core/basic_variable_store.h`. La ROM établit le chemin d'appel, pas à elle seule les cinq octets d'un résultat TIME. Le stockage C99 actuel `real5[5]` n'est ni un encodeur ni un moteur de calcul REAL5 général.

## Corpus figé AVANT acquisition

`tests/fixtures/cpc6128/clk_04_real5/corpus.json` ; **SHA-256 attendu : `3ba8d1ce7f1d1996dd1593cc5b4ae15a84be9fefd9bd637b4c44b2a02e39f423`**. Les résultats attendus ne sont PAS sérialisés dans la source ; ce SHA protège uniquement les sondes. Sept cas : `F_ZERO`, `F_ONE`, `F_NEG_ONE`, `F_HALF`, `F_QUARTER`, `T_DYNAMIC_PAIR`, `T_LATE_BOUNDED`. Deux sessions `original` / `repeat`, au minimum.

Chaque cas : édition des lignes puis `LIST` et `LIST #8` depuis un premier CPC démarré proprement, capture de `program.bin` via SNA temporaire ; dans un **second processus CPC** distinct, `RUN` jusqu'à un `STOP` numéroté, capture SNA au STOP, puis `CONT` et impression `PRINT #8`. Le snapshot doit précéder la continuation, et les lectures ultérieures de `TIME` ne sont pas présumées simultanées à la variable.

- Pour les cinq fixes : `10 T!=<constante>` → `15 STOP` → `PRINT #8,@T!`, `T!`, `T!*2`, `T!>=0`, `T!>32767`.
- Pour les deux dynamiques : `10 T!=TIME` puis `20 U!=TIME` → `25 STOP` → `PRINT #8,@T!,T!,T!*2,T!>=0,T!>32767,@U!,U!,U!>=T!,TIME` sur des **lignes séparées**. Les adresses `@T!` et `@U!` doivent correspondre aux offsets des cinq octets REAL5 extraits, faute de quoi le validateur rejette le témoin. Le dernier `PRINT TIME` est une nouvelle lecture, pas une égalité supposée.
- `T_LATE_BOUNDED` ajoute exactement 160 commandes `CAP32_DELAY` **avant RUN** ; garde subprocess 290 s, sans forcer artificiellement le compteur. Si 32767 n'est pas dépassé, **UNSUPPORTED**, aucune interpolation ni règle de wrap inférée.

Les SNA complets et la ROM sont exclus des artefacts. Le seul `window.bin` archivé vient d'une région originale de la RAM CPC, bornée entre les pointeurs BASIC `&AE68` et `&AE6A`, sur configuration CPC6128 RAM banque 0. Les entrées de neuf octets sont identifiées par nom, marqueur interne `04`, puis cinq octets bruts ; seuls les octets lus de SNA sont probants. `@T!` fournit un **contre-témoin indépendant** de l'adresse. Les deux octets de lien d'entrée et les caches de références restent opaques. Il est interdit de reconstruire `window.bin` à partir d'un nombre affiché.

## Commandes de reproduction en CI (image épinglée)

```sh
python3 -m unittest discover -s tests -p 'test_clk_04_real5_oracle.py' -v
python3 tools/clk_04_real5_oracle.py --self-test
python3 tools/clk_04_real5_oracle.py --acquire \
    --caprice tests/oracles/caprice32 \
    --output /sortie/neuve/clk04-a1-cpc-raw \
    --head "$(git rev-parse HEAD)"
sha256sum /sortie/neuve/clk04-a1-cpc-raw/manifest.json
python3 tools/clk_04_real5_oracle.py \
    --verify /sortie/neuve/clk04-a1-cpc-raw \
    --head "$(git rev-parse HEAD)" --seal SHA256_EXTERNE_PUBLIE
```

Le workflow `.github/workflows/clk-04-real5-oracle.yml` produit un job synthétique négatif, une acquisition en conteneur épinglé et un rejeu du ZIP de données brutes téléchargé dans un job indépendant, avec sceau SHA externe au ZIP et HEAD contraint. L'inventaire fermé CI-OPT3 **38 workflows / 5 familles** n'admet que les cinq filtres de cette mission ; ses falsifications préservent les routes historiques. Les artefacts partiels sont conservés en cas de problème, mais **ne qualifient pas** un oracle.

## Acquisition C1 authentique — HEAD 5ff95c76166f69375e7cfbc12c6472f368ea89c1

Acquisition initiale **ROM-backed réellement exécutée** le 09/11/2026 : [A1 GitHub Actions #42588114812](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42588114812). Trois jobs **SUCCESS** (19 tests structurels/synthétiques, acquisition vraie, rejeu indépendant). L'archive RAW [#13660069804](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42588114812/artifacts/13660069804), ZIP SHA-256 `2f0a700577bd2a44426d27e146664eda7c6d947c843824efd24a83e51de74ec5`, contient **226 fichiers de preuve plus le manifeste** ; aucune ROM ni SNA complète. [Sceau hors archive #13660368827](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42588114812/artifacts/13660368827), ZIP SHA-256 `b727cf4f1ab40607c6304b5312a9311298147a16627d86d01ce3c5e31f3e04ed`.

**SHA-256 MANIFESTE externe** : `366c5caaf7276d8e9ed8a11aa986982f1234e21a8cf530b32028d36553c0e19b`, publié séparément dans les logs du job d'acquisition, transmis au job de rejeu et recoupé indépendamment avec le téléchargement RAW. Le rejeu affiche `RAW_REPLAY_PASS`, avec HEAD contraint à `5ff95c76166f69375e7cfbc12c6472f368ea89c1`.

**Deux garde-vitesses indépendantes :** `original=300,310` et `repeat=300,500` ticks par seconde hôte approximative ; mesurent les fenêtres et leurs coûts, pas une cadence absolue garantie ni une vitesse d'exécution CYD. Tous les processus ont été lancés sous CPC6128 128K, avec ROM et exécutable épinglés et config validée. Les deux PNG `boot/screen.png` ont été réellement inspectés : **Amstrad 128K / BASIC 1.1 / Ready**. Les 14 PNG `run/screen.png` (7 cas × 2 sessions) ont été inspectés, et affichent `STOP`, `Break in 15` ou `Break in 25`, `CONT`, `Ready` ; l'écran est pris **après CONT**, le snapshot temporaire au STOP. Une PNG ne prouve pas la valeur de l'imprimante : les `printer.dat` bruts et les fenêtres RAM sont les canaux numériques.

### Matrice REAL5 originale : deux sessions concordantes

Les nombres sous `PRINT` viennent de `run/printer.dat` **dans la même exécution** que la SNA dont `window.bin` est extrait. Les adresses `@T!` imprimées correspondent à l'adresse `(word[&AE68] + 4)` du champ valeur dans la table scalaire ; `@U!` correspond à l'entrée suivante. Les caches et liens de la ROM ne sont pas convertis en données inventées.

| Cas | `PRINT #8,T!` (original = repeat) | 5 octets RAM de `T!` (original = repeat) | `@T!` | `T!*2` | `T!>=0` | `T!>32767` |
|---|---:|---|---:|---:|---:|---:|
| F_ZERO | 0 | `00 00 00 00 00` | 476 | 0 | -1 | 0 |
| F_ONE | 1 | `00 00 00 00 81` | 476 | 2 | -1 | 0 |
| F_NEG_ONE | -1 | `00 00 00 80 81` | 477 | -2 | 0 | 0 |
| F_HALF | 0.5 | `00 00 00 00 80` | 481 | 1 | -1 | 0 |
| F_QUARTER | 1.25 | `00 00 00 20 81` | 481 | 2.5 | -1 | 0 |
| T_DYNAMIC_PAIR | **5256** | **`00 00 40 24 8D`** | **549** | **10512** | -1 | 0 |
| T_LATE_BOUNDED | **50376** | **`00 00 C8 44 90`** | **549** | **100752** | -1 | **-1** |

Dans les deux cas TIME, `U!` est distincte en mémoire (`@U!=558`) et possède les **mêmes cinq octets** que `T!` dans les deux sessions : `U!=5256` puis `U!=50376`. Cela **ne démontre pas** la résolution sub-tick ou une différence entre deux lectures adjacentes. Une nouvelle lecture `PRINT #8,TIME` plus tard dans le même programme donne respectivement **5977** et **51098** (original = repeat), et confirme la progression entre ces sondes, sans simultanéité présumée. `U!>=T!` imprime `-1` dans les deux cas.

**La barrière 32767 est effectivement franchie** : TIME 50376, REAL5 `00 00 C8 44 90`, comparateur `T!>32767=-1`, double 100752. C'est une observation REAL5 de ce nombre précis, **pas** une preuve de conversion universelle, de wrap ou de gamme `uint32_t`. Aucune SNA n'a été livrée ; SHA SNA et offsets d'extraction figurent dans les `stop.json`, et les fenêtres brutes dans `window.bin`.

### Analyse des octets, niveaux de certitude

- **VERIFIED** : code interne `04` de l'entrée scalaire REAL CPC, cinq octets à l'adresse renvoyée par `@T!`, nom `D4` pour T et `D5` pour U (octet ASCII terminé), imprimante cohérente et opérations. C99 `BVT_REAL=05` est un code propre au moteur hôte et ne doit jamais être confondu avec `04` en RAM CPC.
- **VERIFIED sur ces témoins seulement** : zéro tout nul ; `1` à exposant `81`, `0.5` à `80`, `1.25` avec `20` en quatrième octet ; `-1` diffère de `+1` par le bit `80` du quatrième octet ; les deux valeurs TIME ont respectivement les exposants `8D` et `90`. Les octets de mantisse évoluent selon l'ordre de poids **petit vers grand** dans la fenêtre de quatre octets.
- **Hypothèse de codec compatible avec tous les témoins, pas encore contrat global** : un réel non nul positif peut s'écrire `(1 + M / 2^31) * 2^(E - 0x81)`, avec `M` formé par les quatre premiers octets little-endian dont le bit de poids fort du quatrième octet est réservé au signe, et `E` cinquième octet. Cela redonne exactement les deux valeurs 5256 et 50376 ainsi que 0.5/1/1.25 ; `-1` atteste localement le bit de signe. L'arrondi, dénormalisés, valeurs négatives générales, très grandes valeurs, exponentielles limites et overflow **ne sont pas prouvés** par ces exemples.
- **UNVERIFIED** : origine au boot, `RUN` sur d'autres durées, reset complet, règles de wrap, comportement aux limites non atteintes, `ERR/ERL`, décodage REAL5 général et stabilité tick par tick. Les mêmes valeurs entre `original` et `repeat` attestent une procédure déterministe ici, pas une identité temporelle universelle.
- **UNSUPPORTED en A1** : implémentation `uint32_t ticks → REAL5`, `REAL5 → PRINT CPC`, opérateurs REAL natifs, firmware, scheduler et tests sur CYD.

### CI du HEAD d'acquisition C1 : sept familles

- [C99 4 cellules GCC/Clang OFF/ON #42588114804](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42588114804) — SUCCESS.
- [CI-ARCH #42588114616](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42588114616) — SUCCESS.
- [CI-OPT3 #42588114791](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42588114791) — SUCCESS ; 38 workflows / 5 familles, falsifications CLK04 et anciennes intactes.
- [CPC indépendant historique #42588114691](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42588114691) — SUCCESS.
- [CI-CPC-PERMANENT #42588114678](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42588114678) — SUCCESS sur `sealed-evidence` ; les sous-jobs d'acquisition historiques hors route sont SKIPPED, **pas PASS**.
- [CI-XTENSA #42588114628](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42588114628) — les trois profils CONSOLE/HW3/BASIC_PROBE et `profile-guards` SUCCESS ; `po-standard-build` SKIPPED ; aucun test CYD.
- [CLK-04-A1 #42588114812](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42588114812) — 3/3 SUCCESS, tests négatifs 19/19, vrai CPC, sceau indépendant.

**Ce tableau ne qualifie que le HEAD `5ff95c76166f69375e7cfbc12c6472f368ea89c1`.** Toute nouvelle modification documentaire change le HEAD et impose de constater les nouveaux runs de CI et **une nouvelle acquisition CPC** : aucune preuve ancienne n'est réétiquetée pour le HEAD futur.

## Proposition architecturale A2 (NON AUTORISÉE)

Une éventuelle A2 doit être découpée et arbitrée par Pilotage : représenter sans troncature les ticks injectés ; coder seulement une conversion REAL5 explicitement bornée et vérifiée sur la plage/les témoins retenus ; contrôler le formatter PRINT et le calcul `*2` / comparaison `>=` avec les résultats indépendants ; garantir l'atomicité, les erreurs et les budgets. **Aucun format général, politique d'overflow, reset ou conversion implicite `int16_t` n'est autorisé par cette étude.**

A1 reste oracle uniquement. `core/`, `firmware/`, `integration/`, `io/` et `video/` inchangés. `ON_DEVICE_UNVERIFIED`. Acceptation et fusion exclusivement Pilotage.