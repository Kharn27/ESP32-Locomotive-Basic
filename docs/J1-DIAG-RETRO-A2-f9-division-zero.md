# J1-DIAG-RETRO-A2 — `F9` INTEGER division by literal zero

**Mandat :** [Pilotage #241](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/241).  
**Base de développement :** `main@1026a7782b0bf00b5ee2d4569e4f1733ba5f08bb` (PR A1b #236 déjà fusionnée).  
**Périmètre :** `io/cpc_diag_policy.[ch]`, suite existante `tests/test_j1_diag_retro_a1a.c`, présente note. Aucun changement du moteur, du firmware, du compilateur de tokens, du scheduler ou du CMake.

## Preuve CPC historique / limites

La transcription humaine de deux captures RUN CPC6128 BASIC 1.1, déjà archivées dans [l'inventaire A0](J1-DIAG-RETRO-A0-native-error-inventory.md) et [l'oracle J1.5-A](J1.5-A-integer-division-oracle.md), fournit exactement :

| Témoin historique | Source CPC | Texte de l'écran RUN | Autre observation |
|---|---|---|---|
| `P1_ID0` | `10 A%=1` ; `20 B%=A%\0` | `Division by zero in 20` puis `Ready` | `ERR=11` dans la sonde imprimante |
| `P0_ID0` | `10 A%=0` ; `20 B%=A%\0` | `Division by zero in 20` puis `Ready` | `ERR=11` dans la sonde imprimante |

**Une capture RUN par cas**, pas de paire « original/repeat » pour ces deux divisions, et **pas de mesure indépendante de `ERL`** ; le numéro 20 est une observation d'écran. Le RAM oracle J1.5-A confirme le byte CPC `F9` de l'opérateur division INTEGER. Les PNG, manifestes, matrices et scripts A0 restent intacts ; la note **référence** ces preuves, ne les recrée pas. Les tests renumérotés au-delà de 255 et le `PRINT "BEFORE"` sont des extrapolations contrôlées **natives**, pas de nouveaux témoignages ROM.

La même API C99 `evaluate_integer_binary()` retourne `BE_DIVISION_BY_ZERO` pour **F9 et FB/MOD** ; il est donc interdit d'en déduire un texte CPC à partir de ce statut seul. Le texte `Division by zero` n'est **pas attesté pour MOD** dans les sources sélectionnées. Aucun `ERR/ERL` historique n'est ajouté à l'exécuteur, aucun diviseur variable ne reçoit cette attribution.

## Contrat de politique de diagnostic

`cpc_diag_policy_step()` ne choisit la catégorie `CPC_DIAG_DIVISION_INTEGER_ZERO` et la provenance `CPC_DIAG_ORIGIN_NATIVE_F9_ZERO_CPC_ORACLE` que lorsque l'ensemble suivant est vrai :

- `result.status == BSR_EXECUTOR_ERROR` et `result.executor_status == BE_DIVISION_BY_ZERO` ;
- `BSR_RUNNING`, pointeur de programme cohérent, record courant valide, offset de ligne non nul ; lecture avant `bsr_stop()` ;
- variables de l'exécuteur et du runtime identiques, magasin et programme valides, source INTEGER effectivement présente ;
- dans **la ligne réellement atteinte et au début de son corps**, une affectation INTEGER explicite de la forme `[LET ]B%=A%\0` ; les références sont décodées par les modules BVR/BVB, sans scanner des chaînes ou caches comme des opcodes ;
- opcode **exact `F9`**, littéral zéro INTEGER **canonique `0E`**, rien d'autre après lui à part des espaces.

Ce validateur effectue une **corroboration lexicale bornée en lecture seule**, pas un second passage de l'exécuteur. Les CONTINUATIONS `:`, commentaires et constructions non couvertes échouent fermé vers `CPC_DIAG_HOST_GENERIC` ; cette restriction est volontaire (assignation multistatement refusée par le moteur). Le cas MOD `FB 0E` conserve `ERROR\n`, même avec exactement le même enum natif. `/0`, diviseur variable, overflow et toute autre cause restent génériques.

Le format `Division by zero in <line>\n` comporte un LF et **aucun Ready**. La ligne est le `BasicProgramLine.number` du record réellement atteint, sans valeur codée en dur. Le formatter rejette les couples catégorie/origine inventés et les buffers trop courts avant toute écriture. Le raccord CONSOLE déjà existant appelle la politique avant `bsr_stop()`, puis `cpc_ready_policy` émet **un seul `Ready`** ; aucun fichier firmware modifié. La politique n'écrit ni dans le programme, ni le store, ni les buffers/événements, ni l'état vidéo.

**Statuts hôtes :** la version courante de `BSRStatus` ne possède **pas** de `BSR_RENDER_ERROR` ; on teste `BSR_SESSION_ERROR` et `BSR_OVERLAP` comme causes non-exécuteur, en plus des falsifications `BE_*`. Il serait incorrect de fabriquer un enum pour satisfaire textuellement un cas négatif.

## Plan de reproduction et batterie

**RED indépendant :** [PR de preuve #242](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/242) uniquement tests sur le `main` de base, ajoutant deux témoins F9 et un négatif `FB 0`. Le CTest existant `j1_diag_retro_a1a_gosub_return` doit échouer à la première demande de catégorie CPC F9, et le cas MOD empêcherait aussi un patch naïf `BE_DIVISION_BY_ZERO => CPC`. Pas de changement CMake. Cette PR est une preuve temporaire, non destinée à la fusion.

**GREEN :** CTest existant étendu : `1\0`, `0\0`, lignes 620 et 65535, `PRINT "BEFORE"` préalablement atteint, `PRINT "NEVER"` bloqué après erreur, `MOD 0` hôte, `F9 /1` et `MOD 1` valides, faux statut exécutant ou session, status overflow, littéral altéré, mauvais type, cache corrompu, faux opérateur FB, curseur/statement invalide, source manquante, chaîne/REM/apostrophe, faux couple de provenance, buffer de sortie trop court. La fixture compare programme complet, store/entrées, frames/runtime, sorties/événements et compteurs avant/après le pas fautif, et vérifie un seul `Ready`. Les suites PEN/GOSUB/RETURN/NEXT restent exécutées.

Pour la traçabilité de **l'exact HEAD final**, consulter les runs GitHub de la PR de livraison : C99 GCC/Clang OFF/ON (ASan/UBSan ON), CI-CPC-PERMANENT, CI-ARCH, CI-OPT3, Xtensa v5.5.6 (3 profils) et la preuve séparée de `python3 tools/j1_diag_retro_a0_verify.py --self-test` sur ce SHA exact. **Les numéros de runs et les tailles réelles figurent dans la remise de la PR**, après achèvement des jobs : ne pas substituer des données anciennes. Le comparateur Xtensa est `main@1026a778...` / profil CONSOLE / workflow `#41257532821` ; section Flash_Code, IRAM, DRAM et image firmware, en distinguant le build des mesures sur appareil. Le budget pile n'est pas une mesure réelle tant qu'aucun test CYD n'est disponible.

## Coût mémoire Xtensa CONSOLE — mesure comparative

Les logs ESP-IDF v5.5.6 du profil **CONSOLE** sur [main de départ #41257532821](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41257532821) et [A2 avec le même code C99 #41259329897](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41259329897) donnent :

| Mesure | main `1026a778...` | A2 code HEAD `da5f12ae...` | Delta A2 |
|---|---:|---:|---:|
| Flash_Code | 143846 o | 144346 o | **+500 o** |
| Image firmware | 275421 o | 276001 o | **+580 o** |
| IRAM | 67331 o | 67331 o | 0 o |
| DRAM | 53736 o | 53736 o | 0 o |

`CONSOLE_STORAGE_ELF_BSS_BYTES=22668`, `ARENA_BYTES=4096` et le seuil test de budget restent inchangés, **PASS**. Ce relevé provient d'un HEAD contenant le **même code exécutable** que le HEAD final documenté ultérieurement ; les **cinq CI doivent repasser sur le HEAD final** après la présente mise en forme de note. Aucun chiffre de heap libre, DMA ou marge pile **sur carte** n'est inféré de cette compilation. BASIC_PROBE/HW3 n'utilisent pas cette politique CONSOLE dans le code cible ; les comparaisons sections exactes sont fournies dans la remise après les 3 jobs.

## Protocole matériel réservé au PO (avant fusion)

**Précondition :** le Pilotage vérifie la CI, gèle le **SHA complet final de la PR** et autorise sa transmission au PO ; jamais l'ancien HEAD d'un build intermédiaire. CYD `ESP32-2432S028R` sans PSRAM, ESP-IDF 5.5.6, `CONSOLE`, UART 115200 :

```sh
git fetch origin
git checkout --detach <SHA_COMPLET_GELE_PAR_PILOTAGE>
cd firmware/esp32_display_probe
idf.py -DLOCO_CYD_PROFILE=CONSOLE build
idf.py -p /dev/ttyUSB0 flash monitor
```

Entrer **une ligne BASIC par envoi UART**, après `NEW` pour chacun des six scénarios ci-après. Conserver l'écho, les diagnostics, `Ready` et `LIST` ; ne pas confondre le Ready initial du boot avec celui qui suit RUN.

1. `10 A%=1`, `20 B%=A%\0`, `30 PRINT "NEVER"`, `RUN`, `LIST` : **`Division by zero in 20`**, Ready unique, aucun NEVER exécuté, LIST intact.
2. Même programme mais `A%=0` : **même diagnostic**.
3. `600 A%=1`, `620 B%=A%\0`, `630 PRINT "NEVER"`, `RUN`, `LIST` : **`Division by zero in 620`**.
4. `10 A%=1`, `20 B%=A% MOD 0`, `30 PRINT "NEVER"`, `RUN`, `LIST` : **`ERROR` hôte uniquement**, Ready unique, pas de faux message CPC.
5. `10 A%=1`, `20 B%=A%\1`, `30 PRINT B%`, `RUN` puis `NEW` ; et en contrôle `B%=A% MOD 1` : aucune erreur division par zéro, valeur résultat cohérente.
6. Non-régression du diagnostic existant, par exemple `10 NEXT I%`, `RUN`, `LIST` : **`Unexpected NEXT in 10`**, Ready unique.

**PASS uniquement** si chaque résultat/numéro/Ready et LIST correspondent, pas d'émission `NEVER` après l'échec, pas de reboot, LCD opérationnel, erreurs/timeout DMA à zéro. Collecter le **SHA flashé**, version ESP-IDF, log intégral de build/flash/monitor, photo de l'écran pour les erreurs, mémoire `heap_free`, `max_free_block`, marge pile, compteurs `dma_fault` / `dma_timeouts` et statut LCD (`ESP_OK`). Les 3 profils sont requis en CI ; seul le PO atteste le matériel. Sans rapport physique : **`ON_DEVICE_UNVERIFIED` et pas de fusion**.

## Exclusions maintenues

Pas de conversion pour MOD, diviseur variable, division `/`, overflow, ERR/ERL artificiel, nouvelle acquisition CPC, imprimante, travaux O2 #237, chantiers HW, vidéo, PAPER B2, édition du core, firmware, CMake, CI existante, ni oracle archivé. L'approbation technique et la fusion dans `main` restent exclusivement au **Pilotage**.
