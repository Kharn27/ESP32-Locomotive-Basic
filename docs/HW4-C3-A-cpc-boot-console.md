# HW4-C3-A — démarrage ESP32 CYD / Locomotive BASIC 1.1

**Base :** `main` `fcfb8385c4349bc62dea31604131b3925028123d`.
**Issue :** #101. **Statut :** développement livré sur branche,
`ON_DEVICE_UNVERIFIED` et revue Pilotage requise.

## Architecture

- `video/cpc_boot.c/h` : mise en page HW3 portable C99 partagée entre
  banc OFF et console ON ; 5 textes centralisés, avec position de la
  troisième ligne ajustée spécifiquement pour la console ON.
- Le titre ON devient `ESP32 CYD 128K Microcomputer (v3)` à la demande
  du PO, sur la base de sa capture d'écran ; OFF conserve
  `Amstrad 128K Microcomputer (v3)` sans autre changement visuel.
- Rangées **3, 5, 6, 10 et 12 sur la console ON** : la ligne
  « and Locomotive Software Ltd. » suit immédiatement le copyright 1985
  à la demande du PO (retour matériel sur `74abb57`).
  **HW3 OFF conserve les rangées 3, 5, 7, 10, 12**, sans modification
  de sa mire historique. Copyright HW3 `0x7f`, `BASIC 1.1`, `Ready`
  et curseur en (0,13) sans chevron.
- Le bandeau est dessiné par `cpc_video_put_cell()` dans les
  **16000 octets existants** de VRAM, après initialisation LCD/VRAM
  et avant la première invite UART. La première frappe commence à (0,13).
- Rendu une fois au boot et bandes sales via le `cpc_video_render_row()`
  et le DMA 5120 octets existants. Aucun framebuffer plein écran, malloc,
  nouvelle tâche ni second `app_main`.
- Le chemin de police commun `hw3_glyph_row()` reçoit des glyphes 8×8
  originaux U, W et Y. Y est requis par le nouveau titre CYD ; pas de ROM.
- `cpc_boot_console()` ne touche ni aux compteurs du texte BASIC ni
  au digest FNV d'entrée, et le curseur ne modifie pas les octets VRAM.
- Les contraintes du C2 (RUN/LIST/NEW, Backspace/ANSI Delete, !CLS,
  pagination, rejet atomique) restent inchangées fonctionnellement.

## Nature de la fidélité

Les textes et dispositions sont une **approximation visuelle héritée
de HW3**, plus la personnalisation de titre demandée par le PO.
Ne pas présenter cet écran comme un dump de ROM ou un rendu
bit-à-bit certifié du CPC 6128. Aucune commande BASIC native ne change.

## Tests

Le nouveau `hw4_c3_boot_screen` (tests/test_hw4_c3_boot.c) vérifie
les deux titres, toutes les positions, la couverture des glyphes
(copyright inclus), les pixels VRAM, les canaris, le curseur
non destructif, la première saisie en (0,13), l'effacement !CLS
et 100 cycles de pagination. Les suites HW4-C2 continuent à couvrir
la soumission réelle BASIC et l'éditeur UART actuel.

Commandes Linux à vérifier au HEAD de cette branche :

```sh
cmake -S . -B build -DBP_SANITIZERS=OFF
cmake --build build -j
ctest --test-dir build --output-on-failure
cmake -S . -B build-asan -DBP_SANITIZERS=ON
cmake --build build-asan -j
ctest --test-dir build-asan --output-on-failure
```

Trois variantes Xtensa IDF v5.5.6 requises : ON, OFF et
`firmware/esp32_probe/`. CI, métriques IRAM/DRAM/Flash et contrôles
des oracles CPC existants doivent être vérifiés sur le **HEAD final**.

## Essai obligatoire PO sur la CYD physique

Dans le **dépôt VSCode existant** (sans worktree ni copie) :

```sh
git fetch origin
git switch feat/hw4-c3-a-cpc-boot-console
git pull --ff-only
git rev-parse HEAD
cd firmware/esp32_display_probe
idf.py -DHW4_C2_CONSOLE=ON reconfigure build
idf.py -p /dev/ttyUSB0 flash monitor
```

Capturer l'identité/version application dans le log, l'écran complet
avec titre `ESP32 CYD`, copyright, mention Locomotive, BASIC 1.1,
Ready et curseur sans `>`. Vérifier visuellement Y/U/W et saisir :

```basic
10 A%=2
20 B%=A%+3
30 PRINT B%
40 END
LIST
RUN
NEW
LIST
```

`RUN` doit afficher 5, le bandeau doit survivre aux premières saisies
et `!CLS` doit l'effacer volontairement sans effacer le programme.
Transmettre le log UART, photo si possible, `DEVICE_MEMORY`
(heap, plus grand bloc, pile, DMA/timeouts), HEAD et anomalies.
**Ne jamais attribuer ON_DEVICE_PASS sans ces preuves matérielles.**

## Hors périmètre

Core BASIC et oracles CPC ; véritable éditeur CPC à flèches/Suppr
(#96), police ASCII complète (#97), scrolling CPC fidèle, audio,
tactile, SD, Z80 et HW4-C3-B. Une seule PR, non fusionnée.


## HW4-C3-A-C1 — consolidation avec J1.9-B (28 octobre 2026)

- Synchronisation effective avec `main` `446b0a34e44fe8a744352ca56dde505efcc43959` intégrant J1.9-B (#102).
- Oracle CPC et cœur BASIC repris de `main` **sans édition** ; seule la
  configuration racine CMake ajoute la suite `hw4_c3_boot_screen` à J1.9-B.
  **58 tests** au minimum attendus en CTest Linux OFF et ON ASan/UBSan.
- `tools/hw4_c3_a_scope_gate.sh` énumère explicitement les seules mutations
  sous `video/` et `firmware/` permises pour cette branche : deux fichiers
  `video/cpc_boot.*` et quatre fichiers `esp32_display_probe/main`.
  Toute modification du cœur, des fixtures, oracles, HAL ou transport échoue.
- Adaptations limitées des jobs *architecture* HW4-B, J1.8-A et J1.9-A :
  leur garde originelle demeure active pour **toutes les autres branches**,
  en particulier pour les branches d'acquisition historiques. J1.9-A utilise
  les deux projets ESP-IDF courants, sans recréer `esp32_loco`.
- Le rendu et les glyphes C3-A restent identiques à la version physique
  `c69e4c2`. **Toute nouvelle preuve CYD doit utiliser le HEAD C1 final** ;
  ne pas réutiliser automatiquement l'ancien PASS pour le nouveau binaire.
- Les résultats CI, l'empreinte de merge et les mémoires cibles sont à
  relever depuis les exécutions GitHub Actions sur le HEAD C1 exact.
