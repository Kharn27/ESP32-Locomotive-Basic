# J1-DIAG-RETRO-A3 — Audit ROM et bornes de provenance

Mandat : [#317](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/317). Base : `main@c8cec8b1b4d0cab553cdc8b97b751aef3dd1370d`.

## Étape 0 — écran original consulté avant tout correctif

Les **vrais PNG de session RUN** ci-dessous ont été chargés et relus visuellement depuis les archives GitHub du CPC6128 BASIC 1.1, distinctement des fichiers imprimante et des résultats hôtes. Chaque cas possède une capture RUN originale mais **pas de capture RUN « repeat » identifiée dans cette archive**. La chaîne d'acquisition est celle des manifestes historiques, préservés en lecture seule. Les SHA-256 ci-dessous sont les empreintes consignées dans les manifestes permanents. **ERL n'a pas été mesuré**.

| Source exécutée (ligne 20) | BE hôte | Opcode CPC | PNG original RUN / SHA-256 | Texte écran RUN et Ready | Sonde imprimante après RUN | Classement |
|---|---|---|---|---|---|---|
| `10 A%=-32768` ; `20 B%=A%-1` | `BE_INTEGER_OVERFLOW` | `F5` soustraction binaire | [NMIN_M1/run.png](../tests/fixtures/cpc6128/j1_integer_subtraction/NMIN_M1/run/run.png) / `a6f6aa83aed38eac76643392b416fa3203cd294d3c278006d8e5dccbe4fcaa2b` | `Overflow in 20`, puis `Ready` | `ERR=6`, `B%=0` après erreur | `CPC_ORACLE_VERIFIED` pour graphie/locus |
| `10 A%=32767` ; `20 B%=A%*2` | `BE_INTEGER_OVERFLOW` | `F6` multiplication | [PMAX_MUL2/run.png](../tests/fixtures/cpc6128/j1_integer_multiplication/PMAX_MUL2/run/run.png) / `f44d0904db00c36ca9304663cd7eea4d18320d44aef41c7a710aa8db6b1721ee` | `Overflow in 20`, puis `Ready` | `ERR=6`, `B%=0` après erreur | `CPC_ORACLE_VERIFIED` pour graphie/locus |
| `10 A%=255` ; `20 B%=A%*255` | `BE_INTEGER_OVERFLOW` | `F6` multiplication | [P255_MUL255/run.png](../tests/fixtures/cpc6128/j1_integer_multiplication/P255_MUL255/run/run.png) / `30e00354f0ccfefcf9664afb078e70a41a7f256ae228784d4eb083599a3ffda4` | `Overflow in 20`, puis `Ready` | `ERR=6`, `B%=0` après erreur | `CPC_ORACLE_VERIFIED` pour graphie/locus |
| `10 A%=1` ; `20 B%=A% MOD 0` | `BE_DIVISION_BY_ZERO` | `FB` MOD | [P1_M0/run.png](../tests/fixtures/cpc6128/j1_integer_mod/P1_M0/run/run.png) / `97a12ff791f25598e8dcc991a7727889d532f470ac86f1defd7208c0bbab7d9e` | `Division by zero in 20`, puis `Ready` | `ERR=11`, `B%=0` après erreur | `CPC_ORACLE_VERIFIED` pour graphie/locus |
| `10 A%=0` ; `20 B%=A% MOD 0` | `BE_DIVISION_BY_ZERO` | `FB` MOD | [P0_M0/run.png](../tests/fixtures/cpc6128/j1_integer_mod/P0_M0/run/run.png) / `ec51daebf5e3c4dc249f4c331655c862f90e6aaae942795b08011c9dffef8c35` | `Division by zero in 20`, puis `Ready` | `ERR=11`, `B%=0` après erreur | `CPC_ORACLE_VERIFIED` pour graphie/locus |

Sources de provenance : [soustraction](J1.3-A-integer-subtraction-oracle.md), [multiplication](J1.4-A-integer-multiplication-oracle.md), [MOD](J1.6-A-integer-mod-oracle.md), manifestes `tests/fixtures/cpc6128/j1_integer_{subtraction,multiplication,mod}/manifest.json`. ROM commune SHA-256 `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562`. Les sondes `PRINT #8,ERR` ne sont **pas** du texte extrait de l'écran ; `B%=0` après une erreur n'est ni un quotient ni une preuve d'atomicité.

## Étape 1 — contrat d'affichage borné

- **F5** : uniquement affectation INTEGER autonome `B%=A%-1` avec `A%=-32768`, source INTEGER explicite, sans suffixe ni second statement.
- **F6** : uniquement `B%=A%*2` avec `A%=32767`, ou `B%=A%*255` avec `A%=255`.
- **FB** : uniquement `B%=A% MOD 0` avec `A%=1` ou `A%=0`. Le diagnostic **F9** précédent reste indépendant.
- Un statut `BE_INTEGER_OVERFLOW` ou `BE_DIVISION_BY_ZERO` seul **ne déclenche jamais** ce mapping : le record BASIC réellement atteint, l'offset de statement, les références typées, le vrai contenu du store, l'opérateur et la cause de prévisualisation sont contrôlés en lecture seule. C'est une attribution de provenance limitée, pas un nouvel évaluateur.
- Les lignes 10/620/65535, les espaces, un `PRINT "BEFORE"` et `Ready` unique ne sont que des **variantes hôtes testées** ; l'archive CPC d'origine atteste la ligne 20. Aucune inférence d'un `ERL` CPC, aucune extension aux expressions logiques, FOR/NEXT, +, littéraux ou opérandes non attestés.
- L'ordre documentaire précédent qui laissait `FB` en `DIAG_CPC_UNVERIFIED` reflétait l'absence de relecture des images : ces **deux PNG** ont maintenant été relus ; aucune archive historique n'est réécrite.

## Preuves restantes pour remise

CTest host OFF/ON GCC/Clang + ASan/UBSan ; négatifs de provenance ; CI-ARCH/OPT3/CPC-PERMANENT ; 3 profils Xtensa 5.5.6 au **même HEAD final** ; comparatif Flash/IRAM/DRAM à la base ; réception CYD exclusivement par PO (`ON_DEVICE_UNVERIFIED` auparavant).
