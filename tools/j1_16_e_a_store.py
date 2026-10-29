#!/usr/bin/env python3
"""J1.16-E-A: measure CPC scalar A after L10, before L20 via STOP L15.

No native REAL5 implementation; no fabricated floating point. Genuine Caprice32
SNA is temporary. Only bounded variable RAM windows and attestations are archived.
"""
import argparse
import configparser
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/oracles"))
import token_ram_oracle as cpc

SOURCE = ROOT / "tests/oracles/inputs/j1_16_a"
HISTORY = ROOT / "tests/fixtures/cpc6128/j1_16_real5_scalar"
CASES = ("R_ZERO", "R_ONE", "R_NEG_ONE")
ORIGINAL_SHA = {
    "R_ZERO": "72ce77388872a581b5264111651e9f8731c4f445587d54049ab24a6d602cea0a",
    "R_ONE": "6006d23f5cd752a02763abdd7ef3f5a1604fa71dbe87c3259cf029172bfe4e68",
    "R_NEG_ONE": "0021d791866d0d37c30da31dc9b147187ac5c48ac76fc98d3cbfe7ce8c1f0d08",
}
PRINTER_SHA = {
    "R_ZERO": "599e8a6c46a024ba4d2882b33a7f9a631c06fb4bc994129c6a1603f839b2da66",
    "R_ONE": "7d86a31a45b2e1f6cbaec323f0cc3c6c42fcc8efe0c7320de54b401f44cbee1b",
    "R_NEG_ONE": "d33b69661e641c25f83f1257283260ded56f7a58acfb482338b89908251e1d44",
}
L10 = {
    "R_ZERO": bytes.fromhex("0B 00 0A 00 0D 00 00 C1 EF 0E 00"),
    "R_ONE": bytes.fromhex("0B 00 0A 00 0D 00 00 C1 EF 0F 00"),
    "R_NEG_ONE": bytes.fromhex("0C 00 0A 00 0D 00 00 C1 EF F5 0F 00"),
}
L20 = bytes.fromhex("0B 00 14 00 BF 20 0D 00 00 C1 00")
EXACT_SOURCES = {
    "R_ZERO": b"10 A=0\n20 PRINT A\n30 PRINT #8,A\n40 END\n",
    "R_ONE": b"10 A=1\n20 PRINT A\n30 PRINT #8,A\n40 END\n",
    "R_NEG_ONE": b"10 A=-1\n20 PRINT A\n30 PRINT #8,A\n40 END\n",
}
PINNED_MANIFEST = "d219da77fca0ec619565c8499583157f669532109d0c1f3e1959f2e53d697214"
# Independent anchor is intentionally unset until the genuine CPC capture.
# Initial acquisition is unsealed; a follow-up commit pins each real
# window SHA-256 here, OUTSIDE the archive's mutable metadata chain.
SEALED_E_A_WINDOWS = {
    "R_ZERO": {"original": None, "repeat": None},
    "R_ONE": {"original": None, "repeat": None},
    "R_NEG_ONE": {"original": None, "repeat": None},
}

class Bad(ValueError):
    pass

def check(ok, why):
    if not ok:
        raise Bad(why)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    check(path.is_file() and not path.is_symlink(), "MISSING_OR_SYMLINK " + str(path))
    return path.read_bytes()

def u16(raw, index):
    return int.from_bytes(raw[index:index + 2], "little")

def case_source(case):
    raw = read(SOURCE / (case.lower() + ".bas"))
    check(raw == EXACT_SOURCES[case], "SOURCE_NOT_HISTORICAL_" + case)
    return raw

def old_oracle(case):
    check(digest(read(HISTORY / "manifest.json")) == PINNED_MANIFEST,
          "ORIGINAL_MANIFEST_CHANGED")
    program = read(HISTORY / "original" / case / "program.bin")
    printer = read(HISTORY / "original" / case / "run/printer.dat")
    check(digest(program) == ORIGINAL_SHA[case], "ORIGINAL_PROGRAM_SHA_" + case)
    check(digest(printer) == PRINTER_SHA[case], "ORIGINAL_PRINTER_SHA_" + case)
    nums, rows = cpc.records(program)
    check(nums == [10, 20, 30, 40], "HISTORICAL_LINES_" + case)
    check(program[:len(L10[case])] == L10[case] and
          program[rows[1]["offset"]:rows[1]["offset"] + rows[1]["length"]] == L20,
          "HISTORICAL_RECORD_" + case)
    return program

def same_except_opaque_cache(observed, original, positions):
    if len(observed) != len(original):
        return False
    return all(a == b for i,(a,b) in enumerate(zip(observed, original))
               if i not in positions)

def stopped_source(case):
    raw = case_source(case)
    # Same R_ZERO / R_NEG_ONE witnesses, only a STOP boundary inserted.
    # L10 and L20 remain byte-identical to the immutable CPC original.
    return raw.replace(b"20 PRINT A\n", b"15 STOP\n20 PRINT A\n", 1)

def inspect_snapshot(snap, case):
    check(len(snap) == cpc.HEADER + cpc.RAM_BYTES, "SNA_SIZE")
    check(snap[:8] == b"MV - SNA" and snap[0x10] == 3 and
          u16(snap, cpc.SNA_RAM_KB) == 128 and snap[cpc.SNA_MODEL] == 2 and
          snap[cpc.SNA_RAM_CONFIG] & 7 == 0, "SNA_MODEL_BANK")
    ram = memoryview(snap)[cpc.HEADER:]
    pointers = {k:u16(ram,off) for k,off in
                (("program_base",0xae64),("program_end",0xae66),
                 ("scalar_start",0xae68),("array_start",0xae6a),
                 ("array_end",0xae6c))}
    start, end = pointers["scalar_start"], pointers["array_start"]
    check(0x016f <= pointers["program_base"] < pointers["program_end"] <= start
          <= end <= pointers["array_end"] < 0xac00,
          "RAM_POINTER_ORDER")
    prog = bytes(ram[pointers["program_base"] + 1:pointers["program_end"]])
    nums, recs = cpc.records(prog)
    check(nums == [10, 15, 20, 30, 40], "STOP_LINE_OR_ORDER_MISSING")
    token = [prog[k["offset"]:k["offset"]+k["length"]] for k in recs]
    check(same_except_opaque_cache(token[0], L10[case], (5,6)) and
          same_except_opaque_cache(token[2], L20, (7,8)),
          "ROM_RECORD_L10_L20_DIVERGENCE")
    # CE was observed from the genuine CPC STOP token, not guessed from ROM.
    check(token[1] == bytes.fromhex("06 00 0F 00 CE 00"),
          "STOP_RECORD_MISSING")
    window = bytes(ram[start:end])
    check(0 < len(window) <= 128, "SCALAR_WINDOW_EMPTY_OR_TOO_LONG")
    # Parse only a single bounded scalar candidate. This parser MUST NOT
    # synthesize sign bits or infer them from F5 or from printer output.
    identified = (len(window) == 9 and window[2] == 0xc1 and window[3] == 4)
    return {
        "pointers": pointers,
        "instrumented_program_hex": prog.hex(" ").upper(),
        "stop_line_hex": token[1].hex(" ").upper(),
        "post_run_l10_hex": token[0].hex(" ").upper(),
        "post_run_l20_hex": token[2].hex(" ").upper(),
        "instrumented_program_sha256": digest(prog),
        "snapshot_sha256": digest(snap),
        "snapshot_header_first_16_hex": snap[:16].hex(" ").upper(),
        "window_sha256": digest(window),
        "window_hex": window.hex(" ").upper(),
        "window_length": len(window),
        "entry_link_hex": window[:2].hex(" ").upper(),
        "name_byte_hex": f"{window[2]:02X}" if len(window) >= 3 else None,
        "type_byte_hex": f"{window[3]:02X}" if len(window) >= 4 else None,
        "value_offset": start+4 if identified else None,
        "value_hex": window[4:9].hex(" ").upper() if identified else None,
        "classification": "STORE_SCALAR_REAL5_OBSERVED" if identified else "STORE_UNVERIFIED",
    }, window

def config_capture(cap, session, tmp):
    cfg = configparser.ConfigParser(interpolation=None)
    check(bool(cfg.read(cap / "cap32.cfg")), "CAPRICE_CONFIG_MISSING")
    cfg["system"].update(model="2",ram_size="128",speed="4",auto_pause="0",
                         printer="1",mf2="0",keyboard="0",boot_time="42",
                         limit_speed="0",resources_path=str(cap/"resources"))
    cfg["control"]["kbd_layout"]="0"
    cfg["sound"]["enabled"]="0"
    cfg["video"].update(scr_style="1",scr_window="1")
    cfg["file"]["printer_file"]=str(session/"printer.dat")
    cfg["file"]["snap_path"]=str(tmp)
    cfg["file"]["sdump_dir"]=str(session)
    cfg["rom"]["rom_path"]=str(cap/"rom")
    cfg["rom"]["slot07"]="amsdos.rom"
    cfg["rom"]["rom_mf2"]=""
    path=session/"cap32.cfg"
    with path.open("w") as f:
        cfg.write(f, space_around_delimiters=False)
    return path

def acquire(cap, output):
    check(not output.exists(), "OUTPUT_EXISTS")
    check(digest(read(cap/"rom/cpc6128.rom")) == cpc.ROM_SHA,
          "ROM_SHA_MISMATCH")
    pin = subprocess.check_output(["git","-C",str(cap),"rev-parse","HEAD"],text=True).strip()
    check(pin == cpc.PIN,"CAPRICE_PIN_MISMATCH")
    check((cap/"cap32").is_file(),"PINNED_EXECUTABLE_NOT_FOUND")
    head = subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],text=True).strip()
    manifest = {"schema_version":1,"phase":"J1.16-E-A",
                "classification":"STORE_UNVERIFIED",
                "acquisition_head_sha":head,
                "acquisition_run_id":os.environ.get("GITHUB_RUN_ID","LOCAL"),
                "caprice_commit":pin,"rom_sha256":cpc.ROM_SHA,
                "historical_manifest_sha256":PINNED_MANIFEST,
                "stop_instrumentation":"INSERT_ONLY_15_STOP_KEEP_L10_L20",
                "cases":{}}
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="j116-e-a-sna-") as td:
        snaps = Path(td)
        for case in CASES:
            old_oracle(case)
            raw = stopped_source(case)
            results = []
            for iteration in (0,1):
                label = ("original","repeat")[iteration]
                session = output/label/case
                session.mkdir(parents=True)
                snapshot_dir = snaps/(label+"-"+case)
                snapshot_dir.mkdir()
                cfg = config_capture(cap,session,snapshot_dir)
                commands = raw.decode("ascii").splitlines()+[
                    "RUN", "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT CAP32_EXIT"]
                # Pinned Caprice32 argparse cannot spell CAP32_SNAPSHOT;
                # form feed 0x0c 0x0d is its genuine keyboard event.
                cli = ["xvfb-run","-a",str(cap/"cap32"),"-c",str(cfg)]
                for item in commands:
                    cli.extend(["-a", item.replace("CAP32_SNAPSHOT","\x0c\x0d")])
                env = dict(os.environ,SDL_AUDIODRIVER="dummy",SDL_VIDEODRIVER="x11")
                task = subprocess.run(cli,cwd=cap,env=env,capture_output=True,
                                      timeout=75,check=False)
                check(task.returncode==0,
                      "CAPRICE_RUN_FAILED_"+case+" "+repr(task.stderr[-400:]))
                snapshots=list(snapshot_dir.glob("*.sna"))
                check(len(snapshots)==1,"STOP_SNAPSHOT_MISSING_"+case)
                snap=read(snapshots[0])
                data,window=inspect_snapshot(snap,case)
                printed=(session/"printer.dat").read_bytes() if (session/"printer.dat").exists() else b""
                check(printed==b"","PRINT_BEFORE_STOP_"+case)
                pictures=list(session.glob("screenshot_*.png"))
                check(len(pictures)==1 and read(pictures[0]).startswith(b"\x89PNG\r\n\x1a\n"),
                      "STOP_SCREENSHOT_MISSING_"+case)
                png=pictures[0]
                png.rename(session/"stop.png")
                (session/"window.bin").write_bytes(window)
                # Absolute runner paths in config are ephemeral, never evidence.
                cfg.unlink()
                if (session/"printer.dat").exists():
                    (session/"printer.dat").unlink()
                record = {"case":case,"session":label,
                          "source_sha256":digest(case_source(case)),
                          "instrumented_source_sha256":digest(raw),
                          "historical_program_sha256":ORIGINAL_SHA[case],
                          "historical_printer_sha256":PRINTER_SHA[case],
                          "commands":commands,
                          "sequence":["LIST_EDIT","RUN","EXEC_L10",
                                      "STOP_L15","CAPTURE_SNA","PRINT_L20_NOT_RUN"],
                          "printer_bytes_before_print":0,
                          "stop_png_sha256":digest(read(session/"stop.png")),
                          **data}
                (session/"capture.json").write_text(json.dumps(record,sort_keys=True,indent=2)+"\n")
                # Snapshot removed at exit; do not archive ROM, CPU SNA or log.
                results.append(record)
                print("J1.16-E-A",case,label,"STORE_WINDOW",data["window_hex"],
                      "VAR_REAL5",data["value_hex"],"ADDR",data["value_offset"],
                      "CLASS",data["classification"],flush=True)
            check(results[0]["window_hex"]==results[1]["window_hex"],
                  "TWO_INDEPENDENT_STORE_WINDOWS_DISAGREE_"+case)
            check(results[0]["value_hex"]==results[1]["value_hex"],
                  "TWO_INDEPENDENT_REAL5_VALUES_DISAGREE_"+case)
            manifest["cases"][case]={"original":digest(read(output/"original"/case/"capture.json")),
                                    "repeat":digest(read(output/"repeat"/case/"capture.json")),
                                    "equal_value":True}
    # Six genuine processes, three independently recognized scalar windows.
    # Do not derive store bytes from tokens or the printer.
    records=[json.loads(read(output/label/case/"capture.json"))
             for case in CASES for label in ("original","repeat")]
    if len(records)==6 and all(
            rec["classification"]=="STORE_SCALAR_REAL5_OBSERVED" for rec in records):
        manifest["classification"]="STORE_SCALAR_REAL5_OBSERVED"
    (output/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    verify(output)
    print("J1.16-E-A ACQUIRED",manifest["classification"],"HEAD",head,flush=True)

def verify(root, permanent=False):
    # Fresh CPC acquisition: check self-consistency and repeatability, not
    # the historical sessions' variable metadata or SHA. Permanent sealed
    # archive: additionally enforce independent immutable window pins.
    m=json.loads(read(root/"manifest.json"))
    check(m["schema_version"]==1 and m["phase"]=="J1.16-E-A" and
          m["historical_manifest_sha256"]==PINNED_MANIFEST and
          m["caprice_commit"]==cpc.PIN and m["rom_sha256"]==cpc.ROM_SHA and
          m["stop_instrumentation"]=="INSERT_ONLY_15_STOP_KEEP_L10_L20" and
          set(m["cases"])==set(CASES),"MANIFEST_PROVENANCE")
    cases={}
    for case in CASES:
        old_oracle(case)
        runs=[]
        for session in ("original","repeat"):
            d=root/session/case
            b=read(d/"capture.json")
            check(digest(b)==m["cases"][case][session],
                  "CAPTURE_SHA_MISMATCH_"+case)
            item=json.loads(b)
            window=read(d/"window.bin")
            if permanent:
                check(isinstance(SEALED_E_A_WINDOWS[case][session], str) and
                      len(SEALED_E_A_WINDOWS[case][session])==64,
                      "SEALED_E_A_PINS_NOT_ESTABLISHED")
                check(digest(window)==SEALED_E_A_WINDOWS[case][session],
                      "SEALED_E_A_ARCHIVE_MISMATCH_"+case+"_"+session)
            check(item["case"]==case and item["session"]==session and
                  item["historical_program_sha256"]==ORIGINAL_SHA[case] and
                  item["historical_printer_sha256"]==PRINTER_SHA[case] and
                  item["source_sha256"]==digest(case_source(case)) and
                  item["instrumented_source_sha256"]==digest(stopped_source(case)),
                  "CASE_OR_SOURCE_PROVENANCE_"+case)
            check(item["sequence"]==["LIST_EDIT","RUN","EXEC_L10","STOP_L15",
                  "CAPTURE_SNA","PRINT_L20_NOT_RUN"] and
                  item["printer_bytes_before_print"]==0 and
                  item["commands"][-2:] == ["RUN",
                      "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT CAP32_EXIT"],
                  "CHRONOLOGY_INVALID_"+case)
            check(item["window_sha256"]==digest(window) and
                  item["window_length"]==len(window) and
                  item["window_hex"]==window.hex(" ").upper(),
                  "STORE_WINDOW_HASH_OR_BYTES_"+case)
            ptr=item["pointers"]
            check(set(ptr)=={"program_base","program_end","scalar_start",
                             "array_start","array_end"} and
                  0x016f<=ptr["program_base"]<ptr["program_end"]<=ptr["scalar_start"]<=
                  ptr["array_start"]<=ptr["array_end"]<0xac00 and
                  ptr["array_start"]-ptr["scalar_start"]==len(window),
                  "SCALAR_POINTER_OFFSET_"+case)
            check(item["instrumented_program_sha256"]==
                  digest(bytes.fromhex(item["instrumented_program_hex"])),
                  "STOP_PROGRAM_SHA_"+case)
            nums,rows=cpc.records(bytes.fromhex(item["instrumented_program_hex"]))
            token=bytes.fromhex(item["instrumented_program_hex"])
            l10=token[:rows[0]["length"]]
            l20=token[rows[2]["offset"]:rows[2]["offset"]+rows[2]["length"]]
            check(nums==[10,15,20,30,40] and
                  same_except_opaque_cache(l10,L10[case],(5,6)) and
                  same_except_opaque_cache(l20,L20,(7,8)) and
                  l10.hex(" ").upper()==item["post_run_l10_hex"] and
                  l20.hex(" ").upper()==item["post_run_l20_hex"] and
                  token[rows[1]["offset"]:rows[1]["offset"]+rows[1]["length"]]
                  ==bytes.fromhex("06 00 0F 00 CE 00") and
                  item["stop_line_hex"]=="06 00 0F 00 CE 00",
                  "TOKEN_OR_STOP_CHRONOLOGY_"+case)
            check(digest(read(d/"stop.png"))==item["stop_png_sha256"] and
                  read(d/"stop.png").startswith(b"\x89PNG\r\n\x1a\n"),
                  "STOP_SCREEN_PROVENANCE_"+case)
            identifiable=(len(window)==9 and window[2]==0xc1 and window[3]==4)
            check(item["entry_link_hex"]==window[:2].hex(" ").upper() and
                  item["name_byte_hex"]==(f"{window[2]:02X}" if len(window)>=3 else None) and
                  item["type_byte_hex"]==(f"{window[3]:02X}" if len(window)>=4 else None) and
                  item["value_offset"]==(ptr["scalar_start"]+4 if identifiable else None) and
                  item["value_hex"]==(window[4:9].hex(" ").upper() if identifiable else None) and
                  item["classification"]==("STORE_SCALAR_REAL5_OBSERVED" if identifiable
                                          else "STORE_UNVERIFIED"),
                  "TYPE_NAME_DATA_LAYOUT_"+case)
            runs.append(item)
        check(runs[0]["window_hex"]==runs[1]["window_hex"] and
              runs[0]["value_hex"]==runs[1]["value_hex"] and
              m["cases"][case]["equal_value"] is True,
              "REPEAT_MISMATCH_"+case)
        cases[case]=runs
    expected=("STORE_SCALAR_REAL5_OBSERVED" if all(
        z["classification"]=="STORE_SCALAR_REAL5_OBSERVED"
        for pair in cases.values() for z in pair) else "STORE_UNVERIFIED")
    check(m["classification"]==expected,"FALSE_STORE_CLASSIFICATION")
    print("J1.16-E-A VERIFIED",expected,
          " ".join(case+"="+cases[case][0]["value_hex"] for case in CASES),
          flush=True)


def mutations(root, permanent=False):
    # All tests mutate *clones*. Preserve and rehash the real input archive
    # at the end; no negative test can rewrite genuine sealed bytes.
    protected = [root/"manifest.json"]
    protected += [root/session/case/name for case in CASES
                  for session in ("original", "repeat")
                  for name in ("window.bin", "capture.json", "stop.png")]
    protected_sha = {str(p.relative_to(root)):digest(read(p)) for p in protected}
    # Test directly against a genuine, newly acquired archive. Each clone
    # falsifies one axis; detection must precede any claim of observation.
    import shutil
    for field in ("byte","name","type","offset","case","sha","chronology","stop_token"):
        with tempfile.TemporaryDirectory(prefix="j116-da-mut-") as td:
            alt=Path(td)/"archive"
            shutil.copytree(root,alt)
            one=alt/"original"/"R_NEG_ONE"
            capture=one/"capture.json"
            item=json.loads(read(capture))
            if field=="byte":
                x=bytearray(read(one/"window.bin"));x[-1]^=1
                (one/"window.bin").write_bytes(x)
            elif field=="name":
                item["name_byte_hex"]="C2"
            elif field=="type":
                item["type_byte_hex"]="05"
            elif field=="offset":
                item["pointers"]["scalar_start"]+=1
            elif field=="case":
                item["case"]="R_ONE"
            elif field=="sha":
                item["window_sha256"]="0"*64
            elif field=="chronology":
                item["sequence"][3]="PRINT_L20_ALREADY_EXECUTED"
            elif field=="stop_token":
                item["stop_line_hex"]="06 00 0F 00 C0 00"
            if field!="byte":
                capture.write_text(json.dumps(item,sort_keys=True,indent=2)+"\n")
                m=json.loads(read(alt/"manifest.json"))
                m["cases"]["R_NEG_ONE"]["original"]=digest(read(capture))
                (alt/"manifest.json").write_text(json.dumps(m,sort_keys=True,indent=2)+"\n")
            try:
                verify(alt, permanent=permanent)
            except Bad:
                print("J1.16-E-A MUTATION_REJECTED",field,flush=True)
            else:
                raise Bad("MUTATION_ACCEPTED_"+field)

    if permanent:
        # C1: double-window coordinated forgery. Recompute ALL mutable local
        # SHA claims and metadata to recreate the original vulnerability.
        # Without a separate sealed pin, verify(..., permanent=False) PASSES.
        with tempfile.TemporaryDirectory(prefix="j116-da-collusive-") as td:
            alt=Path(td)/"archive"
            shutil.copytree(root,alt)
            m=json.loads(read(alt/"manifest.json"))
            for session in ("original","repeat"):
                directory=alt/session/"R_NEG_ONE"
                window=bytearray(read(directory/"window.bin"))
                check(len(window)==9 and window[2:4]==bytes.fromhex("C1 04"),
                      "COORDINATED_TEST_BAD_BASELINE")
                window[7]^=1  # actual fourth REAL5 byte; same in both sessions
                forged=bytes(window)
                (directory/"window.bin").write_bytes(forged)
                capture_file=directory/"capture.json"
                item=json.loads(read(capture_file))
                item["window_hex"]=forged.hex(" ").upper()
                item["window_length"]=len(forged)
                item["window_sha256"]=digest(forged)
                item["value_hex"]=forged[4:9].hex(" ").upper()
                capture_file.write_text(json.dumps(item,sort_keys=True,indent=2)+"\n")
                m["cases"]["R_NEG_ONE"][session]=digest(read(capture_file))
            (alt/"manifest.json").write_text(json.dumps(m,sort_keys=True,indent=2)+"\n")
            # Regression assertion: the coordinated fake is self-consistent.
            # Only the independent archive anchor may stop its promotion.
            verify(alt, permanent=False)
            try:
                verify(alt, permanent=True)
            except Bad as e:
                check(str(e).startswith("SEALED_E_A_ARCHIVE_MISMATCH"),
                      "COORDINATED_FORGERY_WRONG_REJECTION_"+str(e))
                print("J1.16-E-A COORDINATED_MUTATION_REJECTED "
                      "SEALED_E_A_ARCHIVE_MISMATCH",flush=True)
            else:
                raise Bad("COORDINATED_MUTATION_ACCEPTED")

    for p in protected:
        check(digest(read(p))==protected_sha[str(p.relative_to(root))],
              "ORIGINAL_ARCHIVE_MUTATED_"+str(p.relative_to(root)))
    print("J1.16-E-A ORIGINAL_ARCHIVE_UNCHANGED",len(protected),flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--caprice",type=Path)
    p.add_argument("--output",type=Path)
    p.add_argument("--evidence",type=Path)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--permanent",action="store_true",
                   help="require independent SHA-256 pins for the archived CPC windows")
    p.add_argument("--check-sources",action="store_true")
    args=p.parse_args()
    for case in CASES:
        old_oracle(case)
        stopped_source(case)
    if args.check_sources:
        print("J1.16-E-A IMMUTABLE_HISTORY_AND_SOURCES_PASS")
    if args.caprice:
        check(args.output is not None and args.evidence is None,"ACQUIRE_ARGS")
        acquire(args.caprice.resolve(),args.output.resolve())
    if args.evidence:
        verify(args.evidence.resolve(),permanent=args.permanent)
        if args.self_test:
            mutations(args.evidence.resolve(),permanent=args.permanent)
    check(not args.permanent or args.evidence is not None,
          "PERMANENT_REQUIRES_ARCHIVED_EVIDENCE")
    check(args.check_sources or args.caprice or args.evidence, "MISSING_MODE")

if __name__=="__main__":
    try:
        main()
    except (Bad,ValueError,OSError,subprocess.SubprocessError,KeyError,
            configparser.Error) as e:
        print("J1.16-E-A FAIL",e,file=sys.stderr)
        sys.exit(1)
