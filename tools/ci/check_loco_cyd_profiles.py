#!/usr/bin/env python3
"""U1-A: exercise the actual CMake profile selector without ESP-IDF hardware.

The self-test includes invalid aliases, contradictory flags and two app_main
symbols. The --nm mode checks the linked Xtensa symbol table, not sources.
"""
import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SELECTOR = ROOT / "firmware" / "esp32_display_probe" / "profile_select.cmake"
APP_MAIN = re.compile(r"^\\S+ [TW] app_main$", re.MULTILINE)


def count_app_main(nm_output: str) -> int:
    return len(APP_MAIN.findall(nm_output))


def check_one_app_main(nm_output: str) -> None:
    count = count_app_main(nm_output)
    if count != 1:
        raise AssertionError(f"U1-A expected exactly one linked app_main, got {count}")


def cmake_case(label: str, args: list[str], valid: bool, profile: str = "") -> None:
    completed = subprocess.run(
        ["cmake", *args, "-P", str(SELECTOR)], cwd=ROOT,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        check=False,
    )
    output = completed.stdout
    if valid:
        if completed.returncode or f"LOCO_CYD_SELECTED={profile} " not in output:
            raise AssertionError(f"{label}: expected {profile}, got:\\n{output}")
    elif completed.returncode == 0 or not (
        "U1-A invalid" in output or "U1-A conflicting selectors" in output
    ):
        raise AssertionError(f"{label}: fail-closed selection missing:\\n{output}")
    print(f"U1-A SELECTOR_{label}=PASS")


def self_test() -> None:
    valid = [
        ("DEFAULT_CONSOLE", [], "CONSOLE"),
        ("LEGACY_ON", ["-DHW4_C2_CONSOLE=ON"], "CONSOLE"),
        ("LEGACY_OFF", ["-DHW4_C2_CONSOLE=OFF"], "HW3"),
        ("EXPLICIT_CONSOLE", ["-DLOCO_CYD_PROFILE=CONSOLE"], "CONSOLE"),
        ("EXPLICIT_HW3", ["-DLOCO_CYD_PROFILE=HW3"], "HW3"),
        ("EXPLICIT_BASIC", ["-DLOCO_CYD_PROFILE=BASIC_PROBE"], "BASIC_PROBE"),
        ("MATCH_ON", ["-DLOCO_CYD_PROFILE=CONSOLE", "-DHW4_C2_CONSOLE=ON"], "CONSOLE"),
        ("MATCH_OFF", ["-DLOCO_CYD_PROFILE=HW3", "-DHW4_C2_CONSOLE=OFF"], "HW3"),
    ]
    invalid = [
        ("UNKNOWN", ["-DLOCO_CYD_PROFILE=UNKNOWN"]),
        ("EMPTY", ["-DLOCO_CYD_PROFILE="]),
        ("LOWERCASE", ["-DLOCO_CYD_PROFILE=console"]),
        ("LEGACY_GARBAGE", ["-DHW4_C2_CONSOLE=NA"]),
        ("COLLISION_ON", ["-DLOCO_CYD_PROFILE=HW3", "-DHW4_C2_CONSOLE=ON"]),
        ("COLLISION_OFF", ["-DLOCO_CYD_PROFILE=CONSOLE", "-DHW4_C2_CONSOLE=OFF"]),
        ("BASIC_WITH_LEGACY", ["-DLOCO_CYD_PROFILE=BASIC_PROBE", "-DHW4_C2_CONSOLE=ON"]),
    ]
    for label, args, profile in valid:
        cmake_case(label, args, True, profile)
    for label, args in invalid:
        cmake_case(label, args, False)
    for nm in ["", "00000000 T app_main\\n00000010 T app_main\\n"]:
        try:
            check_one_app_main(nm)
        except AssertionError:
            pass
        else:
            raise AssertionError("Duplicate/missing app_main escaped the test")
    check_one_app_main("00000000 T app_main\\n")
    print("U1-A DOUBLE_APP_MAIN_REJECTED=PASS")
    print(f"U1-A SELECTOR_MATRIX={len(valid) + len(invalid)}/"
          f"{len(valid) + len(invalid)} PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    exclusive = parser.add_mutually_exclusive_group(required=True)
    exclusive.add_argument("--self-test", action="store_true")
    exclusive.add_argument("--nm", action="store_true",
                           help="check xtensa-esp-elf-nm --defined-only via stdin")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        check_one_app_main(sys.stdin.read())
        print("U1-A ONE_APP_MAIN=PASS")


if __name__ == "__main__":
    main()
