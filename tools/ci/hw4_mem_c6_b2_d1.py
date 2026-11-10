#!/usr/bin/env python3
"""#354 C6-B2-D1: one-shot B/H SPI40 pre-link evidence; never a memory gate.

Runs only on a trusted D1 LAB controller. Does not run GitHub API with untrusted
source code. Docker receives a minimal allowlist of env vars and no GH_TOKEN.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

from hw4_a0_compare_memory import read_size

REPO = 'Kharn27/ESP32-Locomotive-Basic'
M = '3d7f1dc914324a846ff92ba3a33ab9e03916b076'
B = '4d261f2a76374ab99a4dd7415cae7a097330c46b'
H = '64b0087d5087903fee175c4f149c65a65bb43fe6'
TREES = {'base': 'd74061cb975981aafb022409cf1e9682f934235d',
         'head': 'ed23017e46a7f54c76447bdb77937de540588ea8'}
IMAGE = 'espressif/idf@sha256:bf72fe7a15c22849a9a94147301165a545fb8905d97c176cf748e3e4614cac84'
IMAGE_ID = 'sha256:b5ed7387fed7f3c0cc613272ee7dedab5dddfac6f771ee66af41d93f8d46c0bc'
ORACLE_RUN = 42660089530
ORACLE_ARTIFACT = 13693788432
ORACLE_DIGEST = 'sha256:29b8f28c7fcaadd808c3f0ce339ea2a3c18331154a1da08f9116c6ac2c067777'
ORACLE_MANIFEST = '0d5011d103cde1ea6429a4d4edbad8ba6a72aefab02cba1b71c6c242dd014c0b'
LAB_WORKFLOW = 'LAB HW4-MEM-C6-B2-D1 PRELINK 2-XTENSA NOT_REQUIRED'
BRANCH = 'feat/hw4-mem-c6-b2-d1-prelink'
EXPECTED = {'base': {'iram': 67331, 'dram': 54864, 'bss': 43792,
                     'flash_text': 168426, 'flash_rodata': 56484},
            'head': {'iram': 67551, 'dram': 54864, 'bss': 43792,
                     'flash_text': 170242, 'flash_rodata': 56484}}
TARGETS = {
    'esp_system': ('cpu_start.c.obj', 'debug_helpers.c.obj', 'startup.c.obj',
                   'esp_err.c.obj', 'crosscore_int.c.obj', 'esp_ipc.c.obj',
                   'panic_handler.c.obj'),
    'freertos': ('tasks.c.obj',),
    'spi_flash': ('spi_flash_os_func_app.c.obj', 'cache_utils.c.obj',
                  'esp_flash_api.c.obj', 'memspi_host_driver.c.obj'),
    'esp_hw_support': ('rtc_clk.c.obj', 'brownout.c.obj'),
    'log': ('log.c.obj', 'tag_log_level.c.obj'),
    'loco_core': ('basic_executor.c.obj', 'basic_session_runtime.c.obj'),
}
SHA = re.compile(r'[0-9a-f]{40}\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')


class Invalid(RuntimeError):
    pass


def require(ok, reason):
    if not ok:
        raise Invalid('MEASUREMENT_INVALID:' + reason)


def sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def put(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')


def sh(cmd, cwd=None, env=None, log=None):
    p = subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    if log:
        Path(log).write_text(p.stdout + '\nSTDERR:\n' + p.stderr)
    require(p.returncode == 0, 'COMMAND_FAILED:' + Path(cmd[0]).name + ':' + str(p.returncode))
    return p.stdout.strip()


def git(root, *args):
    return sh(['git', '-C', str(root), *args])


def get(path, token):
    require(bool(token) and not re.search(r'\s', token), 'TOKEN_UNAVAILABLE')
    require(path.startswith('/') and '//' not in path and '\\' not in path,
            'UNSAFE_API_PATH')
    req = urllib.request.Request('https://api.github.com/repos/' + REPO + path,
        method='GET', headers={'Authorization':'Bearer '+token,
            'Accept':'application/vnd.github+json',
            'X-GitHub-Api-Version':'2022-11-28', 'User-Agent':'c6-d1-readonly'})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            require(response.status == 200, 'API_HTTP_NOT_OK')
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        raise Invalid('MEASUREMENT_INVALID:API_UNAVAILABLE:'+str(getattr(exc,'code','NETWORK'))) from None


def validate_snap(main, pr, lab, event):
    require(main['commit']['sha'] == M, 'MAIN_DRIFT')
    require(pr['number']==330 and pr['state']=='open' and pr.get('merged_at') is None,
            'PR330_CLOSED')
    require(pr['base']['ref']=='main' and pr['base']['repo']['full_name']==REPO and
            pr['head']['repo']['full_name']==REPO and
            pr['base']['sha']==B and pr['head']['sha']==H,
            'PR330_REAL_BASE_HEAD_DRIFT')
    require(lab['number'] == event['lab_number'] and lab['state']=='open' and
            lab['base']['ref']=='main' and lab['base']['sha']==M and
            lab['head']['sha']==event['lab_head'] and
            lab['head']['repo']['full_name']==REPO,
            'LAB_HEAD_BASE_REPO_DRIFT')
    require(all(SHA.fullmatch(s) for s in (M,B,H,event['lab_head'])), 'INVALID_SHA')
    return {'captured_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
            'main':M,'base':B,'head':H,'lab_head':event['lab_head'],
            'lab_number':event['lab_number'],'preview_sha':pr.get('merge_commit_sha')}


def current_event():
    e={'repo':os.environ.get('GITHUB_REPOSITORY'),
       'lab_head':os.environ.get('LAB_HEAD'),
       'lab_number':int(os.environ.get('LAB_PR_NUMBER','0')),
       'run_id':int(os.environ.get('GITHUB_RUN_ID','0')),
       'attempt':int(os.environ.get('GITHUB_RUN_ATTEMPT','0')),
       'name':os.environ.get('GITHUB_EVENT_NAME'),
       'branch':os.environ.get('GITHUB_HEAD_REF')}
    require(e['repo']==REPO and e['branch']==BRANCH and
            e['name']=='pull_request' and e['attempt']==1 and
            e['run_id']>0 and e['lab_number']>0 and e['lab_number']!=330 and
            isinstance(e['lab_head'],str) and SHA.fullmatch(e['lab_head']),
            'NOT_FIRST_TRUSTED_PULL_REQUEST_RUN')
    return e


def one_shot(runs, e):
    """Reject any other invocation, including a later push on different HEAD."""
    require(isinstance(runs, list), 'RUN_HISTORY_UNAVAILABLE')
    related=[x for x in runs if x.get('name')==LAB_WORKFLOW and
             x.get('head_branch')==BRANCH and x.get('event')=='pull_request']
    require(any(x.get('id')==e['run_id'] and x.get('head_sha')==e['lab_head']
                for x in related), 'CURRENT_LAB_RUN_NOT_FOUND')
    require(len(related)==1 and related[0]['id']==e['run_id'] and
            related[0].get('run_attempt')==1, 'LAB_ALREADY_STARTED_NO_RERUN')
    return {'lab_run_id':e['run_id'], 'candidate_runs':len(related),
            'run_attempt':e['attempt'], 'source':'GitHub GET /actions/runs'}


def github_runs(token):
    """Fail closed if history exceeds bounded pagination or GitHub has no runs."""
    result=[]
    for page in range(1,11):
        response=get('/actions/runs?event=pull_request&branch='+BRANCH+'&per_page=100&page='+str(page),token)
        part=response.get('workflow_runs')
        require(isinstance(part,list),'RUN_HISTORY_MALFORMED')
        result.extend(part)
        if len(part)<100:
            return result
    raise Invalid('MEASUREMENT_INVALID:RUN_HISTORY_PAGINATION_LIMIT')


def snapshot(token, e):
    result=validate_snap(get('/branches/main',token),get('/pulls/330',token),
                         get('/pulls/'+str(e['lab_number']),token),e)
    result['one_shot']=one_shot(github_runs(token),e)
    return result


def verify_main_ci(token):
    """A2 authorizes no expensive cells without six *real* push successes."""
    expected = {
        42776806898: 'CI-C99 portable Linux 4 cells',
        42776806938: 'CI-ARCH core HW4 CPC isolation',
        42776807175: 'CI-OPT3 five-family routing gate',
        42776807197: 'CI-CPC-PERMANENT sealed CPC history',
        42776806929: 'CI-XTENSA U1-B three profiles one ESP-IDF root',
        42776807029: 'HW4-ESC-ORACLE-R1 independent CPC keyboard candidate',
    }
    runs=get('/actions/runs?head_sha='+M+'&event=push&per_page=100',token)
    found={r['id']:r for r in runs.get('workflow_runs',[]) if r.get('id') in expected}
    require(len(found)==6,'MAIN_SIX_CI_MISSING')
    for run_id, name in expected.items():
        r=found[run_id]
        require(r.get('name')==name and r.get('head_sha')==M and
                r.get('event')=='push' and r.get('status')=='completed' and
                r.get('conclusion')=='success',
                'MAIN_PUSH_CI_NOT_SUCCESS:'+str(run_id))
    return {'main':M,'verified_6_push_runs':sorted(expected),
            'all_completed_success':True}


def verify_oracle(old, metadata):
    old=Path(old)
    require(sha_file(old/'SHA256SUMS.txt')==ORACLE_MANIFEST,'ORACLE_MANIFEST_SHA')
    lines=(old/'SHA256SUMS.txt').read_text().splitlines()
    require(len(lines)==134,'ORACLE_MANIFEST_COUNT')
    for line in lines:
        m=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
        require(m is not None,'ORACLE_MANIFEST_FORMAT')
        p=Path(m[2]);require(not p.is_absolute() and '..' not in p.parts,'ORACLE_PATH_ESCAPE')
        f=old/p
        require(f.is_file() and sha_file(f)==m[1],'ORACLE_FILE_DIGEST:'+m[2])
    for label,commit in [('base',B),('head',H)]:
        loc=old/label/'spi40'
        meta=json.loads((loc/'source.json').read_text())
        require(meta['source_sha']==commit and meta['source_tree']==TREES[label]
                and meta['clock_hz']==40000000 and meta['profile']=='CONSOLE'
                and meta['container_image']==IMAGE and
                meta['docker_image_id']==IMAGE_ID and
                meta['map_sha256']==sha_file(loc/'firmware.map'),
                'ORACLE_CELL_PROVENANCE:'+label)
        require({k:read_size(loc/'sections.txt')[k] for k in EXPECTED[label]}
                == EXPECTED[label], 'ORACLE_METRIC_CHANGED:'+label)
        metadata[label]={name:sha_file(loc/name) for name in ('firmware.elf','firmware.bin',
                               'firmware.map','sections.txt','compile_commands.json','sdkconfig')}
    return {'manifest_sha256':ORACLE_MANIFEST,'count':len(lines),
            'run_id':ORACLE_RUN,'artifact_id':ORACLE_ARTIFACT,
            'artifact_zip_sha256':ORACLE_DIGEST,'reference_hashes':metadata}


def verify_git(root, event):
    require(git(root,'rev-parse','HEAD')==event['lab_head'],'UNTRUSTED_LAB_CONTROLLER')
    require(git(root,'status','--porcelain','--untracked-files=no')=='','LAB_DIRTY')
    for commit in (M,B,H):
        require(git(root,'cat-file','-t',commit)=='commit','MISSING_GIT_OBJECT')
    require(git(root,'merge-base',B,H)==B,'WRONG_BASE_HEAD_GRAPH')
    for label,commit in [('base',B),('head',H)]:
        require(git(root,'rev-parse',commit+'^{tree}')==TREES[label],
                'SOURCE_TREE_MISMATCH:'+label)


def verify_context(label, loc, old, out):
    cell=out/label
    d=read_size(cell/'sections.txt')
    require({k:d[k] for k in EXPECTED[label]}==EXPECTED[label],
            'REPRODUCED_SECTION_MISMATCH:'+label)
    cache=(cell/'CMakeCache.txt').read_text()
    require('LOCO_CYD_PROFILE:STRING=CONSOLE' in cache and
            'CYD_LCD_SPI_HZ:STRING=40000000' in cache,'PROFILE_CLOCK_BAD')
    commands=json.loads((cell/'compile_commands.json').read_text())
    hal=[x for x in commands if x.get('file','').endswith('/cyd_ili9341.c')]
    require(len(hal)==1 and '-DLCD_CLOCK_HZ=40000000U' in
            (hal[0].get('arguments') or hal[0].get('command','').split()),
            'ACTUAL_HAL_CLOCK_BAD')
    require((cell/'idf-version.txt').read_text().strip()=='ESP-IDF v5.5.6',
            'WRONG_IDF_VERSION')
    require('14.2.0' in (cell/'gcc-version.txt').read_text() and
            '2.43.1' in (cell/'ld-version.txt').read_text(),
            'WRONG_XTENSA_TOOLCHAIN')
    oldcell=old/label/'spi40'
    hashes={name:{'previous_sha256':sha_file(oldcell/name),
                  'current_sha256':sha_file(cell/name),
                  'byte_identical':sha_file(oldcell/name)==sha_file(cell/name)}
            for name in ('firmware.elf','firmware.bin','firmware.map','sections.txt',
                         'compile_commands.json','sdkconfig')}
    return {'label':label,'source_sha':B if label=='base' else H,
            'tree_sha':TREES[label], 'metrics':{k:d[k] for k in EXPECTED[label]},
            'comparison_old_B2B':hashes, 'clock_hz':40000000,'profile':'CONSOLE'}


def parse_iram_map(path):
    """Independent accounting for the GNU ld IRAM output and pre-relax inputs.

    Zero-sized input contributions are retained. Duplicate object-section keys
    are aggregated when comparing B/H; no unproved conversion to alignment.
    """
    data=Path(path).read_text()
    require('Linker script and memory map' in data, 'MAP_HEADER_MISSING')
    start=data.index('.iram0.text ', data.index('Linker script and memory map'))
    end=data.index('.dram0.data',start)
    lines=data[start:end].splitlines()
    header=re.match(r'^\.iram0\.text\s+0x[0-9a-f]+\s+0x([0-9a-f]+)',lines[0])
    require(header is not None,'MAP_IRAM_OUTPUT_HEADER_BAD')
    iram_length=int(header.group(1),16)
    short=re.compile(r'^\s*(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(\S+\.a\([^)]+\))\s*$')
    single=re.compile(r'^\s*(\.\S+)\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(\S+\.a\([^)]+\))\s*$')
    fill_re=re.compile(r'^\s*\*fill\*\s+0x[0-9a-f]+\s+0x([0-9a-f]+)\s*$')
    before_re=re.compile(r'^\s*(0x[0-9a-f]+) \(size before relaxing\)\s*$')
    last_section=None;entries=[];fill=0
    for i,line in enumerate(lines):
        f=fill_re.match(line)
        if f:
            fill+=int(f.group(1),16)
        m=single.match(line)
        if m:
            section,addr,size,obj=m.groups()
        else:
            m=short.match(line)
            if not m:
                mt=re.match(r'^\s*(\.\S+)\s*$',line)
                if mt: last_section=mt.group(1)
                continue
            addr,size,obj=m.groups();section=last_section
        require(section is not None,'MAP_ORPHAN_INPUT_SECTION')
        after=int(size,16)
        bn=before_re.match(lines[i+1]) if i+1<len(lines) else None
        initial=int(bn.group(1),16) if bn else after
        entries.append({'object':obj,'section':section,'before':initial,
                        'after':after,'address':int(addr,16)})
    require(len(entries)==1054 and
            len(set((e['object'],e['section']) for e in entries))==1052,
            'MAP_ENTRY_INVENTORY_DRIFT')
    require(sum(e['before'] for e in entries)==78051,'MAP_PRELINK_SIZE_DRIFT')
    require(sum(e['after'] for e in entries)+fill==iram_length,
            'MAP_OUTPUT_NOT_COVERED')
    return {'section_size':iram_length,'entry_count':len(entries),
            'key_count':1052, 'before_sum':78051,
            'object_after_sum':sum(e['after'] for e in entries),
            'fill':fill,'entries':entries}


def account_iram_difference(old, out):
    old_b=parse_iram_map(old/'base'/'spi40'/'firmware.map')
    old_h=parse_iram_map(old/'head'/'spi40'/'firmware.map')
    new_b=parse_iram_map(out/'base'/'firmware.map')
    new_h=parse_iram_map(out/'head'/'firmware.map')
    for old_map,new_map,label in ((old_b,new_b,'B'),(old_h,new_h,'H')):
        require((old_map['section_size'],old_map['before_sum'],old_map['key_count'],
                 old_map['object_after_sum'],old_map['fill']) ==
                (new_map['section_size'],new_map['before_sum'],new_map['key_count'],
                 new_map['object_after_sum'],new_map['fill']),
                'NEW_LINK_IRAM_MAP_DIFFERENT_FROM_B2B:'+label)
    def totals(x):
        d={}
        for e in x['entries']:
            k=(e['object'],e['section'])
            a,b=d.get(k,(0,0))
            d[k]=(a+e['before'],b+e['after'])
        return d
    b,h=totals(new_b),totals(new_h)
    require(set(b)==set(h),'DIFFERENT_MAP_INPUT_KEYS')
    require(all(b[k][0]==h[k][0] for k in b), 'BEFORE_RELAX_INPUT_CHANGED')
    changes=[{'archive_member':k[0],'section':k[1],
              'B_post':b[k][1], 'H_post':h[k][1],
              'post_delta':h[k][1]-b[k][1],'pre_bh':b[k][0]}
             for k in sorted(b) if h[k][1]!=b[k][1]]
    require(new_h['section_size']-new_b['section_size']==220 and
            new_h['object_after_sum']-new_b['object_after_sum']==216 and
            new_h['fill']-new_b['fill']==4,'IRAM_220_NOT_REPRODUCED')
    return {'B':{k:v for k,v in new_b.items() if k!='entries'},
            'H':{k:v for k,v in new_h.items() if k!='entries'},
            'sum_object_deltas':sum(e['post_delta'] for e in changes),
            'fill_delta':new_h['fill']-new_b['fill'],
            'total_delta':220,'changed_sections':changes,
            'output_map_contributions':'REPRODUCED_PRE_AND_POST_RELAXATION'}


def summarize_prelink(out):
    """Compare exact pre-link objects, relocations and link layout."""
    targets={}
    for component, names in TARGETS.items():
        for member in names:
            key=component+'/'+member
            b=out/'base'/'prelink'/component/member
            h=out/'head'/'prelink'/component/member
            require(b.is_file() and h.is_file(),'MISSING_PRELINK_MEMBER:'+key)
            brel=Path(str(b)+'.relocs.txt')
            hrel=Path(str(h)+'.relocs.txt')
            require(brel.is_file() and hrel.is_file(),'MISSING_RELOCATION_TABLE:'+key)
            targets[key]={
                'object_sha256':{'B':sha_file(b),'H':sha_file(h)},
                'object_byte_identical':sha_file(b)==sha_file(h),
                'relocation_sha256':{'B':sha_file(brel),'H':sha_file(hrel)},
                'relocation_text_identical':brel.read_text()==hrel.read_text(),
                'B_reloc_lines':sum('R_XTENSA_' in x for x in brel.read_text().splitlines()),
                'H_reloc_lines':sum('R_XTENSA_' in x for x in hrel.read_text().splitlines())}
    return {'count':sum(map(len,TARGETS.values())),'objects':targets,
            'root_cause':'ROOT_CAUSE_UNVERIFIED',
            'scope':'PRELINK_INPUTS_OBSERVED_NOT_AUTOMATIC_CAUSAL_PROOF'}


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('--workspace',type=Path,required=True)
    ap.add_argument('--oracle',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args(argv)
    root=args.workspace.resolve();old=args.oracle.resolve();out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=True)
    attempted=0
    try:
        e=current_event(); token=os.environ.get('GH_TOKEN')
        require(root.is_dir() and old.is_dir(),'BAD_WORKSPACE_OR_ORACLE')
        before=snapshot(token,e)
        put(out/'snapshot-initial.json',before)
        put(out/'main-ci-gate.json',verify_main_ci(token))
        prior={}
        put(out/'old-oracle-proof.json',verify_oracle(old,prior))
        sh(['git','-C',str(root),'fetch','--no-tags','origin',
            '+refs/pull/330/head:refs/remotes/origin/c6-d1-pr330-head'],
            log=out/'fetch.log')
        require(git(root,'rev-parse','refs/remotes/origin/c6-d1-pr330-head')==H,
                'PR330_FETCHED_HEAD_DRIFT')
        verify_git(root,e)
        for label,commit in [('base',B),('head',H)]:
            work=root/'.c6-d1-worktrees'/label
            require(not work.exists(),'PREEXISTING_WORKTREE')
            sh(['git','-C',str(root),'worktree','add','--detach',str(work),commit],
               log=out/('worktree-'+label+'.log'))
            require(git(work,'rev-parse','HEAD')==commit and
                    git(work,'rev-parse','HEAD^{tree}')==TREES[label],
                    'UNTRUSTED_SOURCE_WORKTREE')
        sh(['docker','pull',IMAGE],log=out/'docker-pull.log')
        digest_list=json.loads(sh(['docker','image','inspect',IMAGE,
                                  '--format','{{json .RepoDigests}}']))
        require(any(x.endswith(IMAGE.split('@')[1]) for x in digest_list),
                'DOCKER_REPODIGEST_MISMATCH')
        image_id=sh(['docker','image','inspect',IMAGE,'--format','{{.Id}}'])
        require(image_id==IMAGE_ID,'DOCKER_IMAGE_ID_DRIFT')
        put(out/'image.json',{'image':IMAGE,'image_id':image_id,'repo_digests':digest_list})
        results={}
        for label,commit in [('base',B),('head',H)]:
            check=snapshot(token,e)
            put(out/(label+'-snapshot-pre.json'),check)
            require(git(root,'rev-parse','HEAD')==e['lab_head'],
                    'CONTROLLER_HEAD_MOVED')
            work=root/'.c6-d1-worktrees'/label
            require(git(work,'rev-parse','HEAD')==commit and
                    git(work,'rev-parse','HEAD^{tree}')==TREES[label],
                    'SOURCE_MOVED_BEFORE_BUILD')
            require(attempted<2,'TWO_BUILD_BUDGET_EXCEEDED')
            attempted+=1
            put(out/'attempts.json',{'attempted':attempted,'budget_max':2,
                    'physical_build':label+'/spi40','run_id':e['run_id'],
                    'run_attempt':e['attempt']})
            target=out/label
            target.mkdir()
            script=out/'_capture.sh'
            script.write_text(CAPTURE_SHELL)
            cmd=['docker','run','--rm','-v',str(root)+':'+str(root),
                 '-w',str(work/'firmware/esp32_display_probe'),
                 '-e','D1_ROOT='+str(root), '-e','D1_OUT='+str(target),
                 '-e','D1_LABEL='+label, '-e','D1_SOURCE='+commit,
                 '-e','D1_TREE='+TREES[label], '-e','D1_IMAGE='+IMAGE_ID,
                 '-e','IDF_GIT_SAFE_DIR='+str(work),
                 IMAGE, 'bash',str(script)]
            sh(cmd,log=target/'docker-output.log')
            require(git(work,'rev-parse','HEAD')==commit,'SOURCE_MOVED_AFTER_BUILD')
            results[label]=verify_context(label,work,old,out)
            put(out/(label+'-reproduction.json'),results[label])
            put(out/(label+'-snapshot-post.json'),snapshot(token,e))
            print('C6_D1_PHYSICAL_XTENSA_BUILD',label,'SPI40',results[label]['metrics'],flush=True)
        require(attempted==2,'MISSING_REQUIRED_BH_BUILD')
        put(out/'iram-relax-accounting.json',account_iram_difference(old,out))
        analysis=summarize_prelink(out)
        put(out/'prelink-diff.json',analysis)
        put(out/'reproduction.json',{'status':'REPRODUCED_SECTIONS',
            'sources':results,'physical_builds':attempted,'toolchain':'ESP-IDF 5.5.6',
            'image':IMAGE,'image_id':IMAGE_ID,
            'legacy_PR_INCREMENTAL_VERDICT':'FAIL',
            'legacy_INTEGRATION_MEMORY_VERDICT':'PASS_ONLY_OLD_M_C',
            'integration_current_main':'UNVERIFIED/BLOCKED',
            'root_cause':'ROOT_CAUSE_UNVERIFIED',
            'historical':'RENDER_A/C3_HISTORICAL_FAILURE;A0_HISTORICAL_DEBT',
            'on_device':'ON_DEVICE_UNVERIFIED'})
        put(out/'snapshot-final.json',snapshot(token,e))
        print('C6_D1_PRELINK_CAPTURED two_builds=2 targets='+str(analysis['count'])+
              ' root=ROOT_CAUSE_UNVERIFIED',flush=True)
        return 0
    except (Invalid,KeyError,TypeError,ValueError,OSError,subprocess.CalledProcessError,
            json.JSONDecodeError) as exc:
        put(out/'invalid.json',{'status':'MEASUREMENT_INVALID','reason':str(exc),
            'attempted_builds':attempted,'max_builds':2,
            'root_cause':'ROOT_CAUSE_UNVERIFIED'})
        print('C6_D1_STOP',str(exc),'attempts',attempted,flush=True)
        return 2


CAPTURE_SHELL = r'''#!/usr/bin/env bash
set -euo pipefail
test -z "${GH_TOKEN:-}" && test -z "${GITHUB_TOKEN:-}" && test -z "${GITHUB_ACTIONS:-}"
F="$PWD"; O="$D1_OUT"; L="$D1_LABEL"
BUILD="build-d1-${L}-spi40"; CFG="sdkconfig.d1-${L}-spi40"
test ! -e "$BUILD" && test ! -e "$CFG"
idf.py --version > "$O/idf-version.txt"
grep -Fx 'ESP-IDF v5.5.6' "$O/idf-version.txt"
xtensa-esp-elf-gcc --version > "$O/gcc-version.txt"
xtensa-esp-elf-ld --version > "$O/ld-version.txt"
idf.py -B "$BUILD" -DSDKCONFIG="$F/$CFG" -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=40000000 set-target esp32 > "$O/set-target.log" 2>&1 || { tail -100 "$O/set-target.log"; exit 2; }
idf.py -B "$BUILD" -DSDKCONFIG="$F/$CFG" -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=40000000 build > "$O/build.log" 2>&1 || { tail -100 "$O/build.log"; exit 2; }
cp "$BUILD/CMakeCache.txt" "$O/CMakeCache.txt"
cp "$BUILD/compile_commands.json" "$O/compile_commands.json"
cp "$F/$CFG" "$O/sdkconfig"
cp "$BUILD/loco_esp32_display_probe.elf" "$O/firmware.elf"
cp "$BUILD/loco_esp32_display_probe.bin" "$O/firmware.bin"
cp "$BUILD/loco_esp32_display_probe.map" "$O/firmware.map"
xtensa-esp-elf-size -A "$O/firmware.elf" > "$O/sections.txt"
xtensa-esp-elf-readelf -sW "$O/firmware.elf" > "$O/linked-symbols.txt"
xtensa-esp-elf-readelf -SW "$O/firmware.elf" > "$O/linked-sections.txt"
xtensa-esp-elf-readelf -h "$O/firmware.elf" > "$O/linked-header.txt"
grep -E 'Machine:.*Xtensa' "$O/linked-header.txt"
# Exact final invocation, without a second link or altered linker flags.
if test -s "$BUILD/CMakeFiles/loco_esp32_display_probe.elf.dir/link.txt"; then
    cp "$BUILD/CMakeFiles/loco_esp32_display_probe.elf.dir/link.txt" "$O/link-command.txt"
else
    ninja -C "$BUILD" -t commands loco_esp32_display_probe.elf | tail -n 1 > "$O/link-command.txt"
fi
test -s "$O/link-command.txt"
grep -F 'loco_esp32_display_probe.elf' "$O/link-command.txt"
# Capture link scripts and command files without changing linker invocation.
mkdir -p "$O/link-scripts"
find "$BUILD" -type f \( -name '*.ld' -o -name '*.rsp' \) -size -2048k -print0 | while IFS= read -r -d '' x; do
    d="${x#${BUILD}/}"; mkdir -p "$O/link-scripts/$(dirname "$d")"; cp "$x" "$O/link-scripts/$d"
done
# Archival inputs: exact targeted members plus complete input archives.
mkdir -p "$O/archives" "$O/prelink"
for component in esp_system freertos spi_flash esp_hw_support log loco_core; do
    a="$BUILD/esp-idf/$component/lib${component}.a"
    test -s "$a"
    cp "$a" "$O/archives/lib${component}.a"
    xtensa-esp-elf-ar t "$a" > "$O/archives/lib${component}-members.txt"
done
TARGETS=(
'esp_system cpu_start.c.obj' 'esp_system debug_helpers.c.obj' 'esp_system startup.c.obj'
'esp_system esp_err.c.obj' 'esp_system crosscore_int.c.obj' 'esp_system esp_ipc.c.obj'
'esp_system panic_handler.c.obj' 'freertos tasks.c.obj'
'spi_flash spi_flash_os_func_app.c.obj' 'spi_flash cache_utils.c.obj'
'spi_flash esp_flash_api.c.obj' 'spi_flash memspi_host_driver.c.obj'
'esp_hw_support rtc_clk.c.obj' 'esp_hw_support brownout.c.obj'
'log log.c.obj' 'log tag_log_level.c.obj'
'loco_core basic_executor.c.obj' 'loco_core basic_session_runtime.c.obj')
for pair in "${TARGETS[@]}"; do
    read -r comp member <<< "$pair"
    dest="$O/prelink/$comp"; mkdir -p "$dest"
    archive="$BUILD/esp-idf/$comp/lib${comp}.a"
    test "$(grep -Fxc "$member" "$O/archives/lib${comp}-members.txt")" -eq 1
    xtensa-esp-elf-ar p "$archive" "$member" > "$dest/$member"
    test -s "$dest/$member"
    xtensa-esp-elf-readelf -rW "$dest/$member" > "$dest/$member.relocs.txt"
    xtensa-esp-elf-readelf -SW -sW "$dest/$member" > "$dest/$member.sections-symbols.txt"
    xtensa-esp-elf-objdump -dr "$dest/$member" > "$dest/$member.disasm-relocs.txt"
    # Prove the archive member is byte-identical to the actual compiler output.
    mapfile -d '' inputs < <(find "$BUILD/esp-idf/$comp" -name "$member" -type f -print0)
    test "${#inputs[@]}" -eq 1
    cmp "$dest/$member" "${inputs[0]}"
done
sha256sum "$O"/archives/*.a > "$O/archive-digests.txt"
echo "D1_REAL_PRELINK_CAPTURED label=$L targets=${#TARGETS[@]}"'''

if __name__=='__main__':
    sys.exit(main())