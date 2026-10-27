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

Phase A proposée pour revue contradictoire : image non publiée tant que la
PR n'est pas acceptée et fusionnée. Phase B interdite avant l'observation
sur GitHub de la publication et de l'empreinte exacte.

État applicatif indépendant : J1.2-B / PR #56 acceptée et fusionnée
le 27 octobre 2026, commit `209fc9c58faade3fd8e5aef37eaa7a844d8d29d1`.
Aucune nouvelle validation physique CYD.
