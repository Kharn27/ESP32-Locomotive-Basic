# J1-DIAG-RETRO-A1b — Unexpected NEXT : locus réel, sans mutation

**Mandat :** [#233](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/233) ; dette transverse [#195](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/195). **Base contrôlée :** `main@e76de5c57a39ff9c383129c6d1faaa7babab96e9` (A1a #227 fusionnée, PAPER B1 déjà dans main). Le Pilotage reste seul compétent pour accepter et fusionner.

## Oracle CPC indépendant, portée exacte

L'[audit A0](J1-DIAG-RETRO-A0-native-error-inventory.md) et `tests/diag_retro_a0_matrix.json` lient les PNG ROM-backed CPC6128 des acquisitions J1.12-A **original / repeat** aux deux textes d'écran lus humainement :

| Scénario scellé | Source BASIC J1.12-A | Erreur affichée et Ready |
|---|---|---|
| `F_NEXT_ORPHAN` | `10 PRINT #8,77` ; `20 NEXT I%` ; `30 PRINT #8,88` | `Unexpected NEXT in 20`, puis un `Ready` |
| `F_NEXT_WRONG_VAR` | `10 FOR I%=1 TO 2` ; `20 PRINT #8,I%` ; `30 NEXT J%` | `Unexpected NEXT in 30`, puis un `Ready` |

Les tests natifs de `PRINT` ordinaires ne revendiquent **pas** d'équivalence de la sortie imprimante CPC `#8`. Renumérotations et `:` sont des **dérivés hôtes**, pas de nouvelles observations ROM. Le statut `BE_*` et le texte `ERROR` hôte ne sont pas des codes `ERR/ERL` CPC.

## Localisation et algorithme

Au `FOR` ligne 10, `for_match()` examine structurellement les enregistrements suivants **avant** de commettre l'affectation ou la boucle ; si `NEXT J%` est à la ligne 30, il renvoie `BE_NEXT_VARIABLE_MISMATCH` **depuis le FOR L10**. Le curseur d'exécution conserve donc L10. Il est incorrect de l'utiliser comme numéro du NEXT fautif.

**Interface C99 de consultation uniquement :** `be_next_fault_line(executor, reason, &line)`, acceptant exclusivement `BE_NEXT_WITHOUT_FOR` / `BE_NEXT_VARIABLE_MISMATCH`. La fonction **rejoue la passe de validation sans effets** de `execute_line()` pour le record et la reprise du curseur inchangés ; `for_match()`, scan borné avec sa pile locale fixe de huit clés, renseigne le **numéro de l'enregistrement NEXT réellement visité** uniquement lorsqu'un nom discordant est détecté. Un NEXT atteint directement renseigne son record courant. Il faut que le statut recalculé coïncide exactement avec la cause annoncée et que le locus soit non nul. Sinon `false`, `*line_number` intact.

**Coût :** au plus un scan O(taille du programme) supplémentaire **sur l'échec NEXT seulement** ; aucun heap, tampon variable, stockage de défaut dans `BasicExecutor`, ni modification des deux passes normales de `be_step_events()` hormis un pointeur optionnel toujours NULL durant RUN. Le scan interprète les débuts d'instructions, les caches variables et littéraux, les guillemets, REM et séparateurs CPC : ne cherche pas le premier octet `B0` arbitraire.

**Politique centrale :** `io/cpc_diag_policy_step()` exige `BSR_EXECUTOR_ERROR`, RUNNING, programme cohérent, record courant valide, cause NEXT sélectionnée et résultat de relecture identique ; assigne alors catégorie et provenance typées `CPC_DIAG_NEXT_UNEXPECTED / CPC_DIAG_ORIGIN_NATIVE_NEXT_CPC_ORACLE`. Aucune extension à `BE_FOR_WITHOUT_NEXT`, `BE_INTEGER_OVERFLOW` ou autre erreur. `format_step()` produit **exactement** `Unexpected NEXT in <n>\n`, formatage décimal borné sans allocation, préflight de capacité et sans écriture partielle. `CPC_DIAG_HOST_GENERIC` conserve `ERROR\n` lorsqu'une origine ne correspond pas ; une combinaison fabriquée catégorie/provenance est rejetée.

**CONSOLE :** seule la chaîne de provenance des logs `CPC_NEXT_ORACLE` est ajoutée au raccord A1a **existant**, avant `bsr_stop()`. Le diagnostic de l'écran vient toujours de `cpc_diag_policy_write_step` ; ni double `Ready`, ni nouveau routeur/scheduler/quantum/BREAK/DMA/UART. C'est un chevauchement de **une ligne logique** avec #226 dans `hw4_c2_console.c`, à résoudre contradictoirement par Pilotage en cas d'évolution de main.

## Tests RED→GREEN et preuves à relever sur HEAD final

- **RED isolé :** [PR de preuve non fusionnable #234](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/234), commit `1652d2d07348d1c3a0b2a86051ab116a8c848632` : seulement deux assertions CPC natives dans CTest A1a, moteur initial intact. Attendre les résultats Actions avant de prétendre une preuve RED.
- **GREEN :** CTest existant `j1_diag_retro_a1a_gosub_return`, étendu sans toucher à `CMakeLists.txt` : témoins A0 et répétitions, lignes >255, `NEXT` orphelin après sortie antérieure, `NEXT` dans la même ligne après `:`, pre-scan de `FOR`, traces `PRINT \"NEVER\"` non produites, vérification `Ready` unique, faux statut/cursor/token/provenance, capacité courte, atomicité complète buffers/événements/compteurs/store/frame/records et FOR/NEXT correct. Négatifs `BE_FOR_WITHOUT_NEXT` / `BE_INTEGER_OVERFLOW`, GOTO/IF, GOSUB/RETURN, PEN et sorties vidéo des suites historiques.
- **Historique :** `python3 tools/j1_diag_retro_a0_verify.py --self-test` et CI CPC-PERMANENT inchangés.
- **CI :** GCC + Clang, ASan/UBSan OFF/ON, ARCH, OPT3, Xtensa ESP-IDF v5.5.6 BASIC_PROBE/CONSOLE/HW3 à relever sur le **même HEAD**. Comparer les tailles/sections du profil CONSOLE entre ce HEAD et la base ci-dessus. Ne jamais confondre target-build et CYD physique.

## Protocole obligatoire au PO — CYD, uniquement après gel du HEAD

Carte ESP32-2432S028R **sans PSRAM**, profil `CONSOLE`, UART `115200`, ESP-IDF **5.5.6**, console CPC écran 320×240. Le PO relève le SHA complet depuis GitHub et celui du checkout, ainsi que `App version` réellement affiché au boot (souvent SHA abrégé). Ne pas flasher un binaire de #226, #232 ou une autre branche.

~~~sh
git fetch origin
git switch --detach <SHA-COMPLET-A1B-GELE>
git rev-parse HEAD
cd firmware/esp32_display_probe
idf.py -DLOCO_CYD_PROFILE=CONSOLE build
idf.py -p /dev/ttyUSB0 flash monitor
~~~

Dans le terminal série, entrer **une ligne à la fois**, attendre écho/Ready, conserver le journal UART intégral. Chaque `NEW` isole un scénario. Le `Ready` initial du boot n'entre pas dans le compte après l'erreur.

~~~basic
NEW
10 PRINT "BEFORE"
20 NEXT I%
30 PRINT "NEVER"
RUN
LIST
NEW
10 FOR I%=1 TO 2
20 PRINT "NEVER"
30 NEXT J%
40 END
RUN
LIST
NEW
500 PRINT "BEFORE"
620 NEXT I%
700 PRINT "NEVER"
RUN
NEW
410 FOR I%=1 TO 2
510 PRINT "NEVER"
790 NEXT J%
900 END
RUN
NEW
550 PRINT "BEFORE":NEXT I%:PRINT "NEVER"
RUN
NEW
10 FOR I%=1 TO 2
20 PRINT I%
30 NEXT I%
40 END
RUN
LIST
NEW
10 FOR I%=1 TO 2
20 PRINT "NEVER"
RUN
NEW
10 GOSUB 999
20 PRINT "NEVER"
RUN
NEW
10 RETURN
RUN
NEW
10 PEN 16
RUN
~~~

Attendus **par scénario** : (1) `BEFORE`, puis **`Unexpected NEXT in 20`** et **un `Ready`** ; (2) **`Unexpected NEXT in 30`** (pas `in 10`), un `Ready`, jamais `NEVER` ; (3) `BEFORE`, puis **`Unexpected NEXT in 620`** ; (4) **`Unexpected NEXT in 790`** (pas `in 410`) ; (5) **`Unexpected NEXT in 550`**, sans `BEFORE` ni `NEVER` de cette même ligne (échec atomique) ; (6) FOR/NEXT correct : deux impressions numériques puis Ready **sans** Unexpected NEXT ; (7) `ERROR` générique FOR sans NEXT ; (8) `Line does not exist in 10` ; (9) `Unexpected RETURN in 10` ; (10) `Improper argument in 10`. Les `LIST` après échec restent inchangés.

**PASS** seulement si texte + numéro exacts, Ready **une seule fois** par échec, sortie bloquée, intégrité LIST et absence de reboot/erreur DMA ou LCD. **FAIL** dès divergence. Pièces demandées : HEAD complet, `App version`/ESP-IDF et profil compilé, log intégral build/flash/monitor UART horodaté, photo/vidéo lisible des diagnostics et Ready (photo indispensable si écart écran/UART), compteurs heap libre/max bloc/pile, `dma_fault=0`, `dma_timeouts=0`, retour écran/lcd. **Seul le PO effectue la validation physique.** Tant que celle-ci n'est pas attestée sur le HEAD gelé : `ON_DEVICE_UNVERIFIED` et **aucune fusion**.

## Exclusions et barrières

Aucune modification des oracles historiques, `CMakeLists.txt`, entrées BASIC, exécution FOR/NEXT, registre ERR/ERL, A1a GOSUB/RETURN, PEN #203, scheduler RUN-BREAK #226, ESC-BREAK #232, vidéo ou firmware au-delà de la seule étiquette de provenance au raccord A1a. Aucun A2 ni PAPER B2. Après PR : revue et décision exclusivement Pilotage.
