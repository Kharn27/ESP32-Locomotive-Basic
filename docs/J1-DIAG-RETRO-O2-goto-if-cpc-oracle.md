# J1-DIAG-RETRO-O2 — oracle CPC6128 indépendant GOTO / IF

**Mandat Pilotage :** [#235](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/235), indépendant de [A1b #233](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/233).
**Base vérifiée :** main@e76de5c57a39ff9c383129c6d1faaa7babab96e9, après fusion A1a #227.

## Statut

**CPC_ORACLE_UNVERIFIED — collecte authentique encore bloquée.** Le développeur ne dispose dans son environnement ni de la ROM CPC6128 ni de l'exécutable Caprice32 épinglé. Les six sources et le collecteur sont préparés sans créer de faux PNG, de faux manifestes, de texte écran ou de fausses valeurs ERR/ERL. Ce document n'est ni une acquisition ROM ni une acceptation Pilotage.

L'oracle antérieur J1.10-A (docs/J1.10-A-if-then-cpc-oracle.md) a bien observé par **imprimante CPC** un IF vrai vers ligne manquante avec ERR=8, ERL=20. Cette mesure en lecture seule n'établit pas le texte écran exigé par O2 et ne remplace pas la répétition nouvelle. L'audit A0 #224 prouve le message GOSUB, **pas** sa transposition à GOTO/IF.

## Observation historique ROM-backed contrôlée par lecture visuelle (J1.10-A, pas une acquisition O2)

Le 1er novembre 2026, le Développeur a relu visuellement **les deux PNG existants** du corpus scellé J1.10-A, sous les chemins :
- `tests/fixtures/cpc6128/j1_10_if_then/original/F_TRUE_MISSING/run/run.png`
- `tests/fixtures/cpc6128/j1_10_if_then/repeat/F_TRUE_MISSING/run/run.png`

Leur hash SHA-256 brut **identique**, reporté dans le manifeste historique J1.10-A, est `d8a5d254452faedef7586632ecf54cc43d5143d70fc997651a856105985dbf31` ; le programme original archivé, en lecture seule, est :

```basic
10 A%=1
20 IF A% THEN 90
30 PRINT #8,31
40 END
```

Les deux captures montrent, **mot pour mot**, après `RUN` :

```text
Line does not exist in 20
Ready
```

Le manifeste indépendant enregistre `ERR=8`, `ERL=20`, canal imprimante de `printer.dat` distinct de l'écran et paires de processus CPC originaux/repeat. ROM CPC6128 `31c3668c...`, Caprice32 `8c778bf...`, exactement comme identifiés ci-dessous. Ce témoin **démontre une formulation pour l'IF numérique pris avec cible 90 absente et ligne 20**, mais **ne couvre pas encore** le nouveau cas `IF A% THEN 999`, la renumérotation `IF`, ni surtout `GOTO`. Les authentiques nouvelles paires O2 restent `CPC_ORACLE_UNVERIFIED` et ne doivent pas être simulées par recopie de ce PNG. Les archives J1.10-A ne sont ni modifiées, ni dupliquées, ni baptisées « nouvelles captures O2 ».

### Contrôle historique supplémentaire, branche IF non prise

Le Développeur a également examiné le PNG ROM-backed existant de `F_FALSE_MISSING` (`10 A%=0 / 20 IF A% THEN 90 / 30 PRINT #8,31 / 40 END`) : **après RUN, seul Ready apparaît, sans erreur écran**. Son repeat indépendant possède la même empreinte PNG `bbcc08378bb3dfb0bbe65256e92b83e79ca69fff43557c3e60651ec9d15cf48e` et son manifeste atteste `ERR=0, ERL=0` dans les deux processus. La sortie de programme `31` est imprimée via `#8`, **pas** affichée sur le screen. Il s'agit d'une corroboration historique de non-résolution de cible lorsque IF est faux, **pas** de la nouvelle preuve `PRINT "AFTER"` O2.

Le contrôle positif historique distinct `J1.11-A/F_MISSING_TARGET` montre `Line does not exist in 10` puis `Ready` à l'écran après `10 GOSUB 999`. Il reste en lecture seule et ne justifie aucun mapping GOTO. **La formulation de GOTO demeure entièrement non vérifiée par ces archives.**

## Témoignage historique GOTO en **mode direct**, distinct d'O2/RUN

Lecture visuelle indépendante des **deux** PNG de l'archive antérieure `HW4-DIAG-A`, ID `06_d05_direct_goto` :

- Source clavier réelle : `GOTO 999` **sans numéro de ligne et sans RUN**.
- Écran original et repeat : `Line does not exist` (sans `in <ligne>`), suivi d'un `Ready` visible. Ce texte est **transcrit de la capture**, non extrapolé depuis GOSUB.
- `tests/fixtures/cpc6128/hw4_diag_a/{original,repeat}/06_d05_direct_goto/screen.png` ; SHA-256 identique **`d62e0da2a96f4eeecd6cd36101279d65009fd6920fcff911492f23df129dd951`**, selon le manifeste brut.
- Provenance du manifeste `tests/fixtures/cpc6128/hw4_diag_a/manifest.json` : `main` original `2f1aa23aba49aa8b27a12dbd84289fc94f5ed197`, run `40895194240`, Caprice32 `8c778bf...`, ROM CPC6128 `31c3668c...`, `independent_cpc_process=true` dans les deux sessions.
- **ERR et ERL : UNVERIFIED** pour cette session directe ; aucune sonde imprimante n'y est archivée.

Ce résultat apporte une observation ancienne de la famille GOTO, mais **ne prouve ni le texte complet ni le locus pour `10 GOTO 999 / RUN`**. Il ne compte donc pour **aucun des six cas nouvellement requis** par #235 ; archives HW4 conservées en lecture seule. La mission O2 reste `CPC_ORACLE_UNVERIFIED`.

## Six programmes à exécuter

Les fichiers sous tests/fixtures/cpc6128/j1_diag_goto_if_missing/sources/ sont les **sources seulement**.

| ID | Forme | Contrôle à observer, non présumé |
|---|---|---|
| GOTO_MISSING | 10 GOTO 999 ; 20 PRINT "NEVER" | Texte CPC/Ready, absence de NEVER |
| IF_TAKEN_MISSING | 10 A%=1 ; 20 IF A% THEN 999 ; 30 PRINT "NEVER" | Ligne d'erreur 20, pas 10 |
| IF_UNTAKEN_MISSING | 10 A%=0 ; 20 IF A% THEN 999 ; 30 PRINT "AFTER" | Pas de résolution si branche non prise |
| GOSUB_CONTROL | 10 GOSUB 999 ; 20 PRINT "NEVER" | Contrôle positif, sans modifier A0 |
| GOTO_RENUMBERED | 370 GOTO 999 ; 400 PRINT "NEVER" | Numérotation >255 |
| IF_TAKEN_RENUMBERED | 510 A%=1 ; 520 IF A% THEN 999 ; 530 PRINT "NEVER" | Numéro et locus >255 |

Pour **chaque cas**, original et repeat doivent être acquis dans deux répertoires neufs. Chaque acquisition utilise :
1. Une session CPC fraîche de LIST, screenshot pré-RUN et SNA temporaire pré-RUN ; seuls les enregistrements BASIC délimités et sentinelle RAM sont conservés dans program.bin. Le SNA est détruit.
2. **Une autre** session CPC fraîche de RUN, capture réelle run.png, puis commandes directes PRINT #8,ERR et PRINT #8,ERL **après** la capture. La trace printer.dat est un canal distinct de l'écran.
3. Nouvelle acquisition indépendante en repeat. Hash SHA-256 pour chaque fichier ; RAM, captures PNG et imprimante doivent concorder pour soutenir la reproductibilité.
4. Relecture humaine **des deux PNG**, transcription exacte et position du Ready, contrôle des sorties NEVER/AFTER ; aucune OCR ou transcription synthétique.

L'exécutable ancien de capture tests/oracles/j1_11_gosub_return_oracle.py et le lecteur de snapshots tests/oracles/token_ram_oracle.py sont réutilisés **sans modification** pour chaque nouvelle session. L'acquisition ne réécrit jamais les témoins A0/J1.10/J1.11.

## Provenance ROM et Caprice32

CPC6128, Locomotive BASIC 1.1, RAM 128 Ko.
ROM SHA-256 : 31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562.
Caprice32 commit : 8c778bf072a06fb7c23b9cccd179041db7f79a52.
Image ROM-free : ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c.

L'outil exige le git SHA du checkout réel, le SHA de la ROM et le commit Caprice32 avant de créer le dossier de sortie, puis conserve la provenance, les commandes de lancement et les empreintes individuelles. Aucune ROM, ni SNA complet, ni image construite par C99 n'est distribuée comme capture CPC.

## Exécution dans l'environnement CPC authentique

Sur la branche de la PR et son SHA figé, avec submodule réellement initialisé et ROM présente :

~~~sh
git rev-parse HEAD
git submodule update --init --recursive
python3 tools/j1_diag_retro_o2_verify.py --check-sources --self-test

docker run --rm --network none -v "$PWD:/project" -w /project \
  ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c \
  bash -lc '
    set -euo pipefail
    git config --global --add safe.directory /project
    git config --global --add safe.directory /project/tests/oracles/caprice32
    cp /usr/local/bin/cap32 tests/oracles/caprice32/cap32
    cmake -S . -B /tmp/o2-c99 -DBP_SANITIZERS=OFF
    cmake --build /tmp/o2-c99 --target basic_program_image_cli -j2
    python3 tools/j1_diag_retro_o2_verify.py --acquire \
      --caprice tests/oracles/caprice32 \
      --image-cli /tmp/o2-c99/basic_program_image_cli \
      --output tests/fixtures/cpc6128/j1_diag_goto_if_missing/capture
    python3 tools/j1_diag_retro_o2_verify.py --verify \
      tests/fixtures/cpc6128/j1_diag_goto_if_missing/capture
  '
~~~

La sortie doit être **absente** avant toute acquisition : refus automatique d'écraser des témoins. Le manifeste brut ne peut être produit que par des processus Caprice32 réels. Si le processus CPC ne produit pas de fichier imprimante, le vérificateur n'en crée **aucun** et note les sondes `ERR`/`ERL` `UNVERIFIED` plutôt que fabriquer des octets. L'image écran reste une observation distincte. En cas d'indisponibilité de l'environnement ou d'une capture : **CPC_ORACLE_UNVERIFIED**.

## Revue humaine, constat et conformité — correction demandée par Pilotage #5725512564

Le manifeste brut est sous `capture/manifest.json`, avec deux arbres `capture/original/` et `capture/repeat/`. Le fichier `capture/screen_review.json` **ne doit être créé qu'après inspection humaine réelle** des deux PNG de chaque cas. Il contient un objet par ID (`GOTO_MISSING`, etc.) :

- `case` : ID exact ; `provenance` : `CPC_SCREEN_HUMAN_VISUAL` ; `reviewer` : relecteur identifié ; `reviewed_original_and_repeat` : `true` après les **deux** lectures.
- `original` et `repeat` sont **deux objets distincts**, chacun avec `png_sha256` réellement mesuré, `post_run_output_lines` (tableau de **lignes écran réellement émises après la commande RUN et avant le Ready**, transcrites exactement), et `ready_count` (nombre de `Ready` **après ce RUN**).
- Ne pas reporter dans `post_run_output_lines` les lignes de programme que Caprice32 a **échoées lors de leur saisie** : un `PRINT "NEVER"` visible dans le programme saisi n'est **pas** une sortie `NEVER` exécutée. De même, la trace imprimante `#8` n'est pas une ligne écran.
- Pour `IF_UNTAKEN_MISSING`, mesurer explicitement la sortie post-RUN `AFTER`. Pour les cinq cas d'échec, transcrire la ligne d'erreur brute **sans la deviner à partir de GOSUB ou de BEStatus**. Une divergence réelle doit être préservée et signalée, jamais corrigée dans la transcription.
- Le vérificateur exige que les deux relectures aient les mêmes constats lorsque les PNG bruts sont identiques ; sinon `SCREEN_REVIEW_ORIGINAL_REPEAT_TRANSCRIPT_DIFF` et FAIL. Une déclaration `reviewed_original_and_repeat=true` **n'est pas une preuve visuelle autonome** : le Pilotage doit encore relire les deux captures.

**Deux verdicts séparés** après contrôle SHA/archives : `SCREEN_REVIEW=REVIEWED` exprime seulement une transcription renseignée des deux captures ; `BEHAVIOR=BEHAVIOR_PASS` ou `BEHAVIOR_DIFF` vérifie séparément les constats, avec raisons explicites. Les anomalies suivantes sont `BEHAVIOR_DIFF` et **jamais** `BEHAVIOR_PASS` : `ready_count=0` ou double Ready, `NEVER` exécuté **après RUN**, absence de `AFTER` dans le IF non pris, sortie inattendue, ou locus d'erreur absent/différent. Une **vraie** anomalie est toujours archivable comme observation CPC, et son statut DIFF reste visible. L'outil ne convertit **jamais** la simple présence de la revue en `CPC_ORACLE_VERIFIED` : le meilleur résultat automatique, lorsque toutes les revues sont renseignées sans divergence structurelle, est `O2_EVIDENCE_READY_FOR_PILOTAGE_REVIEW` ; la validation finale du texte appartient au Pilotage.

Les mutations automatiques sont des données de test **éphémères en mémoire uniquement**, jamais des PNG ou des oracles factices : **8/8** falsifications de métadonnées refusées (SHA, relecture non faite, fausse provenance, identité absente, structure, Ready invalide, transcriptions original/repeat divergentes), **6/6** divergences de comportement conservées comme `BEHAVIOR_DIFF` (Ready absent, NEVER exécuté, IF non pris sans AFTER, NEVER en IF non pris, mauvais locus, locus absent) et **5/5** corruptions de structure CPC RAM rejetées. `IF_UNTAKEN_MISSING` avec `AFTER` et Ready unique est un positif du **test de politique seulement**, pas une mesure CPC.

~~~sh
python3 tools/j1_diag_retro_o2_verify.py --check-sources --self-test
python3 tools/j1_diag_retro_o2_verify.py --verify \
  tests/fixtures/cpc6128/j1_diag_goto_if_missing/capture
~~~

## Preuves hôte réellement exécutées (1er novembre 2026)

Le fichier `tools/j1_diag_retro_o2_verify.py` de cette PR a été **reconstitué octet pour octet depuis GitHub dans l'environnement de test local** : `git hash-object` = `d90b6ea4260ecf887959969f29b36c96082cd709`, identique au blob GitHub. Les six `.bas` ont également leurs six hashes Git identiques à ceux des six blobs de la branche. Il ne s'agit pas d'une autre version du code ni d'une transcription manuelle différente.

Résultats exécutés avec Python 3 (hôte, pas CPC) :

- `python3 -m py_compile tools/j1_diag_retro_o2_verify.py` : **PASS**.
- `python3 tools/j1_diag_retro_o2_verify.py --check-sources --self-test` : `O2_SOURCES=PASS CASES=6`, `O2_NEGATIVE_MUTATIONS=11/11 PASS`.
- Mutation isolée `10 GOTO 999` en `10 GOTO 998` sur **copie temporaire locale** puis restauration : `SOURCE_DRIFT`, exit 1 attendu.
- `--verify <capture-absente>` : `CPC_CAPTURE_MISSING`, exit 1 attendu, **aucune preuve fabriquée**.
- `--acquire --caprice /does/not/exist --image-cli /does/not/exist --output <capture-absente>` : `PINNED_CAPRICE32_UNAVAILABLE`, exit 1 attendu ; **aucun répertoire de capture créé**.

Ces tests ne valident **ni la création effective d'une archive CPC**, ni la lecture d'un écran O2 réel, ni le comportement final de l'émulateur sur les six nouveaux scénarios. Les contrôles d'acquisition réel original+repeat et de validation complète d'une archive restent à exécuter sur la ROM authentifiée. `CPC_ORACLE_UNVERIFIED` reste le statut obligatoire jusqu'à ce résultat.

## Critères et exclusions

Le statut CPC_ORACLE_VERIFIED demande 6 paires originale/repeat réelles, soit **12 exécutions RUN et 12 pré-RUN LIST/SNA**, les sorties brutes, hashes, provenance et transcriptions humaines; ERR/ERL doivent rester UNVERIFIED si aucune sonde utilisable. Les vérifications CI Linux/CPC/ARCH/OPT3 applicables seront consignées sur le HEAD de livraison. O2 ne demande ni firmware Xtensa ni tests CYD (ON_DEVICE_NOT_APPLICABLE).

**Interdit :** modification core/, io/, firmware/, video/, integration/, CMakeLists.txt, workflows, oracles A0 existants, et tout mapping automatique de BE_MISSING_TARGET. Le correctif natif O2-B n'est autorisable que par nouveau mandat Pilotage après revue de la preuve et coordination avec A1b #233. Le Pilotage décide seul de l'acceptation et de la fusion.
