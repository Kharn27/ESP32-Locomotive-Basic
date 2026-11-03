# HW4-DIAG-SYNTAX-A — Erreur syntaxique directe, cas prouvé

Mandat : [Issue #288](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/288).
Base GitHub revérifiée avant branche : `origin/main@355b9bd67ba8970abafcf67978854cebcb878273`.
Branche : `fix/hw4-diag-syntax-unknown-command`.

## Origine et limite de classification

**ROM fournie par le PO** (fichier `basic.asm` joint au mandat / référence du projet) :
- `cb49 3e02 : LD A,$02`, marqué `Error: Syntax Error` ; chemin commun `cb55`.
- Table des messages à `cd98` : `"Syntax",&15`, avec substitution pour le suffixe ` error`. Le libellé retenu pour l'écran C99 est **`Syntax error\n`** (casse et LF contractuels).
- Le mandat #288 désigne `LISTT` comme faute de frappe de `LIST`. **Aucun run CPC indépendant de ce mot n'a été effectué ici** : la ROM établit le message de l'erreur 2, le mandat qualifie le cas `LISTT`, pas les autres chaînes.

**Cause et statut** : `bsr_submit` → `BSR_SESSION_ERROR` et `BS_UNSUPPORTED_DIRECT`, avec `BT_OK`, `BP_OK`, `BL_OK` ; comparaison octet par octet du seul mot **`LISTT`**, ASCII insensible à la casse et espaces de bord ignorés, sans suffixe ni séparateur. Cette signature exhaustive déclenche `CPC_DIAG_DIRECT_LISTT_SYNTAX`, origine `CPC_DIAG_ORIGIN_DIRECT_LISTT_ROM_CB49`. La fonction `cpc_diag_policy_direct_origin` la rend contrôlable explicitement. Les catégories antérieures restent inchangées.

**Barrière essentielle** : `BS_UNSUPPORTED_DIRECT` est une **cause hôte non discriminante** ; `GOTO 999`, `MODE 1`, `PAPER 2`, `AUTO` sont des commandes valides mais pas gérées en direct. Elles gardent `HOST_GENERIC` et `ERROR\n`. `LISTTT`, `LISTT 1`, `LISTT:RUN`, les erreurs UART/transport et les statuts fabriqués ou non pertinents restent aussi génériques. Il n'existe **aucun diagnostic CPC inventé** pour des commandes non vérifiées. Étendre à toutes les inconnues demanderait une classification explicite reconnu/inconnu en CORE : **mini-arbitrage Pilotage nécessaire avant tout élargissement**, conformément au mandat.

## Réalisation

Le changement est limité à **`io/cpc_diag_policy.[ch]`**, le test existant **`tests/test_hw4_diag_a.c`** et le présent rapport. Le fichier firmware de la console, la politique Ready et les sources CORE ne changent pas. Le chemin de console utilise déjà `cpc_diag_policy_select → cpc_diag_policy_write → CPC_READY_BASIC_DIAGNOSTIC` : il affiche donc la nouvelle catégorie sans modification du propriétaire matériel.

Un formateur direct pur `cpc_diag_policy_format_direct` permet la comparaison précise de `Syntax error\n` et refuse les catégories illégales, les arguments manquants ou une capacité insuffisante **sans changer le buffer complet ni le compteur**. L'écrivain `cpc_diag_policy_write` l'emploie pour les trois diagnostics directs : `ERROR\n`, `Line does not exist\n` et `Syntax error\n`. Il n'écrit jamais lui-même `Ready`.

Les tests vérifient l'intégration réelle `UART_LINE → bsr_submit → diagnostic → Ready → prompt`, le rendu du texte, la sélection de catégorie, la provenance, les canaris vidéo, la conservation intégrale des octets du programme, les variantes de casse, les faux positifs et les capacités du formateur. Les cas historiques `RUN`, `LIST`, `NEW`, `GOTO 999`, `Line does not exist`, BONJOUR et scroll sont conservés.

## Preuves à relever sur HEAD final

```sh
cmake -S . -B build/hw4-diag-syntax-gcc-off -DBUILD_TESTING=ON \
  -DBP_SANITIZERS=OFF -DCMAKE_C_COMPILER=gcc
cmake --build build/hw4-diag-syntax-gcc-off -j2
ctest --test-dir build/hw4-diag-syntax-gcc-off \
  -R 'hw4_diag_a_native_cpc_diagnostic|hw4_ready_a_real_policy_vram_runtime' --output-on-failure
# Relancer toutes les suites GCC/Clang OFF/ON, sanitizers, ARCH/OPT3,
# scellement CPC et trois builds Xtensa selon les workflows existants.
```

Le rapport du HEAD exact et les métriques de mémoire doivent être relevés dans la **REMISE DÉVELOPPEUR** après les exécutions GitHub ; ne pas considérer des jobs SKIPPED comme PASS. **CYD physique : ON_DEVICE_UNVERIFIED** sans test PO sur ce SHA. Aucun nouveau témoin CPC indépendant n'est revendiqué.

**Remise au Pilotage exclusivement, PR ouverte non fusionnée.**
