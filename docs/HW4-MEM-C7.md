# HW4-MEM-C7 — autorité des gates incrémentales (#379)

## Politique
RENDER-A et SPI-C3 conservent leurs noms, leurs jobs host/horloge, et leurs véritables comparateurs historiques. Sur le HEAD initial, une mesure 67 331 → 67 551 octets donne `HISTORICAL_FAILURE=TRUE (+220 IRAM)`, **code retour historique 1** enregistré et préservé ; l'ancienne référence `21e95a7197413923bb5976067a0419bc729c20c1` (RENDER-A) et `989ec54989537a31c3a9be8074f1ce7c47708f17` (C3) ne sont ni effacées ni requalifiées. Diagnostic historique +88 code / +128 littéraux / +4 fill ; `ROOT_CAUSE_UNVERIFIED`.

L'autorité de réussite d'une nouvelle PR provient désormais des **quatre vrais builds Xtensa** main courant SPI40/SPI20 → HEAD de la PR SPI40/SPI20, sous le même ESP-IDF **v5.5.6** et l'image immuable `espressif/idf@sha256:bf72fe7a15c22849a9a94147301165a545fb8905d97c176cf748e3e4614cac84`. Plus un build historique pour prouver l'ancienne erreur. Les checkouts sont des SHA GitHub complets et vrais commits ; l'ascendance `merge-base==base` est obligatoire. Un `main` divergent ou déplacé pendant la construction est refusé, sans recours silencieux au merge-base ni à un test-merge GitHub.

La chaîne vérifie pour chaque ELF Xtensa les sections requises et `.iram0.text_end=1`, la sortie `size -A` recoupée au binaire construit, l'identité du BIN et sa version de source, les SHA256 des artefacts, l'ID du conteneur, les versions du compilateur/éditeur de liens, le `sdkconfig`, les horloges HAL compilées `40000000U/20000000U`, les caches (`CYD_LCD_SPI20_OPT_IN=OFF/ON`), et la parité SPI40/SPI20 (IRAM, DRAM, deux BIN non identiques). Les SHAs GitHub réels, base et HEAD, sont vérifiés au démarrage et après les cinq builds.

**Règle autoritative** : pour les deux variantes, `ΔIRAM≤0`, `ΔDRAM≤0`, `ΔBSS≤0` par rapport à leur base réelle, **sauf allocation nominative C7-C1 #388** décrite ci-dessous. Toute hausse sans autorisation, y compris **+1 octet** IRAM / DRAM / BSS → `INCREMENTAL_FAIL` et exit code non nul ; invalidité de provenance ou archive → `MEASUREMENT_INVALID` et exit code 2. Conserver les anciennes bornes C3 de DRAM 54 864 octets et coût B3 jusqu'à 696 octets (B3 DRAM 54 168) comme **témoins historiques**, jamais comme nouveaux plafonds de `main` après acceptation de B1. Le rapport affiche les deux verdicts **séparés** et les valeurs métriques/sha256 ; un workflow `SUCCESS` ne signifie pas que la dette historique a disparu.

## Reproductibilité
Une PR Draft `Refs #379` modifiant les chemins C7 déclenche les **deux** workflows existants. Le job hôte C7 lance `python3 -m unittest discover -s tests -p test_hw4_mem_c7.py -v`, avec cas synthétiques positifs et attaques. Le job Xtensa appelle `bash tools/ci/hw4_mem_c7_build.sh` avec `C7_MODE=render` ou `c3` et `C7_PR_NUMBER`. Les preuves persistantes (source SHA/tree, artefacts, empreintes, comparateurs historiques, rapport incrémental, logs et sortie) sont déposées dans `reports/hw4-mem-c7/`. Ces tests hôtes ne sont pas des mesures électriques CYD.

Pour une future réduction de mémoire, les codes historiques reflètent toujours les **mesures historiques réelles** : un comparateur ancien ne peut afficher PASS que s'il retourne réellement zéro. Les tests adversariaux invoquent également l'entrée `main()` du comparateur avec des fixtures **synthétiques** et vérifient directement les codes de sortie 0/1/2 pour chaque métrique et variante. Les jobs Xtensa sont les seules preuves de mesure firmware.

## C7-C1 — Issue #388, GO effectif après fusion #386 (16 novembre 2026)

**Arbitrage nominal du Pilotage :** une seule allocation pour ESC/BREAK B1 issue #385 / PR #387, `+40 B DRAM` **et** `+40 B BSS` au maximum, `+0 B IRAM`. Cette allocation n'est pas un droit de reprise pour d'autres PR. Elle ne change aucune preuve historique ni le budget du logiciel lui-même. C7-C1 est **CI-only** sur une branche indépendante de `main@5d88c71828d4138a589cc794f3d32284eb2ab738`, après fusion de #386. Aucun firmware ni gate C6/LAB/A0 modifié.

### Identité et scellement de l'exception

Le contrôle `hw4_mem_c7_v2.py` n'active `AUTHORIZED_ESC_B1_DRAM_BSS_40` que si **toutes** ces conditions sont satisfaites :

- PR **GitHub réelle, ouverte, même dépôt source/cible**, numéro **#387**, branche `feat/hw4-esc-break-b1-console`, issue #385 identifiée, `main` réel comme base. Les réponses GitHub sont récupérées **au début et à la fin** des builds, et les SHA, trees Git, merge-base et ascendance sont revérifiés avant la comparaison.
- Le commit B1 original `010e2d1d14941e4e09c097c8599b5cf4d0527f2f` doit être un véritable ancêtre du HEAD actualisé par merge non forcé ; son parent d'origine `3f84b119c404b95f72eab3b7dd6f3034bfc7c959` est également vérifié dans les objets Git.
- Le diff **complet** entre `main` et HEAD courant doit être **octet pour octet égal** au diff Git original de B1 et comporter exactement les **dix chemins autorisés** par #385. Un commit de fonctionnalité supplémentaire, même limité à un octet, un mauvais fork, une branche différente, un HEAD falsifié ou une synchronisation qui change ce patch font **STOP** (`MEASUREMENT_INVALID`). Aucune confiance tirée du seul numéro de PR inscrit dans une fixture.
- Pour les deux vrais ELF SPI40 et SPI20 : `ΔIRAM≤0`, `ΔDRAM≤40`, `ΔBSS≤40`, **différence DRAM = différence BSS**, `.dram0.data` **inchangée**, parité IRAM/DRAM/BSS/data entre variantes, BIN différents, digests et versions vérifiés. **+41** sur une seule mesure ou **+1 IRAM** donne `INCREMENTAL_FAIL`. Le budget est accordé uniquement à ce diff B1 ; un prochain main à 54 904 DRAM / 43 832 BSS permet un delta zéro, **pas** une nouvelle hausse de 1 B.

### Deux échecs historiques réels conservés

`tools/ci/hw4_mem_c7_build.sh` exécute toujours les comparateurs RENDER-A et C3 **inchangés** sur leurs vrais ELF historiques (cinq builds Xtensa indépendants). `hw4_mem_c7_legacy.py` accepte strictement **le RC historique 1** et vérifie la première cause contre les **sections ELF structurellement valides** : DRAM avant IRAM si elle dépasse, IRAM sinon, avec message et traceback cohérents. Un RC 0/2, un message non concordant ou une archive tronquée produit `MEASUREMENT_INVALID` : jamais de faux PASS. Après cette attestation, C7 calcule **séparément** l'incrémental actuel sur les deux SPI ; `HISTORICAL_FAILURE` conserve son vrai sens (IRAM `67331 → 67551` : **+220 B**, issue #380).

Les anciennes bornes `54864 DRAM` et `696 B depuis B3` restent imprimées en `HISTORICAL_FAILURE`, mais **ne bloquent pas un futur main ayant intégré B1** lorsque sa PR a `ΔIRAM/DRAM/BSS≤0`. Ce point est indispensable pour refuser à nouveau toutes les hausses non autorisées sans persister un plafond périmé.

### Falsifications et verdicts

`python3 -m unittest discover -s tests -p test_hw4_mem_c7.py -v` exerce les anciennes régressions, plus :

- positif B1 authentifié (diff fermé et commit ancestor), `+40 DRAM/BSS, 0 IRAM` sur les deux SPI, `.dram0.data` fixe, historique rouge et incrémental vert ;
- négatifs `+41 DRAM`, `+41 BSS`, `+1 IRAM`, un SPI seulement, allocation hors BSS, chemin/diff non autorisé, faux fork/ref/PR/HEAD/ancêtre, extension du plafond et autres PR `+1` ;
- ancien comparateur DRAM-first **ou** IRAM-first, RC inattendu, traceback altéré, SPI divergent, section ELF tronquée ;
- scénario après fusion B1 : `main=54904/43832`, future PR `Δ0` passe avec dette historique visible, **future PR `+1` échoue**.

Ces cas sont **synthétiques** : ils ne remplacent **jamais** les mesures des ELF compilés. Les workflows RENDER-A et C3 lancent leurs vraies campagnes ESP-IDF `5.5.6` au HEAD exact avec SHA et artefacts. Tout CI PASS doit être référencé au run et commit complets ; il ne valide **ni** la CYD réelle **ni** le flash. Le Pilotage fusionne seul C7-C1 ; ensuite #387 sera synchronisée **sans force push**, soumise à de **nouveaux** runs C7 et au GO FLASH distinct. **CYD N/A pour #388.**
