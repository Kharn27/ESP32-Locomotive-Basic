# CI-OPT3-PERF-A — latences observées et protocole reproductible

**Mandat :** [issue #176](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/176), [décision Pilotage](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/176#issuecomment-6529805847).
**Données réelles :** [snapshot figé](./CI-OPT3-PERF-REAL-20261030.json), GitHub REST Actions. **Coupure** 2026-10-29 18:51:11Z (merge #175) ; **borne haute inclusive des créations de runs** 2026-10-30 17:40:00Z. 286 runs de `pull_request`, 41 HEADs distincts, 8 numéros de PR retrouvés et 5 SHA non résolus. Toutes les conclusions et les HEADs remplacés restent dans le corpus.

## Résultat (nearest-rank)

Pour n valeurs triées, `P(p)=valeurs[ceil(p*n)-1]`. Départ = plus petit `created_at` des workflows du SHA ; arrivée = plus grand `updated_at` (proxy API si aucun `job.completed_at` mesuré). **Les couloirs parallèles ne sont pas additionnés**. Durées secondes entières avant arrondi décimal.

| Cohorte | N | P50 (min) | P95 (min) | Max (min) |
|---|---:|---:|---:|---:|
| Tous les HEADs terminés, incidents inclus | 41 | 2.70 | 6.13 | 916.47 |
| HEADs terminés, hors deux incidents sans jobs (diagnostic ordinaire) | 39 | 2.67 | 3.87 | 6.13 |
| SUCCESS seulement (secondaire / biais de sélection) | 20 | 2.65 | 3.42 | 6.13 |

**Interprétation :** le P95 descriptif ordinaire est 3.87 min, mais `PERF_NOT_YET_VERIFIED`. Il existe 8 PR identifiées et non 41 PR indépendantes ; certains SHA sont corrélés et le mélange de diffs n'est pas apparié à la baseline. La fenêtre inclut des échecs et annulations. L'objectif indicatif `P95 < 5 min` paraît compatible avec le sous-ensemble hors incidents mais **n'est pas certifié** ; un HEAD ordinaire prend jusqu'à 6.13 min. Aucune revendication numérique de gain global avant/après.

## Familles — runs terminés, non filtrés par SUCCESS, incidents no-jobs >1h isolés

| Famille | N runs | P50 min | P95 min | Max min | Conclusions observées (y compris incidents) |
|---|---:|---:|---:|---:|---|
| ARCH | 39 | 0.20 | 0.53 | 0.55 | success 38, failure 3 |
| C99 | 39 | 1.15 | 1.53 | 2.85 | success 32, failure 6, cancelled 3 |
| CPC acquisition | 10 | 0.02 | 1.48 | 1.48 | skipped 9, failure 1 |
| CPC indépendant | 21 | 1.35 | 1.53 | 1.62 | success 21, failure 2 |
| CPC permanent | 39 | 0.75 | 2.67 | 2.70 | success 32, cancelled 5, failure 4 |
| HW4 autres | 48 | 0.50 | 0.95 | 1.38 | success 42, failure 4, cancelled 2 |
| HW4 mémoire A0 | 15 | 3.17 | 6.13 | 6.13 | success 9, failure 6 |
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
| [#190](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/190) | [`061a62473db6`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/061a62473db620f30889b334351d7315437a7ce9) | 8 · [run 41080231142](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41080231142) | FAILURE | 3.27 | OLD_HEAD |
| [#193](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/193) | [`466ea422e8a5`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/466ea422e8a5a4eaedec00875acea1a783bb4c14) | 9 · [run 41080446427](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41080446427) | SUCCESS | 2.67 | — |
| [#190](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/190) | [`d165c375a2fe`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/d165c375a2fece2a6178b975162a6bf3aca47c61) | 8 · [run 41081507189](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41081507189) | SUCCESS | 3.15 | OLD_HEAD |
| [#190](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/190) | [`4fbd3c108257`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/4fbd3c108257ee046acaef68eda4d2e927dfa565) | 8 · [run 41085303434](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41085303434) | FAILURE | 3.18 | OLD_HEAD |
| [#190](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/190) | [`9f742420ea0d`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/9f742420ea0d8bde7abf2627c3d322d8f155ef07) | 8 · [run 41085425262](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41085425262) | SUCCESS | 3.42 | OLD_HEAD |
| [#190](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/190) | [`b73040b292e5`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/b73040b292e57e3a0149a618ba2abf996eeec75a) | 8 · [run 41099340483](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41099340483) | FAILURE | 3.10 | OLD_HEAD |
| [#190](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/190) | [`3d504de90c20`](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/3d504de90c20b499e2a782688ab69508c274bee4) | 8 · [run 41099638924](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41099638924) | SUCCESS | 6.13 | — |

## Queue, tentatives, reruns, données manquantes

- Les dates `created_at`, `run_started_at`, `updated_at`, `run_attempt`, SHA, chemins et conclusions sont conservées **par run** dans [la source JSON réelle](./CI-OPT3-PERF-REAL-20261030.json). Si `jobs` est absent de l'objet, **non acquis** (ne pas interpréter comme zéro). `jobs: []` est exclusivement utilisé ici pour les **dix runs** dont l'API jobs a été effectivement interrogée.
- [HEAD 0f8d7e42f5c4](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/0f8d7e42f5c4cdb79964910d7271702cd289beed) : cinq workflows `FAILURE`, durée proxy 5 212 s (**1 h 26 min 52 s**) ; **0 job dans les cinq réponses API**. [Exemple run 40956551131](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40956551131).
- [HEAD 0d4214fdc467](https://github.com/Kharn27/ESP32-Locomotive-Basic/commit/0d4214fdc4670dcdaa36f7704fe692b92d43d963) : cinq workflows `FAILURE`, durée proxy 54 988 s (**15 h 16 min 28 s**) ; **0 job dans les cinq réponses API**. [Run 40974350096](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974350096), [40974350095](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974350095), [40974350098](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974350098), [40974350079](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974350079), [40974350124](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40974350124). Cause précise inconnue : **pas 15 h de compilation**.
- [Échec A0 #190, run 41080231240](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41080231240) : trois jobs `base-vs-head`, démarrés 3 s après leur création, fin CONSOLE à 15:26:18Z avec FAILURE, les deux autres SUCCESS ; la comparaison compile **base historique et HEAD pour trois profils (six images)**. C'est un contrôle mémoire absolu distinct de la réussite Xtensa ; budget inchangé.
- [A0 succès ultérieur, run 41099638924](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41099638924) : trois jobs SUCCESS, files de 2–3 s ; job HW3 terminé à 17:36:23Z. Ces trois jobs **s'exécutent en parallèle**.
- [C99 J1.18-B, run 41080446207](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/41080446207) : quatre jobs Linux SUCCESS ; files `started_at - created_at` de **4, 11, 11 et 24 secondes** (P95 nearest-rank = 24 s). File ≠ temps de compilation.
- Les relances sont distinguées par `run_attempt` ; l'outil live charge les tentatives et jobs par `/actions/runs/{id}/attempts/{n}/jobs`. Le snapshot fige seulement certains jobs vérifiés, **et n'est pas une preuve exhaustive des queues/reruns**. La réacquisition live authentifiée est nécessaire pour une distribution complète.

## Avant / après, comparabilité et classification de diff

**Avant CI-OPT3 :** [baseline versionnée](./CI-OPT3-five-family-routes.md) sur **20 runs C99 SUCCESS présélectionnés**, P50 **1,25 min**, P95 **3,82 min**, max **5,13 min**, mesurés uniquement par `updated_at-created_at`. Elle n'échantillonne ni les annulations ni le chemin critique global PR.

**Après CI-OPT3 :** le présent corpus a 41 HEADs terminés (seulement 20 HEADs classés SUCCESS si l'on exclut les deux incidents), dont plusieurs révisions de mêmes PR (#190, #193 et autres). Des HEADs anciens ne peuvent pas être classés honnêtement par les fichiers **actuels** de la PR ; l'outil attribue `UNKNOWN_REVISION` sauf concordance HEAD exact. Une classe de diff et une population pré/post de 20 HEADs *appariés* ne sont pas établies. **Aucun pourcentage de réduction global n'est calculable sans biais démontré.**

**CPC historique :** les acquisitions ROM/Caprice32 spécialisées et leurs `SKIPPED` restent comptées hors SLA ; aucune archive, SHA scellé, falsification ou critère de preuve n'a été modifié par cet audit. Ceci **ne constitue pas** une nouvelle exécution d'oracle CPC.

## Reproduction locale (stdlib, API GET uniquement)

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
