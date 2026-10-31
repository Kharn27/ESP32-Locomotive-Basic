# J1-DIAG-RETRO-A1a — diagnostics CPC GOSUB / RETURN

**Mandat A1a strict.** Base de départ contrôlée : main@ce8294453dedcc54a59398620b29df58e42c25f3. [Livraison #227](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/227). Aucun changement des oracles scellés, du moteur BASIC, des statuts BE/BSR, de la politique Ready ou du chantier BREAK.

## Référence historique indépendante A0

L'[audit A0 #224](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/224), la matrice tests/diag_retro_a0_matrix.json et les captures PNG ROM-backed avec hash SHA-256 scellent les textes suivants.

| Capture CPC6128 BASIC 1.1 | Écran ROM exact | ERR/ERL indépendants |
|---|---|---|
| J1.11 F_MISSING_TARGET | Line does not exist in 10 | 8 / 10 |
| J1.11 F_UNPAIRED_RETURN | Unexpected RETURN in 10 | 3 / 10 |
| J1.11 F_UNPAIRED_AFTER_CALL | Unexpected RETURN in 20 | 3 / 20 |

Les dérivés renumérotés sont des **tests natifs**, pas de nouvelles observations physiques CPC. Les imprimantes CPC ne sont pas assimilées à l'écran CYD.

## Chemin d'échec et garanties

- L'exécuteur prévalide la ligne entière : sur erreur, aucun PRINT ni événement vidéo de cette ligne n'est appliqué ; l'exécuteur, le store, la ligne et les buffers restent inchangés.
- Avant bsr_stop(), la politique io/cpc_diag_policy.c résout le **vrai record** par bp_next sur BasicExecutor.cursor, puis examine le flux tokenisé à partir de statement_offset (position réelle de reprise).
- Pour BE_MISSING_TARGET, il faut que la **première instruction de contrôle pertinente atteinte** soit le token 0x9F (GOSUB). Les tokens 0xA0 GOTO et 0xA1 IF sont distingués ; un préfixe ambigu ne déclenche aucun texte CPC.
- Pour BE_RETURN_WITHOUT_GOSUB, il faut une instruction 0xC9 RETURN effectivement atteinte. La ligne provient du record, non d'un numéro constant. Les guillemets, séparateurs 01, commentaire 01 C0, références variables et payloads numériques sont parcourus sans rechercher naïvement les octets d'opcodes.
- L'adaptateur cpc_diag_policy_format_step formate le texte plus le numéro décimal et LF sans malloc/printf, sans Ready ni effet BASIC. Si la capacité manque, ni la sortie ni son compteur ne sont modifiés.
- Le propriétaire CONSOLE garde l'ordre échec → diagnostic → bsr_stop() → rendu d'une erreur → transition Ready unique. Les logs de provenance distinguent CPC_GOSUB_ORACLE, CPC_RETURN_ORACLE, CPC_PEN_ORACLE et HOST_NOT_CPC_ERR.

Sans provenance et ligne valides : **ERROR** et jamais une déclaration CPC fabriquée. Pas de nouveau ERR/ERL natif. L'existant PEN #203 est inchangé.

## Test RED → GREEN

Le nouveau CTest C99 j1_diag_retro_a1a_gosub_return vérifie les trois scénarios A0, plusieurs lignes renumérotées, un GOSUB après PRINT atomique, une reprise RETURN sur la même ligne, les négatifs GOTO/IF, PEN, absence de PRINT après erreur, programme non muté, buffering événement/PRINT inchangé et Ready unique. Un formatage trop court doit échouer sans écriture partielle.

**RED indépendant** : [PR temporaire #229](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/229) sur le test seul, SHA 154dad7dde8f6d497bf584497d9288e17e56dddc ; [CI RED](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41211518574). Les quatre cellules C99 compilent et échouent à la première assertion de diagnostic CPC dans le nouveau test, sans modifier le moteur. Les liens et statuts GREEN, ARCH, OPT3, CPC permanent, Xtensa et mémoire sont relevés au HEAD final dans la remise, jamais hérités d'un HEAD précédent.

~~~sh
cmake -S . -B build-a1a -DBP_SANITIZERS=OFF
cmake --build build-a1a -j2
ctest --test-dir build-a1a --output-on-failure
python3 tools/j1_diag_retro_a0_verify.py --self-test
~~~

## Protocole PO — test physique CYD sur le HEAD final de PR #227

**Obligatoire :** relever dans GitHub le SHA complet final de la PR, checkout de ce SHA, puis compilation et flash de **la console** sur ESP32-2432S028R sans PSRAM. Vérifier le SHA du firmware, pas un build précédent ni le chantier HW4-RUN-BREAK-B. Dans le workspace officiel :

~~~sh
git fetch origin
git switch --detach <SHA-COMPLET-FINAL-PR-227>
git rev-parse HEAD
cd firmware/esp32_display_probe
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
~~~

LOCO_CYD_PROFILE=CONSOLE (valeur par défaut, cache non mélangé HW3/BASIC_PROBE) ; UART 115200. Les commandes ci-dessous sont **séquentielles**, chaque NEW réinitialise le programme :

~~~basic
NEW
10 GOSUB 999
20 PRINT "NEVER"
RUN
LIST
NEW
10 RETURN
20 PRINT "NEVER"
RUN
LIST
NEW
10 GOSUB 30
20 RETURN
30 RETURN
40 PRINT "NEVER"
RUN
NEW
370 GOSUB 999
400 PRINT "NEVER"
RUN
NEW
510 GOSUB 530
520 RETURN
530 RETURN
540 PRINT "NEVER"
RUN
NEW
10 PRINT "BEFORE":GOSUB 999:PRINT "NEVER"
RUN
NEW
10 GOTO 999
20 PRINT "NEVER"
RUN
NEW
10 A%=1
20 IF A% THEN 999
30 PRINT "NEVER"
RUN
NEW
10 PEN 16
20 PRINT "NEVER"
RUN
~~~

**Messages attendus, dans le même ordre :**
1. Line does not exist in 10
2. Unexpected RETURN in 10
3. Unexpected RETURN in 20
4. Line does not exist in 370
5. Unexpected RETURN in 520
6. Line does not exist in 10
7. ERROR (GOTO non oraclé A0)
8. ERROR (IF non oraclé A0)
9. Improper argument in 10 (PEN #203)

Pour chaque erreur : **un seul Ready**, immédiatement après le diagnostic, aucun PRINT NEVER ni BEFORE de la ligne fautive. Les deux LIST doivent conserver les lignes initiales. Le Ready initial du boot n'est pas compté dans le contrôle d'unicité après erreur.

**PASS** si tous les messages/numéros concordent, Ready unique, aucun PRINT post-erreur, intégrité LIST et ni reset ni erreur mémoire/LCD. **FAIL** dès qu'un de ces critères diverge. Preuves demandées : SHA flashé complet, journal horodaté de build/flash/monitor UART, photos lisibles de GOSUB/RETURN avec Ready, traces GOTO/IF/PEN, LIST et télémétrie HW4-C2 DEVICE_MEMORY si disponible. Sans retour PO, **ON_DEVICE_UNVERIFIED**.

## Exclusions inchangées

NEXT (A1b), division par zéro/INK (A2+), ERR/ERL générique, PEN #203, HW4-RUN-BREAK-B parallèle, refonte de la console/vidéo et remplacement de témoins CPC.
