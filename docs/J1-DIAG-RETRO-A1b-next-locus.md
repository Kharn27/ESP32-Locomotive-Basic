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

**Interface C99 de consultation uniquement :** `cpc_diag_policy_next_locus(executor, reason, &line)`, dans `io/cpc_diag_policy.[ch]`, acceptant exclusivement `BE_NEXT_WITHOUT_FOR` et `BE_NEXT_VARIABLE_MISMATCH`. `BE_*` provient de l'étape réelle `BSR_EXECUTOR_ERROR` ; une consultation seule ne transforme jamais une erreur en code CPC.

La relecture **lexicale bornée** du programme tokenisé à partir du `cursor/statement_offset` courant valide le NEXT direct, ou suit le NEXT réellement rencontré lors d'un précontrôle structurel de `FOR`. Elle compare les clés explicites INTEGER (type+nom), les imbrications FOR/NEXT (pile locale fixe de huit clés), les débuts d'instructions, guillemets, REM/apostrophes, caches variables et payloads CPC. Elle renvoie le numéro du **record NEXT effectivement discordant**, jamais celui du FOR anticipateur. En cas de statut hors NEXT, absence de NEXT cohérent, structure tronquée, nom correct, curseur invalide ou provenance fausse : `false` et sortie intacte.

**Coût :** O(taille du programme) de lecture **uniquement sur l'échec NEXT** ; aucune allocation, aucun tampon variable, aucune écriture dans l'exécuteur, la pile, le magasin, le programme ou les événements. Pour satisfaire le gate existant `CI-ARCH` qui **interdit toute modification simultanée de `core/` et `io/`**, la relecture ciblée est localisée dans la politique diagnostic **sans changer core/basic_executor.[ch]**. Elle ne se substitue pas à la sémantique FOR/NEXT native et ne revendique aucune généralisation à des grammaires non attestées.

**Politique centrale :** `io/cpc_diag_policy_step()` exige `BSR_EXECUTOR_ERROR`, RUNNING, programme cohérent, record courant valide, cause NEXT sélectionnée et relecture lexicale montrant la même catégorie de NEXT fautif ; assigne alors catégorie et provenance typées `CPC_DIAG_NEXT_UNEXPECTED / CPC_DIAG_ORIGIN_NATIVE_NEXT_CPC_ORACLE`. Aucune extension à `BE_FOR_WITHOUT_NEXT`, `BE_INTEGER_OVERFLOW` ou autre erreur. `format_step()` produit **exactement** `Unexpected NEXT in <n>\n`, formatage décimal borné sans allocation, préflight de capacité et sans écriture partielle. `CPC_DIAG_HOST_GENERIC` conserve `ERROR\n` lorsqu'une origine ne correspond pas ; une combinaison fabriquée catégorie/provenance est rejetée.

**CONSOLE :** le raccord A1a **déjà fusionné** appelle `cpc_diag_policy_step()` avant `bsr_stop()`, puis `cpc_diag_policy_write_step()` ; ce chemin imprime le texte CPC de NEXT sans modifier le firmware. Son log de provenance A1a conserve le libellé générique (`HOST_NOT_CPC_ERR`) pour NEXT, tandis que la catégorie/provenance **typées exactes** sont disponibles dans la politique ; cette limite de télémétrie n'affecte pas le rendu. **CI-ARCH interdit CORE+HW4 dans une même PR** : un premier commit de log a été annulé, différence firmware finale nulle. Aucun nouveau scheduler, Ready, quantum, BREAK, DMA, UART.

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

Aucune modification des oracles historiques, `CMakeLists.txt`, firmware, entrées BASIC, exécution FOR/NEXT, registre ERR/ERL, A1a GOSUB/RETURN, PEN #203, scheduler RUN-BREAK #226, ESC-BREAK #232 ou vidéo. Aucun A2 ni PAPER B2. Après PR : revue et décision exclusivement Pilotage.
