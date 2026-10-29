# HW4-DIAG-A — A0 CPC diagnostics de suppression

Mandat du Pilotage : [issue #159](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/159#issuecomment-6499793123). Base réellement vérifiée : `main@6699b828b4526aa707d67eb32871b0dcb5342b36`. PR #162 REAL5 parallèle : aucune modification du `core/`.

## Règle de preuve

**A0 uniquement tant que les PNG indépendants ne sont pas acquis et inspectés.** La trace matérielle PO de `10` absent et le désassemblage ROM ne remplacent pas la capture. L'acquisition `tools/hw4_diag_a_cpc.py` reprend le Caprice32/ROM 6128/GHCR épinglés de HW4-READY-A, avec **un répertoire distinct** `tests/fixtures/cpc6128/hw4_diag_a/`. Deux démarrages indépendants pour chaque séquence, PNG original et répété, journal, saisie exacte et SHA-256. Jamais de décodage imprimante présenté comme image écran.

| Cas | Séquence clavier | Diagnostic CPC | Ready et curseur | Programme | Classification |
| --- | --- | --- | --- | --- | --- |
| D01 | `10` absent | à inspecter | à inspecter | à inspecter | NON TESTÉ |
| D02a | `10 PRINT 2` puis `10` | à inspecter | à inspecter | suppression à vérifier | NON TESTÉ |
| D02b | mêmes puis `LIST` | à inspecter | à inspecter | vide à vérifier | NON TESTÉ |
| D03 | `NEW` puis `10` | à inspecter | à inspecter | à inspecter | NON TESTÉ |
| D04 | `10 ` avec espace final | à inspecter | à inspecter | à inspecter | NON TESTÉ |
| D05 | `GOTO 999` direct | à inspecter | à inspecter | à inspecter | NON TESTÉ |
| Contrôles | `LIST` vide, `10 PRINT 2`+`LIST`, `NEW`+`LIST` | à inspecter | à inspecter | à inspecter | NON TESTÉ |

**Barrière :** si `10` absent ne montre pas `Line does not exist` authentique, arrêter après A0 et demander arbitrage Pilotage. L'adaptateur natif ne convertira jamais des valeurs `BSR`/`BS` en numéros d'erreur CPC.
