# HW4-ESC-ORACLE-R1 — acquisition CPC ESC indépendante

Mandat : [issue #231, décision Pilotage R1](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/231#issuecomment-6550609734).
Base : **main@4ed2b38657ff27797f0309944e3b21cd7d0a4284**, branche **oracle/hw4-esc-r1-cpc**.
Périmètre : seulement acquisition, documentation et outillage ROM-backed. Aucun firmware, core, scheduler,
tokenizer, UART/CYD, CONT natif, ancienne fixture ou PR #226 modifiés. Tranche B bloquée.

## Méthode et authenticité de l'injection (à confirmer par capture)

Caprice32 upstream **8c778bf072a06fb7c23b9cccd179041db7f79a52**, ROM combinée
CPC6128 32768 octets SHA-256 **31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562**,
image GHCR digest **7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c**.
Ces empreintes doivent être vérifiées à l'exécution, et ne prétendent pas à elles seules à une capture R1.

Lecture indépendante des sources Caprice32 à cette révision :
- src/keyboard.h : **CPC_ESC est l'enum 130** (0x82).
- src/keyboard.cpp : **CPC_ESC -> matrice matérielle 0x82**, correspondance SDL **SDLK_ESCAPE**.
  StringToEvents attend le préfixe **BEL (0x07) suivi d'un octet 130** pour une touche CPC.
  Ce 130 doit passer en **Latin-1 binaire**, pas en UTF-8 (0xC2 0x82).
- src/argparse.cpp : --autocmd convertit CAP32_DELAY/CAP32_SCRNSHOT/CAP32_EXIT en
  commandes **émulateur** (préfixe FF, 0x0C), distinctes des touches CPC.
- Contrôle négatif : un **octet brut 0x1B sans BEL** prend le chemin de traduction
  de caractère brut SDL, et non la voie explicite CPC_ESC. Cette voie brute n'est
  **pas** identique à un vrai SDL_KEYDOWN de la touche physique hôte Escape, qui
  peut se mapper à CPC_ESC. Vérifier le comportement sur les PNG avant tout verdict.

L'outillage tests/oracles/hw4_esc_r1_capture.py vérifie commit, ROM et tables de
mappage, enregistre les commandes et le flux exact en hexadécimal, la version,
la configuration, les logs et les **PNG natifs non retouchés** dans un dossier neuf
par session. Chaque prise de vue est séparée de deux CAP32_DELAY avant/après ;
le limiteur de vitesse est activé pour éviter les collisions de noms de PNG
Caprice32 horodatés **à la seconde**. Une seule option autocmd de macro empêche
l'insertion de touches ENTER entre deux ESC et leurs captures.

Workflow .github/workflows/hw4-esc-oracle-r1.yml : image Caprice32 épinglée,
acquisition et dépôt d'un artefact GitHub Actions
**hw4-esc-oracle-r1-candidate-ID**. Le script étiquette délibérément les captures
**CANDIDATE_NOT_VISUALLY_VERIFIED**. Aucune comparaison MATCH_EXACT automatique.

Commande reproductible dans l'environnement CI configuré :

    python3 tests/oracles/hw4_esc_r1_capture.py --caprice tests/oracles/caprice32 --output /tmp/r1-session-neuve

Ne jamais réutiliser le dossier de sortie.

## Matrice d'acquisition et réserves

| Cas | Programme / manipulation | Observables et critère |
|---|---|---|
| NEGATIVE | 10 PRINT "A":GOTO 10 ; octet brut ESC puis CPC_ESC x2 | Comparer la capture après l'octet brut à celles après la vraie séquence CPC |
| E01 | 10 GOTO 10 ; RUN ; ESC seul | Capture avant, après, après pause persistante ; boucle visuellement ambiguë |
| E02 | E01, touche x pour reprendre | Capture après ESC, après x, puis nouveau double ESC ; établir la reprise avec témoin E05 |
| E03 | E01, second ESC distinct | Texte et numéro de ligne **visuellement** relevés après BREAK, sans texte inventé |
| E04 | E03, CONT puis second BREAK | Démontrer contexte et continuation par des captures avant/après |
| E05 | 10 PRINT "A":GOTO 20 / 20 PRINT "B":GOTO 10 | Activité écran RUN/ESC/pause persistante/BREAK ; ne pas préjuger ligne 10/20 |
| E10 | Démarrage frais sans RUN/STOP ; CONT | Erreur exacte et prompt à photographier |
| E07, option | 10 A%=A%+1:GOTO 10 | Variables avant/après BREAK, PRINT A%, CONT, second BREAK ; candidat non validé |

E08 **STOP** reste un témoin historique distinct (pas ESC). E00, E06, E09,
E11–E14 ne sont pas acquis par R1. Ni imprimante #8 ni lecture ROM ne remplacent
une capture de l'écran, ni une compilation C99 une observation CPC.

## Repli prioritaire : protocole CPC 6128 physique pour le PO

Si Caprice32/injection ne peut pas être rendu visuellement discriminant,
prévoir une acquisition sans CYD, sur **CPC 6128 réel** :

1. Filmer sans coupure démarrage BASIC (modèle, version, ROM si connue), clavier
   réel **et écran ensemble** ; avant chaque cas, session neuve, programme
   intégral saisi, LIST filmé avant RUN. Conserver vidéo brute et photo écran
   entière par checkpoint. Noter exactement la date, les touches et délais.
2. E01 : sur 10 GOTO 10, frapper **une seule ESC matérielle** ; retirer le doigt,
   ne rien toucher pendant **au moins 5 s**. Noter toute apparition de Ready ou
   diagnostic ; la boucle sans sortie n'est pas un témoin de pause suffisant.
3. E02 : après ESC #1, frapper x ; observer reprise ou caractère parasite ;
   utiliser E05 comme témoin visuel d'activité.
4. E03 : nouvelle session E01, ESC #1 puis ESC #2, photographier texte complet,
   espaces, casse, **numéro effectivement visible**, Ready et position curseur ;
   ne pas deviner la ligne à partir du listing.
5. E04 : après BREAK documenté E03, saisir CONT ; filmer la continuation,
   puis interrompre par deux ESC distincts ; consigner comportement et texte.
6. E05 : saisir les deux lignes exactes, filmer A/B en RUN, après ESC #1,
   après pause prolongée et après ESC #2 ; répéter pour examiner l'attribution
   de ligne (10/20) sans la présumer.
7. E10 : session fraîche, sans exécution préalable, taper CONT au prompt ;
   enregistrer **le libellé d'erreur exact** sur la vraie image.
8. E07, facultatif : sur boucle A%, relever PRINT A% avant/après le BREAK et
   après CONT ; attention à l'overflow en boucle rapide.
9. Fournir les PNG/vidéos originaux, SHA-256 de chacun, photos du listing,
   modèle/ROM/version, ordre de frappe, transcription littérale issue des images,
   statut OBSERVÉ ou INCONCLUSIF par cas. Ne pas mettre d'images reconstituées.

## Classification stricte

**CPC_ORACLE_VERIFIED** uniquement sur captures indépendantes originales,
inspectées et traçables, avec distinction ESC CPC / hôte brut documentée.
Sinon **CPC_ESC_ORACLE_UNVERIFIED**, même lorsque CI/outillage ont réussi.
**CPC_BREAK_ON_DEVICE_UNVERIFIED** demeure : aucun test CYD n'est demandé en R1.
La décision d'acceptation/fusion et de déblocage éventuel de B appartient
exclusivement au Pilotage après revue séparée de #226.

## R1 — preuves réellement acquises et inspectées, 1er novembre 2026

**[Run de capture #41254339354](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41254339354) SUCCESS.**
Huit démarrages CPC6128 indépendants, **29 PNG originaux** désormais versionnés dans
[tests/fixtures/cpc6128/hw4_esc_r1](../tests/fixtures/cpc6128/hw4_esc_r1).
Manifeste original `manifest.json`, SHA-256
**5eff0daedd5d41d37f05848c02913de3bf8aa4b47009a43a6986095d54b3e850**.
SHA ROM **31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562**,
Caprice32 commit **8c778bf072a06fb7c23b9cccd179041db7f79a52**,
version annoncée **v4.6.0**. Archive poussée sur **branche PR** sous garde de SHA du
HEAD, et non sur main. Les empreintes des PNG, journaux, événements et configurations
sont vérifiées par `tests/oracles/hw4_esc_r1_verify.py --self-test` ;
la modification d'un octet dans une **copie temporaire** d'un PNG déclenche
**R1_MUTATED_PNG_REJECTED**.

### Contrôle négatif et authenticité de l'injection

Le log du contrôle montre **octet brut 0x1B** → `SDLK_UNKNOWN`,
`CPC_POUND`, scancode 304, alors que l'injection authentique
`BEL + CPC_ESC` produit deux événements `CPC_ESC`, scancode 130,
via `SDLK_ESCAPE`. Les images `running` et `raw_host_byte`
sont **identiques bit-à-bit** (SHA
**06c54e7ebea7db648a5b2fe3e9cd6044d8b8afeacc3b6f268308fd87c09190f8**).
La touche `CPC_ESC` change l'image au premier appui puis donne
**Break in 10 / Ready** au second. Le contrôle exclut l'assimilation de
l'**octet brut de cette injection** à l'ESC CPC ; il ne prétend pas qu'une
touche hôte physique SDL Escape ne puisse être mappée à CPC ESC.

### Résultats visuels des vrais PNG originaux

| Cas | Observation effective à l'écran | SHA-256 PNG original du checkpoint | Statut |
|---|---|---|---|
| E01 | `10 GOTO 10`, ESC #1 : curseur jaune, **ni Break ni Ready**, écran stable entre deux captures ; GOTO muet non probant seul pour pause CPU | E01/paused : **93a01fb87da6ed48c64e9cc285cbcdeafe3584a835dacae7b40f375641ff1f72** | OBSERVÉ |
| E02 | Après ESC #1, touche `x` : disparition du curseur de pause, puis nouvel ESC ESC → **Break in 10** | E02/after_x : **b3582443e340450e497d163d7c1f80503b2c89d4517664aab62d570e2f11fe87** | OBSERVÉ |
| E03 | Double ESC distinct sur `10 GOTO 10` → **Break in 10**, ligne suivante **Ready** | E03/after_second : **89d5c62b833cf1e8de675001e356a04658b1992193485a6c1f43eb5a8375f516** | OBSERVÉ |
| E04 | Après BREAK, `CONT` reprend la boucle ; nouveau double ESC → **Break in 10**, Ready | E04/break_after_CONT : **533a7bb141acce6e42a6ce8be513c1903e37f3e95624cee85cd5255c681247ef** | OBSERVÉ |
| E05 | RUN A/B sur lignes 10/20, ESC #1 fige visiblement la sortie ; deux PNG de pause **identiques**, ESC #2 → **Break in 20**, Ready | E05/break : **fd1638ac9581c80f601a4a20536c69c14839cc04a8b405248dac3876f119d1cf** | OBSERVÉ |
| E10 | Boot froid, aucun RUN/STOP ; `CONT` direct → libellé exact **Cannot CONTinue**, puis Ready | E10/without_context : **a02aeae936d4662744374020ef1ec335a268f91612313df892cd3f222a7b4828** | OBSERVÉ |
| E07 | Programme exact `10 A%=A%+1:GOTO 10`, BREAK → `PRINT A%` donne **2632** ; `CONT` et nouveau BREAK → `PRINT A%` donne **5271** | E07_candidate/variable_after_cont : **0d08ab8cf048d46e9275c4c9afe132df5a4d0a7c4229178ff51e17e6c2b42225** | OBSERVÉ |

E05/paused et E05/pause_persistent ont le **même SHA de fichier entier**
**3a6e90faebffe459c4d28870f1e46f345d2d6262c6e240d88c58d6a4fca028e4**,
à plusieurs secondes d'écart. C'est une preuve discriminante de suspension
de l'activité écran A/B. Les captures E01 ont le même contenu CPC hors
bandeau FPS (l'image totale peut différer). Pour chaque cas, chemins PNG originaux,
ordre de frappe et hexadécimal exact, configuration et journal SDL sont dans
le manifeste et les fichiers `events.json` correspondants.

**Portée du résultat :** attribution de la ligne 10 pour E03 et 20 pour
E05 **dans ces sessions seulement**, pas de numéro reconstitué ; `CONT`
prouvé sur E04 et E07, pas après modification de programme ni END/STOP.
Les cas E00, E06, E09, E11–E14 demeurent **UNVERIFIED**, E08 demeure
le précédent témoin **STOP distinct d'ESC**.

**Statuts proposés au Pilotage :**
`CPC_ESC_ORACLE_ROM_BACKED_VERIFIED` pour les faits observés E01–E05,
E07, E10 ; `CPC_BREAK_ON_DEVICE_UNVERIFIED`.
Pas d'essai CPC physique ni CYD et aucune modification firmware ou PR #226.
**Tranche B toujours bloquée, aucune auto-approbation/fusion.**
