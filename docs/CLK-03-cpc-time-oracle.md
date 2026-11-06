# CLK-03 — Oracle CPC6128 indépendant de `TIME`

**Mandat :** [Issue #311](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/311) — GO Oracle uniquement, pas de runtime. **Statut borné : acquisition CPC6128 ROM-backed + inspection des PNG réalisées au HEAD `ca23abe1d055beba29036352e0445f9bd645f8e6` ; le dernier HEAD de la PR doit être réacquis indépendamment.**

## Point de départ vérifié et isolement

Base annoncée par le Pilotage : `main@e500864b3be612a325559259250f41cc35b5252b`. Au pré-audit, GitHub renvoie `main@e0085a9e2d3b601359fc44fcfa3ea83430fc7056` (+1 commit #332, diagnostics graphiques : 6 fichiers hors namespace CLK-03). Branche dédiée suggérée `oracle/clk-03-cpc-time`. Les chantiers J1.25-A/B1/B2 et leurs archives, `CLK-01`, `CLK-02`, CI-OPT3 et HW4 restent en lecture seule. Aucun fichier de production, firmware ou workflow historique modifié. Seul le workflow isolé `clk-03-acquisition.yml` a été ajouté sous le mandat C1, avec corrections ciblées du collecteur suite aux échecs réels.

Les contrôles **réellement exécutés au run CLK-03-C1 #42223246629** confirment les références épinglées, initialement tirées de CLK-01 : Caprice32 commit `8c778bf072a06fb7c23b9cccd179041db7f79a52`, ROM CPC6128 `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562`, image GHCR `sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c`. L'outil d'acquisition refuse les divergences de commit et de ROM, contrôle la version de l'exécutable, et inspecte chaque configuration `model=2`, RAM 128 KiB, `speed=4`, `limit_speed=1`, printer ON et audio OFF. Le texte **BASIC 1.1 sur PNG boot** exige encore contrôle humain ; une config ne suffit pas.

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

## Tableau initial CLK-04 (plan pré-acquisition ; la matrice qualifiée C1 ci-dessous prévaut)

| Question | Source probante à produire | État présent | Conséquence éventuelle pour CLK-04 |
|---|---|---|---|
| Token `TIME` RAM | P01/P02 `program.bin` + `LIST #8` brut | ROM_STATIC_ATTESTED, RAM UNVERIFIED | Lexer/décodeur `FF 46` si confirmé |
| Type BASIC retourné / signe et format | D01, P01, P05 printer + PNG, analyse ROM `&FEA5` | UNVERIFIED | Représentation native à décider **après** preuves ; ni `int16_t` ni REAL5 présupposé |
| Cadence et granularité | Garde indépendant × 2, P02/P03/P04 | UNVERIFIED | API d'horloge injectable envisagée, fréquence à qualifier |
| `NEW`/`RUN` et progression | D02, captures hôte distinctes | UNVERIFIED | Cycle de vie horloge à spécifier |
| Diagnostic et `ERR`/`ERL` | PNG N01/N02, éventuels relevés CPC additionnels non interpolés | UNVERIFIED | Aucun mapping depuis ERR hôte |
| Limite et overflow | P06 et essais plus longs **seulement si horloge atteint seuil** | UNVERIFIED / UNSUPPORTED si non atteinte | Aucun modulo, signe, clamp ou débordement imposé |

Questions `EVERY`/`AFTER`/`REMAIN`/`DI`/`EI` : réservées à CLK-06. Aucun code TIME natif et aucun test CYD dans cette PR. Les CI historiques du HEAD d'acquisition `ca23abe1d055beba29036352e0445f9bd645f8e6` sont référencées ci-dessous ; toute modification ultérieure du HEAD impose recontrôle.


## C1 — Acquisition réelle et inspection indépendante du 6 novembre 2026

Cette section prévaut sur les champs `UNVERIFIED` du **plan pré-acquisition**, sans transformer un résultat limité en conformité CPC générale. Le mandat C1 a explicitement autorisé l'ajout isolé du workflow `.github/workflows/clk-03-acquisition.yml`, sans changement CI-OPT3 ni code de production.

**Chaîne authentifiée :** [run #42223246629](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42223246629), acquisition et rejeu **SUCCESS** sur code HEAD `ca23abe1d055beba29036352e0445f9bd645f8e6`. [RAW, artefact #13504053999](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42223246629/artifacts/13504053999), 203 fichiers (202 pièces scellées + manifeste) ; [sceau externe, artefact #13503574721](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42223246629/artifacts/13503574721). Le hash a été publié **dans le log du job d'acquisition**, puis transmis au job de rejeu distinct par `GITHUB_OUTPUT` et artefact séparé :

```
SHA256(manifest.json)=39a1930254d3248474037c95721b1bbc8acb0f9db7c3af5728d1e869b5107dce
acquisition_head=ca23abe1d055beba29036352e0445f9bd645f8e6
```

Contrôles indépendants après téléchargement : présence **203/203**, hashes et tailles conformes **202/202** ; sceau externe identique au SHA du manifeste ; absence de fichier `.rom` ou `.sna`. Chaque `program.bin` provient de la SNA temporaire du processus CPC, jamais d'une conversion Python de la source. L'image GHCR épinglée a été lancée par GitHub Actions, le commit du sous-module et le SHA de ROM ont été vérifiés dans le job ; les deux `boot/screen.png` ont été réellement inspectés et affichent **Amstrad 128K Microcomputer / BASIC 1.1**. Les configurations originales indiquent `model=2, ram_size=128, speed=4, limit_speed=1, printer=1`, audio désactivé. Les 10 cas ont été exécutés dans deux groupes `original` / `repeat`, avec instances Caprice32 propres et timestamps distincts.

### Deux gardes de cadence indépendants

| Session | delta ticks LONG − SHORT | delta mur hôte LONG − SHORT | taux différentiel observé |
|---|---:|---:|---:|
| original | 4512 | 15,012041588 s | **300,558719715 ticks/s** |
| repeat | 4512 | 15,022539743 s | **300,348681194 ticks/s** |

Le taux est **observé dans ces fenêtres**, et non une garantie de précision absolue de la source CPC. `CAP32_DELAY` est un mécanisme de pilotage de l'automate, pas un chronomètre ; le temps mur des processus inclut boot/sorties. Les coûts de `PRINT #8` et d'exécution BASIC restent inclus. Aucune comparaison directe avec `RUN_DURATION` CYD.

### Matrice réelle des dix cas — original = repeat sur sorties numériques

| Cas | Observations directement acquises et inspectées | Qualification bornée |
|---|---|---|
| `D01_DIRECT` | imprimante `738, 1074, 2238` ; `PRINT TIME` visible à l'écran entre les lectures ; `Ready` final | `VERIFIED` : lecture directe positive et progression |
| `D02_NEW_RUN` | imprimante `738, 1170, 1844, 1940, 2274`, dans cet ordre après `NEW`, deux `RUN` puis lecture directe | `VERIFIED` : croissance dans cette session ; généralisation reset/boot `UNVERIFIED` |
| `P01_NUMBERED` | `LIST #8` brut `10 PRINT #8,TIME`, `20 END` ; `program.bin` commence par `0C 00 0A 00 BF 20 23 16 2C FF 46 00` ; `PRINT #8` en RUN `1172` | `VERIFIED` : token RAM `FF 46` et LIST réel |
| `P02_RAPID` | imprimante `1988, 1992, 1994`, incréments `+4` et `+2` | `VERIFIED` : progression rapide observée ; résolution d'un seul tick `UNVERIFIED` |
| `P03_SHORT` | `2253, 2357` : `104` ticks entre sondes, FOR fini 300 tours | `VERIFIED` : delta dans cette fenêtre |
| `P04_LONG` | `2277, 5239` : `2962` ticks entre sondes, FOR fini 9000 tours ; `Ready` final dans les deux PNG | `VERIFIED` : delta long dans cette fenêtre |
| `P05_EXPRESSION` | `TIME*2` produit `3880`, `IF TIME>=0 THEN PRINT #8,1` produit `1` ; `Ready` | `VERIFIED` : expression et condition ; type interne exact `UNVERIFIED` |
| `P06_BOUNDARY` | `TIME=1724` à la première sonde ; `TIME>32767` donne `0` dans les deux RUN | `VERIFIED` pour l'expression au-dessous du seuil ; **borne/overflow `UNSUPPORTED`** car non atteint |
| `N01_PARENS` | capture écran originale **et repeat** : `PRINT TIME(1)` affiche deux valeurs `738` puis `1`, puis `Ready` ; **pas d'erreur** | `VERIFIED_NO_ERROR` : ne pas assimiler à un appel de fonction avec argument sans examen syntaxique |
| `N02_ASSIGN` | capture écran originale **et repeat** : `TIME=0` affiche exactement **`Syntax error`**, puis `Ready` | `VERIFIED_SCREEN_DIAGNOSTIC` ; `ERR`/`ERL` `UNVERIFIED` (non interrogés) |

Les PNG sont les canaux probants pour `Ready`, `Syntax error` et `PRINT TIME(1)`. Les flux `printer.dat` sont probants pour les valeurs numériques, et `program.bin` pour les octets RAM ; ces canaux **ne sont jamais substitués entre eux**. Le corpus ne démontre ni écriture/assignation valide de `TIME`, ni comportement de remise à zéro après reset CPC, ni débordement, ni signe ou représentation native précise (`int16_t` / REAL5 / `uint32_t`), ni échelle sous-tick. Les valeurs identiques entre les deux runs correspondent à cette configuration automatisée, pas à une garantie de comportement global.

### Échecs réels corrigés, sans mutation du corpus

- [Premier essai #42222304992](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42222304992) : `SNA_MISSING` ; le collecteur envoyait par erreur le littéral `CAP32_SNAPSHOT`. Le correctif appelle les véritables touches `\x0c\x0d` comme l'outillage historique de Caprice32. Archive partielle conservée, **non qualifiée**.
- [Deuxième essai #42222714387](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42222714387) : `TIME_AMBIGUOUS_PRINTER` sur `P04_LONG`, car le screenshot montrait `RUN` en cours et une seule lecture sur `printer.dat`. Le correctif augmente uniquement l'attente de capture à 16 `CAP32_DELAY` pour P04 ; aucun changement aux 9000 itérations. Archive partielle conservée, **non qualifiée**.
- [Troisième essai #42223246629](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42223246629) : **3/3 jobs SUCCESS**, `RAW_REPLAY_PASS`, sources ROM-backed et PNG inspectés.

### CI / limites à remettre au Pilotage

Au HEAD d'acquisition `ca23abe1d055beba29036352e0445f9bd645f8e6`, les CI **C99, ARCH, CPC indépendant historique et CPC-PERMANENT** sont `SUCCESS`, les **13/13** tests synthétiques et le `--self-test` également. **CI-OPT3 est `FAILURE` : `UNKNOWN_OR_MISSING_WORKFLOW`**, car son inventaire n'admet pas le nouveau workflow CLK-03. Le mandat C1 **interdit** toute modification de CI-OPT3 et des workflows existants : un arbitrage supplémentaire du Pilotage reste nécessaire pour rendre ce gate vert. Cette réserve est indépendante de la fidélité de `TIME` acquise. Pas d'essai CYD (oracle-only), pas de code TIME natif, pas de suite CLK-04. Le scénario d'acquisition doit être reproduit et les sceaux contrôlés **sur le HEAD final exact** après la présente documentation.

**Conséquence proposée pour CLK-04, sans lancer ce jalon :** l'API d'horloge injectable devra pouvoir fournir des lectures monotones et être testée indépendamment ; ni le type BASIC interne, ni sa gamme complète, ni une politique de débordement ne peuvent être arrêtés à partir de ces seuls témoins. Le Pilotage reste seul compétent pour décider de l'architecture et de la fusion.
