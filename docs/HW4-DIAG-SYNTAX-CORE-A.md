# HW4-DIAG-SYNTAX-CORE-A — Classificateur lexical direct (Issue #292)

Base vérifiée à la prise en charge : `main@6727c4102d8cc1413386e01325c096eb3e0511a2`.
Branche : `feat/hw4-diag-syntax-core-classification`. Mission CORE uniquement.
Cette PR n'affiche **jamais** `Syntax error` ; le chantier IO #291 est distinct et attend la fusion CORE par Pilotage.

## Source positive : ROM du Locomotive BASIC 1.1

La ROM `basic.asm` fournie par le PO expose les pointeurs par initiale à **`e418`**
et les noms de tokens à **`e44c..e720`**. Le tableau constant
`cpc_rom_known_words` de `core/basic_session.c` reprend les graphies
alphabétiques, numériques et `$` de cette table, notamment les mots **absents**
du tokenizer C99 courant : `AUTO`, `MODE`, `GRAPHICS`, `CONT`,
`MASK`, `FRAME`, `INKEY$`, `TAGOFF`, `ON`, etc. La table n'est **pas**
une liste de fautes corrigées par exception : elle fait une recherche positive
exacte et insensible à la casse de la graphie ROM. Deux variantes du commentaire
ROM sont normalisées : `GO TO`/`GO SUB` correspondent aux formes compactes
`GOTO`/`GOSUB` ; `TAFOFF` à `e493` est une coquille du commentaire :
le token détaillé à `e493` est `TAGOFF` (son entrée à `e4a...`).

La table ROM contient aussi des opérateurs symboliques, mots composés et
variantes contextualisées (`ON BREAK`, `ON SQ`, `GO TO`, `?`).
**Leur grammaire n'est pas reproduite** : le classificateur ne tente ni de
tokeniser ces entrées, ni d'interpréter une instruction valide, ni de conclure
à une erreur CPC historique.

## Contrat C99 append-only

`BS_UNKNOWN_DIRECT=11` est ajouté **à la fin** de `BSStatus`, sans renuméroter
les statuts existants (dont `BS_UNSUPPORTED_DIRECT=7`,
`BS_LISTING_ERROR=10`). `bsr_submit` préserve `BSR_SESSION_ERROR`,
`BSResult` préserve ses quatre champs et les détails `BT_OK/BP_OK/BL_OK`
pour un refus lexical.

Ordre inchangé des contrôles : validité des pointeurs et recouvrements,
validation du programme, NUL/CR/LF, lignes numérotées, blanc, `:` hors
guillemets, `LIST` et `NEW` supportés. Après seulement :

- **`BS_UNKNOWN_DIRECT`** pour une saisie directe composée d'un seul mot
  d'au moins deux **lettres ASCII uniquement**, après suppression des espaces
  ASCII externes, absent du dictionnaire positif ROM. Exemples :
  `LISTT`, `RUNN`, `PRONT`, `WHILLE`, `CLSS`. Ce statut signifie
  « mot lexical non reconnu par la table ROM », **pas** « CPC ERR=2 prouvé ».
- **`BS_UNSUPPORTED_DIRECT`** conservé pour tout mot ROM reconnu mais non
  pris en charge directement (`GOTO 999`, `MODE 1`, `PAPER 2`,
  `AUTO`, `ON`, etc.) et pour **toutes les formes ambiguës** :
  présence d'arguments ou de chiffres, variables/affectations, suffixes
  `$`, `%`, `!`, `.`, tabulations, guillemets, préfixes de commande,
  `GO TO` et autres phrases à grammaire non portée. Les mots isolés à
  une lettre restent volontairement ambigus (variables BASIC).
- Les erreurs du tokenizer, du programme, les alias, les séparateurs
  multiples, les entrées NUL/CR/LF, l'overflow et les erreurs runtime
  restent sur leurs causes hôte précédentes.

**Important :** `BS_UNSUPPORTED_DIRECT` signifie encore « reconnu ou
non caractérisé », **jamais « connu avec certitude »**. L'API distingue
correctement le sous-ensemble lexical prouvé inconnu de tous les autres
refus. Une extension du sous-ensemble exigerait un nouveau mandat.

## Preuves de non-régression

Les CTests CORE existants `basic_session` et `basic_session_runtime`
utilisent la **vraie API de production** :
- minimum trois fautes indépendantes ; casse et espaces ;
- mots ROM reconnus, même si C99 ne les exécute pas ;
- entrées ambiguës, lignes numérotées, séparateur `:`, NUL/CR/LF ;
- refus en `BSR_IDLE` et en `BSR_RUNNING` (curseur et état sauvegardés) ;
- snapshots exacts du programme complet, de la sortie, de `written` et du
  runtime, y compris octets hors taille logique ; `RUN` reste exécutable.

Les quatre cellules CI C99 (GCC/Clang × sanitizers OFF/ON), ARCH, OPT3,
CPC-PERMANENT et Xtensa sont les sources d'autorité pour les tests finaux.

**Statut oracle** : `ROM_DISASSEMBLY_SUPPORTED` pour la liste de mots,
`CPC_ORACLE_NOT_ACQUIRED` pour le comportement direct de chaque faute.
**CYD : ON_DEVICE_UNVERIFIED** (aucun test physique demandé sur cette PR).

## Barrière d'intégration

Ne modifier ni `io/`, ni `integration/`, ni `video/`, ni `firmware/`,
ni les fixtures CPC scellées ni les workflows. Seul **Pilotage** peut accepter
et fusionner la PR CORE. **Après la fusion**, reprendre séparément #291
pour remplacer la condition littérale `LISTT` par `BS_UNKNOWN_DIRECT`
et documenter les limites de l'oracle CPC, sans toucher aux autres diagnostics.
