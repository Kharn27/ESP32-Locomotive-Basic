# HW4-MEM-C6-B2-B — huit builds Xtensa réels pour PR #330 (#351)

**Statut : prototype LAB additif, NON-required, NON fusionné tant que Pilotage ne l'accepte pas.** Cette campagne ne modifie aucun seuil A0, RENDER-A, C3, C5 ni l'état de #330. Aucun test matériel CYD.

## Références indépendantes et candidat

Le mandat fige `M=6d3aae8a95b97e18174d758f35ef240740e9a861` et la paire **GitHub réelle** de #330 :

- `B=4d261f2a76374ab99a4dd7415cae7a097330c46b` : `PR #330.base.sha`, **distinct de M**.
- `H=64b0087d5087903fee175c4f149c65a65bb43fe6` : `PR #330.head.sha`.
- Git merge-bases `MB(M,H)` et `MB(B,H)` : toujours vérifiés à la source au démarrage.
- GitHub preview historique `28e0a1585b204c55e533c284328e9bc797b23492`, parents `(e620c3b1…,H)`, **PREVIEW_STALE_MAIN** : jamais utilisé comme C.
- `C_TEST_MERGE_REPRODUCIBLE` : `git merge-tree --write-tree M H` (deux calculs concordants), puis `git commit-tree TREE -p M -p H`, identités auteur/committer/dates fixes, parents `(M,H)` et arbre revérifiés. Le commit de test reste dans l'espace CI **local et non publié**. Un conflit ou un arbre différent entraîne STOP. C n'est ni un commit GitHub de merge réel, ni une fusion de main.

## Budget : huit cellules exactement, aucune substitution

| Canal | SPI40 | SPI20 | Comparaison |
|---|---|---|---|
| `PR_INCREMENTAL` | B, H | B, H | vraie base GitHub #330 contre son HEAD |
| `INTEGRATION_CANDIDATE` | M, C | M, C | main scellé contre test-merge M+H |

**Une cellule = un `idf.py set-target esp32` puis un `idf.py build` dans un répertoire CMake et sdkconfig propre.** Aucun cache entre les sept nouvelles cellules, et une seule réutilisation **explicite, vérifiée bit-à-bit** de B/SPI40 du premier run. Budget global **1 + 7 = 8**. Les fichiers ELF/map/BIN du B40 proviennent exclusivement de l'artefact authentifié du run initial #42657443478 (artifact #13691574947, ZIP digest `sha256:2c8d0970691abde46233004fccee96ac1e78be3a39c44d14bd7c3f5d0ed5380c`). L'original `SHA256SUMS.txt` porte le digest fixé `9d7304aeeaaf64bb522f390fd2f25a55fdc19c2111621a19b36193144387ef55`. Le CLI refuse un artefact d'une autre run/HEAD, vérifie tous les fichiers de l'original, les arbres SHA Git B/H/M/C, le conteneur et les flags, et recopie B40 byte-for-byte sans nouvelle compilation. Le script contrôle les refs GitHub (y compris la PR du LAB) avant et après **chaque** nouvelle cellule. Drifts → `MEASUREMENT_INVALID`, même si plusieurs cellules ont déjà réussi. Pour relancer après échec, nouvel arbitrage Pilotage afin de respecter la limite de huit builds.

## Reproductibilité, intégrité et contrôle de source

- Runner GitHub Actions sur branche de travail contrôlée ; `permissions: contents: read`, `pull-requests: read`, `actions: read`. Pas de `pull_request_target`, write, promotion de gate ou `continue-on-error`.
- Un job adversarial hôte précède la campagne chère. Aucun token dans les tests hôte.
- Le contrôleur `tools/ci/hw4_mem_c6_b2b.py` appartient au HEAD authentifié de la **PR LAB #351**, pas au code source #330. Le checkout Git est `fetch-depth: 0`, `persist-credentials: false`. Aucun script arbitraire de #330 n'est exécuté avec un jeton GitHub ; le Docker build ne reçoit aucune variable `GH_TOKEN`/`GITHUB_TOKEN`.
- ESP-IDF `v5.5.6`, image `espressif/idf@sha256:bf72fe7a15c22849a9a94147301165a545fb8905d97c176cf748e3e4614cac84`, GCC 14.2.0/ld 2.43.1 validés par le comparateur **C5 inchangé**. Profil `CONSOLE`, `CYD_LCD_SPI_HZ=40000000` ou `20000000`, `-DLCD_CLOCK_HZ=<horloge>U` dans la **vraie compilation HAL**.
- Artefacts par cellule : `firmware.elf`, `firmware.map`, `firmware.bin`, `sections.txt`, `sdkconfig`, `CMakeCache.txt`, `compile_commands.json`, versions IDF/GCC/ld, `source.json` avec SHA Git complet, tree, ID image Docker, profil/fréquence, run-id/attempt/HEAD LAB et SHA256 exacts, journaux de build. `SHA256SUMS.txt` recouvre tous les artefacts présents. Les sept caractères de l'app descriptor BIN ne suffisent **pas** : les arbres et commit IDs complets sont revérifiés.

## Verdicts séparés

Chaque canal compare indépendamment `iram`, `dram` (BSS inclus), BSS, flash text/rodata, parité SPI40/20 (IRAM/DRAM identiques, BIN différents, sdkconfig identiques), absence d'accroissement IRAM/DRAM, budget C3 DRAM absolu au maximum 54 864 et coût B3 entre 0 et 696. Un dépassement prouvé → `FAIL`, preuve incomplète/provenance incorrecte → `MEASUREMENT_INVALID`. `PR_INCREMENTAL_VERDICT` ne pilote jamais `INTEGRATION_MEMORY_VERDICT`, et inversement. Même deux `PASS` ne donnent jamais `INTEGRATION_READINESS=READY`.

**Contrainte de version de l'image historique B/SPI40 :** le véritable BIN contient le descripteur ESP-IDF `app_version="1"` et non le SHA Git. Le validateur C5 historique a donc arrêté le premier run après un build complet avec `EMBEDDED_APP_VERSION_MISMATCH`, `MEASUREMENT_INVALID`. Le validateur additif C6 accepte ce format non identifiant **uniquement en plus des preuves indépendantes** commit Git complet, arbre de source, manifestes SHA256, version ESP-IDF/toolchain, CMake, compilation HAL, app descriptor du projet. La version applicative `"1"` n'est **jamais** une preuve d'identité source. Les anciens scripts C5 et leur contrat restent inchangés. La cellule B/SPI40 réutilisée conserve sa provenance d'origine, et le rapport identifie séparément l'ancien run. Cette procédure s'arrête si la moindre identité diverge.

**Anciens contrats explicitement hors rebaselining :** RENDER-A historique `FAILURE` (+220 IRAM connu), C3 historique `FAILURE` (+220 IRAM), A0 `HISTORICAL_DEBT` (+1136 DRAM sur le témoin), `ROOT_CAUSE_UNVERIFIED`, `ON_DEVICE_UNVERIFIED`. Les vieux contrôles n'ont pas été exécutés ici comme nouvelles références. Les CI automatiques Xtensa habituelles ne font pas office de ces huit builds.

## Limite du prochain changement de main

Les mesures M/C sont valables **uniquement pour M et C identifiés par Git SHA/arbres dans cet artefact**. Si la PR du LAB est fusionnée, `main` avancera, et ce résultat n'est plus une mesure sur le nouveau `main`. Le Pilotage peut demander une nouvelle qualification M'/C' ; seuls les builds B/H inchangés peuvent éventuellement être réutilisés **avec preuves bit-à-bit source/toolchain/config/horloge** et mandat distinct. La campagne actuelle ne fait **aucune** prévision de squash ou de readiness #330.

## Commandes et retour

Sur une PR LAB dédiée et une CI de confiance, le workflow `hw4-mem-c6-b2-b-xtensa.yml` lance les tests hôte puis :

```bash
python3 tools/ci/hw4_mem_c6_b2b.py \
  --workspace "$GITHUB_WORKSPACE" \
  --output "$GITHUB_WORKSPACE/reports/hw4-mem-c6-b2-b" \
  --reuse "$GITHUB_WORKSPACE/reports/c6b2b-prior"
```

Code `0` : **deux comparaisons complètes et conformes au contrat incrémental** (pas de conformité historique ni de fusion) ; `1` : régression réelle dans au moins un canal ; `2` : preuve invalide/STOP (pas de verdict mémoire PASS). Le rapport `verdict.json` nomme chaque canal ; `invalid.json` fait foi lorsque la mesure ne peut pas être qualifiée. Tout retour non nul reste un job CI en échec, avec artefacts incomplets clairement marqués, sans `continue-on-error`.

**Statut après le premier run interrompu :** une vraie cellule B/SPI40 construite, 7 non lancées ; les deux verdicts demeurent `MEASUREMENT_INVALID`. La tentative corrective 1+7 doit être qualifiée sur SON HEAD et ses artefacts, sans rebaptiser les preuves du premier run.

**Statut avant nouvelle exécution réelle :** `PR_INCREMENTAL_VERDICT=UNVERIFIED`, `INTEGRATION_MEMORY_VERDICT=UNVERIFIED`, `INTEGRATION_READINESS=BLOCKED_HISTORICAL_DEBT` et **aucun résultat chiffré** n'est présumé dans cette documentation. La remise développeur doit ajouter le HEAD, le run, les sources/trees de B/H/M/C, les huit métriques et les preuves réellement observées, ou déclarer STOP.