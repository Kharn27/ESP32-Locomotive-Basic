# CI-HW4-A0-C1 — dette historique / garde incrémental

Mandat : [Issue #329, décision Pilotage du 06/11/2026](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/329#issuecomment-6684032238). Branche ci/issue-329-hw4-a0-incremental, créée depuis main@e0085a9e2d3b601359fc44fcfa3ea83430fc7056. Ce SHA de création n'est **pas** un remplacement de la base PR courante.

## Trois références distinctes

1. **A0 historique IMMUTABLE** = 5799c774a3a5b3d453c17012a2328b379bd587bd. Contrôles A0→BASE et A0→HEAD visibles séparément. Un dépassement historique est déclaré **HISTORICAL_DEBT**, jamais A0 PASS.
2. **BASE réelle de la PR** = SHA complet github.event.pull_request.base.sha. Le workflow valide l'objet Git checkout et la réponse **actuelle** de l'API GitHub Pull Requests ; base périmée/falsifiée = FAIL_CLOSED. Le merge-base doit exister et être ancêtre des deux commits ; il peut différer de BASE si la branche n'est pas rebasée. On n'utilise **pas** le merge-base comme substitut de la base PR courante.
3. **HEAD réel de la PR** = SHA complet github.event.pull_request.head.sha, pas le merge-ref GitHub Actions. Vérifié aussi contre l'API live, l'objet Git et la provenance du checkout. Ref mouvante, base=head, faux SHA ou graphe incohérent = FAIL_CLOSED.

## Gardes et classification

Pour **CONSOLE, HW3 et BASIC_PROBE**, build d'A0, BASE et HEAD en ESP-IDF **5.5.6**. Sections mesurées via xtensa-esp-elf-size -A :

- **IRAM** : somme .iram0.* sauf marqueur .iram0.text_end, delta **strictement 0**.
- **DRAM** : somme .dram0.* incluant explicitement .dram0.bss, delta **au plus +256 octets**.
- **BSS** : toujours affichée séparément. **Flash .flash.text et .flash.rodata et taille BIN** : informatifs, sans seuil Flash opportuniste.

La comparaison historique A0→HEAD (et A0→BASE) utilise les mêmes invariants sans modifier les anciens seuils, mais un dépassement produit HISTORICAL_DEBT et non l'échec autoritatif de la PR. Le résultat autoritatif **BASE→HEAD** est INCREMENTAL_PASS (exit 0) ou INCREMENTAL_FAIL (exit 1). La dette héritée **n'autorise aucun** dépassement incrémental.

Le parser refuse section requise absente/malformée/dupliquée, .iram0.text_end différent de 1, Total incohérent, BIN vide, SHA incomplet et profil inconnu : FAIL_CLOSED (exit 2), **ou BASELINE_INVALID (exit 2) si l'invalidité concerne spécifiquement la référence A0 figée**. Sections requises : .dram0.data, .dram0.bss, .iram0.vectors, .iram0.text, .iram0.text_end, .flash.text, .flash.rodata. Toutes les sections DRAM sont comptées, pas uniquement BSS. Échec Git/API/compilation bloque le job (MEASUREMENT_FAILED), sans PASS de secours.

## CI et preuves

Workflow : .github/workflows/hw4-scroll-opt-a0-memory.yml, événement pull_request à chemins ciblés et permissions contents:read uniquement. **Les huit filtres historiques A0 demeurent strictement inchangés**, conformément au contrat indépendant CI-OPT3 (`HW4_A0_PATHS`) ; les nouveaux scripts/tests/docs ne sont pas ajoutés au routage A0. Les modifications du workflow lui-même déclenchent la matrice A0, et `tools/ci/**` déclenche CI-XTENSA. Cette limite de routage est explicite, sans assouplissement du gate CI-OPT3. Pas de pull_request_target, pas de credentials persistants, pas d'inférence sur un SHA de merge synthétique. Le test des cas adversariaux précède le build. Chaque job matrice conserve les 3 builds exacts (A0/BASE/HEAD), version IDF, logs set-target/build, sections, sortie idf.py size, firmware.bin et SHA-256 BIN, plus JSON de provenance/API live et rapports MD/JSON du comparateur dans un artefact nommé hw4-a0-memory-PROFILE. Les fichiers d'un job rouge sont **des traces d'erreur**, pas des preuves de succès.

Exécuter les tests hôte locaux :

~~~sh
python3 -m unittest discover -s tests -p test_hw4_a0_incremental_memory.py -v
~~~

| Injection | Verdict et code attendus |
|---|---|
| A0 historique rouge +1136 B DRAM, BASE→HEAD identique | HISTORICAL_DEBT + INCREMENTAL_PASS, exit 0 |
| A0 historique IRAM différent, BASE→HEAD identique | HISTORICAL_DEBT + INCREMENTAL_PASS, exit 0 |
| +256 B DRAM réelle, IRAM identique | INCREMENTAL_PASS, exit 0 |
| +257 B DRAM réelle (BSS incluse) | INCREMENTAL_FAIL, **exit 1** |
| +1 ou -1 B IRAM | INCREMENTAL_FAIL, **exit 1** |
| Section requise absente, doublon, Total incomplet | FAIL_CLOSED, exit 2 |
| SHA A0 changé ou fichiers A0 corrompus | BASELINE_INVALID, exit 2 |
| Base=head, SHA PR malformé ou nul | FAIL_CLOSED, exit 2 |
| Base/HEAD issus de l'événement divergent de la PR GitHub live | FAIL_CLOSED, exit non-zéro |
| Objet Git non-commit ou checkout discordant | FAIL_CLOSED, exit non-zéro |
| Artefact vide ou échec compilation | FAIL_CLOSED / MEASUREMENT_FAILED, job rouge |

### Dispatch manuel

workflow_dispatch est **explicitement refusé** (exit 2), car github.sha ne permet pas de déduire une base PR univoque. Pour recontrôler : lancer/rejouer le workflow **depuis une vraie PR** à jour, puis vérifier ses trois SHA et ses artefacts. Si main ou la branche PR a bougé entre l'événement et l'API live, le job échoue plutôt que d'employer une base périmée.

### Exclus du mandat

Aucun CORE, firmware, io, video, CMake, oracle CPC, clock/time. Les fichiers tools/ci/hw4_render_a_memory.py et .github/workflows/hw4-disp-render-a.yml restent **intacts** : leur référence distincte 21e95a7197413923bb5976067a0419bc729c20c1 et leur gate ne sont pas assouplis. Pas de mesure physique CYD requise. Les vrais métriques à fournir sont exclusivement celles des logs Xtensa du HEAD PR exact ; les fixtures de tests ne sont pas des mesures firmware. La décision de réception et de fusion est réservée au Pilotage.

## Premier rapport Xtensa réel (HEAD intermédiaire — NE PAS CONFONDRE AVEC LE HEAD FINAL)

Premier passage complet : [run #42214320570](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/42214320570) ; A0=5799c774a3a5b3d453c17012a2328b379bd587bd, BASE=e0085a9e2d3b601359fc44fcfa3ea83430fc7056, HEAD=f9bf4194bb388a59e0480b320dc34257dd72f760 (esp-idf v5.5.6). **Ce HEAD n'est pas le dernier HEAD de la PR.** Trois jobs Xtensa et leurs artefacts réussis ; mesures ELF/BIN en octets :

| Profil | IRAM A0 / BASE / HEAD | DRAM A0 / BASE / HEAD | BSS A0 / BASE / HEAD | delta BASE→HEAD IRAM / DRAM | statut A0→HEAD |
|---|---|---|---|---|---|
| CONSOLE | 67331 / 67551 / 67551 | 53728 / 54864 / 54864 | 42656 / 43792 / 43792 | 0 / 0 | HISTORICAL_DEBT (+220 IRAM, +1136 DRAM) |
| HW3 | 67279 / 67279 / 67279 | 31520 / 31520 / 31520 | 20432 / 20432 / 20432 | 0 / 0 | HISTORICAL_PASS |
| BASIC_PROBE | 51807 / 51807 / 51807 | 31028 / 31228 / 31228 | 21248 / 21448 / 21448 | 0 / 0 | HISTORICAL_PASS |

Les trois verdicts **incrémentaux** de ce run sont INCREMENTAL_PASS. Les trois profils du HEAD final doivent être revérifiés : aucune transposition de ce succès antérieur à un nouveau commit sans nouvelle CI.
