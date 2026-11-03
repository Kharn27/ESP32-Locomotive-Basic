# HW4-DISP-PROFILE-A-C1 — Mémoire et garde A0 (mission Pilotage)

**Périmètre :** correction de l'instrumentation seule, sur la PR Draft #297. Aucun changement SPI20, DMA, renderer, scheduler, BASIC ou garde CI. Aucun déplacement vers heap, pile, PSRAM ou RTC. Validation CYD en attente du Pilotage.

## Provenance indépendante et triplet de référence

- A0 historique : `5799c774a3a5b3d453c17012a2328b379bd587bd`.
- `main` figé pour la mission : `9f19e500a9a46f1e16121ebc5c678202d7e52d82`.
- HEAD instrumenté initial : `7ccb326b689c1dda931ab6101131e025033d6439`.
- Le garde existant [HW4 A0](https://github.com/Kharn27/ESP32-Locomotive-Basic/blob/9f19e500a9a46f1e16121ebc5c678202d7e52d82/tools/ci/hw4_a0_compare_memory.py) exige **IRAM exactement identique** et **DRAM ≤ A0 + 256 o**, sur le même environnement Xtensa. Aucun seuil n'est modifié dans C1.

**Mesure :** ELF/sections et `idf.py size` ESP-IDF v5.5.6, profil CONSOLE. Les valeurs des 3 références proviennent de vrais artefacts GitHub (non d'estimations) :

- [Run HEAD initial #41642826727](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41642826727), artefact `hw4-a0-memory-CONSOLE` (ID **13232514969**) : `base/a0-CONSOLE-sections.txt`, `head/a0-CONSOLE-sections.txt`.
- [Run main figé #41639230924](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41639230924), artefact `arch-hw4-u1-b-console` (ID **13231329362**) : `reports/u1-b/console/elf-sections.txt` et `size.txt`.
- [Run HEAD initial #41642826948](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41642826948), artefact `arch-hw4-u1-b-console` (ID **13234125459**) et contrôle de la même taille par garde A0.

| Métrique (octets) | A0 | main figé | HEAD initial | Δ main→HEAD |
|---|---:|---:|---:|---:|
| `.dram0.data` | 11 072 | 11 072 | 11 072 | 0 |
| `.dram0.bss` | 42 656 | 42 896 | 43 776 | +880 |
| **DRAM totale** | **53 728** | **53 968** | **54 848** | **+880** |
| `.iram0.*` | 67 331 | 67 331 | 67 331 | 0 |
| `.flash.text` | 123 166 | 158 422 | 161 674 | +3 252 |
| `.flash.rodata` | 50 340 | 54 724 | 55 876 | +1 152 |

- A0→main : **+240 o** DRAM. Marge A0 restante au moment de la mission : **16 o**.
- A0→HEAD initial : **+1120 o** DRAM ; garde A0 **FAIL**, dépassement **864 o**.
- Le binaire complet inclut des composants additionnels et padding ; la table ci-dessus utilise les *sections ELF*, pas la taille du binaire compressé/archivé.

**Analyse symboles ELF :** HEAD initial `s_disp_profile` **824 o** (26.2.1 de l'ancienne structure), `s_lcd_metrics` **88 o** inchangés, `s_scroll_metrics` **216 o** inchangés, `s_text` passe de **44** à **64 o**. Une partie restante du delta vient des autres champs de contexte de profilage et de l'alignement BSS.

## Correction C1 réellement proposée dans ce HEAD

Compression **sans perte de l'information auparavant rapportable** :

1. Historique de **16 repaints** : chaque `Hw4DpTrace` reste fourni au code appelant par un *snapshot* C99, mais la représentation interne est **13 octets** par entrée (1 octet pour 1–25 bandes, puis `uint32` scrolls, durée wall et écart, décodage explicite little-endian). Le `seq` n'est pas dupliqué : il est déterminé par le compteur monotone et la position dans le ring. Exactement les mêmes quatre champs numériques, y compris les saturations `UINT32_MAX` déjà en place pour durée/gap. Index invalide rejeté sans altération ; aucune dépendance à `__attribute__((packed))`, à l'alignement Xtensa ou à l'endianness native.
2. La somme des octets est **exactement** `bands × 5120`. Désormais dérivée, avec garde avant accumulation pour interdire tout débordement du produit.
3. La somme `other_us` est **exactement** `wall_us - render_pack_us - submit_us - wait_us` pour les échantillons acceptés (somme des phases ≤ wall par contrôle existant).
4. `zero_scroll` est **exactement** `n - one_scroll - multi_scroll` pour les échantillons acceptés.
5. Histogrammes **32 bits** des 3 classes, min/mean/p50_upper/p95_upper/max, totaux **64 bits** des phases, catégories, séquences `scrolls=0/1/n`, contrôle de monotonie, rejets atomiques et saturations conservés. Aucun déplacement d'allocation ou raccourcissement d'une plage de compteur.

Sur le layout C99 64-bit de l'ancien agrégateur : 824 o → **640 o** calculés à partir des nouveaux champs (confirmation Xtensa et CI à récupérer sur HEAD final). La trace seule passe de **320 → 208 o**. Les journaux UART conservent les mêmes colonnes, le décodeur remplaçant la lecture directe des structures précédentes.

### Situation et limites

Ce correctif retire les redondances **sans modifier les plages de mesure**, mais la cible **A0 +256 o** n'est pas présumée atteinte. Les trois classes et le ring, avec histogrammes `uint32_t` et sommes `uint64_t`, possèdent une taille incompressible significative. Il est interdit de prétendre qu'un déplacement vers heap, pile, PSRAM ou un déplacement symbolique de la référence rétablit la marge A0. Si le garde échoue toujours, documenter le delta **mesuré sur le nouveau HEAD**, proposer au Pilotage une **exception chiffrée séparée, non appliquée**, sans changer les seuils ni réclamer des tests PO. Toute modification réduisant la fidélité des comptes/valeurs doit faire l'objet d'un arbitrage.

## Vérification attendue

- `test_hw4_disp_profile.c` : classes full25/partial/scroll_associated, 0/1/n scrolls, bin borné, trace 16 circulaire, décodage exact `UINT32_MAX`, index invalide, somme dérivée et rejet avant multiplication, overflow et atomicité.
- `bench_hw4_disp_profile.c` : estimation du coût des compteurs sur hôte seulement.
- CI-C99 GCC/Clang sanitizers OFF/ON, CI-ARCH, CI-OPT3, CI-CPC-PERMANENT, Xtensa 3/3 et **garde historique A0 non modifié** sur le HEAD exact ; DRAM/BSS/IRAM/Flash à relever des artefacts du nouveau run.
- Toute mesure physique est **ON_DEVICE_UNVERIFIED** tant que le PO n'a pas flashé le SHA accepté par Pilotage.

**Pas de décision de fusion ni d'exception au niveau développeur.**
