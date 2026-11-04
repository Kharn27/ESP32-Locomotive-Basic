# HW4-DISP-PROFILE-A — C3-INT-B3 : intégration seule

## Autorité, base et périmètre

- Mandat : [Pilotage #6631162512](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/297#issuecomment-6631162512).
- Parent C3-INT : `68488bb0f3a6ffe075fdf28303f64c13247ac420` ; parent `main` J1.24-B3 : `989ec54989537a31c3a9be8074f1ce7c47708f17`.
- PR Draft #297 : aucune optimisation renderer, SPI, DMA, scheduler ou BASIC ; aucun nouvel essai physique CYD.
- Conflit de composition CMake : conservation simultanée des CTest `hw4_disp_profile_accounting`, `hw4_disp_profile_host_overhead` et `j1_24_b3_while_wend_cpc_diagnostics`. Tous les autres chemins B3 restent pris directement de `main`.
- Workflow C3 : checkout de la référence B3 immuable, compilation 2 variantes du HEAD, compilation baseline `main` B3 au même ESP-IDF **5.5.6**, assertions coût propre `≤696 o`, DRAM `≤54864 o`, IRAM `=67331 o`, flags HAL distincts, SHA binaire distinct. Pas de modification du garde A0 global.

## Budget : preuves préalables, pas résultat sur le HEAD de fusion

| Mesure | main B3 seul | C3-INT B2 précédent | C3-INT-B3 attendu (à vérifier) |
|---|---:|---:|---|
| DRAM CONSOLE | **54168 o** | 54864 o | ≤54864 o, delta ≤696 |
| IRAM utile | **67331 o** | 67331 o | 67331 o |
| SPI40/SPI20 | SPI20 base | binaires distincts | vérification sur nouvel HEAD |

Main B3 : [CI-XTENSA #41832571009](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41832571009), log CONSOLE du 04/11/2026. C3 précédent : [rapport vérifié #6614444244](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/297#issuecomment-6614444244). Une différence de baseline ELF lors de la CI C3 impose STOP et arbitrage, sans élargissement implicite. Garde A0 historique : FAIL CONSOLE +1136 o observé sur B2, autorisé exceptionnellement pour le seul périmètre C3 ; un nouveau FAIL doit être rapporté avec sa valeur effective, jamais renommé PASS.

## Traçabilité des blobs protégés

Blob du renderer MODE0/1/2 `video/cpc_video.c` : `9e22ecb70f1ab213a7ef649dff6eb2d36cc1c8dd` (identique entre les deux parents). Blobs C3 repris **tels quels** de l'ancien HEAD : HAL `firmware/components/cyd_ili9341/cyd_ili9341.c` `0565c660b80d0d956ac44764014487a8e757457a`, console `firmware/esp32_display_probe/main/hw4_c2_console.c` `1a1d8c322f7df6d552b4612cdae343ec2d66bcd5`, profiler `video/hw4_disp_profile.c` `255f736c2e6fc96ada77353660ab64939c5767dc`, `video/hw4_disp_profile.h` `8c9a4801f1a92a855816063df1f6610bee78236a`. Blobs B3 repris de `main` sans retouche : `io/cpc_diag_policy.c` `0b0fb75154a381f4622bd7d1c9df1260466e5529`, `io/cpc_diag_policy.h` `433a515c9ebbed22dcdafd58df271bad5b6648db`, `integration/hw4_run_diag_source.h` `ef8ac006f47eb429e0e0a4c8888a13b22e304767`, `tests/test_j1_24_b3_while_wend_diagnostics.c` `37b8df0a17c516553dbf3c449ee94cc816d25b65`.

## Preuves requises au nouveau HEAD

GitHub Actions : C99 GCC/Clang ± ASan/UBSan (incluant B2/B3), ARCH, OPT3, CPC-PERMANENT, HW4-EDIT-P1, HW4-C3-B2, Xtensa 3/3 avec ABI, C3 deux variantes SPI40/SPI20 et garde A0 historique honnêtement déclaré. L'intégration seule ne revendique **aucun PASS avant résultat réel des CI** : les liens, le SHA final et les valeurs effectivement obtenues doivent être transmis au Pilotage dans la remise GitHub de #297.

## Réception physique

Le PO a confirmé `ON_DEVICE_PO_REPORTED_PASS_UART_AND_SCROLL_IMPROVED` **uniquement pour `68488bb0f3a6ffe075fdf28303f64c13247ac420`**, [verdict Pilotage](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/297#issuecomment-6631162512). Le HEAD C3-INT-B3 n'a pas été flashé ; **ON_DEVICE_UNVERIFIED**, aucun reflash autorisé. Seul le Pilotage décide de la fusion, puis du mandat RENDER-A.
