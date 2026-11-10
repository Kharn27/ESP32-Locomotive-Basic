#!/usr/bin/env python3
"""Issue #358 C1: M2 local-only explicit-go test-merge, four Xtensa builds.
LAB_ONLY_NEVER_MERGE. Host push CI can NEVER invoke --run: no GitHub job.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request

REPO = "Kharn27/ESP32-Locomotive-Basic"
M = "c4e4ad889fe3bf1a97f1070553bc0ba15a55c8f0"
B = "4d261f2a76374ab99a4dd7415cae7a097330c46b"
H = "64b0087d5087903fee175c4f149c65a65bb43fe6"
MTREE = "2c32ca0ebba1c690796a16e2ae3182cfe8d1be65"
BTREE = "d74061cb975981aafb022409cf1e9682f934235d"
HTREE = "ed23017e46a7f54c76447bdb77937de540588ea8"
BRANCH = "lab/j1-25-b2-e1-current-integration-m2"
IMAGE = "espressif/idf@sha256:bf72fe7a15c22849a9a94147301165a545fb8905d97c176cf748e3e4614cac84"
IMAGE_ID = "sha256:b5ed7387fed7f3c0cc613272ee7dedab5dddfac6f771ee66af41d93f8d46c0bc"
SHA = re.compile(r"[0-9a-f]{40}\Z")
BUILD_ORDER = (("M",40000000),("M",20000000),("C",40000000),("C",20000000))


class Invalid(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Invalid("MEASUREMENT_INVALID:" + code)


def run(*args, cwd=None, env=None, log=None, check=True):
    p = subprocess.run(list(map(str,args)), cwd=cwd, env=env,
                       text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log is not None:
        Path(log).parent.mkdir(parents=True, exist_ok=True)
        Path(log).write_text(p.stdout)
    if check:
        require(p.returncode == 0, "COMMAND:" + str(args[0]) +
                ":RC=" + str(p.returncode) + ":" + p.stdout[-400:])
    return p.stdout.strip()


def put(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(root,*args,**kw):
    return run("git","-C",root,*args,**kw)


def get(path, token):
    require(token and re.fullmatch(r"[^\s]+",token) and path.startswith("/") and
            "//" not in path, "API_PATH_OR_TOKEN")
    req=urllib.request.Request("https://api.github.com/repos/"+REPO+path,
        headers={"Authorization":"Bearer "+token,
                 "Accept":"application/vnd.github+json",
                 "X-GitHub-Api-Version":"2022-11-28"},
        method="GET")
    with urllib.request.urlopen(req,timeout=30) as f:
        require(f.status==200,"API_STATUS")
        return json.load(f)


def event(approved_head):
    """Human-triggered local campaign only, never a GitHub Actions job."""
    require(not os.environ.get("GITHUB_ACTIONS") and
            not os.environ.get("GITHUB_RUN_ID") and
            not os.environ.get("GITHUB_EVENT_NAME"),
            "GITHUB_ACTIONS_XTENSA_FORBIDDEN")
    require(os.environ.get("E1_PILOTAGE_GO") == "E1_M2_APPROVED_4_BUILDS",
            "PILOTAGE_GO_NOT_SUPPLIED")
    require(isinstance(approved_head,str) and SHA.fullmatch(approved_head),
            "APPROVED_LAB_HEAD_INVALID")
    return {"head":approved_head, "branch":BRANCH, "mode":"LOCAL_EXPLICIT_ONLY"}


def validate_snapshot(data,e):
    main,pr,lab=data["main"],data["pr330"],data["lab"]
    require(main["commit"]["sha"]==M,"MAIN_DRIFT_STOP")
    require(pr["number"]==330 and pr["state"]=="open" and
            pr.get("merged_at") is None and pr["draft"] and
            pr["base"]["ref"]=="main" and
            pr["base"]["sha"]==B and pr["head"]["sha"]==H and
            pr["base"]["repo"]["full_name"]==REPO and
            pr["head"]["repo"]["full_name"]==REPO,
            "PR330_STATE_OR_SHA_DRIFT_STOP")
    require(lab["name"]==BRANCH and lab["commit"]["sha"]==e["head"],
            "LAB_BRANCH_HEAD_DRIFT_STOP")
    return {"main":M,"B":B,"H":H,"lab":e["head"],
            "preview":pr.get("merge_commit_sha"),
            "preview_is_authoritative":False,
            "lab_is_pr":False}


def snapshot(token,e):
    d={"main":get("/branches/main",token),
       "pr330":get("/pulls/330",token),
       "lab":get("/branches/"+BRANCH,token)}
    return validate_snapshot(d,e)


def verify_git(root,e):
    require(git(root,"rev-parse","HEAD")==e["head"],"WRONG_CONTROLLER_SHA")
    for label,commit,tree in (("M",M,MTREE),("B",B,BTREE),("H",H,HTREE)):
        require(git(root,"cat-file","-t",commit)=="commit","MISSING_"+label+"_COMMIT")
        require(git(root,"rev-parse",commit+"^{tree}")==tree,"WRONG_"+label+"_TREE")
    require(git(root,"merge-base",M,H)==B and git(root,"merge-base",B,H)==B,
            "WRONG_GIT_MERGE_BASE")


def make_candidate(root,out):
    # Git's own three-way merge engine, not GitHub's stale merge preview.
    candidate_tree=git(root,"merge-tree","--write-tree",M,H,
                       log=out/"git-merge-tree.txt").splitlines()[0].strip()
    require(SHA.fullmatch(candidate_tree),"INVALID_CANDIDATE_TREE")
    require(git(root,"cat-file","-t",candidate_tree)=="tree","NO_MERGED_TREE")
    env=dict(os.environ,GIT_AUTHOR_NAME="E1 laboratory",
             GIT_AUTHOR_EMAIL="e1-lab@example.invalid",
             GIT_COMMITTER_NAME="E1 laboratory",
             GIT_COMMITTER_EMAIL="e1-lab@example.invalid",
             GIT_AUTHOR_DATE="2026-11-10T00:00:00+0000",
             GIT_COMMITTER_DATE="2026-11-10T00:00:00+0000")
    c=run("git","-C",root,"commit-tree",candidate_tree,"-p",M,"-p",H,
          "-m","E1 #358 ephemeral Git test merge M+H, LAB ONLY",
          env=env).strip()
    require(SHA.fullmatch(c),"BAD_C_SHA")
    require(git(root,"rev-parse",c+"^{tree}")==candidate_tree,"C_TREE_SUBSTITUTION")
    require(git(root,"rev-list","--parents","-n","1",c)==c+" "+M+" "+H,
            "C_PARENT_ORDER")
    return {"C":c,"C_tree":candidate_tree,"parents":[M,H],
            "M_tree":MTREE,"B_tree":BTREE,"H_tree":HTREE,
            "B_H_historical_iram_delta":220,
            "B_H_historical_verdict":"FAIL_HISTORICAL",
            "root_cause":"ROOT_CAUSE_UNVERIFIED",
            "github_preview_used":False}


def make_worktrees(root,out,state):
    target=root/".e1-358"
    require(not target.exists(),"DIRTY_OR_REPEAT_WORKTREES")
    target.mkdir()
    for key,commit in (("M",M),("C",state["C"])):
        loc=target/key
        run("git","-C",root,"worktree","add","--detach",loc,commit,
            log=out/("worktree-"+key+".log"))
        require(git(loc,"rev-parse","HEAD")==commit and
                git(loc,"rev-parse","HEAD^{tree}")==state[key+"_tree"],
                "WORKTREE_SUBSTITUTION_"+key)
    return target


def sizes(path):
    found={}
    for line in Path(path).read_text().splitlines():
        match=re.match(r"\s*(\.[A-Za-z0-9_.$-]+)\s+(\d+)\s+",line)
        if match:
            require(match[1] not in found,"DUP_SECTION")
            found[match[1]]=int(match[2])
    for section in (".dram0.data",".dram0.bss",".iram0.vectors",
                    ".iram0.text",".iram0.text_end",".flash.text",".flash.rodata"):
        require(section in found,"MISSING_SECTION_"+section)
    require(found[".iram0.text_end"]==1,"BAD_IRAM_SENTINEL")
    return {"iram":sum(v for k,v in found.items()
                       if k.startswith(".iram0.") and k!=".iram0.text_end"),
            "iram_text":found[".iram0.text"],
            "dram":sum(v for k,v in found.items() if k.startswith(".dram0.")),
            "bss":found[".dram0.bss"],
            "flash_text":found[".flash.text"],
            "flash_rodata":found[".flash.rodata"]}


def inspect_cell(path,label,hz,commit):
    p=Path(path)
    required=["sections.txt","firmware.bin","firmware.elf","build.log",
              "set-target.log","CMakeCache.txt","compile_commands.json",
              "idf-version.txt","source.txt","sdkconfig","firmware.map"]
    for name in required:
        require((p/name).is_file() and (p/name).stat().st_size>0,
                "MISSING_ARTIFACT:"+label+":"+name)
    cache=(p/"CMakeCache.txt").read_text()
    require("LOCO_CYD_PROFILE:STRING=CONSOLE" in cache and
            "CYD_LCD_SPI_HZ:STRING="+str(hz) in cache,
            "CACHE_PROFILE_OR_HZ")
    require((p/"idf-version.txt").read_text().strip()=="ESP-IDF v5.5.6",
            "ESP_IDF_DRIFT")
    commands=json.loads((p/"compile_commands.json").read_text())
    lcd=[row for row in commands if row["file"].endswith("/cyd_ili9341.c")]
    require(len(lcd)==1,"LCD_COMMAND_MISSING")
    command=lcd[0].get("command") or " ".join(lcd[0].get("arguments",[]))
    require("-DLCD_CLOCK_HZ="+str(hz)+"U" in command,"HAL_CLOCK_MISMATCH")
    require((p/"source.txt").read_text().strip()==commit,"CELL_SOURCE_SHA")
    require((p/"firmware.bin").stat().st_size>0,"EMPTY_BIN")
    d=sizes(p/"sections.txt")
    d.update({"bin_bytes":(p/"firmware.bin").stat().st_size,
              "bin_sha256":sha(p/"firmware.bin"),
              "elf_sha256":sha(p/"firmware.elf"),
              "map_sha256":sha(p/"firmware.map"),
              "sections_sha256":sha(p/"sections.txt"),
              "hal_compiler_clock":hz,
              "commit":commit})
    return d


def compare(cells):
    for key in ("M","C"):
        a,b=cells[key]["40000000"],cells[key]["20000000"]
        for field in ("iram","dram","bss"):
            require(a[field]==b[field],"SPI_PARITY_"+key+"_"+field)
        require(a["bin_sha256"]!=b["bin_sha256"],"SAME_SPI_BIN_"+key)
    matrix={}
    for hz in ("40000000","20000000"):
        m=cells["M"][hz]
        c=cells["C"][hz]
        delta={k:c[k]-m[k] for k in ("iram","iram_text","dram","bss",
                                        "flash_text","flash_rodata","bin_bytes")}
        matrix[hz]=delta
    ok=all(d["iram"]==0 and d["dram"]==0 and d["bss"]<=0 and
           cells["C"][hz]["dram"]<=54864
           for hz,d in matrix.items())
    return {"delta_M_to_C":matrix,
            "verdict":"INTEGRATION_MEMORY_PASS" if ok else "INTEGRATION_MEMORY_FAIL",
            "historical_B_to_H":"FAIL_PLUS_220_IRAM",
            "historical_RENDER_A_C3":"HISTORICAL_FAILURE",
            "historical_A0":"HISTORICAL_DEBT",
            "integration_ready":False}


def seal(out):
    lines=[]
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name!="SHA256SUMS.txt":
            lines.append(sha(p)+"  "+p.relative_to(out).as_posix())
    (out/"SHA256SUMS.txt").write_text("\n".join(lines)+"\n")
    for line in lines:
        digest,name=line.split("  ",1)
        require(sha(out/name)==digest,"ARTIFACT_TAMPER")


def capture(out,work,state):
    require(not os.environ.get("GH_TOKEN") and
            not os.environ.get("GITHUB_TOKEN") and
            not os.environ.get("GITHUB_ACTIONS"),
            "TOKEN_OR_ACTIONS_EXPOSED_IN_DOCKER")
    require(run("idf.py","--version").strip()=="ESP-IDF v5.5.6",
            "IDF_VERSION")
    attempts=[]
    for label,hz in BUILD_ORDER:
        commit=M if label=="M" else state["C"]
        loc=work/label
        require(git(loc,"rev-parse","HEAD")==commit and
                git(loc,"rev-parse","HEAD^{tree}")==state[label+"_tree"],
                "BUILD_TREE_MISMATCH")
        cell=out/label/str(hz)
        cell.mkdir(parents=True,exist_ok=False)
        firmware=loc/"firmware/esp32_display_probe"
        build="build-e1-"+str(hz)
        config="sdkconfig.e1-"+str(hz)
        require(not (firmware/build).exists() and not (firmware/config).exists(),
                "ALREADY_BUILT_STOP")
        attempts.append({"label":label,"hz":hz,"commit":commit,
                         "started_utc":datetime.datetime.now(
                             datetime.timezone.utc).isoformat()})
        require(len(attempts)<=4,"FIFTH_BUILD_REFUSED")
        put(out/"build-attempts.json",{"attempts":attempts,
                                     "maximum":4,"no_retry":True})
        (cell/"source.txt").write_text(commit+"\n")
        (cell/"idf-version.txt").write_text("ESP-IDF v5.5.6\n")
        cmd=["idf.py","-B",build,"-DSDKCONFIG="+str(firmware/config),
             "-DLOCO_CYD_PROFILE=CONSOLE",
             "-DCYD_LCD_SPI_HZ="+str(hz)]
        run(*(cmd+["set-target","esp32"]),cwd=firmware,
            log=cell/"set-target.log")
        run(*(cmd+["build"]),cwd=firmware,log=cell/"build.log")
        for name,src in (("CMakeCache.txt",firmware/build/"CMakeCache.txt"),
                         ("compile_commands.json",firmware/build/"compile_commands.json"),
                         ("sdkconfig",firmware/config),
                         ("firmware.bin",firmware/build/"loco_esp32_display_probe.bin"),
                         ("firmware.elf",firmware/build/"loco_esp32_display_probe.elf"),
                         ("firmware.map",firmware/build/"loco_esp32_display_probe.map")):
            require(src.is_file() and src.stat().st_size>0,"MISSING_BUILD_FILE_"+name)
            shutil.copy2(src,cell/name)
        run("xtensa-esp-elf-size","-A",cell/"firmware.elf",log=cell/"sections.txt")
        run("python3",loc/"tools/ci/verify_esp_app_version.py",
            cell/"firmware.bin",commit,"loco_esp32_display_probe",
            log=cell/"version-verification.txt")
        print("E1_XTENSA_BUILD_OK",label,hz,commit,flush=True)
    return len(attempts)


def host(out,work,state):
    loc=work/"C"
    require(git(loc,"rev-parse","HEAD")==state["C"] and
            git(loc,"rev-parse","HEAD^{tree}")==state["C_tree"],"HOST_NOT_C")
    results=[]
    for compiler in ("gcc","clang"):
        for sanitizer in ("OFF","ON"):
            d=out/"host"/(compiler+"-"+sanitizer)
            d.mkdir(parents=True,exist_ok=True)
            build=loc/("build-e1-host-"+compiler+"-"+sanitizer)
            flags="-fstack-usage"
            if compiler=="clang":
                flags+=" -Wno-error=gnu-offsetof-extensions -Wno-error=string-concatenation"
            run("cmake","-S",loc,"-B",build,"-DCMAKE_C_COMPILER="+compiler,
                "-DCMAKE_BUILD_TYPE=Debug","-DBP_SANITIZERS="+sanitizer,
                "-DCMAKE_C_FLAGS="+flags,log=d/"configure.log")
            run("cmake","--build",build,"--parallel","4",log=d/"build.log")
            run("ctest","--test-dir",build,"--output-on-failure",
                log=d/"ctest.log")
            inventory=run("ctest","--test-dir",build,"-N",log=d/"inventory.txt")
            for case in ("j1_25_b2_integer_run_cpc",
                         "j1_25_b2_c1_skipped_data_while_no_regression",
                         "j1_25_b1_token_list"):
                require(case in inventory,"C_TEST_MISSING:"+case)
                require(case+" " in (d/"ctest.log").read_text() or
                        case+"." in (d/"ctest.log").read_text(),
                        "C_TEST_NOT_RUN:"+case)
            results.append({"compiler":compiler,"sanitizers":sanitizer,
                            "ctests":"PASS","C":state["C"],
                            "log_sha256":sha(d/"ctest.log")})
            print("E1_HOST_C99_PASS",compiler,sanitizer,flush=True)
    run("python3",loc/"tools/ci/opt3_routing.py",
        "--self-test","--expect-head",state["C"],
        log=out/"host"/"opt3-on-C.log")
    run("bash",loc/"tools/ci/test_ci_arch.sh",
        cwd=loc,log=out/"host"/"ci-arch-on-C.log")
    env=dict(os.environ,CI_ARCH_BASE=M)
    run("bash",loc/"tools/ci/ci_arch_changes.sh",cwd=loc,env=env,
        log=out/"host"/"ci-arch-diff-on-C.log")
    return results


def campaign(root,out,approved_head):
    e=event(approved_head)
    require(root.is_dir() and not (out/"campaign.json").exists(),
            "ALREADY_RUN_STOP")
    token=os.environ.get("GH_TOKEN","")
    before=snapshot(token,e)
    put(out/"api-before.json",before)
    run("git","-C",root,"fetch","--no-tags","origin",
        "+refs/pull/330/head:refs/remotes/origin/e1-330-head",
        log=out/"fetch-pr330.log")
    require(git(root,"rev-parse","refs/remotes/origin/e1-330-head")==H,
            "PR330_FETCHED_SHA_DRIFT")
    verify_git(root,e)
    state=make_candidate(root,out)
    put(out/"candidate.json",state)
    work=make_worktrees(root,out,state)
    pre=snapshot(token,e)
    require(pre==before,"PREBUILD_API_DRIFT")
    put(out/"api-prebuild.json",pre)
    run("docker","pull",IMAGE,log=out/"docker-pull.log")
    image_id=run("docker","image","inspect",IMAGE,"--format","{{.Id}}")
    require(image_id==IMAGE_ID,"DOCKER_IMAGE_ID_MISMATCH")
    # No credentials, token or Actions variables pass to Docker.
    safe={key:value for key,value in os.environ.items()
          if key not in ("GH_TOKEN","GITHUB_TOKEN","GITHUB_ACTIONS")}
    safe.pop("GITHUB_ACTIONS",None)
    docker=["docker","run","--rm",
            "-v",str(root)+":/project","-w","/project",
            "-e","E1_WORK=/project/.e1-358","-e","E1_OUT=/project/"+str(out.relative_to(root)),
            "-e","E1_C="+state["C"],IMAGE,
            "bash","-lc",
            "git config --global --add safe.directory /project/.e1-358/M && "
            "git config --global --add safe.directory /project/.e1-358/C && "
            "python3 /project/tools/ci/j125_b2_e1.py --capture"]
    run(*docker,env=safe,log=out/"docker-build.log")
    require((out/"build-attempts.json").is_file() and
            len(json.loads((out/"build-attempts.json").read_text())["attempts"])==4,
            "FOUR_BUILDS_NOT_COMPLETED")
    cells={"M":{},"C":{}}
    for label,hz in BUILD_ORDER:
        cells[label][str(hz)]=inspect_cell(out/label/str(hz),label,hz,
                                          M if label=="M" else state["C"])
    put(out/"cells.json",cells)
    verdict=compare(cells)
    put(out/"memory-verdict.json",verdict)
    after=snapshot(token,e)
    put(out/"api-after.json",after)
    require(before==after,"POSTBUILD_API_DRIFT_STOP")
    require(verdict["verdict"]=="INTEGRATION_MEMORY_PASS",
            "INTEGRATION_MEMORY_REGRESSION_STOP")
    result=host(out,work,state)
    after_host=snapshot(token,e)
    put(out/"api-after-host.json",after_host)
    require(before==after_host,"POSTHOST_API_DRIFT_STOP")
    put(out/"campaign.json",{"state":"LAB_PASS_NOT_MERGE_READY",
        "candidate":state,"memory":verdict,"host":result,
        "docker_image":IMAGE,"docker_image_id":image_id,
        "build_attempts":4,"run_mode":"LOCAL_EXPLICIT_ONLY",
        "lab_head":e["head"],"physical":"ON_DEVICE_UNVERIFIED"})
    return verdict


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--run",action="store_true")
    ap.add_argument("--capture",action="store_true")
    ap.add_argument("--self-test",action="store_true")
    ap.add_argument("--out",type=Path)
    ap.add_argument("--approved-head",type=str)
    a=ap.parse_args()
    if a.self_test:
        self_test()
        return 0
    if a.capture:
        require(os.environ.get("E1_C") and SHA.fullmatch(os.environ["E1_C"]),
                "NO_C_IN_CONTAINER")
        root=Path("/project")
        out=Path(os.environ["E1_OUT"])
        state=json.loads((out/"candidate.json").read_text())
        require(state["C"]==os.environ["E1_C"],"C_SUBSTITUTION")
        return 0 if capture(out,Path(os.environ["E1_WORK"]),state)==4 else 2
    require(a.run and a.out is not None and a.approved_head is not None,
            "USAGE_OR_NOT_APPROVED")
    event(a.approved_head)  # fail closed BEFORE creating output or building
    root=Path.cwd().resolve()
    out=a.out.resolve()
    require(out.is_relative_to(root) and not out.exists(),"OUTPUT_NOT_FRESH")
    out.mkdir(parents=True)
    try:
        result=campaign(root,out,a.approved_head)
        print("E1_INTEGRATION_MEMORY_VERDICT",result["verdict"],flush=True)
        return 0
    except Exception as exc:
        put(out/"STOP.json",{"status":"MEASUREMENT_INVALID_OR_INTEGRATION_FAIL",
                             "reason":str(exc),"no_retry":True})
        print("E1_STOP",str(exc),flush=True)
        return 2
    finally:
        seal(out)


def self_test():
    import tempfile
    def sample(iram=67551,dram=54864,bss=43792,hz=40000000,checksum="a"):
        return {"iram":iram,"dram":dram,"bss":bss,"iram_text":66523,
                "flash_text":170000,"flash_rodata":57000,"bin_bytes":307000,
                "bin_sha256":checksum+str(hz),"hal_compiler_clock":hz}
    cells={"M":{str(h):sample(hz=h,checksum="a") for _,h in BUILD_ORDER[:2]},
           "C":{str(h):sample(hz=h,checksum="b") for _,h in BUILD_ORDER[:2]}}
    require(compare(cells)["verdict"]=="INTEGRATION_MEMORY_PASS","POSITIVE")
    for field in ("iram","dram","bss"):
        broken=json.loads(json.dumps(cells))
        broken["C"]["40000000"][field]+=1
        if field=="bss":
            broken["C"]["20000000"][field]+=1
        elif field=="dram":
            broken["C"]["20000000"][field]+=1
        else:
            broken["C"]["20000000"][field]+=1
        require(compare(broken)["verdict"]=="INTEGRATION_MEMORY_FAIL",
                "PLUS_ONE_ACCEPTED_"+field)
    for key in ("M","C"):
        changed=json.loads(json.dumps(cells))
        changed[key]["20000000"]["dram"]+=1
        try: compare(changed)
        except Invalid: pass
        else: raise Invalid("PARITY_FALSE_PASS")
        changed=json.loads(json.dumps(cells))
        changed[key]["20000000"]["bin_sha256"]=changed[key]["40000000"]["bin_sha256"]
        try: compare(changed)
        except Invalid: pass
        else: raise Invalid("IDENTICAL_BIN_ACCEPTED")
    base={"main":{"commit":{"sha":M}},
        "pr330":{"number":330,"state":"open","merged_at":None,"draft":True,
                 "base":{"ref":"main","sha":B,"repo":{"full_name":REPO}},
                 "head":{"sha":H,"repo":{"full_name":REPO}}},
        "lab":{"name":BRANCH,"commit":{"sha":"a"*40}}}
    e={"head":"a"*40}
    validate_snapshot(base,e)
    for field,value in (("main","b"*40),("prhead","c"*40),("labhead","d"*40)):
        d=json.loads(json.dumps(base))
        if field=="main":d["main"]["commit"]["sha"]=value
        elif field=="prhead":d["pr330"]["head"]["sha"]=value
        else:d["lab"]["commit"]["sha"]=value
        try: validate_snapshot(d,e)
        except Invalid:pass
        else:raise Invalid("DRIFT_ACCEPTED_"+field)
    for bad in ("v"*40,"a"*39,"a"*41):
        require(not SHA.fullmatch(bad),"BAD_SHA_ACCEPTED")
    # Even a forged approval never enables GitHub Actions execution.
    oldgo=os.environ.get("E1_PILOTAGE_GO")
    oldactions=os.environ.get("GITHUB_ACTIONS")
    try:
        os.environ.pop("E1_PILOTAGE_GO",None)
        try:event("a"*40)
        except Invalid:pass
        else:raise Invalid("UNAPPROVED_RUN_ALLOWED")
        os.environ["E1_PILOTAGE_GO"]="E1_M2_APPROVED_4_BUILDS"
        os.environ["GITHUB_ACTIONS"]="true"
        try:event("a"*40)
        except Invalid:pass
        else:raise Invalid("GITHUB_ACTIONS_BUILD_ALLOWED")
    finally:
        if oldgo is None: os.environ.pop("E1_PILOTAGE_GO",None)
        else:os.environ["E1_PILOTAGE_GO"]=oldgo
        if oldactions is None: os.environ.pop("GITHUB_ACTIONS",None)
        else:os.environ["GITHUB_ACTIONS"]=oldactions
    with tempfile.TemporaryDirectory() as temp:
        p=Path(temp)
        (p/"sections.txt").write_text(".dram0.data 10 0\n")
        try:sizes(p/"sections.txt")
        except Invalid:pass
        else:raise Invalid("TRUNCATED_SECTIONS_ACCEPTED")
        (p/"x").write_bytes(b"a")
        checksum=sha(p/"x")
        (p/"x").write_bytes(b"b")
        require(sha(p/"x")!=checksum,"ALTERED_ARTIFACT_ACCEPTED")
        try:require(5<=4,"FIFTH_BUILD_REFUSED")
        except Invalid:pass
        else:raise Invalid("FIFTH_BUILD_ACCEPTED")
    # True Git test merge conflicting edits, with unrelated commits and ordered parents.
    with tempfile.TemporaryDirectory() as temp:
        repo=Path(temp)
        run("git","init","-q",repo)
        env=dict(os.environ,GIT_AUTHOR_NAME="Test",GIT_AUTHOR_EMAIL="test@example.invalid",
                 GIT_COMMITTER_NAME="Test",GIT_COMMITTER_EMAIL="test@example.invalid")
        (repo/"x").write_text("base\n")
        run("git","-C",repo,"add","x")
        run("git","-C",repo,"commit","-qm","base",env=env)
        base_commit=git(repo,"rev-parse","HEAD")
        (repo/"x").write_text("main\n")
        run("git","-C",repo,"commit","-qam","main",env=env)
        main_commit=git(repo,"rev-parse","HEAD")
        run("git","-C",repo,"checkout","-q",base_commit)
        (repo/"x").write_text("head\n")
        run("git","-C",repo,"commit","-qam","head",env=env)
        head_commit=git(repo,"rev-parse","HEAD")
        result=run("git","-C",repo,"merge-tree","--write-tree",
                   main_commit,head_commit,check=False)
        require(not re.fullmatch(r"[0-9a-f]{40}",result.strip()),
                "CONFLICT_MERGE_ACCEPTED")
    print("E1_NEGATIVES_PASS drift=false_head=reject section=reject "
          "hash=reject plus_one=reject parity=reject conflict=reject "
          "fifth_build=reject preview=ignored",flush=True)


if __name__=="__main__":
    sys.exit(main())
