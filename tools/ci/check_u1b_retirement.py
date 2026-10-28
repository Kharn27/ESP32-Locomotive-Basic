#!/usr/bin/env python3
"""U1-B: fail closed on a retired ESP-IDF root in active build instructions.

Historical documents are intentionally not scanned: their path references
preserve audit provenance. The scan concerns executable consumers only.
"""
import argparse
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
RETIRED = "firmware/" + "esp32_probe"
PROJECT = ROOT / "firmware" / "esp32_display_probe"
ENTRYPOINTS = (
    PROJECT / "main" / "hw4_c2_console.c",
    PROJECT / "main" / "main.c",
    PROJECT / "main" / "basic_probe.c",
)


def active_files():
    paths = [ROOT / "CMakeLists.txt"]
    paths += list((ROOT / ".github" / "workflows").glob("*.yml"))
    paths += list((ROOT / "firmware").rglob("CMakeLists.txt"))
    paths += list((ROOT / "firmware").rglob("*.cmake"))
    paths += [p for p in (ROOT / "tools").rglob("*")
              if p.is_file() and p.suffix in (".py", ".sh", ".cmake")]
    return sorted(set(paths))


def stale(text):
    return RETIRED in text.replace("\\", "/")


def self_test():
    assert stale("build " + RETIRED + "/main")
    assert stale("python " + RETIRED + "/scripts/check_build.py")
    assert not stale("firmware/esp32_display_probe/main/basic_probe.c")
    assert not stale("historic probe source renamed to basic_probe.c")
    assert re.findall(r"\bvoid\s+app_main\s*\(\s*void\s*\)", "void app_main(void)")
    print("U1-B RETIRED_REFERENCE_FALSIFICATION=PASS")


def scan():
    if (ROOT / RETIRED).exists():
        raise AssertionError("U1-B retired ESP-IDF directory still exists")
    for path in ENTRYPOINTS:
        source = path.read_text(encoding="utf-8")
        if len(re.findall(r"\bvoid\s+app_main\s*\(\s*void\s*\)", source)) != 1:
            raise AssertionError("U1-B missing or duplicated source app_main: " + str(path))
    for path in (
        ROOT / "firmware/components/loco_core/CMakeLists.txt",
        ROOT / "firmware/components/cyd_ili9341/CMakeLists.txt",
        ROOT / "tools/ci/check_build.py",
        ROOT / "tools/ci/report_abi.py",
    ):
        if not path.is_file():
            raise AssertionError("U1-B migrated consumer missing: " + str(path))
    if "project(loco_esp32_display_probe)" not in (PROJECT / "CMakeLists.txt").read_text():
        raise AssertionError("U1-B canonical project name changed")
    found = [str(path.relative_to(ROOT)) for path in active_files()
             if stale(path.read_text(encoding="utf-8"))]
    if found:
        raise AssertionError("U1-B retired executable reference(s): " + ", ".join(found))
    print("U1-B SINGLE_ROOT_ACTIVE_REFERENCES=PASS")
    print("U1-B SOURCE_ENTRYPOINTS=3/3")
    print("U1-B HISTORICAL_DOCS_EXCLUDED=PROVENANCE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--self-test", action="store_true")
    selection.add_argument("--scan", action="store_true")
    args = parser.parse_args()
    self_test() if args.self_test else scan()
