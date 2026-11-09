# CLK-04-A2 — Qualification expérimentale des entiers non négatifs vers CPC REAL5

Mission Pilotage [#347](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/347), dépendance [CLK-04 #312](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/312), [A1 #340](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/340), [PR #343](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/343) fusionnée. **GO A2 exclusivement expérimental ; aucun TIME natif ni codec de production autorisé.**

## Origine et chaîne de preuve

Base du mandat : main@0c9326bbea46fcd593c122633f0fbbbdb020b2d3. Avant les travaux, GitHub a indiqué une avance de main vers 0d5315be79262bb0355f8141a351937272f548fd, PR #346 (HW4-MEM-C6-B1 : trois fichiers isolés). La branche préexistante oracle/clk-04-a2-numeric-real5 a été avancée sans force-push vers cette base. Fetch/clone local impossibles en raison du DNS : LOCAL_FETCH_UNAVAILABLE ; seuls GitHub API, commits et GitHub Actions sont utilisés comme provenance.

Réutilisation en lecture / import de l'oracle A1 et de CLK-03, sans modification de leurs fichiers :
- Image GHCR immuable : ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c
- Caprice32 : 8c778bf072a06fb7c23b9cccd179041db7f79a52
- ROM CPC6128 : SHA256 31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562
- CPC6128 128 Kio, BASIC 1.1, printer activée, vitesse limitée, configuration vérifiée par outil ; boots à inspecter humainement.

**La source des octets CPC est exclusivement le snapshot temporaire SNA pris au STOP dans le même processus que le PRINT #8 suivant CONT.** Extraction de la table scalaire dans la RAM originale selon les pointeurs &AE68/&AE6A, entrées de 9 octets (lien opaque, nom, type CPC 04, REAL5 brut) et adresse recoupée avec PRINT #8,@variable!. Un autre processus fournit LIST/LIST #8 et program.bin originaux ; ces canaux ne sont pas des nombres fabriqués par Python. Le collecteur A2 n'importe pas le prototype pour l'acquisition. Les SNA complets et ROM sont supprimés/absents des archives ; STOP et CONT ont leurs propres PNG dans chaque processus RUN.

## Corpus avant acquisition, bornes de l'Issue #347

Fichier figé : tests/fixtures/cpc6128/clk_04_a2_numeric/corpus.json
**SHA-256 externe du corpus v3 = 9c36655e872f0a4d2af423f242c8185dfb7053fa418bf81e4ac608f1b5588d53**, publié avant acquisition sur l'Issue #347. Commits et sceaux v1/v2 antérieurs sont conservés dans la discussion, explicitement supplantés AVANT toute acquisition. Les sources BASIC complètes, expressions et ordre sont sérialisés dans le JSON, contrôlés octet pour octet au rejeu.

| Palier | Domaine candidat | Valeurs distinctes prévues | Contre-constructions |
|---|---|---:|---|
| D0 | 0..65536 | 22 | 0 |
| D1 | 65537..2147483647 | 11 | triplets autour de 2^23, 2^24, 2^30, et 2^31−1 |
| D2 | 2147483648..4294967295 | 4 | 2^31, 2^31+1, 2^32−2 et 2^32−1 |

Total 37 entiers uniques, 11 lots bornés, 14 constructions indépendantes. Les témoins entiers A1 0, 1, 5256, 50376 sont inclus. Le témoin A1 -1 et les fractions 0.5/1.25 ne sont pas des entrées uint32 ; ils restent des contrôles documentaires du format, non des valeurs transmises au prototype.

Les bornes D0/D1/D2 sont des **zones d'expérimentation** et non une assertion que TIME parcourt tout uint32 ou une affirmation sur les limites CPC. Tout résultat scientifique hors de ces observations demeure RANGE_UNVERIFIED.

## Hypothèse A1 : prototype entier uniquement

Candidature issue des témoins A1 (zéro 00 00 00 00 00 ; +1 00 00 00 00 81 ; -1 00 00 00 80 81 ; 0.5 00 00 00 00 80 ; 1.25 00 00 00 20 81 ; TIME 5256 et 50376).

Pour un entier positif n <= 2^32−1, k = bit_length(n)−1, et :
- E = 0x81+k (cinquième octet).
- M = (n << (31-k)) − 2^31, entier entre 0 et 2^31−1.
- Quatre octets de M en little-endian ; leur bit 31 vaut zéro (signe positif).
- Si n=0, les cinq octets sont nuls.

L'algorithme du fichier tools/clk_04_a2_numeric.py n'utilise que des entiers Python, sans float, round implicite ni calcul hôte de temps. Il refuse les types non int exacts (bool inclus), valeurs négatives et hors uint32. Le décodeur de test ne couvre que REAL5 positif entier exact sur la plage et refuse les fractionnaires, négatifs, exposants non couverts et octets mal formés. Ces rejets sont une politique locale, **pas** des erreurs observées de la ROM.

**Démonstration interne du prototype :** pour k entre 0 et 31, (n << (31−k)) est entier ; 2^31 <= n << (31−k) < 2^32 ; M est donc exactement codable avec 31 bits. Le décodage restitue ((2^31+M) << k) / 2^31 = n, sans reste. Ce raisonnement démontre seulement la correction arithmétique interne de l'encodeur/décodeur candidat sur uint32, PAS l'identité entre ce modèle et le comportement de parsing/conversion CPC pour toutes les valeurs. **Aucun palier n'est étiqueté MODEL_PROVEN pour la ROM sur cette seule preuve.**

## Identité de la source CPC, comparaison, risques

Chaque valeur existe dans une affectation REAL explicite de type A!=nombre_décimal. Pour 14 valeurs hautes, une autre variable de la même exécution reçoit l'expression arithmétique de puissances de deux (par exemple (2^31)+1). Après STOP, le processus imprime les adresses et valeurs de chaque variable, puis leur comparaison, les différences +1/−1 sur l'alternative ; le vérificateur recoupe ces résultats avec les **deux cellules REAL5 RAM distinctes**. Les valeurs PRINT sont conservées comme texte/Decimal et peuvent être arrondies/scientifiques ; elles ne servent jamais à *recréer* les 5 octets RAM.

- Si deux constructions CPC diffèrent, ou si la comparaison ou les sondes d'adjacence échouent : INPUT_VALUE_UNVERIFIED.
- Si les octets CPC diffèrent du candidat : CPC_SAMPLE_MISMATCH, STOP_ARCHITECTURAL.
- Si la comparaison réussit sur les observations : CPC_SAMPLE_MATCH / VERIFIED_CPC_SAMPLES, **jamais** contrat global implicite.
- Si l'identité de D2 est douteuse : STOP de toute prétention d'exactitude D2, même avec octets identiques.
- Aucun comportement TIME wrap, maximum numérique CPC, débordement ou arrondi universel n'est inféré.

L'acquisition enregistre sans modifier les valeurs ROM, et le rejeu indépendant importe le prototype seulement après validation de la provenance, du SHA de chaque fichier, des pointeurs, des noms, des types, des commandes, de la source, de la session et de l'imprimante.

## Reproduction et négatifs

Workflow isolé .github/workflows/clk-04-a2-numeric-oracle.yml : 3 jobs negative-tests, cpc-acquire, cpc-replay ; déclencheurs pull_request avec cinq chemins stricts et workflow_dispatch. Image/pins immuables, permissions contents/packages lecture seule, checkout HEAD contraint, deux sessions original/repeat, manifest.json inventorié, SHA-256 externe publié dans les logs et artefact de sceau distinct du ZIP RAW, replay à HEAD exact. Artefact de rapport JSON comparatif distinct du RAW pour empêcher toute contamination des octets d'origine. Archivage partiel if:always ; un échec reste FAIL et ne devient pas oracle. Rétention 90 jours.

Sur environnement disposant du sous-module et Caprice32 vérifiés :
    
    python3 -m unittest discover -s tests -p 'test_clk_04_a2_numeric.py' -v
    python3 tools/clk_04_a2_oracle.py --self-test
    python3 tools/clk_04_a2_oracle.py --acquire --caprice tests/oracles/caprice32 --output /nouvelle/sortie-a2 --head "$(git rev-parse HEAD)"
    sha256sum /nouvelle/sortie-a2/manifest.json
    python3 tools/clk_04_a2_oracle.py --verify /nouvelle/sortie-a2 --head "$(git rev-parse HEAD)" --seal SHA_EXTERNE_PUBLIE --report /sortie-hors-archive.json

CI-OPT3 : 40 workflows/5 familles, ajout A2 dans CPC_ACQUISITION seulement, filtre contractuel cinq chemins + falsifications (suppressions, renommage, workflow inconnu, élargissement, doublon, push/dispatch et mauvaise famille). Les tests historiques A1, C5, CLK03 et autres restent intacts.

## Registre d'observations et décision

| Preuve | Statut avant acquisition | Exigence pour qualification |
|---|---|---|
| Corpus SHA fixé et publié | SEALED_PRE_ACQUISITION | Conservation du SHA v3 |
| Deux boots CPC6128 BASIC 1.1 | UNVERIFIED | Inspection humaine PNG |
| 37 valeurs dans 2 sessions | UNVERIFIED | Valeur/adresse/5 octets originaux/PRINT |
| 14 doubles constructions par session | UNVERIFIED | Confirmation d'identité ou INPUT_VALUE_UNVERIFIED |
| Correspondance octet/octet candidat | UNVERIFIED | Rapport séparé au HEAD final |
| Manifestes, sceau et replay | UNVERIFIED | SHA256 externe, inventaire et HEAD |
| Exhaustivité D0/D1/D2 vis-à-vis de la ROM | RANGE_UNVERIFIED | Échantillons seuls insuffisants |
| C99, ARCH, OPT3, CPC, Xtensa | NON VÉRIFIÉ AU HEAD FINAL | Runs GitHub exacts |
| CYD physique | ON_DEVICE_UNVERIFIED | Hors mandat A2 |

Les résultats et les URL de runs/artefacts du HEAD de livraison devront être ajoutés après exécution réelle. Une contradiction authentique est conservée comme résultat scientifique avec STOP_ARCHITECTURAL, jamais corrigée en retouchant l'archive. La phase B de CLK-04 et tout REAL5 natif CORE restent bloqués. **Seul le Pilotage émet un verdict et fusionne la PR.**
