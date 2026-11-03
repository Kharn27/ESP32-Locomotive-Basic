# HW4-SCROLL-OPT-A1-C0 — PoC double-bande DMA, sans VSCR

Refs [#279](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/279). **Draft, non accepté, non fusionné.** Branche `feat/hw4-scroll-a1-c0-batch16-dma`, base `main@e6096fa0ca159c9eda5fa876d0ecf3eb68a7d07f`. PR #274 **fermée sans fusion** et explicitement exclue.

## 1. Principe, périmètre et sécurité

- Le `!DPROBE ON` UART active **uniquement** les flushs dirty où `CpcVideo.mode == MODE1`, `orientation == 10` et `dirty_bands == 0x01ffffff` (les 25 bandes exactement). `!DPROBE OFF` remet le mode original. **OFF par défaut**, y compris après reboot. `!DPROBE STATS` affiche les compteurs ; les commandes sont hors BASIC et ne modifient pas le programme.
- Le plan portable `hw4_batch16_flush()` appelle le rendu/téléversement des lignes Y **20..35, 36..51, …, 196..211, 212..219** : 12 transferts 320×16 puis 1 transfert 320×8. L'écriture RGB565 big-endian utilise `cpc_video_render_row()` inchangé, avec le scanline temporaire existant de 640 o. **La zone hors 20..219 n'est jamais transférée par ce chemin.**
- Le pilote `cyd_ili9341` garde **un unique buffer `MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA`**, porté de 5120 à **10240 o pour CONSOLE seulement** par CMake. `HW3` et `BASIC_PROBE` restent à 5120 o ; pas de framebuffer/PSRAM supplémentaire, ni de tâche, SPI ou queue dédiés. `max_transfer_sz` suit la capacité.
- Sur chemin groupé seulement : après le retour bloquant `cyd_lcd_send` (sémaphore `on_color_trans_done`) **et uniquement en cas de `ESP_OK`**, les deux bits dirty correspondants sont acquittés. Toute erreur DMA ou timeout déclenche le `s_fault` sticky du HAL, rétroéclairage OFF, ressources épinglées, aucun retry ; le groupe échoué et tous les suivants restent dirty. Un échec de rendu arrête également le repaint sans re-soumission.
- **Tous les autres chemins** (dirty partiels, non contigus, autres modes, cas 9 ou autre orientation, effacement natif, `repaint_full()`, rotation) utilisent le chemin 8 px d'origine. `video/`, `core/`, `integration/`, VRAM 16000, E2 1000 cellules, curseur, BREAK, palette `{1,24,20,6}`, marges et RUN quantum 8 restent inchangés. Aucune commande VSCR ni écriture RAMWR directe.

**Limite de la preuve :** la propriété des dirty bits repose sur le propriétaire unique `app_main`; `cpc_video_flush_dirty()` reste inchangé sur le chemin legacy. Cette variante n'autorise pas un second émetteur ou une mise à jour concurrente de `dirty_bands`.

## 2. Résultat analytique (ce ne sont pas des mesures CYD)

| Paramètre pour un repaint intégral MODE1 | OFF (8 px) | ON (16 px) |
|---|---:|---:|
| Bandes logiques dirty | 25 | 25 |
| Transferts de pixels DMA physiques | 25 × 320×8 | 12 × 320×16 + 1 × 320×8 = **13** |
| Octets utiles de pixels RGB565 | **128000** | **128000** |
| Allocation interne unique DMA (CONSOLE) | 10240 o (même firmware, capacité inutilisée en OFF) | 10240 o |
| Coût brut théorique à 20 MHz (pixels seuls) | 51,2 ms | 51,2 ms |
| Coûts fixes de transaction | 25 | 13 |
| Temps réel p50 / p95 / max repaint | **NON MESURÉ** | **NON MESURÉ** |
| Temps réel end-to-end RUN, qualité visuelle | **NON MESURÉ / NON VÉRIFIÉ** | **NON MESURÉ / NON VÉRIFIÉ** |

`spi_pixel_bytes` désigne **seulement les octets des pixels confirmés** ; les octets de commandes/adresses du contrôleur ne sont pas inclus. Aucun gain de débit, accélération de RUN, amélioration du scroll ni intégrité de GRAM ne sont revendiqués sans CYD.

## 3. Tests hôte reproductibles

```sh
bash tests/run_hw4_batch16_dma.sh
python3 tests/hw4_batch16_a1_audit.py --self-test
```

Host réellement exécuté sous Linux x86_64 : GCC 14.2.0, Clang 17.0.0, chaque compilateur `-std=c99 -O1 -Wall -Wextra -Werror -pedantic`, avec/sans `-fsanitize=address,undefined`. **4 cellules PASS.** Les sources compilées sont vérifiées par les blob SHA GitHub : planner `cbb2f729b5c392ca31810bfda8d4a09afe3d5dca`, header `86d71edacae3fd1947a700c8a32f054a3383cc42`, vecteurs `62ac4b4c40e733f5060a69d79b2ea9aaee2fbb99`, script `e5aa36d94d99e94b27f249959cad0c6277f3d02d`.

Tests : comparaison octet-à-octet 128000 RGB565 BE de 25 bandes legacy et 13 groupes, ordre Y, dernières 8 lignes, canaries au bord des 10240 o, autorisation strictement limitée MODE1/case10/full25, rejet de dirty partiel/non contigu, paramètres nuls, injection d'une panne à chacun des **13 envois** avec vérification du masque dirty résiduel et **un seul appel** sur la panne. L'auditeur a un auto-test **synthétique** positif et quatre rejets négatifs, **sans prétention de preuve matérielle**.

La CI du HEAD GitHub final doit être jugée séparément : CI-C99/ARCH/OPT3/CPC-PERMANENT/Xtensa (CONSOLE/HW3/BASIC_PROBE) et HW4-A0 mémoire. La baseline A0 historique `5799c774a3a5b3d453c17012a2328b379bd587bd` plafonne DRAM à +256 o ; **ne pas élargir les seuils ni maquiller les variations**. Le diff A1 ajoute un drapeau BSS et +5120 o d'allocation **heap runtime** en CONSOLE ; sa compatibilité doit être démontrée par les artefacts ELF et par le PO (`heap8_free/largest/min` et marge pile).

## 4. Instrumentation UART et comparaison OFF/ON

- `HW4-A1-C0 REPAINT_SAMPLE` : un échantillon chronométré **après chaque flush dirty** ; `logical_dirty_bands` demandé, `logical_completed` confirmé, `physical_dma_transfers` confirmés, `spi_pixel_bytes` confirmés, `repaint_us` rendu + DMA, `text_scrolls_total`. Émission de la ligne *hors chronomètre* ; sa présence pèse toutefois sur la durée globale RUN dans **les deux modes**.
- `HW4-A1-C0 RUN_CLOCK edge=start/end` : microsecondes `esp_timer_get_time()`, à soustraire par paire, incluant traitement RUN et stdout de ses repaints, hors saisie et prompt final.
- `HW4-A1-C0 STATS` : cumuls depuis le boot, dont `physical_dma_total_including_boot` (attention : **comprend les effacements/rotations**), histogramme et quantiles A0 bornes supérieures. Ne jamais prendre ce total physique brut pour une fenêtre sans soustraire les points de départ.
- `HW4-SCROLL-A0 SAMPLE/CLASS` et `HW4-C3-B2-C1 LCD_METRICS` sont conservés avec leur schéma historique. Pour les comparaisons A1, utiliser **les échantillons individuels**, regroupés par `mode` et `logical_dirty_bands=25`, et les horodatages RUN distincts.

Audit après capture sur le HEAD final (SHA 40 hex) :

```sh
python3 tests/hw4_batch16_a1_audit.py hw4-a1.uart.log \
  --expect-sha "$(git rev-parse HEAD)" --out hw4-a1-audit.json
```

Le parseur exige IDF 5.5.6, CPU 160 MHz, SPI 20 MHz, OFF initial, capacité 10240, au moins **3 RUN par mode** et un repaint full25 par mode ; il vérifie les octets/transferts, absence de faute et mémoire/pile. Les p50/p95 sont **rangs exacts des échantillons remontés**, et le verdict visuel demeure `PO_UNVERIFIED`. En cas d'échantillons trop peu nombreux, conclure **INSUFFISANT**, ne pas inférer de gain. Ce parseur ne mesure pas les bits de commande SPI sur le fil ni la GRAM physique.

## 5. Protocole PO — CYD obligatoire avant décision de fusion

**Préconditions :** même **ESP32-2432S028R sans PSRAM**, alimentation stable, même firmware/HEAD final, ESP-IDF **5.5.6**, fréquence CPU **160 MHz**, SPI LCD **20 MHz**, case **10** au départ. Attendre le HEAD SHA 40 hex transmis dans la remise développeur finale et vérifier `git rev-parse HEAD` ; ne pas flasher un ancien commit intermédiaire.

```sh
git fetch origin
git switch feat/hw4-scroll-a1-c0-batch16-dma
git rev-parse HEAD # comparer au SHA final communiqué
cd firmware/esp32_display_probe
idf.py --version # ESP-IDF v5.5.6
idf.py -B build-hw4-a1-CONSOLE -DSDKCONFIG="$PWD/sdkconfig.hw4-a1-CONSOLE" \
  -DLOCO_CYD_PROFILE=CONSOLE set-target esp32
idf.py -B build-hw4-a1-CONSOLE -DSDKCONFIG="$PWD/sdkconfig.hw4-a1-CONSOLE" \
  -DLOCO_CYD_PROFILE=CONSOLE build
idf.py -p /dev/ttyUSB0 -B build-hw4-a1-CONSOLE flash
script -q -f -c 'idf.py -p /dev/ttyUSB0 -B build-hw4-a1-CONSOLE monitor' hw4-a1.uart.log
```

Après connexion du moniteur, presser RESET/EN et conserver **tout le log depuis le boot**. Contrôler `DMA_CONFIG unique_buffer=1 allocated_bytes=10240 mode=OFF`, `ORIENTATION_PASS case=10`, `VIDEO_READY mode=1 logical=320x200`, mémoire et `lcd_error=ESP_OK`.

Injecter via UART, **une ligne à la fois**, le programme témoin de l'Issue :

```basic
5 CLS
10 FOR I%=1 TO 40
20 PEN 3:PRINT "ROUGE"
30 PEN 1:PRINT "JAUNE"
40 NEXT I%
50 END
```

Puis :

1. `!DPROBE OFF` (vérifier `CONTROL mode=OFF`), `!DPROBE STATS`, effectuer **3 RUN ou plus**, `!DPROBE STATS`. Capturer photos/vidéo écran et logs complets, noter valeurs `REPAINT_SAMPLE`, `RUN_CLOCK`, `DEVICE_MEMORY`.
2. `!DPROBE ON`, `!DPROBE STATS`, effectuer **3 RUN ou plus** du **même programme inchangé**, `!DPROBE STATS`. Vérifier au moins un échantillon full25 `path=BATCH16 logical_dirty_bands=25 physical_dma_transfers=13 spi_pixel_bytes=128000`, et en OFF `path=LEGACY8 ... physical_dma_transfers=25`.
3. Tester `LIST`, `!CLS` (ne doit pas supprimer le programme), puis `LIST`/`RUN` ; inspecter E2/curseur, palette rouge/jaune, absence de fantômes et marges haut/bas **20+20**. Faire une rotation courte **10→9**, vérifier le repli `LEGACY8`, puis **9→10** et l'orientation/rendu sans corruption ; aucun `!SHOT` n'est une lecture physique GRAM.
4. `!DPROBE OFF`, vérifier le retour au chemin normal, le prompt, l'absence de lignes perdues, la réactivité BREAK UART pendant un RUN si un programme prolongé est volontairement exécuté ; relever heap libre, plus gros bloc, minimum, marge pile, `dma_fault=0`, `dma_timeouts=0`, `lcd_error=ESP_OK`.
5. Arrêter le monitor avec Ctrl+] et exécuter l'auditeur. **Remettre au Pilotage** le log UART brut, JSON de synthèse, `git rev-parse HEAD`, version IDF, photos/vidéo, delta mémoire OFF/ON et avis sur la fluidité réelle.

**Critères STOP** : panne DMA, timeout, corruption/marges, perte dirty, pertes E2/BASIC, crash/stack, SHA différent, données insuffisantes ou gain de repaint non significatif. **Aucune fusion sans acceptation technique du Pilotage et rapport PO sur ce HEAD précis.** Aucun A1-C1 sans mandat.
