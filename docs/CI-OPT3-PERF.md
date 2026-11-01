# CI-OPT3-PERF-A — latences observées et protocole reproductible

**Mandat :** [issue #176](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/176), [décision Pilotage](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/176#issuecomment-6529805847).
**Données réelles :** [snapshot figé](./CI-OPT3-PERF-REAL-20261030.json), GitHub REST Actions. **Coupure** 2026-10-29 18:51:11Z (merge #175) ; **borne haute inclusive des créations de runs** 2026-10-30 17:40:00Z. 286 runs de `pull_request`, 41 HEADs distincts, 8 numéros de PR retrouvés et 5 SHA non résolus. Toutes les conclusions et les HEADs remplacés restent dans le corpus.

## Résultat (nearest-rank)

Pour n valeurs triées, `P(p)=valeurs[ceil(p*n)-1]`. Départ du HEAD = plus petit `created_at` des workflows du SHA ; arrivée = dernier `jobs[].completed_at` de la tentative finale lorsque les jobs sont connus, sinon **`updated_at` comme proxy API signalé**. Le maximum des dates de verdict (pas une somme des couloirs parallèles) termine le HEAD. **Les couloirs parallèles ne sont pas additionnés**. Durées secondes entières avant arrondi décimal.

| Cohorte | N | P50 (min) | P95 (min) | Max (min) |
|---|---:|---:|---:|---:|
| Tous les HEADs terminés, incidents inclus | 41 | 2.70 | 4.42 | 916.47 |
| HEADs terminés, hors deux incidents sans jobs (diagnostic ordinaire) | 39 | 2.67 | 3.87 | 4.42 |
| SUCCESS seulement (secondaire / biais de sélection) | 20 | 2.65 | 3.42 | 4.42 |

**Interprétation :** le P95 descriptif ordinaire est 3.87 min, mais `PERF_NOT_YET_VERIFIED`. Il existe 8 PR identifiées et non 41 PR indépendantes ; certains SHA sont corrélés et le mélange de diffs n'est pas apparié à la baseline. La fenêtre inclut des échecs et annulations. L'objectif indicatif `P95 < 5 min` paraît compatible avec le sous-ensemble hors incidents mais **n'est pas certifié** ; un HEAD hors incidents sans jobs prend jusqu'à **4,42 min** dans ce snapshot. Aucune revendication numérique de gain global avant/après.

## Familles — runs terminés, non filtrés par SUCCESS, incidents no-jobs >1h isolés

| Famille | N runs | P50 min | P95 min | Max min | Conclusions observées (y compris incidents) |
|---|---:|---:|---:|---:|---|
| ARCH | 39 | 0.20 | 0.53 | 0.55 | success 38, failure 3 |
| C99 | 39 | 1.15 | 1.53 | 2.85 | success 32, failure 6, cancelled 3 |
| CPC acquisition | 10 | 0.02 | 1.48 | 1.48 | skipped 9, failure 1 |
| CPC indépendant | 21 | 1.35 | 1.53 | 1.62 | success 21, failure 2 |
| CPC permanent | 39 | 0.75 | 2.67 | 2.70 | success 32, cancelled 5, failure 4 |
| HW4 autres | 48 | 0.50 | 0.95 | 1.38 | success 42, failure 4, cancelled 2 |
| HW4 mémoire A0 | 15 | 3.17 | 4.38 | 4.38 | success 9, failure 6 |
| Routeur | 39 | 0.17 | 0.68 | 1.23 | success 37, cancelled 1, failure 3 |
| Xtensa | 26 | 2.63 | 3.87 | 4.42 | success 16, cancelled 10 |

**Attention :** chaque ligne est une distribution **de runs**, pas une latence PR. Les acquisitions `CPC acquisition` (workflow historique, y compris `SKIPPED`) sont **hors circuit SLA PR ordinaire** ; aucun `SKIPPED` ne constitue une acquisition ROM ni un `PASS`. Les protections CPC permanentes et la comparaison indépendante sont deux familles différentes.

## 41 HEADs réels — sélection exhaustive par création dans la fenêtre figée

| PR | SHA HEAD | Runs / preuve GitHub | Verdict | Durée murale (min) | Révision / réserve |
|---|---|---:|---|---:|---|
| [#178](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/178) | [`69a4d3bbdd3e`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/69a4d3bbdd3e82013c8dbd230f9c201b546cbaa6) | 4 · [run 40955018377](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40955018377) | SUCCESS | 1.10 | — |
| NON RÉSOLUE | [`665d64609768`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/665d64609768f7385145d0fccf56facbaa678253) | 6 · [run 40955825360](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40955825360) | FAILURE | 1.48 | — |
| [#179](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/179) | [`0209af531884`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/0209af531884b91195b8d8c715658c397f1a948a) | 5 · [run 40956147674](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40956147674) | CANCELLED | 1.38 | OLD_HEAD; OLD_HEAD_CANCELLED |
| [#179](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/179) | [`a249eae3c81f`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/a249eae3c81f63d571bdef5bdb3ac7aeac24ac8c) | 5 · [run 40956293259](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40956293259) | SUCCESS | 1.80 | OLD_HEAD |
| [#179](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/179) | [`0f8d7e42f5c4`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/0f8d7e42f5c4cdb79964910d7271702cd289beed) | 5 · [run 40956551131](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40956551131) | FAILURE | 86.87 | OLD_HEAD; INCIDENT_NO_JOBS |
| [#179](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/179) | [`84104cfc394d`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/84104cfc394d17ba88f1ecd606ad4604bc7bb5e2) | 5 · [run 40957317695](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40957317695) | FAILURE | 1.35 | OLD_HEAD |
| [#179](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/179) | [`ba44651abac3`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/ba44651abac31321ec71901d3e245709f86cc14a) | 5 · [run 40957503697](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40957503697) | SUCCESS | 1.43 | OLD_HEAD |
| [#181](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/181) | [`08534b40d60b`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/08534b40d60b9a40b869aaa81eb1807f6c449a36) | 5 · [run 40961165128](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40961165128) | SUCCESS | 2.45 | — |
| NON RÉSOLUE | [`2837311a5ae9`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/2837311a5ae97d5096025c42d004932f24b1be23) | 5 · [run 40961285195](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40961285195) | SUCCESS | 2.65 | — |
| [#179](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/179) | [`ecca2dd9985c`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/ecca2dd9985c66ac7d6e258ab394873313d33632) | 5 · [run 40966335108](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40966335108) | SUCCESS | 1.47 | OLD_HEAD |
| [#179](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/179) | [`98a2d6169117`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/98a2d61691170b6f74f8cbf6df5054986c49c937) | 5 · [run 40966784599](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40966784599) | SUCCESS | 1.45 | — |
| [#184](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/184) | [`fad64a0cb257`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/fad64a0cb2572e9c2bc69802eb75a2c3488beed0) | 8 · [run 40966824828](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40966824828) | CANCELLED | 3.12 | OLD_HEAD; OLD_HEAD_CANCELLED |
| [#184](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/184) | [`ef32ca4672b3`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/ef32ca4672b3f9f1dd381f83e9cb6e3ffd08614a) | 8 · [run 40967139904](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40967139904) | SUCCESS | 3.17 | OLD_HEAD |
| [#184](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/184) | [`e710380a7843`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/e710380a7843576660858eb5782678a95052bfb8) | 8 · [run 40968902648](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40968902648) | SUCCESS | 3.07 | — |
| [#186](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/186) | [`6d3267e4bd10`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/6d3267e4bd107565cf13fafc5b2b35583fde08be) | 9 · [run 40969758630](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40969758630) | SUCCESS | 2.50 | OLD_HEAD |
| [#186](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/186) | [`b7936fdcf141`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/b7936fdcf141dc03ed6bfa9c32d0d2059132dd60) | 9 · [run 40970223571](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40970223571) | SUCCESS | 2.40 | — |
| NON RÉSOLUE | [`0381d3ffbafb`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/0381d3ffbafb2fcde8885bf3d8f623efda63f7aa) | 9 · [run 40970245914](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40970245914) | CANCELLED | 2.10 | — |
| NON RÉSOLUE | [`3c6a91af47f0`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/3c6a91af47f0a7fdb0161dabe357cdfbc302f249) | 9 · [run 40970416341](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40970416341) | CANCELLED | 3.10 | — |
| NON RÉSOLUE | [`e5d7f26a0813`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/e5d7f26a08130b3bc6e24bcb6678d2b9b58e78d9) | 9 · [run 40970786281](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40970786281) | SUCCESS | 2.80 | — |
| [#190](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/190) | [`4d18b9e8216f`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/4d18b9e8216fb18529c513a6f63d4bf85a8ede78) | 8 · [run 40973263013](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40973263013) | FAILURE | 3.03 | OLD_HEAD |
| [#190](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/190) | [`a70727177b56`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/a70727177b566d971cf11913ff99dbf25a8e2ea6) | 8 · [run 40973400066](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40973400066) | FAILURE | 3.17 | OLD_HEAD |
| [#191](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/191) | [`54441839655a`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/54441839655ac68081dd032c8b8c356016bca8ad) | 5 · [run 40973623408](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40973623408) | FAILURE | 2.07 | OLD_HEAD |
| [#190](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/190) | [`ae3a98b37a7b`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/ae3a98b37a7bef0383d21e02de2d937e97626f59) | 8 · [run 40973939941](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40973939941) | SUCCESS | 3.05 | OLD_HEAD |
| [#191](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/191) | [`6e9b17b8d545`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/6e9b17b8d545a57ef3942f217c9b4d3daeae8c38) | 5 · [run 40974044447](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974044447) | SUCCESS | 2.70 | OLD_HEAD |
| [#191](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/191) | [`0d4214fdc467`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/0d4214fdc4670dcdaa36f7704fe692b92d43d963) | 5 · [run 40974350096](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974350096) | FAILURE | 916.47 | OLD_HEAD; INCIDENT_NO_JOBS |
| [#191](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/191) | [`c1eb80075cbf`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/c1eb80075cbf4694a54989927a4463afd4499134) | 5 · [run 40974559320](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974559320) | CANCELLED | 2.67 | OLD_HEAD; OLD_HEAD_CANCELLED |
| [#191](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/191) | [`c24cd70ef45e`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/c24cd70ef45ececce1acf1261a805a922abca7a3) | 5 · [run 40974733322](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974733322) | CANCELLED | 2.47 | OLD_HEAD; OLD_HEAD_CANCELLED |
| [#191](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/191) | [`431ddc242898`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/431ddc242898c5798a19277bc182a0ca2d5c45d3) | 5 · [run 40974942629](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974942629) | SUCCESS | 2.62 | — |
| [#190](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/190) | [`64d3a7103ee9`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/64d3a7103ee96bb0ca56542f745077ecce6afea4) | 8 · [run 41079136616](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41079136616) | FAILURE | 3.25 | OLD_HEAD |
| [#193](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/193) | [`4083eefe1e54`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/4083eefe1e543b68b654034dfd93997385351379) | 9 · [run 41079338931](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41079338931) | CANCELLED | 1.90 | OLD_HEAD; OLD_HEAD_CANCELLED |
| [#190](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/190) | [`4f6ed248c9c6`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/4f6ed248c9c6ff6a75154c481a4a005d5b82f4d6) | 8 · [run 41079516335](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41079516335) | FAILURE | 3.27 | OLD_HEAD |
| [#193](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/193) | [`f7be14c10a8f`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/f7be14c10a8f8a9af79f8e63d77d0c81a23744fa) | 9 · [run 41079523143](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41079523143) | CANCELLED | 1.62 | OLD_HEAD; OLD_HEAD_CANCELLED |
| [#193](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/193) | [`b412c0d59f85`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/b412c0d59f8526ecaeb03ff94ab9c7c41ce87cdb) | 9 · [run 41079608071](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41079608071) | SUCCESS | 3.08 | OLD_HEAD |
| [#190](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/190) | [`17ccd33b45df`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/17ccd33b45df337e267b0540699bb8a27f06605d) | 8 · [run 41079673532](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41079673532) | FAILURE | 3.87 | OLD_HEAD |
| [#190](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/190) | [`061a62473db6`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/061a62473db620f30889b334351d7315437a7ce9) | 8 · [run 41080231142](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41080231142) | FAILURE | 3.25 | OLD_HEAD |
| [#193](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/193) | [`466ea422e8a5`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/466ea422e8a5a4eaedec00875acea1a783bb4c14) | 9 · [run 41080446427](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41080446427) | SUCCESS | 2.67 | — |
| [#190](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/190) | [`d165c375a2fe`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/d165c375a2fece2a6178b975162a6bf3aca47c61) | 8 · [run 41081507189](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41081507189) | SUCCESS | 3.15 | OLD_HEAD |
| [#190](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/190) | [`4fbd3c108257`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/4fbd3c108257ee046acaef68eda4d2e927dfa565) | 8 · [run 41085303434](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41085303434) | FAILURE | 3.18 | OLD_HEAD |
| [#190](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/190) | [`9f742420ea0d`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/9f742420ea0d8bde7abf2627c3d322d8f155ef07) | 8 · [run 41085425262](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41085425262) | SUCCESS | 3.42 | OLD_HEAD |
| [#190](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/190) | [`b73040b292e5`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/b73040b292e57e3a0149a618ba2abf996eeec75a) | 8 · [run 41099340483](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41099340483) | FAILURE | 3.10 | OLD_HEAD |
| [#190](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/190) | [`3d504de90c20`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/3d504de90c20b499e2a782688ab69508c274bee4) | 8 · [run 41099638924](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41099638924) | SUCCESS | 4.42 | — |

## Queue, tentatives, reruns, données manquantes

- Les dates `created_at`, `run_started_at`, `updated_at`, `run_attempt`, SHA, chemins et conclusions sont conservées **par run** dans [la source JSON réelle](./CI-OPT3-PERF-REAL-20261030.json). Si `jobs` est absent de l'objet, **non acquis** (ne pas interpréter comme zéro). `jobs: []` est exclusivement utilisé ici pour les **dix runs** dont l'API jobs a été effectivement interrogée.
- [HEAD 0f8d7e42f5c4](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/0f8d7e42f5c4cdb79964910d7271702cd289beed) : cinq workflows `FAILURE`, durée proxy 5 212 s (**1 h 26 min 52 s**) ; **0 job dans les cinq réponses API**. [Exemple run 40956551131](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40956551131).
- [HEAD 0d4214fdc467](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/0d4214fdc4670dcdaa36f7704fe692b92d43d963) : cinq workflows `FAILURE`, durée proxy 54 988 s (**15 h 16 min 28 s**) ; **0 job dans les cinq réponses API**. [Run 40974350096](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974350096), [40974350095](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974350095), [40974350098](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974350098), [40974350079](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974350079), [40974350124](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974350124). Cause précise inconnue : **pas 15 h de compilation**.
- [Échec A0 #190, run 41080231240](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41080231240) : trois jobs `base-vs-head`, démarrés 3 s après leur création, fin CONSOLE à 15:26:18Z avec FAILURE, les deux autres SUCCESS ; la comparaison compile **base historique et HEAD pour trois profils (six images)**. C'est un contrôle mémoire absolu distinct de la réussite Xtensa ; budget inchangé.
- [A0 succès ultérieur, run 41099638924](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41099638924) : trois jobs SUCCESS, files de 2–3 s ; job HW3 terminé à 17:36:23Z. Ces trois jobs **s'exécutent en parallèle**. Le dernier `completed_at` est **17:36:23Z**, tandis que le run n'a été actualisé qu'à **17:38:08Z**, soit **105 secondes** de décalage GitHub. Le moteur mesure donc **263 s (4,38 min)** pour ce run, et non 368 s (6,13 min).
- [C99 J1.18-B, run 41080446207](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41080446207) : quatre jobs Linux SUCCESS ; files `started_at - created_at` de **4, 11, 11 et 24 secondes** (P95 nearest-rank = 24 s). File ≠ temps de compilation.
- Les relances sont distinguées par `run_attempt` ; l'outil live charge les tentatives et jobs par `/actions/runs/{id}/attempts/{n}/jobs`. Le snapshot fige seulement certains jobs vérifiés, **et n'est pas une preuve exhaustive des queues/reruns**. La réacquisition live authentifiée est nécessaire pour une distribution complète. Pour un rerun, le temps mur du HEAD reste calculé depuis la création initiale ; **le temps d'attente de la dernière tentative** part de son propre `run_started_at` vérifié par tentative, sinon de son premier `job.created_at` (borne conservatrice, signalée par `workflow_wait_reference`). Jamais de `run.created_at` historique converti en une heure d'attente de runner.

## Avant / après, comparabilité et classification de diff

**Avant CI-OPT3 :** [baseline versionnée](./CI-OPT3-five-family-routes.md) sur **20 runs C99 SUCCESS présélectionnés**, P50 **1,25 min**, P95 **3,82 min**, max **5,13 min**, mesurés uniquement par `updated_at-created_at`. Elle n'échantillonne ni les annulations ni le chemin critique global PR.

**Après CI-OPT3 :** le présent corpus a 41 HEADs terminés (seulement 20 HEADs classés SUCCESS si l'on exclut les deux incidents), dont plusieurs révisions de mêmes PR (#190, #193 et autres). Des HEADs anciens ne peuvent pas être classés honnêtement par les fichiers **actuels** de la PR ; l'outil attribue `UNKNOWN_REVISION` sauf concordance HEAD exact. Une classe de diff et une population pré/post de 20 HEADs *appariés* ne sont pas établies. **Aucun pourcentage de réduction global n'est calculable sans biais démontré.**

**CPC historique :** les acquisitions ROM/Caprice32 spécialisées et leurs `SKIPPED` restent comptées hors SLA ; aucune archive, SHA scellé, falsification ou critère de preuve n'a été modifié par cet audit. Ceci **ne constitue pas** une nouvelle exécution d'oracle CPC.

## Reproduction locale (stdlib, API GET uniquement)

**Contrôle C1 du snapshot :** 41 HEADs P95 = **4,42 min**, 39 HEADs hors incidents max = **4,42 min**, 20 HEADs SUCCESS max = **4,42 min** ; 15 runs mémoire A0 P95 = **4,38 min**. Les tests `test_frozen_real_*` recomputent ces assertions via le générateur. Le snapshot reste identique et traçable.

```bash
python3 -m unittest discover -s tests -p 'test_opt3_perf_report.py' -v
python3 tools/ci/opt3_perf_report.py \
  --input docs/CI-OPT3-PERF-REAL-20261030.json \
  --output /tmp/ci-opt3-perf-offline.md
GITHUB_TOKEN=... python3 tools/ci/opt3_perf_report.py \
  --through 2026-10-30T17:40:00Z --max-pages 30 \
  --snapshot-out /tmp/ci-opt3-perf-fresh.json --output /tmp/ci-opt3-perf-fresh.md
```

`GITHUB_TOKEN` est **lu en mémoire**, n'est pas imprimé ni sérialisé ; ne jamais enregistrer sa valeur dans un rapport. L'extraction live pagine le REST GitHub, parcourt les SHA non associés à une PR par `commits/{sha}/pulls`, relit les tentatives, jobs et fichiers des PR. Les endpoints sont en **GET**, aucun lancement ni rerun. GitHub peut limiter les requêtes (notamment sans auth), les PR disparues peuvent rendre l'association impossible, et `updated_at` peut être postérieur à la vraie fin d'un job. Une borne de pages incomplète provoque une erreur plutôt qu'un échantillon silencieusement tronqué. La reproduction live peut diverger du snapshot figé si GitHub met à jour des métadonnées de runs ou la cartographie PR.

**Exclusions tenues :** aucun changement `core/`, `firmware/`, `video/`, `io/`, `hal/`, `integration/`, sceaux CPC, `CMakeLists.txt`, `.github/workflows/`, routes `opt3_routing.py` ou budget A0. Aucun contrôle de performance ajouté à la CI. Pas de test physique CYD pertinent (`ON_DEVICE_NOT_APPLICABLE`).

**Statut proposé à Pilotage :** `PERF_NOT_YET_VERIFIED` — outil et données audités, cohorte non indépendante et baseline globale manquante. Demander un nouveau mandat ciblé si l'analyse future de cohorts appariées confirme une régression ; ne pas modifier les gates ici.


---

## Actualisation PERF-A — deuxième fenêtre authentique du 1er novembre 2026 (mandat du 2 novembre)

**Base GitHub de cette actualisation :** `main@f3d11eb8a8723a85f08bb5317852a594780c831a`. La [PR historique #196](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/196) avait déjà fusionné le premier audit ; le snapshot permanent des **41 HEADs du 30 octobre** ci-dessus reste intact. Ce complément **n'écrase pas** ses résultats ni ses oracles.

**Acquisition reproductible :** GitHub REST `GET /repos/Kharn27/ESP32-Locomotive-Basic/actions/runs?event=pull_request&created=2026-11-01&per_page=100&page=N` : pages de **100, 100, 43 runs** (la troisième page ferme exhaustivement la journée), soit 243 exécutions. Coupure descriptive **`2026-11-01T23:15:26Z`** : 235 runs créés avant cette date, couvrant **44 HEADs SHA** ; sélection des **40 HEADs les plus récents par premier `run.created_at`**, en conservant **tous** leurs runs des cinq couloirs et leurs échecs/annulations. Les quatre autres HEADs, antérieurs dans la journée, ne sont pas annulés/supprimés de GitHub : la limite de fenêtre de 40 est explicite. Aucune donnée synthétique dans les chiffres ci-dessous.

La latence murale observée pour un HEAD est `max(run.updated_at) - min(run.created_at)` **entre les workflows des cinq couloirs parallèles**. Les travaux historiques `CPC_ACQUISITION` et les jobs mémoire optionnels sont **en dehors de cette projection à cinq couloirs** ; le générateur général existant les conserve et les sépare si déclenchés. `updated_at` est un **proxy API**, non une preuve de fin réelle du dernier job ; le mode complet du script calcule, lorsque les jobs sont accessibles, la borne par `jobs[].completed_at`. Aucune durée parallèle n'est additionnée.

### Population et percentiles (nearest-rank, bornée aux 40 HEADs)

| Mesure | N | P50 | P95 | Maximum |
|---|---:|---:|---:|---:|
| Fenêtre cinq couloirs, **tous les HEADs terminés** : 13 succès, 20 annulations, 7 échecs | 40 | 2.00 min | 3.00 min | 3.35 min |
| Même cohorte, **succès observés uniquement** (vue *biaisée*, jamais échantillon primaire) | 13 | 2.47 min | 3.35 min | 3.35 min |

Les annulations raccourcissent artificiellement la fenêtre des HEADs remplacés ; **la P50/P95 « tous verdicts » n'est donc pas le temps nécessaire pour obtenir une validation verte**. La sous-cohorte verte n'est pas représentative. Les 40 HEADs ne correspondent qu'à **5 numéros de PR retrouvés**, plus **5 SHA sans association PR déterminée** ; ils ne représentent **pas 40 PR indépendantes**. Parmi les HEADs, les PR #237/#239/#243/#247 contiennent plusieurs révisions corrélées. Les mappings manquants ont été vérifiés par `GET /commits/{sha}/pulls` lorsque les métadonnées de run étaient vides ; le défaut d'association reste étiqueté.

### Durées des workflows par famille, seulement quand le run est SUCCESS (secondaire, biais de sélection)

| Famille | N | P50 (s) | P95 (s) | Maximum (s) | Non déclenchée parmi 40 |
|---|---:|---:|---:|---:|---:|
| C99 | 22 | 76 | 90 | 93 | 0 |
| CPC_PERMANENT | 18 | 145 | 160 | 160 | 0 |
| ARCH | 39 | 11 | 15 | 20 | 0 |
| ROUTER | 36 | 10 | 12 | 12 | 0 |
| XTENSA | 9 | 162 | 201 | 201 | 17 |

Ces mesures sont les **durées de runs individuels**, pas les latences complètes des PR. `XTENSA NOT_TRIGGERED` sur 17 HEADs n'est pas un succès du build ESP32 ; il s'agit d'un couloir filtré par chemins. Les workflows CPC indépendants et les acquisitions ROM sont distincts du permanent, et un job d'acquisition SKIPPED ne constitue jamais un oracle acquis.

### Inventaire de 40 HEADs réels — liens immuables

| # | HEAD exact (lien commit) | PR connue | Verdict observé | Mur (min) | Run C99 témoin |
|---:|---|---|---|---:|---|
| 1 | [`0d3cb23d7ecd`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/0d3cb23d7ecd37c161594269e409ad63ee708769) | [#247](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/247) | SUCCESS_OBSERVED | 2.40 | [41361207485](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41361207485) |
| 2 | [`0a0a5e4a1ba1`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/0a0a5e4a1ba129203447a9e3b6c3ba03cbc127c0) | [#247](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/247) | SUCCESS_OBSERVED | 3.35 | [41359560976](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41359560976) |
| 3 | [`0365ac7eb19a`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/0365ac7eb19afeb7977c09bf51e9148ba26d6169) | [#247](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/247) | CANCELLED | 2.75 | [41359400928](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41359400928) |
| 4 | [`e05837655aba`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/e05837655aba964cf1324129e41dc72d8a0237ad) | [#247](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/247) | CANCELLED | 2.63 | [41359219667](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41359219667) |
| 5 | [`c1f8fc0daafa`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/c1f8fc0daafa57069dafa3f38c8ee831afcd2159) | [#247](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/247) | CANCELLED | 2.00 | [41359100785](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41359100785) |
| 6 | [`dd5f8293589f`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/dd5f8293589f97a1dd53d115967743ac9af16fd0) | [#247](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/247) | CANCELLED | 1.77 | [41358984167](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41358984167) |
| 7 | [`4900ec734196`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/4900ec734196c6f1060ed95f5dd11d0879e728aa) | [#247](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/247) | CANCELLED | 0.53 | [41358963627](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41358963627) |
| 8 | [`78b6f40b1276`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/78b6f40b1276e5bc9c4c4d31768271e0a314d3d5) | [#247](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/247) | FAILURE | 2.45 | [41358818183](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41358818183) |
| 9 | [`e60879f7b4e2`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/e60879f7b4e2178d69f6d3110ff1c3796fa01365) | [#226](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/226) | SUCCESS_OBSERVED | 3.07 | [41358415744](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41358415744) |
| 10 | [`f00cc60c8918`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/f00cc60c891868e28fa67d2d4331d5fac3f5e23e) | [#226](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/226) | FAILURE | 1.88 | [41358283470](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41358283470) |
| 11 | [`97a46f894815`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/97a46f894815c0314bf8d3ca9538e50565f628c4) | PR non résolue | SUCCESS_OBSERVED | 2.70 | [41357623345](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41357623345) |
| 12 | [`0b87ff09e8be`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/0b87ff09e8becfc8400bdd4f69643100e91c2567) | [#243](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/243) | SUCCESS_OBSERVED | 2.43 | [41357560761](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41357560761) |
| 13 | [`1a2a17f8463e`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/1a2a17f8463e5746f2c469a393a0cec32c07bbe3) | PR non résolue | SUCCESS_OBSERVED | 2.42 | [41259593475](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41259593475) |
| 14 | [`7b1018bb01c4`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/7b1018bb01c4f41432df1c4d130604f1fff3f2b5) | [#243](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/243) | SUCCESS_OBSERVED | 2.47 | [41259566349](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41259566349) |
| 15 | [`da5f12ae6e2a`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/da5f12ae6e2ac05d63dbd4be54b7cdc29ab08f53) | [#243](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/243) | SUCCESS_OBSERVED | 2.87 | [41259329963](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41259329963) |
| 16 | [`6bf3ae02e5cc`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/6bf3ae02e5cc0d3d3b59c7cf5b46021edbfe0c9e) | [#237](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/237) | SUCCESS_OBSERVED | 2.55 | [41259248152](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41259248152) |
| 17 | [`972cd94258f2`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/972cd94258f27f203bd16976e0dfd9a03604d0c3) | [#237](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/237) | CANCELLED | 0.88 | [41259199281](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41259199281) |
| 18 | [`dd1c1e3bf651`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/dd1c1e3bf651ae79e3f17e18091a645febc3b584) | [#237](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/237) | CANCELLED | 0.62 | [41259175423](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41259175423) |
| 19 | [`a61d711b5b9f`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/a61d711b5b9f48e43876879cda468d8223b6e562) | [#243](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/243) | CANCELLED | 2.38 | [41259169871](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41259169871) |
| 20 | [`ff5e9478e7d7`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/ff5e9478e7d7b0368462a538fc27d54a7444e1b3) | [#237](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/237) | CANCELLED | 0.95 | [41259134304](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41259134304) |
| 21 | [`b583d54267ab`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/b583d54267ab938aba7ec5a8575a949d0a4a5486) | PR non résolue | FAILURE | 1.93 | [41259035101](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41259035101) |
| 22 | [`57dfce8da797`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/57dfce8da797b0ee498dc75346aef2438fc14b7d) | [#243](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/243) | CANCELLED | 2.42 | [41259032681](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41259032681) |
| 23 | [`4d79448498a7`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/4d79448498a7eb9027cd555d509f5a7579ed34b8) | PR non résolue | FAILURE | 2.38 | [41259022260](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41259022260) |
| 24 | [`b2ca7b75f88d`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/b2ca7b75f88d3a9334e9c04e088c2b7257ea5a6d) | [#237](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/237) | SUCCESS_OBSERVED | 2.43 | [41258934827](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41258934827) |
| 25 | [`a22e7258bd7f`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/a22e7258bd7fec7200b9750e54de8b092f811d25) | [#243](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/243) | FAILURE | 1.98 | [41258872929](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41258872929) |
| 26 | [`599000f3ffcc`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/599000f3ffcc877f396f5fe795a1a92a1a518721) | [#237](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/237) | CANCELLED | 1.23 | [41258849620](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41258849620) |
| 27 | [`1539d5a68f67`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/1539d5a68f672f03d828cd80cea9d8a1ee30416b) | [#239](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/239) | SUCCESS_OBSERVED | 3.00 | [41258785557](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41258785557) |
| 28 | [`9285eaa4e681`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/9285eaa4e6817dd9689a6f6a6ec03843c9f93f04) | [#239](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/239) | CANCELLED | 1.50 | [41258698383](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41258698383) |
| 29 | [`7aafffc80a5e`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/7aafffc80a5ed127618df163de00a6b22cf6c4a4) | [#239](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/239) | CANCELLED | 0.40 | [41258685892](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41258685892) |
| 30 | [`8c3599837e93`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/8c3599837e931b9c8cc381000fd962408b95a8a0) | [#239](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/239) | FAILURE | 0.55 | [41258661313](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41258661313) |
| 31 | [`49707ea3bfb2`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/49707ea3bfb201028c0beee22370ae7c88034b1a) | [#239](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/239) | CANCELLED | 1.25 | [41258589325](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41258589325) |
| 32 | [`bd297ce44bc7`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/bd297ce44bc7c1d953cf8d5d962f235276745299) | [#239](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/239) | CANCELLED | 0.35 | [41258571954](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41258571954) |
| 33 | [`3a81f4d7d2a0`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/3a81f4d7d2a0313e516e471a87fa077590da2757) | [#239](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/239) | CANCELLED | 0.82 | [41258537263](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41258537263) |
| 34 | [`661ce18e035b`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/661ce18e035bbe3abc1a2aa5e50f6b4d4861881a) | PR non résolue | FAILURE | 2.42 | [41258512263](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41258512263) |
| 35 | [`ebe0cbd4123d`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/ebe0cbd4123dd7fc725808426d25e6e467f10e46) | [#237](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/237) | SUCCESS_OBSERVED | 2.43 | [41258404758](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41258404758) |
| 36 | [`2d8a04859fda`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/2d8a04859fdab4e87f2997533b43b0c385ca2ec2) | [#237](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/237) | SUCCESS_OBSERVED | 2.45 | [41255389773](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41255389773) |
| 37 | [`835b3f914687`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/835b3f9146879f88548b6795035de70e24159be6) | [#237](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/237) | CANCELLED | 0.45 | [41255377164](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41255377164) |
| 38 | [`b46e8c7651c6`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/b46e8c7651c671444c90b11c2dbcb8710d3b07ed) | [#237](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/237) | CANCELLED | 1.97 | [41255255416](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41255255416) |
| 39 | [`ed4f0cd39761`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/ed4f0cd39761f2e9c3746ae4193d7026f1e63c84) | [#237](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/237) | CANCELLED | 0.83 | [41255214018](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41255214018) |
| 40 | [`7e4cb4649594`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/7e4cb46495943faf59f77121763ec9b615260dcf) | [#237](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/237) | CANCELLED | 0.73 | [41255174680](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41255174680) |

**Jobs et queues, échantillons réels non extrapolés** (API `GET /actions/runs/{id}/jobs`, timestamps job `started_at-created_at`) : [C99 #41361207485](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41361207485), **quatre jobs exécutés**, attente **3/4/4/4 s** (P95=4 s), exécutions **38/74/62/72 s** ; [CPC permanent #41361207468](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41361207468), un job effectué avec attente **3 s** et cinq jobs SKIPPED non assimilés à du travail ; [Xtensa #41361207629](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41361207629), quatre jobs effectivement exécutés avec attentes **3/2/3/3 s** (P95=3 s) et un job SKIPPED. **Ces quelques jobs ne fondent aucune P95 globale de queue** : exécuter l'outil sans `--no-jobs` pour une distribution complète, sous réserve d'authentification et de quota API. Les jobs `SKIPPED` ne sont pas des succès, et leurs timestamps factices ne prouvent pas une attente nulle.

**Incident hors fenêtre des quarante derniers HEADs, vérifié indépendamment** : sur [`0d4214fdc4670dcdaa36f7704fe692b92d43d963`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/0d4214fdc4670dcdaa36f7704fe692b92d43d963), les runs [#40974350096](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974350096), [#40974350095](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974350095), [#40974350098](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974350098), [#40974350079](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974350079) et [#40974350124](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974350124) sont tous **FAILURE**, créés le 29 octobre 23:37:02Z, mis à jour le 30 octobre 14:53:30Z (**916,47 min / 15 h 16**), **zéro job retourné pour chaque run** par l'API. Cause réelle **INCONNUE** : aucun calcul de 15 heures n'est attribuable au compilateur, à Xtensa ou au runner sans preuve. Cet événement reste dans le snapshot antérieur et **n'est pas effacé** par cette nouvelle sélection temporelle.

### Avant / après : limites d'équivalence

La baseline initiale [CI-OPT3 cinq familles](./CI-OPT3-five-family-routes.md) cite **20 runs C99 SUCCESS présélectionnés** : **P50=1,25 min**, **P95=3,82 min**, **max=5,13 min**. La fenêtre récente mesure **40 HEADs avec tous états**, et les workflows et types de diff ont évolué. Elle n'a pas de 20 PR pré-OPT3 appariées par type de fichier, statut, conditions de runner et combinaisons de gates. Par conséquent, **ni gain global chiffré ni régression chiffrée comparative** ne sont démontrés. Le taux de succès observé sur 40 HEADs n'est pas un taux de succès par PR ; les reprises rapides gonflent les annulations. Le coût du garde mémoire A0 de la PR #190 (six images base/HEAD) reste une famille optionnelle distincte, **sans changement de seuil ni de workflow**.

### Commandes de reproduction de la nouvelle fenêtre

```bash
python3 -m unittest discover -s tests -p 'test_opt3_perf_report.py' -v

# Fenêtre exhaustive d'une seule date, HEADs récents sans sélection de succès.
# Sélection figée avant 23:15:26Z ; la pagination est fail-closed.
GITHUB_TOKEN=${GITHUB_TOKEN} python3 tools/ci/opt3_perf_report.py \
  --created 2026-11-01 --through 2026-11-01T23:15:26Z \
  --latest-heads 40 --max-pages 10 --no-jobs --no-pr-files \
  --snapshot-out /tmp/ci-perf-nov01-api.json \
  --output /tmp/ci-perf-nov01-report.md

# Variante complète (jobs, tentatives et PR/file mapping) : requêtes GET
# plus nombreuses, authentification/rate limit à prévoir.
GITHUB_TOKEN=${GITHUB_TOKEN} python3 tools/ci/opt3_perf_report.py \
  --created 2026-11-01 --through 2026-11-01T23:15:26Z \
  --latest-heads 40 --max-pages 10 \
  --snapshot-out /tmp/ci-perf-nov01-full.json \
  --output /tmp/ci-perf-nov01-full.md
```

La première commande produit un instantané exhaustif des runs sélectionnés avec les **bornes API `updated_at`** ; la variante complète est celle qui documente réellement files/jours de reruns et fins de jobs. L'outil initial, son snapshot fermé du 30 octobre et ses assertions d'intégrité sont conservés. Les changements de la présente actualisation sont strictement l'ajout du filtre `created`, d'une sélection non biaisée par SHA et des tests associés ; **aucun gate CI, archive CPC, firmware ou outil de routage n'a été modifié**.

**Verdict proposé au Pilotage : `PERF_NOT_YET_VERIFIED`.** L'échantillon satisfait le nombre de HEADs distincts post-déploiement, pas le seuil de comparabilité/indépendance nécessaire pour certifier `P95<5 min` ni un gain global. Les mesures elles-mêmes sont auditables ; le gel ou la clôture de la revendication reste exclusivement au Pilotage.
