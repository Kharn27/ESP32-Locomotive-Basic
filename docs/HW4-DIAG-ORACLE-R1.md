# HW4-DIAG-ORACLE-R1 — témoins CPC indépendants de LISTT et RUNN

**Mandat :** [Issue #298](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/298#issuecomment-6633100149). **Base vérifiée au démarrage :** main à `21e95a7197413923bb5976067a0419bc729c20c1`, après intégration Pilotage de #297. **Branche :** `oracle/hw4-diag-oracle-r1`. PR Draft documentaire `Refs #298` ; aucune modification CORE/IO/firmware/rendu/CI standard/scellés.

## Question historique non présumée

Observer, indépendamment du projet C99, l'exécution directe de `LISTT` et `RUNN` sur CPC6128 / Locomotive BASIC 1.1, la sortie **complète à l'écran** et `Ready`. Toute divergence avec « Syntax error » constitue un contre-exemple à remettre au Pilotage, et non à éliminer par modification de la preuve.

`basic.asm` fournit statiquement `cb49: ld a,$02` et le libellé `Syntax` / ` error` à `cd98` ; ceci **ne démontre pas** que les entrées ci-dessus prennent réellement cette voie. Aucun `ERR`/`ERL` n'est déduit.

## Méthode CPC ROM-backed et provenance

L'outillage #298 réutilise exclusivement le pilote Caprice32 historique `tools/hw4_diag_a_cpc.py` ; il n'importe ni ne lance le moteur C99 du projet.

- Caprice32 upstream **`8c778bf072a06fb7c23b9cccd179041db7f79a52`**, version contrôlée sur exécutable.
- Image d'acquisition sans ROM : `ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c`.
- ROM système CPC6128 **32768 octets**, empreinte SHA-256 **`31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562`**, contrôlée sur le sous-module original. Modèle 2, RAM 128 Kio, CPU 4 MHz, clavier anglais, boot à 42 frames, Xvfb.
- Chaque mot est injecté en **commande directe réelle** par un argument Caprice32 `-a LISTT` ou `-a RUNN`, lequel envoie l'ENTER CPC ; la capture est déclenchée ensuite par `CAP32_DELAYCAP32_DELAYCAP32_SCRNSHOTCAP32_EXIT` **dans un seul argument**.
- **Quatre processus CPC indépendants** : `original/01_listt_direct`, `repeat/01_listt_direct`, `original/02_runn_direct`, `repeat/02_runn_direct`. Chaque démarrage produit `screen.png` (écran original non modifié), `autocmd.json` (frappes et paramètres), `cap32.cfg` et `caprice.log`. Aucune ROM, image disque ou snapshot n'est archivée.
- `manifest.json` donne le HEAD d'acquisition, date UTC, run Actions, version/commit/ROM, noms exacts des saisies, SHA et tailles des quatre PNG et des seize fichiers bruts ; le vérificateur rejette toute incohérence, mutation, dossier réutilisé et verdict prématuré.

Le workflow **dédié** `.github/workflows/hw4-diag-oracle-r1.yml` (distinct des 5 workflows CI standards) exécute le vrai Caprice32 sur la PR et dépose un artefact téléchargeable. Si l'acquisition et la vérification réussissent, il pousse les originaux vers `tests/fixtures/cpc6128/hw4_diag_oracle_r1/` **sur cette branche uniquement**, avec bail Git au HEAD et refus de tout écrasement. Ce répertoire est nouveau et n'altère aucune fixture scellée.

### Reproduction autonome (sur l'image CPC épinglée)

~~~sh
cp /usr/local/bin/cap32 tests/oracles/caprice32/cap32
export GITHUB_HEAD_SHA="$(git rev-parse HEAD)"
python3 tools/hw4_diag_oracle_r1_cpc.py --self-test
python3 tools/hw4_diag_oracle_r1_cpc.py \
  --caprice tests/oracles/caprice32 --output /tmp/hw4-diag-oracle-r1-NEUF
python3 tools/hw4_diag_oracle_r1_verify.py \
  --evidence /tmp/hw4-diag-oracle-r1-NEUF --self-test
sha256sum /tmp/hw4-diag-oracle-r1-NEUF/manifest.json
~~~

Utiliser un **nouveau répertoire** pour chaque essai. Hors Actions, `--expected-head <SHA>` peut remplacer la variable d'environnement. Le résultat de l'acquisition ne prouve aucun diagnostic sans lecture effective des images.

## Témoins / résultat

| Saisie directe | Originaux | Octets et SHA | Texte observé et Ready | Classification |
|---|---|---|---|---|
| `LISTT` | Deux démarrages CPC attendus | À acquérir | **Non observé** | `CPC_ORACLE_NOT_ACQUIRED` |
| `RUNN` | Deux démarrages CPC attendus | À acquérir | **Non observé** | `CPC_ORACLE_NOT_ACQUIRED` |

**Barrière :** `CPC_SCREEN_CANDIDATE_NOT_YET_VISUALLY_REVIEWED` est distinct de `CPC_ORACLE_VERIFIED`. Un succès de compilation, de workflow ou de contrôle SHA n'autorise **aucune transcription inventée**. Examiner visuellement les quatre PNG, vérifier le bandeau BASIC 1.1, les deux saisies et la totalité du texte d'erreur, de Ready et des lignes voisines ; noter les différences de répétitions. S'il manque une acquisition, indiquer le blocage et ne pas revendiquer de PASS.

**Frontières :** ni PR #297 ni optimisation d'affichage touchées. Aucun test CYD demandé : `ON_DEVICE_UNVERIFIED`. La **revue, l'acceptation et la fusion** relèvent exclusivement du Pilotage.
