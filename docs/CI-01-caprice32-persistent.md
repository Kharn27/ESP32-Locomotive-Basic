# CI-01 — Image d'oracle CPC persistante (phase A : préparation)

**But :** faire de Caprice32 une **dépendance outillée stable**, pas une
compilation complète de 10–15 minutes déclenchée pour chaque PR.

## Stratégie de déploiement : deux phases, aucun contournement

**CI-01-A (cette PR) :** préparer une image Docker Linux publique et
reproductible, avec runtime SDL, FreeType, Xvfb, Python, CMake, compilateurs
et **Caprice32 compilé à partir du commit exact**
`8c778bf072a06fb7c23b9cccd179041db7f79a52`.
Le build Docker n'est requis qu'à la création/évolution de cette image.
Une PR exécute un build et smoke test isolés sans publier. Après merge
sur `main`, la CI publie sur GitHub Container Registry (GHCR).

**CI-01-B (après preuve de publication et test de tirage GHCR) :** remplacer
les étapes `sudo apt-get update/install` et `make ... WITHOUT_GL=1`
des workflows de preuve CPC concernés par une invocation de l'image
**épinglée par son digest SHA-256 publié et contrôlé**. Le submodule
historique doit toujours être checkout et sa révision vérifiée. Installer
`cap32` au chemin du submodule par copie depuis `/usr/local/bin/cap32`
pour préserver les scripts inchangés. Le binaire est compilé **sans**
macro `APP_PATH` pour que ses données proviennent du répertoire de travail
(celui du submodule, avec ses ROM/config originales).

Image préparée : `ghcr.io/kharn27/esp32-locomotive-basic-caprice32:cpc-8c778bf-ubuntu2404-v1`.

**Aucune ROM CPC incluse dans l'image publiée.** Les ROM sont lues
exclusivement depuis le checkout Git de la révision Caprice32, comme
auparavant, puis validées par leur SHA historique. Le Dockerfile est
versionné, la licence GPL du binaire et l'URL des sources sont fournies.
Le commit source doit être vérifié deux fois : à la compilation de l'image,
et dans le dépôt consommateur.

## Contrats de performance et de fidélité

- **À chaque PR ordinaire** : zéro `apt-get update`, zéro `apt-get install`,
  zéro `make` Caprice32. Le build C99 portable reste nécessaire.
- Conserver toutes les acquisitions CPC, traces écran/imprimante et
  vérifications d'archives, avec le même code des scripts.
- Ne pas confondre une CI rapide avec des tests plus faibles. Les quatre
  familles (Linux OFF/ON, différentiel natif, oracle indépendant, Xtensa)
  demeurent des barrières du développement métier.
- En cas de nouvelle image ou de digest absent/invalide, **échec explicite**
  et restauration par un nouveau build/publish contrôlé ; ne pas utiliser
  tacitement une version mutable ou non vérifiée.

## État

**Phase A ACCEPTÉE, fusionnée, image GHCR publiée :** [PR #57](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/57), commit `6935f01e3cad912d5b49c95875de25f39dc17c41`, [publication SUCCESS #40483979405](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40483979405).
Digest image final (index OCI) : `sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c`.

**Phase B ACCEPTÉE et fusionnée :** [PR #58](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/58), squash `dee25350252aa9cf9186a9ce14c56d081ab7cbeb`, après [oracle CPC complet SUCCESS #40485076739](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40485076739) (HEAD corrigé `4aa97b200e5e40ffc31da4becedee09b46f79b4d`). Le job a tiré l'image directement depuis GHCR, vérifié la révision Caprice32 et le SHA-ROM CPC6128, exécuté 34/34 CTest et conservé **les huit artefacts de preuve CPC**. La migration inclut les réglages `safe.directory` Git propres au conteneur, les chemins d'artefacts adaptés à `RUNNER_TEMP` et Bash comme shell par défaut. **Aucune modification des scripts d'acquisition ni du noyau C99.**

**Mesures vérifiées dans les logs des jobs CPC :**
- ancien environnement avec `apt-get` et `make` : 766,7 s (12 min 46,7 s), run #40478663225, job #122103127393 ;
- nouvelle image GHCR épinglée sans installation ni compilation Caprice32 : 82,0 s (1 min 22,0 s), run #40485076739, job #122124724408 ;
- gain sur ces deux réalisations : **~9,35×**, réduction **~89,3 %** du temps total. Ces observations ne constituent pas une garantie de durée sur tous les futurs runners.

**CI-01 CLOSE.** J1.2-C (frontière négative `-32768`, représentation historique REAL5) peut démarrer sous une nouvelle spécification ; aucune preuve CYD physique nouvelle.

État applicatif indépendant : J1.2-B / PR #56 acceptée et fusionnée
le 27 octobre 2026, commit `209fc9c58faade3fd8e5aef37eaa7a844d8d29d1`.
Aucune nouvelle validation physique CYD.
