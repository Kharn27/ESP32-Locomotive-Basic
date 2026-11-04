# HW4-DISP-PROFILE-A-C3 — cible SPI40, instrumentation inchangée

Mandat : [Pilotage C3](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/297#issuecomment-6609616678), [#295](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/295), parent [#285](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/285). PR #297 Draft ouverte, non fusionnée. **LE GO PHYSIQUE CYD SPI20 DE C2 EST ANNULÉ.**

## C3-INT-B3 — intégration J1.24-B3 (04/11/2026)

Mandat complémentaire : [Pilotage #6631162512](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/297#issuecomment-6631162512). Cette branche est synchronisée avec `main@989ec54989537a31c3a9be8074f1ce7c47708f17` par commit de fusion à deux parents (C3-INT et B3). Les tests C99 C3 et B3 sont tous les deux enregistrés ; le diagnostic CPC B3 reste celui de main, sans réécriture de son code.

**Baseline mesurée avant intégration :** CI-XTENSA de main B3 [#41832571009](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41832571009), profil CONSOLE : **54168 octets DRAM, 67331 octets IRAM utile**. Le contrôle C3 reconstruit maintenant `main@989ec54989537a31c3a9be8074f1ce7c47708f17` dans le même ESP-IDF 5.5.6 que les variantes SPI40 et SPI20 et doit prouver un delta propre **≤696 octets**, DRAM finale **≤54864 octets** et IRAM inchangée. **Aucune extension de plafond accordée.** Le garde A0 global n'est ni modifié ni désactivé ; son FAIL historique sous dérogation reste explicitement signalé.

**Réception matérielle déjà réalisée sur l'ancien SHA uniquement :** le PO a flashé `68488bb0f3a6ffe075fdf28303f64c13247ac420` en CONSOLE SPI40 et rapporté 3 RUN complets (2409604 / 2407691 / 2411329 µs), **0 défaut et 0 timeout DMA**, une marge pile de 4240 octets et un scrolling perçu plus fluide. Voir [verdict Pilotage](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/297#issuecomment-6631162512). Cette preuve **ne qualifie pas physiquement le nouveau SHA intégré** : `ON_DEVICE_UNVERIFIED` pour lui ; **aucune nouvelle campagne CYD demandée ni autorisée par ce changement**. Le SCLK LCD électrique reste non mesuré.

La fiche opératoire historique plus bas sert de référence de traçabilité, **pas d'ordre de reflash**. Les anciennes phrases « pas de flash maintenant » et les mentions de GO futur ci-dessous documentent la phase pré-réception C3 et sont supplantées pour la synchronisation B3 par le présent chapitre.

## C3-INT — synchronisation J1.24-B2 (mandat Pilotage 03/11/2026)

Le complément [Pilotage C3-INT](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/297#issuecomment-6612833974) autorise l'intégration de `main@650ea00177fd3efeb8a3a5ec08e576171fea6091` (J1.24-B2, native WHILE/WEND), sans modification de BASIC par la présente PR. Le précédent plafond **54 664 o** est remplacé, **uniquement dans le contrôle local C3**, par **54 864 o de DRAM** ; le surcoût de la PR par rapport au `main` B2 reconstruit doit rester **≤ 696 o**, et l'IRAM utile doit rester exactement **67 331 o**. Ces valeurs sont des conditions à vérifier sur les ELF du nouveau HEAD, pas un PASS acquis.

La CI C3 réalise désormais une **troisième compilation indépendante** du `main` B2 épinglé dans le même conteneur ESP-IDF 5.5.6. Elle compare ses sections réelles (`xtensa-esp-elf-size -A`) aux **deux** compilations CONSOLE SPI40/SPI20 du **même HEAD intégré**, contrôle le coût propre, les deux identités de compilation HAL et les hashes. Le workflow `ci-xtensa.yml` synchronisé depuis `main` contient les ABI BASIC_PROBE `LocoProbeStorage=19280` et `core_descriptor_bytes=844` ; sa vérification 3/3 reste obligatoire. La CI A0 globale et sa référence restent **strictement inchangées** et doivent conserver leur FAIL CONSOLE sous dérogation.

**CYD : pas de flash maintenant.** La fiche opératoire C3 ci-dessous reste la préparation d'un **unique** essai physique SPI40, seulement après arbitrage Pilotage sur le HEAD complet final. Aucun A/B ni essai SPI20 imposé, aucune fusion autonome.

## Objet et traçabilité

Base de développement : `feat/hw4-disp-profile-a@4a0f2aad688daad757e2b6ba3fcf3b82d21dd986`, par rapport à `main@2d0487338a50c8592a77d3b909bdb74618d3b778`. HEAD final = SHA GitHub de la PR remis au Pilotage et validé sur ce SHA, pas les commits intermédiaires. La PR #289 `6f799ee96f542f28c959d953c0b6df83f431b50f` a été étudiée **uniquement comme diff**, sans cherry-pick ni revendication d'un test SPI40 sur CYD.

La sélection est dans `spi_clock_select.cmake`, inclus **après** `profile_select.cmake`. Valeurs exactes : `CYD_LCD_SPI_HZ=40000000` (CONSOLE **par défaut**), `20000000` (CONSOLE repli explicite), HW3/BASIC_PROBE **20 MHz uniquement**. Toute autre valeur, notamment 55 MHz et 40 MHz sur HW3/BASIC_PROBE, échoue à la configuration. Composant LCD compilé avec `LCD_CLOCK_HZ` et retour `cyd_lcd_requested_spi_hz()` ; le BOOT imprime la **valeur effectivement compilée dans la HAL** et le SHA Git, avec `electrical_spi_hz=UNMEASURED`, jamais une fréquence mesurée sur fil.

**Invariants :** SPI2, MADCTL géométrie et palette, ESP-LCD, une seule bande DMA 320×8×2 = **5120 o**, soumission synchrone et sémaphore, fail-stop sticky, zéro retry, aucune allocation supplémentaire, quantum RUN=8, aucune retouche BASIC. `full25`, `partial`, `scroll_associated`, 12 bins, p50/p95 **upper**, phases wall et ring 16 de C1 restent inchangés. 40 MHz est une **hypothèse matérielle à vérifier**, pas un résultat. Ne pas comparer les 189 ms de l'ancien essai 20 MHz au nouveau 40 MHz comme un A/B expérimental.

## Vérifications host et Xtensa attendues sur le HEAD final

**Précision lecture ELF :** `xtensa-esp-elf-size -A` inclut le symbole de fin `.iram0.text_end` de **1 octet**, déjà identique en A0, C2 et C3. Le contrôle C3 compare les sections IRAM utiles `.iram0.vectors + .iram0.text` (= 67331 o) et vérifie séparément la présence du marqueur ; il ne doit pas compter une seconde fois ce marqueur comme une régression de code. Le garde A0 historique demeure intact et compare les sections de la même manière entre ses deux références.\n\n
- `python3 tools/ci/hw4_disp_spi_policy.py` : **7 configurations acceptées, 15 refusées**, plus invariants de code SPI/DMA.
- [workflow HW4-DISP-PROFILE-C3](../.github/workflows/hw4-disp-profile-c3.yml) : deux **builds Xtensa du même SHA** CONSOLE SPI40 + CONSOLE SPI20 en dossiers/configurations isolés, comparaison `xtensa-esp-elf-size -A`, sections DRAM/BSS/IRAM/Flash, hashes binaires distincts, SHA embarqué et identités `CMakeCache`, budget DRAM **≤54864 o** et surcoût C3 **≤696 o** vs main B2 et IRAM **=67331 o** pour chacun. HW3/BASIC_PROBE à 20 MHz par [CI-XTENSA U1-B](../.github/workflows/ci-xtensa.yml).
- CI-C99 4/4, ARCH, OPT3, CPC-PERMANENT, HW4-EDIT-P1, HW4-C3-B2, Xtensa 3/3 obligatoirement PASS. La CI A0 **reste volontairement inchangée et FAIL CONSOLE +1136 o (constaté sur B2, sous dérogation explicite Pilotage) sous l'exception mémorielle Pilotage C1**, pas un nouveau seuil. Si la DRAM dépasse 54864, l'IRAM change ou les variantes binaires ne se distinguent pas, STOP et réarbitrage préalable.

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
