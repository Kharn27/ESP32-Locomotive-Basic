# HW4-DISP-PROFILE-A-C3 — cible SPI40, instrumentation inchangée

Mandat : [Pilotage C3](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/297#issuecomment-6609616678), [#295](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/295), parent [#285](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/285). PR #297 Draft ouverte, non fusionnée. **LE GO PHYSIQUE CYD SPI20 DE C2 EST ANNULÉ.**

## Objet et traçabilité

Base de développement : `feat/hw4-disp-profile-a@4a0f2aad688daad757e2b6ba3fcf3b82d21dd986`, par rapport à `main@2d0487338a50c8592a77d3b909bdb74618d3b778`. HEAD final = SHA GitHub de la PR remis au Pilotage et validé sur ce SHA, pas les commits intermédiaires. La PR #289 `6f799ee96f542f28c959d953c0b6df83f431b50f` a été étudiée **uniquement comme diff**, sans cherry-pick ni revendication d'un test SPI40 sur CYD.

La sélection est dans `spi_clock_select.cmake`, inclus **après** `profile_select.cmake`. Valeurs exactes : `CYD_LCD_SPI_HZ=40000000` (CONSOLE **par défaut**), `20000000` (CONSOLE repli explicite), HW3/BASIC_PROBE **20 MHz uniquement**. Toute autre valeur, notamment 55 MHz et 40 MHz sur HW3/BASIC_PROBE, échoue à la configuration. Composant LCD compilé avec `LCD_CLOCK_HZ` et retour `cyd_lcd_requested_spi_hz()` ; le BOOT imprime la **valeur effectivement compilée dans la HAL** et le SHA Git, avec `electrical_spi_hz=UNMEASURED`, jamais une fréquence mesurée sur fil.

**Invariants :** SPI2, MADCTL géométrie et palette, ESP-LCD, une seule bande DMA 320×8×2 = **5120 o**, soumission synchrone et sémaphore, fail-stop sticky, zéro retry, aucune allocation supplémentaire, quantum RUN=8, aucune retouche BASIC. `full25`, `partial`, `scroll_associated`, 12 bins, p50/p95 **upper**, phases wall et ring 16 de C1 restent inchangés. 40 MHz est une **hypothèse matérielle à vérifier**, pas un résultat. Ne pas comparer les 189 ms de l'ancien essai 20 MHz au nouveau 40 MHz comme un A/B expérimental.

## Vérifications host et Xtensa attendues sur le HEAD final

**Précision lecture ELF :** `xtensa-esp-elf-size -A` inclut le symbole de fin `.iram0.text_end` de **1 octet**, déjà identique en A0, C2 et C3. Le contrôle C3 compare les sections IRAM utiles `.iram0.vectors + .iram0.text` (= 67331 o) et vérifie séparément la présence du marqueur ; il ne doit pas compter une seconde fois ce marqueur comme une régression de code. Le garde A0 historique demeure intact et compare les sections de la même manière entre ses deux références.\n\n
- `python3 tools/ci/hw4_disp_spi_policy.py` : **7 configurations acceptées, 15 refusées**, plus invariants de code SPI/DMA.
- [workflow HW4-DISP-PROFILE-C3](../.github/workflows/hw4-disp-profile-c3.yml) : deux **builds Xtensa du même SHA** CONSOLE SPI40 + CONSOLE SPI20 en dossiers/configurations isolés, comparaison `xtensa-esp-elf-size -A`, sections DRAM/BSS/IRAM/Flash, hashes binaires distincts, SHA embarqué et identités `CMakeCache`, budget DRAM **≤54664 o** et IRAM **=67331 o** pour chacun. HW3/BASIC_PROBE à 20 MHz par [CI-XTENSA U1-B](../.github/workflows/ci-xtensa.yml).
- CI-C99 4/4, ARCH, OPT3, CPC-PERMANENT, HW4-EDIT-P1, HW4-C3-B2, Xtensa 3/3 obligatoirement PASS. La CI A0 **reste volontairement inchangée et FAIL CONSOLE +936 o sous l'exception mémorielle Pilotage C1**, pas un nouveau seuil. Si la DRAM dépasse 54664, l'IRAM change ou les variantes binaires ne se distinguent pas, STOP et réarbitrage préalable.

## Fiche PO — à utiliser UNIQUEMENT après un GO explicite du Pilotage

**PAS DE TEST CYD À EFFECTUER MAINTENANT.** Après revue des preuves, le Pilotage peut mandater **une seule** campagne physique **SPI40**, sans comparaison 20/40, reflash SPI20 ni vidéo. Cloner/synchroniser le SHA exact communiqué dans cette PR, puis :

```sh
git fetch origin
git switch feat/hw4-disp-profile-a
git pull --ff-only
git rev-parse HEAD     # égal au SHA final annoncé par Pilotage
idf.py --version       # attendu ESP-IDF v5.5.6
cd firmware/esp32_display_probe
idf.py -B build-hw4-c3-spi40 -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=40000000 set-target esp32
idf.py -B build-hw4-c3-spi40 -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=40000000 build
idf.py -p /dev/ttyUSB0 -B build-hw4-c3-spi40 flash
script -q -f -c 'idf.py -p /dev/ttyUSB0 -B build-hw4-c3-spi40 monitor' hw4-disp-c3-spi40.uart.log
```

Adapter seulement le port série. Après un appui EN/RESET dans le monitor, contrôler : `HW4-DISP-PROFILE BOOT spi_request_hz=40000000 variant=SPI40 ... sha=<HEAD>`, `LCD_INIT_PASS dma_bytes=5120`, `ORIENTATION_PASS case=10`. Ne pas appeler ce BOOT une mesure électrique.

Commandes **littérales**, une par ligne puis Entrée ; attendre `RUN_TERMINAL` entre RUN :

```basic
!CLS
NEW
5 CLS
10 FOR I%=1 TO 40
20 PEN 3:PRINT "ROUGE"
30 PEN 1:PRINT "JAUNE"
40 NEXT I%
50 END
LIST
RUN
RUN
RUN
```

Après le troisième RUN : `LIST`, puis `!CLS`. Aucun RUN infini/BREAK, aucune vidéo demandée. Conserver un seul UART brut avec SHA, `RUN_DURATION`, les 3 `CLASS` p50/p95 bornés, `SUMMARY`, `TRACE_INFO/TRACE`, phases wall, scrolls, `CLOCK_OVERHEAD_ESTIMATE`, `LCD_METRICS` et `DEVICE_MEMORY`. Vérifier `dma_fault=0`, `dma_timeouts=0`, `lcd_error=ESP_OK`, valeurs réelles `heap8_free/largest/min`, `stack_margin_bytes`, intégrité texte/couleur, ressenti du scroll et absence de reset. Si défaut de stabilité, joindre le log et interrompre ; le fallback SPI20 reste **constructible**, pas une campagne automatique.

Les 128000 octets de 25 bandes donnent un temps brut théorique de 51,2 ms à 20MHz et 25,6 ms à 40MHz **hors commandes, pauses, rendu et attente**. Les trois classes sont deux classes disjointes et une vue recouvrante : ne jamais sommer la vue `scroll_associated` avec les autres. Les p50/p95 sont des bornes d'histogramme, pas des temps exacts ni des FPS optiques.

## Conclusion et limites

`TARGET_BUILD_VERIFIED` n'est pas `ON_DEVICE_PASS`. La PR reste **Draft/non fusionnée**. Le choix ultérieur RENDER, DMA, PACING ou STOP appartient au Pilotage **après** le rapport réel CYD 40MHz. Aucun nouveau jalon ni autorisation physique implicite.
