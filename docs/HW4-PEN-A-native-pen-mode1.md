# HW4-PEN-A — événements PEN typés → rendu MODE 1 sur CYD

**Mandat :** [Pilotage #188](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/188), base autorisée `main@e857ce66fb28583361ab06cd0d6a642f7fc97a95` après cinq CI `push` (Xtensa 3/3). **Barrière d'acceptation : revue préliminaire Pilotage, puis essai matériel sur le SHA figé par le PO, puis décision du Pilotage ; pas de fusion par le Développeur.**

## Architecture livrée

`bsr_step_events()` reste le seul producteur d'événements vidéo. Le CONSOLE de `firmware/esp32_display_probe/main/hw4_c2_console.c` fournit **3 `BEVideoEvent` en stockage statique, via une union C99 alignée partageant les 2 048 octets temporaires historiques de tokenisation** (aucun heap, aucune perte de capacité et aucun deuxième framebuffer), collecte les octets PRINT natifs inchangés, et transmet les deux flux au module portable `integration/hw4_pen_bridge.[ch]`. Le module dépend de CORE/VIDEO pour le replay et d'IO uniquement pour déléguer au vrai clear CONSOLE de C1, jamais l'inverse, et rejette avant le moindre dessin tout événement illégal, indice logique hors preuve, offset décroissant/hors bornes, ou sink MODE1 invalide. En cas d'échec `bsr_step_events`, aucune mutation TFT/VRAM n'est lancée ; la politique d'erreur HW4 hôte existante reste seule responsable du diagnostic visible.

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

## HW4-PEN-A-C1 — récupération de la palette après !CLS

**Mandat correctif :** conserver les encres `INK2=6` (rouge) et `INK3=18` (vert) à la sortie de la commande hôte `!CLS`, sans redémarrer le CYD. La vraie fonction générique `cpc_uart_console_clear()` réinitialise le mode et rétablit seulement INK0/INK1 ; l'intégration CONSOLE la délègue désormais à `hw4_pen_console_clear()`, qui **réapplique INK2/INK3 après le clear**, sans état supplémentaire ni modification de `video/`, `io/`, `core/` ou des oracles.

**Correction mémoire sans réduction de capacités :** le seul `app_main` CONSOLE exécute `bsr_submit()` (tokenisation) puis `bsr_step_events()` (RUN) **séquentiellement**. `BasicScratch` est une **union statique C99** entre les `TEMP_CAPACITY=2048` octets et `PEN_EVENT_CAPACITY=3` événements typés, correctement alignée et validée par un garde de compilation. Le tableau `s_basic.output` reste **physiquement distinct** des événements, garantissant l'absence d'overlap refusé par le runtime ; il n'y a **ni nouvel état statique, ni réduction de buffers**, ni nouveau framebuffer.

**Preuve RED reproductible (avant correction)** : HEAD `17ccd33b45df337e267b0540699bb8a27f06605d`, [CI-C99 41079673659](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41079673659) : le nouveau test compile dans les quatre cellules mais échoue à la ligne `test_c1_real_console_cls_palette` sur `f.video.ink[2]==6U && f.video.ink[3]==18U` immédiatement après le vrai `cpc_uart_console_clear()`. Le test exécute PEN 2, 3, 15, 4 et l'échec atomique PEN 16 **avant et après !CLS**, en contrôlant les pixels RGB565, le curseur et la conservation des lignes BASIC. Le même test est conservé pour la preuve GREEN, après correction du seul point de réinitialisation CONSOLE.

**Synchronisation de branche :** `main@5ec280be85d47e330e8a917dc234a4d24fa49a80` (oracles scellés J1.18-A et rotation/GPIO36/reset de #184, désormais fusionnée) a été intégré dans la PR #190 par commit à deux parents, sans modification des nouvelles archives J1.18-A ni des preuves J1.17-A. Le profil matériel conserve donc le réglage d'orientation **10** et les initialisations tactiles de `main`.

**Protocole PO mis à jour — À EXÉCUTER UNIQUEMENT APRÈS AUTORISATION DU PILOTAGE :** avec le SHA exact retenu par Pilotage et les commandes de flash ci-dessous, saisir le programme positif, constater les couleurs, puis envoyer directement `!CLS` et `RUN` **sans NEW ni rechargement du programme**. Vérifier après le second RUN : mêmes couleurs `RED` rouge, `GREEN` et `GREEN15` verts, `HIDDEN` bleu-sur-bleu, `YELLOW` jaune ; écran effacé avant la réapparition, sans reboot ; conserver `Ready`, curseur, scroll et code BASIC stocké. Répéter le scénario `PEN 16` avant puis après `!CLS` : dans les deux cas diagnostic `INVALID_PEN` hôte, aucune trace PRINT de `NEVER`. Fournir deux photos couleurs avant/après, extraits UART et mesure mémoire `DEVICE_MEMORY` avec le SHA complet. **Aucun flash demandé par le Développeur : Pilotage décide du déclenchement des essais PO.**

## Tests automatiques et risques

`tests/test_hw4_pen_a.c` couvre l'exécution numérotée `PEN 2/1/3/4/15` → octets `PRINT` → événements typés → VRAM/pixels/RGB565, la conservation FNV et des cellules, les tranches d'événements et leur ordre, un `PEN` sans impression, l'absence de recoloration rétroactive, les erreurs de type/offset/palette/capacité atomiques, les refus `PEN 16/-1/5/14` après préfixe `PRINT`, et le scrolling en 30 lignes. Les tests historiques de boot, UART, READY, EDIT, scrolling, CPC et RAM sont laissés intacts.

**Limites :** la validation bridge prévient les erreurs **prévisibles** avant de toucher au rendu ; une défaillance TFT matérielle ou une mutation concurrente du sink en plein replay n'est pas transactionnelle. Le CONSOLE conserve le propriétaire unique vidéo et le comportement `repaint_dirty` existant. La capacité maximale de **3 événements par étape** est explicitement bornée : dépassement -> `BE_NO_EVENT_SPACE`, aucune ligne partiellement dessinée.

**Synchronisation :** #184 est désormais fusionnée dans `main` ; ses modifications GPIO36/rotation/reset sont conservées sans retouche ni code partagé réinventé. Les 243 archives brutes J1.18-A et les 113 témoins J1.17-A restent inchangés. Toute validation de conflit avec `main` se fait sur le HEAD final de la PR #190.

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

**Répétition après effacement :** saisir `!CLS`, puis `RUN` **sans `NEW`**. Le programme existant doit se réexécuter et produire les mêmes couleurs/événements. La commande hôte de clear n'encode aucun événement `PEN` dans `PRINT_BYTES` et ne réécrit pas les lignes BASIC. Une divergence uniquement sur le second `RUN` est un **FAIL C1**.

**Traces UART positives (formes exactes significatives)** : pour L10, `HW4-C2 PRINT_BYTES length=11 hex=5245440a59454c4c4f570a`, puis deux `HW4-PEN-A VIDEO_EVENT type=SET_TEXT_PEN logical=2 pixel=2 print_offset=0` et `logical=1 pixel=1 print_offset=4`. Pour L20 : `PRINT_BYTES length=14 hex=475245454e0a475245454e31350a`, événements 3 offset0 puis 15 offset6. Pour L30 : `PRINT_BYTES length=7 hex=48494444454e0a` et `logical=4 pixel=0 print_offset=0`. Pour L40 : `logical=1 pixel=1`, `PRINT_BYTES length=13 hex=59454c4c4f5720414741494e0a`. Le nombre d'octets, les offsets et la progression cursor/scroll font foi, pas un `ERR/ERL` CPC inventé.

**Test négatif UART (nouveau programme, aucun changement d'affichage par la ligne invalide)** :

```basic
NEW
10 PEN 16
20 PRINT "NEVER"
RUN
```

Attendu : `HW4-PEN-A STEP_DIAG category=INVALID_PEN events_applied=0 print_applied=0 origin=HOST_NOT_CPC_ERR`, `HW4-C2 BSR_STEP_FAIL ...`, diagnostic d'erreur HW4, **aucun PRINT_BYTES de NEVER**. Optionnel : répéter pour `PEN 5` et constater `UNSUPPORTED_UNVERIFIED` sans la confondre avec une erreur historique CPC.

**Contrôle C1 du refus `PEN 16` après effacement :** après le `RUN` négatif, saisir `!CLS` puis `RUN` sans `NEW`. Le diagnostic hôte `INVALID_PEN` doit être identique, et `NEVER` ne doit apparaître ni à l'écran ni en `PRINT_BYTES`.

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


## HW4-PEN-A-C1-SYNC — synchronisation J1.18-B (30 octobre 2026)

**Base :** `main@d29424699dbca3ffe0c20b7d3e4caef9d1ee8dfc` après fusion #193, cinq CI `push` SUCCESS. `BEVideoEvent` porte désormais les champs additionnels `ink` et `colour` ; `BE_VIDEO_SET_INK=2` est un événement logique du cœur **sans rendu CYD autorisé par cette mission**. La passerelle `hw4_pen_preflight` renvoie explicitement `HW4_PEN_SET_INK_UNSUPPORTED` dès qu'elle rencontre ce type. **Toute la ligne/étape est rejetée avant le premier octet PRINT, y compris les opérations PEN/PRINT qui précèdent INK**. La politique n'implémente ni table RGB, ni recoloration, ni fonction BASIC nouvelle. Les messages UART `VIDEO_REJECT category=SET_INK_UNSUPPORTED printed=0 event_applied=0 print_applied=0` décrivent le refus du rendu, pas une erreur CPC historique.

**Test négatif hôte :** `test_j118b_ink_explicit_reject_no_partial_replay` appelle le véritable `bsr_step_events` avec `PEN 2:PRINT "A":INK 1,26:PRINT "B":PEN 3:PRINT "C"`, qui doit produire **3 événements** aux offsets 0/2/4 et les octets `A\nB\nC\n`. Le préflight ET le replay sont rejetés sans mutation de VRAM, de `CpcVideo`, de `CpcText` ou des octets PRINT ; une requête INK seule est également rejetée. Le test répète le refus après le vrai `hw4_pen_console_clear` et vérifie INK2/3=6/18. Les tests C1 existants préservent PEN, les trois événements au maximum, l'atomicité au quatrième et le comportement `RUN → !CLS → RUN`.

**Mémoire et ABI :** `BasicScratch` demeure une union C99 alignée entre 2048 octets temporaires et trois `BEVideoEvent` ; l'augmentation de taille du type vient du cœur J1.18-B, pas d'une nouvelle allocation. Le workflow `HW4-SCROLL-A0` compare CONSOLE/HW3/BASIC_PROBE entre `main@d29424699dbca3ffe0c20b7d3e4caef9d1ee8dfc` et le HEAD de #190, avec garde IRAM inchangée et seuil DRAM différentiel maximum **+256 octets**. Les chiffres ne sont pas présumés avant les exécutions réelles. Boot MODE1 bleu/jaune, orientation **10** et GPIO36 préservés ; archives scellées jamais retouchées.

### Protocole négatif PO supplémentaire — uniquement après autorisation Pilotage

Après contrôle du SHA complet de la PR autorisé explicitement par Pilotage, et avant puis après `!CLS` sans `NEW`, saisir :

```basic
NEW
10 PEN 2:PRINT "NEVER_BEFORE":INK 1,26:PRINT "NEVER_AFTER":PEN 3:PRINT "NEVER_END"
20 PRINT "NEXT_STEP_NEVER"
RUN
```

Attendus : `HW4-PEN-A VIDEO_REJECT category=SET_INK_UNSUPPORTED` avec `printed=0 event_applied=0 print_applied=0`, **aucune émission `HW4-C2 PRINT_BYTES` de la ligne rejetée**, aucun texte `NEVER_*` dessiné par l'exécution BASIC et aucun changement de PEN dû à cette ligne. L'écho de la source saisie reste distinct de la sortie PRINT et le diagnostic d'erreur hôte peut s'afficher. Faire `!CLS` suivi de `RUN` sans réécrire les lignes, avec les mêmes résultats ; ensuite rejouer le protocole PEN positif C1 déjà décrit pour vérifier l'alternance rouge/vert/jaune, le curseur et les encres conservées après clear. Retour requis : SHA flashé, log UART complet, photos, mesures `DEVICE_MEMORY`, PASS/FAIL par scénario. **Aucun flash n'est demandé sans la décision explicite du Pilotage.**

**SHA à utiliser :** la remise GitHub officielle du Développeur indiquera le HEAD exact de la PR #190 synchronisée ; ne jamais flasher l'ancien `d165c375...`.
