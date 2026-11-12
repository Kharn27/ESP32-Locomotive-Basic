# HW4-PEN-LOGICAL-B1 — projection PEN 5..14, MODE1 C/D uniquement

**Mandat :** [#248 — GO Pilotage après réception physique PEN5](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/248#issuecomment-6774378726). **Base scientifique initiale :** [`main@4a386ee82f6ca2c5bbf73cf17c794f5274b449e9`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/4a386ee82f6ca2c5bbf73cf17c794f5274b449e9). **Base de requalification B1-C1 :** [`main@972ea3573516a19e617c68911a87913554ea9218`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/972ea3573516a19e617c68911a87913554ea9218), après fusion du correctif C99 Clang 21 [#375](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/375). Même PR Draft #370, sans reprise de #226.

## Origine / frontière de preuve

[J1.17-C-A](J1.17-C-A-pen-5-14-cpc-oracle.md), [52 sessions CPC originales/répétées](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41137340431), fournit le token `BB`, l'acceptation CPC `ERR/ERL=0/0`, et le résultat des PNG RGB pour **dix valeurs** et **deux** contextes uniquement. Les sources et archives `tests/fixtures/cpc6128/j1_17_c_a_pen/` et les sceaux externes restent immuables. Le précédent [test PO #248](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/248#issuecomment-6774378726) établit `PEN5_ON_DEVICE_REPRODUCED` **avant** correctif sur `4a386ee…`, pas le succès de cette branche.

**Contexte C** : MODE1, PAPER0, `INK[0..3]={0,26,6,18}` (fond noir, blanc, rouge, vert). **Contexte D** : MODE1, PAPER0, `INK[0..3]={1,24,20,6}` (fond bleu, jaune, cyan, rouge) ; D correspond aussi au boot CONSOLE courant. Toutes les encres `0..3` et le PAPER doivent être exactement conformes à l'un de ces contextes pour `PEN 5..14`. Sinon : `HW4_PEN_UNVERIFIED_VISUAL` **avant** tout replay. Aucune règle `logical & 3` hors de ces témoins.

| PEN logique | CPC C : ROI RGB observée | CPC D : ROI RGB observée | Pixel MODE1 **candidat** |
|---:|---|---|---:|
| 5 | blanc / INK1 | jaune / INK1 | 1 |
| 6 | rouge / INK2 | cyan / INK2 | 2 |
| 7 | vert / INK3 | rouge / INK3 | 3 |
| 8 | **fond seul** / noir | **fond seul** / bleu | 0 **inféré** |
| 9 | blanc / INK1 | jaune / INK1 | 1 |
| 10 | rouge / INK2 | cyan / INK2 | 2 |
| 11 | vert / INK3 | rouge / INK3 | 3 |
| 12 | **fond seul** / noir | **fond seul** / bleu | 0 **inféré** |
| 13 | blanc / INK1 | jaune / INK1 | 1 |
| 14 | rouge / INK2 | cyan / INK2 | 2 |

**Attention 8/12 :** le PNG CPC prouve uniquement que le rectangle contient le fond et que le programme finit normalement. Le chiffre `0` est **notre choix de représentation pour obtenir le même rendu** ; ce n'est **pas** un indice interne CPC mesuré. Les tests séparent la comparaison de RGB observé et l'assertion d'indice candidat ; ils rejettent les palettes partielles/non observées même si une couleur coïncide. Pas de compatibilité générale `PEN` ou MODE0/2 revendiquée.

## Code, sécurité et limites

- `integration/hw4_pen_bridge.c::hw4_pen_pixel_index` reçoit toujours la valeur logique 5..14 du CORE, teste strictement MODE1/PAPER0 et les deux palettes, puis choisit un pixel dans une **table fixe de dix entrées**. Aucun changement d'événement, allocation, palette, CORE, écran, HAL ou firmware.
- `hw4_pen_preflight` valide **tous** les événements d'une étape avant dessin ; un `INK` ultérieur, un offset invalide ou un contexte non mesuré bloque intégralement les PRINT/PEN précédents. `hw4_pen_replay` revalide ; pas de rollback TFT fictif.
- `PEN 4` → index 0 reste borné à PAPER0 et INK0=0/1 ; `PEN 15` → 3 seulement si INK3=18. `PEN 16/-1` conserve le refus BASIC/diagnostic CPC déjà attesté. L'événement `SET_INK` reste **non raccordé** ; refus et texte hôte `ERROR` éventuel sur d'autres erreurs vidéo sont une question distincte [#195](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/195).
- `tests/test_hw4_pen_a.c` : `10 PEN n` → LIST exact → RUN → événement natif → preflight → VRAM/RGB565 → END/Ready unique pour **10×2** cas ; témoin négatif de palettes C/D partiellement changées, PAPER1, cas hors C/D, `PEN5+PRINT+INK`, PEN16 et mauvais offset ; conservation des contrôles 4/15/16 et des tests existants. **HOST_VERIFIED** seulement après CI GREEN. La vérification des sceaux CPC historiques reste dans `CPC-PERMANENT`.

## Réception CYD : barrière Pilotage avant toute fusion

**`ON_DEVICE_UNVERIFIED` sur le HEAD candidat jusqu'au retour PO.** Le Pilotage autorise explicitement le flash d'un **SHA complet figé**, puis le PO teste sur `CONSOLE` ESP-IDF 5.5.6, UART 115200 :

```basic
NEW
10 PEN 1
20 PRINT "PEN5"
30 END
LIST
RUN
```

et, après `NEW`, le **même** texte avec `10 PEN 5`. Fournir `git rev-parse HEAD`, boot/version (ESP-IDF, firmware et SHA du binaire), **UART RX brut** avec `LIST_BYTES`, `RUN_START ... sha=<HEAD>`, `RUN_TERMINAL state=5 ... sha=<HEAD>`, `READY_POLICY ... emitted=1` et `DEVICE_MEMORY` ; relever heap libre/minimum, pile et compteurs DMA (`dma_timeouts`, `dma_fault`, `lcd_error`) **tels qu'émis**, sans inventer de valeurs. Joindre une photo **TFT physique** de chaque témoin (distincte d'une capture logique) ; vérifier que `20 PRINT "PEN5"` apparaît après `RUN`, que Ready n'est émis qu'une fois et que `LIST` conserve le programme. Pour PEN5, exiger l'**absence** de `VIDEO_REJECT` (dont `status=4`) et de `ERROR` : une absence de trace ne prouve pas à elle seule le rendu physique. En contexte INK D au boot, l'affichage candidat PEN5 est jaune ; ne pas inférer la couleur C sur un boot D.

**Frontière des traces :** les callbacks firmware `run_preflight` / `run_replay` n'émettent **aucun `VIDEO_EVENT` par instruction** ; `VIDEO_EVENT logical=5 pixel=1` n'est donc **pas** un critère UART recevable. La correspondance événement logique `5` → pixel MODE1 candidat `1` est une **assertion C99 hôte** de `test_hw4_pen_a.c`, pas une observation instrumentée sur la CYD. Ne pas modifier le firmware pour obtenir cette trace. Le Pilotage conserve le **GO FLASH** et l'acceptation physique du HEAD final.

**Réserves :** `PEN8/12` index internes CPC `UNVERIFIED`, autre palette et autres modes `UNVERIFIED`, incident historique #226 `ORIGINAL_PEN_UNIDENTIFIED`. La PR est livrée au Pilotage sans auto-acceptation ni fusion.


## B1-C2 — cache SPI20 historique et Build standard CONSOLE

**Mandat :** [rectificatif Pilotage #370](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/370#issuecomment-6825484299). Réception PEN1/PEN5 du PO **positive sur SPI20** au HEAD B1-C1 ; elle ne prouve pas le comportement physique SPI40 et n'exige aucun nouveau PEN1 pour la variation de texte PRINT.

Le projet de référence et son répertoire VS Code restent **uniquement** `firmware/esp32_display_probe/build/`. En `CONSOLE`, **Build standard sans flags** doit produire `CYD_LCD_SPI_HZ=40000000`, même quand ce même `CMakeCache.txt` conserve l'ancien `CYD_LCD_SPI_HZ:STRING=20000000`. Cette valeur est la **sortie** de la politique, pas un opt-in : la correction la normalise à l'aide de `set(... CACHE ... FORCE)`. Aucun `fullclean`, nouveau répertoire ou paramètre `-D` n'est demandé au PO.

Le **repli CONSOLE SPI20 délibéré** est maintenant le booléen indépendant `CYD_LCD_SPI20_OPT_IN=ON` (réservé aux développeurs/CI, via `-DCYD_LCD_SPI20_OPT_IN=ON`). Ce choix persiste dans le cache, est imprimé dans `HW4-DISP-C3 ... SPI20_OPT_IN=ON` et revient à SPI40 après `OFF`. L'ancien `-DCYD_LCD_SPI_HZ=20000000` seul **ne constitue plus** un choix traçable. HW3/BASIC_PROBE restent obligatoirement SPI20 ; 40 MHz hors CONSOLE, valeurs invalides dont 55 MHz, et opt-in hors CONSOLE sont refusés. La fréquence électrique demeure **UNMEASURED** ; SPI2/DMA/HAL inchangés.

**Preuve hôte CI :** `python3 tools/ci/hw4_disp_spi_policy.py` crée un unique `build/` temporaire avec sélecteur historique/cache SPI20, compile son témoin, substitue le véritable sélecteur B1-C2 puis exécute **`cmake --build build` sans flags ni suppression du cache**. Le témoin recompilé affiche SPI40 ; le test couvre également fallback explicite persistant et retour SPI40. Le workflow de comparaison Xtensa C3 demande désormais lui-même le repli pour sa variante SPI20, dans ses dossiers temporaires CI. Ce témoin hôte ne constitue ni un build Xtensa ni un essai CYD.

**Recette PO uniquement après GO Pilotage sur le HEAD B1-C2 :** branche #370 mise à jour dans VS Code, boutons **Build → Flash → Monitor** habituels, sans autres manipulations. Attendu au boot : `HW4-DISP-PROFILE BOOT spi_request_hz=40000000 variant=SPI40 ... sha=<HEAD>`. Exécuter le seul cas `NEW; 10 PEN 5; 20 PRINT "PEN5"; 30 END; LIST; RUN` et transmettre UART brut (boot, LIST_BYTES, RUN_TERMINAL state=5, READY_POLICY emitted=1, DEVICE_MEMORY, DMA), plus le TFT observé. Le Pilotage conserve l'autorisation d'essai et la fusion.
