#!/usr/bin/env python3
"""C3 static guard for real ESP-IDF CONSOLE boot and bool/enum contracts.

This is a source-level test, NOT a physical CYD boot test. It consumes the
actual CONSOLE production file from the checkout tested by GitHub Actions.
"""
import argparse
import pathlib
import re
import sys

def functions(src):
    # Match only functions defined at file scope; skip function prototypes.
    pattern = re.compile(r"(?m)^(static[ \t]+)?(bool|Hw4PenDisplayResult|void)[ \t]+"
                         r"([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{")
    out = {}
    for match in pattern.finditer(src):
        depth, pos = 1, match.end()
        while depth and pos < len(src):
            if src[pos] == "{":
                depth += 1
            elif src[pos] == "}":
                depth -= 1
            pos += 1
        if depth:
            raise AssertionError("unbalanced function body: " + match[3])
        out[match[3]] = (match[2], src[match.end():pos-1])
    return out

def verify(source):
    fs = functions(source)
    mandatory_bool = ("fail", "render_band", "repaint_full", "touch_init",
        "touch_poll", "send_dirty_band", "repaint_dirty", "display_error",
        "display_bytes", "apply_ready_policy", "prompt", "basic_submit",
        "basic_run", "is_command", "diagnostic_demo", "execute_line",
        "uart_init", "run_preflight", "run_replay", "basic_run_slice")
    for name in mandatory_bool:
        assert name in fs and fs[name][0] == "bool", "bool signature: "+name
    # B migrates the old enum display function into two bool callbacks.
    assert "display_print_events" not in fs
    assert "app_main" in fs and fs["app_main"][0] == "void"

    # Exhaustive check of literal returns in every CONSOLE bool/enum function;
    # a zero-valued success enum MUST NOT cross a bool boundary, and a
    # C99 true literal MUST NOT be used as an enum success.
    for name, (return_type, body) in fs.items():
        if return_type == "bool":
            assert not re.search(r"\breturn\s+HW4_PEN_(?:DISPLAY|RUN|OK)\w*\s*;", body), (
                "bool/enum mismatch in " + name)
        if return_type == "Hw4PenDisplayResult":
            assert not re.search(r"\breturn\s+(?:true|false)\s*;", body), (
                "bool literal in enum-returning "+name)

    repaint = fs["repaint_dirty"][1]
    returns = re.findall(r"\breturn\s+([^;]+);", repaint)
    assert returns == ["false", "true"], (
        "repaint_dirty must return false on DMA failure and true on success "
        "with dirty bands OR with zero dirty bands: " + repr(returns))
    assert "if(s_video.dirty_bands!=0U)" in repaint
    assert "if(!ok)" in repaint and "return false;" in repaint
    assert repaint.rstrip().endswith("return true;")
    full = fs["repaint_full"][1]
    assert "if(!render_band(top)) return false;" in full
    assert full.rstrip().endswith("return true;")
    touch = fs["touch_init"][1]
    assert "if(e!=ESP_OK) return fail(" in touch
    assert touch.rstrip().endswith("return true;")
    run = fs["basic_run"][1]
    assert "hw4_run_scheduler_init(&s_run_scheduler" in run
    assert "RUN_STEP_BUDGET" not in source
    driver = fs["basic_run_slice"][1]
    assert "hw4_run_scheduler_slice(&s_run_scheduler" in driver
    assert "if(slice.state==HW4_RUN_YIELDED)" in driver
    assert "return apply_ready_policy(s_run_ready_transition) && prompt();" in driver
    preflight = fs["run_preflight"][1]
    replay = fs["run_replay"][1]
    assert "hw4_pen_preflight(&s_text" in preflight
    assert "hw4_pen_replay(&s_text" in replay
    assert replay.rstrip().endswith("return s_run_video_failure==HW4_PEN_OK;")

    prompt = fs["prompt"][1]
    assert "if(!repaint_dirty()) return false;" in prompt
    assert prompt.index("if(!repaint_dirty())") < prompt.index("INPUT_READY")
    assert prompt.rstrip().endswith("return true;")
    main = fs["app_main"][1]
    boot_markers = (
        'printf("HW4-C2 HELP',
        "if(!prompt()) return;",
        "if(!touch_init()) return;",
        'printf("HW4-C3-B2-C1 ECHO_POLICY',
        "for(;;)"
    )
    offsets = [main.find(marker) for marker in boot_markers]
    assert all(offset >= 0 for offset in offsets), "boot chain missing "+str(offsets)
    assert offsets == sorted(offsets), "app_main startup order incorrect"
    print("C3 BOOT_GUARD PASS signatures="+str(len(fs))+
          " bool_functions="+str(len(mandatory_bool))+
          " boot=HELP>prompt>INPUT_READY>touch_init>BOOT_READY>ECHO_POLICY>loop"+
          " dirty=0/nonzero success=true dma_failure=false enum_success=0")

def self_test(source):
    verify(source)
    # Mutants must be detected. No repository file is changed.
    replacements = (
        ("return s_run_video_failure==HW4_PEN_OK;\n}\nstatic bool display_error(void)",
         "return HW4_PEN_DISPLAY_OK;\n}\nstatic bool display_error(void)"),
        ("return s_run_video_failure==HW4_PEN_OK;\n}\nstatic bool display_error(void)",
         "return true;\n}\nstatic bool display_error(void)"),
        ("if(!prompt()) return;", "if(prompt()) return;"),
        ("if(!touch_init()) return;", "if(touch_init()) return;"),
    )
    for i, (old, new) in enumerate(replacements):
        assert old in source, "mutation anchor not found "+str(i)
        mutant = source.replace(old,new,1)
        try:
            verify(mutant)
        except AssertionError:
            continue
        raise AssertionError("test guard accepted known bad source mutant "+str(i))
    print("C3 MUTATIONS 4/4 REJECTED")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("console", type=pathlib.Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    text = args.console.read_text(encoding="utf-8")
    try:
        if args.self_test:
            self_test(text)
        else:
            verify(text)
    except AssertionError as exc:
        print("C3 BOOT_GUARD FAIL: "+str(exc), file=sys.stderr)
        sys.exit(1)
