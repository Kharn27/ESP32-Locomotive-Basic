# HW4-FONT-A — Police ASCII imprimable originale (C99, CYD)

Mandat : [issue #97](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/97#issuecomment-6465196314).
Point de départ vérifié : `main@155f428155ec6abe1519196a7beac8cb4e1edc87`.
Sans extraction ou adaptation de la ROM Amstrad : dessins 8x8 **originaux**.
La fidélité graphique au CPC réel est `OBSERVED_VISUAL` uniquement,
**jamais** `MATCH_EXACT`.

## Inventaire (codes inclusifs)

| Intervalle | Caractères | Situation avant | Situation après |
|---|---|---:|---:|
| 0x20–0x2F | Espace et `!"#$%&'()*+,-./` | HW3 + console partiels | 16/16 |
| 0x30–0x3F | `0123456789:;<=>?` | HW3 + console partiels | 16/16 |
| 0x40–0x4F | `@ABCDEFGHIJKLMNO` | HW3 partiel | 16/16 |
| 0x50–0x5F | `PQRSTUVWXYZ[\\]^_` | HW3 partiel | 16/16 |
| 0x60–0x6F | Accents ASCII (accent grave) et `abcdefghijklmno` | HW3 partiel | 16/16 |
| 0x70–0x7E | `pqrstuvwxyz{|}~` | HW3 partiel | 15/15 |
| **TOTAL** | **0x20–0x7E** | **61/95 effectifs** | **95/95 définis** |

**Avant :** 53 codes dans `cpc_font.c` (dont espace), 8 substitutions
supplémentaires uniquement dans `hw4_c2_console.c` :
`%`, `=`, `+`, `-`, `>`, guillemet, deux-points et barre oblique.
34 codes restaient invisibles malgré leur réception UART.

**Après :** 53 glyphes HW3 inchangés, huit motifs de console copiés
**à l'octet** dans la source canonique, et 34 dessins 8×8 nouveaux :
`! # $ & ' * , ; < ? @ G H J Q Z [ \\ ] ^ _ `accent-grave` b g h j k q x z { | } ~`.
La police comporte 95 codes définis ; **94 produisent au moins un
pixel**, `0x20` (espace) reste volontairement vierge.
Le glyphe de diagnostic `0x7f` reste identique. Pas d'extension
aux codes CPC spéciaux ni aux caractères de contrôle.

## Organisation et parité

- `cpc_font.c` constitue la **seule table** bitmap, immutable
  `static const uint8_t glyphs[128][8]` ; `hw3_glyph_row()` conserve sa
  signature et le garde-fou pour caractère >= 128 et ligne >= 8.
- `hw3_glyph_callback()` dans `cpc_font.h` adapte cette fonction à
  `CpcGlyphRow` ; le boot HW3 et le texte HW4 utilisent désormais les
  **mêmes octets**, sans second tableau dans la console.
- La suite `hw4_font_a_ascii95_canonical_mode1` recalcule FNV-1a sur
  **les 61 anciennes définitions** en ordre ASCII, code + huit lignes :
  `0xee66f2f1` ; et sur `0x7f` : `0x5a077bb6`.
  Ces deux empreintes sont fixées d'après le code de départ et ses huit
  substitutions locales, et non d'après les nouvelles formes.

## Preuves hôte à produire sur le HEAD final

Le test fait passer les 95 codes dans le vrai `uart_line_feed` puis
`cpc_uart_console_append` / `cpc_text_write` / `cpc_video_put_cell`,
contrôle bit à bit les pixels MODE1 par `cpc_video_get` **et**
`cpc_video_render_row`, et vérifie le curseur et la VRAM de 16 000
octets avec deux canaris. L'entrée source est comparée aux octets
collectés, sans modification. Le second scénario utilise réellement
`bsr_submit("10 A%=2")` puis `LIST`, vérifie les bytes du listing
et leurs pixels, contrôle l'invariance des octets du programme avant
et après rendu et `cpc_uart_console_clear`. Les entrées illégales
(row >= 8, ch >= 128, colonne 40, ligne 25) sont également testées.

Build Linux (dans la racine du dépôt) :

```sh
cmake -S . -B /tmp/loco-font-a -DBUILD_TESTING=ON
cmake --build /tmp/loco-font-a --parallel
ctest --test-dir /tmp/loco-font-a -R 'hw4_font_a_ascii95|hw4_c3_boot_screen|hw4_c2_native_uart_runtime_tft' --output-on-failure
```

Pour preuve définitive : utiliser les quatre cellules GCC/Clang et
sanitizers OFF/ON, CI-CPC-PERMANENT, CI-ARCH, et les trois configurations
Xtensa de la PR. Les chiffres mémoire doivent être lus **dans les
artefacts de build de son HEAD**, pas déduits de la taille de table.

## Vérification physique PO (après confirmation CI et HEAD)

Depuis le *workspace actuel* du dépôt, checkout de la branche de PR.
Confirmer `git rev-parse HEAD` **SHA complet**, puis utiliser ESP-IDF
v5.5.6 déjà configuré :

```sh
cd firmware/esp32_display_probe
idf.py -DHW4_C2_CONSOLE=ON build
idf.py -p /dev/ttyUSB0 flash monitor
```

Contrôler au boot la ligne `App version` / SHA du firmware attendu.
À 115200 bauds, saisir **sans valider Entrée** :

```text
! G H J Q Z abcdefghijklmnopqrstuvwxyz []\\{}~@#$?
```

Regarder la forme de chaque caractère avant de l'envoyer (ligne
longue susceptible de passer sur deux lignes). Pour ne pas soumettre
cette chaîne invalide au BASIC, l'effacer au terminal, ou valider
en acceptant l'erreur prévue, sans conclure à une panne de parser.

Ensuite saisir `!CLS`, vérifier **le ! visible avant Entrée**, puis
la disparition de l'écran à validation. Enfin entrer `10 A%=2`,
`LIST`, puis assez de lignes pour déclencher le scroll ; vérifier
les caractères `% =`, l'intégrité du listing, le scroll et le bandeau
de boot au redémarrage.

**Preuves demandées :** SHA intégral checkout, log `App version`,
photo lisible de la saisie avant Entrée, log `!CLS`, photo boot et
constat PASS/FAIL. Sans cela : `ON_DEVICE_UNVERIFIED`.

## Limites et frontières

Pas de bitmap ROM, de runtime PRINT chaîne, de modification du cœur
BASIC, du pipeline vidéo, de l'éditeur ou du pilote LCD. La police
reste une approximation 8×8 lisible : aucune identité pixel à pixel
avec l'Amstrad CPC6128 n'est revendiquée.
