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

    def test_b3_relative_dram_cap_rejected(self):
        for v in c.CLOCKS:
            self.write("base", v, BASE, BASE_TREE, c.CLOCKS[v],
                       dram=54865)
        r = c.evaluate(self.metrics(), provenance())
        self.assertEqual(r["spi_c3"]["variants"]["status"], "SPI_VARIANTS_PARITY_FAIL")

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


if __name__ == "__main__":
    unittest.main()

# Independent C7 single-byte adversarial regression checks (synthetic fixtures).
class SingleByte(unittest.TestCase):
    def test_independent_plus_one_iram_dram_bss(self):
        for variant in c.CLOCKS:
            base={"iram":67551,"dram":54864,"bss":43792}
            for key in base:
                with self.subTest(variant=variant,key=key):
                    head=dict(base); head[key]+=1
                    self.assertEqual(c.judge(base,head)["status"],"INCREMENTAL_FAIL")

