# HW4-MEM-C8-B0 — causalité IRAM Xtensa : chaînon nouveau, causalité finale non attribuée

**Issue :** [#390](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/390), GO Pilotage 17/11/2026. **Dépendance :** [C7-C1 #389](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/389) fusionnée, `main@91cc6b0856cfb4a05fd3ef3f5e5a2bb6aa523084` vérifié au lancement. **Périmètre : Phase A seulement** : archives historiques en lecture seule, aucun code de production modifié.

**Verdict : `BLOCKED_NO_SAFE_PATCH` — `ROOT_CAUSE_UNVERIFIED`.** La cause *globale* est circonscrite au traitement au lien de sections prélink identiques ; le mécanisme **précis** (décision relocation/relaxation, influence de quelle entrée) n'est **pas démontré**. Aucun gain IRAM revendiqué, ni promesse de résultat à -220 octets.

## 1. Chaîne de preuve — vraies archives

| Archive | Run / artifact GitHub | SHA-256 ZIP intégral | Manifeste SHA-256 | Membres validés |
|---|---|---|---|---:|
| B2-B | [#42660089530 / #13693788432](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42660089530/artifacts/13693788432) | `29b8f28c7fcaadd808c3f0ce339ea2a3c18331154a1da08f9116c6ac2c067777` | `0d5011d103cde1ea6429a4d4edbad8ba6a72aefab02cba1b71c6c242dd014c0b` | **134/134** |
| D1 prélink | [#42781263551 / #13746720518](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42781263551/artifacts/13746720518) | `c12bf46013d91cb7ba0389388fa9523a460623944b44e2b8bb2c8c828f61fadc` | `c70a6095a9b9622881a868ee40c80c8fd5653360e6083075940a365bcafe311a` | **228/228** |

Sources historiques **B `4d261f2a76374ab99a4dd7415cae7a097330c46b` / H `64b0087d5087903fee175c4f149c65a65bb43fe6`**. Il s'agit des sources de l'archive, **pas du `main` courant**. L'audit a été exécuté localement sur les deux ZIP téléchargés, aucun ELF simulé ni reconstitution de mesure.

Contrôles : ZIP SHA, manifeste SHA, hash de chaque membre ; quatre MAP B/H SPI40/SPI20 B2-B confrontées aux MAP D1, contribution totale jusqu'à `.dram0.data` ; 18 vrais objets ELF D1 et leurs relocations, commandes de lien et scripts. **Aucune mutation des archives.**

| Élément historique | B SPI40 et SPI20 | H SPI40 et SPI20 | Variation |
|---|---:|---:|---:|
| `.iram0.vectors` | 1 028 | 1 028 | 0 |
| `.iram0.text` | 66 303 | 66 523 | **+220** |
| IRAM hors sentinelle `.iram0.text_end=1` | 67 331 | 67 551 | **+220** |
| DRAM | 54 864 | 54 864 | 0 |
| BSS | 43 792 | 43 792 | 0 |

## 2. Fait nouveau vérifié par rapport à C8-A

Dans les **16 objets système** identifiés dans les cartes de lien, les **sections `SHF_ALLOC` avant lien**, mais aussi les fichiers de **relocations prélink** `*.relocs.txt` et les sorties **sections/symboles prélink** `*.sections-symbols.txt`, sont *identiques B/H octet par octet*. Pour les deux objets `loco_core/basic_executor.c.obj` et `loco_core/basic_session_runtime.c.obj`, les sections allouées et les relocations diffèrent. Le premier a notamment de nouvelles références `bvb_resolve_explicit`, `bvb_read_explicit`, `bp_find`, `bvs_assign`, mais **aucun de ces changements ne prouve une cause particulière du phénomène IRAM système**.

Après normalisation **exclusive** des préfixes de worktree `base/head` et des noms de répertoires de build, **`link-command.txt` et `sections.ld` sont identiques**, et `memory.ld` est identique sans normalisation. La commande de lien contient notamment `-Wl,--gc-sections` et `-fno-lto`. Les MAP des deux côtés portent explicitement les annotations **`size before relaxing`** et exposent des tailles finales différentes **pour des sections d'entrée dont les relocs n'ont pas changé**. Il s'agit d'une preuve vérifiable du *stade* de divergence du traitement de lien ; **pas** de la règle d'optimisation effectivement déclenchée ni de l'élément déclencheur.

### Matrice des 16 contributions postlink, mêmes résultats sur SPI40 et SPI20

| Composant / objet | Code Δ | Littéraux Δ | Total Δ |
|---|---:|---:|---:|
| esp_system / `cpu_start.c.obj` | +20 | +28 | +48 |
| freertos / `tasks.c.obj` | +11 | +12 | +23 |
| spi_flash / `spi_flash_os_func_app.c.obj` | +11 | +12 | +23 |
| esp_system / `debug_helpers.c.obj` | +12 | +8 | +20 |
| spi_flash / `cache_utils.c.obj` | +8 | +12 | +20 |
| esp_hw_support / `rtc_clk.c.obj` | +4 | +12 | +16 |
| esp_system / `startup.c.obj` | +7 | +8 | +15 |
| esp_hw_support / `brownout.c.obj` | +4 | +4 | +8 |
| esp_system / `esp_err.c.obj` | +4 | +4 | +8 |
| spi_flash / `esp_flash_api.c.obj` | +4 | +4 | +8 |
| esp_system / `crosscore_int.c.obj` | +3 | +4 | +7 |
| esp_system / `esp_ipc.c.obj` | 0 | +4 | +4 |
| esp_system / `panic_handler.c.obj` | 0 | +4 | +4 |
| log / `log.c.obj` | 0 | +4 | +4 |
| log / `tag_log_level.c.obj` | 0 | +4 | +4 |
| spi_flash / `memspi_host_driver.c.obj` | 0 | +4 | +4 |
| **Total 16 objets** | **+88** | **+128** | **+216** |

**`*fill*` dans `.iram0.text` : +4 octets. Bilan : +216 + 4 = +220 octets réels.** Aucun `loco_core` ne participe directement à ces contributions IRAM.

### Exemples **adressés** pour falsification, pris des MAP D1

| Source / section postlink | B adresse, taille | H adresse, taille | Δ taille |
|---|---|---|---:|
| `esp_system/startup.c.obj`, `.iram1.0.literal` | `0x40080418`, 8 B | `0x40080418`, 16 B | +8 |
| `esp_system/startup.c.obj`, `.iram1.0` | `0x40081358`, 38 B | `0x400813d8`, 45 B | +7 |
| `esp_system/cpu_start.c.obj`, `.iram1.7.literal` | `0x40080420`, 36 B | `0x40080428`, 48 B | +12 |
| `esp_system/cpu_start.c.obj`, `.iram1.7` | `0x40081380`, 155 B | `0x40081408`, 163 B | +8 |
| `esp_system/esp_err.c.obj`, `.literal.esp_error_check_failed_print` | `0x40080c2c`, 16 B | `0x40080c80`, 20 B | +4 |
| `esp_system/esp_err.c.obj`, `.text.esp_error_check_failed_print` | `0x40087a4c`, 71 B | `0x40087b08`, 75 B | +4 |
| `spi_flash/spi_flash_os_func_app.c.obj`, `.text.get_buffer_malloc` | `0x400902a4`, 63 B | `0x40090374`, 70 B | +7 |

Les adresses, tailles et sections de **tous les 16 objets** sont aussi émises sous `changed_idf[].sections` dans le rapport JSON produit par l'outil versionné. Aucune reconstruction de taille à partir des symboles C source n'est utilisée.

## 3. Cibles des relocations et hypothèse unique

Les tables de relocations système, strictement identiques B/H, contiennent **437 marqueurs `R_XTENSA_ASM_EXPAND` dans les sections de lien attribuées** ; **377** références à des cibles ont une adresse unique dans les tables `linked-symbols.txt` des deux images. **60** références ne sont pas résolues par ce rapprochement (par exemple symboles locaux de section) : c'est une **limite de preuve**, et non une preuve d'absence de condition de relaxation.

Exemple précis : `esp_err.c.obj` comporte quatre relocations `R_XTENSA_ASM_EXPAND` vers `esp_rom_printf`, offsets prélink `0x0b`, `0x20`, `0x2e`, `0x47`, cible absolue B/H `0x40007d54`. Pour l'offset `0x47`, la distance symbolique estimée par l'adresse du bloc et l'offset prélink passe de **-523 583 B** à **-523 771 B**, tandis que le bloc croît de 71 à 75 B. La borne **±524 288 B (512 Kio)** est évaluée comme **hypothèse de tri**, pas comme règle du linker attestée : aucune des **377** cibles résolues ne franchit cette borne entre B et H. Le déplacement de l'instruction après relaxation peut invalider une distance calculée sur l'offset prélink ; ce test ne démontre donc **ni** qu'une relaxation particulière est responsable de +4 B **ni** l'absence d'autres seuils/règles. Le désassemblage **prélink** est disponible, mais l'archive ne fournit **pas** le traçage de chaque relocation vers sa décision **postlink**.

**Hypothèse H1, unique et falsifiable :** les différences de sections/relocations des deux objets applicatifs modifient l'adresse d'une ou plusieurs cibles lors du lien, ce qui change le choix de relaxation/expansion des relocations Xtensa `R_XTENSA_ASM_EXPAND` dans les objets système autrement inchangés, et conduit au coût +220 IRAM. **H1 n'est PAS validée.** La lecture seule démontre un changement de taille *après lien*, pas l'enchaînement causal exact.

**Contre-épreuve nécessaire avant toute correction de production :** reconstruire l'entrée **complète et figée** du linker ESP-IDF 5.5.6 avec le même binaire Xtensa, toutes archives, scripts, options, ordonnancement, `sdkconfig`, puis ne remplacer **qu'un seul** des deux objets applicatifs B/H à la fois, à autres entrées identiques ; relier SPI40/SPI20 et comparer pour chaque `R_XTENSA_ASM_EXPAND` adresse effective, cible, instruction/décision d'expansion, taille de section et gain causal. Si le changement isolé n'explique pas une mutation traçable des mêmes sections, **H1 est falsifiée**. Une simple modification du padding, un réordonnancement opportuniste ou un résultat unique favorable n'est **pas** une preuve. **Cette expérience n'a pas été réalisée :** les deux archives ne contiennent ni la totalité des autres bibliothèques/link inputs ni l'environnement de lien exécutable complet, et le présent environnement ne dispose pas des binutils Xtensa. Il serait inexact de prétendre pouvoir reconstruire ce lien à partir de seuls 18 objets enregistrés.

## 4. Protocole de reproduction et budget

Outil de lecture seule dans `tools/ci/hw4_mem_c8_b0_causal.py`, utilisant les scellements préexistants de `hw4_mem_c8_forensic.py` (aucune modification de cet ancien outil) :

```bash
python3 tools/ci/hw4_mem_c8_b0_causal.py \
  --b2b /path/to/artifact-13693788432.zip \
  --d1 /path/to/artifact-13746720518.zip \
  --output c8-b0-archive-witness.json
```

Les refus attendus sur archive ZIP corrompue, manifeste modifié, changement de section IRAM, relocation système, script de lien ou résultat divergent sont **fail-closed**, sans transformer une archive partielle en succès.

**Budget exploratoire : 0 / 4 vrais builds Xtensa utilisés.** Aucun candidat firmware autorisé, aucun code C/ISR/HAL touché, **aucun gain matériel revendiqué**, aucune CI-C7 réétalonnée. Si GitHub CI construit un firmware inchangé pour cette PR, c'est une preuve d'absence de régression, **pas** un nouveau gain IRAM ni un build exploratoire de contre-épreuve. En cas d'avance de `main` (dont B1 #387), le statut diagnostic reste historique ; aucun seuil RAM ancien n'est reporté automatiquement au nouveau main.

## 5. Remise, limites et sécurité

**Verdict proposé : `BLOCKED_NO_SAFE_PATCH`**, plus précisément **`INSUFFICIENT_EVIDENCE` du chemin relocation→instruction retenue→cause d'une décision de relaxation**, faute de lien contrôlé à un seul facteur. Cette lacune est désormais délimitée par des contrôles nouveaux au-delà de C8-A (identité des relocations, scripts, cibles résolubles et exemples adressés) ; la même dette **#380 demeure ouverte**, la cible **IRAM ≤67 331 B n'est pas atteinte**.

La PR Draft de cette mission ne modifie que le script C8-B0 et ce rapport. Aucune modification du firmware, des comparateurs C7, workflows, budget nominal ESC #387, du code DEV2 ni des archives. **`ON_DEVICE_NOT_APPLICABLE_DIAGNOSTIC_ONLY`**, aucun GO FLASH demandé. Pilotage seul décide de la revue, des éventuelles suites et de la fusion ; le Développeur 1 n'ouvre **pas** C8-B1.
