# Roadmap et barrières de phase — LOCO-CYD

**Décision Pilotage du 24 octobre 2026.** Ce document définit les critères de changement de phase. Les numéros de missions à venir sont **indicatifs** : aucun basculement automatique au seul motif d'avoir atteint un certain J0.x.

## Principes

- Objectif intangible : reproduction native en C du **Locomotive BASIC 1.1 du CPC 6128**, sans Z80, avec contrôle de fidélité progressivement démontré.
- Le coeur reste portable C99 et testable sous Linux. La cible CYD est ESP32-2432S028R (4 Mo Flash, sans PSRAM) ; contraintes RAM/Flash mesurées et suivies.
- La ROM CPC donne les règles à reconstruire. Un test basé sur un comportement déduit de la ROM n'est **pas** une capture indépendante CPC.
- Les jalons sont de petits incréments avec PR, revue du diff, CI standard + sanitizers et fusion par Pilotage après validation.

## J0 — Socle exécutable cohérent, sans couverture complète du langage

J0 est achevé lorsque **toutes** les conditions sont satisfaites :

1. **Tranche verticale en CLI Linux** : saisir les lignes, tokeniser, stocker, LIST, RUN, arrêt avec END ; exécuter une variable scalaire explicitement typée, une affectation et une expression arithmétique simple puis afficher la valeur. Programme témoin cible : `10 A%=2` / `20 B%=A%+3` / `30 PRINT B%` / `40 END`, avec sortie numérique 5 (format exact à comparer à l'oracle CPC).
2. **Architecture mémoire** : table des variables et évaluateur bornés, état fourni par l'appelant ; aucune allocation cachée, pointeurs CPC transcrits en pointeurs ESP32 ou mutation non contractuelle du flux tokenisé ; types INT16, REAL5 et STRING distincts. Aucun calcul en float/double hôte présenté comme le Maths Pack CPC.
3. **Robustesse** : tests Linux et ASan/UBSan de toutes les suites réussis sur le HEAD, cas d'échec/atomicité/corruption/budget couverts, absence de régression sur les comportements déjà acceptés.
4. **Premier banc différentiel indépendant** : au moins quelques cas de tokenisation/LIST/exécution du périmètre J0 documentés avec sortie d'un vrai CPC 6128 ou d'un émulateur CPC identifié ; conservation de la provenance et des conditions. Les écarts doivent être classés et, s'ils touchent la tranche verticale, traités avant passage à J1. En l'absence d'oracle, la barrière ne peut pas être déclarée pleinement satisfaite.
5. **Budget CYD** : estimation chiffrée RAM/Flash, limites d'entrées/programmes et marge de sécurité, plus un contrôle anticipé de faisabilité (compilation cible ou prototype mémoire quand la chaîne ESP32 est disponible). Pas besoin d'écran/tactile pleinement fonctionnels pour clore J0.

Le passage à J1 marque la **maturité du socle**, pas la fin du projet ni une promesse de compatibilité complète.

## Ordre de travail J0 restant (prévision, ajustable après chaque revue)

**Acquis au terme de J0.23 :** stockage scalaire borné, résolution des références explicites, affectations INTEGER constantes autonomes, puis `PRINT A%` et l'alias `?A%` avec lecture du magasin. Ces fonctionnalités sont validées en CI hôte, **pas** encore contre un oracle CPC indépendant.

- **J0.21 acquis via PR #24** : tokenisation et restitution LIST de `B%=A%+3`, sans exécution ; 18/18 suites Linux et ASan/UBSan, vecteurs ROM-dérivés.
- **J0.22 acquis via PR #26** : premier évaluateur INTEGER borné ; le programme témoin affiche `5`, atteint `END` et dispose de tests sur débordement/atomicité (19/19 Linux et ASan/UBSan). Les sémantiques CPC exactes restent à confronter à un oracle indépendant.
- **J0.23 acquis via PR #28** : audit C99 ABI Linux, quatre scénarios de réservation, relevés ELF et pile GCC ; risque CLI hôte `main()` 170 256 octets, non transposable directement à FreeRTOS. **Compilation et mesures matérielles CYD toujours non vérifiées**. Budget plausible, mais pas une preuve de faisabilité cible.
- **J0.24 en cours, clôture historique BLOQUÉE** : infrastructure acceptée via PR #30 (21/21 Linux et 21/21 ASan/UBSan), 9 cas sources préparés. Initialement aucune capture ; deux exécutions ROM-backed ont depuis été capturées en J0.24-C1, sans remplir la barrière des 8 cas et 2 images tokenisées.
- **J0.24-C1 acquis via PR #32** : Caprice32 v4.6.0 à SHA fixe, workflow autonome, deux exécutions réelles CPC BASIC 1.1 avec PNG, sonde imprimante et manifeste SHA-256 conservés dans l'artefact CI ; comparaison sémantique entière uniquement, ni token exact ni formatage écran certifié. Artefacts temporaires (14 jours).
- **J0.24-C2 acquis via PR #34** : deux captures PNG historiques, sondes imprimante et stdout C99 inchangés, manifeste SHA-256 archivés dans Git ; preuves recoupées avec les objets Git, 22/22 CTest en CI standard et ASan/UBSan. Aucune ROM copiée, aucune identité d'octets écran présumée.
- **J0.24-C3 accepté via PR #36**, squash [`8dd30eaf`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/8dd30eafd9356eb5ed0ef3a842b652d88f31682e) : images RAM tokenisées originales de `b_integer_scalar` et `c_integer_add` extraites indépendamment depuis les pointeurs CPC `&AE64`/`&AE66`, octets et SHA conservés sans snapshot complet ; deux `MATCH_EXACT` avec le C99. CI finale #40225053721 : 23/23 Linux et ASan/UBSan ; oracle #40225053658 vert. **J0.24 reste ouvert : 2 cas indépendants sur 8 requis.** Suite prévue J0.24-C4 : trois acquisitions supplémentaires diversifiées, sans dérive vers J0.25. La barrière ESP32/Xtensa/heap/pile reste distincte.
- **Avant clôture J0** : preuve de compilation ESP-IDF/Xtensa et de marge RAM/Flash/pile de la CYD reste nécessaire ; si l'outillage est indisponible, la phase ne peut pas être clôturée.
- **Clôture J0** : tests Linux et sanitizers, vérifications différentielles CPC indépendantes, diagnostics d'écarts, budget RAM/Flash et preuve anticipée de faisabilité CYD. Nombre exact de PR à fixer après revue des résultats.

## J1 — Développement de la compatibilité Locomotive BASIC 1.1

Élargissement systématique des instructions et fonctions : DEFINT/DEFREAL/DEFSTR selon sémantique historique, chaînes, contrôle de flux (IF, FOR/NEXT, GOSUB/RETURN), expressions complètes, données et erreurs CPC, nombres REAL5 et opérations Maths Pack, puis autres familles du langage. Pour chaque famille, matrice ROM → implémentation → tests CPC indépendants. Les fonctions graphiques dépendantes du matériel disposent d'une interface abstraite et pourront être implémentées conjointement avec J2.

## J2 — Firmware CYD et environnement

Portage et validation ESP32, écran ILI9341, modes/palette/graphismes CPC, tactile/entrée utilisateur, microSD et fichiers BASIC historiques. Des *spikes* matériels sont autorisés dès J0/J1 pour lever les risques RAM et faisabilité ; J2 n'est pas une interdiction de tester le matériel plus tôt.

## J3 — Consolidation/certification de fidélité

Campagne systématique de programmes historiques et tests différentiels, traitement des divergences, mesure des performances/mémoire et robustesse firmware. La fidélité est testée dès J0, et non repoussée à J3. Aucune revendication de « 100 % compatible » sans preuves couvrant réellement la surface concernée.

## Gouvernance des barrières

Pilotage déclare chaque passage de phase uniquement après examen des livrables réels, des PR fusionnées, de la CI, des écarts CPC et de la mémoire cible. Si une condition manque, la phase reste ouverte avec risque/documentation, même si les autres activités avancent.
