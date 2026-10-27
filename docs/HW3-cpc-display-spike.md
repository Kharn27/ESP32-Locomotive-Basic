# HW3 — Sonde autonome d'affichage du boot CPC 6128

**Périmètre :** issue [#64](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/64), autorisée en parallèle de J1.3-A #62. Ce programme ne contient **ni BASIC, ni Z80, ni ROM CPC**, et n'est pas une implémentation des commandes graphiques. Sa cible est exclusivement `firmware/esp32_display_probe/`.

## Référence et géométrie

Le CPC 6128 démarre en MODE 1, 320 × 200 pixels logiques, 40 × 25 caractères de 8 × 8. Sur l'ILI9341 physique 320 × 240 en paysage, l'aire logique occupe **x=0..319 et y=20..219**, à l'échelle **1:1** ; le BORDER est rendu par les 20 lignes bleues au-dessus et en dessous (sans effet de mise à l'échelle). Le fond bleu occupe l'intégralité de l'écran, comme PAPER et BORDER au démarrage CPC. Ce n'est pas une simulation de la bordure analogique d'un moniteur CRT.

La palette déterministe de cette sonde utilise les deux valeurs par défaut documentées dans les manuels CPC :
- **INK 0 / couleur CPC 1, bleu :** RGB888 `#000080`, RGB565 `0x0010` ;
- **INK 1 / couleur CPC 24, jaune vif :** RGB888 `#FFFF00`, RGB565 `0xFFE0`.

Chaque pixel RGB565 est transmis **octet fort puis octet faible**. La configuration ILI9341 utilise `LCD_RGB_DATA_ENDIAN_BIG` et `LCD_RGB_ELEMENT_ORDER_RGB` par défaut ; pour un module dont la polarité rouge/bleu est inversée, essayer `HW3_LCD_BGR=1` et consigner la valeur choisie sur le CYD réel. Les couleurs perçues sur une photo de CRT/convertisseur vidéo dépendent aussi de l'appareil photographique, du gamma et de l'affichage.

Écran statique : bannière `Amstrad 128K Microcomputer (v3)`, `©1985 Amstrad Consumer Electronics plc`, `and Locomotive Software Ltd.`, `BASIC 1.1`, `Ready`. Le curseur est une cellule 8 × 8 en **colonne 0, ligne texte 13 (indice zéro)**, sous `Ready` (ligne 12), clignotant toutes les 500 ms. Le code source du désassemblage BASIC 1.1 (adresse `C033`) contient `" BASIC 1.1",10,10,0`, et à `C0D7`, `"Ready",10,0`. La disposition de la bannière ROM/OS ainsi que les espaces verticaux demeurent **une approximation visuelle**, à comparer avec une photo réelle de CPC 6128 ; le désassemblage BASIC fourni n'est pas à lui seul une preuve de l'espacement de la bannière système.

Références de contrôle visuel et technique (images **non copiées** dans le firmware) :
- [Issue HW3 #64](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/64) : cahier des charges matériel / frontières.
- [Photo d'un boot CPC 6128](https://retrotechtive.wordpress.com/2022/10/27/the-amstrad-cpc-nostalgia-and-the-6128/) : comparaison qualitative uniquement.
- [Table des 27 couleurs CPC](https://anto80.com/fr-fr/traitement-image/imagetoamstradcpc-options-conversion-listoptionimagetocpc) et manuel CPC 6128.
- [CPC BASIC v1.1 disassembly](http://cpctech.cpc-live.com/docs/basic.asm) : chaînes d'initialisation `BASIC 1.1` et `Ready`.
- [Brochage ESP32-2432S028R](https://github.com/witnessmenow/ESP32-Cheap-Yellow-Display) : à recouper avec la sérigraphie de la carte.

## Fonte : droits et limites

`main/cpc_font.c` contient une **fonte originale, dessinée pour HW3**, couvrant uniquement les caractères de ces messages. Elle ne reproduit **aucune ROM/dump, aucun caractère extrait d'une ROM CPC, aucune source de police tierce**. Les fichiers `cpc_font.c` et `cpc_font.h` portent `SPDX-License-Identifier: MIT` ; les nouveaux dessins sont proposés sous licence MIT. La forme 8 × 8 (majoritairement un alphabet 5 × 7 occupant une cellule 8 × 8) **s'inspire du genre de présentation micro-ordinateur**, sans revendiquer une correspondance bit à bit avec la fonte historique CPC. Le caractère `0x7F` est ici un glyphe `©` original, propre à la sonde. Les autres caractères ASCII non implémentés restent blancs/vides ; ce n'est pas une police CPC générale.

## Dépendance du contrôleur ILI9341

ESP-IDF **v5.5.6 fournit l'API générale `esp_lcd` mais n'embarque pas le pilote spécifique ILI9341**. HW3 déclare dans `main/idf_component.yml` : **`espressif/esp_lcd_ili9341 == 2.1.0`** (composant officiel Espressif, licence **Apache-2.0**, [source et versions](https://components.espressif.com/components/espressif/esp_lcd_ili9341)). Le gestionnaire de composants IDF télécharge cette dépendance pendant la configuration. Ni Arduino, ni LVGL, ni copie d'une ROM.

La version du pilote est **verrouillée à une version exacte** et le workflow de compilation fixe `espressif/idf:v5.5.6`. Une compilation fraîche exige un accès réseau au registre de composants Espressif lors de la première résolution.

## GPIO, SPI, options

| Fonction | GPIO | Note |
|---|---:|---|
| LCD SPI2 MOSI | 13 | écran uniquement |
| LCD SPI2 SCLK | 14 | SPI 20 MHz pour premier flash |
| LCD SPI2 CS | 15 | sélection LCD |
| LCD DC | 2 | données / commandes |
| LCD MISO | -1 | non utilisé ; GPIO12 non affecté |
| LCD RST | -1 | reset matériel lié au reset carte, pas à GPIO4 |
| LCD backlight | 21 | actif HIGH, allumé après rendu réussi |
| XPT2046, microSD, LED RGB | aucun | pas d'initialisation |

Orientation candidate HW3-C1 : `swap_xy=true`, `mirror_x=false`, `mirror_y=true` (cas **5**), à **confirmer** sur le CYD réel. La précédente configuration était `1/1/0` (cas **3**) et a donné un rendu incorrect en test matériel. Pour figer l'orientation après calibration, depuis la racine du projet ESP-IDF :

```bash
idf.py -DHW3_SWAP_XY=1 -DHW3_MIRROR_X=0 -DHW3_MIRROR_Y=1 build
```

Les options CMake sont transmises au compilateur par `target_compile_definitions`; changer une option nécessite reconfiguration/recompilation avant nouveau flash. La fréquence du bus est volontairement limitée à 20 MHz tant que le câblage réel n'est pas validé. Pas de tactile, d'entrée clavier, ni de gestion de stockage.


## HW3-C1 — Photo matérielle et calibration (27 octobre 2026)

**Observation physique :** première version de la sonde sur CYD réel : affichage bleu et curseur visibles, mais texte illisible, image pré-flash encore visible sur une bande d'environ 80 pixels et orientation incorrecte. Le premier essai est `ON_DEVICE_FAILED_INITIAL`, et non « validé ». Une photo ne suffit pas à déterminer quel bit MADCTL est effectivement actif.

**Correctifs :** avant chaque choix MADCTL, forcer le portrait natif (`swap_xy=0`, `mirror_x=0`, `mirror_y=0`) et vider **240×320 pixels** au moyen de 40 bandes DMA de 240×8. Puis appliquer `swap_xy` et les deux miroirs, dessiner la mire dans l'espace légal **240×320 si swap=0** ou **320×240 si swap=1**. Ne jamais envoyer 320 colonnes en mode portrait. Pas de framebuffer, pas de changement RGB/BGR.

La mire affiche un contour jaune et quatre coins distincts : **haut gauche rouge, haut droit vert, bas gauche jaune, bas droit blanc**, avec `CASE n`. Elle permet de constater plein écran propre / orientation / absence de résidu indépendamment de la fonte. Un cas portrait (pair) ne peut pas héberger la zone CPC 320×200 sans conversion logicielle supplémentaire ; le boot CPC est donc réservé aux cas paysages (impairs).

**Un seul flash pour tester les huit possibilités.** Commandes depuis `idf.py monitor` (UART0, 115200) :

| Touche | Action |
|---|---|
| `m` | Parcours des 8 mires dans l'ordre 0 → 7 (2,5 secondes chacune), puis restauration du cas précédent |
| `0` à `7` | Affiche la mire d'un cas jusqu'à nouvel ordre |
| `b` | Affiche le boot CPC avec le cas sélectionné **si paysage** ; conserve une mire si portrait |
| `r` | Revient au cas compilé et affiche le boot |
| `?` | Rappelle l'aide UART |

| Cas | swap_xy | mirror_x | mirror_y | Surface |
|---:|---:|---:|---:|---|
| 0 | 0 | 0 | 0 | 240×320 |
| 1 | 1 | 0 | 0 | 320×240 |
| 2 | 0 | 1 | 0 | 240×320 |
| 3 | 1 | 1 | 0 | 320×240 — **réglage initial défaillant** |
| 4 | 0 | 0 | 1 | 240×320 |
| 5 | 1 | 0 | 1 | 320×240 — **nouveau candidat** |
| 6 | 0 | 1 | 1 | 240×320 |
| 7 | 1 | 1 | 1 | 320×240 |

L'index vaut `(swap_xy ? 1 : 0) + (mirror_x ? 2 : 0) + (mirror_y ? 4 : 0)`.

**Retest du Product Owner :** tourner physiquement la carte en paysage pour juger les cas impairs. Prendre les photos des **cas 1, 3, 5 et 7**, puis sélectionner le meilleur avec son chiffre et taper `b` pour contrôler bannière, « Ready », plein écran 320×240, aire CPC y=20..219, curseur jaune clignotant et absence d'ancienne image. Remonter le log depuis le reset comprenant `HW3 BUILD_IDENT`, `HW3 ORIENTATION_CASE`, `HW3 CALIBRATION_DRAWN`, `HW3 DEVICE_MEMORY` et erreurs éventuelles. Mesurer l'absence de WDT/reset. Seul ce retour peut déterminer la combinaison à figer. **Aucune validation physique finale n'est revendiquée à ce stade.**

**Statut de correction tant que le nouveau test n'est pas reçu :** `HW3-C1 PUSHED — TARGET_BUILD_PENDING — ON_DEVICE_RETEST_PENDING — PR #66 OPEN / NON MERGED`.


## HW3-C2 — Photos C1 non conformes et voies alternatives (27 octobre 2026)

**Échec visuel de HW3-C1 sur le CYD réel :** les commandes UART fonctionnent, mais les photos montrent des caractères illisibles, des traits de mire repliés ou tronqués et un cadrage incorrect. Aucun des huit cas MADCTL ne peut être considéré validé sur la base de ces observations. La cause exacte doit être mesurée : décalage de repères entre GRAM, fenêtre SPI et orientation LCD ; une mauvaise fonte ne suffit pas à expliquer les bordures.

**Deux nouvelles hypothèses, indépendantes de la matrice C1 :**
- **Cas 8..11 :** adresser directement **320×240** avec **MV=0** (pas de permutation matérielle) et quatre combinaisons des miroirs. Cette variante est documentée sur au moins une CYD dans [Overhead — orientation landscape-native](https://github.com/JamesDavid/Overhead/blob/main/CYD-ESP32-2432S028R.md#display-orientation--the-fix-overhead-lovyangfx), sans garantie que la révision du PO soit identique.
- **Cas 12/13 :** **rotation logicielle** depuis les pixels BASIC 320×240 vers la GRAM native 240×320, toujours **MV=0** et miroirs désactivés. Cas 12 : `u=239-y, v=x` ; cas 13 : `u=y, v=319-x`. L'écran est redessiné par 40 bandes **240×8** ; le curseur 8×8 est converti vers les mêmes coordonnées. Aucun framebuffer plein écran, aucun changement RGB/BGR.

**Commandes UART0 à 115200 (nouveau firmware de la même PR #66) :**

| Entrée | Effet |
|---|---|
| `n` | boucle six mires **8 à 13** (2,5 s chacune) |
| `8` / `9` / `a` / `c` | maintient la mire native-large du cas **8 / 9 / 10 / 11** |
| `d` | mire de rotation logicielle **cas 12** (horaire) |
| `e` | mire de rotation logicielle **cas 13** (antihoraire) |
| `b` | boot CPC dans le cas retenu (et curseur clignotant) |
| `r` | rétablit le cas 12, configuré par défaut |
| `m` / `0..7` | anciens huit cas matériels conservés pour comparaison |

**Protocole réel :** flasher le dernier HEAD, regarder le boot par défaut **cas 12**, tourner physiquement le CYD en paysage pour juger texte et marges, puis essayer `d`, `b` et `e`, `b`. Pour isoler le chemin natif-large essayer `8`, `b`. Fournir les photos et le journal des marqueurs `HW3 ORIENTATION_CASE`, `HW3 SOFTWARE_ROTATION_DRAWN`, `HW3 BOOT_SCREEN_DRAWN`, `HW3 DEVICE_MEMORY`. **CI verte ≠ résolution graphique prouvée** ; la PR ne doit pas être fusionnée avant preuve photographique et UART cohérente.

**État HW3-C2 :** `ON_DEVICE_C1_FAILED / ON_DEVICE_C2_RETEST_PENDING / PR #66 OPEN`.


## HW3-C3 — Correction de la géométrie après les six photos C2

**Retour terrain :** le propriétaire du CYD a photographié les commandes `d`, `b`, `e`, `b`, `8`, `b`. Les deux variantes de rotation logicielle (12/13) montrent des bandes anormales. Le **cas 8 + boot** révèle en revanche des lignes de crédit et `Ready` presque intégralement visibles, quoique tournées et inversées. Cela encourage à tester les miroirs de l'adressage 320×240 sans permutation (`MV=0`), plutôt que de persister avec la rotation logicielle.

**Bug C2 découvert et corrigé dans le code :** `set_orientation()` utilisait bien **320×240** pour les indices 8 à 11, mais `draw_diagnostic()` continuait à calculer les dimensions avec `idx & 1`. La mire du **cas 8** envoyait donc **240×320** dans une configuration déclarée **320×240**. La photo de cette mire ne permettait pas de juger la validité du mode paysage. C'est une erreur de l'implémentation C2, pas une défaillance de la carte.

**Correction :** `draw_diagnostic()` calcule désormais 320×240 pour TOUS les cas 8 à 11 et journalise `HW3 DIAGNOSTIC_GEOMETRY case=... width=320 height=240`. Les étiquettes de mire sont sur deux chiffres (`CASE 08`, `CASE 09`, `CASE 10`, `CASE 11`). Les cas 12/13 restent accessibles pour comparaison, sans être sélectionnés au démarrage.

**Démarrage candidat HW3-C3 :** **cas 9**, `swap_xy=false`, `mirror_x=true`, `mirror_y=false`, surface **320×240**. Il n'est **pas validé physiquement**. Les cas 8/9/10/11 restent sélectionnables sans reflash.

**Retest sur vrai CYD :**
1. Flasher le HEAD final et photographier le boot **cas 9** par défaut, en tenant physiquement le CYD en paysage.
2. Si besoin, essayer **`a` puis `b`** (cas 10) et **`c` puis `b`** (cas 11), éventuellement **`8` puis `b`** comme témoin.
3. Sur un candidat prometteur, afficher sa mire avec son caractère seul (`9`, `a` ou `c`) et examiner le contour entier, les quatre coins colorés et les absences de bandes résiduelles.
4. Conserver le journal UART comprenant `HW3 ORIENTATION_CASE`, `HW3 DIAGNOSTIC_GEOMETRY`, `HW3 BOOT_SCREEN_DRAWN` et les éventuelles erreurs. Aucune photographie n'est inventée, et `ON_DEVICE_PASS` reste interdit jusqu'au contrôle.

**Statut :** `HW3-C3 POUSSÉ — ON_DEVICE_C2_FAILED — ON_DEVICE_C3_RETEST_PENDING — PR #66 NON FUSIONNÉE`.


## HW3-C4 — Retest terrain C3 : paysage lisible et espacement du texte

**Éléments réellement reçus :** le Product Owner a photographié le démarrage C3 **cas 9** (réglage initial, carte tenue en paysage), puis les séquences **9/b**, **a/b** (cas 10), **c/b** (cas 11). Aucun journal UART complet ni chronométrage du curseur ne sont joints à ces photos.

**Résultat de géométrie :** le **cas 9** (`swap_xy=0`, `mirror_x=1`, `mirror_y=0`, dessin 320×240, sans swap matériel) donne enfin un boot BASIC **lisible et dans le bon sens** dans l'orientation de carte photographiée. Le fond bleu couvre la surface visible ; `BASIC 1.1`, `Ready` et le curseur bloc sont reconnaissables, sans reliquat de l'ancienne image visible sur cette photo. Les trois lignes de crédits sont visuellement **trop serrées**. Ce constat valide un **candidat fort pour l'orientation**, mais ne prouve pas l'exactitude des couleurs, des temps du curseur ni la fidélité bit à bit CPC.

Le **cas 10** (`a`, puis `b`) donne lui aussi un boot reconnaissable si la carte est **physiquement retournée de 180 degrés**. Les photos sans retournement donnent des textes inversés, ce qui est attendu pour cette orientation. Le cas 11 (`c`, puis `b`) présente encore un texte visuellement renversé / peu exploitable dans l'orientation photographiée.

**Modification limitée HW3-C4 :** garder le **cas 9** comme démarrage par défaut, mais séparer les trois lignes de crédits par une ligne de texte vide (lignes 3, 5, 7 au lieu de 4, 5, 6), puis `BASIC 1.1` ligne 10, `Ready` ligne 12 et curseur ligne 13. La grille CPC reste **40×25** en **320×200** logique centré à y=20..219. Il s'agit d'une *approximation de présentation* adaptée au TFT et **non** d'une preuve de fidélité aux sauts de ligne exacts de la ROM CPC. Aucune modification du tokenizer, du cœur BASIC, de l'interface SPI, des GPIO ou du budget mémoire.

**Retest de clôture attendu :** flasher le HEAD C4, conserver le boot par défaut (cas 9), photographier en paysage, vérifier que les crédits ne se touchent plus, observer plusieurs cycles du curseur jaune plein sous `Ready`, et conserver le journal UART de l'initialisation aux marqueurs de démarrage avec les mesures mémoire. Au besoin envoyer `9` pour la mire et vérifier les quatre coins en paysage, puis `b` pour revenir au boot. Un essai satisfaisant donnera au Pilotage des éléments pour une décision de fusion ; les photos disponibles ne suffisent pas à elles seules à valider la cadence du curseur.

**Statut à ce point :** `HW3-C3 ON_DEVICE_LANDSCAPE_VISUALLY_PROMISING / HW3-C4 RETEST_PENDING / PR #66 OPEN — NOT MERGED`.


## HW3-C5 — Régression déterminante sur les redessins du même cas

**Observations réelles du PO, à préserver sans extrapolation :**

| Manipulation | Résultat |
|---|---|
| démarrage frais en cas 9 | écran CPC paysage, lisible, sans résidu visible |
| `9` puis `b` | écran illisible / décrit comme portrait |
| `a` puis `b` (cas 10) | lisible si le CYD est tenu dans l'autre sens (rotation physique de 180°) |
| `c` puis `b` (cas 11) | caractères reconnaissables mais en miroir |

Ces résultats **ne valident pas** le redessin ni la robustesse des transitions. Ils distinguent le succès au démarrage de la reproduction fiable du même rendu. Une photo correcte après reset ne vaut pas validation fonctionnelle.

**Défaut plausible dans le code C4 :** chaque invocation de `show_case()` appelait `set_orientation()` sans distinguer le cas déjà actif. Même lors de `9` puis `b`, le code réappliquait les registres de permutation / miroir (`MADCTL`) et repassait par `clear_native_gram()` avant de redessiner. Il n'est pas démontré que cela soit l'unique cause des pixels corrompus, mais la séquence constitue une variable parasite évitable.

**Expérience ciblée C5 :**
- `s_active_case` démarre à `UINT_MAX` (aucune orientation connue).
- Si `set_orientation(idx)` reçoit le **même index** que `s_active_case`, sauter **uniquement** l'effacement et l'écriture de MADCTL ; redessiner la mire ou le boot sur la totalité de la zone **320×240** avec les mêmes transferts DMA.
- Si l'index change, conserver le protocole expérimental d'avant (clear + configuration), **sans affirmer que ces transitions sont bonnes**.
- UART : `HW3 ORIENTATION_REUSED case=9 MADCTL_UNCHANGED=1 CLEAR_SKIPPED=1` et `HW3 FULL_REPAINT_PASS case=9 mode=MIRE|BOOT` ; les changements d'orientation marquent `HW3 ORIENTATION_APPLIED case=...`.

**Protocole discriminant, à réaliser sur le CYD après compilation C5 :** rebooter, photographier l'écran initial ; envoyer `9` (mire), puis `b` (boot), **sans passer par `a` ni `c`**. Comparer au démarrage et conserver le journal UART. Si cet aller-retour devient conforme, répéter `9`/`b` trois fois. Si l'échec subsiste **malgré les marqueurs `ORIENTATION_REUSED`**, l'hypothèse « réécriture répétée de MADCTL » n'est pas suffisante ; arrêter les essais de miroir et instrumenter fenêtres `CASET/RASET`, transferts `RAMWR` et intégrité du tampon avant/après DMA. Tester les transitions 9→10→9 séparément, car la correction C5 ne prétend pas les traiter.

**Statut :** `HW3-C5 — CORRECTION DE CONTRÔLE D'ÉTAT, NON VALIDÉE SUR CYD — PR #66 OUVERTE / NON FUSIONNÉE`.

## Budget mémoire et signalisation

Le rendu n'utilise qu'un **tampon DMA interne de 320 × 8 × 2 = 5 120 octets**, aligné et alloué via `heap_caps_malloc(MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA)`, et une grille texte statique de **40 × 25 = 1 000 octets** en .bss. La fonte (`128 × 8 = 1 024 octets`) réside en lecture seule en Flash. Aucune allocation de **153 600 octets** (framebuffer RGB565 320 × 240), aucun recours à la PSRAM. Le tampon est conservé tant que le rendu fonctionne pour ne pas fragmenter le heap.

Un sémaphore est émis par le callback de fin de transmission SPI couleur. Le thread **attend l'acquittement DMA** avant de réutiliser le tampon ; le curseur clignotant transmet seulement **8 × 8 × 2 = 128 octets**. L'unique instance de `app_main` utilise une pile configurée à **6 144 octets** (`CONFIG_ESP_MAIN_TASK_STACK_SIZE`). La marge réellement disponible doit être relevée au runtime par `uxTaskGetStackHighWaterMark(NULL)` (ESP-IDF exprime cette valeur en **octets**, contrairement au FreeRTOS d'origine), et non estimée à partir du seul binaire.

Marqueurs UART 115200 attendus :
```text
HW3 START
HW3 BUILD_IDENT project=loco_esp32_display_probe ...
HW3 LCD_INIT_PASS
HW3 DEVICE_MEMORY phase=LCD_INIT_PASS heap8_free=... heap8_largest=... heap8_min=... stack_margin_bytes=... dma_buffer_bytes=5120 text_grid_bytes=1000
HW3 BOOT_SCREEN_DRAWN
HW3 DEVICE_MEMORY phase=BOOT_SCREEN_DRAWN ...
HW3 CURSOR_BLINK_ACTIVE
```
Si un échec survient, `HW3 LCD_INIT_FAIL`, `HW3 LCD_DRAW_FAIL`, `HW3 LCD_BACKLIGHT_FAIL` ou `HW3 CURSOR_DRAW_FAIL` sont écrits avec la cause ESP-IDF ; ne pas prétendre que le boot a été dessiné. Aucun identifiant MAC n'est exposé dans les marqueurs.

## Compilation et flash

Avec **ESP-IDF v5.5.6** activé sur Linux et le dépôt dans une copie de travail indépendante :

```bash
# Depuis la racine du dépôt, si la branche HW3 a déjà été poussée :
git fetch origin
git worktree add ../ESP32-Locomotive-Basic-HW3 -b hw3-local --track origin/spike/hw3-cpc-boot-display
cd ../ESP32-Locomotive-Basic-HW3/firmware/esp32_display_probe
idf.py --version                 # ESP-IDF v5.5.6
idf.py set-target esp32
idf.py build
idf.py size
idf.py size-components
idf.py -p /dev/ttyUSB0 flash monitor
```

`Ctrl+]` pour sortir du moniteur. **Attention :** flasher HW3 remplace temporairement le firmware BASIC actuel sur le CYD physique ; il ne modifie aucun autre répertoire source ni aucune branche Git. Ne pas lancer le flash en même temps qu'une session de test BASIC sur la même carte.

## Niveaux de preuve

- `TARGET_BUILD_VERIFIED` exige une exécution réussie de la compilation **Xtensa ESP32** en ESP-IDF v5.5.6. CI : workflow indépendant `.github/workflows/hw3-display.yml` ; preuve retenue : log build, ELF/architecture, taille Flash/RAM, version compilateur et sdkconfig effectif.
- Les workflows historiques sont **inchangés** ; la CI générale de PR reste une barrière de non-régression indépendante de la sonde.
- `ON_DEVICE_UNVERIFIED` tant que le Product Owner n'a pas flashé le CYD physique et fourni **photo non générée**, **log UART complet** et **observation du clignotement du curseur** sans plantage. Le callback de fin DMA et le mapping RGB/BGR ne sont pas validés par un build.
- Le commit HW3 ne doit être fusionné par Pilotage qu'après ces contrôles physiques et la revue contradictoire.

### Checklist pour l'essai du Product Owner

1. Confirmer la révision exacte (ESP32-2432S028R, Flash 4 MiB, PSRAM absente, écran ILI9341).
2. Flasher la sonde et photographier l'écran en entier, orientation et marges visibles.
3. Vérifier l'absence d'effet miroir, le bleu du fond/bord et le jaune du texte.
4. Observer le **curseur jaune plein clignotant** sous `Ready`, 500 ms par alternance, pendant au moins 30 secondes.
5. Joindre le log UART (du reset au clignotement), avec valeurs `DEVICE_MEMORY`, et déclarer tout reset/WDT.
6. Noter les options `HW3_LCD_BGR`, `HW3_MIRROR_X`, `HW3_MIRROR_Y` réellement utilisées.

**État actualisé HW3-C1 :** l’essai initial a échoué visuellement ; huit cas disponibles pour un retest physique. Pas de données mémoire physiques inventées ni de succès visuel présumé.
