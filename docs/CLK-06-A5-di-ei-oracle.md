# CLK-06-A5 — Oracle CPC6128 DI/EI sur EVERY canaux 2/3

**Mandat GO Pilotage** : https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/400  
**Nature** : phase A, acquisition CPC indépendante uniquement. Pas de code natif/CORE/firmware ni de CYD physique.  
**Base historique** : `main@ac4ff970bdcb1833bc54e600d6b6c3734b3b58eb` ; rapprochement additif avec `main@902f3abeaf6fc9244236b397ddd1f278cf545b09` (fusion #399). Branche `oracle/clk-06-a5-di-ei`. A1–A4 en lecture seule.

## Quatre programmes finis — questions, pas réponses codées

| Programme | Construction | Marqueurs imprimante |
| --- | --- | --- |
| S01 contrôle | `EI`, `EVERY 10,2`, boucle 8500, handler et `RETURN` | `PRE/POST`, `H2` et `R2` |
| S02 | `DI` avant armement ch2, fenêtres 4500/5500 autour de `EI` | `PRE/DI/EI/POST`, `H2` et `R2` |
| S03 | armement ch2 avant `DI`, deux fenêtres 4500/5500 puis `EI` | `PRE/DI/EI/POST`, `H2` et `R2` |
| S04 | `DI`, armement ch2 et ch3, fenêtres 5000/6000 puis `EI`, handlers distincts | `PRE2/3`, `DI2/3`, `EI2/3`, `POST2/3`, `ORDER` et `R2/R3` |

Tous les `DI` ont un `EI` explicite avant `END`. Les traces de handlers sont limitées aux quatre premières livraisons (S01–S03) et aux huit premières livraisons intercanaux (S04) ; **aucun compteur de livraison n'est plafonné**. `REMAIN` est appelé uniquement après les fenêtres. Les résultats numériques ne figurent pas dans le corpus.

## Mode opératoire et intégrité

```sh
python3 tools/clk_06_a5_di_ei_oracle.py --self-test
python3 tools/clk_06_a5_di_ei_oracle.py --check-sources
python3 -m unittest discover -s tests -p 'test_clk_06_a5_di_ei_oracle.py' -v
```

Le workflow isolé `.github/workflows/clk-06-a5-acquisition.yml` comprend trois jobs : négatifs HOST_ONLY, acquisition dans une image GHCR fixée, puis rejeu indépendant. Chacune des deux sessions `original/repeat` doit démarrer à partir d'un boot CPC autonome. Preuves : LIST écran/impresseur, capture RAM tokenisée, RUN écran/impresseur, logs/processus et horodatages, gate de vitesse **sans inférence de temps événementiel**, manifeste avec SHA256 et tailles, sceau hors RAW. Timeout, sortie absente, hash altéré ou session dupliquée => `UNVERIFIED`. ROM/SNA/DSK complets jamais archivés.

Pins exacts contrôlés : ROM CPC6128 `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562` ; Caprice32 commit `8c778bf072a06fb7c23b9cccd179041db7f79a52` ; cap32 SHA256 `5170b3fc68ab116e7698e6e68a742e324d0e9dbfd87eeb7b2090e13c639f73eb` ; GHCR `sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c`. Helpers CLK-03 importés en lecture seule.

Référence **ROM seulement**, non observation : BASIC `DI` `C997` appelle `KL EVENT DISABLE BD04`, BASIC `EI` `C99D` appelle `KL EVENT ENABLE BD07`; tokens RAM `DB/DC`.

## Matrice observationnelle

Les cases ci-dessous restent **UNVERIFIED** tant qu'aucun octet de la campagne et aucune capture écran n'ont été vérifiés et scellés. Une divergence entre deux sessions est classée `INCONCLUSIVE`, jamais dissimulée.

| Cas | original | repeat | Observations |
| --- | --- | --- | --- |
| S01 | NON ACQUIS | NON ACQUIS | UNVERIFIED |
| S02 | NON ACQUIS | NON ACQUIS | UNVERIFIED |
| S03 | NON ACQUIS | NON ACQUIS | UNVERIFIED |
| S04 | NON ACQUIS | NON ACQUIS | UNVERIFIED |

Aucune conclusion de priorité universelle, simultanéité, file d'attente, granularité temporelle ou compatibilité native. La classification des observations CPC se fait après inspection de l'archive authentique.

**Barrière** : ce nouveau workflow n'est pas enregistré dans le routeur OPT3 partagé en phase A. Si `UNKNOWN_OR_MISSING_WORKFLOW`, **STOP intégration**, mandat C1 à obtenir du Pilotage ; pas de waiver, ni modification de `tools/ci/opt3_routing.py`, CI-ARCH ou route numérique. La PR doit rester DRAFT, non fusionnée. **CYD : ON_DEVICE_NOT_APPLICABLE_A5**.
