# CLK-06-A1 — Oracle CPC6128 indépendant `AFTER` / `REMAIN(0)`

**Mandat exclusivement oracle PC :** [#314, GO Pilotage du 13 novembre 2026](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/314#issuecomment-6851391655). **Base exacte** : `main@4f8264c5b1fd370c185d687f5e03e92fe4c8f1e2`, vérifiée sur GitHub avant branchement. **Branche** : `oracle/clk-06-a1-after-remain` ; les chantiers HW4-MEM-C8-A (#380), BASIC natif et firmware CYD sont strictement hors périmètre. Le Développeur ne fusionne pas.

## État de preuve initial (ne pas confondre préparation et observations)

L'existence du programme BASIC, la reconnaissance statique d'un token dans `basic.asm`, un test hôte avec PNG synthétique et une commande Caprice32 configurée **NE démontrent PAS** le comportement du CPC6128. Les qualifications `OBSERVED` exigent des processus CPC ROM-backed effectivement exécutés, deux sessions indépendantes, des archives intègres et une inspection des écrans. Tant que ces éléments manquent, la case reste `UNVERIFIED` ou `INCONCLUSIVE`, **jamais `CPC_ORACLE_VERIFIED` par anticipation**.

**Références CLK-03 lues, non modifiées :** `docs/CLK-03-cpc-time-oracle.md`, `tools/clk_03_cpc_time.py`, son sous-module `tests/oracles/caprice32`, son parseur de RAM SNA et ses fonctions de configuration, exécution `xvfb-run`, contrôle de vitesse et vérification des PNG. Épingles héritées **à revérifier au runtime** : Caprice32 commit `8c778bf072a06fb7c23b9cccd179041db7f79a52`, ROM CPC6128 `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562`, image GHCR `ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c` ; binaire `/usr/local/bin/cap32` SHA-256 `5170b3fc68ab116e7698e6e68a742e324d0e9dbfd87eeb7b2090e13c639f73eb` observé au premier essai réel du workflow #43836366998. Ces valeurs sont un **contrat de provenance**, pas une déclaration qu'une acquisition A1 a déjà été exécutée.

La référence ROM `basic.asm` a été inspectée : la routine `AFTER` à `&CA22` prépare un ticker par `KL ADD TICKER` (`&BCE9`) ; `REMAIN` à `&CA50` utilise `KL DEL TICKER` (`&BCEC`), avec validation de canal à `&CA62` ; tokens `AFTER=&80`, `REMAIN=FF 13`, `GOSUB=&9F`, `RETURN=&C9` (ce dernier corrigé après examen des octets RAM acquis à la première tentative). Ce sont des **indices de ROM statiques**, non une preuve de cadence, d'ordre d'exécution ou de valeur de retour à l'écran. Aucun `TIME` **natif** n'est ajouté ; le garde d'émulation CLK-03 observe `TIME` CPC seulement pour détecter une vitesse hôte incohérente. Aucune fréquence 1/50 s n'est présupposée.

## Huit expériences BASIC distinctes, finies et ré-acquérables

Sources ASCII exactes : `tests/fixtures/cpc6128/clk_06_a1_after_remain/sources/*.bas`. Un manifeste JSON fixe l'ordre et les fenêtres de capture **sans contenir de sortie attendue** : `tests/fixtures/cpc6128/clk_06_a1_after_remain/corpus.json`, SHA-256 `4f1120f76ff52f9cab67a83da82623a6e6fd23711db432eec3622a38c187d443`. L'outil vérifie aussi l'égalité octet-pour-octet de chaque fichier `.bas` et de son tableau `lines`.

| Sonde | Question historique à observer, sans verdict anticipé | État avant acquisition |
|---|---|---|
| `A01_NEVER_ARMED` | `REMAIN(0)` avant tout armement et après une boucle bornée | `UNVERIFIED` |
| `A02_ARM_FIRE` | `AFTER 10,0 GOSUB` ; événement et `RETURN` puis continuité du main | `UNVERIFIED` |
| `A03_ONESHOT` | `AFTER 1,0 GOSUB` : absence ou présence de livraisons multiples pendant une boucle longue mais finie | `UNVERIFIED` |
| `A04_CANCEL_EARLY` | `REMAIN(0)` aussitôt après `AFTER 250,0` ; annulation/délai retourné, puis handler éventuel | `UNVERIFIED` |
| `A05_REMAIN_AFTER_FIRE` | `REMAIN(0)` après fenêtre d'exécution d'un timer court | `UNVERIFIED` |
| `A06_REARM_SAME_CHANNEL` | Deux `AFTER` successifs sur le canal 0 vers deux handlers distincts | `UNVERIFIED` |
| `A07_NESTED_RETURN` | Handler du timer avec `GOSUB` imbriqué, deux `RETURN`, puis marqueur du main | `UNVERIFIED` |
| `A08_BAD_ARGUMENT` | `AFTER -1,0` : diagnostic **réel** à relever sur capture écran, sans présumer de l'erreur | `UNVERIFIED` |

Chaque programme se termine par `END` ou une sous-routine `RETURN` ; tous les `FOR ... NEXT` ont une borne fixe. La longueur des fenêtres d'automatisation `CAP32_DELAY` est fixée avant capture, non convertie artificiellement en ticks CPC ; un `RUN` interrompu/non terminé doit être déclaré `INCONCLUSIVE`, jamais comptabilisé dans 8 cas qualifiés. L'état de `ERR/ERL` reste `UNVERIFIED` tant qu'il n'a pas été réellement acquis.

## Acquisition en deux sessions CPC fraîches

La session `original` et la session `repeat` exécutent chacune **un boot indépendant**, deux gardes de vitesse `TIME` host/CPC empruntés à CLK-03, puis les huit cas. **Chaque sonde** lance **deux processus Caprice32 distincts** : `list` pour saisir le programme, acquérir `LIST` à l'écran, `LIST #8` dans `printer.dat`, une SNA **temporaire** et le `program.bin` réellement extrait de RAM ; `run` pour saisir à nouveau le même programme, `RUN`, capturer l'écran final et le flux brut de l'imprimante. Des commandes et temps de début/fin de chaque processus sont enregistrés. Aucune SNA complète ni ROM n'est archivée. Il n'y a ni exécuteur BASIC local, ni génération d'une réponse attendue depuis Python.

```bash
# Préflight hôte : aucune preuve CPC ne sort de ces commandes.
python3 tools/clk_06_a1_oracle.py --check-sources
python3 tools/clk_06_a1_oracle.py --self-test
python3 -m unittest discover -s tests -p 'test_clk_06_a1_oracle.py' -v

# À exécuter UNIQUEMENT dans la chaîne Caprice32/ROM épinglée et
# sur un checkout propre du HEAD exact (ou workflow isolé de cette PR) :
python3 tools/clk_06_a1_oracle.py --acquire \
  --caprice tests/oracles/caprice32 \
  --output /chemin/ABSENT/clk06-a1-raw \
  --head "$(git rev-parse HEAD)"
sha256sum /chemin/ABSENT/clk06-a1-raw/manifest.json
# Sceau EXTERNE obligatoire, publié dans logs GitHub acquisition et artefact séparé :
python3 tools/clk_06_a1_oracle.py --verify /chemin/ABSENT/clk06-a1-raw \
  --head "$(git rev-parse HEAD)" --seal SHA256_DU_MANIFEST_PUBLIE_HORS_ARCHIVE
```

L'acquisition CI est proposée dans le workflow isolé `.github/workflows/clk-06-a1-acquisition.yml` (déclencheurs limités à ses cinq routes). Elle échoue **sans** commit Caprice32 correct, sans ROM exacte, sans binaire Caprice disponible, sans corpus conforme, sans snapshot RAM exploitable, sans PNG intègre ou sans copie complète des seize processus. Les fichiers partiels sont conservés avec `status=ACQUISITION_PARTIAL`, **pas un PASS**. La publication externe du SHA manifeste est indépendante de l'archive téléchargée par un second job et liée au HEAD de la PR. Le coffre d'artefacts de GitHub Actions est provisoire (rétention 90 jours) : sa présence n'est pas un scellement permanent en dépôt.

## Replay, falsifications et limites strictes

Le vérificateur exige un `--head` 40 hex, un **sceau SHA-256 externe** 64 hex et leur accord avec le manifeste. Il exige le corpus fixe, la chaîne Caprice32/ROM/GHCR épinglée, deux sessions fraîches, 8 × 2 pièces LIST+RUN, fichiers d'automatisation et config, timestamps de processus distincts, logs `returncode=0`, les 16 `program.bin` et leurs tokens CPC issus de SNA, les listes réelles `LIST #8`, les fichiers imprimante RUN, PNG structurellement complets (chunks CRC et flux zlib) et l'inventaire intégral taille+SHA-256. Il refuse les sources mutées, observations auto-déclarées comme écran déjà interprété, absence ou ajout de fichier, insertion `.sna`/`.rom`, mauvais HEAD, manifeste/signature modifiés et paramètres de provenance incorrects. Les **fixtures falsifiées des tests unitaires sont exclusivement temporaires et marquées synthétiques**, jamais archivées comme sessions Caprice32.

**Frontière résiduelle :** un en-tête PNG et une archive correctement hachée ne prouvent pas que l'écran affiche le programme attendu ; le contrôle visuel des `boot/list/run` (BASIC 1.1, `LIST`, erreurs, `Ready` final), les valeurs affichées et l'ordre exact des messages restent indispensables. `RAW_REPLAY_PASS` n'est pas le verdict sémantique `CPC_ORACLE_VERIFIED`. Une sonde absente, non interprétable ou en cours d'exécution = `INCONCLUSIVE` ou `UNVERIFIED`. Ni type numérique ni cadence timer ne seront extrapolés des nombres imprimés sans expériences supplémentaires.

## CI, conflits et remise

Les workflows historiques, `tools/clk_03_cpc_time.py`, les sceaux CPC, `core/`, `firmware/`, `integration/`, `video/`, `hal/`, `io/`, CMake et tous les scripts de RAM/IRAM sont **inchangés**. `HW4-MEM-C8-A` n'est ni lu ni modifié. **Point de décision CI :** le routeur `CI-OPT3` possède une liste fermée de workflows. Le GO A1 autorise un workflow isolé additif, mais l'enregistrement de ce nouveau workflow dans le routeur partagé `tools/ci/opt3_routing.py` est une modification commune nécessitant un arbitrage Pilotage si le gate la refuse. Ne pas élargir soi-même le routeur ni toucher à un workflow historique. En cas de CI-OPT3 rouge, **noter le blocage, ne pas prétendre la CI verte**.

**Qualification finale à compléter seulement avec les vrais artefacts acquis :** URL du run sur HEAD, SHA externe, inventaire, vérification séparée, inspection humaine des PNG, table des octets d'imprimante originaux/repeat et conclusion distincte pour chaque cas. Tout élément non acquis reste `UNVERIFIED`. **Oracle PC uniquement : `ON_DEVICE_NOT_APPLICABLE_A1` ; aucun test CYD ni passage à CLK-06-A2/CLK-07.**

### Première acquisition réelle partielle — preuve de falsification négative

[Workflow #43836366998](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/43836366998) : Caprice32, ROM et binaire GHCR ont passé les vérifications, et le collecteur a capturé des octets `program.bin` et des sorties `printer.dat` originaux. L’acquisition s’est interrompue **avant 8 × 2** avec `CPC_RAM_TOKEN_MISSING_RETURN` : un contrôle local avait confondu le token `RETURN=&C9` avec `&1D` présent dans un message d’erreur ROM. L’artefact partiel [#14210788068](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/43836366998/artifacts/14210788068) reste non qualifié. Les vrais octets de la ligne 1020 du `program.bin` A02 finissent par `C9 00`, confirmant le token à vérifier ; la première ligne `REMAIN(0)` de A01 contient `FF 13`. Aucune conclusion globale du timer n’est tirée de cette tentative. Les vérifications ont été renforcées avec la véritable empreinte du binaire du conteneur.
