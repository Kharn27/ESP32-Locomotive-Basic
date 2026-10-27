# HW4-B — extraction pilote ILI9341 réutilisable (issue #82)

## Périmètre et architecture

Branche `feat/hw4-b-ili9341-shared-driver`; base main `f8832715933f730dbbb787ad5dd555afce9ed7d9`. **HW4-A accepté/fusionné via PR #78**. Réorganisation uniquement matérielle. `core/`, `video/` (C99 indépendant ESP-IDF), les scénarios CPC et les oracles historiques ne sont pas modifiés. **HW4-C NON AUTORISÉ** : aucune commande BASIC PRINT reliée au LCD.

```
firmware/components/cyd_ili9341/          composant matériel ESP-IDF unique
  include/cyd_ili9341.h                 API transport
  cyd_ili9341.c                         GPIO/SPI2/ILI9341/DMA/sémaphore
  idf_component.yml                     esp_lcd_ili9341 2.1.0
firmware/esp32_display_probe/main/        sonde vidéo et commandes UART
firmware/esp32_probe/main/                test BASIC série; dépendance liée seulement
video/                                    rendu CPC C99 autonome
```

Les deux projets ESP-IDF chargent le même composant via `EXTRA_COMPONENT_DIRS`. Chacun conserve son propre `app_main`, jamais deux dans un firmware. Le firmware BASIC appelle uniquement une lecture de diagnostics sans initialiser le panneau : sa sortie PRINT demeure sur UART.

## Contrat de ressources

- `cyd_lcd_init()` : GPIO rétroéclairage 21 laissé éteint, SPI2 (MOSI 13, SCLK 14, CS 15, DC 2), 20 MHz, initialisation ILI9341 via composant Espressif officiel ; allocation unique `heap_caps_malloc(5120, MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA)` et sémaphore de fin de transaction. Nettoyage après échec d'initialisation et propagation de l'erreur ESP-IDF.
- `cyd_lcd_band()` : pointeur *emprunté*, propriété exclusive du pilote, pour une bande RGB565 **MSB first**. L'appelant peut remplir ce tampon seulement hors transfert ; aucun malloc dans le rafraîchissement.
- `cyd_lcd_send(x,y,w,h)` : contrôle des dimensions et capacité maximale **5120 octets** (320×8×2) ; transfert sérialisé et accusé réception par callback DMA ISR + sémaphore sous **2 secondes**. En erreur ou timeout, verrouille le pilote, éteint le rétroéclairage et conserve les ressources allouées (un callback DMA tardif ne doit jamais voir son buffer ou sémaphore libéré). Redémarrage requis, pas de hot-reinit.
- `cyd_lcd_orientation(index, clear_rgb565)` : réglage MADCTL et nettoyage GRAM avant changement ; garde réutilisation de la même orientation. **Cas 9 physiquement validé**, autres 0–13 expérimentaux maintenus pour les diagnostics HW3 (pas de certification implicite). La sonde choisit la couleur de nettoyage et interprète les scènes.
- `cyd_lcd_backlight()` : allumé seulement après dessin initial réussi. `cyd_lcd_current_orientation()` lit la sélection. `cyd_lcd_diagnostics()` : état, timeout, transfert, heap 8-bit libre/min/plus grand bloc et marge pile (octets).

Le composant ne possède ni texte, ni font, ni palette, ni VRAM, ni clavier/UART. Les logs `HW3 ORIENTATION_*` restent préservés ; les logs `HW3 DEVICE_MEMORY` sont conservés par la sonde, ajout de `HW4B DRIVER`.

## Bilan mémoire

RAM DMA allouée : **5120 octets**. VRAM compacte de la sonde : **16000 octets statiques** ; grille BOOT : **1000 octets statiques**. Aucun framebuffer RGB565 complet (320×240×2 = 153600 octets), aucune PSRAM, aucune allocation dans le chemin de refresh. Structures panel/SPI/sémaphore consomment aussi de la mémoire dynamique à l'initialisation.

**Référence HW4-A antérieure (non mesurée sur la branche HW4-B)** : sonde IRAM 67279/131072, DRAM 30360/180736, Flash Code 81294, image 206897 octets ; firmware BASIC IRAM 51807/131072, DRAM 30396/180736, Flash Code 66186, image 157481 octets. Heap sur le CYD précédent MODE 0 : libre **275980**, plus grand bloc **147456**, marge pile **4824 octets**. Les builds HW4-B doivent fournir leurs propres métriques séparées par image. **Ne pas additionner** les deux applications ; le coût produit BASIC + écran actif devra être mesuré dans le futur firmware unique, après HW4-C.

## Validation requise

1. Compilation Linux C99 `BP_SANITIZERS=OFF/ON`, suites et empreintes PPM inchangées, oracles CPC au SHA de branche. Aucun changement `core/`, `video/`, oracles/fixtures.
2. Deux builds cible v5.5.6 `firmware/esp32_display_probe` et `firmware/esp32_probe`, `idf.py size` et `size-components`, images ELF/bin séparées. CI HW4-B contrôle les duplications SPI et la portabilité.
3. **Test physique Product Owner seulement APRÈS CI verte**, sur branche/SHA exacts affichés dans la PR :

```sh
git fetch origin
git switch feat/hw4-b-ili9341-shared-driver
cd firmware/esp32_display_probe
idf.py set-target esp32
idf.py build
idf.py -p /dev/ttyUSB0 flash
idf.py -p /dev/ttyUSB0 monitor
```

Sur vrai ESP32-2432S028R : BOOT CPC (cas 9), `v` trois fois (MODE0/1/2), `p` couleurs, `z` curseur, `w` viewport MODE2, `r` retour BOOT ; envoyer journaux UART et retour visuel explicite, heap8_free, heap8_largest, stack_margin_bytes, aucune réinitialisation ni `DMA_FAIL`.

**En attente** : résultats CI à inscrire après exécution et rapport matériel réel du PO. `TARGET_BUILD_UNVERIFIED` et `ON_DEVICE_UNVERIFIED` tant que ces preuves n'existent pas ; pas de merge autonome ; HW4-C reste bloqué.
