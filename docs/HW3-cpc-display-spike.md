# HW3 — Sonde autonome d'affichage du boot CPC 6128

**Périmètre :** issue [#64](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/64), autorisée en parallèle de J1.3-A #62. Ce programme ne contient **ni BASIC, ni Z80, ni ROM CPC**, et n'est pas une implémentation des commandes graphiques. Sa cible est exclusivement `firmware/esp32_display_probe/`.

## Référence et géométrie

Le CPC 6128 démarre en MODE 1, 320 × 200 pixels logiques, 40 × 25 caractères de 8 × 8. Sur l'ILI9341 physique 320 × 240 en paysage, l'aire logique occupe **x=0..319 et y=20..219**, à l'échelle **1:1** ; le BORDER est rendu par les 20 lignes bleues au-dessus et en dessous (sans effet de mise à l'échelle). Le fond bleu occupe l'intégralité de l'écran, comme PAPER et BORDER au démarrage CPC. Ce n'est pas une simulation de la bordure analogique d'un moniteur CRT.

La palette déterministe de cette sonde utilise les deux valeurs par défaut documentées dans les manuels CPC :
- **INK 0 / couleur CPC 1, bleu :** RGB888 `#000080`, RGB565 `0x0010` ;
- **INK 1 / couleur CPC 24, jaune vif :** RGB888 `#FFFF00`, RGB565 `0xFFE0`.

Chaque pixel RGB565 est transmis **octet fort puis octet faible**. La configuration ILI9341 utilise `LCD_RGB_DATA_ENDIAN_BIG` et `LCD_RGB_ELEMENT_ORDER_RGB` par défaut ; pour un module dont la polarité rouge/bleu est inversée, essayer `HW3_LCD_BGR=1` et consigner la valeur choisie sur le CYD réel. Les couleurs perçues sur une photo de CRT/convertisseur vidéo dépendent aussi de l'appareil photographique, du gamma et de l'affichage.

Écran statique : bannière `Amstrad 128K Microcomputer (v3)`, `©1985 Amstrad Consumer Electronics plc`, `and Locomotive Software Ltd.`, `BASIC 1.1`, `Ready`. Le curseur est une cellule 8 × 8 en **colonne 0, ligne texte 11 (indice zéro)**, sous `Ready` (ligne 10), clignotant toutes les 500 ms. Le code source du désassemblage BASIC 1.1 (adresse `C033`) contient `" BASIC 1.1",10,10,0`, et à `C0D7`, `"Ready",10,0`. La disposition de la bannière ROM/OS ainsi que les espaces verticaux demeurent **une approximation visuelle**, à comparer avec une photo réelle de CPC 6128 ; le désassemblage BASIC fourni n'est pas à lui seul une preuve de l'espacement de la bannière système.

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
