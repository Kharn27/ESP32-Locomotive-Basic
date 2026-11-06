# CLK-03 — Oracle CPC6128 indépendant de `TIME`

**Mandat :** [Issue #311](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/311) — GO Oracle uniquement, pas de runtime. **Statut présent : `CPC_ORACLE_UNVERIFIED` — acquisition non exécutée dans l'environnement développeur.**

## Point de départ vérifié et isolement

Base annoncée par le Pilotage : `main@e500864b3be612a325559259250f41cc35b5252b`. Au pré-audit, GitHub renvoie `main@e0085a9e2d3b601359fc44fcfa3ea83430fc7056` (+1 commit #332, diagnostics graphiques : 6 fichiers hors namespace CLK-03). Branche dédiée suggérée `oracle/clk-03-cpc-time`. Les chantiers J1.25-A/B1/B2 et leurs archives, `CLK-01`, `CLK-02`, CI-OPT3 et HW4 restent en lecture seule. Aucun fichier de production, firmware ou workflow modifié.

La configuration historique d'oracle CLK-01 donne comme **références attendues, pas comme constats revérifiés** : Caprice32 commit `8c778bf072a06fb7c23b9cccd179041db7f79a52`, ROM CPC6128 `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562`, image GHCR `sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c`. L'outil d'acquisition refuse les divergences de commit et de ROM, contrôle la version de l'exécutable, et inspecte chaque configuration `model=2`, RAM 128 KiB, `speed=4`, `limit_speed=1`, printer ON et audio OFF. Le texte **BASIC 1.1 sur PNG boot** exige encore contrôle humain ; une config ne suffit pas.

## Ce que la ROM démontre, et ce qu'elle ne démontre pas

Le `basic.asm` de référence indique table des variables internes `TIME` → routine `&D139` (`&D117`), mot-clé préfixé `FF 46` (`&E493`) ; cette routine appelle `KL TIME PLEASE` `&BD0D` puis `&FEA5`. Ceci ne démontre à lui seul ni la fréquence 300 Hz, ni le type numérique effectivement affiché, ni une plage de débordement. `TIME` ne doit être assimilé ni à une durée mur de processus, ni au `RUN_DURATION` CYD. Les assertions RAM `FF 46` ne seront comptées que sur les `program.bin` effectivement extraits d'une SNA CPC6128 temporaire, jamais à partir d'une tokenisation Python.

## Corpus figé avant acquisition

Source exacte en ASCII sérialisé JSON : `tests/fixtures/cpc6128/clk_03_time/corpus.json` ; **SHA-256 fixe** `0b35697d97e7b6c69c2645308805b65e83dfd328a590e3b6d9a8b21607482084`. Chaque source conserve son ordre exact dans le champ `commands` ou `lines`. Aucun résultat attendu de `TIME` n'y figure : seules les **quantités de sondes numériques `PRINT #8`** sont prédéfinies.

| Cas | Contexte et question | Canal à inspecter | Conclusion a priori |
|---|---|---|---|
| D01_DIRECT | Lecture directe rapprochée, `PRINT TIME` écran et deux `CAP32_DELAY` | `printer.dat` + PNG | UNVERIFIED |
| D02_NEW_RUN | Lectures avant/après `NEW`, deux `RUN` puis lecture directe | printer + PNG | UNVERIFIED |
| P01_NUMBERED | `PRINT #8,TIME` stocké | LIST #8, écran et RAM | UNVERIFIED |
| P02_RAPID | Trois lectures successives en RUN | printer + RAM | UNVERIFIED |
| P03_SHORT | Boucle FINIE 300 itérations, avant/après | printer + temps processus isolé | UNVERIFIED |
| P04_LONG | Boucle FINIE 9 000 itérations, avant/après | printer + temps processus isolé | UNVERIFIED |
| P05_EXPRESSION | `TIME*2` et condition `TIME>=0` | printer + LIST/RAM | UNVERIFIED |
| P06_BOUNDARY | Test `TIME>32767` sans forcer le compteur | printer + LIST/RAM | UNVERIFIED / limite non atteinte |
| N01_PARENS | `PRINT TIME(1)` direct | PNG diagnostic, ERR/ERL non sondés | UNVERIFIED |
| N02_ASSIGN | `TIME=0` direct | PNG diagnostic, ERR/ERL non sondés | UNVERIFIED |

Deux sessions indépendantes `original` et `repeat`, chacune avec un démarrage CPC propre par capture. Dans chacune : PNG de boot, paire de mesures de vitesse par deux processus indépendants (`short` 2 × `CAP32_DELAY`, `long` 18 × `CAP32_DELAY`), puis tous les cas. `P*` utilisent un processus de `LIST` + `LIST #8` et une SNA **temporaire** puis un second processus de RUN. Une SNA complète ne doit pas être archivée ; seuls les octets du programme BASIC sous `program.bin` sont conservés. Toutes les commandes exactes, `cap32.cfg`, stdout/stderr/returncode, UTC hôte début/fin, mur hôte, `screen.png`, printer et manifest hashes/taille doivent être préservés.

### Fenêtres et coût des sondes

Le garde de vitesse est celui différentiel de CLK-01, recalculé **par session** : `(delta_ticks_long - delta_ticks_short)/(wall_long - wall_short)`, où chaque `delta_ticks` provient de deux appels `PRINT #8,TIME` dans un processus CPC donné. Critères provisoires 255–345 ticks par seconde hôte, `delta_wall>0,5 s` et `delta_ticks>100` ; les timestamps monotones appartiennent à l'hôte, les ticks au CPC. Ce garde contrôle approximativement le mode nominal ; il n'atteste pas une précision absolue de 300 Hz. Les coûts des appels `PRINT #8`, de la tokenisation, de l'interpréteur, de l'impression et des `CAP32_DELAY` polluent les fenêtres ; ni ratio d'exécution CPU ni précision sub-tick ne seront déduits d'eux. P03/P04 mesurent des deltas CPC entre deux lectures, **pas** une durée mur RUN. Le `RUN` est envoyé après la saisie et se termine avant capture ; l'éventuel temps de sortie/d'interpréteur n'est pas isolé. Aucune boucle infinie.

### Protocole reproductible dans un environnement Caprice32 autorisé

L'acquisition requiert une **autorisation Pilotage pour un workflow dédié** si elle doit être exécutée dans la CI : l'Issue #311 interdit d'ajouter un workflow sans STOP/arbitrage. Sur un poste ayant déjà la chaîne Caprice32 (binaire disponible dans le sous-module épinglé), depuis le checkout exact de la branche :

```sh
python3 tools/clk_03_cpc_time.py --self-test
python3 -m unittest discover -s tests -p 'test_clk_03_time.py' -v
# Exécuter seulement après contrôle manuel de la provenance et du HEAD :
python3 tools/clk_03_cpc_time.py --acquire \
    --caprice tests/oracles/caprice32 \
    --output /chemin/neuf/clk03-raw --head "$(git rev-parse HEAD)"
# Le SHA externe du manifeste doit être consigné HORS du candidat dans l'Issue/CI :
sha256sum /chemin/neuf/clk03-raw/manifest.json
python3 tools/clk_03_cpc_time.py --verify /chemin/neuf/clk03-raw \
    --head "$(git rev-parse HEAD)" --seal SHA256_PUBLIE_EN_CI
```

Le répertoire de sortie doit être absent avant la collecte. Le validateur REFUSE de valider sans **SHA du manifeste publié en dehors de l'archive** et HEAD explicite. Une sortie d'acquisition valide n'est qu'`ACQUIRED_PENDING_SCREEN_REVIEW` : la lecture des PNG et des messages d'erreurs par un humain reste requise. Les logs d'acquisition partielle sont gardés ; le statut n'est pas relevé. Les tests négatifs ne génèrent que des fixtures synthétiques temporaires, jamais archivées comme capture CPC.

## Vérifications et falsifications

`--verify` exige deux sessions distinctes, un ensemble exact de cas, inventaire fichier→(taille, SHA-256), double garde de vitesse, configuration, captures PNG originales, `LIST #8` initial, `program.bin` tokenisé avec `FF 46`, flux numérique `PRINT #8` à cardinalité stricte, fichiers `caprice.log`, commandes `autocmd.json` et horodatages de chaque processus distincts. Les falsifications testées sur hôte : absence de fichier, altération, mauvais sceau, mauvais HEAD, même timestamp session, horloge hors plage, mauvaise config, imprimante ambiguë, session manquante, mauvaise ROM, mauvaise source et commande LIST falsifiée. Des faux fichiers portant des en-têtes PNG peuvent passer des validations superficielles : **seul un sceau indépendant adossé à une exécution effectivement vérifiée dans la CI et une inspection des PNG constitue une provenance expérimentale**. Ne pas présenter l'autotest de structure comme un oracle.

## Tableau à renseigner pour CLK-04 après acquisition réelle

| Question | Source probante à produire | État présent | Conséquence éventuelle pour CLK-04 |
|---|---|---|---|
| Token `TIME` RAM | P01/P02 `program.bin` + `LIST #8` brut | ROM_STATIC_ATTESTED, RAM UNVERIFIED | Lexer/décodeur `FF 46` si confirmé |
| Type BASIC retourné / signe et format | D01, P01, P05 printer + PNG, analyse ROM `&FEA5` | UNVERIFIED | Représentation native à décider **après** preuves ; ni `int16_t` ni REAL5 présupposé |
| Cadence et granularité | Garde indépendant × 2, P02/P03/P04 | UNVERIFIED | API d'horloge injectable envisagée, fréquence à qualifier |
| `NEW`/`RUN` et progression | D02, captures hôte distinctes | UNVERIFIED | Cycle de vie horloge à spécifier |
| Diagnostic et `ERR`/`ERL` | PNG N01/N02, éventuels relevés CPC additionnels non interpolés | UNVERIFIED | Aucun mapping depuis ERR hôte |
| Limite et overflow | P06 et essais plus longs **seulement si horloge atteint seuil** | UNVERIFIED / UNSUPPORTED si non atteinte | Aucun modulo, signe, clamp ou débordement imposé |

Questions `EVERY`/`AFTER`/`REMAIN`/`DI`/`EI` : réservées à CLK-06. Aucun code TIME natif et aucun test CYD dans cette PR. Les CI du HEAD exact seront indiquées seulement après exécution observable.
