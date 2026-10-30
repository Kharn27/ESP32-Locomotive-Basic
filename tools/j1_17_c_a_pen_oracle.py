#!/usr/bin/env python3
"""J1.17-C-A: independent CPC MODE1 PEN 5..14 acquisition, not a native fix.

The historical J1.17-A module is imported read-only for its proven Caprice32
launcher, SNA RAM extraction and byte-exact ERR/ERL printer protocol. This
module owns its own input matrix, captures, ROI checks and falsification gates.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import j1_17_a_pen_evidence as base
import j1_18_a_ink_pixels as rgb

PHASE = "J1.17-C-A"
BASE = "1d309b667272106f5ba1c85ca8347f25a88850d4"
BRANCH = "oracle/j1-17-c-a-pen-5-14-cpc"
EVIDENCE = ROOT / "tests/fixtures/cpc6128/j1_17_c_a_pen"
SOURCES = ROOT / "tests/oracles/inputs/j1_17_c_a"
SESSIONS = ("original", "repeat")
VALUES = (5,6,7,8,9,10,11,12,13,14,0,2,3)
CASES = {f"{context}{value:02d}": (context, value)
         for context in ("C", "D") for value in VALUES}
CONTROLLED = ["MODE 1", "INK 0,0", "INK 1,26", "INK 2,6",
              "INK 3,18", "PAPER 0", "PEN 1", "CLS", "NEW"]
DEFAULT = ["MODE 1", "PAPER 0", "PEN 1", "CLS", "NEW"]
# Filled in a separate, audited commit AFTER acquiring authentic GHCR records.
# External seals MUST NOT be inferred from the archive under verification.
EXTERNAL_MANIFEST_SHA256 = "1907f9203333c43c0a840e5b36f0aca6c792ab76bcc60a91937047cf68964be9"
EXTERNAL_RECORD_SHA256 = {
    "C05": {
        "original": "bac1fc830f8772b5f08014ddafcff3019816016d5afd5ff4874d1f3f1036001a",
        "repeat": "93570abb7c91990476a72cc1108e55f18486242f97bf2dcb177b0305fadc8042"
    },
    "C06": {
        "original": "b83dd9fe53dabe62e18fcf6aa40d825a525e213b1703fc62d3163046285d0441",
        "repeat": "d03be698cb7032349605828870df03dfd383d81c867eb1a655cc7a785bb8a6a9"
    },
    "C07": {
        "original": "d86b6baf236c373c6bce0f5098fa94302155c6f23d0a385a0382c4d6ec521ec4",
        "repeat": "78ed3960f324d9b9af864dbb5b77ee7af6ce5993030396002ba5de20b50fb61c"
    },
    "C08": {
        "original": "4f50e1def516240e010b10687dd6d9954858212fc472821be3a65e80ea4dc976",
        "repeat": "a9b3c2ea1fd3cbe35283abc5886ed90831b710657dcd0100cd13a825ee9a6173"
    },
    "C09": {
        "original": "8115435f1e9b3ed63dacaed2650bed2b0a3946f993a43528b1288e16f4f5fa5f",
        "repeat": "d854497468b517d61fd5753af99c87182ec9e5fef3082dd3ad13228a3b1afc68"
    },
    "C10": {
        "original": "592da56a96aaee86c4874523a214531d61bbb79058bc25557bd03dde37c95293",
        "repeat": "51d7eb3e70ec0fe968ef1730d1ba390b184ccdd521b92f466b66fab8f5fe4ae1"
    },
    "C11": {
        "original": "495b81c6cbfb8c8e42c676c85d0252b17fed158bcfd579ee41e5ead64a00bdf4",
        "repeat": "63a3477c20ec684ac2a256bf04491f77460a64d388e2c8fb600ce834c1df0764"
    },
    "C12": {
        "original": "e8236444be862f8202912369164927d570998ea05f4281501b792fa04503f9d8",
        "repeat": "b16f15216cdf549d191b89ce9ab03dd63c63c05e5740a06975ddb4dec8e3fb74"
    },
    "C13": {
        "original": "0a6fea0e3755bd0e0a3a06fce97566b6284853669da75d29caae0a8706e3b7fa",
        "repeat": "8a103a91f815fb6f7c174d031f8af22a40477f18d154493f795ff6c549a431fd"
    },
    "C14": {
        "original": "5a84f6453c5b4b8739cd16923ec465e6127f0699adffaa5cd499b881a5ae100b",
        "repeat": "3632259c867a75b84d8a26b8a2047f80948153fd91d0f8f226530406931ccc08"
    },
    "C00": {
        "original": "efa57c79df7c9105ae4ec395e03088b27f2f8e41cd53446da40ff7a60f8ac075",
        "repeat": "da9e870701f6701afc6149e4fa364d2700a15e18b985f8e54b2236f896c986e7"
    },
    "C02": {
        "original": "a7f24167a4ecf7bb21b4fc8e7455473e8adc0c6816e00682260aeacd04553870",
        "repeat": "9a70ed32f0ef41f5dc7e177162903a4942004d61ab3f4a400b4b520b366e159c"
    },
    "C03": {
        "original": "28d6a07f9920b0a85218359d09f8d8b90e289c8ce869015279b1e729299bf8f5",
        "repeat": "512801ccefb8427104cf9637d25a5c79b3acc70da0e48ed73828cc0c8255ed61"
    },
    "D05": {
        "original": "aa7d7a164ce1eb65c1bb3e30e2dd8922aee2bc7213060d313e0696e665e4c294",
        "repeat": "6cdd7696209b01f7f9665696e62231734badf36650acdfac6d2f6a72b282aa7e"
    },
    "D06": {
        "original": "36429d4c62deb736e51293c4afd983c6f1065e722de25fdbe99de5a184fe0881",
        "repeat": "e82891f88daa85569168b5fdf226636334e8f0738bf2cc2f935e564429a019d1"
    },
    "D07": {
        "original": "aa408d08199a9ee9ec89814186947c684116a7fd6c6f7a6625559e2a44c07a8b",
        "repeat": "df91c02fc49ddeacbff45b7405696f870f915d3a8e922753b967dbaacd6ee1ac"
    },
    "D08": {
        "original": "9cc292684fa5172fc45cb7eab325ac3cce9551a1dd658f582bf1c266fdb5391b",
        "repeat": "bedebbf55a03ceb73d73d01fb66fe8d87e25a53bf9101f873a66a6d9d049b4b6"
    },
    "D09": {
        "original": "b1581360f247c69e14682684ede5b871c402390949650177b4d173bbc29a2193",
        "repeat": "4200ef3840ca6ffa83f54043f1d153314d30f98be5cfb761daebe20c57a9f767"
    },
    "D10": {
        "original": "3fd86e5cca567f366b6c1c164d18427a5f60749a9a40ef7d6c68735dcc763de1",
        "repeat": "e8d8e2db387c9ab9a3f7a967e29d06a61a4fb537469e480f3934e062982313a3"
    },
    "D11": {
        "original": "cef1bba6f8e7edfab2d6170ed3c493e37b4f759fcc940d95f085b46e74a137fc",
        "repeat": "7acb14e49b73d05ef608cadc12e4ba5bb373d7e774b5cbeb4b218fe6bbd62f88"
    },
    "D12": {
        "original": "5d74d540b1bfcfc52be183e2160a266533fe8d017ae456deee47c7933a11a374",
        "repeat": "60680db365efa244e1da908b569d050a0eb1eeb30167585e236df001d1796a10"
    },
    "D13": {
        "original": "58f03d8ede3d06748ef81bfc8486c2d529f7193391007f35f25589ffa97b30a6",
        "repeat": "592720a6fff966fe46bba877178088642f7d6eeae830b165ee573b254fd6ace6"
    },
    "D14": {
        "original": "c01f0dd6ce4553919865080c5e0abb817a6577965cab2c378d5eb172e7a6804d",
        "repeat": "6cf1bb2295b4b87c0a452f17692d1d4a1ecda9adbd9d4893b7d748d387b1f4d2"
    },
    "D00": {
        "original": "a273dced1078849a12fa347375d7c4f83ea2bf8b410fa7408c689e1c1a00ed12",
        "repeat": "62f3aeadaaf47b60e69c99632c1c47cac99c5ad92b35c8bfd5f1df14de1bc1c6"
    },
    "D02": {
        "original": "33f46564f3fbe9055040b60fa6174a132dc43dd55a77b2847081f0fc0ab8111c",
        "repeat": "7eb623f04580a483dfb6e57259fde3e858d80b4d7caa43a823b41987ae71f0d2"
    },
    "D03": {
        "original": "7fcb3f8a003b925ff54bb7821fd098605d4ef0a2abc88eb85d3e3720966c0291",
        "repeat": "8c830d7d4a8163b7d10968d6c140048a4ea91eb251a4921f172822b809dfcc27"
    }
}

class Invalid(ValueError):
    pass

def need(ok, reason):
    if not ok:
        raise Invalid(reason)

def sha(b):
    return hashlib.sha256(b).hexdigest()

def raw(p):
    need(p.is_file() and not p.is_symlink(), "MISSING_OR_SYMLINK_"+str(p))
    return p.read_bytes()

def encoded(x):
    return (json.dumps(x, sort_keys=True, indent=2)+"\n").encode("ascii")

def source(case):
    need(case in CASES, "INVALID_CASE")
    value=CASES[case][1]
    expected=(f"10 PEN {value}\n20 LOCATE 1,15\n"
              '30 PRINT "J117PEN"\n40 END\n').encode("ascii")
    need(raw(SOURCES/(case.lower()+".bas"))==expected,"SOURCE_DRIFT_"+case)
    return expected

def setup(case):
    return CONTROLLED if CASES[case][0]=="C" else DEFAULT

def case_seal(work):
    """Independent reproducible digest over ALL seven raw artifacts."""
    digest=hashlib.sha256()
    for rel in ("program.bin","list/screen.png","run/screen.png",
                "run/printer.dat","list/caprice.log","run/caprice.log","capture.json"):
        value=raw(work/rel)
        digest.update(rel.encode("ascii")+b"\0")
        digest.update(sha(value).encode("ascii")+b"\n")
    return digest.hexdigest()

def check_head(head):
    need(re.fullmatch("[0-9a-f]{40}",head) is not None,"INVALID_HEAD")
    actual=subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],text=True).strip()
    need(actual==head,"HEAD_MISMATCH_"+actual)
    ancestry=subprocess.run(["git","-C",str(ROOT),"merge-base","--is-ancestor",BASE,head])
    need(ancestry.returncode==0,"BASE_NOT_ANCESTOR")
    return head

def acquire(cap,out,head):
    need(not out.exists(),"OUTPUT_EXISTS")
    version=base.check_caprice(cap)
    out.mkdir(parents=True)
    manifest={"schema":1,"phase":PHASE,"base":BASE,"acquisition_head":head,
              "run_id":os.environ.get("GITHUB_RUN_ID","LOCAL"),
              "caprice":base.cpc.PIN,"rom":base.cpc.ROM_SHA,
              "ghcr":base.GHCR,"version":version,
              "model":"CPC6128","basic":"1.1",
              "snapshots_archived":False,"native_changes":False,
              "cases":{}}
    # Disjoint fresh Caprice32 processes for LIST/SNA and RUN for every case
    # and each independent repetition; NO SNA or ROM is ever published.
    old_source=base.source
    base.source=source
    try:
        with tempfile.TemporaryDirectory(prefix="j117c-sna-") as tmp:
            for case in CASES:
                record={}
                for session in SESSIONS:
                    base.SETUP=setup(case)
                    caprec=base.capture_one(cap,out,case,session,Path(tmp))
                    path=out/session/case
                    # The inherited generic capture assumes controlled inks;
                    # override with the REAL setup and independently read RGB.
                    caprec["setup_commands"]=setup(case)
                    caprec["palette_context"]="explicit" if case[0]=="C" else "mode1_default"
                    caprec["inks"]=({"0":0,"1":26,"2":6,"3":18}
                                    if case[0]=="C" else None)
                    caprec["logical_pen"]=CASES[case][1]
                    caprec["rgb_roi"]=rgb.histogram(path/"run/screen.png")
                    caprec["visual_classification"]="RGB_ROI_MEASURED"
                    caprec["visual_reason"]="ROI histogram; no inferred logical-to-pixel mapping"
                    (path/"capture.json").write_bytes(encoded(caprec))
                    record[session]=caprec
                    print(PHASE,"ACQUIRED",case,session,"PEN_RECORD",
                          caprec["pen_record_hex"],"ERR",caprec["err"],
                          "ERL",caprec["erl"],"RGB",caprec["rgb_roi"]["pixels"],
                          flush=True)
                need((record["original"]["program_hex"],record["original"]["err"],
                      record["original"]["erl"],record["original"]["rgb_roi"]["pixels"])==
                     (record["repeat"]["program_hex"],record["repeat"]["err"],
                      record["repeat"]["erl"],record["repeat"]["rgb_roi"]["pixels"]),
                     "REPETITION_MISMATCH_"+case)
                manifest["cases"][case]={s:sha(raw(out/s/case/"capture.json"))
                                         for s in SESSIONS}
    finally:
        base.source=old_source
    (out/"manifest.json").write_bytes(encoded(manifest))
    verify(out,False)
    print(PHASE,"FRESH_ARCHIVE",len(CASES)*len(SESSIONS),
          "case sessions; MANIFEST_SHA256",sha(raw(out/"manifest.json")))
    for case in CASES:
        for s in SESSIONS:
            print("EXTERNAL_PIN",case,s,case_seal(out/s/case),flush=True)

def verify(out,permanent):
    m=json.loads(raw(out/"manifest.json"))
    need(m.get("phase")==PHASE and m.get("schema")==1 and m.get("base")==BASE
         and m.get("caprice")==base.cpc.PIN and m.get("rom")==base.cpc.ROM_SHA
         and m.get("ghcr")==base.GHCR and m.get("model")=="CPC6128"
         and m.get("basic")=="1.1" and m.get("snapshots_archived") is False
         and m.get("native_changes") is False
         and set(m.get("cases",{}))==set(CASES),
         "MANIFEST_PROVENANCE")
    head=m["acquisition_head"]
    need(re.fullmatch("[0-9a-f]{40}",head) is not None,"ACQUISITION_SHA")
    need(subprocess.run(["git","-C",str(ROOT),"merge-base","--is-ancestor",
                         head,"HEAD"]).returncode==0,"UNREACHABLE_ACQUISITION")
    if permanent:
        need(bool(re.fullmatch("[0-9a-f]{64}",EXTERNAL_MANIFEST_SHA256)) and
             sha(raw(out/"manifest.json"))==EXTERNAL_MANIFEST_SHA256,
             "EXTERNAL_MANIFEST_SEAL")
        need(set(EXTERNAL_RECORD_SHA256)==set(CASES),"MISSING_EXTERNAL_RECORD_SEALS")
    for case in CASES:
        records=[]
        for session in SESSIONS:
            path=out/session/case
            d=json.loads(raw(path/"capture.json"))
            src=source(case)
            program=raw(path/"program.bin")
            numbers,rows=base.cpc.records(program)
            pen_record=program[:rows[0]["length"]]
            val=CASES[case][1]
            expected_token=bytes([0x0e+val]) if val<=9 else bytes([0x19,val])
            need(numbers==[10,20,30,40] and pen_record[4]==0xbb and
                 pen_record[5]==0x20 and
                 pen_record[6:6+len(expected_token)]==expected_token and
                 d["pen_record_hex"]==pen_record.hex(" ").upper(),
                 "RAM_PEN_TOKEN_VALUE_"+case+session)
            need(d["program_hex"]==program.hex(" ").upper() and
                 d["program_sha256"]==sha(program) and
                 d["source_sha256"]==sha(src) and
                 d["case"]==case and d["session"]==session and
                 d["logical_pen"]==val and
                 d["palette_context"]==("explicit" if case[0]=="C" else "mode1_default")
                 and d["setup_commands"]==setup(case) and
                 d["inks"]==({"0":0,"1":26,"2":6,"3":18}
                             if case[0]=="C" else None) and
                 d["visual_classification"]=="RGB_ROI_MEASURED",
                 "CAPTURE_PROVENANCE_"+case+session)
            for stage in ("list","run"):
                expected_tail=(["LIST","CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT CAP32_EXIT"]
                               if stage=="list" else
                               ["RUN","CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT",
                                "PRINT #8,ERR","PRINT #8,ERL","CAP32_DELAY CAP32_EXIT"])
                need(d[stage]["commands"]==setup(case)+src.decode("ascii").splitlines()+expected_tail,
                     "COMMAND_TIMELINE_"+case+session+stage)
                shot=raw(path/stage/"screen.png")
                need(sha(shot)==d[stage+"_png_sha256"] and
                     shot.startswith(b"\x89PNG\r\n\x1a\n"),
                     "SCREEN_HASH_"+case+session+stage)
                log=raw(path/stage/"caprice.log")
                need(log.startswith(b"exit code: 0\n") and
                     sha(log)==d[stage+"_log_sha256"],
                     "CAPRICE_PROCESS_"+case+session+stage)
            printer=raw(path/"run/printer.dat")
            integers=[base.parse_integer(line) for line in printer.splitlines(keepends=True)]
            need(len(integers)==2 and all(x is not None for x in integers)
                 and [x["numeric_value"] for x in integers]==[d["err"],d["erl"]]
                 and sha(printer)==d["printer_sha256"],
                 "ERR_ERL_PRINTER_"+case+session)
            need(d["run_kind"]==("ERROR" if d["err"] else "NO_ERROR"),
                 "RUN_KIND_"+case+session)
            roi=rgb.histogram(path/"run/screen.png")
            need(roi==d["rgb_roi"],"PNG_RGB_CRC_HISTOGRAM_"+case+session)
            need(m["cases"][case][session]==sha(raw(path/"capture.json")),
                 "CAPTURE_INTERNAL_SEAL_"+case+session)
            if permanent:
                need(EXTERNAL_RECORD_SHA256[case][session]==case_seal(path),
                     "EXTERNAL_RECORD_SEAL_"+case+session)
            records.append(d)
        for key in ("program_hex","err","erl"):
            need(records[0][key]==records[1][key],"PAIR_"+key+"_"+case)
        need(records[0]["rgb_roi"]["pixels"]==records[1]["rgb_roi"]["pixels"],
             "PAIR_RGB_"+case)
    print(PHASE,"VERIFIED",len(CASES)*len(SESSIONS),"sessions",
          "EXTERNALLY_SEALED" if permanent else "UNSEALED",flush=True)

def negatives(out,permanent):
    experiments=("ram","png","printer","capture","fake_head") + (("coordinated",) if permanent else ())
    archive_sha=sha(raw(out/"manifest.json"))
    for kind in experiments:
        with tempfile.TemporaryDirectory(prefix="j117c-falsify-") as tmp:
            clone=Path(tmp)/"clone"
            shutil.copytree(out,clone)
            p=clone/"original/C05"
            d=json.loads(raw(p/"capture.json"))
            m=json.loads(raw(clone/"manifest.json"))
            if kind in ("ram","coordinated"):
                content=bytearray(raw(p/"program.bin"));content[6]^=1
                (p/"program.bin").write_bytes(content)
                if kind=="coordinated":
                    d["program_sha256"]=sha(content)
                    d["program_hex"]=bytes(content).hex(" ").upper()
                    d["pen_record_hex"]=bytes(content[:int.from_bytes(content[:2],"little")]).hex(" ").upper()
                    (p/"capture.json").write_bytes(encoded(d))
                    m["cases"]["C05"]["original"]=sha(raw(p/"capture.json"))
                    (clone/"manifest.json").write_bytes(encoded(m))
            elif kind=="png":
                content=bytearray(raw(p/"run/screen.png"));content[-1]^=1
                (p/"run/screen.png").write_bytes(content)
            elif kind=="printer":
                (p/"run/printer.dat").write_bytes(b"99\r\n10\r\n")
            elif kind=="capture":
                d["err"]=99
                (p/"capture.json").write_bytes(encoded(d))
            elif kind=="fake_head":
                m["acquisition_head"]="0"*40
                (clone/"manifest.json").write_bytes(encoded(m))
            try:
                verify(clone,permanent)
            except (Invalid,base.Invalid,rgb.Invalid,ValueError,KeyError,IndexError) as exc:
                print(PHASE,"FALSIFICATION_REJECTED",kind,str(exc)[:120],flush=True)
            else:
                raise Invalid("FALSIFICATION_ACCEPTED_"+kind)
    need(sha(raw(out/"manifest.json"))==archive_sha,"ORIGINAL_MANIFEST_MUTATED")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--caprice",type=Path)
    p.add_argument("--output",type=Path)
    p.add_argument("--evidence",type=Path)
    p.add_argument("--expect-head")
    p.add_argument("--check-sources",action="store_true")
    p.add_argument("--permanent",action="store_true")
    p.add_argument("--self-test",action="store_true")
    a=p.parse_args()
    if a.expect_head:check_head(a.expect_head)
    if a.check_sources or a.self_test:
        need(len(CASES)==26 and len(SESSIONS)==2,"MATRIX_SIZE")
        for case in CASES:source(case)
        need(BASE!="0"*40,"FALSE_BASE")
    if a.caprice:
        need(a.output is not None and a.evidence is None,"CAPTURE_ARGUMENTS")
        head=a.expect_head or subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
        acquire(a.caprice.resolve(),a.output.resolve(),check_head(head))
    if a.evidence:
        verify(a.evidence.resolve(),a.permanent)
        if a.self_test:negatives(a.evidence.resolve(),a.permanent)
    need(a.caprice or a.evidence or a.check_sources or a.self_test,"NO_OPERATION")

if __name__=="__main__":
    try:main()
    except (Invalid,base.Invalid,rgb.Invalid,ValueError,KeyError,IndexError,
            OSError,subprocess.SubprocessError,UnicodeError) as e:
        print(PHASE,"FAIL",e,file=sys.stderr)
        sys.exit(1)
