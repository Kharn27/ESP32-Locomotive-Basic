# HW4-PEN-A — événements PEN typés → rendu MODE 1 sur CYD

**Mandat :** [Pilotage #188](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/188), base autorisée `main@e857ce66fb28583361ab06cd0d6a642f7fc97a95` après cinq CI `push` (Xtensa 3/3). **Barrière d'acceptation : revue préliminaire Pilotage, puis essai matériel sur le SHA figé par le PO, puis décision du Pilotage ; pas de fusion par le Développeur.**

## Architecture livrée

`bsr_step_events()` reste le seul producteur d'événements vidéo. Le CONSOLE de `firmware/esp32_display_probe/main/hw4_c2_console.c` fournit un tableau **statique de 16 `BEVideoEvent`** (aucune allocation et aucun deuxième framebuffer), collecte les octets PRINT natifs inchangés, et transmet les deux flux au module portable `integration/hw4_pen_bridge.[ch]`. Le module ne dépend que de `core/basic_executor.h` et de `video/cpc_text.h`/CpcVideo, jamais l'inverse, et rejette avant le moindre dessin tout événement illégal, indice logique hors preuve, offset décroissant/hors bornes, ou sink MODE1 invalide. En cas d'échec `bsr_step_events`, aucune mutation TFT/VRAM n'est lancée ; la politique d'erreur HW4 hôte existante reste seule responsable du diagnostic visible.

Les événements sont appliqués dans l'ordre natif des `print_offset`, entre les appels `cpc_text_write()` sur les **sous-tranches des octets PRINT d'origine** : la ligne `PEN 2:PRINT "A":PEN 1:PRINT "B"` fournit `41 0A 42 0A`, événements `(2,0)`, `(1,2)`. Les statistiques `CpcText` et son FNV-1a sont ceux des **quatre seuls octets**, jamais des événements. Le log `HW4-C2 PRINT_BYTES length=4 hex=410a420a` reste **unique** pour la ligne. Les traces supplémentaires `HW4-PEN-A VIDEO_EVENT type=SET_TEXT_PEN logical=... pixel=... print_offset=...` indiquent leur emplacement sans jamais encoder de faux octets.

L'encre de texte est changée par `cpc_video_set_text_colors()` uniquement lors du replay, sans modifier les pixels déjà stockés. Le curseur/dirty-bands/scroll MODE 1 et la surface de **16 000 octets** restent ceux de HW4-C3, en conservant le boot bleu (INK0=1), jaune (INK1=24) et `PEN=1/PAPER=0`. Les deux indices de sortie auparavant inutilisés sont explicitement initialisés à **INK2=6 (rouge)** et **INK3=18 (vert)**, sans changement de la présentation au démarrage.

## Correspondance de domaine bornée — pas une palette CPC générale

| PEN logique observé dans J1.17-A | Pixel MODE1 local | Hypothèse et limite |
|---|---:|---|
| 0,1,2,3 | 0,1,2,3 | indices MODE1 homologues ; encres CYD boot : 1=bleu,24=jaune,6=rouge,18=vert |
| 4 | 0 | **uniquement PAPER0 et INK0=0 ou 1** : le texte se confond avec le fond. Dans l'oracle CPC INK0=0 => noir/noir ; dans le boot CYD INK0=1 => bleu/bleu, **pas noir/noir** |
| 15 | 3 | **uniquement si INK3=18**, vert, comme l'observation P15 ; pas de règle globale |
| 5..14 | aucun | `BE_UNSUPPORTED` côté CORE, **UNVERIFIED** sur CPC |
| 16,-1 | aucun | `BE_INVALID_PEN` côté CORE, diagnostic hôte distinct des erreurs CPC `ERR=5/ERL=10` |

Les correspondances 4→0 et 15→3 sont des **projections expérimentales limitées aux conditions écrites**, indépendantes de l'acceptation logique. Les tests host démontrent la couleur sous les encres configurées ; ils ne remplacent pas une mesure TFT réelle ni ne prouvent une palette CPC complète. Aucun ajout `PEN #`, transparence, `INK`, `MODE`, `PAPER` ni réécriture du cœur J1.17-B.

## Tests automatiques et risques

`tests/test_hw4_pen_a.c` couvre l'exécution numérotée `PEN 2/1/3/4/15` → octets `PRINT` → événements typés → VRAM/pixels/RGB565, la conservation FNV et des cellules, les tranches d'événements et leur ordre, un `PEN` sans impression, l'absence de recoloration rétroactive, les erreurs de type/offset/palette/capacité atomiques, les refus `PEN 16/-1/5/14` après préfixe `PRINT`, et le scrolling en 30 lignes. Les tests historiques de boot, UART, READY, EDIT, scrolling, CPC et RAM sont laissés intacts.

**Limites :** la validation bridge prévient les erreurs **prévisibles** avant de toucher au rendu ; une défaillance TFT matérielle ou une mutation concurrente du sink en plein replay n'est pas transactionnelle. Le CONSOLE conserve le propriétaire unique vidéo et le comportement `repaint_dirty` existant. La capacité maximale de **16 événements par étape** est explicitement bornée : dépassement -> `BE_NO_EVENT_SPACE`, aucune ligne partiellement dessinée.

**Parallélisme :** la PR #184 de rotation/GPIO36/reset touche aussi `firmware/esp32_display_probe/main/hw4_c2_console.c`, `firmware/esp32_display_probe/main/CMakeLists.txt` et `CMakeLists.txt`. Aucun changement #184 n'est repris, aucun rebase ni fusion anticipé : Pilotage doit arbitrer l'ordre d'intégration et toute résolution de conflit.

## Procédure PO — obligatoire *après* revue préliminaire favorable du Pilotage

La PR restera **NON FUSIONNÉE** pendant cette phase. Le Pilotage communique le **HEAD complet** de la PR en revue ; le PO vérifie strictement le même SHA avant compilation/flash. Sur Debian/Linux avec ESP-IDF v5.5.6 actif, dans le dépôt de travail déjà présent :

```sh
git fetch origin
git switch feat/hw4-pen-a-mode1-events
git pull --ff-only origin feat/hw4-pen-a-mode1-events
git rev-parse HEAD           # DOIT égaler le SHA complet fixé par Pilotage
cd firmware/esp32_display_probe
idf.py -DLOCO_CYD_PROFILE=CONSOLE reconfigure build
idf.py -p /dev/ttyUSB0 flash monitor
```

Si la branche locale n'existe pas, utiliser `git switch --track origin/feat/hw4-pen-a-mode1-events` ; conserver son projet VS Code et son répertoire build existant, **sans fullclean, set-target, worktree ni écrasement d'une branche étrangère**. L'écran attend en mode 1, 40×25, fond bleu, écriture jaune, avant tout PEN. Paramétrage TFT explicite : **INK0=1 bleu, INK1=24 jaune, INK2=6 rouge, INK3=18 vert**, PAPER=0, PEN initial 1. Les numéros d'encre sont le modèle digital CPC, non des mesures physiques calibrées.

**Test positif UART** — saisir chaque ligne suivie de Entrée (115200 bauds) :

```basic
NEW
10 PEN 2:PRINT "RED":PEN 1:PRINT "YELLOW"
20 PEN 3:PRINT "GREEN":PEN 15:PRINT "GREEN15"
30 PEN 4:PRINT "HIDDEN"
40 PEN 1:PRINT "YELLOW AGAIN"
50 END
LIST
RUN
```

Sur TFT : `RED` rouge, `YELLOW` jaune, `GREEN` et `GREEN15` verts, `HIDDEN` invisible bleu-sur-bleu dans ce boot (le contenu logique est néanmoins consommé), `YELLOW AGAIN` jaune. Les caractères déjà tracés gardent leur couleur. `Ready` et le curseur restent actifs ; les changements PEN ne mettent pas les octets commandes dans le texte.

**Traces UART positives (formes exactes significatives)** : pour L10, `HW4-C2 PRINT_BYTES length=11 hex=5245440a59454c4c4f570a`, puis deux `HW4-PEN-A VIDEO_EVENT type=SET_TEXT_PEN logical=2 pixel=2 print_offset=0` et `logical=1 pixel=1 print_offset=4`. Pour L20 : `PRINT_BYTES length=14 hex=475245454e0a475245454e31350a`, événements 3 offset0 puis 15 offset6. Pour L30 : `PRINT_BYTES length=7 hex=48494444454e0a` et `logical=4 pixel=0 print_offset=0`. Pour L40 : `logical=1 pixel=1`, `PRINT_BYTES length=13 hex=59454c4c4f5720414741494e0a`. Le nombre d'octets, les offsets et la progression cursor/scroll font foi, pas un `ERR/ERL` CPC inventé.

**Test négatif UART (nouveau programme, aucun changement d'affichage par la ligne invalide)** :

```basic
NEW
10 PEN 16
20 PRINT "NEVER"
RUN
```

Attendu : `HW4-PEN-A STEP_DIAG category=INVALID_PEN events_applied=0 print_applied=0 origin=HOST_NOT_CPC_ERR`, `HW4-C2 BSR_STEP_FAIL ...`, diagnostic d'erreur HW4, **aucun PRINT_BYTES de NEVER**. Optionnel : répéter pour `PEN 5` et constater `UNSUPPORTED_UNVERIFIED` sans la confondre avec une erreur historique CPC.

**Scroll / curseur** (après un NEW, volontairement borné par le budget de RUN et pouvant afficher l'erreur hôte de budget à la fin) :

```basic
NEW
10 PEN 3:PRINT "SCROLL GREEN"
20 GOTO 10
RUN
```

Attendu : au-delà de 25 lignes, `HW4-C3-B2 SCREEN_SCROLL rows=... total=...`, texte vert, curseur/Ready visibles et aucun effacement silencieux de programme. Le budget de 256 étapes peut arrêter l'exécution avec son diagnostic hôte normal ; ce n'est pas une panne PEN.

**Preuves exigées pour le retour PO :** SHA complet de `git rev-parse HEAD` et version firmware dans le journal UART, commande de flash utilisée, photos TFT (au moins alternance rouge/jaune/vert + curseur + scroll), log UART complet avec PRINT_BYTES et VIDEO_EVENT/STEP_DIAG, lignes `MEMORY` heap/plus grand bloc/pile, résultat `PASS/FAIL` par scénario et décision de transmission au Pilotage. **Sans photos/logs réellement obtenus, statut obligatoire `ON_DEVICE_UNVERIFIED`.**

## États / décision

`TARGET_BUILD_VERIFIED` seulement après trois compilations Xtensa sur le HEAD final. La suite C99, les cinq CI, les contrôles d'oracles et les budgets sont cités dans la PR sur son HEAD précis. Aucun test PO ne peut être **auto-validé** par le Développeur ; Pilotage décide après retour physique favorable sur ce HEAD.
