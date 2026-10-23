# État du projet — ESP32 Locomotive BASIC

**Mis à jour :** 23 octobre 2026. **Branche de référence :** `main`. Les jalons marqués « en validation » ne sont pas acquis avant revue/merge du chef de projet.

## Suivi des jalons

| Jalon | Périmètre | État | Livrable |
|---|---|---|---|
| **J0.1** | Cartographie statique des sous-systèmes Locomotive BASIC 1.1 | **Accepté et intégré dans `main` via [PR #1](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/1)** | [J0.1](J0.1-architecture-locomotive-basic-1.1.md) |
| **J0.2** | Format binaire lignes numérotées, tokens, références, flux, erreurs et vecteurs | **En cours de validation** — PR dédiée, ne pas fusionner sans accord | [J0.2](J0.2-format-binaire-tokens.md) |
| **J0.3 (pressenti)** | Stockage/lecture du flux tokenisé en C portable sur Linux, tests de sérialisation et validation des enregistrements ; éventuellement premier noyau lexical selon la revue | **Non lancé** | Aucun |
| Étapes ultérieures | LIST/RUN/NEW, interpréteur minimum, console série, puis écran CYD | **Non lancées** | Aucun |

## Décisions techniques actées

1. Projet = **réimplémentation native en C**, pas d'émulation CPC ou Z80.
2. Le **cœur BASIC est indépendant du matériel** et validé sous Linux avant ESP32 ; architecture en composants tokenizer, programme, interpréteur, runtime, graphique, stockage et HAL.
3. **Mode de référence** : Locomotive BASIC 1.1 ; le désassemblage `basic.asm` est la source primaire. Les adaptations ESP32 doivent être explicitement séparées des comportements CPC.
4. **J0.2 propose** un flux tokenisé canonique : longueur `u16 LE`, numéro `u16 LE`, corps tokenisé, `00`, puis sentinelle `00 00`, sans sauvegarder l'octet de garde RAM. Décision définitivement acquise **après acceptation de J0.2**.
5. **J0.2 propose** de conserver les références de ligne sous forme `1E` dans le format persistant et de gérer les résolutions par offsets/caches invalidables, sans y placer des pointeurs C.
6. Pas d'optimisation de références `1D` historique tant que le comportement `record_begin-1` n'est pas validé sur CPC/émulateur de référence.
7. Dans les docs, séparer preuve directe du code Z80 **[C]**, déduction **[D]**, point à vérifier **[V]**, blocage **[B]**. Aucun vecteur déduit du désassemblage n'est automatiquement une « golden reference ».

## Risques / inconnues restantes

| Importance | Risque ou incertitude | Mesure prévue |
|---|---|---|
| **P0** | Emission lexicale exacte (espaces, variable I, constante 10, `GOTO`) encore non confrontée à un dump indépendant | Capture RAM ou fichiers tokenisés sur CPC/émulateur de référence, comparer aux vecteurs J0.2 |
| **P0** | Pointeurs temporaires `1D` et inversion en `1E` lors des modifications | Comparer dump avant/après RUN, remplacement et suppression |
| P1 | Numérotation 0 / 65535 / débordements et code d'erreur associé | Matrice de tests limites sur référence |
| P1 | Contextes complexes REM/DATA/ELSE/ON, suffixes de variables et noms collés | Tests différentiels de tokenisation et LIST |
| P1 | RAM ESP32 classique sans PSRAM, fragmentation, taille des structures BASIC | Budget RAM/SRAM mesuré à chaque version |
| P1 | Reproduction des réels CPC sur 5 octets et de l'arrondi | Jalon ultérieur de rétro-ingénierie numérique |
| P1 | Imprécisions/transcriptions dans le listing Z80 | Vérifier les octets source avant toute conclusion fragile |

## Barrières de livraison et plan pressenti

**Avant J0.3 :** revue explicite de la PR J0.2 ; vérification de la cohérence des tables/tokens, du format, des cinq investigations et des quatre vecteurs. L'absence de validation matérielle doit rester signalée, pas masquée par des tests fabriqués.

**J0.3 pressenti (proposition au chef de projet, non autorisation de codage) :** coder un seul module `basic_program` portable C99, capable de lire, valider, insérer, remplacer, supprimer et exporter une image de lignes tokenisées ; tests Linux de bornes, d'offsets, d'ordre et de sentinelle, y compris entrées malformées ; un jeu de vecteurs de test marqué « déduit » tant qu'il n'est pas validé indépendamment. Aucun pilote graphique, firmware ni moteur d'exécution. Le périmètre définitif sera fixé par le chef de projet après J0.2.

## Gouvernance GitHub

- **Développeur :** investigation et implémentation sur branche dédiée, commits et PR vers `main`, sans fusion autonome.
- **Pilotage :** revue technique des critères, demandes de corrections, acceptation/fusion selon autorisation et rédaction du prochain prompt.
- **Garde-fou :** ne pas enchaîner automatiquement sur le jalon suivant.
