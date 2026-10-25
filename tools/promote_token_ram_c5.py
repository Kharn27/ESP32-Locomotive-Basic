#!/usr/bin/env python3
"""J0.24-C5: promote ONLY independent CPC ROM captures on the originating runner.

The C3/C4 archives remain byte-for-byte untouched. No ROM or SNA is committed.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/oracles"))
import token_ram_oracle as oracle
import cpc_token_evidence as evidence

NEW = ("d_self_reference", "e_goto", "g_uninitialized")
SOURCES = {
    "d_self_reference": "618271a360f538c5a68bc3dae662dbce3d875fe01cacd2375e1e2bf3dc8d2e15",
    "e_goto": "a1c8557fb0b12d66062b7833e4128ef410515142538475cbd969a1fdc399671c",
    "g_uninitialized": "c9e530e3240bf828ec3fad99f4e8245e62772745a7eb2b2309d0f2843dba9b9f",
}
ARCHIVE = ROOT / "tests/fixtures/cpc6128/token_ram"
DIFF = ROOT / "tests/fixtures/cpc6128/manifest.json"
REPORT = ROOT / "docs/J0.24-C5-eight-case-oracle.md"
STATUS = ROOT / "docs/PROJECT_STATUS.md"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--artifact-id", type=int, required=True)
    p.add_argument("--artifact-digest", required=True)
    args = p.parse_args()
    require(args.run_id > 0 and args.artifact_id > 0 and
            re.fullmatch(r"sha256:[0-9a-f]{64}", args.artifact_digest),
            "invalid GitHub Actions artifact identity")
    base = args.evidence.resolve()
    acquisition = load(base / "manifest.json")
    evidence.validate(base, acquisition)
    require(len(acquisition["captures"]) == 8, "expected eight original CPC acquisitions")

    prior = load(ARCHIVE / "manifest.json")
    require(prior.get("phase") == "J0.24-C4" and len(prior["cases"]) == 5,
            "expected unmodified five-case C3/C4 archive")
    evidence.validate_permanent(ROOT, prior)
    historical = {case["id"]: case.copy() for case in prior["cases"]}

    diff = load(DIFF)
    cases = {case["id"]: case for case in diff["cases"]}
    require(all(name in cases and name in oracle.CASES for name in NEW),
            "missing differential or oracle source")
    acquired_at = acquisition["generated_at"]
    rows = []
    for capture in acquisition["captures"]:
        name = capture["case"]
        folder = base / name
        cpc = (folder / "program.bin").read_bytes()
        if name in historical:
            # Compare against the archived original, never overwrite or restage it.
            require(cpc == (ARCHIVE / name / "program.bin").read_bytes(),
                    "re-acquisition changed a previously accepted CPC image")
            require((folder / "c99.bin").read_bytes() ==
                    (ARCHIVE / name / "c99.bin").read_bytes(),
                    "re-acquisition changed a previously accepted C99 image")
            continue
        require(name in NEW, "unregistered new acquisition: " + name)
        source_rel, numbers = oracle.CASES[name]
        source_sha = evidence.sha((ROOT / "tests/fixtures/cpc6128" / source_rel).read_bytes())
        require(source_sha == SOURCES[name] == capture["source_sha256"] ==
                cases[name]["source_sha256"], "C5 source changed")
        require(cases[name]["observations"] == {} and
                "TOKENS" not in cases[name]["operations"],
                "C5 observation already promoted")
        reg = capture["region"]
        result = capture["comparison"]
        local_file = folder / "c99.bin"
        local = local_file.read_bytes() if local_file.is_file() else None
        exact, delta = evidence.compare(cpc, local) if local is not None else (False, None)
        classification = ("UNSUPPORTED" if local is None else
                          "MATCH_EXACT" if exact else "DIFF")
        require(result["classification"] == classification and
                result["first_difference"] == delta,
                "unverified comparison status or first divergence")
        require(reg["line_numbers"] == numbers and
                reg["start_address"] == reg["base_pointer_value"]+1 and
                reg["end_exclusive"] == reg["start_address"]+len(cpc),
                "invalid ROM pointer bounds")
        dest = ARCHIVE / name
        require(not dest.exists(), "new capture already archived")
        dest.mkdir()
        (dest / "program.bin").write_bytes(cpc)
        if local is not None:
            (dest / "c99.bin").write_bytes(local)
        record = {
            "id": name,
            "source_path": "tests/fixtures/cpc6128/" + source_rel,
            "source_sha256": source_sha,
            "command_sequence": "numbered source; LIST; CAP32_DELAY twice; CAP32_SCRNSHOT; CAP32_SNAPSHOT; CAP32_EXIT; no RUN",
            "program_path": "tests/fixtures/cpc6128/token_ram/" + name + "/program.bin",
            "program_sha256": evidence.sha(cpc), "program_bytes": len(cpc),
            "c99_path": ("tests/fixtures/cpc6128/token_ram/" + name + "/c99.bin") if local is not None else None,
            "c99_sha256": evidence.sha(local) if local is not None else None,
            "c99_bytes": len(local) if local is not None else None,
            "c99_rejection": result["c99_rejection"],
            "start_pointer_ram": 0xAE64, "end_pointer_ram": 0xAE66,
            "base_pointer_value": reg["base_pointer_value"],
            "program_start_cpc": reg["start_address"],
            "program_end_exclusive_cpc": reg["end_exclusive"],
            "snapshot_header_length": 256,
            "snapshot_program_file_offset": reg["snapshot_program_offset"],
            "ram_bank": 0, "line_numbers": numbers,
            "line_record_lengths": [row["length"] for row in reg["records"]],
            "line_terminator_hex": "00", "program_terminator_hex": "0000",
            "original_list_png_sha256": evidence.sha((folder / "list.png").read_bytes()),
            "comparison": classification, "first_difference": delta,
            "normalization": "none", "raw_acquisition_preserved": True,
            "acquisition": {
                "workflow": "J0.24-C5 one-shot import",
                "run_id": args.run_id,
                "run_url": "https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/" + str(args.run_id),
                "artifact_name": "cpc6128-c5-original-evidence",
                "artifact_id": args.artifact_id,
                "artifact_digest": args.artifact_digest,
                "captured_at": acquired_at,
                "caprice32_commit": oracle.PIN,
                "rom_sha256": oracle.ROM_SHA,
                "source_sha256": source_sha,
            },
        }
        prior["cases"].append(record)
        cases[name]["operations"].append("TOKENS")
        cases[name]["observations"]["TOKENS"] = {
            "path": "token_ram/" + name + "/program.bin",
            "sha256": record["program_sha256"],
            "origin": "cpc6128-rom-basic11", "captured_at": acquired_at,
            "method": ("Caprice32 pinned 8c778bf; LIST then temporary SNA before RUN; "
                       "pointer &AE64/&AE66; RAM &%04X–&%04X; GitHub Actions #%d; no complete snapshot retained"
                       % (reg["start_address"], reg["end_exclusive"], args.run_id)),
            "media": "binary", "comparison": "exact-bytes",
            "expected_classification": classification,
            "program_region": {"offset": 0, "length": len(cpc),
                               "container": "raw-ram-export", "header_bytes": 0,
                               "memory_layout": "contiguous-cpc-ram-records"},
        }
        rows.append((name, reg, record))
    require(len(rows) == 3 and len(prior["cases"]) == 8, "three authentic C5 additions required")
    require(all(prior["cases"][i] == case for i, case in enumerate(historical.values())),
            "old C3/C4 metadata changed")
    prior["phase"] = "J0.24-C5"
    prior["purpose"] = ("Eight original CPC6128 ROM BASIC 1.1 token RAM images; "
                       "token-only eight-case threshold, not J0.24 acceptance")
    prior["c5_acquisition"] = {
        "workflow": "J0.24-C5 one-shot import",
        "run_id": args.run_id,
        "artifact_name": "cpc6128-c5-original-evidence",
        "artifact_id": args.artifact_id,
        "artifact_digest": args.artifact_digest,
        "captured_at": acquired_at,
        "caprice32_commit": oracle.PIN,
        "rom_sha256": oracle.ROM_SHA,
    }
    diff["purpose"] = "Eight authentic ROM-backed TOKENS observations; LIST/RUN still unverified"
    diff["acquisition"]["status"] = "PARTIAL"
    diff["acquisition"]["reason"] = "8 original token RAM images; LIST/RUN and Xtensa not validated."
    diff["acquisition"]["date"] = acquired_at[:10]
    diff["acquisition"]["reference"] = (
        "https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/" + str(args.run_id))
    diff["oracle"]["capture_method"] += "; C5 run " + str(args.run_id)
    save(ARCHIVE / "manifest.json", prior)
    save(DIFF, diff)
    evidence.validate_permanent(ROOT, load(ARCHIVE / "manifest.json"))
    evidence.permanent_self_test(ROOT, load(ARCHIVE / "manifest.json"))

    table = "\n".join(
        "| `%s` | `&%04X–&%04X` | %d | `%s` | %s | %s |"
        % (name, reg["start_address"], reg["end_exclusive"], record["program_bytes"],
           record["program_sha256"], record["comparison"],
           "—" if record["first_difference"] is None else
           "offset %s: CPC %s / C99 %s" %
           (record["first_difference"]["first_offset"],
            record["first_difference"]["cpc_byte"],
            record["first_difference"]["c99_byte"]))
        for name, reg, record in rows)
    mismatches = [name for name, _, rec in rows if rec["comparison"] != "MATCH_EXACT"]
    report = (
        "# J0.24-C5 — Huit programmes CPC indépendants\n\n"
        "## Résultats expérimentaux C5\n\n"
        "| Cas | Adresses CPC [début, fin exclue] | Octets | SHA-256 CPC | Classification | Premier écart |\n"
        "|---|---|---:|---|---|---|\n" + table + "\n\n"
        "Les cinq captures C3/C4 et leurs octets ne sont pas modifiés. "
        "Les nouvelles images CPC ont été prélevées par pointeurs ROM (`&AE64`, `&AE66`) "
        "après saisie et `LIST`, **avant `RUN`**, dans des sessions distinctes. "
        "Chaque SNA complet est temporaire, supprimé ; aucun ROM/SNA n'est versé au dépôt.\n\n"
        "## Provenance\n\n"
        "- Caprice32 4.6.0, commit `" + oracle.PIN + "`, CPC 6128 128 Kio\n"
        "- ROM système SHA-256 : `" + oracle.ROM_SHA + "`\n"
        "- Run d'import d'origine : https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/" + str(args.run_id) + "\n"
        "- Artefact original : https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/" +
        str(args.run_id) + "/artifacts/" + str(args.artifact_id) + "\n"
        "- Digest GitHub Actions de cet artefact : `" + args.artifact_digest + "`\n"
        "- Capture UTC : `" + acquired_at + "`\n"
        "- Les manifestes détaillent SHA, longueurs par ligne, témoins PNG LIST et comparaisons C99.\n\n"
        "## Limites de la preuve\n\n"
        "Seule la **tokenisation en RAM** est comparée. Le témoin PNG LIST ne constitue "
        "pas une validation des octets de LIST. Aucun RUN n'a été exécuté pour ces captures. "
        "Les effets de GOTO, d'auto-référence, d'initialisation des variables et le formatage "
        "CPC ne sont pas couverts. Une classification UNSUPPORTED signifie que seul "
        "`program.bin` CPC est publié et aucun `c99.bin` n'a été inventé.\n\n"
        "La barrière `cpc_diff.py --require-independent` atteint huit cas distincts "
        "après promotion réussie, **sans valoir acceptation de J0.24**, J0 ou J1.\n\n"
        "## Divergences à arbitrer par Pilotage\n\n"
        + ("Cas non MATCH_EXACT : " + ", ".join("`" + s + "`" for s in mismatches)
           if mismatches else "Aucune divergence byte-à-byte observée dans les trois nouvelles acquisitions.")
        + "\n\n"
        "Hypothèse initiale pour chaque DIFF : différence d'encodage lexical "
        "ou de référence de ligne entre ROM et C99, à départager par analyse "
        "des octets originaux, sans modifier le moteur dans C5.\n")
    REPORT.write_text(report, encoding="utf-8")
    status = STATUS.read_text(encoding="utf-8")
    require("**J0.24-C5 —" not in status, "C5 already documented")
    status += (
        "\n**J0.24-C5 — LIVRÉ POUR REVUE PILOTAGE :** Trois acquisitions originales "
        "CPC 6128 additionnelles ; huit cas TOKEN RAM indépendants archivés. "
        "Classifications réelles, SHA et adresses dans [le rapport C5](J0.24-C5-eight-case-oracle.md). "
        "[Run historique](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/"
        + str(args.run_id) + "). **La barre 8/8 n'accepte ni J0.24 ni J0/J1 : "
        "LIST/RUN et la preuve ESP32/Xtensa restent ouverts.**\n")
    STATUS.write_text(status, encoding="utf-8")
    print("C5 PROMOTED", args.run_id, table, "DIVERGENCES", mismatches, sep="\n")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        print("C5 PROMOTION FAILED:", exc, file=sys.stderr)
        sys.exit(1)
