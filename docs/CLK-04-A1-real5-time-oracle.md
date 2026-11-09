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

## Matrice de preuve (à remplir UNIQUEMENT après acquisition)

| Objet | État initial | Condition de promotion |
|---|---|---|
| Token `FF 46` et `LIST #8` | `CLK-03 VERIFIED`, A1 `UNVERIFIED` | RAM et LIST réels du corpus A1 |
| Octets REAL5 `0,1,-1,0.5,1.25` | J1.16-E-A indépendamment prouvé pour A, A1 `UNVERIFIED` pour `T!` | Fenêtre RAM + `@T!` + même `PRINT #8,T!` |
| `T!=TIME` et `U!=TIME` | `UNVERIFIED` | Deux snapshots de sessions indépendantes + adresses et valeurs liées, sans synthèse |
| `T!*2`, `T!>=0`, `U!>=T!` | `UNVERIFIED` | Imprimante brute effectivement acquise et comparée |
| Valeur TIME au-delà de 32767 | `UNSUPPORTED` | Lecture originale strictement supérieure à 32767 pendant la fenêtre bornée |
| Format au-dessus de la plage mesurée, arrondi, signe de TIME et wrap | `UNVERIFIED/UNSUPPORTED` | Nouvelles observations, **non induites** par les fixes |
| Origine/reset TIME, `ERR/ERL`, simultanéité de `TIME` et `T!` | `UNVERIFIED` | Aucun comportement inventé |
| Codec natif, cible ESP32 / CYD | `UNSUPPORTED` en A1 / `ON_DEVICE_UNVERIFIED` | Mandat distinct après décision Pilotage |

## Architecture à soumettre au Pilotage (aucun code natif A1)

Une future tranche A2 devra distinguer (i) représentation des ticks 32 bits à leur échelle brute, (ii) **conversion numérique CPC** réellement qualifiée en cinq octets REAL5, (iii) opérations REAL5 minimales pour `TIME*2` et `TIME>=0`, (iv) sortie numérique CPC et diagnostic d'erreur atomique. **Aucune politique de dépassement, de wrap, d'arrondi ou de reset n'est spécifiée sans témoin.** Les octets bruts, valeurs décimales et comparateurs doivent être mis en correspondance sans confondre leur provenance. Le découpage en PR(s) A2 est une **proposition pour arbitrage**, pas une autorisation.

**CI et acquisition : en attente de résultats du HEAD exact.** Ne pas classer `CPC_ORACLE_VERIFIED` avant sceau externe, rejeu indépendant et inspection humaine des PNG boot/STOP. Ne pas publier de SNA ou de ROM. Les problèmes d'acquisition doivent rester visibles sous `CPC_NUMERIC_UNVERIFIED` jusqu'à correction démontrée.