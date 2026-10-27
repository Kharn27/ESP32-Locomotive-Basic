# HW4-C2 — console BASIC UART0 vers TFT CYD (prototype natif)

## Point de départ et non-régressions

Basé sur `main` **e05e9a295c130de051006da55ed1cc67860e8bed** après HW4-C1 (#87) accepté/fusionné. Issue de mission **#90**. Le chantier J1.7-B (#89) reste distinct ; aucun `core/`, archive CPC, oracle, `cpc_video`, pilote LCD partagé ni autre banc firmware modifié. L'application `firmware/esp32_loco/` est la seule intégrée interactive.

## Chaîne réelle

```text
PC 115200 UART0 bytes -- uart_read_bytes
                        |
                        v
            io/uart_line.c  (C99, 120 octets, CR LF CRLF, BS DEL)
                        |
                input validé / refus
                        |
                        v
        bsr_submit() [core original] -> LIST/NEW/RUN/ligne stockée
                          -> bsr_step() [max 256 lignes par RUN]
                        |
              octets originaux PRINT/LIST
                        |
           video/cpc_text.c -> VRAM MODE1 16000 octets
                        |
      video/cpc_video_render_row -> LCD DMA 5120 octets (pilote unique)
```

Les octets affichés sont ceux de `bsr_submit` pour `LIST` et `bsr_step` pour `PRINT`. Aucun interpréteur, tokeniseur, exécution Z80 ni valeur `5` construite pour l'écran. Le vieux programme HW4-C1 subsiste uniquement comme **diagnostic explicite `!DEMO`**, via les appels réels BASIC.

## Contrat de saisie et limite de l'écran

- Entrée : UART0 115200 8N1, lignes ASCII 0x20..0x7e, sans terminaison stockée ; CR, LF ou CRLF = **un seul** submit ; BS et DEL effacent une cellule visuelle. Caractères non ASCII / contrôles ignorés. Prompt `>` : marqueur **hôte**, non BASIC.
- Mémoire de ligne statique : **120 octets utiles + sentinelle**. Au 121e caractère, signal `INPUT_OVERFLOW` et **rejet intégral** au Enter suivant, même si BS a ensuite raccourci la ligne. Aucune mutation du programme sur refus. Les 120 premiers octets peuvent rester visibles pendant le rejet ; le dépassement est annoncé sur UART.
- Écho : `cpc_uart_console_append` passe par `cpc_text_write`, BS/DEL repeint une cellule vide via `cpc_video_put_cell` et remet le curseur superposé. Les caractères `% = + - > " : /` ont un complément original provisoire au jeu HW3 ; police CPC ROM authentique non revendiquée.
- **Politique transitoire non CPC** : après toute commande, le prochain prompt exige assez de place pour la ligne maximale (4 rangées) ; s'il reste moins de quatre lignes, l'écran logique est automatiquement vidé et le journal inscrit `SCREEN_PAGE_RESET ... program_preserved=1`. Les variables/programmes ne sont pas touchés. Une sortie trop longue pour 25 lignes (ex. `LIST` de 100 lignes) est **clippée sans déborder**, diagnostic `SCREEN_FULL_OUTPUT_CLIPPED` sur UART ; le prochain prompt pagine. Cela n'est **ni un scrolling** ni une pagination CPC fidèle.
- **`!CLS`** : commande hôte pour effacer uniquement le TFT ; n'est pas transmise à BASIC et ne modifie ni programme ni variables.
- **`!DEMO`** : commande hôte qui effectue `NEW`, quatre saisies BASIC HW4-C1 et `RUN` ; elle **remplace le programme courant**, ce qui est volontairement annoncé.
- `RUN` : 256 pas `bsr_step()` maximum ; à la limite, `bsr_stop()`, `BSR_STEP_BUDGET_EXCEEDED` et diagnostic `ERROR` **hôte** (pas code d'erreur CPC). Erreur d'exécution : `BSR_STEP_FAIL`, arrêt conservateur, récupération de l'interface. `LIST` est plafonné au buffer de sortie BASIC existant de 4096 octets. Les erreurs `BSR/BS/BT/BP/BL/BE` sont reportées en valeurs de diagnostics internes, jamais présentées comme `ERR` CPC.

## Test console prévu sur vrai CYD

Après CI entièrement verte, employer le **SHA final de la PR** (ne pas flasher `main` par erreur), dans un nouveau worktree :

```bash
git fetch origin
git worktree add --detach ../loco-hw4c2 <FULL_PR_HEAD_SHA>
cd ../loco-hw4c2/firmware/esp32_loco
git rev-parse HEAD
idf.py set-target esp32
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```

Saisir manuellement au terminal, via un moniteur permettant l'envoi brut CR ou LF :

```basic
10 A%=2
20 B%=A%+3
30 PRINT B%
40 END
RUN
LIST
NEW
LIST
!DEMO
!CLS
```

Vérifier `PRINT_BYTES length=4 hex=2035200a`, `BSR_END`, `LIST_BYTES` provenant du core, `NEW` puis `LIST` vide, corrections BS/DEL (tester une lettre erronée puis BS), ligne malformée volontaire, saturation de l'écran et état mémoire/DMA. **Attention : `idf.py monitor` utilise habituellement Ctrl+] pour sortir ; selon la configuration du terminal il peut traiter Backspace localement ou envoyer 0x08 / 0x7f.** Employer un vrai terminal série approprié s'il n'envoie pas les octets bruts.

**Photo souhaitée** mais l'absence de photo n'est pas automatiquement couverte par la dérogation de C1. La preuve physique doit inclure journal UART, compte rendu visuel PO et SHA du firmware flashé. Les marqueurs d'exécution logiciels ne prouvent pas un essai physique.

## Architecture, budgets et gate

Deux modules C99 sans heap (`io/uart_line` et `video/cpc_uart_console`), tests Linux séparés : caractères, CRLF, effacements, 121e caractère, 100 lignes et canaris ; intégration native avec `LIST`, `RUN`, `NEW` et exact `2035200a`, échec atomique. `video/cpc_text`, `cpc_video` et anciens tests restent inchangés. Aucun buffer RGB565 plein écran, PSRAM ni second SPI ; render/send au même propriétaire (tâche principale). Seuls buffers ajoutés : `UartLine` statique et RX UART interne installé une fois au boot. `CydLcdDiagnostics` : heap libre/min/largest, pile et DMA à vérifier physiquement. Les trois images Xtensa IDF 5.5.6 doivent être compilées indépendamment, résultats `idf.py size` archivé.

**Critères à remplir avant acceptation** : tests Linux OFF/ON **51/51**, CI des trois images, validation réelle PO sur HEAD final, réserves de compatibilité documentées, revue contradictoire Pilotage. **PR non fusionnée ; HW4-C3 non autorisé.**
