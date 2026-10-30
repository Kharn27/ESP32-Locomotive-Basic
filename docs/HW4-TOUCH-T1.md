# HW4-TOUCH-T1 — CYD console PENIRQ: rotation 180° / soft reset

Mandat : [Pilotage #183](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/183). CONSOLE uniquement, ESP32-2432S028R sans PSRAM. Aucun changement du BASIC, des ROM/oracles CPC, du stockage flash/NVS, des profils HW3/BASIC_PROBE ou des workflows CI.

## Contrat matériel et temps

- XPT2046 **/PENIRQ sur GPIO36**, entrée uniquement, actif bas. **Aucun pull-up/pull-down interne** (GPIO36 ne propose pas de pull-up). L'étage externe de la carte doit fournir l'état haut au repos ; en cas de ligne flottante/IRQ non exploitable, remonter les observations au Pilotage **sans SPI tactile ajouté en silence**. Le geste accepte toute la surface, sans coordonnées/calibration.
- Un état initial **désarmé** impose une libération stable pendant **50 ms**, même après redémarrage alors que le doigt reste sur l'écran. Appui validé après 50 ms d'anti-rebond ; parasites courts ignorés.
- **Tap** : seule la libération stable d'un appui de durée **inférieure à 3 000 ms** produit SHORT_ROTATE. Un appui de **2 999 ms** est court. Orientation paysage **10 → 9 → 10** (boot sur 10) (miroirs X/Y opposés), géométrie 320×240, sans changement de VRAM/variables/éditeur. On appelle l'unique transport `cyd_ili9341`, puis **repaint_full()** (30 bandes de 8 lignes, buffer DMA de 5 120 octets réutilisé), sans toucher au garde sticky-fault DMA, sans retry en cas d'erreur.
- **Maintien** : si la pression continue atteint **3 000 ms**, LONG_RESET émis **une seule fois** sans rotation préalable, avant UP, puis `esp_restart()` (pas NEW, pas reset électrique externe, pas d'effacement NVS/flash). En cas de libération constatée après le seuil mais entre deux polls, la classification du bord UP reste LONG ; aucune double action. Un doigt maintenu après reboot ne doit pas provoquer une boucle.
- La machine à états pure est `hw4_touch_t1.c`. Polling coopératif dans la boucle UART existante ; **timeout UART limité à 20 ms** (100 ms sans écho avant T1, 20 ms avec écho), pour préserver les contrats HW4-C3-B2. Franchissement du seuil observé au prochain poll (~20 ms sans blocage applicatif), avec latence de polling et de rendu/UART potentiellement non nulle ; les tests hôte vérifient le seuil logique exact, le test physique doit vérifier la réactivité réelle.

## Logs UART (115 200 bauds)

`HW4-C2 START`, `HW4-C2 ORIENTATION_PASS case=10`, `HW4-TOUCH-T1 BOOT_READY orientation=10 penirq_gpio=36 ... armed=0`; à l'appui validé `HW4-TOUCH-T1 PRESS at_ms=...`; à chaque tap `HW4-TOUCH-T1 SHORT_ROTATE orientation=9|10 elapsed_ms=... program_preserved=1 repaint=full`; au maintien `HW4-TOUCH-T1 LONG_RESET elapsed_ms=... action=esp_restart orientation_before=...`, suivi d'un **nouveau** `HW4-C2 START` / `HW4-TOUCH-T1 BOOT_READY orientation=10`. Aucune trace en boucle.

## Build et flash exact HEAD (PO)

Sur le poste ayant ESP-IDF **v5.5.6** configuré (`idf.py` opérationnel), dans le dépôt :

```sh
git fetch origin feat/hw4-touch-t1-rotate-reset
git switch --detach <HEAD_SHA_FOURNI_DANS_LA_PR>
git rev-parse HEAD     # vérifier identité exacte avant toute preuve
idf.py -C firmware/esp32_display_probe -B build-touch-t1 -DLOCO_CYD_PROFILE=CONSOLE build
idf.py -C firmware/esp32_display_probe -B build-touch-t1 -p /dev/ttyUSB0 flash monitor
```

**Ne pas flasher un firmware antérieur** ; noter le SHA et la version de l'ESP-IDF dans les preuves. `Ctrl+]` pour quitter monitor. C'est le **CONSOLE** sur le port USB du CYD classique, pas HW3 ou BASIC_PROBE.

## Protocole physique PO (obligatoire avant acceptation)

1. Démarrer sans toucher : boot console paysage normal, `Ready`/curseur visibles, log START/ORIENTATION_PASS/BOOT_READY une seule fois ; aucun geste parasite.
2. Un tap bref puis un autre : premier `SHORT_ROTATE orientation=9`, écran **entièrement inversé de 180°**, texte et curseur lisibles, pas de bande résiduelle de 80 pixels ; second `orientation=10`, retour exact au départ.
3. Saisir au moniteur UART `10 PRINT "T"` puis `LIST`. Faire un tap, demander de nouveau `LIST` : ligne et variables conservées. `RUN` reste fonctionnel, aucun défaut LCD/DMA ni curseur/scroll corrompu.
4. Maintenir **2,0–2,9 s** puis relâcher : **aucun reboot** ; tap long mais inférieur au seuil peut tourner, c'est normal. Photographier/filmer et noter le `elapsed_ms`.
5. Maintenir **au moins 3 s** : `LONG_RESET` apparaît **sans SHORT_ROTATE préalable**, un seul redémarrage `esp_restart`, nouveau boot avec orientation par défaut 10 et `Ready`. `LIST` est vide ; l'ancienne ligne BASIC/les variables ont disparu. Le boot ne doit pas effacer NVS/flash.
6. Maintenir le doigt **plus de 5 s à travers le reboot** : **aucune boucle de resets** ; relâcher 50 ms ou plus avant nouvel appui ; UART reste fonctionnel.
7. Collecter **journal UART complet et constat visuel PO** (vidéo/photo si disponibles) avec START, deux orientations, LONG_RESET et second BOOT_READY, SHA compilé/flashé, mode CONSOLE, éventuelles anomalies, notamment IRQ GPIO36 au repos, couleurs, bandes de 80 px, DMA ou scroll.

Critères **FAIL** : rotation sur appui long avant reset, double reset tant que doigt posé, orientation non réversible, écran altéré, BASIC modifié par rotation, perte UART, sticky fault LCD, GPIO36 qui reste bloqué bas/haut. Les essais physiques constituent une preuve **distincte** de CI C99/ESP-IDF ; avant eux, statut obligatoire `ON_DEVICE_UNVERIFIED`.

## Vérifications logicielles

`hw4_touch_t1_gestures` dans CTest couvre boot doigt posé, stabilité du relâchement, rebonds et dropout bref, double tap, 2 999/3 000 ms, reset unique >5 s, redémarrage pendant maintien et horloge monotone. C99 GCC/Clang OFF/ON et CI Xtensa 3/3 via workflows existants ; **aucun workflow ajouté**. L'orientation 9↔10 doit être **validée réellement sur CYD** : les tests hôte ne peuvent certifier la matrice MADCTL/GRAM sur carte.

**Limite** : `esp_restart()` ressemble fonctionnellement à un reset complet de l'environnement CPC, sans équivalence ROM ni équivalence électrique stricte à CTRL+SHIFT+ESC.

## Retour terrain sur le HEAD précédent (PO, 29 octobre 2026)

Le PO rapporte un fonctionnement tactile et visuel excellent sur le firmware `ef32ca4672b3f9f1dd381f83e9cb6e3ffd08614a` (version ESP-IDF affichée `ef32ca4`), **avant** ce changement d'orientation initiale. Son journal UART `hw4-scroll-a0-c2-20261029-234506.uart.log` contient 5 `SHORT_ROTATE` alternant les cas 10/9, 2 `LONG_RESET elapsed_ms=3000`, 2 `SW_CPU_RESET` et deux résultats `LIST_BYTES` identiques (programme conservé pendant la rotation). Les diagnostics visibles sont `dma_fault=0` et `dma_timeouts=0`. Aucune vidéo n'a été produite. **Ce témoignage ne valide pas automatiquement le nouveau boot 10 : une nouvelle observation sur son SHA exact est demandée.**
