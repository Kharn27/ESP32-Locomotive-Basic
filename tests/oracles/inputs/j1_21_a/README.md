# J1.21-A — corpus source CLS (pré-acquisition)

Mandat : [#216](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/216). Ces 14 fichiers `.bas` sont des **entrées textuelles de test**, **pas des observations CPC**. Les cas D_* contiennent un programme `REM/END` préexistant pour tester sa conservation lors d'un `CLS` **direct** ; les cas N_* portent un `CLS` numéroté, exécuté par `RUN`.

La configuration de l'écran, la chronologie du screenshot `before` puis de la commande puis du screenshot `after` **dans un même processus**, les variantes WINDOW/PAPER/INK/MODE et la lecture des deux `LIST #8` sont pilotées par `tools/j1_21_a_cls_oracle.py`. Les tests `D_HASH0/D_HASH7/D_HASH8` vérifient des **hypothèses statiques ROM** : ils ne présument ni acceptation, ni comportement.

Les répétitions doivent être acquises avec la ROM CPC6128, Caprice32 et le GHCR épinglés. L'archive cible `tests/fixtures/cpc6128/j1_21_a_cls/` **n'est pas créée artificiellement**. Aucun `*.sna`, binaire `cap32`, ROM ni `cap32.cfg` ne doit être archivé. Les sceaux externes restent vides jusqu'à une acquisition GitHub originale téléchargée et contrôlée indépendamment.

Voir [le protocole complet](../../../docs/J1.21-A-cls-cpc-oracle.md).