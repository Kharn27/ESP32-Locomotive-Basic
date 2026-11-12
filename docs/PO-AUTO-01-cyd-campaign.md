# PO-AUTO-01 — recette CYD UART/CRC reproductible (#373)

**Statut :** outil proposé pour revue du **Pilotage** ; la réussite automatique ne certifie pas l'écran physique, la compatibilité générale CPC, ni une imprimante `PRINT #8`. Aucune modification du cœur C99, HAL, vidéo, ROM, baseline ou firmware. La campagne physique de référence #371 concerne `main@4a386ee82f6ca2c5bbf73cf17c794f5274b449e9` et le prototype *hors dépôt* ; elle ne vaut pas test du runner intégré.

## Prérequis et démarrage Linux

- Checkout Git de la révision à tester, avec **aucun fichier suivi modifié** (`git status --porcelain --untracked-files=no` vide). Sources `.bas` immuables dans `tests/oracles/inputs/j1_25_a` ; leurs empreintes SHA-256 sont calculées au départ, listées dans le manifeste et dans les résultats.
- ESP-IDF **v5.5.6** disponible dans le shell (`idf.py`), cible ESP32 classique, profil `CONSOLE`, **sans PSRAM** ; permissions sur `/dev/ttyUSB0` ; `python3 -m pip install pyserial` dans l'environnement Python de l'utilisateur.
- **Arrêter `idf.py monitor`, minicom, screen, tout autre lecteur/émetteur UART**. Le runner vérifie `fuser` si installé, puis utilise un unique `serial.Serial(exclusive=True)` pour RX/TX après l'éventuel flash. La phase `idf.py flash` a son accès série propre *avant* cette session. Ne jamais ouvrir un second monitor. Une ouverture de port peut agir sur DTR/RTS : après ouverture, **appuyer une seule fois sur RESET** et laisser enregistrer le boot entier, sans taper de commandes concurrentes.

Depuis la racine du checkout :

```bash
python3 tools/cyd_po_campaign.py --dry-run --suite j1_25_b2_b3
python3 tools/cyd_po_campaign.py --port /dev/ttyUSB0 --flash --suite j1_25_b2_b3 --shots all
# Réutilisation du binaire déjà flashé : le boot capturé DOIT correspondre au HEAD entier.
python3 tools/cyd_po_campaign.py --port /dev/ttyUSB0 --existing-firmware --suite j1_25_b2_b3 --shots all
```

`--flash` : le runner construit **une seule fois** CONSOLE dans le dossier d'archives (`_idf_build`, `sdkconfig`), contrôle le profil CMake et le descripteur `loco_esp32_display_probe` du **binaire** via `tools/ci/verify_esp_app_version.py`, flashe une fois puis exige un nouveau boot complet attesté. Aucune commande Git mutante, aucun effacement NVS, aucun pull/rebase, aucun autre profil. Le SHA du build local et le SHA compilé exposé au boot doivent correspondre au HEAD à 40 caractères. `--existing-firmware` **n'atteste jamais le firmware au simple vu d'un argument de l'opérateur** : il requiert `START project/version/idf/target`, `HW4-DISP-PROFILE BOOT sha=<40 hex>` puis `UART_READY` et `INPUT_READY`, dans cet ordre. Une version incohérente, un boot absent ou un reset intempestif donnent `INCOMPLETE`.

Les délais sont **des limites de refus** (`--boot-timeout`, `--command-timeout`, `--shot-timeout`), pas des critères de succès. Les commandes `NEW`, chaque ligne numérotée, `LIST`, `RUN` attendent l'écho UART exact `length/hex`, la politique `READY_POLICY`, puis le vrai `INPUT_READY`. Pour RUN, `RUN_START` et `RUN_TERMINAL state=5`, `break_source=none`, SHA, compteurs, état et prompt normaux sont exigés. `!SHOT` est injecté *uniquement après* LIST ou le RUN terminé, jamais pendant le RUN. Le lecteur surveille les diagnostics fatals et les redémarrages à tout instant. Un timeout provoque STOP/`INCOMPLETE` sans injection supplémentaire.

## Couverture et provenance

La suite est **déclarative** : `tools/cyd_po_suites/j1_25_b2_b3.json` référence les six **vrais** fichiers déjà archivés, sans copie ni adaptation. Trois B2 : `TWO_INTEGERS`, `RESTORE_BEGIN`, `RESTORE_TARGET` ; trois B3 : `ONE_STRING`, `QUOTED_COMMA`, `MIXED_TYPES`. Chaque scénario est indépendant grâce à `NEW`. Des suites futures peuvent être ajoutées dans le répertoire de manifestes, avec le même schéma 1 (identifiant unique, groupe, source sous corpus oracle, catégorie `AUTO_UART_CRC`), sans ajouter de logique câblée à ce runner.

| Option | Captures attendues | Portée |
|---|---:|---|
| `--shots all` *(défaut)* | 12 (LIST + RUN pour les six) | `EXHAUSTIVE`, exigée pour la recette #371 |
| `--shots run` | 6 (RUN seulement) | `REDUCED_SMOKE` |
| `--shots none` | 0 | `REDUCED_SMOKE` ; **aucune vérification PNG/CRC** |

Le mécanisme **réutilise** `tools/hw4_shot_watch.py` + le strict `tools/hw4_shot_decode.py`. Chaque trame exige `BEGIN`, 240 `ROW`, `DONE`, CRC ligne et global ; `ABORT`, perte de ligne, doublon d'ID, ordre ou SHA douteux, photo absente, longueur illégale, CRC falsifié => **INCOMPLETE**, jamais un PNG artificiel. Le `seq` monotone et l'`id` proviennent du firmware; les PNG sont nommés `<ID_SCENARIO>_LIST.png` / `<ID_SCENARIO>_RUN.png` avec métadonnées JSON. Les images sont du **RGB565LE logique**, **pas** un relevé du GRAM physique : `LOGICAL_VRAM_VERIFIED` est distinct de `PHYSICAL_TFT_VISUAL_PO_VERIFIED` (réservé au PO).

## Archive, FAIL et confidentialité

Nouveau dossier non écrasable `cyd-campaigns/CYD_J1_25_B2_B3_YYYY-MM-DD_HH-MM-SS_<SHA>/`, contenant `manifest.json`, `uart.raw.log` (**octets RX uniquement, conservés intacts**), `uart.tx.jsonl` (**commandes TX et temps séparés**), `screenshots/*.png`, `results.json`, `rapport_PO_a_completer.md`, `SHA256SUMS`, ZIP autonome interne ; `build.log` / `flash.log` + identité et SHA-256 du binaire si `--flash`. Le dossier de build `_idf_build` reste local mais n'est pas inclus dans ZIP. Les SHA256SUMS couvrent tous les fichiers transmis hors ZIP lui-même (auto-référence impossible). Le SHA-256 du ZIP est affiché sur stdout. Aucune transmission automatisée de traces/GitHub/Internet.

**En cas d'échec, d'interruption Ctrl+C, de port occupé ou de données manquantes**, code retour `2`, archive partielle conservée, statut `INCOMPLETE`. La réussite automatique n'est **que** `PO_REVIEW_PENDING`, jamais `ON_DEVICE_PASS`; les tests manuels `MANUAL_PO_VISUAL` (orientation/écran réel, fluidité, défilement, tactilité) sont consignés par le PO dans le rapport non rempli. Les compteurs `DEVICE_MEMORY` sont conservés tels quels (`heap8_free`, `stack_margin_bytes`, `dma_timeouts`, `dma_fault`, `lcd_error`) et provoquent refus si erreur, sans valeurs fabriquées. Les échecs historiques `RENDER_A_HISTORICAL_FAILURE` sont exclus de la qualification physique de cette suite.

### Tests hôte / CI

```bash
python3 -m py_compile tools/cyd_po_campaign.py tests/test_cyd_po_campaign.py
python3 -m unittest discover -s tests -p 'test_cyd_po_campaign.py' -v
```

Tests simulés **sans CYD** : absence de boot, mauvais HEAD/version/IDF, reboot, panique, ligne UART hors ordre, RUN sans terminal ou terminal incorrect, capture tronquée/CRC fausse/SHA décalé/doublon, 12 PNG et hashes/ZIP, refus d'écrasement, interruption, mémoire défaillante et séparation RX/TX. La CI ne flashe rien et ne peut attribuer une réussite physique. Pilotage effectue la revue de la PR Draft et décide seul de la fusion ; le PO est l'autorité pour les observations physiques.