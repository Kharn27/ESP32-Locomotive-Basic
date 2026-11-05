# CLK-01 — Calibration CPC6128 ↔ CYD

Mandat Pilotage : issue #308, parent #307. Branche : test/clk-01-cpc-speed-baseline. Base GitHub vérifiée au lancement : c8cec8b1b4d0cab553cdc8b97b751aef3dd1370d. Aucun changement de production. Aucun jalon suivant autorisé.

## Périmètre de mesure et instrumentation existante

La ligne UART HW4-DISP-PROFILE RUN_DURATION run=N core_us=D scope=RUN_slices_including_repaint_excluding_final_prompt mesure le temps mur des tranches RUN, y compris repaint et yields FreeRTOS. Elle ne mesure PAS le CPU BASIC seul et exclut le prompt final. HW4-RUN-B RUN_START identifie le SHA et quantum=8 ; RUN_TERMINAL state=5 identifie une fin normale (4 est BREAK). Le groupe HW4-DISP-PROFILE SUMMARY/CLASS/TRACE est émis après prompt final. Les classes full25 et partial sont disjointes, scroll_associated les recouvre : NE PAS sommer les trois classes ; les métriques de repaint incluent potentiellement le prompt final, contrairement à RUN_DURATION. LCD_METRICS fournit les cumuls LCD ; DEVICE_MEMORY fournit heap/stack, DMA et lcd_error. Aucune instrumentation nouvelle ne remplace ces éléments.

La sonde CPC utilise TIME (300 ticks/seconde). Le programme CPC original est copié dans la RAM de l'outil d'acquisition avec une ligne 5 T=TIME et une ligne PRINT #8,TIME-T juste avant END ; aucun TIME sur CYD. La mesure CPC part après le déclenchement RUN et finit avant END, alors que RUN_DURATION CYD englobe les tranches de RUN et excludes le prompt. Les sondes ont un surcoût inconnu. Les temps mur du processus Caprice32 incluent l'initialisation de l'émulateur. Aucun ratio direct CPC ↔ CYD n'est donc publié sans alignement démontré des fenêtres : NOT_COMPARABLE. Ne pas étendre le constat visuel ROUGE/JAUNE ~3,4 à tous les profils.

## Corpus exact et contrôle

Cinq fichiers ASCII LF sous tests/fixtures/cpc6128/clk_01_speed/ ; manifest.json associe SHA256, charge, sorties attendues et nombre de répétitions. Programmes finis, pas de GOTO infini, pas de TIME/CPC-only dans la source CYD.

| Programme | Profil | Boucles | Sortie écran attendue |
|---|---|---:|---|
| 01_for.bas | FOR/NEXT sans PRINT dans la boucle | 1200 | CLK01 FOR |
| 02_integer.bas | INTEGER +3, -2 | 500 | 501 |
| 03_gosub.bas | GOSUB / RETURN | 300 | 300 |
| 04_print_fixed.bas | 3 PRINT depuis la position courante | 3 | CLK01 FIXED ×3 |
| 05_print_scroll.bas | 30 PRINT consécutifs (scroll garanti même sans LOCATE) | 30 | CLK01 SCROLL ×30 |

Résultat CPC et sortie natifs doivent être contrôlés séparément : le contenu affiché par la dalle n'est pas imprimé sur UART et ne peut pas être inventé à partir de RUN_DURATION. Le comportement réellement sans scroll du cas 04 devra être confirmé par les compteurs / l'écran ; à défaut ce qualificatif devient observation incertaine.

## Acquisition CPC indépendante et scellés

Sous-module Caprice32 déjà existant : commit 8c778bf072a06fb7c23b9cccd179041db7f79a52. ROM combinée CPC6128 (BASIC 1.1 attendu) : SHA256 31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562. Image GHCR : sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c. Paramètres isolés : model=2, ram_size=128, speed=4 MHz, limit_speed=1, imprimante active, audio OFF. Contrôle visuel BASIC 1.1 requis sur PNG BOOT. Aucun fichier ROM ni snapshot RAM contenant ROM dans les preuves.

L'outil tools/clk_01_cpc.py capture un boot puis réalise un garde de vitesse : deux paires indépendantes d'acquisitions PRINT #8,TIME, séparées par des séquences CAP32_DELAY courte/longue ; il calcule le quotient de différences ticks/différences de durées mur des deux processus. Chaque paire doit être dans l'intervalle 255..345 ticks/s, sinon EMULATOR_SPEED_UNVERIFIED. Ce garde approximatif reste sensible au jitter de l'hôte ; ce n'est pas une preuve de précision chronométrique absolue. Si le garde passe, cinq exécutions CPC indépendantes par programme, capture printer.dat, PNG, cap32.cfg, autocmd.json et caprice.log, manifest.json d'acquisition avec hash/tailles/temps. Une acquisition non exécutée ou partielle = CPC UNVERIFIED.

Commande de précontrôle (sans émulateur) :

~~~sh
python3 tools/clk_01_cpc.py --self-test
~~~

Exécution authentique programmée dans la CI isolée .github/workflows/clk-01-acquisition.yml, qui utilise le conteneur et le sous-module figés, puis conserve l'artefact clk-01-cpc-raw. L'artefact doit être téléchargé et relu avant classement CPC_ORACLE_VERIFIED ; aucune sortie simulée ne peut être appelée CPC. Ne pas modifier les fixtures ni workflows historiques ni ceux de J1.25-A/#309.

Le CLI hôte C99 réel est exercé via tools/clk_01_native.py --cli /chemin/loco_basic_cli, avec les mêmes fichiers et leurs sorties attendues. HOST_VERIFIED exige succès réel au HEAD exact. Aucun build hôte ne prouve le résultat CYD.

## Parseur UART

~~~sh
python3 -m unittest discover -s tests -p 'test_clk_01_uart.py' -v
python3 tools/clk_01_uart.py clk01-uart-raw.log --sha SHA_COMPLET \
    --csv clk01-resultats.csv --markdown clk01-resultats.md
~~~

Refus : mauvais SHA ou version boot sale, plusieurs boots, mauvais IDF v5.5.6, autre profil que SPI40 40000000 demandé, moins de trois RUN par scénario, nombre/ordre RUN différents, RUN interrompu ou en erreur, log incomplet, RUN_DURATION scope changé, mémoire/DMA/LCD en défaut, données SUMMARY/CLASS absentes. Une capture cohérente fournit min/médiane/max en µs, mais NOT_COMPARABLE tant que les deux bancs et leurs fenêtres ne sont pas indépendamment validés. Les logs synthétiques des tests négatifs ne sont pas des données réelles.

## Fiche PO : campagne physique après GO TEST PILOTAGE uniquement

Préconditions : GO Pilotage accordé, firmware sur le SHA complet de la PR annoncé dans la remise, ESP-IDF v5.5.6 et un seul port UART0 115200 ; console SPI40, CYD ESP32-2432S028R sans PSRAM. Le script automatisé détient seul le port (ne PAS lancer idf.py monitor simultanément). Procédure à copier depuis la racine du dépôt :

~~~sh
git fetch origin test/clk-01-cpc-speed-baseline
git switch --detach FETCH_HEAD
git rev-parse HEAD
git status --porcelain
idf.py --version
cd firmware/esp32_display_probe
idf.py -B build-clk01 -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=40000000 set-target esp32
idf.py -B build-clk01 -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=40000000 build
idf.py -p /dev/ttyUSB0 -B build-clk01 flash
cd ../..
python3 -m pip install pyserial
python3 tools/clk_01_po_capture.py --go-test-pilotage --port /dev/ttyUSB0 \
    --sha "$(git rev-parse HEAD)" --raw clk01-uart-raw.log
sha256sum clk01-uart-raw.log clk01-uart-raw.tx.jsonl
python3 tools/clk_01_uart.py clk01-uart-raw.log --sha "$(git rev-parse HEAD)" \
    --csv clk01-resultats.csv --markdown clk01-resultats.md
~~~

Vérifier que le SHA complet correspond à celui du Pilotage et le working tree est propre avant build. Au lancement du script, appuyer une fois sur RESET du CYD pour que le boot soit conservé dans la capture brute. Le script envoie automatiquement NEW + chaque ligne numérotée de chaque fichier, puis RUN trois fois avant de changer de programme : 15 RUN, une session, un seul fichier UART reçu sans annotation. Il sauve séparément un fichier TX horodaté. Ne pas lancer de vidéo, de monitor simultané ou de deuxième flash de profil. Sur échec, garder le RAW partiel, annoter FAIL et stopper.

Alternative manuelle uniquement si pyserial impossible : idf.py -p /dev/ttyUSB0 -B build-clk01 monitor ; saisir chaque bloc exact ci-dessous. Attendre le RUN_TERMINAL à chaque fois avant d'envoyer le RUN suivant. Ne pas saisir TIME sur CYD.

Scénario 01 :

~~~
NEW
10 A%=0
20 FOR I%=1 TO 1200
30 NEXT I%
40 PRINT "CLK01 FOR"
50 END
RUN
RUN
RUN
~~~

Scénario 02 :

~~~
NEW
10 A%=1
20 FOR I%=1 TO 500
30 A%=A%+3
40 A%=A%-2
50 NEXT I%
60 PRINT A%
70 END
RUN
RUN
RUN
~~~

Scénario 03 :

~~~
NEW
10 A%=0
20 FOR I%=1 TO 300
30 GOSUB 100
40 NEXT I%
50 PRINT A%
60 END
100 A%=A%+1
110 RETURN
RUN
RUN
RUN
~~~

Scénario 04 :

~~~
NEW
10 FOR I%=1 TO 3
20 PRINT "CLK01 FIXED"
30 NEXT I%
40 END
RUN
RUN
RUN
~~~

Scénario 05 :

~~~
NEW
10 FOR I%=1 TO 30
20 PRINT "CLK01 SCROLL"
30 NEXT I%
40 END
RUN
RUN
RUN
~~~

Réception PO : comparer les sorties à l'écran (3 lignes pour profil 04, 30 impressions pour profil 05), vérifier RUN_DURATION, RUN_TERMINAL state=5, trois CLASS + SUMMARY, LCD_METRICS, DEVICE_MEMORY, dma_fault=0, dma_timeouts=0, lcd_error=ESP_OK, aucune erreur BASIC ou reboot, heap/pile non dégradés. Renvoyer au Pilotage SHA réellement flashé, version IDF, commande build, fichier UART brut + son SHA, sidecar TX, CSV/Markdown, et PASS/FAIL physique par scénario. Aucun ON_DEVICE_PASS n'est décidé par le script ou le développeur.

## États et barrières

HOST_VERIFIED uniquement si tests hôte réels réussis. CPC_ORACLE_VERIFIED uniquement si ROM/émulateur authentifiés et artefacts consultés. TARGET_BUILD_VERIFIED uniquement si compilation Xtensa réellement exécutée au SHA exact. CYD reste ON_DEVICE_UNVERIFIED jusqu'aux preuves PO après GO. Aucun ratio universel déduit d'un seul témoin ; NOT_COMPARABLE est la réponse si fenêtres non alignées. PR Draft non fusionnée ; acceptation et fusion réservées au Pilotage ; CLK-02 et CLK-03 interdits sans mandat.
