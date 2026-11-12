#!/usr/bin/env python3
"""PO-AUTO-01: fail-closed, single-owner CYD physical campaign recorder.

Proof boundaries: captured RX bytes, independently recorded TX, CRC-validated
logical VRAM images, and PO review. No physical TFT or CPC approval is implied.
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
sys.dont_write_bytecode = True  # No Python cache artefacts beside the repository tools.
import time
import zipfile

from hw4_shot_watch import Watcher
from hw4_shot_decode import PREFIX, FAMILY, ShotError, _begin, _transport_line

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "firmware/esp32_display_probe"
SUITES = Path(__file__).resolve().parent / "cyd_po_suites"
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
UART_LINE = re.compile(r"HW4-C2 UART_LINE length=(\d+) hex=([0-9a-f]+)(?:\s|$)")
BOOT = re.compile(r"HW4-C2 START project=([^ ]+) version=([^ ]+) idf=([^ ]+) target=([^ ]+)")
FATAL = re.compile(r"Guru Meditation|panic|Backtrace:|LCD_FAIL_STOP|HW4-C2 FAIL |MEMORY_FAIL|VIDEO_REJECT|HW4_RUN_DISPLAY_.*FAILED|RENDER_FAIL_STOP", re.I)
MEMORY = re.compile(r"HW4-C2 DEVICE_MEMORY stage=([^ ]+) (.+)")
RUN_TERMINAL = re.compile(r"HW4-RUN-B RUN_TERMINAL (.+)")
START = "HW4-C2 START "
RENDER_HISTORICAL = "RENDER_A_HISTORICAL_FAILURE"


class Incomplete(RuntimeError):
    """Campaign cannot be attested; preserve all partial artifacts."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise Incomplete(reason)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def kv(text: str) -> dict[str, str]:
    result = {}
    for part in text.split():
        if "=" in part:
            key, value = part.split("=", 1)
            require(key not in result and bool(value), "DUPLICATE_OR_EMPTY_FIELD")
            result[key] = value
    return result


def run_git(*args: str) -> str:
    result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                            text=True, check=False)
    require(result.returncode == 0, "GIT_ERROR: " + result.stderr.strip()[:300])
    return result.stdout.strip()


def identity() -> str:
    require(Path(run_git("rev-parse", "--show-toplevel")).resolve() == ROOT.resolve(),
            "WRONG_REPOSITORY_ROOT")
    head = run_git("rev-parse", "--verify", "HEAD")
    require(bool(FULL_SHA.fullmatch(head)), "BAD_GIT_HEAD")
    require(not run_git("status", "--porcelain", "--untracked-files=no"),
            "TRACKED_SOURCES_DIRTY")
    return head


def load_suite(name: str) -> dict:
    require(bool(re.fullmatch(r"[a-z0-9_]+", name)), "INVALID_SUITE_NAME")
    path = SUITES / (name + ".json")
    obj = json.loads(path.read_text(encoding="utf-8"))
    require(obj.get("schema") == 1 and obj.get("name") == name, "INVALID_SUITE_SCHEMA")
    scenarios = obj.get("scenarios")
    require(isinstance(scenarios, list) and scenarios and len(scenarios) <= 40,
            "INVALID_SCENARIO_COUNT")
    used = set()
    for item in scenarios:
        require(isinstance(item, dict) and set(item) == {"id", "group", "source", "category"},
                "INVALID_SCENARIO_FIELDS")
        ident = item["id"]
        require(isinstance(ident, str) and re.fullmatch(r"[A-Z0-9_]{1,40}", ident)
                and ident not in used, "BAD_OR_DUPLICATE_SCENARIO_ID")
        used.add(ident)
        require(item["category"] == "AUTO_UART_CRC" and isinstance(item["group"], str),
                "INVALID_SCENARIO_CATEGORY")
        rel = item["source"]
        require(isinstance(rel, str) and rel.startswith("tests/oracles/inputs/")
                and not any(x in ("..", "") for x in Path(rel).parts), "UNSAFE_SOURCE_PATH")
        source = (ROOT / rel).resolve()
        require(source.is_relative_to((ROOT / "tests/oracles/inputs").resolve()),
                "SOURCE_OUTSIDE_CORPUS")
        data = source.read_bytes()
        require(0 < len(data) < 4096 and data.endswith(b"\n") and b"\r" not in data
                and all(len(line) <= 32 and line.isascii() for line in data.splitlines()),
                "UNSUPPORTED_SOURCE_FORMAT: " + ident)
        item["source_sha256"] = hashlib.sha256(data).hexdigest()
        item["source_lines"] = data.decode("ascii").splitlines()
    return obj


def command_line(text: str) -> bytes:
    data = text.encode("ascii")
    require(0 < len(data) <= 32 and b"\r" not in data and b"\n" not in data,
            "COMMAND_TOO_LONG")
    return data


def plan(suite: dict, shots: str) -> list[dict]:
    result = []
    for spec in suite["scenarios"]:
        operations = ["NEW", *spec["source_lines"], "LIST"]
        if shots == "all":
            operations.append("!SHOT")
        operations.append("RUN")
        if shots in ("all", "run"):
            operations.append("!SHOT")
        result.append({"id": spec["id"], "source": spec["source"],
                       "source_sha256": spec["source_sha256"], "commands": operations})
    return result


def make_folder(base: Path, suite: str, head: str) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"CYD_{suite.upper()}_{stamp}_{head[:12]}"
    # Atomic and intentionally not retried: timestamp collision must refuse overwrite.
    path.mkdir(parents=True, exist_ok=False)
    (path / "screenshots").mkdir()
    return path


def run_idf(folder: Path, head: str, port: str) -> dict:
    build_dir = folder / "_idf_build"
    sdkconfig = folder / "sdkconfig"
    def command(args: list[str], logfile: Path) -> None:
        with logfile.open("xb") as output:
            process = subprocess.run(args, cwd=PROJECT, stdout=output,
                                     stderr=subprocess.STDOUT, check=False)
        require(process.returncode == 0, "IDF_COMMAND_FAILED: " + logfile.name)
    probe = subprocess.run(["idf.py", "--version"], cwd=PROJECT,
                           capture_output=True, text=True, check=False)
    require(probe.returncode == 0 and probe.stdout.strip() == "ESP-IDF v5.5.6",
            "WRONG_HOST_IDF_VERSION")
    common = ["idf.py", "-B", str(build_dir), "-DSDKCONFIG=" + str(sdkconfig),
              "-DLOCO_CYD_PROFILE=CONSOLE"]
    # set-target and build share a single log, kept even on failure.
    with (folder / "build.log").open("xb") as output:
        for action in (["set-target", "esp32"], ["build"]):
            p = subprocess.run(common + action, cwd=PROJECT, stdout=output,
                               stderr=subprocess.STDOUT, check=False)
            require(p.returncode == 0, "IDF_BUILD_FAILED")
    app = build_dir / "loco_esp32_display_probe.bin"
    cache = (build_dir / "CMakeCache.txt").read_text(encoding="utf-8")
    require("LOCO_CYD_PROFILE:STRING=CONSOLE" in cache, "WRONG_BUILD_PROFILE")
    # Reuse existing exact app-descriptor parser; do not trust a stale build.
    from ci.verify_esp_app_version import boot_version
    version = boot_version(app.read_bytes(), "loco_esp32_display_probe")
    require(version.startswith(head[:7]), "STALE_APP_BINARY")
    build_hash = sha256(app)
    command(common + ["-p", port, "flash"], folder / "flash.log")
    return {"binary_sha256": build_hash, "binary_version": version,
            "binary_path": str(app.relative_to(folder)), "profile": "CONSOLE"}


def collision_guard(port: str) -> None:
    # Advisory preflight complements pyserial POSIX exclusive fd ownership.
    proc = subprocess.run(["fuser", port], capture_output=True, text=True,
                          check=False) if shutil_which("fuser") else None
    if proc is not None:
        require(proc.returncode == 1, "SERIAL_PORT_BUSY_OR_UNCHECKABLE: stop idf.py monitor")


def shutil_which(command: str) -> str | None:
    from shutil import which
    return which(command)


class Session:
    """One serial reader, ordered complete lines and immutable byte-for-byte RX."""

    def __init__(self, port, folder: Path, head: str, version: str | None,
                 boot_timeout: float, command_timeout: float, shot_timeout: float):
        self.port = port
        self.folder = folder
        self.head = head
        self.version = version
        self.boot_timeout = boot_timeout
        self.command_timeout = command_timeout
        self.shot_timeout = shot_timeout
        self.raw = (folder / "uart.raw.log").open("xb", buffering=0)
        self.tx = (folder / "uart.tx.jsonl").open("x", encoding="utf-8", buffering=1)
        self.pending = bytearray()
        self.lines = deque()
        self.starts = 0
        self.memory = []
        self.shots = []
        self.shot_ids = set()
        self.shot_seq = None
        self.awaiting_shot = False
        self.shot_metadata = None
        self.watcher = Watcher(folder / "screenshots")
        self.rx_bytes = 0
        self.tx_count = 0

    def close(self) -> None:
        self.raw.close()
        self.tx.close()

    def emit(self, line: str) -> None:
        data = command_line(line)
        event = {"time_utc": utc(), "monotonic_ns": time.monotonic_ns(),
                 "command": line, "hex": (data + b"\r").hex(), "status": "attempt"}
        self.tx.write(json.dumps(event, sort_keys=True) + "\n")
        self.tx.flush()
        self.tx_count += 1
        sent = self.port.write(data + b"\r")
        self.port.flush()
        require(sent == len(data) + 1, "SHORT_UART_WRITE")

    def pump(self) -> None:
        block = self.port.read(8192)
        if not block:
            return
        self.raw.write(block)  # NEVER modified or polluted with host TX.
        self.rx_bytes += len(block)
        for char in block:
            if char == 10:
                data = bytes(self.pending) + b"\n"
                self.pending.clear()
                self.lines.append(data)
            else:
                self.pending.append(char)
                require(len(self.pending) <= 4096, "RX_LINE_OVERFLOW")

    def next_line(self, deadline: float) -> str:
        while not self.lines:
            require(time.monotonic() < deadline, "UART_TIMEOUT")
            self.pump()
        raw = self.lines.popleft()
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        self.inspect(raw, line)
        return line

    def inspect(self, raw: bytes, line: str) -> None:
        require(not FATAL.search(line), "FATAL_DIAGNOSTIC: " + line[:180])
        if START in line:
            self.starts += 1
            require(self.starts == 1, "REBOOT_DURING_CAMPAIGN")
        memory = MEMORY.search(line)
        if memory:
            sample = {"stage": memory.group(1), **kv(memory.group(2))}
            for field in ("heap8_free", "heap8_largest", "stack_margin_bytes",
                          "dma_timeouts", "dma_fault"):
                require(field in sample and sample[field].isdecimal(),
                        "INVALID_DEVICE_MEMORY_" + field)
            require(min(int(sample[k]) for k in ("heap8_free", "heap8_largest",
                          "stack_margin_bytes")) > 0, "MEMORY_EXHAUSTED")
            require(int(sample["dma_timeouts"]) == int(sample["dma_fault"]) == 0
                    and sample.get("lcd_error") == "ESP_OK", "DEVICE_MEMORY_FAULT")
            self.memory.append(sample)
        if FAMILY in line:
            try:
                rec = _transport_line(line + "\n", 0)
                require(rec is not None, "MALFORMED_SHOT_TRANSPORT")
                kind = rec.split("|", 1)[0]
                require(self.awaiting_shot, "UNSOLICITED_SHOT_FRAME")
                if kind == "BEGIN":
                    require(not self.watcher.active and self.shot_metadata is None,
                            "DUPLICATE_OR_NESTED_SHOT_BEGIN")
                    meta = _begin(rec)
                    require(meta["id"] not in self.shot_ids, "DUPLICATE_SHOT_ID")
                    self.shot_ids.add(meta["id"])
                    require(meta["sha"] == self.head and
                            meta["fw"].startswith(self.head[:7]) and
                            (self.shot_seq is None or meta["seq"] > self.shot_seq),
                            "SHOT_FIRMWARE_IDENTITY_OR_SEQUENCE_MISMATCH")
                    self.shot_seq = meta["seq"]
                    self.shot_metadata = meta
                else:
                    require(self.shot_metadata is not None, "ORPHAN_SHOT_RECORD")
                    require(kind in ("ROW", "DONE", "ABORT"), "UNKNOWN_SHOT_RECORD")
                before_bad = self.watcher.bad
                before_count = self.watcher.count
                self.watcher.feed(raw)
                require(self.watcher.bad == before_bad, "SHOT_WATCHER_REJECT")
                if kind == "ABORT":
                    raise Incomplete("SHOT_ABORT")
                if kind == "DONE":
                    require(self.watcher.count == before_count + 1 and not self.watcher.active,
                            "SHOT_MISSING_VALID_PNG")
            except (ShotError, ValueError) as exc:
                raise Incomplete("SHOT_PROTOCOL_INVALID: " + str(exc)) from exc

    def wait(self, marker: str, seconds: float) -> str:
        deadline = time.monotonic() + seconds
        while True:
            line = self.next_line(deadline)
            # Any other command echo means answers are out-of-order.
            if UART_LINE.search(line) and marker != "HW4-C2 UART_LINE ":
                raise Incomplete("UNEXPECTED_UART_COMMAND_ECHO")
            if marker in line:
                return line

    def boot(self) -> str:
        deadline = time.monotonic() + self.boot_timeout
        started = None
        display_sha = None
        uart_ready = False
        while True:
            line = self.next_line(deadline)
            if START in line:
                match = BOOT.search(line)
                require(match is not None, "MALFORMED_BOOT_START")
                project, version, idf, target = match.groups()
                require(project == "loco_esp32_display_probe" and
                        target == "esp32" and idf == "v5.5.6" and
                        version.startswith(self.head[:7]) and
                        (self.version is None or self.version == version),
                        "BOOT_WRONG_VERSION_TARGET_OR_IDF")
                started = version
            if "HW4-DISP-PROFILE BOOT " in line:
                require(started and display_sha is None, "BOOT_SHA_OUT_OF_ORDER")
                display_sha = kv(line.split("HW4-DISP-PROFILE BOOT ", 1)[1]).get("sha")
                require(display_sha == self.head, "BOOT_FULL_SHA_MISMATCH")
            if "HW4-C2 UART_READY " in line:
                require(started and display_sha, "INCOMPLETE_BOOT_PROVENANCE")
                require("port=0 baud=115200" in line, "WRONG_UART_CONTRACT")
                uart_ready = True
            if "HW4-C3-B2 INPUT_READY " in line:
                require(uart_ready and started is not None and display_sha == self.head,
                        "BOOT_READY_OUT_OF_ORDER")
                return started

    def submit(self, line: str, transition: str, run: bool = False) -> None:
        self.emit(line)
        echo = self.wait("HW4-C2 UART_LINE ", self.command_timeout)
        match = UART_LINE.search(echo)
        data = command_line(line)
        require(match is not None and int(match.group(1)) == len(data)
                and match.group(2) == data.hex(), "UART_ECHO_OR_ORDER_MISMATCH")
        if run:
            memory_at_run_start = len(self.memory)
            started = self.wait("HW4-RUN-B RUN_START ", self.command_timeout)
            fields = kv(started.split("HW4-RUN-B RUN_START ", 1)[1])
            require(fields.get("sha") == self.head and fields.get("budget") == "none",
                    "RUN_START_BAD_PROVENANCE")
            terminal = self.wait("HW4-RUN-B RUN_TERMINAL ", self.command_timeout)
            details = kv(terminal.split("HW4-RUN-B RUN_TERMINAL ", 1)[1])
            require(details.get("sha") == self.head and details.get("state") == "5"
                    and details.get("break_source") == "none"
                    and details.get("stop_calls") == "0"
                    and details.get("overflow_input_lines") == "0"
                    and details.get("ignored_input_lines") == "0"
                    and details.get("steps", "0").isdecimal()
                    and int(details["steps"]) > 0, "RUN_NOT_NORMAL_TERMINAL")
        policy = self.wait("HW4-READY-A READY_POLICY ", self.command_timeout)
        require(f"transition={transition} " in policy, "READY_POLICY_OUT_OF_ORDER")
        self.wait("HW4-C3-B2 INPUT_READY ", self.command_timeout)
        if run:
            terminals = [m for m in self.memory[memory_at_run_start:]
                         if m["stage"] == "run_terminal"]
            require(len(terminals) == 1, "MISSING_OR_DUPLICATE_RUN_MEMORY")

    def capture(self, scenario: str, stage: str) -> dict:
        require(not self.awaiting_shot and self.shot_metadata is None, "SHOT_STATE_LEAK")
        self.awaiting_shot = True
        existing = set((self.folder / "screenshots").glob("*.png"))
        try:
            self.submit("!SHOT", "DIRECT_UNKNOWN")
            done = self.wait("HW4-SHOT-A CAPTURE_DONE ", self.shot_timeout)
            fields = kv(done.split("HW4-SHOT-A CAPTURE_DONE ", 1)[1])
            meta = self.shot_metadata
            require(meta is not None and fields.get("id") == meta["id"]
                    and fields.get("seq") == str(meta["seq"])
                    and fields.get("sha") == self.head and not self.watcher.active,
                    "SHOT_DONE_METADATA_MISMATCH")
            files = set((self.folder / "screenshots").glob("*.png")) - existing
            require(len(files) == 1, "SHOT_PNG_COUNT_MISMATCH")
            src = next(iter(files))
            name = f"{scenario}_{stage}.png"
            dst = self.folder / "screenshots" / name
            require(not dst.exists(), "REFUSE_SHOT_OVERWRITE")
            src.rename(dst)
            record = {"scenario": scenario, "stage": stage, "id": meta["id"],
                      "seq": meta["seq"], "sha": meta["sha"],
                      "orientation": meta["orient"], "png": "screenshots/" + name,
                      "png_sha256": sha256(dst), "status": "LOGICAL_VRAM_VERIFIED"}
            self.shots.append(record)
            return record
        finally:
            self.awaiting_shot = False
            self.shot_metadata = None


def write_json(path: Path, obj: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(obj, stream, indent=2, ensure_ascii=False, sort_keys=True)
        stream.write("\n")


def finalize(folder: Path, result: dict) -> Path:
    write_json(folder / "results.json", result)
    lines = ["# Compte rendu PO — à compléter", "", "Statut automatique : **" + result["status"] + "**",
             "", "La validation UART/CRC ne valide **pas** le TFT réel ni l'imprimante CPC.", "",
             "## MANUAL_PO_VISUAL", "", "- [ ] Orientation dalle réelle et PNG logique",
             "- [ ] Défilement et fluidité", "- [ ] Sensibilité tactile",
             "- [ ] Confrontation physique couleurs/cadre/curseur", "",
             "Observations PO (photos, défauts, SHA flashé) :", "", "…", ""]
    (folder / "rapport_PO_a_completer.md").write_text("\n".join(lines), encoding="utf-8")
    files = sorted(p for p in folder.rglob("*") if p.is_file() and
                   "_idf_build" not in p.relative_to(folder).parts and
                   p.name != "SHA256SUMS" and p.suffix != ".zip")
    (folder / "SHA256SUMS").write_text("".join(f"{sha256(p)}  {p.relative_to(folder)}\n"
                                             for p in files), encoding="ascii")
    archive = folder / (folder.name + ".zip")
    # zip created exclusive first; zipfile accepts an already-open handle.
    with archive.open("xb") as stream:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6) as zipped:
            for path in files + [folder / "SHA256SUMS"]:
                zipped.write(path, arcname=str(path.relative_to(folder)))
    return archive


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", help="CYD UART0 e.g. /dev/ttyUSB0 (exclusive)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--flash", action="store_true", help="build + flash CONSOLE once")
    mode.add_argument("--existing-firmware", action="store_true",
                      help="require full boot version and SHA match local HEAD")
    ap.add_argument("--suite", default="j1_25_b2_b3")
    ap.add_argument("--shots", choices=("all", "run", "none"), default="all")
    ap.add_argument("--dry-run", action="store_true", help="validate + print only, no hardware/files")
    ap.add_argument("--output-root", type=Path, default=ROOT / "cyd-campaigns")
    ap.add_argument("--boot-timeout", type=float, default=60)
    ap.add_argument("--command-timeout", type=float, default=30)
    ap.add_argument("--shot-timeout", type=float, default=120)
    a = ap.parse_args(argv)
    if any(x <= 0 for x in (a.boot_timeout, a.command_timeout, a.shot_timeout)):
        ap.error("timeouts must be positive")
    if not a.dry_run and (not a.port or not (a.flash or a.existing_firmware)):
        ap.error("--port and exactly one of --flash / --existing-firmware required")
    folder = None
    session = None
    result = {"status": "INCOMPLETE", "classification": "AUTO_UART_CRC",
              "manual": "MANUAL_PO_VISUAL", "scenarios": [], "shots": [],
              "memory": [], "errors": [], "historical_render_a": "EXCLUDED_FROM_PHYSICAL_QUALIFICATION"}
    try:
        head = identity()
        suite = load_suite(a.suite)
        steps = plan(suite, a.shots)
        if a.dry_run:
            print(json.dumps({"head": head, "suite": a.suite, "shots": a.shots,
                              "planned": steps, "classification": "NOT_VERIFIED"}, indent=2))
            return 0
        folder = make_folder(a.output_root, a.suite, head)
        expected_shots = len(steps) * {"all": 2, "run": 1, "none": 0}[a.shots]
        result.update({"head": head, "suite": a.suite, "shots_mode": a.shots,
                       "expected_png_count": expected_shots, "coverage": "EXHAUSTIVE"
                       if a.shots == "all" else "REDUCED_SMOKE",
                       "started_utc": utc(), "port": a.port, "idf": "v5.5.6",
                       "scenario_sources": [{"id": p["id"], "path": p["source"],
                                             "sha256": p["source_sha256"]} for p in steps]})
        write_json(folder / "manifest.json", {"schema": 1, "head": head,
            "suite": a.suite, "shots_mode": a.shots, "expected_png_count": expected_shots,
            "coverage": result["coverage"], "started_utc": result["started_utc"],
            "plan": steps, "classification": "NOT_VERIFIED_UNTIL_RESULTS"})
        firmware = run_idf(folder, head, a.port) if a.flash else {"mode": "existing_firmware"}
        result["firmware"] = firmware
        # Recheck after build/flash before trusting the source identity.
        require(identity() == head, "SOURCE_CHANGED_AFTER_BUILD")
        collision_guard(a.port)
        try:
            import serial  # pyserial is only required by the hardware path.
        except ImportError as exc:
            raise Incomplete("PYSERIAL_MISSING: python3 -m pip install pyserial") from exc
        print("Press CYD RESET once after the serial port opens, to capture a COMPLETE boot.",
              flush=True)
        # Preconfigure inactive modem lines before opening the port. A USB
        # serial driver can still glitch DTR/RTS, hence mandatory boot audit.
        port = serial.Serial(port=None, baudrate=115200, timeout=0.10,
                             write_timeout=5, exclusive=True)
        port.dtr = False
        port.rts = False
        port.port = a.port
        with port:
            if not port.is_open:
                port.open()
            session = Session(port, folder, head, firmware.get("binary_version"),
                              a.boot_timeout, a.command_timeout, a.shot_timeout)
            version = session.boot()
            result["observed_app_version"] = version
            for item in steps:
                last_command = None
                case = {"id": item["id"], "status": "INCOMPLETE", "commands": 0,
                        "source_sha256": item["source_sha256"],
                        "rx_start_bytes": session.rx_bytes, "tx_start_count": session.tx_count}
                result["scenarios"].append(case)
                for command in item["commands"]:
                    if command == "!SHOT":
                        # No positional ambiguity: last executed non-SHOT command.
                        require(last_command in ("LIST", "RUN"), "SHOT_BEFORE_TERMINAL")
                        stage = last_command
                        session.capture(item["id"], stage)
                    else:
                        transition = ("NEW_RETURN" if command == "NEW" else
                                      "LIST_RETURN" if command == "LIST" else
                                      "NUMBERED_STORED" if command[0].isdigit() else
                                      "RUN_RETURN")
                        session.submit(command, transition, run=(command == "RUN"))
                        last_command = command
                    case["commands"] += 1
                case["status"] = "AUTO_UART_CRC_CANDIDATE"
                case["rx_end_bytes"] = session.rx_bytes
                case["tx_end_count"] = session.tx_count
                case["captures"] = [s["stage"] for s in session.shots
                                    if s["scenario"] == item["id"]]
            require(identity() == head, "SOURCE_CHANGED_DURING_CAMPAIGN")
            for source in steps:
                require(sha256(ROOT / source["source"]) == source["source_sha256"],
                        "SOURCE_MUTATED_DURING_CAMPAIGN")
            require(session.watcher.bad == 0 and not session.watcher.active,
                    "SHOT_FRAME_REJECTED_OR_INCOMPLETE")
            require(len(session.shots) == expected_shots, "PNG_COUNT_MISMATCH")
            result["status"] = "PO_REVIEW_PENDING"
    except (Incomplete, OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt,
            json.JSONDecodeError) as exc:
        reason = "INTERRUPTED_BY_OPERATOR" if isinstance(exc, KeyboardInterrupt) else str(exc)
        result["errors"].append(reason)
        print("PO-AUTO-01 INCOMPLETE: " + reason, file=sys.stderr)
    finally:
        if session is not None:
            result["memory"] = session.memory
            result["shots"] = session.shots
            result["rx_bytes"] = session.rx_bytes
            result["tx_count"] = session.tx_count
            session.close()
        if folder is not None:
            result["completed_utc"] = utc()
            try:
                archive = finalize(folder, result)
                print(f"PO-AUTO-01 {result['status']} : {folder}\nZIP: {archive}\n"
                      f"ZIP_SHA256: {sha256(archive)}", flush=True)
            except (OSError, ValueError) as exc:
                result["status"] = "INCOMPLETE"
                print("ARCHIVE_FAILURE: " + str(exc), file=sys.stderr)
    return 0 if result["status"] == "PO_REVIEW_PENDING" else 2


if __name__ == "__main__":
    raise SystemExit(main())