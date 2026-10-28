# ARCH-HW4-U1-B — retrait de l'ancienne racine ESP-IDF

**Mission Pilotage :** [#142](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/142) ; parent #112 ; préalable [U1-A / PR #141](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/141) fusionné. Base imposée : `main@39cddf37b3a18cdf0852cb70a52d573bcdba7ab1`. Branche : `feat/arch-hw4-u1-b-retire-legacy-probe`.

## Inventaire avant migration

| Racine / consommateur | État au départ U1-B | Décision |
| --- | --- | --- |
| `firmware/esp32_probe/main/main.c` | Unique sonde historique J0.25, ABI/NMIN/REAL5 | Déplacer **sans modifier le blob** sous `firmware/esp32_display_probe/main/basic_probe.c` |
| `firmware/esp32_probe/components/loco_core/CMakeLists.txt` | Unique descripteur ESP-IDF des dix `core/*.c` | Déplacer vers `firmware/components/loco_core/CMakeLists.txt`, n'ajuster que `LOCO_CORE_DIR` |
| `firmware/esp32_probe/scripts/check_build.py` | Contrôle esp32/4 Mio/partitions/radio/PSRAM | Déplacer **à l'identique** dans `tools/ci/check_build.py` |
| `firmware/esp32_probe/scripts/report_abi.py` | Extraction ELF de 16 champs ABI | Déplacer **à l'identique** dans `tools/ci/report_abi.py` |
| `firmware/esp32_probe/CMakeLists.txt`, `main/CMakeLists.txt`, `sdkconfig.defaults`, `partitions.csv` | Deuxième projet et doublons de configuration | Retirer après migration ; les paramètres actifs restent ceux du projet PO |
| `firmware/esp32_display_probe/CMakeLists.txt` et `main/CMakeLists.txt` | Dépendance active au descripteur / source de l'ancienne racine | Rediriger vers composant partagé et fichier local déplacé |
| `.github/workflows/ci-xtensa.yml` | Trois images, dont une ancienne racine autonome, et job U1-A temporaire | Un job permanent 3 profils dans **la racine unique**, sans 4e build |
| `.github/workflows/ci-arch.yml` | Garde sur l'ancien chemin source | Supprimer ce chemin, conserver les tests d'unicité pilote et d'isolement |
| `tools/hw4_c3_a_scope_gate.sh` | Ancien argument de chemin dans la garde historique de diff | Retirer l'argument de l'ancienne racine ; `firmware/components/` reste protégé |
| `README.md` et docs de statut actuels | Instructions pré-U1-B | Décrire la racine conservée et les chemins actifs |
| Documents historiques (J0.25, HW4, U1-A, anciens jalons) | Provenance de builds et de mesures réels de l'ancienne racine | **Conserver** les liens et noms d'origine, ne pas réécrire les archives |

L'inventaire n'autorise **aucune** modification de `core/`, `io/`, `video/`, `firmware/components/cyd_ili9341/`, des oracles, des fixtures, du DMA, de l'UART ou des sources fonctionnelles console/HW3.

## Architecture après migration

Le projet **inchangé pour le PO** est `firmware/esp32_display_probe`, de nom `loco_esp32_display_probe`. `idf.py build` seul dans son répertoire (même `build/`, sans `fullclean`) reste le chemin de production par défaut `CONSOLE`. `HW3` et `BASIC_PROBE` sont sélectionnés en CI avec `LOCO_CYD_PROFILE` et des caches/configurations séparés. Les couples historiques `HW4_C2_CONSOLE=ON/OFF` restent compatibles et les conflits restent des erreurs.

Un `app_main` est choisi dans chaque ELF : `hw4_c2_console.c` / `main.c` / `basic_probe.c`. Les dix fichiers `core/*.c` sont référencés directement par `firmware/components/loco_core` avec `-std=c99` ; aucune copie de source. `cyd_ili9341` reste unique. Les anciennes valeurs `sdkconfig.defaults` de la sonde autonome (pile 4 096) n'ont plus d'application : les trois profils partagent la pile du projet conservé (**6 144**, déjà constatée en U1-A).

La sortie du scanner `python3 tools/ci/check_u1b_retirement.py --scan` doit être PASS ; les documents archivés ne sont **pas** des consommateurs exécutables. Le `--self-test` doit rejeter un appel falsifié de chemin périmé. Aucun travail hors mandat ne doit être réintroduit.

## Préuves et barrières (à renseigner d'après GitHub Actions du HEAD final)

| Preuve | Exigence |
| --- | --- |
| Linux GCC/Clang OFF/ON avec ASan/UBSan | Toutes les suites CTest de main inchangées, résultats de la CI au SHA final |
| CPC / oracle indépendant / ARCH / scroll | Workflows permanents intacts et succès au SHA final ; pas de SKIPPED compté PASS |
| 3 profils Xtensa 5.5.6 | 3 `loco_esp32_display_probe.elf` et `.bin` dans `build-u1-{console,hw3,basic}` |
| Un seul `app_main` / image | `xtensa-esp-elf-nm` pour chaque ELF + tests négatifs 0/2 symboles |
| Appdesc / partitions | Version du commit courant dans les 3 BIN ; 4 Mio sans PSRAM, ESP32, factory 3 Mio |
| ABI / NMIN / REAL5 | Blob de la sonde conservé, 16 champs ELF, valeurs de référence ; scénario de diagnostic inchangé |
| Sélecteurs | 15 positifs/négatifs U1-A permanents, plus erreurs CMake réelles sur nom invalide/collision |
| Outils migrés | `test_u1b_partition.py` : config valide, cible invalide, PSRAM, Wi-Fi, overlap, factory absente, overflow |
| Rémanences | Scan des workflows, scripts et CMake actifs + falsification ; ancienne racine absente |
| Transition PO | Job `po-standard-build` : `main → branche`, même `build/`, `idf.py build` standard et appdesc nouveau SHA |

**Base chiffrée U1-A à comparer à l'artefact U1-B (octets) :**

| Profil | Flash Code U1-A | IRAM U1-A | DRAM U1-A | BIN U1-A |
| --- | ---: | ---: | ---: | ---: |
| CONSOLE | 111 082 | 67 279 | 49 368 | 237 533 |
| HW3 | 82 878 | 67 279 | 31 520 | 208 753 |
| BASIC_PROBE | 74 990 | 51 807 | 31 020 | 166 477 |

Source : [rapport U1-A](ARCH-HW4-U1-A-profiles.md). Référence ABI U1-A : `LocoProbeStorage=19072`, `core_descriptor_bytes=636`, `owned_buffers_and_entries_bytes=18432` ; les **16 champs** sont extraits du nouvel ELF. **Mesures U1-B réelles** — [CI Xtensa #40780780584](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40780780584), commit fonctionnel `7cce9800cf5008fa29b75afb5ad9f067b4ca71ea`, `ESP-IDF v5.5.6` ; **3/3 profils PASS** et `profile-guards` PASS. Le seul delta de répertoire source n'introduit aucune variation des budgets :

| Profil U1-B | Flash Code | IRAM | DRAM | Image | Δ Flash / IRAM / DRAM / image vs U1-A |
| --- | ---: | ---: | ---: | ---: | --- |
| CONSOLE | 111 082 | 67 279 | 49 368 | 237 533 | **0 / 0 / 0 / 0 o** |
| HW3 | 82 878 | 67 279 | 31 520 | 208 753 | **0 / 0 / 0 / 0 o** |
| BASIC_PROBE | 74 990 | 51 807 | 31 020 | 166 477 | **0 / 0 / 0 / 0 o** |

ABI BASIC_PROBE : 16/16 champs et `LocoProbeStorage=19072`, `core_descriptor_bytes=636`, `owned_buffers_and_entries_bytes=18432` (lecture ELF, pas une mesure matérielle). `app_main=1` vérifié pour chaque image. Appdesc sur les trois images : `7cce980`; la transition standard `main → branche` au même cache `build/` a produit `PO_STANDARD_BOOT_SHA=PASS` sur ce même commit. Tests réels des profils invalides et des sélecteurs contradictoires : refus confirmés. Les validations complémentaires sur ce commit sont [C99 4 cellules #40780780801](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40780780801) (83/83 CTest par cellule), [CI-ARCH #40780780568](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40780780568), [CPC permanent #40780780618](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40780780618), [oracle CPC indépendant #40780780677](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40780780677) et [HW4 scroll #40780780511](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40780780511) : **SUCCESS**. Les anciens workflows conditionnels `SKIPPED` ne sont pas comptés PASS.

**La présente actualisation documentaire produit un nouveau HEAD : toutes les vérifications doivent être répétées sur ce HEAD final avant remise.** La comparaison ci-dessus est une preuve du précédent commit fonctionnel, pas un substitut à cette réexécution. Écart > 2 048 octets DRAM ou IRAM CONSOLE : STOP, arbitrage Pilotage. Tout écart Flash/appdesc/ABI doit être expliqué.

## Essai obligatoire du PO sur le SHA final

Après succès de la CI et remise du SHA intégral : **ouvrir le projet VS Code existant**, sélectionner la branche de PR, cliquer Build / Flash / Monitor **sans options ajoutées ni nettoyage**. En CLI si besoin : `cd firmware/esp32_display_probe && idf.py build && idf.py flash monitor`. Relever `version=<SHA court du HEAD>` et vérifier l'accueil `BASIC 1.1`, `Ready`, curseur ; saisir `10 PRINT 2`, `20 PRINT 3`, `LIST`, `RUN`, `NEW`, puis un programme témoin `IF A% THEN` déjà connu, éditer avec gauche / Backspace / Suppr, provoquer des scrolls et `!CLS`. Critères : aucune erreur/panic, comportement identique au SHA U1-A validé, `dma_fault=0`, `dma_timeouts=0` ; fournir heap libre, largest et pile HWM observés. Retour PO **PASS/FAIL + extrait UART** ; photo non demandée.

**État de qualification :** parité Xtensa confirmée sur le commit fonctionnel et CI du HEAD documentaire final à relire ; `ON_DEVICE_UNVERIFIED`. Aucun test matériel ne découle d'une compilation. **La revue, l'acceptation et la fusion de la PR appartiennent au Pilotage. J1.15 et HW4 concurrents restent gelés.**
