#!/usr/bin/env python3
"""Promote ONLY observed C4 CPC ROM RAM captures during the originating CI run.

This file is intentionally not an oracle: it consumes outputs already extracted
and validated by token_ram_oracle.py, without ever locating RAM using C99 data.
No full RAM snapshot, ROM, or screenshot is committed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/oracles"))
import token_ram_oracle as ram_oracle
import cpc_token_evidence as evidence

NEW = ("a_print_constants", "f_let_spacing", "f_mixed_case")
EXPECTED_SOURCES = {
    "a_print_constants": "7e7ae5a03b179326eef2f4b5eab4315d9d86432baa672a964666fb3af36bdfa3",
    "f_let_spacing": "1070c2ad379dc254bec45e48e35d2da7a57228d1f73c867f34d200485a0a0506",
    "f_mixed_case": "8b1c146b127009fec277794afa9ad8ee586ceeb8f0bac75c652ded59b73c34d6",
}
DIFF_MANIFEST = ROOT / "tests/fixtures/cpc6128/manifest.json"
ARCHIVE = ROOT / "tests/fixtures/cpc6128/token_ram"
STATUS = ROOT / "docs/PROJECT_STATUS.md"
REPORT = ROOT / "docs/J0.24-C4-extended-token-oracle.md"


def require(test, message):
    if not test:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--run-id", type=int, required=True)
    args = p.parse_args()
    require(args.run_id > 0, "invalid originating CI run")
    base = args.evidence.resolve()
    manifest = load(base / "manifest.json")
    evidence.validate(base, manifest)
    require(len(manifest["captures"]) == 5, "expected five independent captures")
    prior = load(ARCHIVE / "manifest.json")
    require(len(prior["cases"]) == 2 and "phase" not in prior,
            "only original C3 manifest can be promoted")
    evidence.validate_permanent(ROOT, prior)
    require({c["id"] for c in prior["cases"]} == set(evidence.C3_SHA),
            "historical archive altered")
    diff = load(DIFF_MANIFEST)
    require(len(diff["cases"]) >= 8, "differential cases missing")
    cases = {case["id"]: case for case in diff["cases"]}
    now = datetime.now(timezone.utc).isoformat()
    note_rows = []
    for cap in manifest["captures"]:
        name = cap["case"]
        folder = base / name
        source_rel, numbers = ram_oracle.CASES[name]
        srcpath = ROOT / "tests/fixtures/cpc6128" / source_rel
        raw_source = srcpath.read_bytes()
        require(evidence.sha(raw_source) == cap["source_sha256"],
                "acquisition source differs from frozen repository")
        if name in evidence.C3_SHA:
            c3 = evidence.C3_SHA[name]
            require(evidence.sha((folder / "program.bin").read_bytes()) == c3 and
                    evidence.sha((folder / "c99.bin").read_bytes()) == c3,
                    "reacquired original C3 program changed")
            continue
        require(name in NEW and evidence.sha(raw_source) == EXPECTED_SOURCES[name],
                "unexpected or changed C4 source")
        require(cases[name]["source_sha256"] == EXPECTED_SOURCES[name] and
                cases[name]["observations"] == {},
                "C4 differential record was already populated")
        rec = cap["region"]
        cpc = (folder / "program.bin").read_bytes()
        c99 = (folder / "c99.bin").read_bytes()
        report = cap["comparison"]
        exact, detail = evidence.compare(cpc, c99)
        require(report["classification"] == ("MATCH_EXACT" if exact else "DIFF") and
                report["first_difference"] == detail, "classification falsified")
        path = ARCHIVE / name
        require(not path.exists(), "refusing to overwrite promoted capture")
        path.mkdir()
        (path / "program.bin").write_bytes(cpc)
        (path / "c99.bin").write_bytes(c99)
        record = {
            "id": name,
            "source_path": "tests/fixtures/cpc6128/" + source_rel,
            "source_sha256": EXPECTED_SOURCES[name],
            "command_sequence": "numbered source; LIST; CAP32_DELAY twice; CAP32_SCRNSHOT; CAP32_SNAPSHOT; CAP32_EXIT; no RUN",
            "program_path": "tests/fixtures/cpc6128/token_ram/" + name + "/program.bin",
            "program_sha256": evidence.sha(cpc),
            "program_bytes": len(cpc),
            "c99_path": "tests/fixtures/cpc6128/token_ram/" + name + "/c99.bin",
            "c99_sha256": evidence.sha(c99),
            "c99_bytes": len(c99),
            "start_pointer_ram": 0xAE64,
            "end_pointer_ram": 0xAE66,
            "base_pointer_value": rec["base_pointer_value"],
            "program_start_cpc": rec["start_address"],
            "program_end_exclusive_cpc": rec["end_exclusive"],
            "snapshot_header_length": 256,
            "snapshot_program_file_offset": rec["snapshot_program_offset"],
            "ram_bank": 0,
            "line_numbers": numbers,
            "line_record_lengths": [r["length"] for r in rec["records"]],
            "line_terminator_hex": "00",
            "program_terminator_hex": "0000",
            "original_list_png_sha256": evidence.sha((folder / "list.png").read_bytes()),
            "comparison": report["classification"],
            "first_difference": detail,
            "normalization": "none",
            "raw_acquisition_preserved": True,
            "acquisition": {
                "workflow": "J0.24-C4 one-shot import",
                "run_id": args.run_id,
                "run_url": "https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/" + str(args.run_id),
                "artifact_name": "cpc6128-c4-original-evidence",
                "captured_at": manifest["generated_at"],
                "caprice32_commit": ram_oracle.PIN,
                "rom_sha256": ram_oracle.ROM_SHA,
                "source_sha256": EXPECTED_SOURCES[name],
            },
        }
        prior["cases"].append(record)
        if "TOKENS" not in cases[name]["operations"]:
            cases[name]["operations"].append("TOKENS")
        cases[name]["observations"]["TOKENS"] = {
            "path": "token_ram/" + name + "/program.bin",
            "sha256": record["program_sha256"],
            "origin": "cpc6128-rom-basic11",
            "captured_at": manifest["generated_at"],
            "method": (
                "Caprice32 pinned 8c778bf; LIST then temporary SNA before RUN; "
                "pointer &AE64/&AE66; RAM &%04X–&%04X; GitHub Actions #%d; no full snapshot retained"
                % (rec["start_address"], rec["end_exclusive"], args.run_id)
            ),
            "media": "binary",
            "comparison": "exact-bytes",
            "expected_classification": record["comparison"],
            "program_region": {
                "offset": 0,
                "length": len(cpc),
                "container": "raw-ram-export",
                "header_bytes": 0,
                "memory_layout": "contiguous-cpc-ram-records",
            }
        }
        diff_text = "" if exact else " ; first offset " + str(detail["first_offset"])
        note_rows.append(
            "| `%s` | `&%04X–&%04X` (fin exclue) | %d | `%s` | %s%s |"
            % (name, rec["start_address"], rec["end_exclusive"], len(cpc),
               record["program_sha256"], record["comparison"], diff_text)
        )
    require(len(note_rows) == 3 and len(prior["cases"]) == 5,
            "promotion must add exactly three cases")
    prior["phase"] = "J0.24-C4"
    prior["purpose"] = "Five authentic CPC6128 ROM BASIC 1.1 token RAM images (C3 immutable, C4 measured); eight-case J0.24 gate remains open"
    prior["c4_acquisition"] = {
        "workflow": "J0.24-C4 one-shot import",
        "run_id": args.run_id,
        "artifact_name": "cpc6128-c4-original-evidence",
        "captured_at": manifest["generated_at"],
        "caprice32_commit": ram_oracle.PIN,
        "rom_sha256": ram_oracle.ROM_SHA,
    }
    diff["purpose"] = "Five authentic ROM-backed TOKENS observations; LIST/RUN and remaining cases not presumed verified"
    diff["acquisition"]["status"] = "PARTIAL"
    diff["acquisition"]["reason"] = "Five distinct authentic token RAM acquisitions; >=8 distinct cases required; LIST/RUN still unverified."
    diff["acquisition"]["reference"] = "https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/" + str(args.run_id)
    diff["oracle"]["capture_method"] = "SNA v3 ephemeral, ROM pointers &AE64/&AE66; C3 run 40223535739 and C4 run " + str(args.run_id)
    save(ARCHIVE / "manifest.json", prior)
    save(DIFF_MANIFEST, diff)
    evidence.validate_permanent(ROOT, load(ARCHIVE / "manifest.json"))
    evidence.permanent_self_test(ROOT, load(ARCHIVE / "manifest.json"))
    intro = (
        "# J0.24-C4 — Oracle étendu des programmes tokenisés CPC 6128\n\n"
        "## Résultats réels de l'acquisition\n\n"
        "Acquisition native ROM BASIC 1.1 sur CPC 6128 via Caprice32 épinglé. "
        "Snapshot transitoire supprimé, sans exécution RUN, sans normalisation.\n\n"
        "| Cas | RAM CPC | Octets | SHA-256 programme ROM | Classification |\n"
        "|---|---|---:|---|---|\n"
        + "\n".join(note_rows)
        + "\n\n"
        "Les fichiers `program.bin` CPC et `c99.bin` sont conservés séparément. "
        "La classification ne porte que sur les octets tokenisés en RAM. "
        "Les opérations `LIST` (témoin visuel PNG seulement) et `RUN` "
        "(non lancé) demeurent non vérifiées par comparaison octet à octet.\n\n"
        "## Provenance\n\n"
        "- Workflow ponctuel : "
        + "https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/"
        + str(args.run_id) + "\n"
        "- Artefact éphémère : `cpc6128-c4-original-evidence` (fichiers, témoins et manifestes SHA)\n"
        "- Caprice32 commit `" + ram_oracle.PIN + "`, CPC6128 128 Kio, ROM `" + ram_oracle.ROM_SHA + "`\n"
        "- C3 immuable : `b_integer_scalar` et `c_integer_add`, SHA-256 historiques inchangés\n"
        "- Les fichiers source BASIC d'origine ne sont pas modifiés ; capture après `LIST`, avant `RUN`\n"
        "- RAM via `(&AE64)` et `(&AE66)`, y compris sentinelle de fin `00 00`\n"
        "- Aucun snapshot SNA, dump RAM complet ou fichier ROM archivé\n\n"
        "## Portée et suite\n\n"
        "`VERIFIED_CASES=5`, `TOKEN_BINARIES=5` après promotion et validation C99. "
        "**J0.24 demeure ouvert (5/8)** ; pas de J0.25 ni J1. "
        "Toute divergence `DIFF` est conservée et doit être étudiée avant une correction du cœur.\n"
    )
    REPORT.write_text(intro, encoding="utf-8")
    status = STATUS.read_text(encoding="utf-8")
    require("**J0.24-C4 —" not in status, "status already promoted")
    status += (
        "\n**J0.24-C4 — LIVRÉ POUR REVUE PILOTAGE :** "
        "Trois captures RAM CPC 6128 ROM BASIC 1.1 supplémentaires, pour cinq cas indépendants. "
        "Captures conservées avec SHA, adresses mesurées et comparaisons exactes ou divergentes ; "
        "C3 inchangé. [Acquisition C4](https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/"
        + str(args.run_id) + ") ; [Rapport C4](J0.24-C4-extended-token-oracle.md). "
        "**J0.24 reste ouvert (5/8) ; J0.25 et J1 non engagés.**\n"
    )
    STATUS.write_text(status, encoding="utf-8")
    print("PROMOTED C4 from ORIGINAL RUN", args.run_id, *note_rows, sep="\n")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        print("C4 PROMOTION FAILED:", exc, file=sys.stderr)
        sys.exit(1)
