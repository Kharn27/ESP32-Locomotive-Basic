# HW4-C1 — premier PRINT du Locomotive BASIC natif sur TFT CYD

Issue [#86](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/86). Branche de développement `feat/hw4-c1-native-basic-tft`.
État au développement : **ON_DEVICE_UNVERIFIED**. Aucune validation sur la carte ne doit être déduite des tests Linux ou d'une compilation Xtensa.

## Contrat et architecture

Troisième image ESP-IDF indépendante : `firmware/esp32_loco/`, avec un seul `app_main`. Les deux bancs `esp32_probe` et `esp32_display_probe` demeurent inchangés. Cette image réutilise le **même** composant `loco_core` (fichiers `core/`), `video/cpc_video`, la police provisoire `cpc_font.c` de HW3 et `firmware/components/cyd_ili9341`.

Flux effectif :

```text
quatre lignes BASIC stockées -> bsr_submit("RUN")
  -> bsr_step() -> sortie brute (4 octets pour PRINT)
  -> cpc_text_write() -> cpc_video_put_cell() / cursor
  -> cpc_video_take_dirty() -> cpc_video_render_row()
  -> cyd_lcd_band() -> cyd_lcd_send() (DMA fini)
  -> écran TFT ILI9341, orientation case 9
```

La constante diagnostique `20 35 20 0a` sert **exclusivement** à invalider une exécution incorrecte ; jamais au dessin, jamais à fabriquer le PRINT. La sortie UART `PRINT_BYTES` provient de la même tranche de buffer passée à `cpc_text_write`. L'intégration Linux exécute les mêmes 4 lignes sur le vrai runtime, compare l'octet-source, le digest FNV-1a de l'adaptateur et la VRAM modifiée.

Le mode est CPC **MODE 1**, 320×200 logiques / 40×25 cellules 8×8, centré en 320×240 avec 20 pixels de marge supérieure et inférieure, bleu (CPC INK 1), jaune (CPC INK 24). Police HW3 provisoire, **pas** la ROM CPC. Le curseur est superposé sans mutation de VRAM. Ce jalon ne revendique ni scrolling ni fidélité des 80 colonnes MODE 2.

`CpcText` est indépendant du matériel (C99, zéro allocation). ASCII imprimable [0x20,0x7e] dessiné, CR = retour colonne zéro, LF = colonne zéro / ligne suivante, CRLF = un seul saut. Le passage après la 40e colonne est différé jusqu'au prochain caractère imprimable ; pas de deuxième saut de ligne à cause du LF. Les commandes hors périmètre sont ignorées et comptées. Les lettres ASCII non dessinées dans la police provisoire restent visuellement vides ; les octets sont toujours comptabilisés. Au bas de l'écran, le texte excédentaire est compté et non écrit ; pas de dépassement VRAM.

Propriété : **une seule tâche** (`app_main`) modifie `CpcVideo`, remplit `cyd_lcd_band()` et appelle `cyd_lcd_send()`. Le driver conserve l'unique tampon interne DMA **5120 octets**. Chaque transfert est bloquant jusqu'à son callback DMA ; timeout => pilote en état de faute et écran éteint. Aucun framebuffer RGB565 complet, aucune allocation en rafraîchissement ; VRAM 16000 octets statiques, buffers BASIC statiques et bornés.

## Tests et preuves attendues

- Linux : `cmake -S . -B build -DBP_SANITIZERS=OFF && cmake --build build -j2 && ctest --test-dir build --output-on-failure` ; réexécuter avec `BP_SANITIZERS=ON`.
- Nouvelles suites `hw4_c1_text_boundaries` (CR/LF, caractère non pris en charge, canaris, 40×25, débordement, curseur, dirty mask, empreinte) et `hw4_c1_native_runtime_tft_bytes` (sortie réelle `bsr_step` vers VRAM).
- Suite des tests BASIC/CPC existante inchangée, PPM existants inchangés.
- ESP-IDF **v5.5.6** : trois builds indépendants et `idf.py size`/size-components, avec données spécifiques à la nouvelle image.
- Log physique requis : `HW4-C1 LCD_INIT_PASS`, `ORIENTATION_PASS case=9`, `VIDEO_READY mode=1`, `PRINT_BYTES length=4 hex=2035200a`, `TFT_PRINT_PASS`, `BSR_END`, `DEVICE_MEMORY`, `ON_DEVICE_TEST_PASS_CANDIDATE`. Ces marqueurs ne constituent un PASS réel que s'ils sont issus de l'UART de la carte au SHA flashé.
- En cas de problème : `BASIC_SUBMIT_FAIL`, `BASIC_STEP_FAIL`, `PRINT_MISMATCH`, `LCD_SEND_FAIL`, `DMA_FAIL`, `DEVICE_MEMORY ... dma_timeouts`; absence de marqueur final.

### Test PO physique obligatoire (après CI verte au HEAD final)

Utiliser le **SHA complet de la PR HW4-C1 finalisée**, communiqué explicitement par le développeur (ne pas flasher `main` par erreur) :

```sh
git fetch origin
git worktree add --detach ../loco-hw4c1 <SHA-HEAD-PR-A-REMPLACER>
cd ../loco-hw4c1/firmware/esp32_loco
git rev-parse HEAD
idf.py set-target esp32
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```

Prendre **une photographie lisible** de l'écran montrant le `5` jaune sur bleu (l'espace initial est significatif) et envoyer le **journal UART complet**, incluant la version, les octets, `BSR_END`, les éventuels timeouts et les métriques `heap8_free`, `heap8_largest`, `heap8_min`, `stack_margin_bytes`. Rapporter pixels anormaux, inversion de l'orientation ou reset éventuel.

## Risques résiduels et gates

Limites volontaires : pas de scroll, jeu de glyphes partiel, pas de REPL, pas de SD/tactile, pas d'émulation Z80, pas de commande graphique BASIC. Les dimensions et ressources physiques demandent preuve UART et photographie au SHA exact. Aucun changement du coeur historique, des fixtures CPC, des oracles et du chantier parallèle J1.7-A.

**Ni fusion autonome, ni autorisation HW4-C2.** Revue contradictoire et décision d'intégration par Pilotage uniquement.
