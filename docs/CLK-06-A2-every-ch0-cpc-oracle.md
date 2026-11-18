# CLK-06-A2 — Oracle CPC6128 EVERY, canal 0

**Mandat :** [GO Pilotage #314 / 6982929276](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/314#issuecomment-6982929276). **Base :** `91cc6b0856cfb4a05fd3ef3f5e5a2bb6aa523084`. **Branche :** `oracle/clk-06-a2-every-ch0`.

## Nature des preuves

Cette branche ne contient **aucune implémentation de timer BASIC natif**. `corpus.json` et six fichiers `.bas` sont **des entrées expérimentales**, jamais des résultats CPC. `tools/clk_06_a2_oracle.py` est dérivé de la méthode A1, mais indépendant et borné au namespace A2 : ROM et exécutable Caprice32 vérifiés SHA-256, build GHCR verrouillé par digest, deux suites de processus isolées, écran LIST et impression `LIST #8`, RAM tokenisée extraite d'une SNA éphémère, écran RUN, octets originaux d'imprimante, commandes, horodatages, garde CPC TIME/hôte, inventaire SHA-256 et sceau externe. Les SNA/ROM ne sont pas archivées. Le second job refait le contrôle à partir d'un sceau **extérieur** au ZIP de preuves.

**Attention :** un résultat `RAW_REPLAY_PASS` prouve la cohérence de fichiers bruts, pas l'exactitude visuelle de leurs captures ni les comportements de `EVERY`. Une inspection humaine des PNG de boot, LIST, RUN et du diagnostic négatif ainsi qu'une confrontation byte-exact des imprimantes et des deux sessions sont obligatoires avant tout `OBSERVED`.

## Matrice des six hypothèses à falsifier

| Sondage | Question | Garde de fin | Statut initial |
| --- | --- | --- | --- |
| E01 | Deux livraisons ou plus, handler RETURN, reprise du principal | FOR 8000 ; REMAIN(0) final | UNVERIFIED |
| E02 | Période 40 vs 10 de E01, sans supposer les unités | FOR 11000 ; REMAIN(0) final | UNVERIFIED |
| E03 | REMAIN(0) immédiat et absence d'événements ultérieurs | FOR 8500 ; observation témoin E01 | UNVERIFIED |
| E04 | Réarmement même canal de EVERY 5 à EVERY 20, deux handlers | FOR 8500 ; REMAIN(0) final | UNVERIFIED |
| E05 | EVERY 5 suivi de AFTER 15 sur canal 0, deux handlers | FOR 8500 ; REMAIN(0) final | UNVERIFIED |
| E06 | EVERY -1,0 ; diagnostic et ligne imprimés par CPC | Terminaison par erreur ou END | UNVERIFIED |

## Mode opératoire

```sh
python3 tools/clk_06_a2_oracle.py --self-test
python3 tools/clk_06_a2_oracle.py --check-sources
python3 -m unittest discover -s tests -p 'test_clk_06_a2_oracle.py' -v
# Acquisition : workflow clk-06-a2-acquisition.yml (Caprice32 ROM-backed)
# Rejeu : python3 tools/clk_06_a2_oracle.py --verify DIR --head SHA40 --seal SHA256_EXTERN
```

## Limites au moment de l'ouverture

Acquisition CPC **EN ATTENTE** ; 0/12 sessions observées et contrôlées visuellement au moment du commit initial. Aucune fréquence intrinsèque (notamment 1/50 s), priorité inter-canaux, exception, TIME natif ou comportement CYD ne peut être inférée des sources ni du listing ROM. `ON_DEVICE_NOT_APPLICABLE_A2`. Les fichiers historiques A1/CLK-03 sont en lecture seule et ne doivent être ni retouchés ni rescéllés. Les verdicts finaux et liens de CI seront rapportés sur la PR au SHA réel après exécution.
