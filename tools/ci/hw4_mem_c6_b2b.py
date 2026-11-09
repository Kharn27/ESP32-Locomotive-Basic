#!/usr/bin/env python3
"""C6-B2-B #351: eight *actual* Xtensa CONSOLE builds; two independent verdicts.

Trusted control script runs on a pinned PR #351 checkout. The untrusted #330
sources are built only inside Docker WITHOUT a GitHub token/host credentials.
No historical budgets, required checks, or C5 code are modified.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

from hw4_mem_c5_v2 import build_metrics, IMAGE, CLOCKS, EXPECTED, ANCHORS, FILES

REPO = 'Kharn27/ESP32-Locomotive-Basic'
POLICY_MAIN = '6d3aae8a95b97e18174d758f35ef240740e9a861'
EXPECTED_B = '4d261f2a76374ab99a4dd7415cae7a097330c46b'
EXPECTED_H = '64b0087d5087903fee175c4f149c65a65bb43fe6'
LEGACY_PREVIEW = '28e0a1585b204c55e533c284328e9bc797b23492'
PR_NUMBER = 330
PAIRS = {'PR_INCREMENTAL': ('base', 'head'),
         'INTEGRATION_CANDIDATE': ('main', 'candidate')}
LABELS = ('base', 'head', 'main', 'candidate')
VARIANTS = ('spi40', 'spi20')
MAX_BUILDS = 8
SHA = re.compile(r'[0-9a-f]{40}\Z')


class Invalid(Exception):
    pass


def require(ok, reason):
    if not ok:
        raise Invalid('MEASUREMENT_INVALID: ' + reason)


def sh(cmd, cwd=None, env=None, output=None):
    res = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if output:
        Path(output).write_text(res.stdout + '\nSTDERR:\n' + res.stderr)
    require(res.returncode == 0, 'COMMAND_FAILURE:' + str(cmd[:4]) + ':' + str(res.returncode))
    return res.stdout.strip()


def git(root, *parts):
    return sh(['git', '-C', str(root), *parts])


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put_json(path, payload):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, sort_keys=True, indent=2) + '\n')


def get(api_path, token):
    require(token and not re.search(r'[\s\r\n]', token), 'GITHUB_TOKEN_MISSING')
    require(api_path.startswith('/') and '//' not in api_path and '?' not in api_path,
            'UNSAFE_API_PATH')
    url = 'https://api.github.com/repos/' + REPO + api_path
    req = urllib.request.Request(url, method='GET', headers={
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'c6-b2b-8build-readonly',
        'Authorization': 'Bearer ' + token,
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            require(response.status == 200, 'GITHUB_API_HTTP_STATUS')
            return json.load(response)
    except (urllib.error.URLError, ValueError, TimeoutError, OSError) as err:
        # Never serialize token, URL headers or remote error body.
        raise Invalid('MEASUREMENT_INVALID: GITHUB_API_UNAVAILABLE:' +
                      str(getattr(err, 'code', 'NETWORK'))) from None


def snapshot(token):
    branch = get('/branches/main', token)
    pr = get('/pulls/330', token)
    m = branch['commit']['sha']
    b = pr['base']['sha']
    h = pr['head']['sha']
    c_preview = pr.get('merge_commit_sha')
    for value in (m, b, h):
        require(SHA.fullmatch(value), 'INVALID_REF_SHA')
    require((m, b, h) == (POLICY_MAIN, EXPECTED_B, EXPECTED_H), 'GITHUB_REF_DRIFT')
    require(pr['number'] == PR_NUMBER and pr['state'] == 'open' and
            pr.get('merged_at') is None and pr['base']['ref'] == 'main' and
            pr['base']['repo']['full_name'] == REPO and
            pr['head']['repo']['full_name'] == REPO,
            'GITHUB_PR_IDENTITY_CHANGED')
    require(c_preview == LEGACY_PREVIEW, 'GITHUB_PREVIEW_CHANGED')
    return {'M': m, 'B': b, 'H': h, 'old_preview': c_preview,
            'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}


def pin_git(root, proof):
    require(git(root, 'rev-parse', 'HEAD') == os.environ['LAB_HEAD'],
            'LAB_HEAD_CHANGED')
    require(os.environ['LAB_BASE'] == POLICY_MAIN, 'LAB_BASE_MISMATCH')
    # Ref objects fetched from origin but never execute the foreign source as controller.
    for value in (proof['M'], proof['B'], proof['H']):
        git(root, 'cat-file', '-t', value)
        require(git(root, 'cat-file', '-t', value) == 'commit', 'NOT_GIT_COMMIT')
    mb = git(root, 'merge-base', proof['M'], proof['H'])
    mb_bh = git(root, 'merge-base', proof['B'], proof['H'])
    require(mb == proof['B'] and mb_bh == proof['B'], 'WRONG_MERGE_BASE')
    require(sh(['git', '-C', str(root), 'merge-base', '--is-ancestor',
                proof['B'], proof['M']]) == '', 'BASE_NOT_ANCESTOR')
    # git merge-tree uses the actual Git 3-way merge algorithm. Exit !=0
    # represents conflict: STOP; never resolve business conflicts automatically.
    merged = sh(['git', '-C', str(root), 'merge-tree', '--write-tree',
                 proof['M'], proof['H']])
    require(SHA.fullmatch(merged), 'MERGE_TREE_NOT_SINGLE_SHA')
    repeat = sh(['git', '-C', str(root), 'merge-tree', '--write-tree',
                 proof['M'], proof['H']])
    require(merged == repeat, 'MERGE_TREE_NONREPRODUCIBLE')
    env = dict(os.environ)
    env.update({'GIT_AUTHOR_NAME': 'C6-B2-B Test Merge',
                'GIT_AUTHOR_EMAIL': 'ci-test-merge@localhost',
                'GIT_COMMITTER_NAME': 'C6-B2-B Test Merge',
                'GIT_COMMITTER_EMAIL': 'ci-test-merge@localhost',
                'GIT_AUTHOR_DATE': '2000-01-01T00:00:00+0000',
                'GIT_COMMITTER_DATE': '2000-01-01T00:00:00+0000'})
    args = ['git', '-C', str(root), 'commit-tree', merged,
            '-p', proof['M'], '-p', proof['H']]
    c = sh(args, env=env)
    assert SHA.fullmatch(c)
    require(c not in (proof['M'], proof['H'], proof['old_preview']),
            'TEST_MERGE_REUSES_EXISTING_COMMIT')
    require(git(root, 'rev-parse', c+'^{tree}') == merged,
            'CANDIDATE_TREE_MISMATCH')
    require(git(root, 'rev-list', '--parents', '-n', '1', c).split() ==
            [c, proof['M'], proof['H']], 'CANDIDATE_PARENTS_MISMATCH')
    proof.update({'MB_MH': mb, 'MB_BH': mb_bh, 'C': c,
                  'C_tree': merged, 'candidate_kind': 'C_TEST_MERGE_REPRODUCIBLE',
                  'trees': {tag: git(root, 'rev-parse', commit + '^{tree}')
                            for tag, commit in (('base', proof['B']),
                                                ('head', proof['H']),
                                                ('main', proof['M']),
                                                ('candidate', c))}})
    return proof


def validate_cell(root, label, variant, sha, tree):
    folder = root / label / variant
    meta = json.loads((folder/'source.json').read_text())
    require(meta['source_sha'] == sha and meta['source_tree'] == tree and
            meta['source_label'] == label and meta['variant'] == variant,
            'CELL_PROVENANCE_MISMATCH')
    require(meta['map_sha256'] == digest(folder/'firmware.map'), 'MAP_DIGEST')
    require(meta.get('github_run_id') == os.environ.get('GITHUB_RUN_ID') and
            meta.get('github_run_attempt') == os.environ.get('GITHUB_RUN_ATTEMPT') and
            meta.get('lab_head') == os.environ.get('LAB_HEAD'),
            'FOREIGN_RUN_OR_HEAD_ARTIFACT')
    require(meta['source_sha'] != meta.get('app_source_sha7'), 'SHA7_ONLY')
    return build_metrics(root, label, variant, sha, tree)


def decide_pair(metrics, left, right):
    failed = []
    increments = {}
    for v in VARIANTS:
        a, b = metrics[left][v], metrics[right][v]
        for prop in ('sdkconfig', 'gcc', 'ld', 'idf', 'docker_image_id'):
            require(a[prop] == b[prop], 'PAIR_CONFIG_DRIFT:'+left+right+v+prop)
        delta = {k: b[k]-a[k] for k in ('iram', 'dram', 'bss', 'flash_text', 'flash_rodata')}
        increments[v] = delta
        if delta['iram'] > 0 or delta['dram'] > 0:
            failed.append(v+':IRAM_OR_DRAM_INCREASE')
        for label, cell in ((left,a),(right,b)):
            cost = cell['dram'] - EXPECTED['B3']['dram']
            if not 0 <= cost <= 696 or cell['dram'] > 54864:
                failed.append(v+':'+label+':C3_DRAM_CAP')
    for label in (left, right):
        a,b=metrics[label]['spi40'],metrics[label]['spi20']
        if (a['iram'],a['dram']) != (b['iram'],b['dram']):
            failed.append(label+':SPI_IRAM_DRAM_PARITY')
        if a['bin_sha256'] == b['bin_sha256']:
            failed.append(label+':IDENTICAL_SPI_BIN')
        if a['sdkconfig'] != b['sdkconfig']:
            failed.append(label+':SPI_SDKCONFIG_MISMATCH')
    return {'verdict':'FAIL' if failed else 'PASS',
            'delta':increments,'faults':failed}


def evaluate(root, proven, attempt_count):
    require(attempt_count == MAX_BUILDS, 'INCOMPLETE_EIGHT_BUILDS')
    identities = {'base': proven['B'], 'head': proven['H'],
                  'main': proven['M'], 'candidate': proven['C']}
    evidence={label: {v:validate_cell(root,label,v,sha,proven['trees'][label])
                     for v in VARIANTS} for label,sha in identities.items()}
    channels={key:decide_pair(evidence,*labels) for key,labels in PAIRS.items()}
    history={'RENDER_A_HISTORICAL':'FAILURE',
             'C3_HISTORICAL':'FAILURE',
             'A0_HISTORICAL':'HISTORICAL_DEBT',
             'ROOT_CAUSE':'ROOT_CAUSE_UNVERIFIED',
             'ON_DEVICE':'ON_DEVICE_UNVERIFIED',
             'ANCHORS':ANCHORS,'EXPECTED_BYTES':EXPECTED,
             'RE_EVALUATED':False}
    return {'contract':'HW4-MEM-C6-B2-B/eight-xtensa-v1',
            'status':'MEASURED', 'provenance':proven,
            'PR_INCREMENTAL_VERDICT':channels['PR_INCREMENTAL']['verdict'],
            'INTEGRATION_MEMORY_VERDICT':channels['INTEGRATION_CANDIDATE']['verdict'],
            'INTEGRATION_READINESS':'BLOCKED_HISTORICAL_DEBT',
            'channels':channels,'metrics':evidence,'historical':history,
            'xtensa_build_count':attempt_count,
            'merge_preview_is_not_candidate':True}


def build_one(workspace, report, proof, label, variant, image_id, count):
    require(count <= MAX_BUILDS, 'BUILD_BUDGET_EXCEEDED')
    sha={'base':proof['B'],'head':proof['H'],
         'main':proof['M'],'candidate':proof['C']}[label]
    tree=proof['trees'][label]
    work=workspace/'.c6-b2b-worktrees'/label
    folder=report/label/variant
    folder.mkdir(parents=True,exist_ok=False)
    hz=CLOCKS[variant]
    firmware=work/'firmware/esp32_display_probe'
    build='build-c6b2b-'+label+'-'+variant
    config='sdkconfig.c6b2b-'+label+'-'+variant
    require(not (firmware/build).exists() and not (firmware/config).exists(),
            'BUILD_CACHE_NOT_CLEAN')
    # Build only untrusted firmware source inside docker, no GITHUB_TOKEN env,
    # no extraheader, no secrets, no mount of ~/.git-credentials.
    bash=r'''set -euo pipefail
idf.py --version > "$OUT/idf-version.txt"
grep -Fx 'ESP-IDF v5.5.6' "$OUT/idf-version.txt"
xtensa-esp-elf-gcc --version > "$OUT/gcc-version.txt"
xtensa-esp-elf-ld --version > "$OUT/ld-version.txt"
idf.py -B "$BUILD" -DSDKCONFIG="$PWD/$CFG" -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ="$HZ" set-target esp32 > "$OUT/set-target.log" 2>&1 || { tail -80 "$OUT/set-target.log"; exit 4; }
idf.py -B "$BUILD" -DSDKCONFIG="$PWD/$CFG" -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ="$HZ" build > "$OUT/build.log" 2>&1 || { tail -80 "$OUT/build.log"; exit 5; }
cp "$BUILD/CMakeCache.txt" "$OUT/CMakeCache.txt"
cp "$BUILD/compile_commands.json" "$OUT/compile_commands.json"
cp "$PWD/$CFG" "$OUT/sdkconfig"
cp "$BUILD/loco_esp32_display_probe.elf" "$OUT/firmware.elf"
cp "$BUILD/loco_esp32_display_probe.bin" "$OUT/firmware.bin"
cp "$BUILD/loco_esp32_display_probe.map" "$OUT/firmware.map"
xtensa-esp-elf-size -A "$OUT/firmware.elf" > "$OUT/sections.txt"
xtensa-esp-elf-readelf -h "$OUT/firmware.elf" > "$OUT/readelf-header.txt"
grep -E 'Machine:.*Xtensa' "$OUT/readelf-header.txt"
'''
    envs={'OUT':str(folder),'BUILD':build,'CFG':config,'HZ':str(hz)}
    args=['docker','run','--rm','-v',str(workspace)+':'+str(workspace),
          '-w',str(firmware)]
    for k,v in envs.items(): args+=['-e',k+'='+v]
    args +=[IMAGE,'bash','-lc',bash]
    sh(args,output=folder/'docker-output.log')
    from verify_esp_app_version import boot_version
    ver=boot_version((folder/'firmware.bin').read_bytes(), 'loco_esp32_display_probe')
    require(ver.startswith(sha[:7]),'EMBEDDED_APP_VERSION_MISMATCH')
    digests={name:digest(folder/name) for name in FILES}
    meta={'source_sha':sha,'source_tree':tree,'app_source_sha':sha,
          'app_source_sha7':ver[:7], 'source_label':label,'variant':variant,
          'clock_hz':hz,'profile':'CONSOLE','container_image':IMAGE,
          'docker_image_id':image_id,'digests':digests,
          'sdkconfig_sha256':digests['sdkconfig'],
          'map_sha256':digest(folder/'firmware.map'),
          'github_run_id':os.environ.get('GITHUB_RUN_ID'),
          'github_run_attempt':os.environ.get('GITHUB_RUN_ATTEMPT'),
          'lab_head':os.environ.get('LAB_HEAD'),
          'build_no':count}
    put_json(folder/'source.json',meta)
    m=validate_cell(report,label,variant,sha,tree)
    return {k:m[k] for k in ('iram','dram','bss','flash_text','flash_rodata',
                             'elf_sha256','bin_sha256')}


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    root=args.workspace.resolve(); report=args.output.resolve()
    token=os.environ.get('GH_TOKEN')
    proof={'status':'MEASUREMENT_INVALID','reason':'NOT_STARTED'}
    attempts=0
    report.mkdir(parents=True,exist_ok=True)
    try:
        require(os.environ.get('GITHUB_REPOSITORY')==REPO,'WRONG_REPOSITORY')
        require(os.environ.get('LAB_HEAD') and SHA.fullmatch(os.environ['LAB_HEAD']),
                'LAB_HEAD_ABSENT')
        first=snapshot(token)
        require(os.environ.get('LAB_BASE') == first['M'],'LAB_BASE_DIFFERS_FROM_MAIN')
        # Fetch the exact native GitHub PR ref without running its code or
        # keeping any GitHub credentials in Git configuration.
        sh(['git','-C',str(root),'fetch','--no-tags','origin',
            '+refs/pull/330/head:refs/remotes/origin/c6b2b-330-head'],
            output=report/'fetch-pr330.log')
        require(git(root,'rev-parse','refs/remotes/origin/c6b2b-330-head')
                ==first['H'], 'FETCHED_PR_HEAD_DRIFT')
        proof=pin_git(root,first)
        put_json(report/'git-provenance.json',proof)
        for label,commit in [('base',proof['B']),('head',proof['H']),
                             ('main',proof['M']),('candidate',proof['C'])]:
            work=root/'.c6-b2b-worktrees'/label
            require(not work.exists(),'SOURCE_WORKTREE_EXISTS')
            sh(['git','-C',str(root),'worktree','add','--detach',str(work),commit],
               output=report/('worktree-'+label+'.log'))
            require(git(work,'rev-parse','HEAD')==commit and
                    git(work,'rev-parse','HEAD^{tree}')==proof['trees'][label],
                    'WORKTREE_REF_DRIFT')
        require(snapshot(token)['M'] == proof['M'],'MAIN_DRIFT_PRE_IMAGE')
        sh(['docker','pull',IMAGE],output=report/'docker-pull.log')
        digests=json.loads(sh(['docker','image','inspect',IMAGE,'--format','{{json .RepoDigests}}']))
        require(any(x.endswith(IMAGE.split('@')[-1]) for x in digests),
                'IMAGE_DIGEST_NOT_PINNED')
        image_id=sh(['docker','image','inspect',IMAGE,'--format','{{.Id}}'])
        require(re.fullmatch('sha256:[0-9a-f]{64}',image_id),'IMAGE_ID_INVALID')
        put_json(report/'image.json',{'name':IMAGE,'id':image_id,'repo_digests':digests})
        for label in LABELS:
            for variant in VARIANTS:
                # Both BEFORE and AFTER each costly cell; stale GitHub refs STOP.
                now=snapshot(token)
                require(all(now[k]==proof[k] for k in ('M','B','H')) and
                        now['old_preview']==proof['old_preview'],
                        'REF_DRIFT_BEFORE_CELL')
                attempts+=1
                put_json(report/'attempts.json',{'attempted':attempts,
                                                 'max':MAX_BUILDS,'active':label+'/'+variant})
                metrics=build_one(root,report,proof,label,variant,image_id,attempts)
                put_json(report/'attempts.json',{'attempted':attempts,
                                                 'max':MAX_BUILDS,'finished':label+'/'+variant})
                after=snapshot(token)
                require(all(after[k]==proof[k] for k in ('M','B','H')) and
                        after['old_preview']==proof['old_preview'],
                        'REF_DRIFT_AFTER_CELL')
                print('C6_B2B_REAL_XTENSA_BUILD',attempts,label,variant,metrics,flush=True)
        result=evaluate(report,proof,attempts)
        final=snapshot(token)
        require(all(final[k]==proof[k] for k in ('M','B','H')) and
                final['old_preview']==proof['old_preview'],
                'REF_DRIFT_FINAL')
        require(git(root,'rev-parse','HEAD')==os.environ['LAB_HEAD'],
                'RUN_HEAD_DRIFT_FINAL')
        result['final_snapshot']=final
        put_json(report/'verdict.json',result)
        print('C6_B2B_PAIR_VERDICTS',result['PR_INCREMENTAL_VERDICT'],
              result['INTEGRATION_MEMORY_VERDICT'],
              'INTEGRATION_READINESS',result['INTEGRATION_READINESS'],flush=True)
        return 1 if 'FAIL' in (result['PR_INCREMENTAL_VERDICT'],
                               result['INTEGRATION_MEMORY_VERDICT']) else 0
    except (Invalid,KeyError,TypeError,ValueError,OSError,
            subprocess.CalledProcessError,json.JSONDecodeError) as e:
        reason=str(e)
        put_json(report/'invalid.json',{'status':'MEASUREMENT_INVALID',
            'reason':reason,'completed_or_attempted_cells':attempts,
            'PR_INCREMENTAL_VERDICT':'MEASUREMENT_INVALID',
            'INTEGRATION_MEMORY_VERDICT':'MEASUREMENT_INVALID',
            'INTEGRATION_READINESS':'BLOCKED_MEASUREMENT_INVALID'})
        print('C6_B2B_MEASUREMENT_INVALID',reason,'attempts',attempts,flush=True)
        return 2


if __name__ == '__main__':
    sys.exit(main())