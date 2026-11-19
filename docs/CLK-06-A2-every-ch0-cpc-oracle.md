# CLK-06-A2 — Oracle CPC6128 `EVERY` canal 0 : observations bornées et preuves scellées

**Mission :** [GO Pilotage #314](https://github.com/Kharn27/ESP32-Locomotive-Basic/issues/314#issuecomment-6982929276). **Mandat C1 :** [verdict conditionnel sur PR #393](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/393#issuecomment-7005234608). **Branche :** `oracle/clk-06-a2-every-ch0`. **Base d'acquisition historique :** `main@91cc6b0856cfb4a05fd3ef3f5e5a2bb6aa523084`. **HEAD réel de l'acquisition archivée :** `74820eefa1e6f26a3225962addb523c836a8b9a1`, **distinct de tout HEAD de synchronisation C1 ultérieur**.

## Provenance et chaîne d'intégrité (12 observations = six sondes × deux sessions)

- [Workflow GitHub Actions #44345600912](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44345600912) : trois jobs **SUCCESS** (11 tests adversariaux hôte, acquisition ROM-backed, rejeu indépendant).
- [Artifact original RAW #14447266571](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44345600912/artifacts/14447266571) : copie ZIP **bit à bit identique** `tests/fixtures/cpc6128/clk_06_a2_every_ch0/evidence/run-44345600912-74820eef-raw.zip` ; **SHA-256 du ZIP** `54b039bdb90818d6f963c060847ad9cfe13f89a5356203b7f465a61fad9ffc6c`.
- [Artifact sceau externe #14447276551](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44345600912/artifacts/14447276551) : copie ZIP **bit à bit identique** `tests/fixtures/cpc6128/clk_06_a2_every_ch0/evidence/run-44345600912-74820eef-external-seal.zip` ; **SHA-256 du ZIP** `afbdad827635a86e0a341ff60ff211f0397eb66a27ede1d60816e3bde0b983ed`.
- Le fichier `clk06-a2-seal.json` du ZIP de sceau est **extérieur** au ZIP RAW : `mission=CLK-06-A2`, `head=74820eefa1e6f26a3225962addb523c836a8b9a1`, `manifest_sha256=e369b03c4bd945eaf98582e2b2e1fe5504dc878bcf7ba95faffa8007c11c20d9`. Le SHA-256 recalculé des octets RAW `manifest.json` correspond exactement.
- ZIP RAW : **163 entrées**, dont **162 pièces originales** déclarées par le manifeste ; 162/162 inventoriées par taille et SHA-256, sans entrée absente ni supplémentaire, ZIP sans erreur. Les 12 paires `program.bin`, `list/printer.dat`, `list/screen.png`, `run/printer.dat`, `run/screen.png` ont des octets strictement égaux entre `original` et `repeat` pour chacun des six cas.
- Caprice32 `v4.6.0-8c778bf072a06fb7c23b9cccd179041db7f79a52` ; commit `8c778bf072a06fb7c23b9cccd179041db7f79a52` ; binaire SHA-256 `5170b3fc68ab116e7698e6e68a742e324d0e9dbfd87eeb7b2090e13c639f73eb` ; ROM CPC6128 SHA-256 `31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562` ; image GHCR `ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c`.
- Deux démarrages indépendants constatés à **2026-11-18 16:18:48.070268 UTC** (`original`) et **16:25:27.712828 UTC** (`repeat`), captures boot `Amstrad 128K` / `BASIC 1.1`. Garde `TIME` CPC / durée hôte **300,44** et **300,26 ticks/s** respectivement : ce sont des contrôles de cadence d'émulateur **et non** une mesure de période `EVERY`.
- Les captures PNG des deux sessions (boot, LIST, RUN, erreur) ont été examinées directement par le Pilotage le **19/11/2026** ; relecture C1 des deux captures boot/E06 et des 162 fichiers originaux. `LIST #8`, RAM tokenisée et sorties RUN imprimante sont préservées, sans reconstruction.
- Les `corpus.json` et six `.bas` restent **des entrées** ; SHA-256 corpus `340775c9c48b20faf6bc505da595c3c62abaeae21c31c5a0df69fad50a3c4259`. Le manifeste original conserve **sans modification** `ACQUIRED_PENDING_SCREEN_REVIEW` et ses champs `screen_review=UNVERIFIED` : les conclusions ci-dessous sont des **qualifications contradictoires documentaires postérieures**, pas un réétiquetage des preuves brutes.

## Observations CPC : matrice limitée aux fenêtres finies acquises

Chaque ligne ci-dessous a été constatée **dans les deux processus indépendants** et contrôlée sur sorties imprimante **byte-exact**, LIST/RAM et écrans ; `OBSERVED` est un état d'observation CPC, **pas** un `MATCH_EXACT` du firmware.

| Cas | Source / question expérimentale | Sortie CPC des deux sessions (valeurs observées) | Statut |
| --- | --- | --- | --- |
| **E01_RECUR_RETURN** | `EVERY 10,0 GOSUB 1000`, `FOR I%=1 TO 8000`, `RETURN` et désarmement | `HIT=1..4` imprimés (traces volontairement plafonnées), `MAIN=19`, `CANCEL=1`, `FINAL=19`. Au moins deux livraisons et reprise du principal, sans nombre total de lignes `HIT` égal à 19 | **OBSERVED**, borne E01 |
| **E02_LONGER_INTERVAL** | `EVERY 40,0`, `FOR I%=1 TO 11000` | `HIT=1..4`, `MAIN=6`, `CANCEL=12`. **La boucle n'a pas la même longueur qu'E01** : ne calculer aucun ratio de fréquence 10/40 à partir de ces seuls compteurs | **OBSERVED**, borne E02 |
| **E03_REMAIN_CANCEL** | `EVERY 2,0`, `REMAIN(0)` immédiatement, puis `FOR I%=1 TO 8500` | `REMAIN=2`, `MAIN=0`, `R2=0`, sans sortie `HIT` pendant la fenêtre observée ; témoin de sensibilité E01 positif sur un autre programme | **OBSERVED**, absence bornée |
| **E04_REARM_CHANNEL** | `EVERY 5,0` vers handler A puis `EVERY 20,0` vers handler B sur **le même canal 0** ; `FOR I%=1 TO 8500` | `SECOND=1..4` affichés, `MAIN_A=0`, `MAIN_B=10`, `CANCEL=11` : aucun handler A livré dans cette fenêtre | **OBSERVED**, même canal |
| **E05_EVERY_AFTER** | `EVERY 5,0` suivi de `AFTER 15,0` sur **le même canal 0** ; `FOR I%=1 TO 8500` | `AFTER=1`, `MAIN_A=0`, `MAIN_B=1`, `CANCEL=0` : seul le handler AFTER est observé, aucune conclusion sur les priorités multi-canaux | **OBSERVED**, même canal |
| **E06_BAD_ARGUMENT** | `EVERY -1,0 GOSUB 1000` ligne 20 | Seul `E06:BEGIN` sur imprimante, puis écran **`Improper argument in 20`** et **`Ready`** ; ni `AFTER_BAD` ni handler exécutés | **OBSERVED**, diagnostic visuel |

**Exception et bornage :** E06 provoque volontairement une erreur, les cinq autres expériences se terminent dans une fenêtre de boucles `FOR/NEXT` finies ; une absence d'événement dans ces fenêtres ne prouve pas une impossibilité globale. Les sorties `HIT=1..4` sont plafonnées par les programmes et ne doivent pas être interprétées comme quatre interruptions totales. E02 ne distingue pas quantitativement toutes les influences de la vitesse de boucle.

## Vérifier les ZIP permanents de façon indépendante

Depuis la racine du dépôt, exécuter le contrôle suivant, qui refuse toute différence des ZIP, sceaux, pièces ou sessions, **sans modifier les données historiques** :

```sh
sha256sum \
  tests/fixtures/cpc6128/clk_06_a2_every_ch0/evidence/run-44345600912-74820eef-raw.zip \
  tests/fixtures/cpc6128/clk_06_a2_every_ch0/evidence/run-44345600912-74820eef-external-seal.zip
python3 - <<'PY'
import hashlib, io, json, pathlib, zipfile
root=pathlib.Path("tests/fixtures/cpc6128/clk_06_a2_every_ch0/evidence")
raw=(root/"run-44345600912-74820eef-raw.zip").read_bytes()
outer=(root/"run-44345600912-74820eef-external-seal.zip").read_bytes()
assert hashlib.sha256(raw).hexdigest()=="54b039bdb90818d6f963c060847ad9cfe13f89a5356203b7f465a61fad9ffc6c"
assert hashlib.sha256(outer).hexdigest()=="afbdad827635a86e0a341ff60ff211f0397eb66a27ede1d60816e3bde0b983ed"
with zipfile.ZipFile(io.BytesIO(outer)) as zs,zipfile.ZipFile(io.BytesIO(raw)) as zr:
    assert zs.testzip() is None and zr.testzip() is None
    assert zs.namelist()==["clk06-a2-seal.json"]
    seal=json.loads(zs.read("clk06-a2-seal.json"))
    mraw=zr.read("manifest.json")
    m=json.loads(mraw)
    assert m["head"]==seal["head"]=="74820eefa1e6f26a3225962addb523c836a8b9a1"
    assert m["mission"]==seal["mission"]=="CLK-06-A2"
    assert hashlib.sha256(mraw).hexdigest()==seal["manifest_sha256"]=="e369b03c4bd945eaf98582e2b2e1fe5504dc878bcf7ba95faffa8007c11c20d9"
    assert m["status"]=="ACQUIRED_PENDING_SCREEN_REVIEW"
    assert len(m["files"])==162
    assert set(zr.namelist())==set(m["files"])|{"manifest.json"}
    for name,entry in m["files"].items():
        content=zr.read(name)
        assert len(content)==entry["bytes"] and hashlib.sha256(content).hexdigest()==entry["sha256"], name
    for case in m["sessions"]["original"]["cases"]:
        assert case in m["sessions"]["repeat"]["cases"]
        for part in ("program.bin","list/printer.dat","list/screen.png","run/printer.dat","run/screen.png"):
            assert zr.read("original/"+case+"/"+part)==zr.read("repeat/"+case+"/"+part),(case,part)
print("CLK-06-A2 ARCHIVE_162_OF_162_SEALED_PASS; SCREEN_REVIEW_IS_SEPARATE")
PY
```

Rejeu du vérificateur A2 (après extraction du **ZIP RAW d'origine**, avec le **HEAD historique de la capture**, non le HEAD C1) : `python3 tools/clk_06_a2_oracle.py --verify /chemin/du/raw-extrait --head 74820eefa1e6f26a3225962addb523c836a8b9a1 --seal e369b03c4bd945eaf98582e2b2e1fe5504dc878bcf7ba95faffa8007c11c20d9`. Les fixtures synthétiques de `tests/test_clk_06_a2_oracle.py` ne sont jamais des témoins CPC.

## CI et limites de la qualification

- CI initiales **du HEAD d'acquisition `74820eef...`** : [A2 3/3](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44345600912), [OPT3](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44345600504), [C99](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44345600513), [ARCH](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44345600315), [CPC-PERMANENT](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44345600174), [oracle CPC historique](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44345600271), [XTENSA](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/44345600368) : **SUCCESS**, vérifiées au précédent HEAD uniquement.
- La synchronisation C1 avec `main` crée un **autre HEAD**. Toute acquisition de ce HEAD doit recevoir **son propre sceau et ses propres observations** : ne jamais associer les ZIP archivés `74820eef...` au SHA C1. Consulter [PR #393](https://github.com/Kharn27/ESP32-Locomotive-Basic/pull/393) pour CI et qualifications finales par SHA.
- `UNVERIFIED` / hors périmètre : canaux 1–3, priorités ou simultanéité inter-canaux, `DI/EI`, durée universelle d'un tick `EVERY` (y compris 1/50 s), `ERR/ERL` non acquis, vitesse CPC non testée et correspondance avec un runtime C99/CYD. Aucune expérimentation CYD : `ON_DEVICE_NOT_APPLICABLE_A2`.

**Périmètre conservé :** aucun changement `core/`, `firmware/`, `integration/`, HAL, moteur temporel BASIC, outils et archives A1/CLK-03, CI historique C7 ni PR DEV2 #387. L'acceptation finale et la fusion demeurent exclusivement au Pilotage. Pas de CLK-06-A3/CLK-07.
