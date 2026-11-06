# J1-DIAG-RETRO-A4 — provenance des diagnostics graphiques CPC

**Mandat :** [Issue #331](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/331) ; **base :** `main@4d261f2a76374ab99a4dd7415cae7a097330c46b` (six CI de démarrage SUCCESS). Périmètre : `io/cpc_diag_policy.[ch]`, labels de provenance `integration/hw4_run_diag_source.h`, suites de tests existantes. Pas de CORE, firmware, CMake partagé, workflow, archive CPC ou changement de l'exécution vidéo.

## Acquisition et indépendance

Oracle **Amstrad CPC 6128 / Locomotive BASIC 1.1** en vrai Caprice32 avec ROM SHA-256 `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562`. Les trois archives immuables sont `tests/fixtures/cpc6128/j1_18_a_ink/`, `j1_19_a_paper/` et `j1_23_a_locate_border/`. Les détails de scellement, ports ROM et limites d'acquisition sont conservés dans [INK](J1.18-A-ink-cpc-oracle.md), [PAPER](J1.19-A-paper-cpc-oracle.md) et [LOCATE/BORDER](J1.23-A-locate-border-cpc-oracle.md).

**Contrôle effectué par le DÉVELOPPEUR :** les 26 PNG `RUN` original/repeat ci-dessous ont été ouverts directement depuis GitHub et relus **visuellement sans OCR** ; leurs **SHA-256 ont été recalculés sur les octets PNG réellement récupérés** avec une implémentation SHA-256 indépendante, vérifiée préalablement sur `SHA256(abc)=ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad`, puis confrontés aux empreintes des captures/manifests. Les vingt-quatre PNG positifs de diagnostic correspondent au texte indiqué ; les deux derniers `L_MISSING` sont une contradiction préservée, pas un témoin « Improper argument ». Aucun PNG n'est modifié. Ne pas interpréter `ERR` comme texte écran.

## Matrice source → record BASIC CPC → cause native → texte écran

Les bytes indiquent **le record complet de la ligne fautive** : mot longueur LE, numéro de ligne LE, corps tokenisé, zéro final. Le reste du programme (REM, PRINT marqueur, END) est conservé dans les archives. Pour chaque ligne, les deux captures CPC indépendantes original et repeat ont été relues ; les SHA sont ceux du **PNG RUN visible**, pas du `program.bin`.

| Cas / source exacte | Record CPC HEX de la ligne | Cause `BEStatus` / ERR-ERL imprimé | Graphie PNG et catégorie |
|---|---|---|---|
| `I1626` — `10 INK 16,26` | `0C 00 0A 00 A2 20 19 10 2C 19 1A 00` | `BE_INVALID_INK`, 5/10 | `Improper argument in 10` — **VERIFIED / CPC_ORACLE** |
| `IN126` — `10 INK -1,26` | `0C 00 0A 00 A2 20 F5 0F 2C 19 1A 00` | `BE_INVALID_INK`, 5/10 | `Improper argument in 10` — **VERIFIED / CPC_ORACLE** |
| `I132` — `10 INK 1,32` | `0B 00 0A 00 A2 20 0F 2C 19 20 00` | `BE_INVALID_INK`, 5/10 | `Improper argument in 10` — **VERIFIED / CPC_ORACLE** |
| `I1N1` — `10 INK 1,-1` | `0B 00 0A 00 A2 20 0F 2C F5 0F 00` | `BE_INVALID_INK`, 5/10 | `Improper argument in 10` — **VERIFIED / CPC_ORACLE** |
| `P16` — `20 PAPER 16` | `09 00 14 00 BA 20 19 10 00` | `BE_INVALID_PAPER`, 5/20 | `Improper argument in 20` — **VERIFIED / CPC_ORACLE** |
| `PN1` — `20 PAPER -1` | `09 00 14 00 BA 20 F5 0F 00` | `BE_INVALID_PAPER`, 5/20 | `Improper argument in 20` — **VERIFIED / CPC_ORACLE** |
| `L_00_01` — `10 LOCATE 0,1` | `0A 00 0A 00 A9 20 0E 2C 0F 00` | `BE_INVALID_LOCATE`, 5/10 | `Improper argument in 10` — **VERIFIED / CPC_ORACLE** |
| `L_01_00` — `10 LOCATE 1,0` | `0A 00 0A 00 A9 20 0F 2C 0E 00` | `BE_INVALID_LOCATE`, 5/10 | `Improper argument in 10` — **VERIFIED / CPC_ORACLE** |
| `L_NEG_01` — `10 LOCATE -1,1` | `0B 00 0A 00 A9 20 F5 0F 2C 0F 00` | `BE_INVALID_LOCATE`, 5/10 | `Improper argument in 10` — **VERIFIED / CPC_ORACLE** |
| `B_NEG` — `10 BORDER -1` | `09 00 0A 00 82 20 F5 0F 00` | `BE_INVALID_BORDER`, 5/10 | `Improper argument in 10` — **VERIFIED / CPC_ORACLE** |
| `B_NEG_01` — `10 BORDER -1,1` | `0B 00 0A 00 82 20 F5 0F 2C 0F 00` | `BE_INVALID_BORDER`, 5/10 | `Improper argument in 10` — **VERIFIED / CPC_ORACLE** |
| `B_MISSING` — `10 BORDER 1,` | `09 00 0A 00 82 20 0F 2C 00` | `BE_OPERAND_MISSING`, 22/10 | `Operand missing in 10` — **VERIFIED / CPC_ORACLE** |
| `L_MISSING` — `10 LOCATE 1` | `08 00 0A 00 A9 20 0F 00` | `BE_DIAG_CONTRADICTORY`, 0/10 (!) | `Syntax error in 10 (éditeur)` — **CONTRADICTORY / HOST** |

## Références PNG originales et répétées — SHA-256 recalculés

| Cas | PNG original RUN / SHA-256 | PNG repeat RUN / SHA-256 |
|---|---|---|
| `I1626` | [original](../tests/fixtures/cpc6128/j1_18_a_ink/original/I1626/run/screen.png) — `731c95b4a6ab7e0b82b18def3a9abad5556b7511142cce8d7e9782aa9dbfebb1` | [repeat](../tests/fixtures/cpc6128/j1_18_a_ink/repeat/I1626/run/screen.png) — `2d7f7472cdafc258fe00a09a12edb3d85223435b5e2d72c1d24199206f01ea71` |
| `IN126` | [original](../tests/fixtures/cpc6128/j1_18_a_ink/original/IN126/run/screen.png) — `82879bfb61cb3129099e21620d952dfe063001469a91b754ee01c130727c7ef3` | [repeat](../tests/fixtures/cpc6128/j1_18_a_ink/repeat/IN126/run/screen.png) — `c0f800b0f78866ec6e71dee961475838b9ec982d7469ded72c6ce26adfcb05c5` |
| `I132` | [original](../tests/fixtures/cpc6128/j1_18_a_ink/original/I132/run/screen.png) — `f778cc7b8d3d8895ed78ba8f28c02e71ae8956e184581fcafd233b9d3fc0c9f4` | [repeat](../tests/fixtures/cpc6128/j1_18_a_ink/repeat/I132/run/screen.png) — `b74c05e40b7ba367317531a7a18fbfbe2df8edd7d9958809886456d4f61ded5a` |
| `I1N1` | [original](../tests/fixtures/cpc6128/j1_18_a_ink/original/I1N1/run/screen.png) — `19d526e97c1a784b575c5ae932ccd661ef70208828e7df297887785342ad3fbf` | [repeat](../tests/fixtures/cpc6128/j1_18_a_ink/repeat/I1N1/run/screen.png) — `bd13b56cf00e0f0018167214b619eca8579d08c300cbddb779adb57697e11219` |
| `P16` | [original](../tests/fixtures/cpc6128/j1_19_a_paper/original/P16/run/screen.png) — `887d6ff2fb7d92e2d1708e463f4a884e776edb8432ca315e366cb0c25fa51a00` | [repeat](../tests/fixtures/cpc6128/j1_19_a_paper/repeat/P16/run/screen.png) — `7b3d830699116d7d282fa436540f5d9cacb42c14301c4f699ae41100a0883e4e` |
| `PN1` | [original](../tests/fixtures/cpc6128/j1_19_a_paper/original/PN1/run/screen.png) — `ce370a18d99fb7b0aebc3b96f6d3622f622889e147ba91d387a41bc27b988139` | [repeat](../tests/fixtures/cpc6128/j1_19_a_paper/repeat/PN1/run/screen.png) — `b33d2a7f6096928f1c44a208db55df0fc9dfa0ee8e4e740d7bbe63462239a443` |
| `L_00_01` | [original](../tests/fixtures/cpc6128/j1_23_a_locate_border/original/L_00_01/run/screen_1.png) — `d51c72e4fad358db6ed2e7c75a251625a2ca743aff7007c3addaf6e1b3718a2d` | [repeat](../tests/fixtures/cpc6128/j1_23_a_locate_border/repeat/L_00_01/run/screen_1.png) — `3127d5f8ba9f349f8495b95b087e2884cf7ff6280ad7fc5a4f1382dee504c079` |
| `L_01_00` | [original](../tests/fixtures/cpc6128/j1_23_a_locate_border/original/L_01_00/run/screen_1.png) — `4ef40bc3eb0e56dc4613e96c5668a5c526f38d97fa6f83608ecc2e139e5b0015` | [repeat](../tests/fixtures/cpc6128/j1_23_a_locate_border/repeat/L_01_00/run/screen_1.png) — `a46e1165f738db26292610bb77884bb98b0433ccb43436195c2ed910856deba3` |
| `L_NEG_01` | [original](../tests/fixtures/cpc6128/j1_23_a_locate_border/original/L_NEG_01/run/screen_1.png) — `3105961b54ef342aa3cba06452f6a4fc2d401ab184c8203d1bd4922ff29214ef` | [repeat](../tests/fixtures/cpc6128/j1_23_a_locate_border/repeat/L_NEG_01/run/screen_1.png) — `6a2bcaaffa856e612a1e099c7f0273d0c7a4f249435b9a17c8ae2fb0178bf397` |
| `B_NEG` | [original](../tests/fixtures/cpc6128/j1_23_a_locate_border/original/B_NEG/run/screen_1.png) — `6bffb645173e7b51e9e9ab1735de37e8a457748e04ebbeefb33b62fd52af09c0` | [repeat](../tests/fixtures/cpc6128/j1_23_a_locate_border/repeat/B_NEG/run/screen_1.png) — `6bffb645173e7b51e9e9ab1735de37e8a457748e04ebbeefb33b62fd52af09c0` |
| `B_NEG_01` | [original](../tests/fixtures/cpc6128/j1_23_a_locate_border/original/B_NEG_01/run/screen_1.png) — `73b0deac7d4c93d5dd46ca39894865a839705b46250a6b98e6180b58d095c61b` | [repeat](../tests/fixtures/cpc6128/j1_23_a_locate_border/repeat/B_NEG_01/run/screen_1.png) — `b538ce17114d0bc02161b753c2b72fc0620c2ccd3d5c9737fe3e8a25a48a53ce` |
| `B_MISSING` | [original](../tests/fixtures/cpc6128/j1_23_a_locate_border/original/B_MISSING/run/screen_1.png) — `270167f0e715582711cc75a7fcf473c05579b19e29408425b88da90e84ee00ac` | [repeat](../tests/fixtures/cpc6128/j1_23_a_locate_border/repeat/B_MISSING/run/screen_1.png) — `142554aae50b7e2ce85f774677ece533ebda4c3ee2c3f9b62b8f5d0196a4ccb6` |
| `L_MISSING` | [original](../tests/fixtures/cpc6128/j1_23_a_locate_border/original/L_MISSING/run/screen_1.png) — `387561768285b627cee98ed7db3eb099ba9cea39c727604bec06228223e1062d` | [repeat](../tests/fixtures/cpc6128/j1_23_a_locate_border/repeat/L_MISSING/run/screen_1.png) — `8f06d9afafd671fa9df9ea2fc8650810982bbda7584461d4af3d9500790d1389` |

## Règle précise de promotion CPC

- `cpc_diag_policy_step` exige `BSR_EXECUTOR_ERROR` dans un **BSR_RUNNING réel**, `bp_next` du vrai record courant, `statement_offset=0`, stockage valide, type de faute exactement `BE_INVALID_INK / PAPER / LOCATE / BORDER` ou `BE_OPERAND_MISSING`. Chaque famille exige **égalité octet-à-octet du corps complet** avec l'un des **douze** témoins `VERIFIED` ci-dessus ; aucun scanner de sous-chaîne, REM, guillemets, cache, continuation `:`, autre opérande ou variante de grammaire.
- La **prévisualisation native sans commit** de `be_preview_step_events` doit retrouver la **même erreur** sur le même curseur. Une cause forgée, un échec `BSR_SESSION_ERROR`, un `VIDEO_REJECT`, une défaillance DMA/BUF, un token inconnu, un faux record, une mutation des bytes ou un locus erroné reste `HOST_GENERIC = ERROR\n`.
- Catégories et origines **append-only** ; `BEStatus` n'est jamais interprété comme un registre `ERR/ERL` historique. Seul l'affichage CPC validé est transcrit. Le numéro `N` sort du vrai record et peut être 10, 20 ou 620 dans les tests ; **620 est une variation hôte, pas une nouvelle preuve CPC originale**.
- Le formatter écrit **`Improper argument in N\n`** ou **`Operand missing in N\n`**, sans `Ready`. Le caller préexistant émet `Ready` exactement une fois. Capacité trop courte, catégorie/origine incohérente et ligne zéro ne doivent pas écrire un octet ni changer le compteur.
- **Exclusions et contradictions conservées** : `LOCATE 1` affiche `Syntax error in 10` **avec éditeur activé**, mais l'imprimante ERR/ERL vaut **0/10** dans les deux sessions : `BE_DIAG_CONTRADICTORY` reste `HOST` ; aucune « correction » automatique. Les formes positives `INK 1,27`, `INK 1,31`, `LOCATE 41,1`, `LOCATE 1,26`, `BORDER 27` restent acceptées. Aucune borne nouvelle. Aucun support direct nouveau. Le périmètre PEN/GOSUB/GOTO/IF/RETURN/NEXT/WHILE/WEND et A3 doit demeurer inchangé.

## Preuves RED → GREEN et plan CI

- Commit **RED** `8bcee4c53a02672ca3874caf4b0a5381da300e7d` : [CI-C99 #42206469105](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42206469105), échec du CTest `j1_diag_retro_a1a_gosub_return` attendu sur `expect_diagnostic` : la catégorie était `HOST_GENERIC` pour le premier témoin `INK`.
- Commit IO initial GREEN `ece810a5cbf110e9482336cbeb199c223262475e` : [CI-C99 #42206962468](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42206962468), **4/4 cellules SUCCESS, 131/131 CTests par cellule** (GCC/Clang × ASan/UBSan OFF/ON).
- Vérifications à conserver au **HEAD de remise final** : C99 4 cellules, ARCH, OPT3, CPC-PERMANENT et Xtensa BASIC_PROBE/CONSOLE/HW3 3/3, avec SHA, lien et comparaison Flash_Code/IRAM/DRAM contre `main@4d261f2…`. Les tests A4 sont ajoutés aux CTests existants, **pas** à un nouveau job ou workflow.
- Négatifs A4 : faux BEStatus/état/locus, altération d'opcode, troncature, fausse longueur de record, espaces/colon non attestés, REM/chaîne, variantes valides 27/31, `BE_UNSUPPORTED` et `BE_DIAG_CONTRADICTORY`, retour renderer/HOST, tampons trop courts, `Ready` unique, intégrité du programme, du store, du curseur, des buffers/events/VRAM à l'échec. Étiquette `HOST_VERIFIED` uniquement après CI à un SHA identifié.

## Protocole court pour essai physique PO si exigé par Pilotage

**`ON_DEVICE_UNVERIFIED`** : il n'existe aucune preuve de flash CYD à ce HEAD ; l'essai physique n'est **pas un prérequis automatique** de cette correction d'affichage si Pilotage estime les BSR/CI suffisants.

Sur ESP32-2432S028R (CYD), profil CONSOLE, ESP-IDF 5.5.6, UART 115200 et **SHA final validé par Pilotage** :

```sh
git fetch origin
git checkout --detach <SHA_A4_APPROUVE_PILOTAGE>
cd firmware/esp32_display_probe
idf.py -DLOCO_CYD_PROFILE=CONSOLE build
idf.py -p /dev/ttyUSB0 flash monitor
```

Après chaque `NEW`, saisir les lignes puis `RUN` : `10 INK 16,26`, `10 INK -1,26`, `10 INK 1,32`, `10 INK 1,-1`, `20 PAPER 16` (avec `10 REM J119-P16`), `20 PAPER -1` (avec `10 REM J119-PN1`), `10 LOCATE 0,1`, `10 LOCATE 1,0`, `10 LOCATE -1,1`, `10 BORDER -1`, `10 BORDER -1,1`, `10 BORDER 1,` ; ajouter une ligne ultérieure `PRINT "NEVER"` comme canari. Attendre `Improper argument in N` sur les onze premières formes, `Operand missing in 10` sur la dernière, puis **une seule** occurrence de `Ready`. Les origines UART attendues sont `CPC_INK_ORACLE`, `CPC_PAPER_ORACLE`, `CPC_LOCATE_ORACLE`, `CPC_BORDER_ORACLE`. Vérifier que le `LIST` reste intact, que `NEVER` n'est pas exécuté, que l'écran/LCD fonctionne et qu'il n'y a ni redémarrage ni panne DMA.

**Retour à Pilotage si essai prescrit** : SHA réellement flashé, logs build/flash/monitor, photo des messages, `heap_free`, `max_free_block`, marge pile, `dma_fault` / `dma_timeouts` et état TFT si disponibles. Ne jamais fabriquer les métriques absentes. Aucun auto-merge ou mandat A5/B2/CLK-03.
