# HW4-PAL-BOOT-CPC-B1 — palette initiale MODE1 CPC en CONSOLE

**Mandat Pilotage :** [#250 / décision DÉVELOPPEUR 3](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/250#issuecomment-6580688753), actualisation [post-C1 CLS et hotfix CI](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/250#issuecomment-6581738585). [PR DRAFT de livraison #270](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/270), réservée à la revue et à la fusion par Pilotage. Base : `main@e6ddd3be0b003f718cbcd1e49cbda85ea6cf20e0`.

## Résultat voulu, provenance et limites

Le PO a observé directement sur son CPC 6128 le programme `10 PEN 3:PRINT "SCROLL GREEN"`, `20 PEN 1:PRINT "SCROLL XXXXX"`, `30 GOTO 10`. Malgré le mot « GREEN », la première ligne est **rouge** sur le CPC, la seconde est **jaune**, et le fond est **bleu**. Cette observation couleur est **rapportée par le PO**, pas une acquisition Caprice32 scellée, un oracle pixel-perfect ou un essai CYD.

En MODE1, les encres CPC de démarrage `INK[0..3]={1,24,20,6}` correspondent à bleu / jaune / cyan / rouge. `PEN` choisit l'indice logique, `INK` détermine la couleur de cet indice, le raster MODE1 conserve les indices (2 bits par pixel) et la projection RGB565 s'effectue à l'affichage. Le moteur vidéo portable `video/cpc_video.c` possède **déjà** ces valeurs ; son comportement n'est pas modifié.

L'ancien CONSOLE remplaçait `INK2=20` par **6 rouge** et `INK3=6` par **18 vert** (profil expérimental HW4-PEN-A) à deux endroits : `app_main()` et `hw4_pen_console_clear()`. Le correctif restaure `{1,24,20,6}` au boot et après la commande **hôte** `!CLS` ; il aligne le log UART `INK_CONTEXT` sur la palette effective. Il ne modifie pas les valeurs d'encre utilisateur pendant les pas ordinaires de RUN.

## Politique PEN15 et distinction des deux CLS

La passerelle `hw4_pen_pixel_index` reste inchangée : les PEN logiques 1, 2, 3 sont représentés directement par les indices MODE1 ; le PEN4 est borné au fond compatible ; la projection **expérimentale** `PEN15 -> pixel3` nécessite explicitement `INK3=18` (vert). Sous la nouvelle palette CPC `INK3=6`, **PEN15 est refusé avec `HW4_PEN_UNVERIFIED_VISUAL`**, sans dessin, plutôt que de fabriquer une équivalence CPC. Les anciens témoins PEN15 sous 18 restent exécutés par les tests, avec configuration **explicite** du profil historique.

| Chemin | Origine et effet sur la palette | Programme BASIC |
|---|---|---|
| Démarrage CONSOLE | `CpcVideo` MODE1 + `{1,24,20,6}`, PAPER 0, PEN 1, bordure bleue | Initialise la session |
| Commande hôte `!CLS` | Vrai `cpc_uart_console_clear()`, restauration CONSOLE de `INK2=20`, `INK3=6`, reinitialisation texte/curseur/Ready indépendante | **Conservé**, permet `RUN -> !CLS -> RUN` |
| Instruction BASIC `CLS` pendant RUN, jalon #258 | Événement typé `BE_VIDEO_CLEAR_TEXT` puis `cpc_text_clear`, efface sous PAPER courant, **préserve les INK[]**, PEN/PAPER et bordure | Transaction du pas existante |
| `CLS` direct au prompt, jalon J1.21-C2 futur | **Non implémenté par cette PR** ; core-only C1 #264 déjà fusionné | Coordination réservée au Pilotage |

Ne pas confondre **`!CLS`**, commande de service avec reset palette, et **`CLS`**, instruction BASIC, qui ne réinitialise **pas** les encres. `SET_INK` provenant de BASIC demeure explicitement **UNSUPPORTED** par la passerelle actuelle, sans simuler un rendu en cours de RUN. Aucun PEN 5..14, nouveau moteur BASIC, variante MODE0/2, LCD/DMA/VRAM supplémentaire ou optimisation scroll n'est ajouté.

## Couverture C99 et preuves

Le CTest existant `tests/test_hw4_pen_a.c` injecte des lignes numérotées dans un véritable `BasicSessionRuntime`, exécute `bsr_step_events`, préflight/replay sur `CpcText`, vérifie VRAM, pixels MODE1 et RGB565, curseur et FNV de sortie. L'ajout B1 vérifie la source de production des overrides CONSOLE, PEN1 jaune / PEN2 cyan / PEN3 rouge sur fond bleu, `RUN -> !CLS -> RUN` sans mutation du programme, échec fermé PEN15 sous `INK3=6`, distinction du `CLS` natif conservant la palette et rejeu du témoin historique PEN15 après configuration **explicite** d'INK3=18. `tests/test_hw4_c3_boot.c` contrôle la palette du vidéo générique lors du boot et après clear UART.

**RED** : [PR auxiliaire test-only #271](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/271) figée sur l'ancien CONSOLE, sans correctif de production, pour constater l'échec des nouvelles assertions. **GREEN** : résultats exacts de la PR #270 et memory delta à consigner après les CI ; le passage du CTest ne constitue jamais un test CYD matériel.

Les états C99, RGB565, CMake, taille et CI GitHub servent de preuves hôte/compilation. La fidélité visuelle des teintes est à vérifier sur écran réel par le PO. Ne pas déclarer un `ON_DEVICE_PO_REPORTED_PASS` depuis ces assertions.

## Protocole PO CYD — uniquement sur autorisation Pilotage et SHA final figé

**Porte A — identification, démarrage, ressources.** Sur ESP32-2432S028R sans PSRAM, avec ESP-IDF **v5.5.6**, le Pilotage communique le SHA HEAD complet de la PR #270 prêt pour essai. Vérifier ce SHA **avant** le flash (ne jamais utiliser un ancien build sans preuve) :

```sh
git fetch origin
git switch feat/hw4-pal-boot-cpc-mode1
git pull --ff-only origin feat/hw4-pal-boot-cpc-mode1
git rev-parse HEAD              # doit correspondre au HEAD autorisé
cd firmware/esp32_display_probe
idf.py -DLOCO_CYD_PROFILE=CONSOLE reconfigure build
idf.py -p /dev/ttyUSB0 flash monitor
```

Si la branche locale n'existe pas, `git switch --track origin/feat/hw4-pal-boot-cpc-mode1`. Éviter `fullclean`, `set-target`, l'écrasement d'une autre branche et le flash sans confirmation de l'identité du firmware. Capturer le UART dès reset à **115200 bauds** et la version dans `HW4-C2 START` ; exiger `LCD_INIT_PASS`, `VIDEO_READY`, `HW4-PEN-A INK_CONTEXT ... ink0=1_blue ink1=24_yellow ink2=20_cyan ink3=6_red ... pen15=unverified_requires_ink3_18`, `UART_READY`, `DEVICE_MEMORY ... interactive_ready`, `INPUT_READY`, `TOUCH-T1 BOOT_READY`, `ECHO_POLICY`. Écran de boot bleu CPC et texte jaune, Ready/éditeur disponibles. L'absence d'interactivité, un reset ou `main_task: Returned from app_main()` constitue un FAIL bloquant pour la Porte B.

**Porte B — rendu et conservation du programme.** À la console UART, saisir ligne par ligne :

```basic
10 PEN 1:PRINT "JAUNE"
20 PEN 2:PRINT "CYAN"
30 PEN 3:PRINT "ROUGE"
40 END
RUN
```

Contrôler à l'écran et sur photo les trois couleurs **jaune/cyan/rouge**, fond **bleu**, bon ordre, sans couleur verte imposée, aucun saut de curseur inattendu, Ready unique. Attendre `VIDEO_EVENT` pour PEN 1/2/3 et `PRINT_BYTES` pour chaque ligne ; différencier l'écho UART de l'affichage BASIC. Envoyer ensuite `!CLS` suivi immédiatement de `RUN`, **sans NEW ni ressaisie**. Le programme conservé produit les **mêmes trois couleurs** et Ready, sans régression scroll/écran/cursor ni retour vert expérimental. `LIST` doit encore montrer les lignes intactes.

**Porte C — témoin CPC du PO et rejets.** Après `NEW`, le PO peut saisir son témoin de scroll :

```basic
10 PEN 3:PRINT "SCROLL GREEN"
20 PEN 1:PRINT "SCROLL XXXXX"
30 GOTO 10
RUN
```

Attendre **rouge / jaune** en alternance, avec le scroll MODE1 habituel ; le texte « GREEN » n'est pas une instruction de couleur. Interrompre par la voie `BREAK` déjà prise en charge par le firmware, vérifier prompt/Ready, aucune corruption LCD/DMA et aucune dérive palette. Pour isoler PEN15 et ne pas laisser une boucle active, `NEW` puis `10 PEN 15:PRINT "NO"`, `20 END`, `RUN` : la projection doit être **refusée**, sans apparition de `NO`, avec diagnostic hôte/fail-stop et aucun PASS graphique inventé. Contrôler que la console reste utilisable, puis `!CLS`, `LIST`, et un test RUN positif. Les scénarios `INK` natifs restent des rejets, pas un changement dynamique de palette garanti.

**Retour PO exigé, sans présumer du résultat :** SHA complet flashé, version boot, fichier log UART complet (`INK_CONTEXT`, `VIDEO_EVENT`, `PRINT_BYTES`, éventuels `VIDEO_REJECT`, `DEVICE_MEMORY` heap libre / plus grand bloc / marge pile), deux photos TFT au minimum avant/après `!CLS` plus la photo du scroll, PASS/FAIL distinct pour Porte A/B/C, état LCD/DMA et comparaison **visuelle qualitative** avec le CPC de référence. Pas d'oracle RGB565 mesuré par photographie ni de preuve pixel-perfect supposée. **Toute fusion et tout déclenchement du test restent soumis à la décision du Pilotage ; ON_DEVICE_UNVERIFIED tant que preuves PO non reçues.**

## Propriété des chemins et réserves

#250 est propriétaire provisoire de `hw4_c2_console.c` et `hw4_pen_bridge.c` jusqu'à remise. Les travaux J1.21-C2 de CLS direct et HW4-SCROLL-A1-P ne doivent pas modifier simultanément ces mêmes chemins sans réconciliation décidée par Pilotage. Aucun changement sur `core/`, `video/cpc_video.[ch]`, CMake, workflows, firmware LCD, archives CPC, framebuffer, HOR, ESC, DMA ou implémentation native de `INK` n'est autorisé ici.

**Statut à remettre : `HOST_VERIFIED` / `TARGET_BUILD_VERIFIED` selon CI constatées, `ON_DEVICE_UNVERIFIED` jusqu'au retour matériel.**
