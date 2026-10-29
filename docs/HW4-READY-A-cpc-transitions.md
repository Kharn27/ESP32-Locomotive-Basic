# HW4-READY-A — Transitions de `Ready` (Locomotive BASIC 1.1)
 
Issue [#151](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/151). **Étape A0 en acquisition ; A1 NON AUTORISÉE tant que la matrice visuelle n'est pas attestée.**

## Traçabilité et non-confusion

Base GitHub relevée le 29/10/2026 : `main@399cdf412b019dcba2ae0c6c0b8c699ebf01812f`. Le point de départ proposé `28946334534f8f2887935731baf85e1effd0358a` est antérieur à la fusion de REAL5 [PR #158](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/158). Aucun changement du cœur REAL5, des archives historiques existantes ni du firmware pendant A0.

L'acquisition utilise les ROM CPC6128 réelles via le sous-module Caprice32 épinglé `8c778bf072a06fb7c23b9cccd179041db7f79a52`, la ROM `cpc6128.rom` SHA-256 `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562` et l'image GHCR digestée `sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c`. Deux processus indépendants par cas, clavier CPC simulé via `-a`, une capture PNG après les entrées. Les séquences exactes et empreintes figurent dans le manifeste sous `tests/fixtures/cpc6128/hw4_ready_a/` **une fois acquis** ; une capture n'est pas équivalente à un verdict tant que l'image n'est pas inspectée. L'imprimante CPC n'est jamais assimilée au flux écran.

## Matrice A0 — à remplir sur PNG originaux uniquement

| État final capturé | Saisie après boot CPC6128 | Ready supplémentaire | Reprise curseur | Classification |
| --- | --- | --- | --- | --- |
| Boot | aucune | à analyser (Ready initial attendu du boot) | à analyser | NON TESTÉ |
| Après ligne numérotée 10 | `10 PRINT 2` | à analyser | à analyser | NON TESTÉ |
| Après ligne numérotée 20 | `10 PRINT 2`, `20 END` | à analyser | à analyser | NON TESTÉ |
| Entrée vide | les deux lignes puis Enter vide | à analyser | à analyser | NON TESTÉ |
| LIST | les deux lignes puis `LIST` | à analyser | à analyser | NON TESTÉ |
| NEW | les deux lignes puis `NEW` | à analyser | à analyser | NON TESTÉ |
| RUN normal | les deux lignes puis `RUN` | à analyser | à analyser | NON TESTÉ |
| STOP | `10 PRINT 2`, `20 STOP`, `RUN` | à analyser | à analyser | NON TESTÉ |
| Diagnostic d'erreur | les deux lignes puis `GOTO 999` | à analyser | à analyser | NON TESTÉ |
| RUN puis NEW | les deux lignes puis `RUN`, `NEW` | à analyser | à analyser | NON TESTÉ |
| `!CLS` / `!DEMO` | diagnostics hôtes, inexistants sur CPC | pas d'oracle CPC | n/a | NON SUPPORTÉ |

**Hypothèse ROM séparée (non probante)** : `basic.asm` place la chaîne `Ready\n` à `&C0D7`, la sélection à `&C081`, et le chemin de saisie à `&C087` ; l'insertion d'une ligne numérotée rejoint `&C087`. Cela ne fixe ni les positions à l'écran, ni la sortie d'erreur, ni la présence effective d'une transition : seule la capture CPC servira d'arbitre.

## Barrière A0 → A1

Si les PNG n'ont pas été réellement produits, comparés et inspectés, **STOP A0** : aucune nouvelle politique C99, aucune revendication `CPC_ORACLE_VERIFIED`, aucun protocole flash pour un firmware non modifié. L'analyse de l'écran et les positions doivent être consignées avant tout correctif. `!CLS` et `!DEMO` auront une règle hôte explicite après validation A0.
