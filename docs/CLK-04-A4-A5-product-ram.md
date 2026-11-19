# CLK-04-A4-A5 — Produit T!*2, REAL5 RAM indépendante

Mandat Pilotage : [#394](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/394) et [#312](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/312#issuecomment-7006884156). **ORACLE CPC UNIQUEMENT** : aucun TIME natif, CORE, firmware, ESP-IDF ou CYD.

## Gel avant acquisition

Base initialement demandée : main@ce449f27cf704c12bc8b852fe773290f253dd7f3. GitHub, à l'ouverture du chantier : main@5bead95481d062cba2c1003a78226ad9a752eb64, soit le squash de #393 entre les deux. Branche créée depuis ce main réactualisé, sans réécrire aucun fichier de #393 et sans modifier le routeur OPT3 partagé.

Corpus : tests/fixtures/cpc6128/clk_04_a4_numeric/a5_product_ram/corpus.json, **3966 octets**, SHA256 **09a132467b71aed8c55e9c8691948c350b921dce5b1195f3af26ace0adfd600c** ; Git blob b2bc5168253122655b053eb855cc36484649918a, commit de gel 15f967cf02a43bdfff076556b57c8d704109e887. [Publication du gel avant acquisition](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/394#issuecomment-7007060559).

Valeurs distinctes (8 cas, deux sessions original/repeat) : **0, 1, 32767, 32768, 65536, 8388608, 2147483648, 4294967295**. Chaque source CPC effectue 10 T!=n, 20 U!=T!*2, STOP 90, puis PRINT #8,@T!, @U!, T!, U!, T!*2. Les grandes valeurs ont un témoin R! indépendant provenant des méthodes déjà utilisées par A2/A4 (2^15, 2^16, 2^23, 2^31, (2^32)-1) et vérifient T!=R!, (R!+1)-R!, R!-(R!-1). Aucun témoin R! ne sert à fabriquer les octets U! : **la ROM calcule réellement U!**.

## Preuve indépendante

Le collecteur A5 réutilise **en lecture seule** les utilitaires A4, A1 et CLK-03 : Caprice32, ROM CPC6128 1.1, speed gate, LIST/program.bin, SNA STOP transitoire, tableau scalaires &AE68/&AE6A et fenêtre RAM, adresses/type 04 et 5 octets bruts **T! et U!**, CONT, imprimante byte-exact et photos PNG STOP/CONT, plus boot de chaque session. **Aucun byte de REAL5 n'est reconstruit à partir du PRINT ou du candidat C99.** SNA et ROM ne sont pas archivés.

Un manifeste compte chaque membre, sa taille et SHA256, lie HEAD/corpus/ROM/Caprice/image et les identités des deux boots. Son SHA256 est publié **hors RAW**, dans un second artefact. Sur un runner distinct, le rejeu refuse toute anomalie de sceau, HEAD, source, noms/type, pointeurs, fenêtre T!/U!, membres/tailles/SHA, session ou cardinalité, avant d'appeler le **candidat C99 A4 inchangé**. Sont séparés dans le rapport : RAW_INPUT_REAL5_CPC, RAW_PRODUCT_REAL5_CPC, RAW_PRINT_CPC, C99_CANDIDATE, résultat CANDIDATE_MATCH/MISMATCH par valeur et session. Une divergence C99 n'est pas un échec d'acquisition ni une falsification des octets CPC ; elle reste inscrite explicitement.

## CI et garde de périmètre

Seul le workflow existant .github/workflows/clk-04-a4-numeric-pipeline.yml gagne les trois jobs A5 host/acquisition/replay. La politique tools/ci/clk_04_a4_fast_route.py est étendue de manière strictement additive : une modification du nouveau sous-dossier A5 ne réactive pas les 240 RAW historiques A4 ; les anciennes entrées A4 relancent toujours leur FULL. Pas de nouveau workflow, pas de changement tools/ci/opt3_routing.py, des fixtures/scellés A4 ou des fichiers #393. Tests négatifs : le seul U! altéré, type, nom, adresse, octets du programme, source, corpus, manifeste, sceau, HEAD, ROM/image, inventaire, séances, nombre de captures et candidat. Les tests C99 A4 GCC/Clang ASan/UBSan sont conservés ; aucune bibliothèque de production n'est modifiée.

Image GHCR inchangée : sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c. Caprice32 commit 8c778bf072a06fb7c23b9cccd179041db7f79a52. ROM CPC6128 SHA256 31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562.

**Vérification à la remise** : 16 produits (8 valeurs × 2 vrais boots) et hash externe, logs/artefacts/head CI, captures boot/STOP/CONT revues humainement. Une CI PASS seule ne qualifie pas l'examen PNG. Les statuts ne sont avancés qu'après preuves réelles ; un manque demeure UNVERIFIED.

**Limites hors domaine** : uint32 global, encodage REAL5 universel, imprimante exponentielle générale, origine/wrap/reset et exécution TIME native. Pas d'essai CYD ; ON_DEVICE_UNVERIFIED. Aucune phase B ni A6 lancée sans mandat Pilotage.
