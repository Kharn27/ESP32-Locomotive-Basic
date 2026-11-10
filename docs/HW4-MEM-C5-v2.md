# HW4-MEM-C5 — Contrats mémoire v2 (prototype ADDITIF, #341)

**Statut : expérimental, non required, non promu.** Branche dédiée depuis
`main@03f83c39e6f9ed4daeddb1ed93a989a35d726e30`, **aucune fusion
autorisée au Développeur**. Réception technique et promotion éventuelle
réservées au Pilotage. Les comparateurs originaux A0, RENDER-A et C3
restent inchangés et leurs statuts rouges restent vrais.

## Sources et seuils historiques NON remplacés

| Contrat | Commit de référence immuable | IRAM | DRAM | Verdict historique constaté |
|---|---|---:|---:|---|
| A0 | `5799c774a3a5b3d453c17012a2328b379bd587bd` | 67 331 | 53 728 | `HISTORICAL_DEBT` main CONSOLE +220 IRAM / +1 136 DRAM |
| RENDER-A | `21e95a7197413923bb5976067a0419bc729c20c1` | 67 331 | 54 864 | `HISTORICAL_FAILURE` si main/head 67 551 |
| HW4-DISP-PROFILE-C3 (B3) | `989ec54989537a31c3a9be8074f1ce7c47708f17` | 67 331 | 54 168 | `HISTORICAL_FAILURE` si main/head 67 551 |

C4 #338, run [42398280615](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42398280615) : IRAM `e500→e008` **+220 B**
dans `.iram0.text`, sans cause exclusive prouvée (`ROOT_CAUSE_UNVERIFIED`).
A0 est autonome, avec IRAM delta=0 et DRAM delta≤256 : **C5 ne l'évalue
ni ne modifie son verdict**.

## Modèle C5 / contrat versionné

`tools/ci/hw4_mem_c5_v2.py` consomme une preuve issue de **quatre
compilations réellement indépendantes** : `base/spi40`, `base/spi20`,
`head/spi40`, `head/spi20`. La base et le HEAD sont les SHA renvoyés
par l'API GitHub pour **une PR ouverte réelle** ciblant `main`, vérifiés
au moment de la compilation **puis après**. Aucun arbre synthétique ni
requalification du merge-base en base de mesure.

- RENDER-A v2, **SPI40/CONSOLE seulement** : `HEAD.iram≤BASE.iram`,
  `HEAD.dram≤BASE.dram`. Le budget historique absolu
  67 331 IRAM / 54 864 DRAM est calculé et signalé **à part**.
- SPI-C3 v2, **SPI40 et SPI20 chacun** : aucun accroissement IRAM/DRAM
  versus la base GitHub réelle ; DRAM absolue≤54 864, coût relatif B3
  entre 0 et 696 ; parité IRAM/DRAM des deux fréquences à la base **et**
  au HEAD ; SHA256 des BIN de fréquences différentes.
  Le 67 331 IRAM B3 n'est jamais proclamé PASS si 67 551 sont mesurés.
- **BSS est compris** dans le total DRAM de `.dram0.*`. On archive BSS
  et le delta séparément, sans lui inventer un quota autonome.
- `INCREMENTAL_PASS` / `INCREMENTAL_FAIL` et
  `SPI_VARIANTS_PARITY_PASS/FAIL/UNVERIFIED` décrivent seulement C5.
  La dette historique apparaît comme `HISTORICAL_DEBT` avec
  `HISTORICAL_FAILURE` par ancre. Le code retour du prototype est
  `0` seulement pour une preuve complète sans régression/parité fautive,
  `1` pour les régressions ou la parité démontrée en échec,
  `2` pour `MEASUREMENT_INVALID`. **Un code retour 0 ne met aucun
  contrôle historique au vert**.

## Chaîne de provenance et mécanismes fail-closed

`tools/ci/hw4_mem_c5_provenance.py` reprend la validation A0 :
numéro/état de PR, `base.ref=main`, repo, SHA complets non nuls,
checkouts distincts, commit Git, arbres, merge-base et ancêtres réels.
Le comparateur v2 **recalcule indépendamment** les SHA/arbres/merge-base
dans les checkouts au verdict. Une branche de PR peut diverger de
`main` ; cette divergence est explicitée (`diverged_from_base=true`)
sans lui inventer une fusion ni un résultat post-rebase.

`tools/ci/hw4_mem_c5_build.sh` lance ESP-IDF **v5.5.6**, image
`espressif/idf@sha256:bf72fe7a15c22849a9a94147301165a545fb8905d97c176cf748e3e4614cac84`,
Xtensa GCC 14.2.0 / ld 2.43.1. Chaque variante requiert
`LOCO_CYD_PROFILE:STRING=CONSOLE`, `CYD_LCD_SPI_HZ:STRING=40000000`
ou `20000000`, et la commande de compilation réelle du HAL ILI9341
avec `-DLCD_CLOCK_HZ=40000000U` ou `20000000U`.

Artefacts consignés : `.elf`, `.bin`, inventaire `xtensa-esp-elf-size -A`,
cache CMake, `compile_commands.json`, SDKCONFIG, IDF/GCC/ld,
digests SHA256 de chaque entrée, Docker image ID, SHA/objet/arbre
source. Le BIN contient le descriptif d'application ESP-IDF (SHA
Git source abrégé sur 7 hex) ; la provenance complète est garantie
par la double vérification des checkouts Git, **pas par ces 7 hex
seuls**. L'ELF doit être Xtensa 32 bits ; le parseur exige sections
obligatoires, total concordant et sentinelle `.iram0.text_end=1`.
Source absente/incohérente, flags manquants, versions discordantes,
provenance altérée, gate B3 ou sortie manquante : pas de PASS implicite.

`tests/test_hw4_mem_c5_v2.py` regroupe des fixtures adversariales
**synthétiques (ce ne sont PAS des mesures Xtensa)** : +1 IRAM, +1 DRAM
avec BSS, défauts de parité, deux BIN identiques, mauvais profil,
clock/flag HAL, image/idf/toolchain/sdkconfig, sections manquantes,
mauvais ELF/BIN/app SHA, arbres/ancres/merge-base/PR substitués,
sorties absentes. Les preuves Xtensa sont **exclusivement** celles du
workflow dédié.

## Exécution et lecture contradictoire

Workflow additionnel `.github/workflows/hw4-mem-c5-v2.yml`.
La **PR Draft C5 elle-même** est le témoin de bout en bout via
`pull_request` : les deux SHA comparés proviennent de son API GitHub
réelle ; en `workflow_dispatch`, l'opérateur fournit un numéro de PR
ouvert dont `base.sha` doit être exactement le `main@03f83...` mandaté.
La PR #339 n'est pas utilisée comme paire probante C5 : GitHub expose
actuellement `base.sha=ae07e039...` pour #339, différent du SHA
`main@03f83...` imposé ; substituer arbitrairement `main@03f83...`
à cette base violerait la provenance. Son run C3 existant n'est utilisé
que comme source du **référentiel historique B3**, sans toucher #339. Une mutation de `main`,
de base ou de HEAD au cours d'un run entraîne **STOP/INVALID**.
GitHub Actions conserve `provenance.json`, `source.json` pour quatre
constructions, `verdict.json/md` et codes retour ; le run est une
preuve CI **uniquement s'il est entièrement SUCCESS**.

En présence de `RENDER_A_HISTORICAL=FAILURE` ou
`C3_HISTORICAL=FAILURE`, l'ancienne CI reste rouge. Le maintien,
le remplacement, ou la promotion d'un nouveau contrôle requis ainsi
que la résolution des PR #330/#339 exigent **un mandat Pilotage
distinct**. Aucun changement de seuil, relayout, firmware, CMake ou
garde historique n'est introduit en C5.

**Limites :** aucun test CYD physique (`ON_DEVICE_UNVERIFIED`) ;
aucune nouvelle vérité CPC ; `ROOT_CAUSE_UNVERIFIED` ; une comparaison
de SHAs GitHub réel/base divergente ne prédit **pas** le coût
d'une future fusion ou d'un rebase. Exiger un nouveau run sur les
SHA modifiés.
