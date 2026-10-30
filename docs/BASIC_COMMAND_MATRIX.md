# Matrice de compatibilité Locomotive BASIC 1.1 — DOC-CAT-A

**Version de lecture : 31 octobre 2026. Base d'audit : [`main@9d4131ef4847b6e6bb324bc7c3a2baddc3851ac3`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/9d4131ef4847b6e6bb324bc7c3a2baddc3851ac3). Mandat : [#212](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/212).** Cette page est un **instantané du code à ce SHA**. La documentation historique et les rapports restent des archives à date, pas des propriétés automatiquement transférables au HEAD.

## Lire les statuts sans les fusionner

- `NOT_IMPLEMENTED` : pas de prise en charge de cette forme dans le composant cité, **pas** « syntaxe CPC invalide ». Pour le tokenizer actuel, la table des mots-clés est une liste blanche ; les autres mots ROM ne deviennent pas des tokens C99 par leur présence ici.
- `TOKEN_ONLY` : encodage démontré sans LIST ni exécution garantis. **Ne jamais** promouvoir seul ce statut vers LIST ou RUN ; aucun cas courant de la table n'est classé `TOKEN_ONLY` isolément faute de besoin de fausse promotion.
- `LIST_ONLY` : encodage **et** reconstruction LIST dans un corpus borné, sans RUN pour cette forme. Pour les directives directes `LIST/RUN/NEW`, ce statut vise leur **forme stockée**, et non leur exécution directe.
- `C99_NATIVE_BOUNDED` : traitement effectif par les chemins C99 précisés, **avec les seuls opérandes, données, contexts et actions mesurés** ; ne garantit pas toute la grammaire CPC.
- `CYD_CONNECTED` : passage effectivement câblé via BSR/firmware et éventuellement événement/rendu vidéo pour la forme indiquée. Ce n'est **pas** un flash réussi ni un oracle matériel.
- `CPC_ORACLE_VERIFIED` : source BASIC et RAM/printer/PNG CPC réellement acquises et scellées, pour le corpus lié ; ce n'est ni une exécution C99 ni une preuve CYD.
- `ON_DEVICE_PO_REPORTED_PASS` : retour de test sur **un SHA firmware identifié dans un rapport ou une PR** et sur un scénario ciblé. Cette qualification ne valide ni toutes les formes de l'entrée ni le HEAD documentaire présent.
- `UNVERIFIED` : absence de preuve pertinente pour **cette dimension et cette forme**. Ne signifie pas « invalide », ni même « impossible » sur CPC.
- `HOST_ONLY` : commande ou convention firmware/outil **hors langage BASIC**. `HOST_ONLY` et `CYD_CONNECTED` n'impliquent pas tokenisation CPC.

**Dimensions de la table :** « forme native » indique l'entrée reconnue et utilisée aujourd'hui, pas la liste complète de toutes ses formes CPC. La colonne Token/LIST + RUN est la situation du *moteur* C99 ; les colonnes CYD, oracle CPC et PO sont indépendantes. Quand la table indique `UNVERIFIED` pour l'oracle, la présence du nom dans la ROM reste une **preuve statique de vocabulaire**, **pas** une session d'observation. Les entrées sans implémentation portent volontairement `NOT_IMPLEMENTED` malgré la présence de fonctions de bas niveau ailleurs.

## Sources figées et méthode

- **ROM** : [désassemblage `basic.asm`](http://cpctech.cpc-live.com/docs/basic.asm), table de recherche lexicale **E418 / E44C–E720**, table des opérateurs **E736** et entrée `CLS` **C280**. Les noms du tableau ci-dessous sont les graphies lues dans la table (y compris `ON ERROR GOTO` et `ON BREAK`) ; cela **ne démontre ni la syntaxe complète, ni toutes les variantes directes**, ni les commandes RSX `|…`, périphériques/disquettes/extensions ou toutes les séquences d'échappement. **Inventaire global CPC : INCOMPLET / UNVERIFIED**, inventaire des mots-clés ROM montrés : vérifié statiquement, sans garantie de toutes leurs constructions.
- **Native** : [`core/basic_tokenizer.c`](../core/basic_tokenizer.c) (`keywords[]`, grammaires locales), [`core/basic_listing.c`](../core/basic_listing.c) (`decode`), [`core/basic_executor.c`](../core/basic_executor.c) (`execute_line`, `pen_argument`, `ink_arguments`), [`core/basic_session.c`](../core/basic_session.c) (direct `LIST/NEW` seulement), [`core/basic_session_runtime.c`](../core/basic_session_runtime.c) (`RUN` direct / `bsr_step_events`). Aucun parseur générique pour tous les mots ROM.
- **Cible** : [`integration/hw4_pen_bridge.c`](../integration/hw4_pen_bridge.c), [`firmware/esp32_display_probe/main/hw4_c2_console.c`](../firmware/esp32_display_probe/main/hw4_c2_console.c), [`io/cpc_uart_console.c`](../io/cpc_uart_console.c) et [`video/cpc_video.c`](../video/cpc_video.c). Une API graphique peut exister **sans** prise en charge d'une commande BASIC correspondante.
- **Tests** : [`tests/test_basic_session.c`](../tests/test_basic_session.c), [`tests/test_basic_session_runtime.c`](../tests/test_basic_session_runtime.c), [`tests/test_basic_executor.c`](../tests/test_basic_executor.c), [`tests/test_basic_pen_events.c`](../tests/test_basic_pen_events.c), [`tests/test_basic_ink_events.c`](../tests/test_basic_ink_events.c), [`tests/test_basic_abs_token_list.c`](../tests/test_basic_abs_token_list.c), [`tests/test_hw4_pen_a.c`](../tests/test_hw4_pen_a.c) et [CI du dépôt](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions). Les tests C99 ne sont pas un oracle CPC.

## Repères de preuve / statut de mission

| Repère | Source primaire | Couverture pertinente et limites |
|---|---|---|
| [HW4] | [HW4-C2 UART](HW4-C2-uart-interactive-console.md), [HW4-PEN-A](HW4-PEN-A-native-pen-mode1.md), [#91](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/91) | `RUN/LIST/NEW` et `PRINT` de programmes ciblés ont des rapports PO sur leurs SHA, sans généralisation ; quelques cas PEN/HW4 restent distincts. |
| [PEN] | [J1.17-A](J1.17-A-pen-cpc-oracle.md), [J1.17-C-A](J1.17-C-A-pen-5-14-cpc-oracle.md), [issue B #210](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/210) | CPC accepte `PEN 5..14` (`ERR=0/ERL=0`, deux palettes, 52 acquisitions) ; au **SHA audité**, C99 renvoie encore `BE_UNSUPPORTED` ; jalon B indépendant non fusionné à cet instant. `PEN 8/12` invisibles dans leurs contextes RGB, sans indice général prouvé. |
| [INK] | [J1.18-A](J1.18-A-ink-cpc-oracle.md), [J1.18-B](J1.18-B-ink-native.md) | 13 formes scellées ; certains couples C99 émettent `SET_INK` ; le pont CYD rejette tout événement INK (`HW4_PEN_SET_INK_UNSUPPORTED`). La forme clignotante `INK 1,26,6` est LIST-only / unsupported RUN. |
| [ABS] | [J1.20-A](J1.20-A-abs-integer-cpc-oracle.md), [J1.20-B1](J1.20-B1-abs-token-list-native.md) | 16 sources exactes `FF 00`, 2 archives chaque ; `TOKEN/LIST` natifs sur cas bornés **sans calcul `ABS` en RUN**, y compris témoins d'erreurs à l'exécution CPC. |
| [F10] / [F13] / [F14] | [IF/THEN](J1.10-B-if-then-integer-native.md), [comparaisons](J1.13-B-integer-relational-if-native.md), [ELSE](J1.14-B-if-inline-else-native.md) | IF INTEGER, opérateurs relationnels et ELSE inline dans les corpus jalonnés ; pas de langage booléen général. |
| [F11] / [F12] | [GOSUB/RETURN](J1.11-B-gosub-return-native.md), [FOR/NEXT](J1.12-B2-for-next-integer-native.md) | Formes de contrôle de flux INTEGER et piles bornées, oracles indépendants dans les rapports A correspondants. |
| [MATH] / [VAR] / [P15] / [FL] / [EX] / [TOK] | [Rapports J1](PROJECT_STATUS.md), [J1.9](J1.9-B-integer-binary-family-native.md), [J1.15](J1.15-B-string-scalar-native.md), [J0.7](J0.7-basic-executor.md), [J0.4](J0.4-basic-tokenizer.md) | Opérateurs entiers bornés, affectation INTEGER et chaîne scalaire, PRINT de valeurs et de chaînes limitées ; pas d'évaluateur BASIC universel. [FL] vise le saut GOTO, [EX] le chemin END, [TOK] la grammaire native. |
| [VIDEO] / [CLS] | [`cpc_video.c`](../video/cpc_video.c), [`cpc_uart_console.c`](../io/cpc_uart_console.c), [source ROM CLS C280](http://cpctech.cpc-live.com/docs/basic.asm) | API MODE1 / encres / clear de console **sans** commandes BASIC `MODE/PAPER/CLS`. Oracle CLS à constituer séparément. |

## Vue rapide pour utiliser le projet

| Famille | Ce qui fonctionne aujourd'hui, dans ses bornes | Ce qui manque |
|---|---|---|
| Éditeur/stockage | Lignes numérotées, remplacement/suppression, `LIST`, `NEW` direct, `RUN` séquencé, `END` | Editeur CPC complet, commandes directes générales, `AUTO/RENUM/EDIT/DELETE`, gestion fichiers |
| Sortie et variables | `PRINT` de chaînes/entiers/scalaires limités, INTEGER `%`, STRING `$` et trois témoins REAL5 ; colon et commentaires bornés | Fonctions, tableaux, expression générales, imprimerie CPC `#` réelle |
| Flux | `GOTO/GOSUB/RETURN`, `IF/THEN/ELSE` INTEGER, `FOR/TO/STEP/NEXT` INTEGER bornés | Conditions/expressions générales, `WHILE/WEND`, `ON`, `STOP/CONT` |
| Opérateurs/fonctions | Comparaisons INTEGER et `+/-/*/\`/`MOD` bornés ; `ABS` uniquement token/LIST | Réel mathématique général, opérateurs logiques/bitwise, `ABS` exécutable |
| CPC affichage | `PEN 0..4,15` C99, pont MODE1 borné ; `INK` événement natif C99 borné | `PEN 5..14` C99 (issue #210), `INK` raccord CYD, `CLS/MODE/PAPER`, autres dessins |
| Périphériques | UART/écran hôte pour les tests indiqués | BASIC `SOUND`, fichiers, imprimante/flux CPC, mémoire/ports, RSX, graphisme complet |

## Catalogue ROM : une entrée par mot-clé

Le **mot-clé ROM n'est pas automatiquement un mot-clé reconnu par le tokenizer natif**. `NOT_IMPLEMENTED` correspond au code *à cette base* et `UNVERIFIED` dans les colonnes CPC/PO ne nie pas la fonction sur Amstrad. Les instructions `PRINT`, `PEN`, `INK`, etc. ne sont dites exécutables que pour les formes bornées signalées. Pour toute ligne marquée « non planifié », aucun jalon n'est auto-décrété : le Pilotage doit d'abord mandater l'oracle puis, le cas échéant, le natif.

### Programme / flux / édition

| Entrée ROM 1.1 | Forme **native** | Token/LIST + RUN C99 | Pont CYD BASIC | Oracle CPC indépendant | Essai physique PO | Écart et suite |
|---|---|---|---|---|---|---|
| `AUTO` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `AFTER` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `CAT` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `CHAIN` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `CLEAR` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `CLOSEIN` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `CLOSEOUT` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `CONT` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `DATA` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `DELETE` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `EDIT` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `END` | numérotée | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | UNVERIFIED | UNVERIFIED | END en RUN borné, pas STOP/CONT; [EX] |
| `ERASE` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `ERROR` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `EVERY` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `FOR` | numérotée | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | CPC_ORACLE_VERIFIED | UNVERIFIED | INTEGER avec bornes et STEP, pile et overflow host limités; [F12] |
| `GOSUB` | numérotée | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | CPC_ORACLE_VERIFIED | UNVERIFIED | cible constante, pile bornée, RETURN associé; [F11] |
| `GOTO` | numérotée | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | CPC_ORACLE_VERIFIED | UNVERIFIED | cible constante L1..65535, formes GOTO uniquement; [FL] |
| `IF` | numérotée | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | CPC_ORACLE_VERIFIED | UNVERIFIED | INTEGER condition bornée THEN/ELSE; pas IF général; [F10][F13][F14] |
| `LINE` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `LET` | numérotée | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | CPC_ORACLE_VERIFIED | UNVERIFIED | INTEGER `%` explicite et STRING `# Matrice de compatibilité Locomotive BASIC 1.1 — DOC-CAT-A

**Version de lecture : 31 octobre 2026. Base d'audit : [`main@9d4131ef4847b6e6bb324bc7c3a2baddc3851ac3`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/9d4131ef4847b6e6bb324bc7c3a2baddc3851ac3). Mandat : [#212](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/212).** Cette page est un **instantané du code à ce SHA**. La documentation historique et les rapports restent des archives à date, pas des propriétés automatiquement transférables au HEAD.

## Lire les statuts sans les fusionner

- `NOT_IMPLEMENTED` : pas de prise en charge de cette forme dans le composant cité, **pas** « syntaxe CPC invalide ». Pour le tokenizer actuel, la table des mots-clés est une liste blanche ; les autres mots ROM ne deviennent pas des tokens C99 par leur présence ici.
- `TOKEN_ONLY` : encodage démontré sans LIST ni exécution garantis. **Ne jamais** promouvoir seul ce statut vers LIST ou RUN ; aucun cas courant de la table n'est classé `TOKEN_ONLY` isolément faute de besoin de fausse promotion.
- `LIST_ONLY` : encodage **et** reconstruction LIST dans un corpus borné, sans RUN pour cette forme. Pour les directives directes `LIST/RUN/NEW`, ce statut vise leur **forme stockée**, et non leur exécution directe.
- `C99_NATIVE_BOUNDED` : traitement effectif par les chemins C99 précisés, **avec les seuls opérandes, données, contexts et actions mesurés** ; ne garantit pas toute la grammaire CPC.
- `CYD_CONNECTED` : passage effectivement câblé via BSR/firmware et éventuellement événement/rendu vidéo pour la forme indiquée. Ce n'est **pas** un flash réussi ni un oracle matériel.
- `CPC_ORACLE_VERIFIED` : source BASIC et RAM/printer/PNG CPC réellement acquises et scellées, pour le corpus lié ; ce n'est ni une exécution C99 ni une preuve CYD.
- `ON_DEVICE_PO_REPORTED_PASS` : retour de test sur **un SHA firmware identifié dans un rapport ou une PR** et sur un scénario ciblé. Cette qualification ne valide ni toutes les formes de l'entrée ni le HEAD documentaire présent.
- `UNVERIFIED` : absence de preuve pertinente pour **cette dimension et cette forme**. Ne signifie pas « invalide », ni même « impossible » sur CPC.
- `HOST_ONLY` : commande ou convention firmware/outil **hors langage BASIC**. `HOST_ONLY` et `CYD_CONNECTED` n'impliquent pas tokenisation CPC.

**Dimensions de la table :** « forme native » indique l'entrée reconnue et utilisée aujourd'hui, pas la liste complète de toutes ses formes CPC. La colonne Token/LIST + RUN est la situation du *moteur* C99 ; les colonnes CYD, oracle CPC et PO sont indépendantes. Quand la table indique `UNVERIFIED` pour l'oracle, la présence du nom dans la ROM reste une **preuve statique de vocabulaire**, **pas** une session d'observation. Les entrées sans implémentation portent volontairement `NOT_IMPLEMENTED` malgré la présence de fonctions de bas niveau ailleurs.

## Sources figées et méthode

- **ROM** : [désassemblage `basic.asm`](http://cpctech.cpc-live.com/docs/basic.asm), table de recherche lexicale **E418 / E44C–E720**, table des opérateurs **E736** et entrée `CLS` **C280**. Les noms du tableau ci-dessous sont les graphies lues dans la table (y compris `ON ERROR GOTO` et `ON BREAK`) ; cela **ne démontre ni la syntaxe complète, ni toutes les variantes directes**, ni les commandes RSX `|…`, périphériques/disquettes/extensions ou toutes les séquences d'échappement. **Inventaire global CPC : INCOMPLET / UNVERIFIED**, inventaire des mots-clés ROM montrés : vérifié statiquement, sans garantie de toutes leurs constructions.
- **Native** : [`core/basic_tokenizer.c`](../core/basic_tokenizer.c) (`keywords[]`, grammaires locales), [`core/basic_listing.c`](../core/basic_listing.c) (`decode`), [`core/basic_executor.c`](../core/basic_executor.c) (`execute_line`, `pen_argument`, `ink_arguments`), [`core/basic_session.c`](../core/basic_session.c) (direct `LIST/NEW` seulement), [`core/basic_session_runtime.c`](../core/basic_session_runtime.c) (`RUN` direct / `bsr_step_events`). Aucun parseur générique pour tous les mots ROM.
- **Cible** : [`integration/hw4_pen_bridge.c`](../integration/hw4_pen_bridge.c), [`firmware/esp32_display_probe/main/hw4_c2_console.c`](../firmware/esp32_display_probe/main/hw4_c2_console.c), [`io/cpc_uart_console.c`](../io/cpc_uart_console.c) et [`video/cpc_video.c`](../video/cpc_video.c). Une API graphique peut exister **sans** prise en charge d'une commande BASIC correspondante.
- **Tests** : [`tests/test_basic_session.c`](../tests/test_basic_session.c), [`tests/test_basic_session_runtime.c`](../tests/test_basic_session_runtime.c), [`tests/test_basic_executor.c`](../tests/test_basic_executor.c), [`tests/test_basic_pen_events.c`](../tests/test_basic_pen_events.c), [`tests/test_basic_ink_events.c`](../tests/test_basic_ink_events.c), [`tests/test_basic_abs_token_list.c`](../tests/test_basic_abs_token_list.c), [`tests/test_hw4_pen_a.c`](../tests/test_hw4_pen_a.c) et [CI du dépôt](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions). Les tests C99 ne sont pas un oracle CPC.

## Repères de preuve / statut de mission

| Repère | Source primaire | Couverture pertinente et limites |
|---|---|---|
| [HW4] | [HW4-C2 UART](HW4-C2-uart-interactive-console.md), [HW4-PEN-A](HW4-PEN-A-native-pen-mode1.md), [#91](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/91) | `RUN/LIST/NEW` et `PRINT` de programmes ciblés ont des rapports PO sur leurs SHA, sans généralisation ; quelques cas PEN/HW4 restent distincts. |
| [PEN] | [J1.17-A](J1.17-A-pen-cpc-oracle.md), [J1.17-C-A](J1.17-C-A-pen-5-14-cpc-oracle.md), [issue B #210](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/210) | CPC accepte `PEN 5..14` (`ERR=0/ERL=0`, deux palettes, 52 acquisitions) ; au **SHA audité**, C99 renvoie encore `BE_UNSUPPORTED` ; jalon B indépendant non fusionné à cet instant. `PEN 8/12` invisibles dans leurs contextes RGB, sans indice général prouvé. |
| [INK] | [J1.18-A](J1.18-A-ink-cpc-oracle.md), [J1.18-B](J1.18-B-ink-native.md) | 13 formes scellées ; certains couples C99 émettent `SET_INK` ; le pont CYD rejette tout événement INK (`HW4_PEN_SET_INK_UNSUPPORTED`). La forme clignotante `INK 1,26,6` est LIST-only / unsupported RUN. |
| [ABS] | [J1.20-A](J1.20-A-abs-integer-cpc-oracle.md), [J1.20-B1](J1.20-B1-abs-token-list-native.md) | 16 sources exactes `FF 00`, 2 archives chaque ; `TOKEN/LIST` natifs sur cas bornés **sans calcul `ABS` en RUN**, y compris témoins d'erreurs à l'exécution CPC. |
| [F10] / [F13] / [F14] | [IF/THEN](J1.10-B-if-then-integer-native.md), [comparaisons](J1.13-B-integer-relational-if-native.md), [ELSE](J1.14-B-if-inline-else-native.md) | IF INTEGER, opérateurs relationnels et ELSE inline dans les corpus jalonnés ; pas de langage booléen général. |
| [F11] / [F12] | [GOSUB/RETURN](J1.11-B-gosub-return-native.md), [FOR/NEXT](J1.12-B2-for-next-integer-native.md) | Formes de contrôle de flux INTEGER et piles bornées, oracles indépendants dans les rapports A correspondants. |
| [MATH] / [VAR] / [P15] / [FL] / [EX] / [TOK] | [Rapports J1](PROJECT_STATUS.md), [J1.9](J1.9-B-integer-binary-family-native.md), [J1.15](J1.15-B-string-scalar-native.md), [J0.7](J0.7-basic-executor.md), [J0.4](J0.4-basic-tokenizer.md) | Opérateurs entiers bornés, affectation INTEGER et chaîne scalaire, PRINT de valeurs et de chaînes limitées ; pas d'évaluateur BASIC universel. [FL] vise le saut GOTO, [EX] le chemin END, [TOK] la grammaire native. |
| [VIDEO] / [CLS] | [`cpc_video.c`](../video/cpc_video.c), [`cpc_uart_console.c`](../io/cpc_uart_console.c), [source ROM CLS C280](http://cpctech.cpc-live.com/docs/basic.asm) | API MODE1 / encres / clear de console **sans** commandes BASIC `MODE/PAPER/CLS`. Oracle CLS à constituer séparément. |

## Vue rapide pour utiliser le projet

| Famille | Ce qui fonctionne aujourd'hui, dans ses bornes | Ce qui manque |
|---|---|---|
| Éditeur/stockage | Lignes numérotées, remplacement/suppression, `LIST`, `NEW` direct, `RUN` séquencé, `END` | Editeur CPC complet, commandes directes générales, `AUTO/RENUM/EDIT/DELETE`, gestion fichiers |
| Sortie et variables | `PRINT` de chaînes/entiers/scalaires limités, INTEGER `%`, STRING `$` et trois témoins REAL5 ; colon et commentaires bornés | Fonctions, tableaux, expression générales, imprimerie CPC `#` réelle |
| Flux | `GOTO/GOSUB/RETURN`, `IF/THEN/ELSE` INTEGER, `FOR/TO/STEP/NEXT` INTEGER bornés | Conditions/expressions générales, `WHILE/WEND`, `ON`, `STOP/CONT` |
| Opérateurs/fonctions | Comparaisons INTEGER et `+/-/*/\`/`MOD` bornés ; `ABS` uniquement token/LIST | Réel mathématique général, opérateurs logiques/bitwise, `ABS` exécutable |
| CPC affichage | `PEN 0..4,15` C99, pont MODE1 borné ; `INK` événement natif C99 borné | `PEN 5..14` C99 (issue #210), `INK` raccord CYD, `CLS/MODE/PAPER`, autres dessins |
| Périphériques | UART/écran hôte pour les tests indiqués | BASIC `SOUND`, fichiers, imprimante/flux CPC, mémoire/ports, RSX, graphisme complet |

## Catalogue ROM : une entrée par mot-clé

Le **mot-clé ROM n'est pas automatiquement un mot-clé reconnu par le tokenizer natif**. `NOT_IMPLEMENTED` correspond au code *à cette base* et `UNVERIFIED` dans les colonnes CPC/PO ne nie pas la fonction sur Amstrad. Les instructions `PRINT`, `PEN`, `INK`, etc. ne sont dites exécutables que pour les formes bornées signalées. Pour toute ligne marquée « non planifié », aucun jalon n'est auto-décrété : le Pilotage doit d'abord mandater l'oracle puis, le cas échéant, le natif.

### Programme / flux / édition

| Entrée ROM 1.1 | Forme **native** | Token/LIST + RUN C99 | Pont CYD BASIC | Oracle CPC indépendant | Essai physique PO | Écart et suite |
|---|---|---|---|---|---|---|
| `AUTO` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `AFTER` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `CAT` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `CHAIN` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `CLEAR` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `CLOSEIN` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `CLOSEOUT` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `CONT` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `DATA` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `DELETE` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `EDIT` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `END` | numérotée | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | UNVERIFIED | UNVERIFIED | END en RUN borné, pas STOP/CONT; [EX] |
| `ERASE` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `ERROR` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `EVERY` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `FOR` | numérotée | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | CPC_ORACLE_VERIFIED | UNVERIFIED | INTEGER avec bornes et STEP, pile et overflow host limités; [F12] |
| `GOSUB` | numérotée | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | CPC_ORACLE_VERIFIED | UNVERIFIED | cible constante, pile bornée, RETURN associé; [F11] |
| `GOTO` | numérotée | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | CPC_ORACLE_VERIFIED | UNVERIFIED | cible constante L1..65535, formes GOTO uniquement; [FL] |
| `IF` | numérotée | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | CPC_ORACLE_VERIFIED | UNVERIFIED | INTEGER condition bornée THEN/ELSE; pas IF général; [F10][F13][F14] |
 scalaire; LET implicite sans jeton A5; [VAR] |
| `LIST` | direct | LIST_ONLY (stocké) / C99_NATIVE_BOUNDED (direct) | CYD_CONNECTED | UNVERIFIED | ON_DEVICE_PO_REPORTED_PASS | commande directe; L10 LIST tokenisable, RUN non exécuté; [HW4] |
| `LOAD` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `MERGE` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `NEW` | direct | LIST_ONLY (stocké) / C99_NATIVE_BOUNDED (direct) | CYD_CONNECTED | UNVERIFIED | ON_DEVICE_PO_REPORTED_PASS | efface programme par session, pas par !CLS; NEW stocké non exécuté; [HW4] |
| `NEXT` | numérotée | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | CPC_ORACLE_VERIFIED | UNVERIFIED | NEXT avec ou sans variable % selon sous-ensemble; [F12] |
| `ON` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `ON BREAK` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `ON ERROR GOTO` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `ON SQ` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `OPENIN` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `OPENOUT` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `PRINT` | numérotée | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | CPC_ORACLE_VERIFIED | ON_DEVICE_PO_REPORTED_PASS | littéral, entier <=255, variable %/$, témoins REAL5; sortie via console, pas PRINT général; [P15][HW4] |
| `RANDOMIZE` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `READ` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `REM` | numérotée | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | UNVERIFIED | UNVERIFIED | commentaire opaque, y compris deux-points; [TOK][EX] |
| `RENUM` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `RESTORE` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `RESUME` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `RETURN` | numérotée | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | CPC_ORACLE_VERIFIED | UNVERIFIED | pile GOSUB, RETURN sans appel refusé; [F11] |
| `RUN` | direct | LIST_ONLY (stocké) / C99_NATIVE_BOUNDED (direct) | CYD_CONNECTED | UNVERIFIED | ON_DEVICE_PO_REPORTED_PASS | RUN direct par BSR avec limite firmware 256 pas; RUN stocké non exécuté; [HW4] |
| `SAVE` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `STOP` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `TRON` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `TROFF` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `WEND` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `WHILE` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |

### Texte / affichage / graphisme

| Entrée ROM 1.1 | Forme **native** | Token/LIST + RUN C99 | Pont CYD BASIC | Oracle CPC indépendant | Essai physique PO | Écart et suite |
|---|---|---|---|---|---|---|
| `BORDER` | CPC forme à caractériser | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | appel VIDEO/ROM ≠ connexion BASIC; mission à qualifier |
| `CLG` | CPC forme à caractériser | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | appel VIDEO/ROM ≠ connexion BASIC; mission à qualifier |
| `CLS` | CPC forme à caractériser | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | ROM 8A, C280→TXT CLEAR WINDOW &BB6C; oracle CLS séparé demandé; [CLS] |
| `DRAW` | CPC forme à caractériser | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | appel VIDEO/ROM ≠ connexion BASIC; mission à qualifier |
| `DRAWR` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `FILL` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `GRAPHICS` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `INK` | numérotée | LIST_ONLY + C99_NATIVE_BOUNDED | NOT_IMPLEMENTED | CPC_ORACLE_VERIFIED | UNVERIFIED | liste blanche de couples C99, événement SET_INK; bridge CYD rejette avant peinture; clignotement non impl.; [INK] |
| `LOCATE` | CPC forme à caractériser | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | appel VIDEO/ROM ≠ connexion BASIC; mission à qualifier |
| `MASK` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `MODE` | CPC forme à caractériser | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | API VIDEO existante ≠ instruction BASIC native; [VIDEO] |
| `MOVE` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `MOVER` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `ORIGIN` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `PAPER` | CPC forme à caractériser | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | API VIDEO existante ≠ instruction BASIC native; [VIDEO] |
| `PEN` | numérotée | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | CPC_ORACLE_VERIFIED | UNVERIFIED | 0..4,15 seulement RUN C99; 5..14 acceptés CPC mais BE_UNSUPPORTED; 16/-1 invalide; CYD MODE1 0..3 + 4/15 bornés; #210 [PEN] |
| `PLOT` | CPC forme à caractériser | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | appel VIDEO/ROM ≠ connexion BASIC; mission à qualifier |
| `PLOTR` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `SYMBOL` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `TAG` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `TAGOFF` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `WINDOW` | CPC forme à caractériser | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | appel VIDEO/ROM ≠ connexion BASIC; mission à qualifier |
| `WIDTH` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `WRITE` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `ZONE` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |

### Machine / entrée / son / divers

| Entrée ROM 1.1 | Forme **native** | Token/LIST + RUN C99 | Pont CYD BASIC | Oracle CPC indépendant | Essai physique PO | Écart et suite |
|---|---|---|---|---|---|---|
| `CALL` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `CURSOR` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `DEF` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `DEFINT` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `DEFREAL` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `DEFSTR` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `DEG` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `DI` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `DIM` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `EI` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `ENT` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `ENV` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `FRAME` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `INPUT` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `KEY` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `MEMORY` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `OUT` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `POKE` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `RAD` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `RELEASE` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `SOUND` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `SPEED` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `SWAP` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `WAIT` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |

### Fonctions / identifiants CPC

| Entrée ROM 1.1 | Forme **native** | Token/LIST + RUN C99 | Pont CYD BASIC | Oracle CPC indépendant | Essai physique PO | Écart et suite |
|---|---|---|---|---|---|---|
| `ABS` | fonction en PRINT/affect. | LIST_ONLY | NOT_IMPLEMENTED | CPC_ORACLE_VERIFIED | UNVERIFIED | FF 00 pour 16 témoins scellés; RUN C99 refusé; [ABS] |
| `ASC` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `ATN` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `BIN$` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `CHR$` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `CINT` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `COPYCHR$` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `COS` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `CREAL` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `DEC$` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `DERR` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `EOF` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `ERL` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `ERR` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `EXP` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `FIX` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `FN` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `FRE` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `HEX$` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `HIMEM` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `INKEY` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `INKEY$` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `INP` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `INSTR` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `INT` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `JOY` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `LEFT$` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `LEN` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `LOG` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `LOG10` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `LOWER$` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `MAX` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `MID$` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `MIN` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `PEEK` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `PI` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `POS` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `REMAIN` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `RIGHT$` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `RND` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `ROUND` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `SGN` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `SIN` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `SPACE$` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `SQR` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `STR$` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `STRING$` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `TAN` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `TEST` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `TESTR` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `TIME` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `UNT` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `UPPER$` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `VAL` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `VPOS` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `XPOS` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `YPOS` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |

### Opérateurs / mots de grammaire

| Entrée ROM 1.1 | Forme **native** | Token/LIST + RUN C99 | Pont CYD BASIC | Oracle CPC indépendant | Essai physique PO | Écart et suite |
|---|---|---|---|---|---|---|
| `AND` | expression CPC non acquise | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | à caractériser indépendamment; pas d'expression C99 générale |
| `OR` | expression CPC non acquise | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | à caractériser indépendamment; pas d'expression C99 générale |
| `XOR` | expression CPC non acquise | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | à caractériser indépendamment; pas d'expression C99 générale |
| `NOT` | expression CPC non acquise | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | à caractériser indépendamment; pas d'expression C99 générale |
| `MOD` | expression INTEGER | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | CPC_ORACLE_VERIFIED | UNVERIFIED | A% MOD entier/référence en affectation bornée; [MATH] |
| `TO` | expression FOR | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | CPC_ORACLE_VERIFIED | UNVERIFIED | seulement en FOR INTEGER; [F12] |
| `STEP` | expression FOR | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | CPC_ORACLE_VERIFIED | UNVERIFIED | seulement en FOR INTEGER; STEP 0 refus hôte; [F12] |
| `THEN` | expression IF | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | CPC_ORACLE_VERIFIED | UNVERIFIED | uniquement dans le IF pris en charge; [F10][F14] |
| `ELSE` | expression IF | LIST_ONLY + C99_NATIVE_BOUNDED | CYD_CONNECTED | CPC_ORACLE_VERIFIED | UNVERIFIED | branche IF inline limitée; [F14] |
| `USING` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `TAB` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `SPC` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |
| `SQ` | UNVERIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED | UNVERIFIED | non planifié; oracle + tokenisation + C99 + CYD par mandats distincts |

## Formes lexicales et expressions **non autonomes**

| Source/forme | Direct vs ligne | Token/LIST | RUN C99 | CYD | CPC/PO et limite | Suite |
|---|---|---|---|---|---|---|
| `?"X"` alias `PRINT` | numérotée | LIST_ONLY | C99_NATIVE_BOUNDED (`PRINT`) | CYD_CONNECTED via RUN | CPC forme de référence, résultat exact hors témoins UNVERIFIED | tests syntaxiques supplémentaires |
| `10 A%=...`, `10 LET A%=...` | numérotée | LIST_ONLY | C99_NATIVE_BOUNDED (scalaires INTEGER bornés) | CYD_CONNECTED via RUN | cas A/J1 attestés ; pas tableau ni expression complète | extension sous mandat |
| `10 A$="X"`, `PRINT A$` | numérotée | LIST_ONLY | C99_NATIVE_BOUNDED (STRING scalaire, arène limitée) | CYD_CONNECTED via RUN | [J1.15](J1.15-B-string-scalar-native.md); [J1.15-C](J1.15-C-cyd-string-arena.md) | extension sous mandat |
| `A=0.5 / A=1.25 / A=-0.5` | numérotée | LIST_ONLY | C99_NATIVE_BOUNDED (trois records REAL5) | CYD_CONNECTED via RUN | [J1.16-B/C/D-B](J1.16-B-real5-half-native.md) ; pas REAL générique | généralisation non autorisée |
| `+`, `-`, `*`, `\`, `MOD` | expression INTEGER | LIST_ONLY | C99_NATIVE_BOUNDED (binaire entier explicite, réf./immédiat, sous-ensemble) | CYD_CONNECTED via RUN | [J1.3–J1.9](PROJECT_STATUS.md), division entière et débordement bornés | extension au moteur général |
| `=`, `<`, `>`, `<=`, `>=`, `<>` | IF INTEGER, affectation (`=`) | LIST_ONLY | C99_NATIVE_BOUNDED (témoins IF relations) | CYD_CONNECTED via RUN | [J1.13-A](J1.13-A-integer-relational-if-cpc-oracle.md) | pas IF/expr généraux |
| `/`, `^`, `AND`, `OR`, `XOR`, `NOT` | expressions CPC non acquises | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | UNVERIFIED pour ce code natif, bien qu'en ROM | oracle puis jalon à mandater |
| `:` | instruction numérotée | LIST_ONLY (token 01 hors chaîne) | C99_NATIVE_BOUNDED pour enchaînements admissibles, restrictions sur assignation/IF | CYD_CONNECTED via RUN | aucune sémantique générale revendiquée | tests au cas par cas |
| `'` | commentaire numéroté | LIST_ONLY (`01 C0`) | C99_NATIVE_BOUNDED (commentaire opaque) | CYD_CONNECTED via RUN | distinct de `REM`, apostrophe non token C0 isolé | extension si besoins |
| `PRINT #8,...` | instruction numérotée | LIST_ONLY pour témoins | C99_NATIVE_BOUNDED pour témoins stricts, **pas** une imprimante CPC raccordée | NOT_IMPLEMENTED comme imprimante | CPC fichiers imprimante oracles ≠ dispositif CYD | périphérique à mandater |
| `GO TO` / `GO SUB` | variante orthographique ROM | UNVERIFIED (tokenizer natif attend `GOTO`/`GOSUB`) | NOT_IMPLEMENTED comme variante | NOT_IMPLEMENTED | ROM référence variantes, pas de capture de cette forme native | oracle si utile |
| `CLS #...` | forme hypothétique non acquise | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | **UNVERIFIED** ; ne pas la présenter comme syntaxe CPC avant vérification | seulement après oracle CLS |

## Commandes hôte réservées — `HOST_ONLY`, pas du BASIC

| Entrée au prompt UART | Couche interceptant la saisie | Effet réel | Programme BASIC | Statut |
|---|---|---|---|---|
| `!CLS` | `hw4_c2_console.c::execute_line()` **avant** `basic_submit/bsr_submit` | `hw4_pen_console_clear()` délègue `cpc_uart_console_clear()` : reinitialise la surface MODE 1, INK0=1 (bleu), INK1=24 (jaune), PEN1/PAPER0 et texte ; puis restauration INK2=6 (rouge), INK3=18 (vert) ; reset métriques scroll locales | **Conservé** ; `RUN` après `!CLS` relit les mêmes lignes | `HOST_ONLY` / **pas** token, pas `CLS` CPC |
| `!DEMO` | même point d'entrée firmware | appelle le véritable `BSR` avec `NEW`, `10 A%=2`, `20 B%=A%+3`, `30 PRINT B%`, `40 END`, `RUN` | **Remplacé volontairement** par ce témoin, non préservé | `HOST_ONLY`, pas token `DEMO` CPC |
| `CLS` (sans `!`) | **non intercepté** : passe à `basic_submit` | direct refusé par `bs_process_line` ; en ligne numérotée refusé par le tokenizer (`CLS` absent de `keywords[]`) | aucun effet de clear BASIC | `NOT_IMPLEMENTED` : **ne pas** l'aliaser vers `!CLS` |

**Différence historique :** la ROM BASIC 1.1 indexe `CLS` **token 8A**, via `basic.asm` **C280 → appel `&BB6C` « TXT CLEAR WINDOW »**, effacement dans **la fenêtre texte courante**, et non la procédure firmware qui remet MODE1 et les encres du terminal dans un état de service. Un `CLS` natif devra préserver les règles CPC de fenêtre, curseur et couleur, après acquisition CPC. Les `MODE`/`PAPER` et l'encre de dessin sont aussi des instructions distinctes des API `cpc_video_*`.

## Exemples contradictoires vérifiables (ne pas fusionner leurs états)

1. `NEW`, `10 PRINT "X"`, `LIST`, `RUN` : les commandes directes passent par le runtime ; `PRINT` stocké émet sur le sous-ensemble natif, mais `PRINT "X"` **direct** n'est pas pris en charge (`BS_UNSUPPORTED_DIRECT`).
2. `10 PEN 5` : token `BB 20 13`, LIST possible, **CPC accepté** en MODE1 (`ERR=0/ERL=0` dans [J1.17-C-A](J1.17-C-A-pen-5-14-cpc-oracle.md)), mais `core/basic_executor.c::pen_argument()` renvoie `BE_UNSUPPORTED` à la base auditée ; [issue #210](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/210) est séparée. Ne pas confondre acceptance CPC et CYD.
3. `10 INK 1,26` : token/LIST et émission logique C99 `SET_INK` dans la liste blanche, mais `hw4_pen_preflight()` renvoie `HW4_PEN_SET_INK_UNSUPPORTED` **avant toute peinture** ; aucune conformité CYD n'en découle.
4. `10 PRINT ABS(1)` : token de fonction `FF 00` et LIST vérifiés dans le corpus J1.20-B1 ; RUN C99 non implémenté. `10 B%=ABS(A%)` peut également être encodé sans calcul natif.
5. `10 MODE 1` ou `10 PAPER 0` : les API `cpc_video_set_mode` / `cpc_video_set_text_colors` sont opérationnelles en tant que primitives vidéo hôte, **mais** aucune entrée `MODE`/`PAPER` dans la table du tokenizer C99. `CLS` réel est absent lui aussi.
6. `!CLS` suivi de `LIST` : programme conservé ; `!DEMO` suivi de `LIST` : programme remplacé par le témoin. Les deux sont `HOST_ONLY` et n'ont pas d'équivalent BASIC implicite.

## Travaux restants à soumettre au Pilotage (sans démarrer ici)

- **Priorité de vérité** : acquérir un oracle **CPC CLS** indépendant, sur sessions isolées `CLS` directe et `10 CLS`/`RUN`, fenêtre courante (`WINDOW`), curseur avant/après, `PEN/PAPER/INK` et palette, effets RGB et RAM/token `8A`, `ERR/ERL` ; vérifier toute variante `CLS #` **seulement** si la ROM/CPC l'atteste. Première mission oracle seule, puis mandat natif C99 et raccord CYD dans d'autres PR avec preuves distinctes.
- **Moteur** : `ABS` (seulement LIST), `PEN 5..14` (#210, C99 seulement), `INK` CYD, `MODE`/`PAPER`, syntaxe directe hors `LIST/NEW/RUN`, expressions générales, fonctions numériques/chaînes, tableaux, entrée/sortie CPC.
- **Périphériques** : graphisme CPC, fenêtre texte, imprimante `#8`, fichiers/disquettes, son, port/joystick, RSX et tests physiques par SHA. Le seul tableau ROM ne suffit pas à planifier la totalité de ces fonctionnalités.

### Traçabilité et limites

Ce document ne change ni les jalons précédents ni leurs statuts datés, même lorsqu'une mention historique « non implémenté » n'est plus actuelle. [README](../README.md) annonce clairement la photographie du 27 octobre. Le tableau reflète le **code `main` audité** et peut devenir périmé dès qu'un nouveau commit est fusionné : réauditer le diff `tokenizer → listing → executor → bridge → firmware` et les preuves CPC/PO pour toute promotion de statut. Absence de preuve ≠ invalidité CPC ; `TARGET_BUILD_VERIFIED` n'est pas `ON_DEVICE_PO_REPORTED_PASS`.
