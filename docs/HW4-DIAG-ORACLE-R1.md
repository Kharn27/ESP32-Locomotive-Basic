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

Un **workflow d'acquisition dédié temporaire**, présent au **HEAD d'acquisition `38e3887379477aa885d48bb99736d7e52d82`**, a exécuté le vrai Caprice32 sur la PR, publié l'[artefact d'acquisition #13363502470](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41914521177/artifacts/13363502470) et poussé les originaux dans `tests/fixtures/cpc6128/hw4_diag_oracle_r1/` **sur la branche PR uniquement**, avec contrôle strict du HEAD. Son YAML exact reste conservé dans [`docs/HW4-DIAG-ORACLE-R1-acquisition-workflow.yml`](HW4-DIAG-ORACLE-R1-acquisition-workflow.yml) et dans [le commit original d'acquisition](https://github.com/Kharn27/ESP32-Locomotive-Basic/blob/38e3887379477aa885d48bb99736d7e52d82/.github/workflows/hw4-diag-oracle-r1.yml). **La copie exécutable sous `.github/workflows` a ensuite été retirée** : le routeur CI-OPT3 interdit les nouveaux workflows non enregistrés (`UNKNOWN_OR_MISSING_WORKFLOW`) et le mandat exclut toute modification de la CI standard. La recette reste reproductible hors CI ; sa simple présence dans `docs/` ne déclenche plus d'Actions. Aucune fixture scellée n'a été écrasée.

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

## Témoins acquis — vrais PNG Caprice32 / ROM CPC 6128 BASIC 1.1

**Acquisition indépendante réelle :** [GitHub Actions #41914521177](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41914521177), job `acquire-independent-cpc` **SUCCESS**, le **4 novembre 2026 à 21:16:48–21:16:50 UTC**, exécuté sur **HEAD exact `38e3887379477aa885d48bb99736d7ae27c910a2`**. Archive poussée par l'Action **sur la branche dédiée uniquement**, commit `5162fb35b61857ca641da3f50ed47b7f8b41a463`.

- [Archive brute (artefact Actions #13363502470)](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41914521177/artifacts/13363502470), sans ROM et sans snapshot.
- [Manifeste original JSON archivé](../tests/fixtures/cpc6128/hw4_diag_oracle_r1/manifest.json), **SHA-256 externe dans les logs Actions : `e2dc7ec6b7e0ab9befbee2b0d6b522a9b3bb54b4d1e1baf7b95bd0deea8582af`**.
- **Caprice32 `v4.6.0-8c778bf...`**, modèle `CPC6128`, ROM vérifiée SHA-256 `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562`.
- 4 processus/boots indépendants, **4/4 codes retour 0**, 4 PNG natifs **768×540**, leurs séquences `autocmd.json` et leurs journaux. Les 16 fichiers du manifeste sont identifiés par leur taille et SHA-256 ; contrôle de provenance/données **PASS**. Le même SHA pour original et répétition est une **égalité d'octets de l'écran**, non une duplication du processus (deux départs et deux captures distincts sont consignés).

| Commande directe | PNG original et répétition | SHA-256 de chaque PNG | Message lu sur l'écran CPC | `Ready` après erreur | Statut borné |
|---|---|---|---|---|---|
| `LISTT` | [original](../tests/fixtures/cpc6128/hw4_diag_oracle_r1/original/01_listt_direct/screen.png) ; [repeat](../tests/fixtures/cpc6128/hw4_diag_oracle_r1/repeat/01_listt_direct/screen.png) | `40963349d0c8a6e63e4ae93e08e097983bb5c94f08abc3839ed3e3c5ff87e026` (les deux) | **`Syntax error`** | **Oui** | `CPC_ORACLE_VERIFIED` (cas LISTT) |
| `RUNN` | [original](../tests/fixtures/cpc6128/hw4_diag_oracle_r1/original/02_runn_direct/screen.png) ; [repeat](../tests/fixtures/cpc6128/hw4_diag_oracle_r1/repeat/02_runn_direct/screen.png) | `9320f74f86d72ba8fb581ec20bd2e931c9533ff7e9c8f5d4b4fc0808dcb55844` (les deux) | **`Syntax error`** | **Oui** | `CPC_ORACLE_VERIFIED` (cas RUNN) |

### Transcription visuelle indépendante — blocs pertinents complets

**`LISTT`** : sous la bannière `Amstrad 128K Microcomputer (v3)`, copyrights Amstrad / Locomotive et `BASIC 1.1`, le PNG original montre les lignes :

~~~text
Ready
LISTT
Syntax error
Ready
~~~

Puis un curseur sur la ligne vide suivante. **`RUNN`**, capture issue d'un autre processus CPC (même bannière) :

~~~text
Ready
RUNN
Syntax error
Ready
~~~

Puis un curseur sur la ligne vide suivante. Les **deux répétitions sont identiques bit pour bit** à leurs originaux respectifs et donc portent cette même transcription. Le premier `Ready` est le prompt de démarrage ; le **second est bien émis après le message**. La surcharge `0FPS 0%` en haut à gauche appartient à l'émulateur, **pas au diagnostic BASIC**. Aucun numéro de ligne d'erreur n'est affiché.

Les octets **du texte source de saisie** sont `LISTT = 4C 49 53 54 54` et `RUNN = 52 55 4E 4E` en ASCII (plus ENTER injecté par l'option Caprice32 `-a`). Leurs traces de touches exactes sont archivées dans [LISTT/autocmd.json](../tests/fixtures/cpc6128/hw4_diag_oracle_r1/original/01_listt_direct/autocmd.json) et [RUNN/autocmd.json](../tests/fixtures/cpc6128/hw4_diag_oracle_r1/original/02_runn_direct/autocmd.json), sans injection d'un pré-message écrit par le script.

**Limite de canal :** `Syntax error` et `Ready` sont des **transcriptions de pixels lus visuellement sur les PNG originaux**, pas des octets de RAM écran ni un export texte CPC. Les SHA-256 concernent les **fichiers PNG intégraux** ; on ne prétend pas avoir acquis des codes `ERR`/`ERL`, un buffer de caractères ou des octets BASIC imprimante. La vérification des SHA et des octets d'entrée est automatique, la lecture du texte affiché a été réalisée **séparément** après la capture. Il ne s'agit pas d'un test CPC 6128 matériel, mais d'une exécution **de la véritable ROM CPC6128 dans l'émulateur indépendant épinglé**, sans passer par le C99 du projet.

### Contre-exemple et comparaison demandée

Pour **les seuls cas observés `LISTT` et `RUNN`**, l'écran CPC émet `Syntax error` puis `Ready`, cohérent avec la correspondance d'affichage hôte issue de #291. **Aucun contre-exemple trouvé sur ces deux cas** ; pas de correction CORE/IO justifiée par ces preuves. Cela **ne prouve pas** la classification de toutes les erreurs de saisie directe et ne transforme pas le désassemblage `cb49/cd98` en preuve d'une trajectoire machine observée ou d'un numéro `ERR` effectivement lu.

**Historique de la CI :** sur le HEAD intermédiaire `0ef6beee99cde0595685cffc65e9884086676c9d`, [CI-OPT3 #41915230591](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41915230591) a refusé le *nouveau fichier de workflow*, indépendamment des captures CPC. La livraison conserve la recette sous `docs/` et enlève son enregistrement `.github/workflows` **sans modifier le routeur, sans relancer l'acquisition et sans retoucher aucun octet de preuve**. Les CI du HEAD final doivent être relues séparément ; ce run intermédiaire en échec n'est pas présenté comme un PASS.

Le contrôleur d'archives continue à indiquer `CPC_SCREEN_CANDIDATE_NOT_YET_VISUALLY_REVIEWED` dans le manifeste **original immuable** ; c'est sa classification **au moment de l'acquisition automatique**, volontairement conservée pour éviter une réécriture des preuves. **Le présent rapport porte la revue visuelle ultérieure**, avec ses SHA et son canal distinct. Les falsifications sur copie en mémoire du manifeste (hash PNG, entrée, ROM, verdict automatique) doivent être refusées par le test dédié ; ne jamais modifier les originaux.

**STATUT D'ORACLE PROPOSÉ : `CPC_ORACLE_VERIFIED` — périmètre exactement `LISTT` et `RUNN` dans ces 4 sessions ROM-backed. `ON_DEVICE_UNVERIFIED` pour tout matériel CYD.**

**Frontières maintenues :** ni PR #297 ni jalon d'optimisation d'affichage, CORE, IO, firmware, rendu ou workflows standards touchés. Aucune fixture scellée écrasée. **PR Draft non fusionnée ; la revue et la fusion restent au Pilotage.**
