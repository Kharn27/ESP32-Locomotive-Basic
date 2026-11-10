# HW4-MEM-C6-B2-D1 — Investigation pré-lien #330 (Issue #354)

**LAB strictement non-required. Deux vrais builds au maximum, `B@SPI40` puis
`H@SPI40`, sur une seule exécution.** Aucune correction firmware, nouveau
budget, promotion de contrôle obligatoire, ou mesure M/C/SPI20 n'est admise.

## Mandat et avenants

Le Pilotage a autorisé la base GitHub **`main@3d7f1dc914324a846ff92ba3a33ab9e03916b076`**
(#354 A1/A2) après la fusion de #350, **6/6 CI push SUCCESS** sur ce SHA.
La base réelle #330 et son HEAD doivent rester :

- **B (PR #330 base)** `4d261f2a76374ab99a4dd7415cae7a097330c46b`,
  tree `d74061cb975981aafb022409cf1e9682f934235d`.
- **H (PR #330 HEAD)** `64b0087d5087903fee175c4f149c65a65bb43fe6`,
  tree `ed23017e46a7f54c76447bdb77937de540588ea8`.

Ne pas substituer à B le `main` de la campagne historique (M
`6d3aae8a95b97e18174d758f35ef240740e9a861`), ni le `main`
actuel. Le preview GitHub ancien et le candidat de test-merge M/C de B2-B
ne servent **pas** de source pour les builds D1.

## Contrats de reproduction et sources figées

Oracle externe immuable : run `42660089530`, artefact `13693788432` :
ZIP `sha256:29b8f28c7fcaadd808c3f0ce339ea2a3c18331154a1da08f9116c6ac2c067777` ;
`SHA256SUMS.txt` `0d5011d103cde1ea6429a4d4edbad8ba6a72aefab02cba1b71c6c242dd014c0b`.
Le contrôleur vérifie chaque empreinte des **134 fichiers** et les
manifests `source.json` historiques ; jamais l'`app_version=1` du BIN
pour identifier le commit.

Chaîne identique aux builds de B2-B : image
`espressif/idf@sha256:bf72fe7a15c22849a9a94147301165a545fb8905d97c176cf748e3e4614cac84`,
ID `sha256:b5ed7387fed7f3c0cc613272ee7dedab5dddfac6f771ee66af41d93f8d46c0bc`,
ESP-IDF 5.5.6, GCC Xtensa 14.2.0, ld 2.43.1, CONSOLE et
`CYD_LCD_SPI_HZ=40000000`; vérification dans `compile_commands.json` du
vrai HAL compilé avec `-DLCD_CLOCK_HZ=40000000U`. Chaque source B/H est
un worktree Git propre et isolé ; cache CMake et SDKCONFIG séparés.

Valeurs contractuelles sur les **deux** images : DRAM **54 864**, BSS
**43 792**, IRAM B **67 331** / H **67 551**, `.iram0.text` B
**66 303** / H **66 523**, `.flash.text` B **168 426** / H **170 242**.
Les entrées `.iram0.text` du map comportent 1 052 clés objet-section,
78 051 B pré-relax identiques ; objets post-relax B **65 548** / H
**65 764**, fill B **755** / H **759**. Les huit ELF/maps de B2-B restent
les témoins ; D1 ne lance **aucun** build SPI20 ou M/C.

## Exécution et garde one-shot

Nouveau workflow : `.github/workflows/hw4-mem-c6-b2-d1-prelink.yml`.
Déclenchement : `pull_request.paths` exactement les cinq chemins D1 ;
`workflow_dispatch` reste exposé mais **ne peut lancer le job de builds**.
Le contrôle host vérifie le HEAD et les tests adversariaux (sans token),
puis `opt3_routing.py --self-test` avec inventaire fermé **43 workflows / 5
familles**. La campagne coûteuse n'est autorisée qu'après ce succès.

Avant le premier build et avant/après **chaque** cellule, une lecture GET
GitHub revérifie `main`, B/H et le HEAD/base de la PR LAB. L'historique
GitHub Actions de la branche D1 doit comporter **exactement le run
courant** et `run_attempt=1` : une tentative antérieure, une seconde
ouverture/push, un rerun, une autre branche ou un `workflow_dispatch`
sont **fail-closed**. Concurrency fixe pour #330 et
`cancel-in-progress:false`. Les deux runs ne sont jamais relancés sans
nouveau mandat même en cas de `MEASUREMENT_INVALID`.

Le contrôleur ne se trouve **jamais** dans les objets B/H exécutés :
les sources B/H sont compilées seulement dans un conteneur Docker avec
une liste explicite de variables d'environnement **sans `GH_TOKEN`,
`GITHUB_TOKEN` ni credentials persistés**. Seul le contrôleur confiance
réalise les GET GitHub avec `contents:read, pull-requests:read,
actions:read`. Pas de `pull_request_target`, pas de secrets additionnels,
pas de `push` de code, pas de mutation de PR #330/#339.

## Preuves sélectionnées, avant / après le lien

À chacun des **deux builds**, collecte attestée : ELF, BIN, map,
`xtensa-esp-elf-size -A`, `CMakeCache.txt`, SDKCONFIG,
`compile_commands.json`, versions IDF/GCC/ld, empreintes, commandes
réelles du lien (`link.txt` ou Ninja `-t commands`, **sans exécuter de
lien supplémentaire**), fichiers `.ld`/`.rsp` présents.

Dans les six archives `.a` de composants (`esp_system`, `freertos`,
`spi_flash`, `esp_hw_support`, `log`, `loco_core`) : les **16 membres
IDF/RTOS/log** ayant un delta IRAM dans B2-C, plus `basic_executor.c.obj`
et `basic_session_runtime.c.obj` (18 membres). Chaque membre est extrait
avec `xtensa-esp-elf-ar p`, comparé **bit-à-bit** à l'objet CMake
correspondant, puis examiné par `readelf -rW`, `readelf -SW -sW` et
`objdump -dr`. Les archives complètes et les fichiers d'analyse sont
hashés et conservés. Le contrôle du map conserve les tailles pré/post
relaxation sur 1 052 clés et produit le delta exact (216 + 4 = 220).

La comparaison des **SHA256 complets** de l'ELF, de la map, du BIN,
du SDKCONFIG, des sections et des commandes aux deux anciens témoins
est inscrite dans `*-reproduction.json` ; une divergence binaire n'est
**pas** qualifiée de reproduction bit-à-bit, même si les budgets sont
reproduits. Tout écart de métriques/horloge/profil/objets authentiques
provoque `MEASUREMENT_INVALID`.

Le rapport `prelink-diff.json` expose les SHA256 et les différences de
relocalisations par objet ; `iram-relax-accounting.json` inventorie
les 220 B. L'identification d'une relocation précise et de sa cible
nécessite une lecture contradictoire ultérieure des fichiers acquis :
**l'outil n'émet pas automatiquement `ROOT_CAUSE_VERIFIED`**. Si le
lien exact causal ne peut être démontré, conserver `ROOT_CAUSE_UNVERIFIED`.

## Stabilité des verdicts

- PR #330 historique : `PR_INCREMENTAL_VERDICT=FAIL` (B→H, +220 IRAM,
  SPI40/SPI20), ne change pas sur la base de cette investigation.
- Ancien M/C B2-B : `INTEGRATION_MEMORY_VERDICT=PASS` uniquement sur
  `M@6d3aae8...`→`C@5e5757...` ; aucun M'/C' sur le main de D1.
  `INTEGRATION_READINESS=BLOCKED`.
- `RENDER_A/C3=HISTORICAL_FAILURE`, `A0=HISTORICAL_DEBT`,
  `ON_DEVICE_UNVERIFIED`; `ROOT_CAUSE_UNVERIFIED` par défaut.
- Les LABs B2-A (`MAIN_DRIFT`) et B2-B (`FAIL` réel) sont scellés et
  non-required. Aucun check historique n'est repeint en vert.

**Après fusion éventuelle du LAB :** un nouveau `main` rend périmées les
mesures d'intégration M/C antérieures. D1 ne prétend pas requalifier le
`main` ultérieur. La réception et toute étude D2 ou correction restent
exclusivement sous l'autorité du Pilotage.