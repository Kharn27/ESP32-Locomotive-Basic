#!/usr/bin/env python3
"""CLK-04-A4: ROM-backed CPC REAL5 evidence; model NEVER feeds acquisition.

Raw variable bytes are taken only from transient Caprice32 SNA at BASIC STOP.
The candidate model is imported ONLY in the independent sealed verifier.
No ROM, full SNA or generated 'oracle' bytes are shipped.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clk_03_cpc_time as prior
import clk_04_real5_oracle as a1

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/cpc6128/clk_04_a4_numeric/corpus.json"
SOURCE_SHA = "e9fd767a394d7717816fe537695bf09bc5e40a2a5198f338d5c5e4aa42d1c79d"
SESSIONS = prior.SESSIONS
PINS = {"caprice_commit": prior.CAP_SHA, "rom_sha256": prior.ROM_SHA,
        "image": prior.IMAGE}
need, sha, read, canonical = prior.need, prior.sha, prior.read, prior.canonical
PRINT = re.compile(rb"[ \t]*([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?)[ \t\r]*\Z")


def mandatory_values():
    return [0,1,2,9,10,99,100,999,1000,5256,12934,14350,27664,32767,
            32768,33174,50376,65535,65536,65537,8388607,8388608,
            2147483647,2147483648,4294967295]

def alternative(value):
    return {32768:"2^15",65536:"2^16",65537:"(2^16)+1",
            8388607:"(2^23)-1",8388608:"2^23",
            2147483647:"(2^31)-1",2147483648:"2^31",
            4294967295:"(2^32)-1"}.get(value)

def source_lines(items):
    rows = []
    line = 10
    for item in items:
        rows.append("%d %s=%s" % (line,item["variable"],item["value"]))
        line += 10
    for item in items:
        if item["arithmetic"]:
            rows.append("%d %s=%s" %
                        (line,item["arithmetic_variable"],item["arithmetic"]))
            line += 10
    need(line <= 90, "SOURCE_TOO_MANY_VARIABLES")
    rows.append("90 STOP")
    line = 100
    for item in items:
        var = item["variable"]
        fields = ["@" + var, var, var+"*2", var+">=0", var+">32767"]
        if item["arithmetic"]:
            alt = item["arithmetic_variable"]
            fields.extend(("@"+alt, alt, var+"="+alt,
                           "("+alt+"+1)-"+alt, alt+"-("+alt+"-1)"))
        for expr in fields:
            rows.append("%d PRINT #8,%s" % (line,expr))
            line += 10
    rows.append("%d END" % line)
    return rows

def source_cases():
    data = read(SOURCE)
    need(sha(data) == SOURCE_SHA, "CORPUS_SHA_DRIFT")
    obj = json.loads(data)
    cases = obj.get("cases", [])
    need(obj.get("schema")==1 and obj.get("mission")=="CLK-04-A4"
         and obj.get("status")=="SEALED_INPUTS_NOT_OBSERVATIONS"
         and obj.get("range")=="uint32_sampled_only_no_global_claim"
         and isinstance(cases,list) and len(cases)==7, "CORPUS_SCHEMA_INVALID")
    seen = []
    for k,case in enumerate(cases):
        items = case.get("items")
        need(case.get("id")=="B%02d"%(k+1) and isinstance(items,list)
             and 1<=len(items)<=4, "BATCH_SHAPE_DRIFT")
        for j,item in enumerate(items):
            value = item.get("value")
            need(type(value) is str and re.fullmatch(r"0|[1-9][0-9]*",value)
                 and int(value)<=4294967295, "SOURCE_VALUE_INVALID")
            n=int(value)
            need(item.get("variable")==chr(84+j)+"!"
                 and item.get("arithmetic")==alternative(n)
                 and item.get("arithmetic_variable")==(
                    chr(80+j)+"!" if alternative(n) else None),
                 "SOURCE_VARIABLE_OR_CONSTRUCTION_DRIFT")
            seen.append(n)
        last = int(items[-1]["value"])
        tier="D0" if last<=65536 else "D1" if last<=2147483647 else "D2"
        need(case.get("tier")==tier and case.get("lines")==source_lines(items)
             and case.get("printer_numeric_count")==sum(
                 10 if i["arithmetic"] else 5 for i in items),
             "SOURCE_BASIC_OR_PRINT_COUNT_DRIFT")
    need(seen==mandatory_values(), "SOURCE_VALUES_OR_BATCH_ORDER")
    return cases

def raw_number_lines(raw,count):
    """Return numeric parsing AND exact original bytes, without normalising PRINT."""
    need(bool(raw) and raw.endswith(b"\n"), "RAW_PRINTER_NO_FINAL_LF")
    lines = raw.splitlines(keepends=True)
    need(len(lines)==count, "PRINTER_CARDINALITY")
    found=[]
    for line in lines:
        need(line.endswith(b"\n") and len(line)<=128, "PRINTER_LINE_TRUNCATED")
        match=PRINT.fullmatch(line[:-1])
        need(match is not None, "PRINTER_AMBIGUOUS")
        try:
            number=Decimal(match.group(1).decode("ascii"))
        except InvalidOperation as exc:
            raise prior.OracleError("PRINTER_DECIMAL_INVALID") from exc
        found.append({"number":number,"raw_hex":line.hex().upper()})
    return found

def snapshot_window(snapshot,lines,items):
    parser = prior.ram_parser()
    line_nums = [int(x.split(" ",1)[0]) for x in lines]
    program,region = parser.extract_snapshot(snapshot,line_nums)
    need(b"\xff\x46" not in program, "TIME_TOKEN_IN_A2_PROGRAM")
    mem = memoryview(snapshot)[parser.HEADER:]
    word = lambda pos: int.from_bytes(mem[pos:pos+2],"little")
    ptr = {"program_end":word(0xae66),"scalar_start":word(0xae68),
           "array_start":word(0xae6a),"array_end":word(0xae6c)}
    st,en=ptr["scalar_start"],ptr["array_start"]
    need(0x016f < ptr["program_end"] <= st < en <= ptr["array_end"] < 0xac00,
         "RAM_POINTER_ORDER")
    window = bytes(mem[st:en])
    names = [ord(item["variable"][0]) for item in items]
    names += [ord(item["arithmetic_variable"][0]) for item in items
              if item["arithmetic"]]
    entries = a1.check_window(window,st,names)
    return program,window,{"sna_sha256":sha(snapshot),
         "sna_header_first_16_hex":snapshot[:16].hex(" ").upper(),
         "pointers":ptr,"ram_window_start":st,"ram_window_end":en,
         "ram_window_sha256":sha(window),"entries":entries,"region":region}


def run_double_screen(cap,folder,cmds,snaps,timeout=130):
    """A2-owned adaptation of CLK-03 run: capture BOTH STOP and CONT PNG."""
    need(not folder.exists(), "NO_OVERWRITE")
    folder.mkdir(parents=True)
    prior.setup(cap,folder,snaps)
    argv = ["xvfb-run","-a",str(cap/"cap32"),"-c",str(folder/"cap32.cfg")]
    for cmd in cmds:
        need("\r" not in cmd and "\n" not in cmd, "NEWLINE_IN_AUTOCMD")
        argv.extend(("-a",cmd.replace("CAP32_SNAPSHOT","\x0c\x0d")))
    (folder/"autocmd.json").write_bytes(canonical({"commands":cmds,"argv":argv}))
    env=dict(os.environ,SDL_VIDEODRIVER="x11",SDL_AUDIODRIVER="dummy")
    started=datetime.now(timezone.utc).isoformat()
    t0=time.monotonic_ns()
    try:
        proc=subprocess.run(argv,cwd=cap,env=env,capture_output=True,
                            timeout=timeout,check=False)
    except subprocess.TimeoutExpired as exc:
        (folder/"caprice.log").write_bytes((exc.stdout or b"")+
                                           b"\nTIMEOUT\n"+(exc.stderr or b""))
        raise prior.OracleError("CAPRICE_TIMEOUT") from exc
    seconds=(time.monotonic_ns()-t0)/1e9
    ended=datetime.now(timezone.utc).isoformat()
    (folder/"caprice.log").write_bytes(
        ("returncode=%d\nstart_utc=%s\nend_utc=%s\nwall_seconds=%.9f\n[stdout]\n"
         %(proc.returncode,started,ended,seconds)).encode()+proc.stdout+
         b"\n[stderr]\n"+proc.stderr)
    need(proc.returncode==0,"CAPRICE_NONZERO")
    pics=sorted(folder.glob("screenshot_*.png"))
    need(len(pics)==2 and all(prior.valid_png(read(p)) for p in pics),
         "STOP_CONT_SCREENSHOTS_MISSING")
    pics[0].rename(folder/"stop-screen.png")
    pics[1].rename(folder/"cont-screen.png")
    return {"started_utc":started,"ended_utc":ended,
            "wall_seconds":seconds,"returncode":proc.returncode}


def list_commands(lines):
    """Finish lengthy screen LIST before LIST #8, then drain printer output."""
    big = len(lines) > 20
    screen_wait = 14 if big else 2
    printer_wait = 14 if big else 3
    return ["MODE 1","NEW",*lines,"LIST",
        " ".join(["CAP32_DELAY"]*screen_wait) +
        " CAP32_SCRNSHOT CAP32_SNAPSHOT",
        "LIST #8", " ".join(["CAP32_DELAY"]*printer_wait) +
        " CAP32_EXIT"]


def run_commands(lines):
    """After CONT, allow long PRINT series to finish before second PNG."""
    wait = 14 if len(lines)>20 else 6
    return ["MODE 1","NEW",*lines,"RUN",
       "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT",
       "CONT"," ".join(["CAP32_DELAY"]*wait)+" CAP32_SCRNSHOT CAP32_EXIT"]


def capture_case(cap,out,session,case,snap_root):
    folder = out/session/case["id"]
    lines=case["lines"]
    nums=[int(s.split(" ",1)[0]) for s in lines]
    snaps=snap_root/(session+"-"+case["id"]+"-list")
    snaps.mkdir()
    listcmd=list_commands(lines)
    listing=prior.run(cap,folder/"list",listcmd,snaps,
                      timeout=200 if len(lines)>20 else 130)
    files=list(snaps.glob("*.sna"))
    need(len(files)==1,"LIST_SNA_MISSING")
    program,region=prior.ram_parser().extract_snapshot(read(files[0]),nums)
    files[0].unlink()
    need(read(folder/"list/printer.dat").strip(),"LIST_PRINTER_MISSING")
    (folder/"program.bin").write_bytes(program)

    snaps=snap_root/(session+"-"+case["id"]+"-stop")
    snaps.mkdir()
    controls=run_commands(lines)
    execution=run_double_screen(cap,folder/"run",controls,snaps,
                                timeout=200 if len(lines)>20 else 130)
    files=list(snaps.glob("*.sna"))
    need(len(files)==1,"STOP_SNA_MISSING")
    stop_prog,window,stop=snapshot_window(read(files[0]),lines,case["items"])
    files[0].unlink()
    (folder/"window.bin").write_bytes(window)
    (folder/"stop_program.bin").write_bytes(stop_prog)
    (folder/"stop.json").write_bytes(canonical(stop))
    observations=read_values(case,stop,folder/"run/printer.dat")
    return {"list":listing,"run":execution,"list_region":region,
       "program_sha256":sha(program),"stop_program_sha256":sha(stop_prog),
       "window_sha256":sha(window),"stop_sha256":sha(read(folder/"stop.json")),
       "list_printer_sha256":sha(read(folder/"list/printer.dat")),
       "readings":observations}


def read_values(case,stop,printer):
    entries = {int(k):v for k,v in stop["entries"].items()}
    lines=raw_number_lines(read(printer),case["printer_numeric_count"])
    result=[];offset=0
    for item in case["items"]:
        name=item["variable"]
        entry=entries[ord(name[0])]
        part=lines[offset:offset+5];offset+=5
        need(part[0]["number"]==entry["address"], "AT_VARIABLE_ADDRESS_MISMATCH")
        row={"value_requested":item["value"],"variable":name,
             "address":entry["address"],"cpc_real5_hex":entry["value_hex"],
             "cpc_print":str(part[1]["number"]),
             "cpc_twice":str(part[2]["number"]),
             "cpc_ge_zero":str(part[3]["number"]),
             "cpc_gt_32767":str(part[4]["number"]),
             "raw_print_hex":{key:part[j]["raw_hex"] for j,key in
                  enumerate(("address","value","twice","ge_zero","gt_32767"))}}
        if item["arithmetic"]:
            other=entries[ord(item["arithmetic_variable"][0])]
            alt=lines[offset:offset+5];offset+=5
            need(alt[0]["number"]==other["address"],"AT_ALT_ADDRESS_MISMATCH")
            row.update(arithmetic_expression=item["arithmetic"],
                 arithmetic_variable=item["arithmetic_variable"],
                 arithmetic_real5_hex=other["value_hex"],
                 arithmetic_address=other["address"],
                 cpc_arithmetic_print=str(alt[1]["number"]),
                 cpc_equal=str(alt[2]["number"]),
                 cpc_plus_step=str(alt[3]["number"]),
                 cpc_minus_step=str(alt[4]["number"]),
                 raw_alternative_hex=[v["raw_hex"] for v in alt])
        result.append(row)
    need(offset==len(lines), "PRINTER_READING_SHAPE")
    return result

def cfg_process(folder,meta,double=False):
    pics=("stop-screen.png","cont-screen.png") if double else ("screen.png",)
    need(meta["returncode"]==0 and meta["wall_seconds"]>0 and
         b"returncode=0\n" in read(folder/"caprice.log") and
         all(prior.valid_png(read(folder/p)) for p in pics),
         "PROCESS_PROVENANCE")
    prior.cfg_validate(folder/"cap32.cfg")
    need(datetime.fromisoformat(meta["started_utc"]).tzinfo is not None
         and datetime.fromisoformat(meta["ended_utc"]).tzinfo is not None,
         "TIMESTAMP_INVALID")
    return json.loads(read(folder/"autocmd.json"))["commands"]


def acquire(cap,out,head):
    cases=source_cases()
    need(prior.SHA40.fullmatch(head or ""), "HEAD_INVALID")
    actual=subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],
                                   text=True).strip()
    need(actual==head,"HEAD_NOT_CHECKED_OUT")
    need(not out.exists(),"OUTPUT_EXISTS")
    need(subprocess.check_output(["git","-C",str(cap),"rev-parse","HEAD"],
       text=True).strip()==prior.CAP_SHA,"CAPRICE_SHA_MISMATCH")
    need(sha(read(cap/"rom/cpc6128.rom"))==prior.ROM_SHA,"ROM_SHA_MISMATCH")
    need((cap/"cap32").is_file() and (cap/"rom/amsdos.rom").is_file(),
         "CAPRICE_BINARY_OR_AMSDOS_MISSING")
    version=subprocess.check_output([str(cap/"cap32"),"--version"],
                                    text=True).strip()
    m={"schema":1,"mission":"CLK-04-A4","status":"ACQUISITION_PARTIAL",
       "head":head,"corpus_sha256":SOURCE_SHA,**PINS,
       "caprice_version":version,"run_id":os.getenv("GITHUB_RUN_ID","LOCAL"),
       "observation_class":"CPC6128_CAPRICE32_ROM_BACKED",
       "rom_archived":False,"snapshot_archived":False,
       "sessions":{},"files":{}}
    out.mkdir(parents=True)
    try:
        with tempfile.TemporaryDirectory(prefix="clk04-a4-sna-") as tmp:
            snaps=Path(tmp)
            for session in SESSIONS:
                boot=prior.run(cap,out/session/"boot",
                     ["CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"],snaps)
                gate=prior.speed_gate(cap,out,session,snaps)
                found={}
                for case in cases:
                    found[case["id"]]=capture_case(cap,out,session,case,snaps)
                m["sessions"][session]={"boot":boot,"gate":gate,"cases":found}
        m["status"]="ACQUIRED_PENDING_PNG_REVIEW"
    finally:
        m["files"]=prior.inventory(out)
        (out/"manifest.json").write_bytes(canonical(m))
    need(m["status"]=="ACQUIRED_PENDING_PNG_REVIEW","ACQUISITION_INCOMPLETE")
    print("CLK-04-A4 ROM_ACQUIRED_PENDING_PNG_REVIEW",sha(read(out/"manifest.json")))


def classify_sample(row, record):
    """Classify one candidate row AFTER independently authenticated CPC RAW replay."""
    fields=record.split("\t")
    need(len(fields)==10 and fields[0]==row["value_requested"],
         "CANDIDATE_RECORD_ORDER")
    n=int(row["value_requested"])
    raw_candidate=bytes.fromhex(fields[1]).hex(" ").upper()
    doubled_candidate=bytes.fromhex(fields[3]).hex(" ").upper()
    independent=("arithmetic_real5_hex" not in row or
       (row["arithmetic_real5_hex"]==row["cpc_real5_hex"] and
        row["cpc_equal"]=="-1" and row["cpc_plus_step"]=="1" and
        row["cpc_minus_step"]=="1"))
    row["input_identity"]=(
       "INPUT_UNVERIFIED" if not independent else
       "SECOND_CPC_CONSTRUCTION_CONCORDANT"
       if "arithmetic_real5_hex" in row else "DECIMAL_LITERAL_ONLY")
    # Scientific PRINT may lose decimals: NEVER interpret PRINT rounding
    # as a difference in the five stored bytes.
    exact_print=(n<=999999)
    observed_algebra=(Decimal(row["cpc_ge_zero"])==Decimal(-1) and
         Decimal(row["cpc_gt_32767"])==Decimal(-1 if n>32767 else 0) and
         (not exact_print or
            (Decimal(row["cpc_print"])==Decimal(n) and
             Decimal(row["cpc_twice"])==Decimal(n*2))))
    numeric_candidate=(fields[2]==str(n*2) and fields[4]=="-1" and
                       fields[5]==str(-1 if n>32767 else 0))
    print_keys=("value","twice","ge_zero","gt_32767")
    printed={key:("UNSUPPORTED" if fields[6+j]=="UNSUPPORTED" else
             "CANDIDATE_MATCH" if fields[6+j]==row["raw_print_hex"][key]
             else "CPC_MISMATCH_STOP") for j,key in enumerate(print_keys)}
    # Missing C99 PRINT support is explicit; no invented general format.
    status=("INPUT_UNVERIFIED" if not independent else
            "CPC_MISMATCH_STOP" if raw_candidate!=row["cpc_real5_hex"] or
               not observed_algebra or not numeric_candidate or
               "CPC_MISMATCH_STOP" in printed.values() else
            "UNSUPPORTED" if not exact_print or
               "UNSUPPORTED" in printed.values() else "CANDIDATE_MATCH")
    row["c99_candidate"]={"real5_hex":raw_candidate,
         "twice_real5_hex":doubled_candidate,
         "twice_integer":fields[2],"ge_zero_integer":fields[4],
         "gt_32767_integer":fields[5],
         "raw_print_candidates":dict(zip(print_keys,fields[6:])),
         "print_comparison":printed}
    row["status"]=status
    return status


def verify(out,head,seal,candidate):
    cases=source_cases()
    need(prior.SHA64.fullmatch(seal or "") and
         sha(read(out/"manifest.json"))==seal,"EXTERNAL_SEAL_REQUIRED")
    m=json.loads(read(out/"manifest.json"))
    need(prior.SHA40.fullmatch(head or "") and m.get("head")==head,
         "HEAD_MISMATCH")
    need(m.get("schema")==1 and m.get("mission")=="CLK-04-A4"
         and m.get("status")=="ACQUIRED_PENDING_PNG_REVIEW"
         and m.get("corpus_sha256")==SOURCE_SHA
         and all(m.get(k)==v for k,v in PINS.items())
         and m.get("observation_class")=="CPC6128_CAPRICE32_ROM_BACKED"
         and m.get("rom_archived") is False and
         m.get("snapshot_archived") is False,"PROVENANCE_MISMATCH")
    need(set(m.get("sessions",{}))==set(SESSIONS),"SESSIONS_MISSING")
    actual=prior.inventory(out)
    actual.pop("manifest.json",None)
    need(m.get("files")==actual and bool(actual) and
         not any(x.endswith(".sna") or x.endswith(".rom") for x in actual),
         "FILE_INVENTORY_MISMATCH")
    validparts={c["id"] for c in cases}|{"boot","gate_short","gate_long"}
    need(all(p.split("/")[0] in SESSIONS and
             p.split("/")[1] in validparts for p in actual),
         "UNEXPECTED_FILE_IN_ARCHIVE")
    timestamps=set()
    report=[]
    for session in SESSIONS:
        group=m["sessions"][session]
        gate=group["gate"]
        need(set(group["cases"])=={c["id"] for c in cases},"CASES_MISSING")
        for part,meta in (("boot",group["boot"]),("gate_short",gate["short"]),
                          ("gate_long",gate["long"])):
            cfg_process(out/session/part,meta)
            need(meta["started_utc"] not in timestamps,"DUPLICATE_START_TIMESTAMP")
            timestamps.add(meta["started_utc"])
            if part.startswith("gate"):
                got=prior.parse_numbers(read(out/session/part/"printer.dat"),2)
                need(got==meta["ticks"] and got[1]-got[0]==meta["delta_ticks"],
                     "GATE_PRINTER_DRIFT")
        delta_wall=gate["long"]["wall_seconds"]-gate["short"]["wall_seconds"]
        delta_ticks=gate["long"]["delta_ticks"]-gate["short"]["delta_ticks"]
        need(delta_wall>.5 and delta_ticks>100 and
             abs(gate["delta_wall_seconds"]-delta_wall)<1e-6 and
             delta_ticks==gate["delta_ticks"] and
             abs(gate["ticks_per_wall_second"]-delta_ticks/delta_wall)<1e-5
             and 255<=delta_ticks/delta_wall<=345,"SPEED_GATE_FAILED")
        for case in cases:
            data=group["cases"][case["id"]]
            folder=out/session/case["id"]
            expected_list=list_commands(case["lines"])
            expected_run=run_commands(case["lines"])
            listing=cfg_process(folder/"list",data["list"])
            running=cfg_process(folder/"run",data["run"],double=True)
            need(listing==expected_list and running==expected_run,
                 "COMMANDS_OR_SOURCE_DRIFT")
            for meta in (data["list"],data["run"]):
                need(meta["started_utc"] not in timestamps,"DUPLICATE_START_TIMESTAMP")
                timestamps.add(meta["started_utc"])
            program=read(folder/"program.bin")
            lines,_=prior.ram_parser().records(program)
            need(lines==[int(x.split(" ",1)[0]) for x in case["lines"]]
                 and b"\xff\x46" not in program and
                 sha(program)==data["program_sha256"]
                 and sha(read(folder/"stop_program.bin"))==data["stop_program_sha256"]
                 and sha(read(folder/"list/printer.dat"))==data["list_printer_sha256"]
                 and read(folder/"list/printer.dat").strip(),
                 "PROGRAM_OR_LIST_DRIFT")
            stop=json.loads(read(folder/"stop.json"))
            window=read(folder/"window.bin")
            ptr=stop["pointers"]
            need(stop["ram_window_sha256"]==sha(window)==data["window_sha256"]
                 and stop["ram_window_start"]==ptr["scalar_start"]
                 and stop["ram_window_end"]==ptr["array_start"]
                 and ptr["array_start"]-ptr["scalar_start"]==len(window)
                 and 0x016f<ptr["program_end"]<=ptr["scalar_start"]<
                 ptr["array_start"]<=ptr["array_end"]<0xac00,
                 "RAM_POINTER_OR_HASH_MISMATCH")
            names=[ord(i["variable"][0]) for i in case["items"]]
            names += [ord(i["arithmetic_variable"][0]) for i in case["items"]
                      if i["arithmetic"]]
            entries=a1.check_window(window,ptr["scalar_start"],names)
            need({str(k):v for k,v in entries.items()}==stop["entries"]
                 and sha(read(folder/"stop.json"))==data["stop_sha256"],
                 "RAM_SCALAR_METADATA_MISMATCH")
            rows=read_values(case,stop,folder/"run/printer.dat")
            need(rows==data["readings"],"PRINTER_DRIFT")

            # RAW records already re-read; candidate has not run yet.
            report.extend([{**row,"session":session,"tier":case["tier"]}
                           for row in rows])
    # Acquiring and inventory verification above NEVER consume C99 outputs.
    need(candidate is not None and Path(candidate).is_file(),
         "C99_CANDIDATE_REQUIRED_FOR_REPLAY")
    args=[str(Path(candidate).resolve())]+[r["value_requested"] for r in report]
    proc=subprocess.run(args,capture_output=True,timeout=20,check=False)
    need(proc.returncode==0 and not proc.stderr,"C99_CANDIDATE_FAILED")
    output=proc.stdout.decode("ascii").splitlines()
    need(len(output)==len(report),"CANDIDATE_CARDINALITY")
    totals={"VERIFIED_CPC_SAMPLE":0,"CANDIDATE_MATCH":0,
            "CPC_MISMATCH_STOP":0,"INPUT_UNVERIFIED":0,"UNSUPPORTED":0}
    for row,record in zip(report,output):
        status=classify_sample(row,record)
        totals["VERIFIED_CPC_SAMPLE"]+=1
        totals[status]+=1
    status=("STOP_ARCHITECTURAL" if totals["CPC_MISMATCH_STOP"] or
            totals["INPUT_UNVERIFIED"] else
            "UNSUPPORTED" if totals["UNSUPPORTED"] else
            "VERIFIED_CPC_SAMPLES_ONLY")
    output={"mission":"CLK-04-A4","head":head,"seal":seal,"status":status,
            "totals":totals,"samples":report,
            "range_claim":"RANGE_UNVERIFIED",
            "human_png_review":"REQUIRED_NOT_AUTOMATED"}
    print("CLK-04-A4 RAW_REPLAY_PASS",json.dumps(totals,sort_keys=True),
          "STATUS",status,"RANGE_UNVERIFIED")
    return output


def self_test():
    cases=source_cases()
    need(len(cases)==7 and sum(len(c["items"]) for c in cases)==25,
         "SELF_CORPUS_COUNT")
    need(raw_number_lines(b" 4.2949673E+09\r\n-1 \r\n",2)[0]["raw_hex"]==
         "20342E32393439363733452B30390D0A","SELF_RAW_PRINT")
    for bad in (b"",b"1",b"1\n2\n",b"1\n\n",b"1.2.3\n",b"1\x00\n"):
        try:raw_number_lines(bad,1)
        except prior.OracleError:pass
        else:raise prior.OracleError("SELF_PRINTER_FALSIFICATION_ACCEPTED")
    print("CLK-04-A4 SELF_TEST_PASS (SYNTHETIC_NOT_CPC)")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--acquire",action="store_true")
    p.add_argument("--verify",type=Path)
    p.add_argument("--caprice",type=Path)
    p.add_argument("--output",type=Path)
    p.add_argument("--report",type=Path)
    p.add_argument("--head")
    p.add_argument("--seal")
    p.add_argument("--candidate",type=Path)
    args=p.parse_args()
    if args.self_test:
        self_test()
    elif args.acquire:
        need(args.caprice is not None and args.output is not None and args.head,
             "ACQUISITION_ARGS_MISSING")
        acquire(args.caprice.resolve(),args.output.resolve(),args.head)
    elif args.verify:
        need(args.head and args.seal,"REPLAY_HEAD_AND_SEAL_REQUIRED")
        report=verify(args.verify.resolve(),args.head,args.seal,args.candidate)
        if args.report:
            need(not args.report.exists(),"REPORT_EXISTS")
            args.report.write_bytes(canonical(report))
    else:
        p.error("choose --self-test, --acquire or --verify")


if __name__=="__main__":
    try:
        main()
    except (prior.OracleError,ValueError,TypeError,KeyError,IndexError,
            subprocess.CalledProcessError,OSError) as exc:
        print("CLK-04-A4 REJECT",str(exc),file=sys.stderr)
        raise SystemExit(2)
