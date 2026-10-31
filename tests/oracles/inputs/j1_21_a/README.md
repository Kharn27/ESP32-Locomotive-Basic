# J1.21-A — sources et corpus CPC réel CLS

Mandat : [#216](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/216). Ces 14 fichiers `.bas` sont des **entrées textuelles de test**, **pas des observations CPC**. Les cas D_* contiennent un programme `REM/END` préexistant pour tester sa conservation lors d'un `CLS` **direct** ; les cas N_* portent un `CLS` numéroté, exécuté par `RUN`.

La configuration de l'écran, la chronologie du screenshot `before` puis de la commande puis du screenshot `after` **dans un même processus**, les variantes WINDOW/PAPER/INK/MODE et la lecture des deux `LIST #8` sont pilotées par `tools/j1_21_a_cls_oracle.py`. Les tests `D_HASH0/D_HASH7/D_HASH8` vérifient des **hypothèses statiques ROM** : ils ne présument ni acceptation, ni comportement.

Les répétitions ont été acquises avec la ROM CPC6128, Caprice32 et le GHCR épinglés. L'archive **authentique** [tests/fixtures/cpc6128/j1_21_a_cls/](../../fixtures/cpc6128/j1_21_a_cls/) a été créée par le job [GHCR #41151360024](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41151360024), [artefact original #13023548397](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41151360024/artifacts/13023548397) ; elle contient 252 pièces de 28 sessions CPC et des empreintes SHA-256 externes épinglées dans `tools/j1_21_a_cls_oracle.py`. Aucun `*.sna`, binaire `cap32`, ROM ni `cap32.cfg` n'est archivé. Un commit du bot n'est **pas** une approbation Pilotage.

Voir [le protocole complet](../../../docs/J1.21-A-cls-cpc-oracle.md).