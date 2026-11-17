"""HW4-MEM-C7 v2: synthetic adversarial fixtures, NOT firmware measurements."""
import copy
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "ci"))
import hw4_mem_c7_v2 as c
import hw4_mem_c7_provenance as p
import hw4_mem_c7_legacy as legacy

BASE = "e586f0161c73e309291060111335f0b30fc48e84"
HEAD = "1" * 40
BASE_TREE = "2" * 40
HEAD_TREE = "3" * 40
MERGE = BASE
REPO = "Kharn27/ESP32-Locomotive-Basic"
PR = 339


def sect(iram=67551, dram=54864, bss=43792, missing=None, marker=1):
    d = {".dram0.data": dram - bss, ".dram0.bss": bss,
         ".iram0.vectors": 1028, ".iram0.text": iram - 1028,
         ".iram0.text_end": marker, ".flash.text": 170030,
         ".flash.rodata": 57572}
    if missing:
        del d[missing]
    return ("test.elf :\nsection size addr\n" +
            "".join(f"{k} {v} 1073414144\n" for k, v in d.items()) +
            f"Total {sum(d.values())}\n")


def bin_image(sha, tail):
    desc = struct.pack("<I", 0xABCD5432) + b"\0" * 12
    desc += sha[:7].encode().ljust(32, b"\0")
    desc += b"loco_esp32_display_probe".ljust(32, b"\0")
    return b"testimage" + desc + tail.encode()


def elf_image():
    x = bytearray(64)
    x[:6] = b"\x7fELF\x01\x01"
    struct.pack_into("<H", x, 18, 94)
    return bytes(x)


def live():
    return {"number": PR, "state": "open",
            "base": {"ref": "main", "repo": {"full_name": REPO}, "sha": BASE},
            "head": {"sha": HEAD}}


def provenance():
    return {"status": "PROVENANCE_PASS", "repo": REPO, "pr_number": PR,
            "base_sha": BASE, "head_sha": HEAD,
            "base_tree": BASE_TREE, "head_tree": HEAD_TREE, "merge_base": MERGE,
            "ancestry_verified": True, "diverged_from_base": False,
            "policy_main": BASE,
            "anchors": copy.deepcopy(c.ANCHORS),
            "historical_bytes": copy.deepcopy(c.EXPECTED)}


class Comparator(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for label, sha, tree in (("base", BASE, BASE_TREE), ("head", HEAD, HEAD_TREE)):
            for variant, hz in c.CLOCKS.items():
                self.write(label, variant, sha, tree, hz)

    def write(self, label, variant, sha, tree, hz, **kw):
        d = self.root / label / variant
        d.mkdir(parents=True, exist_ok=True)
        files = {"sections.txt": sect(iram=kw.get("iram", 67551),
                                     dram=kw.get("dram", 54864),
                                     bss=kw.get("bss", 43792),
                                     missing=kw.get("missing"), marker=kw.get("marker", 1)),
                 "firmware.elf": elf_image(),
                 "firmware.bin": bin_image(sha, label + variant),
                 "CMakeCache.txt": ("LOCO_CYD_PROFILE:STRING=CONSOLE\n"
                                     f"CYD_LCD_SPI_HZ:STRING={hz}\n"
                                     f"CYD_LCD_SPI20_OPT_IN:BOOL={'OFF' if variant == 'spi40' else 'ON'}\n"),
                 "compile_commands.json": json.dumps([{
                     "file": "/a/cyd_ili9341.c",
                     "arguments": ["gcc", f"-DLCD_CLOCK_HZ={hz}U", "-c"]}]),
                 "sdkconfig": "CONFIG_C7_TEST=1\n",
                 "idf-version.txt": "ESP-IDF v5.5.6\n",
                 "gcc-version.txt": "xtensa-esp-elf-gcc 14.2.0\n",
                 "ld-version.txt": "GNU ld 2.43.1\n"}
        for name, data in files.items():
            (d / name).write_bytes(data if isinstance(data, bytes) else data.encode())
        self.refresh_meta(label, variant, sha=sha, tree=tree, hz=hz)

    def refresh_meta(self, label, variant, sha=None, tree=None, hz=None):
        d = self.root / label / variant
        old = json.loads((d / "source.json").read_text()) if (d / "source.json").exists() else {}
        source = sha or old["source_sha"]
        meta = {"source_sha": source, "source_tree": tree or old["source_tree"],
                "app_source_sha": source, "source_label": label,
                "variant": variant, "clock_hz": hz or c.CLOCKS[variant],
                "profile": "CONSOLE", "container_image": c.IMAGE,
                "docker_image_id": "sha256:" + "f" * 64,
                "digests": {f: hashlib.sha256((d / f).read_bytes()).hexdigest()
                            for f in c.FILES},
                "sdkconfig_sha256": hashlib.sha256((d / "sdkconfig").read_bytes()).hexdigest()}
        (d / "source.json").write_text(json.dumps(meta))
        return meta

    def mutate(self, label="head", variant="spi40", fname="source.json",
               replacement=None, change=None, update_digest=True):
        path = self.root / label / variant / fname
        if fname == "source.json":
            data = json.loads(path.read_text())
            data.update(change)
            path.write_text(json.dumps(data))
        else:
            if replacement is not None:
                path.write_bytes(replacement if isinstance(replacement, bytes)
                                 else replacement.encode())
            if update_digest:
                self.refresh_meta(label, variant)
        return path

    def metrics(self):
        return {l: {v: c.build_metrics(self.root, l, v, s, t)
                    for v in c.CLOCKS}
                for l, s, t in (("base", BASE, BASE_TREE), ("head", HEAD, HEAD_TREE))}

    def test_c7_real_comparator_cli_return_codes_synthetic(self):
        """Actually invoke C7 main(), proving rc=0, rc=1 and rc=2 paths.

        These are synthetic fixtures, not Xtensa ELF measurements. The CI
        workflows separately run five real Xtensa builds per consumer.
        """
        pv = self.root / "provenance.json"
        lv = self.root / "pr.json"
        pv.write_text(json.dumps(provenance()))
        lv.write_text(json.dumps(live()))
        dest = self.root / "verdict"

        def invoke():
            sequence = [BASE, "commit", BASE_TREE, HEAD, "commit", HEAD_TREE, MERGE]
            with mock.patch.object(c, "git", side_effect=sequence), \
                 mock.patch.object(c.subprocess, "run",
                                   return_value=mock.Mock(returncode=0)):
                return c.main(["--root", str(self.root), "--provenance", str(pv),
                               "--live-pr-start", str(lv), "--live-pr", str(lv),
                               "--repo", REPO, "--pr-number", str(PR),
                               "--output", str(dest),
                               "--base-checkout", "base", "--head-checkout", "head"])

        self.assertEqual(invoke(), 0)
        self.assertEqual(json.loads((dest / "verdict.json").read_text())["status"],
                         "INCREMENTAL_PASS")
        for variant in c.CLOCKS:
            for key in ("iram", "dram", "bss"):
                with self.subTest(variant=variant, metric=key):
                    changes = {key: {"iram": 67551, "dram": 54864, "bss": 43792}[key] + 1}
                    self.write("head", variant, HEAD, HEAD_TREE, c.CLOCKS[variant],
                               **changes)
                    self.assertEqual(invoke(), 1, (variant, key))
                    self.assertEqual(json.loads((dest / "verdict.json").read_text())["status"],
                                     "INCREMENTAL_FAIL")
                    self.write("head", variant, HEAD, HEAD_TREE, c.CLOCKS[variant])
        # Invalid compiled SPI20 opt-in cache is NOT an incremental test success.
        path = self.root / "head/spi20/CMakeCache.txt"
        old_cache = path.read_text()
        self.mutate(variant="spi20", fname="CMakeCache.txt",
                    replacement=old_cache.replace("CYD_LCD_SPI20_OPT_IN:BOOL=ON",
                                                  "CYD_LCD_SPI20_OPT_IN:BOOL=OFF"))
        self.assertEqual(invoke(), 2)
        self.mutate(variant="spi20", fname="CMakeCache.txt", replacement=old_cache)
        # Tampered real artifacts are invalid, even with all metrics equal.
        self.mutate(fname="sections.txt", replacement=sect(iram=67552),
                    update_digest=False)
        self.assertEqual(invoke(), 2)

    def test_positive_debt_not_erased(self):
        r = c.evaluate(self.metrics(), provenance())
        self.assertEqual(r["historical_debt"], "HISTORICAL_DEBT")
        self.assertEqual(r["render_a"]["historical"]["head"]["status"], "HISTORICAL_FAILURE")
        self.assertEqual(r["spi_c3"]["historical"]["head"]["spi40"]["status"],
                         "HISTORICAL_FAILURE")
        self.assertEqual(r["render_a"]["incremental"]["status"], "INCREMENTAL_PASS")
        self.assertEqual(r["spi_c3"]["variants"]["status"], "SPI_VARIANTS_PARITY_PASS")
        self.assertEqual(r["status"], "INCREMENTAL_PASS")
        self.assertIn("HISTORICAL_FAILURE", c.markdown(r))

    def test_one_byte_iram_increment_is_failure(self):
        for v in c.CLOCKS:
            self.write("head", v, HEAD, HEAD_TREE, c.CLOCKS[v], iram=67552)
        r = c.evaluate(self.metrics(), provenance())
        self.assertEqual(r["render_a"]["incremental"]["status"], "INCREMENTAL_FAIL")
        self.assertEqual(r["spi_c3"]["incremental"]["spi20"]["iram"], 1)

    def test_one_byte_dram_including_bss_increment_is_failure(self):
        for v in c.CLOCKS:
            self.write("head", v, HEAD, HEAD_TREE, c.CLOCKS[v],
                       dram=54865, bss=43793)
        r = c.evaluate(self.metrics(), provenance())
        self.assertEqual(r["render_a"]["incremental"]["status"], "INCREMENTAL_FAIL")
        self.assertEqual(r["spi_c3"]["incremental"]["spi40"]["dram"], 1)

    def test_spi40_spi20_iram_parity_failure(self):
        self.write("head", "spi20", HEAD, HEAD_TREE, 20000000, iram=67552)
        r = c.evaluate(self.metrics(), provenance())
        self.assertEqual(r["spi_c3"]["variants"]["status"], "SPI_VARIANTS_PARITY_FAIL")
        self.assertEqual(r["status"], "INCREMENTAL_FAIL")

    def test_spi40_spi20_dram_parity_failure(self):
        self.write("head", "spi20", HEAD, HEAD_TREE, 20000000, dram=54863)
        r = c.evaluate(self.metrics(), provenance())
        self.assertEqual(r["spi_c3"]["variants"]["status"], "SPI_VARIANTS_PARITY_FAIL")

    def test_identical_bins_rejected(self):
        b = (self.root / "head/spi40/firmware.bin").read_bytes()
        self.mutate(variant="spi20", fname="firmware.bin", replacement=b)
        r = c.evaluate(self.metrics(), provenance())
        self.assertEqual(r["spi_c3"]["variants"]["status"], "SPI_VARIANTS_PARITY_FAIL")

    def test_b3_relative_dram_cap_is_historical_not_future_perpetual_ceiling(self):
        for v in c.CLOCKS:
            self.write("base", v, BASE, BASE_TREE, c.CLOCKS[v],
                       dram=54865)
        r = c.evaluate(self.metrics(), provenance())
        self.assertEqual(r["spi_c3"]["historical"]["base"]["spi40"]["status"],
                         "HISTORICAL_FAILURE")
        # No new growth: base 54865 -> head 54864 is allowed. The old
        # permanent 54864 cap may not block a newer already-accepted main.
        self.assertEqual(r["spi_c3"]["variants"]["status"],
                         "SPI_VARIANTS_PARITY_PASS")
        self.assertEqual(r["status"], "INCREMENTAL_PASS")

    def test_profiles_clocks_hal_flags_rejected(self):
        for field, val in (("profile", "HW3"), ("clock_hz", 1), ("variant", "spi20")):
            with self.subTest(field=field):
                self.mutate(change={field: val})
                with self.assertRaises(ValueError):
                    c.build_metrics(self.root, "head", "spi40", HEAD, HEAD_TREE)
                self.refresh_meta("head", "spi40", sha=HEAD, tree=HEAD_TREE, hz=40000000)
        path = self.root / "head/spi40/compile_commands.json"
        self.mutate(fname="compile_commands.json",
                    replacement='[{"file":"/a/cyd_ili9341.c","arguments":["gcc"]}]')
        with self.assertRaisesRegex(ValueError, "HAL"):
            c.build_metrics(self.root, "head", "spi40", HEAD, HEAD_TREE)

    def test_wrong_cache_profile_and_clock(self):
        for content in ("LOCO_CYD_PROFILE:STRING=HW3\nCYD_LCD_SPI_HZ:STRING=40000000",
                        "LOCO_CYD_PROFILE:STRING=CONSOLE\nCYD_LCD_SPI_HZ:STRING=20000000"):
            with self.subTest(content=content):
                self.mutate(fname="CMakeCache.txt", replacement=content)
                with self.assertRaises(ValueError):
                    c.build_metrics(self.root, "head", "spi40", HEAD, HEAD_TREE)

    def test_bad_docker_id_sdkconfig_idf_gcc_ld(self):
        for field, val in (("container_image", "espressif/idf:latest"),
                           ("docker_image_id", "sha256:bad"),
                           ("sdkconfig_sha256", "bad")):
            with self.subTest(field=field):
                self.mutate(change={field: val})
                with self.assertRaises(ValueError):
                    c.build_metrics(self.root, "head", "spi40", HEAD, HEAD_TREE)
                self.refresh_meta("head", "spi40", sha=HEAD, tree=HEAD_TREE, hz=40000000)
        for name, content in (("idf-version.txt", "ESP-IDF v5.5.5"),
                              ("gcc-version.txt", "gcc 12.0"),
                              ("ld-version.txt", "ld 2.40")):
            with self.subTest(name=name):
                path = self.root / "head/spi40" / name
                before = path.read_bytes()
                self.mutate(fname=name, replacement=content)
                with self.assertRaises(ValueError):
                    c.build_metrics(self.root, "head", "spi40", HEAD, HEAD_TREE)
                self.mutate(fname=name, replacement=before)

    def test_missing_files_section_and_elf_bin_rejected(self):
        for name in c.FILES:
            with self.subTest(name=name):
                pth = self.root / "head/spi40" / name
                data = pth.read_bytes()
                pth.unlink()
                with self.assertRaises((OSError, ValueError)):
                    c.build_metrics(self.root, "head", "spi40", HEAD, HEAD_TREE)
                pth.write_bytes(data)
        for key in (".dram0.data", ".dram0.bss", ".iram0.vectors",
                    ".iram0.text", ".iram0.text_end", ".flash.text", ".flash.rodata"):
            with self.subTest(key=key):
                self.mutate(fname="sections.txt", replacement=sect(missing=key))
                with self.assertRaises(ValueError):
                    c.build_metrics(self.root, "head", "spi40", HEAD, HEAD_TREE)
        self.mutate(fname="sections.txt", replacement=sect(marker=2))
        with self.assertRaises(ValueError):
            c.build_metrics(self.root, "head", "spi40", HEAD, HEAD_TREE)

    def test_bad_binary_app_sha_and_elf_arch_rejected(self):
        self.mutate(fname="firmware.bin", replacement=bin_image(BASE, "wrong"))
        with self.assertRaises(ValueError):
            c.build_metrics(self.root, "head", "spi40", HEAD, HEAD_TREE)
        self.mutate(fname="firmware.bin", replacement=bin_image(HEAD, "right"))
        self.mutate(fname="firmware.elf", replacement=b"not-an-elf")
        with self.assertRaises(ValueError):
            c.build_metrics(self.root, "head", "spi40", HEAD, HEAD_TREE)

    def test_artifact_wrong_source_sha_tree_and_digest(self):
        for field, val in (("source_sha", "4" * 40), ("source_tree", "5" * 40),
                           ("app_source_sha", "0" * 40), ("source_label", "base")):
            with self.subTest(field=field):
                self.mutate(change={field: val})
                with self.assertRaises(ValueError):
                    c.build_metrics(self.root, "head", "spi40", HEAD, HEAD_TREE)
                self.refresh_meta("head", "spi40", sha=HEAD, tree=HEAD_TREE, hz=40000000)
        self.mutate(fname="sections.txt", replacement=sect(iram=67552),
                    update_digest=False)
        with self.assertRaises(ValueError):
            c.build_metrics(self.root, "head", "spi40", HEAD, HEAD_TREE)

    def test_base_head_settings_mismatch_invalid(self):
        self.mutate(fname="sdkconfig", replacement="CONFIG_CHANGED=y\n")
        with self.assertRaisesRegex(ValueError, "settings"):
            c.evaluate(self.metrics(), provenance())

    def test_immutable_anchors_substitution(self):
        for field in ("A0", "RENDER_A", "B3"):
            with self.subTest(anchor=field):
                pv = provenance()
                pv["anchors"][field] = "f" * 40
                with self.assertRaisesRegex(ValueError, "anchors"):
                    c.verify_provenance(pv, live(), REPO, PR, "base", "head")
                pv = provenance()
                pv["historical_bytes"][field]["iram"] += 1
                with self.assertRaisesRegex(ValueError, "measurements"):
                    c.verify_provenance(pv, live(), REPO, PR, "base", "head")

    def test_pr_identity_and_stale_base_head(self):
        for entry, val in (("base", "4" * 40), ("head", "5" * 40)):
            with self.subTest(entry=entry):
                lv = live()
                lv[entry]["sha"] = val
                with self.assertRaises(ValueError):
                    c.verify_provenance(provenance(), lv, REPO, PR, "base", "head")
        for field, val in (("base_sha", "0" * 40), ("head_sha", BASE),
                           ("policy_main", "4" * 40), ("ancestry_verified", False)):
            with self.subTest(field=field):
                pv = provenance()
                pv[field] = val
                with self.assertRaises(ValueError):
                    c.verify_provenance(pv, live(), REPO, PR, "base", "head")

    def test_comparator_rechecks_git_sha_tree_and_merge_base(self):
        expected_sequence = [BASE, "commit", BASE_TREE, HEAD, "commit",
                             HEAD_TREE, MERGE]
        def verify(s):
            with mock.patch.object(c, "git", side_effect=s), \
                 mock.patch.object(c.subprocess, "run",
                                   return_value=mock.Mock(returncode=0)):
                return c.verify_provenance(provenance(), live(), REPO, PR, "base", "head")
        self.assertEqual(verify(expected_sequence), (BASE, HEAD))
        for index, val in ((0, "9" * 40), (2, "8" * 40), (6, "7" * 40)):
            with self.subTest(index=index):
                seq = expected_sequence.copy()
                seq[index] = val
                with self.assertRaises(ValueError):
                    verify(seq)

    def test_provenance_producer_live_pr_and_ancestry_fail_closed(self):
        for field in ("state", "number", "base", "head"):
            lv = live()
            if field == "state": lv["state"] = "closed"
            elif field == "number": lv["number"] = 330
            else: lv[field]["sha"] = "f" * 40
            # Head substitution reaches the real-checkout guard; a missing
            # Git object/checkout is also a fail-closed negative.
            with self.subTest(field=field), self.assertRaises(
                    (ValueError, subprocess.CalledProcessError)):
                p.checked_git(lv, REPO, PR, "base", "head", BASE)
        with mock.patch.object(p, "git", side_effect=[BASE, "commit", HEAD,
                                                     "commit", "commit", MERGE,
                                                     BASE_TREE, HEAD_TREE]), \
             mock.patch.object(p.subprocess, "run",
                               return_value=mock.Mock(returncode=0)):
            proof = p.checked_git(live(), REPO, PR, "base", "head", BASE)
            self.assertEqual(proof["merge_base"], MERGE)

    def test_missing_inputs_report_invalid_not_pass(self):
        output = self.root / "out"
        rc = c.main(["--root", str(self.root), "--provenance", str(self.root / "missing"),
                     "--live-pr", str(self.root / "not-live"),
                     "--live-pr-start", str(self.root / "not-live-start"), "--repo", REPO,
                     "--pr-number", str(PR), "--output", str(output),
                     "--base-checkout", "base", "--head-checkout", "head"])
        self.assertEqual(rc, 2)
        report = json.loads((output / "verdict.json").read_text())
        self.assertEqual(report["status"], "MEASUREMENT_INVALID")
        self.assertEqual(report["spi_variants_parity"], "SPI_VARIANTS_PARITY_UNVERIFIED")


# Independent C7 single-byte adversarial regression checks (synthetic fixtures).
class SingleByte(unittest.TestCase):
    def test_independent_plus_one_iram_dram_bss(self):
        for variant in c.CLOCKS:
            base={"iram":67551,"dram":54864,"bss":43792}
            for key in base:
                with self.subTest(variant=variant,key=key):
                    head=dict(base); head[key]+=1
                    self.assertEqual(c.judge(base,head)["status"],"INCREMENTAL_FAIL")



# #388: authenticate allocation only by real PR #387 + pinned B1 Git patch.
# Synthetic mock Git responses prove both positive and fail-closed branches;
# no fixture alone creates a deployment authorization.
class EscB1Allocation(Comparator):
    def approved(self, changes=None, git_overrides=None, anc_ok=True):
        """Simulate Git object/tree commands; override individual hostile answers."""
        pv = provenance()
        pv["pr_number"] = c.ESC_B1_PR
        pv["repo"] = c.ESC_B1_REPO
        lv = live()
        lv.update({"number": c.ESC_B1_PR,
                   "title": "[DRAFT] HW4-ESC-BREAK-B1 (#385)"})
        lv["head"]["repo"] = {"full_name": c.ESC_B1_REPO}
        lv["head"]["ref"] = c.ESC_B1_BRANCH
        if changes:
            for location, name, value in changes:
                (pv if location == "provenance" else
                 lv["head"] if location == "head" else lv)[name] = value

        original_paths = "\n".join(sorted(c.ESC_B1_PATHS))
        closed_paths = "\n".join(sorted(
            c.ESC_B1_PATHS | frozenset(c.ESC_B1_HOST_BLOBS) |
            c.ESC_B1_CI_PATHS))
        opts = ("diff", "--binary", "--no-ext-diff", "--no-renames")
        patch_paths = ("--", *sorted(c.ESC_B1_PATHS))

        def fake_git(folder, *args):
            if git_overrides and args in git_overrides:
                return git_overrides[args]
            if args[:2] == ("cat-file", "-t"):
                return "commit"
            if args[:3] == ("diff", "--name-only", "--no-renames"):
                return (original_paths if args[3] == c.ESC_B1_SOURCE_BASE
                        else closed_paths)
            if args[:4] == opts and args[-len(patch_paths):] == patch_paths:
                return "approved B1 patch"
            if len(args) == 4 and args[0] == "ls-tree" and args[2] == "--":
                rev, path = args[1], args[3]
                if path in c.ESC_B1_PATHS:
                    if rev in (c.ESC_B1_SOURCE_HEAD, HEAD):
                        return "100644 blob " + "a" * 40 + "\t" + path
                elif path in c.ESC_B1_HOST_BLOBS:
                    if rev == BASE:
                        return ""
                    if rev in (c.ESC_B1_PO_HEAD, HEAD):
                        return ("100644 blob " + c.ESC_B1_HOST_BLOBS[path] +
                                "\t" + path)
                elif path in c.ESC_B1_CI_PATHS:
                    if rev in (BASE, HEAD):
                        return ("100644 blob " +
                                ("b" if rev == BASE else "c") * 40 +
                                "\t" + path)
            raise AssertionError("unexpected Git lookup: " + repr(args))

        with mock.patch.object(c, "git", side_effect=fake_git), \
             mock.patch.object(c.subprocess, "run",
                               return_value=mock.Mock(
                                   returncode=0 if anc_ok else 1)):
            return c.authorize_esc_b1(pv, lv, c.ESC_B1_REPO,
                                      c.ESC_B1_PR, "/verified-head")

    def b1_metrics(self, growth=40, bss_growth=40, iram_growth=0,
                   only_variant=None):
        for variant in c.CLOCKS:
            if only_variant is not None and variant != only_variant:
                continue
            self.write("head", variant, HEAD, HEAD_TREE, c.CLOCKS[variant],
                       iram=67551 + iram_growth,
                       dram=54864 + growth, bss=43792 + bss_growth)
        return self.metrics()

    def test_approved_closed_ledger_and_provenance(self):
        self.assertEqual(c.ESC_B1_PR, 387)
        self.assertEqual(c.ESC_B1_ISSUE, 385)
        self.assertEqual(c.ESC_B1_LIMIT, {"iram": 0, "dram": 40, "bss": 40})
        self.assertEqual(c.ESC_B1_SOURCE_HEAD,
                         "010e2d1d14941e4e09c097c8599b5cf4d0527f2f")
        self.assertEqual(len(c.ESC_B1_PATHS), 10)
        self.assertEqual(c.ESC_B1_CI_PATHS,
                         frozenset({"tools/ci/hw4_mem_c7_v2.py",
                                    "tests/test_hw4_mem_c7.py"}))
        token = self.approved()
        self.assertEqual(token["po_source_head"], c.ESC_B1_PO_HEAD)
        self.assertEqual(token["host_blobs"], c.ESC_B1_HOST_BLOBS)
        self.assertEqual(token["ci_paths"], sorted(c.ESC_B1_CI_PATHS))
        self.assertEqual(token["status"], "AUTHORIZED_ESC_B1_DRAM_BSS_40")
        self.assertEqual(len(token["patch_sha256"]), 64)
        report = c.evaluate(self.b1_metrics(), provenance(), token)
        self.assertEqual(report["status"], "INCREMENTAL_PASS")
        self.assertEqual(report["spi_c3"]["variants"]["status"],
                         "SPI_VARIANTS_PARITY_PASS")
        self.assertEqual(report["render_a"]["historical"]["head"]["status"],
                         "HISTORICAL_FAILURE")
        self.assertEqual(report["spi_c3"]["historical"]["head"]["spi40"]["status"],
                         "HISTORICAL_FAILURE")
        self.assertIn("AUTHORIZED_ESC_B1_DRAM_BSS_40", c.markdown(report))
        self.assertEqual(report["measured"]["head"]["spi40"]["dram_data"], 11072)

    def test_plus_41_bss_dram_and_plus_one_iram_still_fail(self):
        token = self.approved()
        for variant in c.CLOCKS:
            for dram, bss, iram in ((41, 41, 0), (40, 41, 0),
                                    (41, 40, 0), (40, 40, 1)):
                with self.subTest(variant=variant, dram=dram, bss=bss, iram=iram):
                    self.setUp()
                    report = c.evaluate(self.b1_metrics(dram, bss, iram),
                                        provenance(), token)
                    self.assertEqual(report["status"], "INCREMENTAL_FAIL")
                    self.assertEqual(report["allocation"]["limit"],
                                     {"iram": 0, "dram": 40, "bss": 40})

    def test_one_variant_only_or_dram_data_changed_rejected(self):
        token = self.approved()
        self.assertEqual(c.evaluate(self.b1_metrics(only_variant="spi40"),
                                    provenance(), token)["status"], "INCREMENTAL_FAIL")
        self.setUp()
        changed_data = c.evaluate(self.b1_metrics(40, 39), provenance(), token)
        self.assertEqual(changed_data["status"], "INCREMENTAL_FAIL")
        self.assertIn("ESC allocation changed .dram0.data",
                      " ".join(changed_data["spi_c3"]["variants"]["faults"]))

    def test_no_budget_for_other_pr_or_reused_head_sha(self):
        measurements = self.b1_metrics()
        self.assertEqual(c.evaluate(measurements, provenance())["status"],
                         "INCREMENTAL_FAIL")
        for identity in (0, 385, 388, 999):
            self.assertIsNone(c.authorize_esc_b1(provenance(), live(),
                                                 c.ESC_B1_REPO, identity, "head"))
        for metric in ("iram", "dram", "bss"):
            base = {"iram": 67551, "dram": 54864, "bss": 43792}
            newer = dict(base)
            newer[metric] += 1
            self.assertEqual(c.judge(base, newer)["status"], "INCREMENTAL_FAIL")

    def test_wrong_fork_pr_ref_head_patch_and_ancestry(self):
        bad = [
            [("head", "ref", "other-branch")],
            [("head", "repo", {"full_name": "evil/ESP32-Locomotive-Basic"})],
            [("head", "sha", "f" * 40)],
            [("provenance", "pr_number", 388)],
            [("live", "state", "closed")],
            [("live", "title", "unrelated")],
            [("live", "base", {"ref": "main",
                              "repo": {"full_name": c.ESC_B1_REPO},
                              "sha": "e" * 40})],
        ]
        for changes in bad:
            with self.subTest(changes=changes), self.assertRaisesRegex(
                    ValueError, "ESC allocation"):
                self.approved(changes=changes)
        with self.assertRaisesRegex(ValueError, "ancestry"):
            self.approved(anc_ok=False)

        opts = ("diff", "--binary", "--no-ext-diff", "--no-renames")
        b1 = ("--", *sorted(c.ESC_B1_PATHS))
        original_names = "\n".join(sorted(c.ESC_B1_PATHS))
        closed_names = "\n".join(sorted(c.ESC_B1_PATHS |
                                         frozenset(c.ESC_B1_HOST_BLOBS) |
                                         c.ESC_B1_CI_PATHS))
        tampering = [
            {("cat-file", "-t", c.ESC_B1_SOURCE_BASE): "missing"},
            {("cat-file", "-t", c.ESC_B1_PO_HEAD): "missing"},
            {("diff", "--name-only", "--no-renames",
              c.ESC_B1_SOURCE_BASE, c.ESC_B1_SOURCE_HEAD): "other.py"},
            {("diff", "--name-only", "--no-renames",
              BASE, HEAD): closed_names + "\nother.py"},
            {(*opts, BASE, HEAD, *b1): "tampered B1 patch"},
            {("ls-tree", HEAD, "--",
              "integration/hw4_run_scheduler.c"):
             "100644 blob " + "f" * 40 +
             "\tintegration/hw4_run_scheduler.c"},
        ]
        for overrides in tampering:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.approved(git_overrides=overrides)

    def test_host_runner_blob_and_mode_must_match_po_firmware(self):
        self.assertEqual(c.ESC_B1_PO_HEAD,
                         "5e44ca338e91283484b2ac41c46a7fcc3b2b0a10")
        self.assertEqual(c.ESC_B1_HOST_BLOBS,
                         {"tools/hw4_esc_b1_po_auto.py":
                          "c14f2772dee0ba1b303098b4d97c18d717e12736"})
        path, sha = next(iter(c.ESC_B1_HOST_BLOBS.items()))
        for overrides in (
            {("ls-tree", HEAD, "--", path):
             "100644 blob " + "f" * 40 + "\t" + path},
            {("ls-tree", HEAD, "--", path):
             "100755 blob " + sha + "\t" + path},
            {("ls-tree", c.ESC_B1_PO_HEAD, "--", path): ""},
            {("ls-tree", BASE, "--", path):
             "100644 blob " + sha + "\t" + path},
        ):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(
                    ValueError, "host runner"):
                self.approved(git_overrides=overrides)

    def test_extra_host_script_or_ci_tampering_must_fail(self):
        expected = c.ESC_B1_PATHS | frozenset(c.ESC_B1_HOST_BLOBS) | c.ESC_B1_CI_PATHS
        self.assertEqual(len(expected), 13)
        for injected in ("tools/extra_runner.py", "tools/ci/opt3_routing.py",
                         "firmware/esp32_display_probe/main/extra.c",
                         "docs/FORGED-MEMORY.md"):
            changed = "\n".join(sorted(expected | {injected}))
            overrides = {("diff", "--name-only", "--no-renames",
                          BASE, HEAD): changed}
            with self.subTest(path=injected), self.assertRaisesRegex(
                    ValueError, "closed file diff mismatch"):
                self.approved(git_overrides=overrides)
        for missing in (next(iter(c.ESC_B1_HOST_BLOBS)),
                        next(iter(c.ESC_B1_CI_PATHS))):
            changed = "\n".join(sorted(expected - {missing}))
            with self.subTest(missing=missing), self.assertRaisesRegex(
                    ValueError, "closed file diff mismatch"):
                self.approved(git_overrides={
                    ("diff", "--name-only", "--no-renames", BASE, HEAD): changed})
        for path in c.ESC_B1_CI_PATHS:
            with self.subTest(unmodified=path), self.assertRaisesRegex(
                    ValueError, "CI-only policy/test blob invalid"):
                self.approved(git_overrides={
                    ("ls-tree", HEAD, "--", path):
                    "100644 blob " + "b" * 40 + "\t" + path})

    def test_mutated_allocation_ledger_rejected(self):
        token = self.approved()
        for key, val in (("issue", 999), ("source_head", "f" * 40),
                         ("po_source_head", "f" * 40),
                         ("host_blobs", {"tools/evil.py": "f" * 40}),
                         ("ci_paths", ["tools/ci/opt3_routing.py"]),
                         ("pr_number", 388),
                         ("status", "ANY_PR_PLUS_40")):
            trial = dict(token)
            trial[key] = val
            with self.subTest(key=key), self.assertRaisesRegex(
                    ValueError, "ledger changed"):
                c.evaluate(self.b1_metrics(), provenance(), trial)
        for key, val in (("dram", 41), ("bss", 41), ("iram", 1)):
            with self.subTest(key=key):
                t = dict(token)
                t["limit"] = dict(token["limit"])
                t["limit"][key] = val
                with self.assertRaises(ValueError):
                    c.evaluate(self.b1_metrics(), provenance(), t)

    def test_future_main_after_b1_has_no_automatic_allowance(self):
        # Newer accepted real main is 54904/43832; unchanged branch is PASS
        # despite old C3/RENDER-A 54864, which must remain historically red.
        for variant in c.CLOCKS:
            self.write("base", variant, BASE, BASE_TREE, c.CLOCKS[variant],
                       dram=54904, bss=43832)
            self.write("head", variant, HEAD, HEAD_TREE, c.CLOCKS[variant],
                       dram=54904, bss=43832)
        r = c.evaluate(self.metrics(), provenance())
        self.assertEqual(r["status"], "INCREMENTAL_PASS")
        self.assertEqual(r["allocation"]["status"], "NO_ALLOCATION")
        self.assertEqual(r["render_a"]["historical"]["base"]["status"],
                         "HISTORICAL_FAILURE")
        self.assertEqual(r["spi_c3"]["historical"]["base"]["spi40"]["status"],
                         "HISTORICAL_FAILURE")
        self.write("head", "spi40", HEAD, HEAD_TREE, 40000000,
                   dram=54905, bss=43833)
        self.write("head", "spi20", HEAD, HEAD_TREE, 20000000,
                   dram=54905, bss=43833)
        self.assertEqual(c.evaluate(self.metrics(), provenance())["status"],
                         "INCREMENTAL_FAIL")


class HistoricalWitness(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)

    def files(self, mode, dram, iram):
        anchor = 54864 if mode == "render" else 54168
        history = self.folder / "historical.txt"
        spi40 = self.folder / "spi40.txt"
        spi20 = self.folder / "spi20.txt"
        for path, data in ((history, sect(iram=67331, dram=anchor, bss=43000)),
                           (spi40, sect(iram=iram, dram=dram, bss=43792)),
                           (spi20, sect(iram=iram, dram=dram, bss=43792))):
            path.write_text(data, encoding="utf-8")
        log = self.folder / "legacy.log"
        return log, history, spi40, spi20

    def test_history_dram_first_and_iram_first_both_valid_rc1(self):
        cases = [
            ("render", 54904, 67551, "ValueError: " + legacy.RENDER_DRAM, "DRAM"),
            ("render", 54864, 67551, "ValueError: " + legacy.RENDER_IRAM, "IRAM"),
            ("c3", 54904, 67551, "AssertionError: ('spi40', '" + legacy.C3_DRAM + "')", "DRAM"),
            ("c3", 54864, 67551, "AssertionError: ('spi40', '" + legacy.C3_IRAM + "')", "IRAM"),
        ]
        for mode, dram, iram, message, first in cases:
            with self.subTest(mode=mode, first=first):
                log, h, a, b = self.files(mode, dram, iram)
                log.write_text("Traceback (most recent call last):\n" + message + "\n")
                result = legacy.attest(mode, 1, log, h, a, b)
                self.assertEqual(result["status"], "HISTORICAL_FAILURE")
                self.assertEqual(result["old_rc"], 1)
                self.assertEqual(result["first_failed_metric"], first)

    def test_bad_legacy_rc_or_wrong_error_always_stops(self):
        for mode in ("render", "c3"):
            log, h, a, b = self.files(mode, 54904, 67551)
            marker = ("ValueError: " + legacy.RENDER_DRAM if mode == "render"
                      else "AssertionError: ('spi40', '" + legacy.C3_DRAM + "')")
            log.write_text("Traceback (most recent call last):\n" + marker + "\n")
            for rc in (0, 2, 3, -1):
                with self.subTest(mode=mode, rc=rc), self.assertRaisesRegex(
                        ValueError, "unexpected rc"):
                    legacy.attest(mode, rc, log, h, a, b)
            log.write_text("Traceback (most recent call last):\nIRAM changed\n")
            with self.assertRaises(ValueError):
                legacy.attest(mode, 1, log, h, a, b)
            log.write_text(marker)
            with self.assertRaises(ValueError):
                legacy.attest(mode, 1, log, h, a, b)
            log.write_text("Traceback (most recent call last):\n" + marker + "\n")
            b.write_text(sect(iram=67552, dram=54904, bss=43792))
            with self.assertRaisesRegex(ValueError, "SPI mismatch"):
                legacy.attest(mode, 1, log, h, a, b)
            b.write_text("")
            with self.assertRaises(ValueError):
                legacy.attest(mode, 1, log, h, a, b)


if __name__ == "__main__":
    unittest.main()
