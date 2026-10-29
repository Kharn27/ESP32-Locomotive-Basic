# HW4-DIAG-A — A0 CPC diagnostics de suppression

Mandat du Pilotage : [issue #159](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/159#issuecomment-6499793123). Base réellement vérifiée : `main@6699b828b4526aa707d67eb32871b0dcb5342b36`. PR #162 REAL5 parallèle : aucune modification du `core/`.

## A0 — acquisition ROM effective du 29 octobre 2026

- [GitHub Actions #40895194240](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40895194240), checkout d'acquisition `2f1aa23aba49aa8b27a12dbd84289fc94f5ed197`.
- Outil `tools/hw4_diag_a_cpc.py`; Caprice32 `8c778bf072a06fb7c23b9cccd179041db7f79a52` ; ROM CPC6128 BASIC 1.1 SHA-256 `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562` ; image GHCR `sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c`.
- `tests/fixtures/cpc6128/hw4_diag_a/`: **20 PNG (10 cas × 2 processus CPC indépendants), dix paires identiques SHA-256**, séquences brutes, `cap32.cfg`, journaux et manifeste archivés. Aucun fichier ROM ni snapshot historique J0/J1 altéré. Captures 768×540 pixels, capture CAP32 sans espace parasite.
- Une capture *écran* est la preuve ici ; les valeurs `BSR` du C99, désassemblages et imprimante ne servent pas d'oracle. Les séquences `GOTO 999` sont exécutables directement sur **CPC**, mais actuellement *non supportées comme commande directe du moteur natif*.

| Cas | Séquence | Texte final observé sur écran CPC | Ready post-saisie | Effet / contrôle | SHA-256 original PNG |
|---|---|---|---|---|---|
| D01 | `10` absent | `Line does not exist` | oui | ligne absente ; état initial vide | `e8f731b770e2f87de775e11dd8f394c15e294c0208aee857f9d402e39f09e2c8` |
| D02a | `10 PRINT 2` → `10` | aucun diagnostic | non | suppression ligne 10 réussie | `c6a669ab8a6d45b03fbaf7a635341f9204d4df3de6b231386e621bdb0988a25d` |
| D02b | idem → `LIST` | liste vide, aucun diagnostic | oui après LIST | absence de la ligne dans LIST | `8bad7d319c6435aa1ab3ec28b8e2df24d0f618188ca6793238abd4ece4fe98a0` |
| D03 | `NEW` → `10` | `Line does not exist` | oui après NEW puis oui après erreur | programme vide | `b767736d44a8d03db02a62b81c736b53e8bc96f47365292c2c6e6424f75b406b` |
| D04 | `10 ` (avec espace) | `Line does not exist` | oui | même écran bit-à-bit que D01 | `e8f731b770e2f87de775e11dd8f394c15e294c0208aee857f9d402e39f09e2c8` |
| D05a | `GOTO 999` direct sur CPC | `Line does not exist` | oui | **hors mapping natif autorisé**, commande directe non supportée | `d62e0da2a96f4eeecd6cd36101279d65009fd6920fcff911492f23df129dd951` |
| D05b | `LIST` vide | aucun diagnostic | oui | programme toujours vide | `91b421d10318467c1d6c6d393fce914dd4ff5ea5472535b5c2c9ef7baf67b655` |
| Contrôle | `10 PRINT 2` → `LIST` | `10 PRINT 2` | oui après LIST | ligne présente | `b788d7545207374b53bb153bbf7f053e07b0d32c1b9c1462b450caf611e27679` |
| Contrôle | `10 PRINT 2` → `NEW` → `LIST` | liste vide | oui après NEW/LIST | nettoyage effectif | `74030e5b9116a643cdc5d4a106f2dc6db6c722b06709d105a840432b52be1bf9` |

**Statuts :** ces dix écrans sont `OBSERVÉ CPC`; la règle de présentation pour `10` et `10 ` absents est probante. Le curseur visible repart en première colonne de la ligne suivant le `Ready` le cas échéant, et après la ligne saisie quand le `Ready` est absent. Le moteur natif direct `GOTO 999` est `NON SUPPORTÉ`, et l'application de la règle à d'autres diagnostics internes est `NON TESTÉ` / exclue. `10 PRINT 2` suivi de `10` ne produit pas d'erreur et ne doit pas produire de `Ready`. La présence de `Line does not exist` sur le CPC pour GOTO n'autorise **pas** à changer le diagnostic `ERROR` sur CYD pour cette commande.

**Barrière A0 → A1 : franchissable** pour la suppression absente uniquement, sans toucher `core/` ni à `io/cpc_ready_policy.*`.


## A1 — implémentation bornée (aucune modification de `core/`)

L'adaptateur C99 `io/cpc_diag_policy.{h,c}` détermine `NUMBERED_DELETE_ABSENT` **seulement si** tous les critères suivants sont vérifiés : `BSRResult.status == BSR_SESSION_ERROR`, `session.status == BS_NOT_FOUND`, tous les sous-statuts `BT/BP/BL` sont `OK`, et l'entrée originale est un entier décimal de ligne valide (1..65535) suivi uniquement d'espaces ASCII ou de fin d'entrée. Les nombres saisis sont des **numéros de lignes**, jamais des numéros d'erreur ROM. Le contrôle de syntaxe est une garde de présentation, pas une réécriture de la grammaire. Les cas A0 `10` et `10 ` sont attestés ; la généralisation aux autres valeurs de numéros repose sur la sémantique native identique, non sur un écran CPC acquis pour chaque valeur.

`CPC_DIAG_LINE_DOES_NOT_EXIST` écrit exactement `Line does not exist\n` ; `CPC_DIAG_HOST_GENERIC` écrit exactement `ERROR\n`. La vraie fonction de production `cpc_diag_policy_write()` écrit une seule fois dans `CpcText`, sans framebuffer supplémentaire, allocation dynamique ou copie de programme. Dans `hw4_c2_console.c`, la décision est prise sur l'objet **réel** `BSRResult` renvoyé par `bsr_submit`, et non sur des codes `6`/`1` inventés. Les autres erreurs de `bsr_submit`, les erreurs de `bsr_step`, la limite de pas, et les événements UART rejetés restent des diagnostics `ERROR` d'origine hôte. Les traces bornées `HW4-DIAG-A DIAG_POLICY` identifient catégorie, origine, statut session pour `submit` et message ; aucun contenu utilisateur illimité.

La responsabilité de `Ready` demeure **intégralement** celle de `io/cpc_ready_policy` issue de la PR #161. Après une suppression absente, `BASIC_DIAGNOSTIC` produit exactement un `Ready` ; suppression réussie => aucun diagnostic ni Ready. `LIST`/`NEW`/`RUN` conservent leur politique et `!CLS`/`!DEMO` restent des commandes hôtes.

### Tests natifs de production

`tests/test_hw4_diag_a.c` instancie réellement `BasicSessionRuntime`, `BasicVariableStore` avec arène STRING, programme, `UartLine`, console vidéo MODE 1, `cpc_diag_policy_select/write` et `cpc_ready_policy_apply` ; aucune réussite `BSR` simulée pour les cas positifs. Les cas incluent : `10` absent, `10 ` absent, création/suppression `10 PRINT 2` + `LIST` vide, `NEW` + `10`, `GOTO 999` et `listt` conservant `ERROR`, numéro `0` invalide, faux états de diagnostic isolés en tests **négatifs**, comptages du `Ready`, caractères réellement peints et canaris VRAM. L'exécution native `10 A$="BONJOUR"` / `20 PRINT A$` / `30 END` vérifie le résultat `BONJOUR` **avant** le Ready final de `RUN` ; un diagnostic au bas de l'écran vérifie le scrolling sans clipping. `tools/hw4_diag_a_evidence.py` ajoute un CTest permanent de l'archive A0 : 10 captures originales + 10 répétitions SHA, provenance, clavier, sortie émulateur et contrôle négatif de sceau.

**À renseigner en dernier après contrôle du HEAD :** CI Linux GCC/Clang OFF/ON + ASan/UBSan, CI CPC permanent + A0, CI ARCH/E2/scroll et Xtensa 3 profils, puis mémoire et `App version`. Une CI sautée n'est jamais présentée comme PASS.

## Protocole matériel PO obligatoire — avant décision du Pilotage

Sur le poste Linux avec ESP-IDF 5.5.6 actif, partir de la branche et vérifier le SHA **complet** contre celui remis dans la PR. Si le cache ESP-IDF correspond à un autre profil, utiliser un build CONSOLE neuf/isolé et ne jamais mélanger les sélecteurs de profils.

```bash
git fetch origin feat/hw4-diag-a-line-not-exist
git switch feat/hw4-diag-a-line-not-exist
git pull --ff-only origin feat/hw4-diag-a-line-not-exist
git rev-parse HEAD
cd firmware/esp32_display_probe
idf.py -DLOCO_CYD_PROFILE=CONSOLE build
idf.py -p /dev/ttyUSB0 flash
idf.py -p /dev/ttyUSB0 monitor
```

Vérifier la ligne `App version` contre le préfixe du SHA complet, puis tester les entrées ci-dessous sur l'écran CYD **et** en UART. Les séquences D02 démarrent après `NEW` pour garantir l'état du programme.

| Test PO | Actions CYD exactes | Verdict attendu (texte / Ready) |
|---|---|---|
| P00 boot | Mise sous tension | un `Ready` initial, curseur cohérent |
| P01 absent | `NEW`, `10` + Enter | `Line does not exist`, puis exactement un `Ready` |
| P02 existant | `10 PRINT 2`, `10` + Enter | suppression sans erreur et sans `Ready` additionnel |
| P03 prouver suppression | `LIST` + Enter | liste vide et un `Ready` |
| P04 après NEW | `NEW`, `10` + Enter | texte historique identique et un `Ready` |
| P05 témoin direct | `GOTO 999`, puis `listt` | `ERROR` générique pour chacun, aucun faux mapping historique |
| P06 régression | `10 PRINT 2`, `20 END`, `LIST`, `RUN` | liste intacte, sortie numérique `2`, `Ready` après LIST et RUN |
| P07 hôte | `!CLS` | effacement sans `Ready` supplémentaire |

Consigner **PASS/FAIL par scénario**, photos/constats des textes, casse, espaces et position du curseur, journal UART `HW4-DIAG-A DIAG_POLICY` et `HW4-READY-A READY_POLICY`, `HW4-C2 DEVICE_MEMORY` (`heap8_free`, `heap8_largest`, pile), `HW4-C3-B2-C1 LCD_METRICS`, `dma_fault=0`, `dma_timeouts=0`, `lcd_error=ESP_OK` et absence de panic. Le PO n'est **pas** chargé de fusionner. Sans ces preuves sur le **HEAD exact** : `ON_DEVICE_UNVERIFIED`, avis de livraison **conditionnel**, PR non fusionnée, Pilotage responsable de la décision.
