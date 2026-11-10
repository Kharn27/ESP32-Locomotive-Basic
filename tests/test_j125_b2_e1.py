"""J1.25-B2-E1 #358: pure adversarial contracts, zero target builds."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "ci"))
import j125_b2_e1 as e1


def cell(hz, iram=67551, dram=54864, bss=43792, suffix=""):
    return dict(iram=iram, dram=dram, bss=bss, iram_text=66523,
                flash_text=170000, flash_rodata=57000, bin_bytes=307000,
                bin_sha256="sha" + str(hz) + suffix)


class Adversarial(unittest.TestCase):
    def setUp(self):
        self.c={
            "M":{str(h):cell(h,suffix="M") for h in (40000000,20000000)},
            "C":{str(h):cell(h,suffix="C") for h in (40000000,20000000)}}

    def test_zero_delta_pass_is_only_integration(self):
        result=e1.compare(self.c)
        self.assertEqual(result["verdict"],"INTEGRATION_MEMORY_PASS")
        self.assertFalse(result["integration_ready"])
        self.assertEqual(result["historical_B_to_H"],"FAIL_PLUS_220_IRAM")
        self.assertEqual(result["historical_RENDER_A_C3"],"HISTORICAL_FAILURE")

    def test_plus_one_each_section_fails(self):
        for k in ("iram","dram","bss"):
            with self.subTest(k=k):
                c=copy.deepcopy(self.c)
                for hz in ("40000000","20000000"):
                    c["C"][hz][k]+=1
                self.assertEqual(e1.compare(c)["verdict"],
                                 "INTEGRATION_MEMORY_FAIL")

    def test_parity_fails_closed(self):
        for k in ("iram","dram","bss"):
            with self.subTest(k=k):
                c=copy.deepcopy(self.c)
                c["C"]["20000000"][k]+=1
                with self.assertRaises(e1.Invalid):e1.compare(c)

    def test_clock_binary_parity_required(self):
        c=copy.deepcopy(self.c)
        c["C"]["20000000"]["bin_sha256"]=c["C"]["40000000"]["bin_sha256"]
        with self.assertRaises(e1.Invalid):e1.compare(c)

    def test_absolute_dram_cap(self):
        c=copy.deepcopy(self.c)
        for hz in ("40000000","20000000"):
            c["C"][hz]["dram"]=54865
        self.assertEqual(e1.compare(c)["verdict"],"INTEGRATION_MEMORY_FAIL")

    def test_missing_sections(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"sections"
            p.write_text(".dram0.bss 43792 0\n")
            with self.assertRaises(e1.Invalid):e1.sizes(p)

    def test_malformed_sections_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"sections"
            p.write_text(".dram0.data 1 0\n.dram0.data 2 0\n")
            with self.assertRaises(e1.Invalid):e1.sizes(p)

    def test_wrong_cache_and_missing_artifact(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(e1.Invalid):
                e1.inspect_cell(Path(folder),"M",40000000,e1.M)

    def test_wrong_identity_and_live_api_drift(self):
        event={"pr":"358","head":"a"*40}
        snap={"main":{"commit":{"sha":e1.M}},
          "pr330":{"number":330,"state":"open","draft":True,
             "merged_at":None,
             "base":{"ref":"main","sha":e1.B,
                     "repo":{"full_name":e1.REPO}},
             "head":{"sha":e1.H,"repo":{"full_name":e1.REPO}}},
          "lab":{"number":358,"state":"open","merged_at":None,
             "base":{"ref":"main","sha":e1.M},
             "head":{"sha":"a"*40,"repo":{"full_name":e1.REPO}}}}
        e1.validate_snapshot(snap,event)
        for path,wrong in [(("main","commit","sha"),"b"*40),
                           (("pr330","head","sha"),"c"*40),
                           (("lab","head","sha"),"d"*40)]:
            wrong_state=copy.deepcopy(snap)
            item=wrong_state
            for key in path[:-1]:item=item[key]
            item[path[-1]]=wrong
            with self.assertRaises(e1.Invalid):
                e1.validate_snapshot(wrong_state,event)

    def test_no_fifth_real_build(self):
        with self.assertRaises(e1.Invalid):
            e1.require(5<=4,"FIFTH_BUILD_REFUSED")


if __name__=="__main__":
    unittest.main()
