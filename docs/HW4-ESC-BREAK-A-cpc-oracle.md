# HW4-ESC-BREAK-A — ESC / BREAK / CONT : état de l'oracle CPC et contrat UART C99

Mandat : [issue #231](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/231), **tranche A exclusivement**. Base GitHub `main@e76de5c57a39ff9c383129c6d1faaa7babab96e9`, branche `feat/hw4-esc-break-a-cpc-oracle`. **PR #226 ouverte et intacte**, non prise comme base. Ni raccord firmware/console UART, ni changement de `core/`, ordonnanceur, tokenizer, `STOP`, `CONT` ou `ON BREAK`.

## Sources et niveau de preuve

1. **Manuel, pas acquisition nouvelle.** Le manuel utilisateur CPC 6128, section GOTO ([transcription](https://www.notice-facile.com/notice/18520/amstrad%2Bcpc%2B6128-_f)) décrit ESC une fois = pause, toute autre touche = reprise, deux ESC = arrêt. Le [manuel BASIC CPC6128](https://www.cpcalive.com/docs/basic_doc_en.html) et [CPCWiki](https://www.cpcwiki.eu/index.php/BASIC) décrivent `CONT` après interruption et son invalidation après modification du programme ; les variantes `ON BREAK` sont des instructions distinctes. **Ces descriptions ne sont pas des captures exactes des scénarios ci-dessous.**
2. **Preuve CPC antérieure limitée à STOP.** [HW4-READY-A A0-v2](HW4-READY-A-cpc-transitions.md), cas `07_stop` : `10 PRINT 2 / 20 STOP / RUN` donne `Break in 20` et `Ready`, screenshot PNG original SHA-256 `ceca9c385a2574b37ff9730e1ad01677c29e8dbd90d60d96a0de3d9e969fc8e0`. Il s'agit de **STOP**, en aucun cas d'une capture ESC. Ancienne acquisition : Caprice32 `8c778bf072a06fb7c23b9cccd179041db7f79a52` (version rapportée 4.6.0), CPC6128 ROM BASIC 1.1 SHA-256 `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562`, image GHCR digest `sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c`. Ces empreintes **documentent le run précédent, pas un run réalisé pour cette issue**.
3. **Interprétation statique de la ROM**, pas oracle d'écran : `basic.asm` fourni, BASIC 1.1, `C472` lit une touche, `C476–C47F` traite le code firmware `&FC`/BREAK, `C492` arme la routine, `C4A1` attend la suite et compare les codes, `C4D0/C4D3` ON BREAK CONT/STOP, `C976` ON BREAK, `CC01/CC04` chaîne `Break`, `CC26` STOP, `CC66/CC83` sauvegarde contexte, `CC93` CONT (erreur `&11` sans adresse sauvegardée), `C0D7` `Ready`. Le `&FC` firmware **n'est ni l'octet UART 0x1B ni un token BASIC BREAK**. Cette lecture ne confirme pas les délais, la ligne courante, les espaces ou le curseur au BREAK effectif.

**Bilan d'oracle : `CPC_ESC_ORACLE_UNVERIFIED`.** Aucun nouveau processus Caprice32 ni CPC physique, aucune capture ESC originale, aucun manifeste de session ou empreinte de captures ESC dans cette PR. Aucun `MATCH_EXACT` ni `Break in <numéro>` supposé.

## Table des cas discriminants

Légende : **DOC** = comportement documenté historiquement, **A0** = précédent screenshot CPC de STOP, **À ACQUÉRIR** = aucune nouvelle preuve ESC indépendante. Le texte exact, les positions de curseur et les numéros de ligne ne doivent pas être inventés.

| Cas | Programme et manœuvre sur CPC6128 | État de la preuve |
|---|---|---|
| E00 | Prompt direct, ESC isolé, double ESC, `CONT` | À ACQUÉRIR : comportement direct, texte, Ready |
| E01 | `10 GOTO 10`; RUN, ESC isolé, sans touche ultérieure | DOC pause ; à acquérir absence de saut à Ready |
| E02 | E01, touche `x` ou espace après ESC | DOC reprise ; à acquérir état exact et consommation de touche |
| E03 | E01, second ESC pendant la pause | DOC BREAK ; à acquérir écran **exact** et numéro de ligne |
| E04 | E03, saisir `CONT` | DOC continuation ; à acquérir traces avant/après et variables |
| E05 | `10 PRINT "A":GOTO 20` / `20 PRINT "B":GOTO 10`, ESC aux lignes 10 et 20 | À ACQUÉRIR : attribution authentique des deux lignes et texte |
| E06 | E05, pause/reprise trois fois, puis double ESC | À ACQUÉRIR : répétitions et état final |
| E07 | `10 A%=A%+1:GOTO 10`, BREAK, `PRINT A%`, puis `CONT`, puis BREAK | À ACQUÉRIR : variables, programme intact, point de reprise |
| E08 | `10 PRINT 2` / `20 STOP`; RUN | A0 **STOP** observé : `Break in 20` puis Ready ; **pas ESC** |
| E09 | E08 suivi de `CONT`; ajouter ligne `30 END` pour distinguer la fin | DOC CONT après STOP ; acquisition manquante |
| E10 | Sans RUN/STOP préalable, `CONT` | ROM erreur `&11` Cannot CONTinue ; écran exact à acquérir |
| E11 | Après double ESC, modifier une ligne numérotée, `CONT` | DOC invalidation de CONT ; capture à acquérir |
| E12 | `10 PRINT 2` / `20 END`; RUN, puis `CONT` | À ACQUÉRIR : **END ≠ STOP ≠ BREAK** |
| E13 | LIST long, ESC / espace / ESC ESC | DOC interruption LIST distincte de RUN ; à acquérir |
| E14 | RUN avec `ON BREAK CONT/GOSUB/STOP` | DOC/ROM mots-clés distincts ; preuves à acquérir, implémentation hors A |

Il n'existe **aucune** autorisation documentaire d'afficher artificiellement `Break in 10`, `Break in 20` (pour ESC), `Break` ou `Ready` sans capture du cas. Le flux imprimante `#8` n'est pas une transcription vidéo.

## Procédure d'acquisition à exécuter pour lever la réserve

Utiliser un **CPC6128 réel** (préciser machine et ROM) ou Caprice32 à la révision épinglée ci-dessus et ROM SHA vérifiée. S'inspirer de `tests/oracles/run_caprice32.py` pour config, manifeste et PNG, **sans considérer que ses macros de saisie valident une touche ESC**. Vérifier d'abord que la méthode injecte une *véritable touche CPC ESC* plutôt qu'un octet terminal/une commande Caprice32. Pour chaque cas E00–E14 :

1. Session BASIC 1.1 neuve ; capturer version, config/réglages clavier, empreintes ROM et outil, listing du programme exact avant RUN.
2. Horodater séparément ESC #1, touche de reprise, ESC #2 et commandes directes ; enregistrer images écran avant, pendant la pause, à la reprise, au BREAK, après CONT. Répéter sur les deux lignes et les trois cycles prévus.
3. Archiver PNG originaux (non re-rendus), logs de frappe, transcriptions exactes, SHA-256, manifeste de provenance/version/ligne courante/variables, et éventuellement vidéo. Ne pas remplacer les fixtures permanentes existantes. Distinguer strictement écran et imprimante.
4. Noter espaces/casse de `Break in`, numéro de ligne effectivement visible, nombre/position des `Ready`, prompt et curseur. Comparer avec le cas négatif CONT sans contexte et après modification. Inscrire `UNVERIFIED` à toute case sans preuve.
5. Attribuer `CPC_ORACLE_VERIFIED` uniquement aux cas ayant captures identifiées et traçables. L'émulation seule n'est jamais une mesure CYD.

## Contrat d'entrée C99 proposé (expérience isolée)

Fichiers `integration/hw4_cpc_escape_contract.[ch]` et `tests/test_hw4_cpc_escape_contract.c`. Aucune allocation, pas de dépendance à ESP-IDF/BSR/FreeRTOS, aucun câblage à la console, aucun délai caché. Le décodeur a deux champs, produit au maximum deux événements par octet ; le routage RUN est **proposé** et non une pause réelle de l'exécuteur.

| Flux UART / événement logique | Sortie du décodeur | Réaction proposée pendant RUN |
|---|---|---|
| `1B` seul, après résolution explicite d'ambiguïté | `ESCAPE` | RUNNING → PAUSED, **pas BREAK** |
| `1B 1B` et résolution du second préfixe | deux `ESCAPE` | RUNNING → PAUSED → STOPPED, BREAK_REQUEST uniquement au 2e |
| Touche ordinaire (y compris espace/CR/LF/Ctrl+C) | `OTHER` | si PAUSED : RESUME ; Ctrl+C **pas assimilé à ESC** |
| `ESC [ ... final` ANSI CSI (flèches/HOME/Del), `ESC O final` SS3 | `ANSI` unique, **pas ESCAPE** | si PAUSED : RESUME provisoire, à confronter au CPC |
| CSI tronquée/invalide/>16 octets de paramètres, SS3 invalide | `REJECTED` (quarantaine du CSI surlong jusqu'au final) | pas d'effet RUN ni octet BASIC parasite |
| Événement `HOST_BREAK` fourni explicitement par le reconnaisseur supérieur | **ne peut pas sortir du décodeur brut** | aucun effet de contrôle CPC ; `!BREAK` hôte séparé |
| `ESCAPE` au prompt / après STOPPED | `ESCAPE` | aucune action RUN ; éditeur non branché |

**Point critique UART :** le premier octet `1B` est ambigu avec le début de `ESC[D`. `release_pending()` ne doit être appelé qu'à une **frontière d'ambiguïté de transport** validée ; jamais après chaque paquet `uart_read_bytes`. Aucune constante temporelle arbitraire ou « double ESC dans N ms » n'est retenue. `finish()` est réservé à une vraie fin/reset de flux ; une CSI fragmentée entre deux lectures reste en attente. CSI malformée ne devient jamais un BREAK par erreur. `!BREAK\r`, `!BREAK\n`, `!SHOT` et `!CLS` sont des protocoles hôtes à distinguer avant routage; leurs lettres sont de simples `OTHER` pour le décodeur isolé. Les choix de priorité entre éditeur et commande service appartiennent à la tranche B **non autorisée**.

## CONT : contexte indispensable avant un futur arrêt

À la frontière d'une instruction/statement réellement interrompu(e), préserver la **ligne BASIC courante vérifiée par l'exécuteur**, la position dans une ligne à `:`, l'adresse/identité et génération du programme, l'état de variables et pile FOR/GOSUB et l'adresse du prochain statement, la cause de terminaison (**STOP, END, BREAK, !BREAK, erreur**), et l'éventuel contexte nécessaire à CONT. Lire les données de `BasicExecutor` / `BSRResult` avant un `bsr_stop` destructeur ; ne pas reconstruire un numéro CPC à partir du quantum, de l'affichage, de `ERR/ERL` hôtes ni du nombre de PRINT. La ROM `CC66/CC83/CC93` éclaire cette distinction mais **la ligne affichée et le point de reprise restent à acquérir**. Le scheduler de la PR #226 réalise un arrêt de service hôte, pas un CONT CPC. Aucun token autonome BREAK n'est créé.

## Tests et barrière

Le banc `hw4_esc_break_a_transport_contract` comprend ESC pause/reprise répétée, ESC ESC, flèches/HOME/Suppr ANSI, CSI fragmentée, CSI surlong et corrompue, prompt/direct, commande hôte synthétique, pointeurs nuls et **différentiel négatif** contre le mutant « chaque octet ESC = BREAK ». GCC/Clang C99 `-Wall -Wextra -Wpedantic -Wconversion -Werror` OFF/ON ASan-UBSan. CMake/CTest enregistre uniquement ce test portable ; `core/` et le firmware ne le lient pas.

État A : **transport host seulement**. Oracle ESC E00–E14 **UNVERIFIED** ; build Xtensa du nouveau module **N/A (non lié)** ; CYD `CPC_BREAK_ON_DEVICE_UNVERIFIED`. Les CI historiques doivent être relues sur le HEAD de la PR et consignées dans la remise, sans transformer un succès permanent CPC en oracle ESC. Tranche B reste bloquée à la décision du Pilotage après A et revue/fusion de #226 ; les missions natives STOP/CONT/ON BREAK sont distinctes.


## Correctif C1 — quarantaine CSI et falsification du routage (31/10/2026)

Mandat complémentaire **HW4-ESC-BREAK-A-C1** : sur la **même PR #232**, à partir de
`c04a86b965fbcb843c11171d37ba68aaa459af92`, base PR toujours `main`.
Les sources firmware, `core/`, scheduler, `!BREAK`, BREAK CPC natif et PR #226 ne changent pas.

### Défaut réellement reproduit (ancienne source)

Le blob historique Git `integration/hw4_cpc_escape_contract.c` a pour empreinte
`d82fdc82e41e0766c9e376e114f0a07500337d6b` au HEAD antérieur.
Pour le flux `1B 5B 31 00 44` (`ESC [ 1 NUL D`) :
- l'ancien `HW4_ESC_CSI` émet `REJECTED` sur `NUL` **mais retourne à TEXT** ;
- `D` est alors émis `OTHER`, et dans `PAUSED` le routeur le transforme en `RESUME` parasite ;
- l'ancien `HW4_ESC_CSI_DISCARD` sortait également dès un contrôle (`NUL`, `ESC`, LF), avant le final ANSI.

**RED démontré localement**, en compilant le source original au SHA ci-dessus avec le nouveau fichier
`tests/test_hw4_cpc_escape_contract.c` (du présent HEAD) :
```sh
git show c04a86b965fbcb843c11171d37ba68aaa459af92:integration/hw4_cpc_escape_contract.c > /tmp/hw4-esc-old.c
gcc -std=c99 -Wall -Wextra -Wpedantic -Wconversion -Werror -Iintegration \
  /tmp/hw4-esc-old.c tests/test_hw4_cpc_escape_contract.c -o /tmp/hw4-esc-old
/tmp/hw4-esc-old
# exit=1 : FAIL tests/test_hw4_cpc_escape_contract.c:161: count == expected_count
#          FAIL tests/test_hw4_cpc_escape_contract.c:183: quarantined_byte(&d, &phase, (uint8_t)'D', 0u, HW4_ESC_KEY_NONE) == 0
```
L'ancien source original et le nouveau fichier de tests furent effectivement compilés et exécutés
sur hôte ; **ce RED est un test C99, non une nouvelle observation CPC**.

### Contrat corrigé

- Dans `CSI`, un octet hors paramètres/intermédiaires `0x20..0x3F` et hors final
  `0x40..0x7E` émet **une seule fois** `REJECTED` et entre en `CSI_DISCARD`.
  La même règle s'applique dès le **17e octet** de paramètres/intermédiaires.
- Dans `CSI_DISCARD`, **tous** les octets, notamment `NUL`, `ESC`, LF, 0x7F
  et les suivants, sont consommés silencieusement. **Seul** un octet final ANSI
  explicite `0x40..0x7E` termine la quarantaine, sans émission d'un `ANSI`,
  `OTHER` ou `ESCAPE`. Un final correct remet en `TEXT` et réinitialise
  `sequence_length`. Les séquences ANSI CSI valides restent inchangées.
- `release_pending()` ne décharge **jamais** une CSI, y compris rejetée, entre deux
  fragments UART. La vraie fin/reset du flux (`finish()`) remet systématiquement
  `TEXT` et le compteur à zéro. Elle émet `REJECTED` pour une CSI/SS3 encore
  incomplète et **NONE** si la CSI était déjà rejetée (pas de double signalement).
  **Aucun timeout arbitraire** ne déclenche de réarmement.
- En `PAUSED`, le routeur reçoit **tous** les événements émis par le décodeur
  pendant les tests (y compris `REJECTED`) : aucun `RESUME` ou `BREAK_REQUEST`
  n'est généré par une CSI rejetée. Après son final ou `finish()`, une *nouvelle*
  touche ordinaire peut légitimement provoquer `RESUME`.
- Un final ANSI est défini au niveau transport par la plage standard `0x40..0x7E` ;
  C1 ne prétend pas valider la signification CPC de ce final ni ajouter une
  réinterprétation des touches du firmware.

### Cas du test C1

| ID | Séquence | Contrôle exigé |
|---|---|---|
| P0 | ESC [ 1 NUL D, puis x | `REJECTED` unique, ni RESUME pendant la CSI ; x reprend *après* final |
| P1 | ESC [ 1 NUL ESC 1 D | ESC interne consommé, aucun BREAK ni RESUME |
| P2 | ESC [ + 17 paramètres + LF ESC 2 D | surlongue rejetée, contrôles quarantainés, final réarme |
| P3 | ESC [ DEL / frontière UART / 2 ESC ~ / ESC [ D | `release_pending` ne casse pas la quarantaine, ANSI suivant valide |
| P4 | CSI valide tronquée à `finish`; CSI rejetée tronquée à `finish` | rejet une fois, zéro double signalement, TEXT réarmé |

Preuve hôte C1 autonome locale : GCC 14.2 et Clang 17,
`-std=c99 -Wall -Wextra -Wpedantic -Wconversion -Werror`,
**4/4 OFF/ON ASan+UBSan PASS**. Le CTest racine réutilise le test existant
`hw4_esc_break_a_transport_contract` : pas de nouveau binaire ou dépendance
firmware. La CI du nouveau HEAD doit confirmer tous les workflows obligatoires.
Statuts inchangés : `CPC_ESC_ORACLE_UNVERIFIED` et `CPC_BREAK_ON_DEVICE_UNVERIFIED`.

