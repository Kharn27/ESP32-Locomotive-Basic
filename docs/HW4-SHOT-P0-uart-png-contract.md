# HW4-SHOT-P0 — Contrat UART screenshot ASCII v1 / PNG hôte

**Issue :** [#197](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/197) (préparation de [#194](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/194)). **Provenance :** contrat logiciel proposé et vérifié exclusivement par **trames `TEST_SYNTHETIC` sur PC**, pas par une capture d'un ESP32 CYD. **Statut de la fidélité TFT :** `ON_DEVICE_UNVERIFIED` / `ON_DEVICE_NOT_APPLICABLE_FOR_P0`.

## Contrat figé v1 (émetteur #194 futur)

Transport : **une ligne ASCII terminée par `\n` (ou `\r\n`) par enregistrement**, destinée à être imprimée au fil de l'eau sur **UART0 115200, 8N1**, dans un journal ordinaire `idf.py monitor`. Aucun encodage binaire brut, aucun échappement ni découpe de ligne dans un enregistrement. Préfixe réservé exact **`@CYDSHOT:1|`** (v1) suivi de `BEGIN`, `ROW`, `DONE` ou `ABORT`. Le préfixe est au début du contenu UART de l'émetteur. Le décodeur accepte uniquement des préfixes d'habillage `idf.py monitor` connus (couleur ANSI éventuelle, horodatage `[ ... ]`, `I (123) tag: `) avant le marqueur ; il **ne recherche pas le marqueur n'importe où dans du texte BASIC/UI**. Des lignes UART sans marqueur sont ignorées ; un marqueur screenshot malformé est une erreur. Aucun préfixe partiel ne peut produire une capture valide.

**Grammaire canonique (champs obligatoires dans cet ordre, sensibles à la casse) :**

```text
@CYDSHOT:1|BEGIN|id=<ID>|seq=<N>|w=320|h=240|pix=RGB565LE|orient=<ORIENTATION>|fw=<VERSION>|sha=<SHA>
@CYDSHOT:1|ROW|id=<ID>|n=0|crc=<CRC8>|b64=<BASE64>
@CYDSHOT:1|ROW|id=<ID>|n=1|crc=<CRC8>|b64=<BASE64>
... exactement un ROW pour chacun des indices 2 à 238 ...
@CYDSHOT:1|ROW|id=<ID>|n=239|crc=<CRC8>|b64=<BASE64>
@CYDSHOT:1|DONE|id=<ID>|crc=<CRC8>
```

En cas d'échec côté émetteur **à la place de `DONE`** :

```text
@CYDSHOT:1|ABORT|id=<ID>|reason=<REASON>
```

- **`id` :** 1 à 32 caractères `[A-Za-z0-9_-]`, **unique dans un journal/une session**, identique sur les 242 enregistrements (`BEGIN` + 240 `ROW` + `DONE`) ; son rôle est d'identifier *une seule* session, non d'exposer un numéro de série. Le décodeur refuse toute réutilisation d'ID. Avec plusieurs captures valides dans un log, le PC doit spécifier `--id`. En cas de trames croisées, même entre IDs non sélectionnés : refus.
- **`seq` :** entier décimal canonique `0..4294967295`, pas de signe, zéro initial interdit sauf `0` ; compteur de capture fourni par l'émetteur, distinct de l'ID. La politique de réinitialisation après reboot appartient à #194 ; ici la seule contrainte est son format borné et sa conservation dans les métadonnées.
- **`w`,`h`,`pix` :** valeurs littérales `320`,`240`,`RGB565LE`. **RGB565 little-endian** : pixel transmis sur **2 octets** `lo = pixel & 0xff`, `hi = pixel >> 8`, bits `RRRRRGGG GGGBBBBB` dans le mot 16 bits. Pas de stride ni de padding de ligne. Un autre mode, une autre dimension ou `RGB565BE` est **interdit en v1**.
- **`orient` :** 1 à 24 caractères `[A-Za-z0-9_-]`, métadonnée explicite de configuration et/ou de doute (`LCD10_UNVERIFIED` est un **exemple non homologué**). **Aucune rotation, inversion, transposition ou miroir effectués par le décodeur.** La ligne 0 est la première ligne logique envoyée et `x=0` est le premier pixel de chaque `ROW` ; le PNG conserve strictement cet ordre. L'orientation LCD réelle (« 10 ») et les overlays sont à caractériser physiquement dans #194, pas inférés ici.
- **`fw` :** version logicielle ASCII de 1 à 48 caractères `[A-Za-z0-9_.-]`, sans chemin ni identifiant utilisateur ; **`sha` :** préfixe hexadécimal Git de 7 à 40 caractères **minuscules** `[0-9a-f]`. Les deux champs sont **obligatoires**, permettant de lier ensuite une capture à un firmware réellement flashé par le PO. L'émetteur #194 devra fournir une identité réelle ; `TEST_SYNTHETIC`/`012345...` dans les tests ne prouvent aucun firmware.
- **`n` :** index décimal canonique, strictement successif de **0 à 239** ; aucun trou, doublon, inversion, index supplémentaire, ou mélange d'IDs. Dans le format v1, **640 octets binaires par ligne** (`320 × 2`) et **856 caractères base64 ASCII** (RFC 4648, standard avec le padding final exactement canonique). Le décodeur exige un décodage `base64.b64decode(..., validate=True)` **et** la réencodabilité octet pour octet de la chaîne (pas d'espace, padding excessif, alphabets alternatifs, ni caractères hors base64).
- **`crc` :** exactement huit chiffres hexadécimaux **majuscules** `[0-9A-F]{8}`, valeur CRC-32/ISO-HDLC (= CRC-32/ADCCP, CRC-32 Ethernet), polynôme normal `0x04C11DB7` / réfléchi `0xEDB88320`, init `0xFFFFFFFF`, `refin/refout=true`, xorout `0xFFFFFFFF`. Implémentation **`zlib.crc32(data) & 0xffffffff`**. Pour `ROW`, CRC sur les **640 octets binaires**, avant encodage base64, **sans saut de ligne** ni champs UART. Pour `DONE`, CRC sur **la concaténation binaire de ROW 0 à 239** (153 600 octets), dans l'ordre du fil, sans métadonnées : `acc=0; acc=zlib.crc32(raw_row, acc) & 0xffffffff` répété 240 fois. Pas de CRC sur les 205 440 caractères base64.
- **`reason` :** code ASCII 1 à 24 caractères `[A-Za-z0-9_-]` (`UART_TIMEOUT`, `RENDER_ERROR`, ...). `ABORT` ne peut jamais être traité comme `DONE`, même si 240 `ROW` ont été envoyés.

**Limites de taille :** **1 024 caractères max par ligne *transport*, y compris décorations du monitor et fin de ligne**. Chaque `ROW` porte exactement 856 caractères base64 ; son enveloppe inclut la trame, les champs et la fin de ligne. Les en-têtes sont bornés par les tailles des champs ci-dessus et ce plafond de 1024. Le décodeur lit le journal **ligne par ligne** avec une taille bornée, sans conserver tout le log. 240 `ROW` obligatoires + `BEGIN`/`DONE` = 242 enregistrements pour une réussite. Un autre marqueur `BEGIN` au milieu, un `DONE` prématuré, un `ABORT`, un `ROW` d'autre ID, un CRC faux ou un EOF avant `DONE` sont des erreurs **fatales** ; pas de synchronisation automatique au milieu d'un flux interrompu. Une session terminée ne peut pas réutiliser le même ID dans le log. Les champs supplémentaires, absents ou réordonnés sont refusés.

**Débit :** 240 × 856 = **205 440 caractères base64** seuls, soit environ **205 Ko décimaux**, *avant* la surcharge des 240 en-têtes `ROW`, CRC, `BEGIN`, `DONE` et `CRLF`. À **115 200 bit/s avec 8N1** (~11 520 octets/s théoriques), la charge base64 exige à elle seule ~**17,83 s**, donc **plus de ~18 s pour la vraie trame**, davantage avec émission UART, scheduling, traitement et log ; aucune promesse de capture instantanée.

## Décodeur Python 3 hôte

Outil : [`tools/hw4_shot_decode.py`](../tools/hw4_shot_decode.py), **bibliothèque standard uniquement**. Entrée : fichier de journal ou `stdin` (`-`), option `--id` pour une sélection déterministe, sortie `--output`/`-o` obligatoire. Le décodeur valide intégralement chaque session rencontrée **avant** de produire un PNG. Une trame non sélectionnée endommagée provoque aussi un refus conservateur. L'image PNG utilise `IHDR` **320×240, 8 bits par composante, couleur vraie RGB (type 2)** ; un seul `IDAT` compressé zlib ; `IEND`, CRC sur chacun des chunks PNG. Conversion RGB565→RGB888 déterministe par réplication des bits : `R8=(R5<<3)|(R5>>2)`, `G8=(G6<<2)|(G6>>4)`, `B8=(B5<<3)|(B5>>2)` ; **zéro interpolation, zéro transformation d'orientation**. Chaque scanline PNG comporte un filtre `0` (« None »).

L'écriture passe par un fichier temporaire **dans le répertoire de sortie**, `flush` + `fsync`, puis `os.replace` **après** la validation de la trame entière et la génération du PNG. Toute erreur de protocole ou de CRC entraîne code de sortie `2`, **pas de nouveau PNG**, et aucun écrasement d'un PNG existant. Le dossier de destination doit préexister ; le décodeur ne contacte aucun service, ne modifie aucun port série, n'accède pas au CYD. **Attention :** la mention `fw/sha` dans une trame reçue est du texte fourni par l'émetteur, **non une preuve authentifiée** d'un firmware réel.

### Reproduction offline déterministe — exclusivement `TEST_SYNTHETIC`

Depuis la racine du dépôt :

```bash
python3 -m py_compile tools/hw4_shot_decode.py tests/test_hw4_shot_decode.py
python3 -m unittest discover -s tests -p 'test_hw4_shot_decode.py' -v
python3 tests/test_hw4_shot_decode.py --emit-synthetic /tmp/hw4-shot-TEST_SYNTHETIC-uart.log
python3 tools/hw4_shot_decode.py /tmp/hw4-shot-TEST_SYNTHETIC-uart.log \
    --id TEST_SCREEN_001 --output /tmp/hw4-shot-TEST_SYNTHETIC.png
# Alternative : cat /tmp/hw4-shot-TEST_SYNTHETIC-uart.log | \
#   python3 tools/hw4_shot_decode.py - --id TEST_SCREEN_001 -o /tmp/stdin.png
```

**Empreintes de l’exemple `TEST_SYNTHETIC` généré localement :** journal UART 224 600 octets, SHA-256 `715e64e74d3c0b5b55b835f77e8cf173cdef2067af2f3d69400b47ca0eabedb2` ; PNG reconstruit 604 octets, SHA-256 `fb91a2b5d7442a680a2f011f9a4da86824035061e19cb4fcb8214c2128c19609`. Ce sont des **preuves de reproductibilité côté PC** et non des preuves matérielles CYD.

Les générateurs de trames sont **exclusivement dans `tests/test_hw4_shot_decode.py`** ; aucune fixture ne contient une « capture CYD ». L'exemple utilise un fond bleu, des coins bleu/jaune, un trait de bordure blanc et un point rouge/vert au centre. La suite crée de véritables PNG en mémoire et sur disque, **reparcourt les 240×320 pixels** et relit indépendamment les chunks `IHDR`, `IDAT`, `IEND`, leurs CRC, l'IDAT zlib et les 240 scanlines (en Python stdlib). Elle couvre également l'ancien fichier protégé et l'absence d'image après rejet de flux altéré.

## Contrat de raccordement **ultérieur** #194 (NON IMPLÉMENTÉ)

Rien de cette section n'autorise une modification de firmware sur cette PR :

1. **Source des pixels** : futurs 240 appels au rendu logique réel (`cpc_video_render_row()` envisagé en #194) avec **au maximum un tampon de 320 pixels = 640 octets**, sans allocation de framebuffer complet, sans lecture GRAM SPI et sans second propriétaire LCD/DMA. Vérifier sur la vraie cible quel rendu couvre fond, bordures, texte, couleurs PEN/INK et curseur/overlays du TFT ; ne pas inventer cette équivalence dans P0.
2. **Orientation** : vérifier explicitement le mapping réel `x/y`, notamment orientation 10 et marges 20+20. Toute réorientation éventuelle du flux doit être un choix côté émetteur documenté **en conservant RGB565LE et l'ordre canonique des ROW v1**, ou faire l'objet d'une évolution de protocole mandatée. Le décodeur v1 ne devine rien.
3. **Propriétaire LCD** : préserver l'unicité du propriétaire vidéo existant, l'état de la console, l'édition et la mémoire, le verrou/non-réentrance de capture et les invariants de DMA. Aucun framebuffer/copie écran 153 600 o sur CYD.
4. **Déclenchement** : HOME ANSI `ESC[H` seulement **dans l'édition E3** (sans soumettre ni altérer le buffer) et HOME existant en **focus SCREEN** `UART_LINE_RETURN_HOME`/`cpc_screen_nav_home` à préserver ; ajouter `!SHOT` comme secours *dans #194 seulement*. Pas de HOME ni `!SHOT` dans P0.
5. **Transfert et identité** : fournir `id` unique, `seq` de capture, `fw` et `sha` tirés de la construction effective, acquérir un verrou de capture, émettre intégralement `BEGIN`→240 `ROW`→`DONE`, ou `ABORT` en échec, en prenant en compte la latence UART >18 s. Les métadonnées ne doivent contenir ni secrets ni numéros de série.
6. **Preuve matérielle future** : après autorisation du Pilotage et fusion de #190, faire vérifier par le PO sur CYD réél le HOME E3 et SCREEN, `!SHOT`, les overlays, le curseur, les marges, l'orientation et le PNG comparé à l'écran. Le présent lot est **`HOST_PROTOCOL_VERIFIED — ON_DEVICE_NOT_APPLICABLE_FOR_P0`** uniquement lorsque ses tests hôte passent.

**Exclusions réaffirmées :** PR #190 et ses fichiers intouchés, aucune intervention `firmware/`, `core/`, `video/`, `io/`, `hal/`, `integration/`, `.github/workflows/`, ni modification d'oracles CPC, de budgets RAM, de CMake, de scripts existants ou de l'outil `capture_cyd_uart.sh`. Pas de nouvelle CI. **L'acceptation et la fusion relèvent exclusivement du Pilotage.**
