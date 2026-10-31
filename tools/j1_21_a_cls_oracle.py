#!/usr/bin/env python3
"""J1.21-A: genuine CPC6128 CLS oracle. No native-C or CYD implementation.

The acquisition is deliberately unavailable without the pinned real Caprice32
binary, ROM and source checkout. External SHA pins MUST be copied from the
independent GitHub Actions ORIGINAL artifact, not derived from the candidate
archive being verified. Incomplete pins always fail --permanent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "tests/oracles/inputs/j1_21_a"
PHASE = "J1.21-A"
BASE = "d9194aa7ce7c723165d9f5f4493c440678fb1fef"
SESSIONS = ("original", "repeat")
CASES = {
    "D_FULL": ("direct", "CLS", 1, "full"),
    "D_WINDOW": ("direct", "CLS", 1, "window"),
    "D_PAPER": ("direct", "CLS", 1, "paper"),
    "D_INK": ("direct", "CLS", 1, "ink"),
    "D_HASH0": ("direct", "CLS #0", 1, "full"),
    "D_HASH7": ("direct", "CLS #7", 1, "full"),
    "D_HASH8": ("direct", "CLS #8", 1, "full"),
    "N_FULL": ("numbered", "RUN", 1, "full"),
    "N_WINDOW": ("numbered", "RUN", 1, "window"),
    "N_PAPER": ("numbered", "RUN", 1, "paper"),
    "N_MODE0": ("numbered", "RUN", 0, "full"),
    "N_MODE2": ("numbered", "RUN", 2, "full"),
    "N_CURSOR": ("numbered", "RUN", 1, "cursor"),
    "N_DOUBLE": ("numbered", "RUN", 1, "full"),
}
SOURCE_LINES = {
    "D_FULL": ("10 REM CLS DIRECT KEEP", "20 END"),
    "D_WINDOW": ("10 REM WINDOW DIRECT KEEP", "20 END"),
    "D_PAPER": ("10 REM PAPER DIRECT KEEP", "20 END"),
    "D_INK": ("10 REM INK DIRECT KEEP", "20 END"),
    "D_HASH0": ("10 REM CLS HASH ZERO", "20 END"),
    "D_HASH7": ("10 REM CLS HASH SEVEN", "20 END"),
    "D_HASH8": ("10 REM CLS HASH EIGHT", "20 END"),
    "N_FULL": ("10 CLS", "20 END"),
    "N_WINDOW": ("10 CLS", "20 END"),
    "N_PAPER": ("10 PAPER 2", "20 CLS", "30 END"),
    "N_MODE0": ("10 CLS", "20 END"),
    "N_MODE2": ("10 CLS", "20 END"),
    "N_CURSOR": ("10 CLS", '20 PRINT "AFTER"', "30 END"),
    "N_DOUBLE": ("10 CLS:CLS", "20 END"),
}
GHCR = ("ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:"
        "7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c")
ROM_SHA256 = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
CAPRICE_COMMIT = "8c778bf072a06fb7c23b9cccd179041db7f79a52"
# FILL ONLY AFTER independent genuine GitHub Actions artifact download + verification:
SEALED_MANIFEST_SHA256 = ""
SEALED_ACQUISITION_HEAD = ""
SEALED_FILE_SHA256 = {}
CASE_FILES = ("program.bin", "capture.json", "list/caprice.log",
              "list/screen.png", "list/printer.dat", "run/caprice.log",
              "run/screen_0.png", "run/screen_1.png", "run/printer.dat")
# Rectangles are Caprice32 screenshot pixels, not the CYD's 320x240.
# Bounds are deliberately broad; only differential ROI data are reported.
ROIS = {
    "text_area": (64, 81, 704, 481),
    "upper_left": (64, 81, 200, 161),
    "window_center": (224, 201, 544, 401),
    "lower_right": (560, 401, 704, 481),
}


class Invalid(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise Invalid(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    need(path.is_file() and not path.is_symlink(), "FILE_ABSENT_OR_SYMLINK_" + str(path))
    return path.read_bytes()


def encoded(obj):
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def source(case):
    need(case in CASES, "UNKNOWN_CASE")
    expected = ("\n".join(SOURCE_LINES[case]) + "\n").encode("ascii")
    need(read(SOURCES / (case.lower() + ".bas")) == expected,
         "SOURCE_DRIFT_" + case)
    return expected


def check_sources():
    need(set(p.name for p in SOURCES.glob("*.bas")) ==
         {c.lower() + ".bas" for c in CASES}, "SOURCE_INVENTORY")
    need(len(CASES) >= 10 and len(SESSIONS) == 2, "MATRIX_TOO_SMALL")
    for c in CASES:
        source(c)
    return True


def check_head(head):
    need(re.fullmatch(r"[0-9a-f]{40}", head or "") is not None, "HEAD_FORMAT")
    actual = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    need(actual == head, "FALSE_HEAD_" + actual)
    need(subprocess.run(
        ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", BASE, head],
        capture_output=True).returncode == 0, "MISSING_BASE_ANCESTOR")
    return head


def ancestor(head):
    return re.fullmatch(r"[a-f0-9]{40}", head or "") is not None and \
           subprocess.run(
               ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", head, "HEAD"],
               capture_output=True).returncode == 0


def cpc_tools():
    sys.path.insert(0, str(ROOT / "tools"))
    import j1_18_a_ink_evidence as ink
    import j1_18_a_ink_pixels as rgb
    need(ink.cpc.PIN == CAPRICE_COMMIT and
         ink.cpc.ROM_SHA == ROM_SHA256 and ink.GHCR == GHCR,
         "ORACLE_PIN_DRIFT")
    return ink, rgb


def setup(case):
    _, _, mode, shape = CASES[case]
    commands = ["MODE " + str(mode), "INK 0,0", "INK 1,26",
                "INK 2,6", "INK 3,18", "PAPER 0", "PEN 1",
                "CLS", "NEW"]
    if shape == "ink":
        commands += ["INK 0,6", "INK 1,26"]
    if shape == "paper":
        commands += ["PAPER 2"]
    return commands


def preparation(case):
    shape = CASES[case][3]
    if shape == "window":
        # OUTSIDE is placed BEFORE WINDOW; INSIDE uses window-relative LOCATE.
        return ["LOCATE 2,2", 'PRINT "OUTSIDE"',
                "WINDOW 10,30,8,20", "LOCATE 2,3",
                'PRINT "INSIDE"']
    if shape == "cursor":
        return ["LOCATE 8,9", 'PRINT "CURSOR"', "LOCATE 4,4"]
    return ["LOCATE 1,15", 'PRINT "J121CLS"', "LOCATE 1,1"]


def command_list(case):
    return setup(case) + source(case).decode("ascii").splitlines() + [
        "LIST", "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT",
        "LIST #8", "CAP32_DELAY CAP32_EXIT"]


def command_run(case):
    return (setup(case) + source(case).decode("ascii").splitlines() +
            preparation(case) + [
                "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT",
                CASES[case][1],
                "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT",
                "PRINT #8,ERR", "PRINT #8,ERL",
                "LIST #8", "CAP32_DELAY CAP32_EXIT"])


def paths():
    return {f"{sess}/{case}/{file}"
            for sess in SESSIONS for case in CASES for file in CASE_FILES}


def histogram(rows, rect):
    x0, y0, x1, y1 = rect
    need(len(rows) >= y1 and 0 <= x0 < x1 <= 768 and
         0 <= y0 < y1 <= 540, "PNG_ROI_RANGE")
    hist = {}
    for y in range(y0, y1):
        for x in range(x0, x1):
            p = ",".join(str(i) for i in rows[y][3*x:3*x+3])
            hist[p] = hist.get(p, 0) + 1
    need(sum(hist.values()) == (x1-x0)*(y1-y0), "PNG_ROI_PIXELS")
    return hist


def pixel_evidence(before, after):
    need(len(before) == len(after) == 540, "PNG_DIMENSIONS")
    need(all(len(x) == 768*3 for x in before+after), "PNG_WIDTH")
    result = {}
    for name, (x0,y0,x1,y1) in ROIS.items():
        changes = 0
        for y in range(y0, y1):
            for x in range(x0, x1):
                a = before[y][3*x:3*x+3]
                b = after[y][3*x:3*x+3]
                changes += (a != b)
        result[name] = {
            "roi": [x0,y0,x1,y1],
            "changed_rgb_pixels": changes,
            "total_pixels": (x1-x0)*(y1-y0),
            "before_rgb_histogram": histogram(before,(x0,y0,x1,y1)),
            "after_rgb_histogram": histogram(after,(x0,y0,x1,y1)),
        }
    return result


def capture_case(cap, out, sess, case, temp, ink, rgb):
    dest = out/sess/case
    snaps = temp/(sess+"-"+case)
    snaps.mkdir()
    lcmd, rcmd = command_list(case), command_run(case)
    listmeta = ink.launch(cap, dest/"list", snaps, lcmd, True)
    files = list(snaps.glob("*.sna"))
    need(len(files) == 1, "SNAPSHOT_COUNT_"+case)
    expected_lines = [int(x.split(" ",1)[0]) for x in SOURCE_LINES[case]]
    program, region = ink.cpc.extract_snapshot(read(files[0]), expected_lines)
    nums, records = ink.cpc.records(program)
    need(nums == expected_lines, "RAM_LINE_NUMBERS_"+case)
    if CASES[case][0] == "numbered":
        target = 20 if case == "N_PAPER" else 10
        row = records[nums.index(target)]
        raw = program[row["offset"]:row["offset"]+row["length"]]
        need(0x8a in raw[4:], "CLS_ROM_TOKEN_8A_ABSENT_"+case)
    else:
        # Direct-mode CLS should NOT appear in the stored preservation witness.
        need(all(0x8a not in program[
            row["offset"]+4:row["offset"]+row["length"]]
            for row in records), "DIRECT_CLS_LEAKED_INTO_PROGRAM")
    (dest/"program.bin").write_bytes(program)
    listbytes = read(dest/"list/printer.dat")
    need(bool(listbytes), "LIST_PRINTER_EMPTY")
    runmeta = ink.launch(cap, dest/"run", temp, rcmd, True, shots=2)
    printer = read(dest/"run/printer.dat")
    lines = printer.splitlines(keepends=True)
    need(len(lines) >= 2, "ERR_ERL_PRINTER_MISSING")
    parsed = [ink.parse_integer(x) for x in lines[:2]]
    need(all(v is not None for v in parsed), "ERR_ERL_UNREADABLE")
    err, erl = [v["numeric_value"] for v in parsed]
    listed = b"".join(lines[2:])
    need(bool(listed), "POST_CLS_LIST_MISSING")
    # The printer's exact bytes, not an inferred CPC string, prove preservation.
    need(listed == listbytes, "PROGRAM_LIST_CHANGED_BY_CLS_"+case)
    a = rgb.png_rgb(dest/"run/screen_0.png")
    b = rgb.png_rgb(dest/"run/screen_1.png")
    measure = pixel_evidence(a,b)
    caprec = {
        "case":case, "session":sess, "phase":PHASE,
        "classification":"OBSERVED_IN_REAL_ACQUISITION",
        "source_sha256":sha(source(case)), "source_mode":CASES[case][0],
        "source_lines":list(SOURCE_LINES[case]), "setup":setup(case),
        "preparation":preparation(case),
        "commands":{"list":lcmd,"run":rcmd},
        "metadata":{"list":listmeta,"run":runmeta},
        "ram_sha256":sha(program),
        "ram_hex":program.hex(" ").upper(), "ram_region":region,
        "ram_lines":nums, "err":err,"erl":erl,
        "printer_sha256":sha(printer), "printer_hex":printer.hex(),
        "list_before_sha256":sha(listbytes),
        "list_after_sha256":sha(listed),
        "screens":{"before_sha256":sha(read(dest/"run/screen_0.png")),
                   "after_sha256":sha(read(dest/"run/screen_1.png")),
                   "before_rgb_sha256":sha(b"".join(a)),
                   "after_rgb_sha256":sha(b"".join(b))},
        "rois":measure,
        "cursor_position":"UNVERIFIED_UNLESS_POST_PROBE_ACQUIRED",
        "semantic_clear_window":"INCONCLUSIVE_PENDING_ROI_INSPECTION",
        "diagnostic_text":"UNVERIFIED_FROM_SCREEN",
        "post_run_instrumentation":"PRINT #8 ERR/ERL + LIST #8 AFTER SECOND SCREENSHOT",
        "screen_capture_is_not_rom_token_evidence":True,
        "rom_not_executed_on_esp32":True,
        "kind":"CPC6128_CAPRICE32_REAL_ONLY"
    }
    (dest/"capture.json").write_bytes(encoded(caprec))
    return caprec


def acquire(cap, out, head):
    need(not out.exists(), "DESTINATION_ALREADY_EXISTS")
    check_head(head)
    check_sources()
    ink,rgb = cpc_tools()
    version = ink.check_caprice(cap)
    out.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="j121-cls-sna-") as tmp:
        for sess in SESSIONS:
            for case in CASES:
                r = capture_case(cap,out,sess,case,Path(tmp),ink,rgb)
                print(PHASE,"CAPTURED",case,sess,"ERR",r["err"],"ERL",r["erl"],
                      "CHANGED",r["rois"]["text_area"]["changed_rgb_pixels"],flush=True)
    manifest = {
        "schema":1, "phase":PHASE, "acquisition_head":head,
        "run_id":os.environ.get("GITHUB_RUN_ID","LOCAL"),
        "origin":"CPC6128_REAL_CAPRICE32", "source_ref":BASE,
        "oracle":{"rom_sha256":ROM_SHA256,"caprice_commit":CAPRICE_COMMIT,
                  "ghcr":GHCR,"caprice_version":version,
                  "model":"CPC6128","basic":"1.1"},
        "cases":list(CASES), "sessions":list(SESSIONS),
        "files":{p:sha(read(out/p)) for p in sorted(paths())},
        "temporary_snapshots_archived":False, "native_changes":False,
        "observations":"PRE_AND_POST_CLS_PNG_TWO_SHOTS_SAME_PROCESS",
        "external_seals":"PENDING_FROM_ORIGINAL_ACTIONS_ARTIFACT",
    }
    (out/"manifest.json").write_bytes(encoded(manifest))
    verify(out,False)
    print(PHASE,"FRESH_28_SESSIONS_UNSEALED",
          "MANIFEST_SHA256",sha(read(out/"manifest.json")),flush=True)
    for p in sorted(paths()):
        print("EXTERNAL_FILE_SHA256",p,sha(read(out/p)),flush=True)


def verify(out, permanent=False):
    check_sources()
    need((out/"manifest.json").is_file(), "ARCHIVE_ABSENT")
    manifest_bytes=read(out/"manifest.json")
    m=json.loads(manifest_bytes)
    need(m.get("schema")==1 and m.get("phase")==PHASE and
         m.get("source_ref")==BASE and
         m.get("origin")=="CPC6128_REAL_CAPRICE32" and
         m.get("cases")==list(CASES) and m.get("sessions")==list(SESSIONS) and
         m.get("temporary_snapshots_archived") is False and
         m.get("native_changes") is False and
         m.get("external_seals")=="PENDING_FROM_ORIGINAL_ACTIONS_ARTIFACT" and
         m.get("oracle",{}).get("rom_sha256")==ROM_SHA256 and
         m.get("oracle",{}).get("caprice_commit")==CAPRICE_COMMIT and
         m.get("oracle",{}).get("ghcr")==GHCR, "MANIFEST_PROVENANCE")
    head=m.get("acquisition_head","")
    need(ancestor(head), "FAKE_HEAD_OR_MISSING_ANCESTOR")
    wanted=paths()
    actual={str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()}
    need(actual==wanted|{"manifest.json"}, "ARCHIVE_INVENTORY")
    need(set(m.get("files",{}))==wanted, "MANIFEST_FILE_KEYS")
    if permanent:
        need(re.fullmatch(r"[a-f0-9]{64}",SEALED_MANIFEST_SHA256) is not None and
             re.fullmatch(r"[a-f0-9]{40}",SEALED_ACQUISITION_HEAD) is not None and
             set(SEALED_FILE_SHA256)==wanted, "EXTERNAL_SEALS_NOT_ACQUIRED")
        need(head==SEALED_ACQUISITION_HEAD and
             sha(manifest_bytes)==SEALED_MANIFEST_SHA256,
             "EXTERNAL_MANIFEST_OR_HEAD_MISMATCH")
    for name in sorted(wanted):
        raw=read(out/name)
        need(sha(raw)==m["files"][name], "MANIFEST_SHA_CHANGED_"+name)
        if permanent:
            need(sha(raw)==SEALED_FILE_SHA256[name],
                 "EXTERNAL_SHA_CHANGED_"+name)
    ink,rgb=cpc_tools()
    record={}
    for sess in SESSIONS:
        for case in CASES:
            dest=out/sess/case
            d=json.loads(read(dest/"capture.json"))
            need(d.get("phase")==PHASE and d.get("case")==case and
                 d.get("session")==sess and
                 d.get("source_sha256")==sha(source(case)) and
                 d.get("source_lines")==list(SOURCE_LINES[case]) and
                 d.get("source_mode")==CASES[case][0] and
                 d.get("setup")==setup(case) and
                 d.get("preparation")==preparation(case) and
                 d.get("kind")=="CPC6128_CAPRICE32_REAL_ONLY" and
                 d.get("commands")=={"list":command_list(case),"run":command_run(case)} and
                 d.get("metadata",{}).get("list",{}).get("commands")==command_list(case) and
                 d.get("metadata",{}).get("run",{}).get("commands")==command_run(case),
                 "CAPTURE_COMMAND_PROVENANCE_"+case+sess)
            prog=read(dest/"program.bin")
            nums,rows=ink.cpc.records(prog)
            expected_nums=[int(x.split(" ",1)[0]) for x in SOURCE_LINES[case]]
            need(nums==expected_nums and d.get("ram_sha256")==sha(prog) and
                 d.get("ram_hex")==prog.hex(" ").upper() and
                 d.get("ram_lines")==nums, "RAM_"+case+sess)
            if CASES[case][0]=="numbered":
                target=20 if case=="N_PAPER" else 10
                r=rows[nums.index(target)]
                need(0x8a in prog[r["offset"]+4:r["offset"]+r["length"]],
                     "TOKEN_CLS_8A_"+case+sess)
            else:
                need(all(0x8a not in prog[
                    r["offset"]+4:r["offset"]+r["length"]] for r in rows),
                    "DIRECT_CLS_NOT_IN_STORED_PROGRAM")
            pre=read(dest/"list/printer.dat")
            raw=read(dest/"run/printer.dat")
            rows_printer=raw.splitlines(keepends=True)
            parsed=[ink.parse_integer(x) for x in rows_printer[:2]]
            need(len(parsed)==2 and all(x is not None for x in parsed) and
                 [x["numeric_value"] for x in parsed]==[d.get("err"),d.get("erl")],
                 "ERR_ERL_"+case+sess)
            need(d.get("printer_hex")==raw.hex() and
                 d.get("printer_sha256")==sha(raw) and
                 d.get("list_before_sha256")==sha(pre) and
                 d.get("list_after_sha256")==sha(b"".join(rows_printer[2:])) and
                 b"".join(rows_printer[2:])==pre,
                 "LIST_PROGRAM_PRESERVATION_"+case+sess)
            before=read(dest/"run/screen_0.png")
            after=read(dest/"run/screen_1.png")
            a=rgb.png_rgb(dest/"run/screen_0.png")
            b=rgb.png_rgb(dest/"run/screen_1.png")
            need(d.get("screens")=={
                "before_sha256":sha(before),"after_sha256":sha(after),
                "before_rgb_sha256":sha(b"".join(a)),
                "after_rgb_sha256":sha(b"".join(b))} and
                 d.get("rois")==pixel_evidence(a,b), "PNG_CRC_RGB_ROI_"+case+sess)
            for task in ("list","run"):
                log=read(dest/task/"caprice.log")
                need(log.startswith(b"exit code: 0\n"),"CPC_PROCESS_"+case+sess+task)
            record[(case,sess)] = d
    for case in CASES:
        a,b=record[case,"original"],record[case,"repeat"]
        need(a["ram_hex"]==b["ram_hex"] and a["err"]==b["err"] and
             a["erl"]==b["erl"] and a["list_before_sha256"]==b["list_before_sha256"] and
             a["rois"]==b["rois"] and
             a["screens"]["before_rgb_sha256"]==b["screens"]["before_rgb_sha256"] and
             a["screens"]["after_rgb_sha256"]==b["screens"]["after_rgb_sha256"] and
             a["metadata"]["list"]["started_utc"]!=b["metadata"]["list"]["started_utc"] and
             a["metadata"]["run"]["started_utc"]!=b["metadata"]["run"]["started_utc"],
             "INDEPENDENT_REPEAT_MISMATCH_"+case)
    return {"case_count":len(CASES),"sessions":len(CASES)*2,
            "seal":"EXTERNALLY_SEALED" if permanent else "UNSEALED",
            "classification":"OBSERVED"}


def falsifications(out, permanent=False):
    kinds=["ram","png","printer","capture","manifest","fake_head","repeat_swap"]
    if permanent:
        kinds.append("coordinated_rehash")
    original_sha=sha(read(out/"manifest.json"))
    for kind in kinds:
        with tempfile.TemporaryDirectory(prefix="j121-negative-") as temp:
            clone=Path(temp)/"clone"
            shutil.copytree(out,clone)
            victim=clone/"original"/"N_FULL"
            if kind=="ram":
                data=bytearray(read(victim/"program.bin")); data[-3]^=1
                (victim/"program.bin").write_bytes(data)
            elif kind=="png":
                data=bytearray(read(victim/"run/screen_1.png"));data[-1]^=1
                (victim/"run/screen_1.png").write_bytes(data)
            elif kind=="printer":
                (victim/"run/printer.dat").write_bytes(b"99\r\n0\r\n")
            elif kind=="capture":
                d=json.loads(read(victim/"capture.json"));d["err"]=99
                (victim/"capture.json").write_bytes(encoded(d))
            elif kind=="manifest":
                data=bytearray(read(clone/"manifest.json"));data[-2]^=1
                (clone/"manifest.json").write_bytes(data)
            elif kind=="fake_head":
                m=json.loads(read(clone/"manifest.json"))
                m["acquisition_head"]="0"*40
                (clone/"manifest.json").write_bytes(encoded(m))
            elif kind=="repeat_swap":
                other=clone/"repeat"/"N_FULL"/"run/screen_1.png"
                shutil.copyfile(other,victim/"run/screen_1.png")
                # Detection must be either byte SHA or source timestamp/pixel checks.
                if read(other)==read(victim/"run/screen_1.png"):
                    # Identical PNG bytes would be a non-discriminant swap.
                    data=bytearray(read(victim/"run/screen_1.png"));data[-1]^=1
                    (victim/"run/screen_1.png").write_bytes(data)
            elif kind=="coordinated_rehash":
                data=bytearray(read(victim/"program.bin"));data[-3]^=1
                (victim/"program.bin").write_bytes(data)
                m=json.loads(read(clone/"manifest.json"))
                path="original/N_FULL/program.bin"
                m["files"][path]=sha(read(victim/"program.bin"))
                (clone/"manifest.json").write_bytes(encoded(m))
            try:
                verify(clone,permanent)
            except (Invalid,ValueError,KeyError,IndexError,UnicodeError) as ex:
                print(PHASE,"FALSIFICATION_REJECTED",kind,str(ex)[:100],flush=True)
            else:
                raise Invalid("FALSIFICATION_ACCEPTED_"+kind)
    need(sha(read(out/"manifest.json"))==original_sha,"NEGATIVE_MUTATED_ORIGINAL")
    return len(kinds)


def local_tests():
    check_sources()
    need(len(paths())==14*2*len(CASE_FILES), "CASE_FILE_COUNT")
    need(all("CAP32_SCRNSHOT" in " ".join(command_run(c)) for c in CASES),
         "MISSING_SCREENSHOT")
    with tempfile.TemporaryDirectory(prefix="j121-noarchive-") as tmp:
        try:
            verify(Path(tmp),permanent=True)
        except Invalid as e:
            need(str(e)=="ARCHIVE_ABSENT","BAD_FAIL_CLOSED")
        else:
            raise Invalid("FALSE_PERMANENT_PASS")
    need(not SEALED_MANIFEST_SHA256 or len(SEALED_MANIFEST_SHA256)==64,
         "PARTIAL_MANIFEST_PIN")
    print(PHASE,"OFFLINE_CONTRACT_PASS",len(CASES),"CASES",flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check-sources",action="store_true")
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--acquire",type=Path)
    p.add_argument("--output",type=Path)
    p.add_argument("--head")
    p.add_argument("--evidence",type=Path)
    p.add_argument("--permanent",action="store_true")
    a=p.parse_args()
    need(a.check_sources or a.self_test or a.acquire or a.evidence,
         "OPERATION_REQUIRED")
    if a.check_sources:
        check_sources()
    if a.self_test and not a.evidence:
        local_tests()
    if a.acquire:
        need(a.output is not None and a.evidence is None, "ARGUMENTS")
        acquire(a.acquire.resolve(),a.output.resolve(),
                check_head(a.head or subprocess.check_output(
                    ["git","-C",str(ROOT),"rev-parse","HEAD"],text=True).strip()))
    if a.evidence:
        result=verify(a.evidence.resolve(),a.permanent)
        print(PHASE,"ARCHIVE_VERIFIED",result,flush=True)
        if a.self_test:
            print(PHASE,"NEGATIVES_REJECTED",falsifications(
                a.evidence.resolve(),a.permanent),flush=True)


if __name__=="__main__":
    try:
        main()
    except (Invalid,OSError,subprocess.SubprocessError,
            ValueError,KeyError,IndexError,UnicodeError) as exc:
        print(PHASE,"FAIL",str(exc),file=sys.stderr)
        sys.exit(1)
