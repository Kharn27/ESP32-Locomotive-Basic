#!/usr/bin/env python3
"""HW4-ESC-BREAK-B1: recette PO automatisée sur CYD, version figée PR #387.

Réutilise PO-AUTO-01 (Session, CRC/PNG, provenance, ZIP, SHA256SUMS),
sans modifier le firmware ni les outils du dépôt.

CAPTURE: HOME (ESC[H) depuis E3, par le routeur UART existant.
!SHOT est un secours HOST au prompt, non utilisé par ce script.
Aucune capture HOME/!SHOT pendant RUN/PAUSED.
Les PNG automatiques prouvent la VRAM logique AVANT RUN et APRES BREAK ;
une photo du TFT pendant PAUSED reste une observation physique PO.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time

EXPECTED_HEAD = None  # --expected-head doit être explicitement autorisé
EXPECTED_MAIN = "91cc6b0856cfb4a05fd3ef3f5e5a2bb6aa523084"
SCENARIOS = ("SILENT_ESC", "VISIBLE_AB", "HOST_BREAK_PAUSED", "HOST_BREAK_LF")
EXPECTED_PNG = 6
VISUAL_HOLD_SECONDS = 15.0  # Host timing only, never firmware ESC idle threshold
VISUAL_PROGRESS_SECONDS = 6.0
# The opt-in visual program changes displayed digits between repaint quanta.
DEFAULT_AB_LINES = ('10 PRINT "A":GOTO 20', '20 PRINT "B":GOTO 10')
VISUAL_COUNTER_LINES = ('10 A%=A%+1:PRINT A%:GOTO 20', '20 PRINT "B":GOTO 10')
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def parse_fields(line: str, marker: str) -> dict[str, str]:
    if marker not in line:
        raise AssertionError("MISSING_MARKER: " + marker)
    out = {}
    for part in line.split(marker, 1)[1].split():
        if "=" in part:
            key, val = part.split("=", 1)
            if key in out or not val:
                raise AssertionError("MALFORMED_FIELD: " + key)
            out[key] = val
    return out


def check_terminal(terminal: str, head: str, source: str) -> dict[str, str]:
    f = parse_fields(terminal, "HW4-RUN-B RUN_TERMINAL ")
    required = ("sha", "state", "break_source", "stop_calls",
                "steps", "program_preserved")
    if not all(k in f for k in required):
        raise AssertionError("RUN_TERMINAL_FIELDS_MISSING")
    if (f["sha"] != head or f["state"] != "4"
            or f["break_source"] != source
            or f["stop_calls"] != "1"
            or f["program_preserved"] != "1"
            or not f["steps"].isdigit() or int(f["steps"]) <= 0):
        raise AssertionError("RUN_TERMINAL_MISMATCH: " + str(f))
    return f


def self_test() -> None:
    global EXPECTED_HEAD
    EXPECTED_HEAD = "a" * 40  # synthetic; self-test only
    line = ("HW4-RUN-B RUN_TERMINAL state=4 steps=512 "
            "break_source=CPC_ESC_DOUBLE stop_calls=1 "
            f"sha={EXPECTED_HEAD} program_preserved=1")
    assert check_terminal(line, EXPECTED_HEAD, "CPC_ESC_DOUBLE")["steps"] == "512"
    for replacement in ("state=5", "stop_calls=2", "break_source=UART_CR",
                        "program_preserved=0"):
        original = replacement.split("=")[0]
        source = re.search(r"\b" + original + r"=[^\s]+", line).group(0)
        changed = line.replace(source, replacement)
        try:
            check_terminal(changed, EXPECTED_HEAD, "CPC_ESC_DOUBLE")
        except AssertionError:
            pass
        else:
            raise AssertionError("NEGATIVE_ACCEPTED: " + replacement)
    print("HW4-ESC-B1 SELF_TEST PASS; aucun CYD utilisé")


def setup_imports():
    # Le script peut être copié dans tools/ OU exécuté depuis un autre dossier.
    p = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                       text=True, capture_output=True)
    if p.returncode:
        raise RuntimeError("Exécuter depuis la racine du checkout Git")
    root = Path(p.stdout.strip()).resolve()
    if not (root / "tools/cyd_po_campaign.py").is_file():
        raise RuntimeError("PO-AUTO-01 absent: tools/cyd_po_campaign.py")
    sys.path.insert(0, str(root / "tools"))
    import cyd_po_campaign as po
    if po.ROOT.resolve() != root:
        raise RuntimeError("PO-AUTO-01 vient d'un autre dépôt")
    return root, po


class Driver:
    def __init__(self, po, session, events, result, command_timeout: float,
                 visual_observation: bool = False):
        self.po, self.s, self.events, self.result = po, session, events, result
        self.timeout = command_timeout
        self.active = None
        self.visual_observation = visual_observation

    def event(self, step: str, state: str, detail: str = ""):
        self.events.log(step, state, detail=detail, scenario=self.active)

    def wait(self, marker: str, timeout: float | None = None) -> str:
        return self.s.wait(marker, timeout if timeout is not None else self.timeout)

    def send_raw(self, data: bytes, purpose: str):
        if not data:
            raise self.po.Incomplete("EMPTY_RAW_TX")
        record = {"time_utc": self.po.utc(),
                  "monotonic_ns": time.monotonic_ns(), "purpose": purpose,
                  "hex": data.hex(), "status": "attempt"}
        self.s.tx.write(json.dumps(record, sort_keys=True) + "\n")
        self.s.tx.flush()
        self.s.tx_count += 1
        sent = self.s.port.write(data)
        self.s.port.flush()
        self.po.require(sent == len(data), "SHORT_RAW_TX")
        self.event("TX", "SENT", purpose + " hex=" + data.hex())

    def observe(self, seconds: float, forbidden: tuple[str, ...] = (),
                want: str | None = None) -> bool:
        # Read actual complete UART lines without resetting the RX buffer.
        found = False
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            self.s.pump()
            while self.s.lines:
                raw = self.s.lines.popleft()
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                self.s.inspect(raw, line)
                for marker in forbidden:
                    self.po.require(marker not in line,
                                    "FORBIDDEN_DURING_OBSERVATION: " + marker)
                if want and want in line:
                    found = True
        return found

    def observe_progress(self, seconds: float, paused_steps: int) -> int:
        """Monitor real post-RESUME YIELD for a full 6s via sole UART owner."""
        deadline = time.monotonic() + seconds
        latest = paused_steps
        while time.monotonic() < deadline:
            self.s.pump()
            while self.s.lines:
                raw = self.s.lines.popleft()
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                self.s.inspect(raw, line)  # reboot, fatal, DMA, LCD
                self.po.require("HW4-RUN-B RUN_TERMINAL " not in line and
                                "HW4-ESC-BREAK-B1 ESC_TRANSITION " not in line and
                                "HW4-C2 UART_LINE " not in line,
                                "UNEXPECTED_RUN_TRANSITION_DURING_RESUME")
                if "HW4-RUN-B YIELD " in line:
                    f = parse_fields(line, "HW4-RUN-B YIELD ")
                    self.po.require(f.get("sha") == EXPECTED_HEAD and
                                    f.get("steps", "").isdigit(),
                                    "VISIBLE_PROGRESS_YIELD_INVALID")
                    steps = int(f["steps"])
                    self.po.require(steps >= latest, "VISIBLE_STEPS_REGRESSED")
                    latest = steps
        self.po.require(latest > paused_steps, "VISIBLE_NO_PROGRESS_AFTER_RESUME")
        self.check("VISIBLE_PROGRESS_AFTER_RESUME",
                   f"steps={paused_steps}->{latest} over {seconds}s")
        return latest

    def command(self, cmd: str, transition: str):
        self.s.submit(cmd, transition)
        self.event("BASIC", "ACK", cmd)

    def load(self, cid: str, numbered_lines: tuple[str, ...]):
        self.active = cid
        self.result["scenarios"].append({
            "id": cid, "status": "INCOMPLETE",
            "lines": list(numbered_lines), "checks": [],
            "photos_during_pause": "MANUAL_PO_VISUAL_REQUIRED"})
        self.event("CASE", "START", cid)
        self.command("NEW", "NEW_RETURN")
        for line in numbered_lines:
            self.po.require(len(line.encode("ascii")) <= 32, "BASIC_LINE_TOO_LONG")
            self.command(line, "NUMBERED_STORED")
        self.command("LIST", "LIST_RETURN")

    def check(self, name: str, details: str):
        self.result["scenarios"][-1]["checks"].append(
            {"name": name, "status": "PASS", "details": details})
        self.event("CHECK", "PASS", name + " " + details)

    def shot(self, cid: str, stage: str):
        # HW4-SHOT-A: CTRL HOME en E3 = 0x1B 0x5B 0x48, sans CR.
        # PO-AUTO-01 Session.inspect/Watcher valide strictement la capture,
        # son identité SHA et CRC et produit le PNG réel du framebuffer logique.
        # HOME_E3 émet after_shot UNIQUEMENT, pas after_line (!SHOT/prompt).
        s = self.s
        self.po.require(not s.awaiting_shot and s.shot_metadata is None,
                        "SHOT_STATE_LEAK")
        original = set((s.folder / "screenshots").glob("*.png"))
        s.awaiting_shot = True
        self.event("SHOT", "START", f"{cid}_{stage}: HOME_E3 hex=1b5b48")
        try:
            self.send_raw(b"\x1b[H", "HOME_E3_SCREENSHOT")
            done = self.wait("HW4-SHOT-A CAPTURE_DONE ", s.shot_timeout)
            fields = parse_fields(done, "HW4-SHOT-A CAPTURE_DONE ")
            meta = s.shot_metadata
            self.po.require(meta is not None and
                            fields.get("trigger") == "HOME_E3" and
                            fields.get("id") == meta["id"] and
                            fields.get("seq") == str(meta["seq"]) and
                            fields.get("sha") == EXPECTED_HEAD and
                            not s.watcher.active,
                            "HOME_CAPTURE_DONE_MISMATCH")
            # Contrairement à !SHOT, HOME ne soumet pas une ligne BASIC :
            # pas de READY_POLICY, INPUT_READY ni stage=after_line après HOME.
            # La ligne DEVICE_MEMORY stage=after_shot est réellement exigée.
            deadline = time.monotonic() + s.shot_timeout
            expected = ("heap8_free", "heap8_largest", "heap8_min",
                        "stack_margin_bytes", "dma_transfers", "dma_timeouts",
                        "dma_fault", "lcd_error")
            while True:
                line = s.next_line(deadline)
                if "HW4-C2 DEVICE_MEMORY stage=" in line:
                    match = self.po.MEMORY.fullmatch(line)
                    self.po.require(match is not None and
                                    match.group(1) == "after_shot",
                                    "HOME_POST_SHOT_MEMORY_INVALID")
                    mem = self.po.kv(match.group(2))
                    self.po.require(all(k in mem for k in expected) and
                                    all(mem[k].isdecimal() for k in expected[:-1]) and
                                    mem["lcd_error"] == "ESP_OK",
                                    "HOME_POST_SHOT_MEMORY_INCOMPLETE")
                    break
                self.po.require(not ("HW4-SHOT-A CAPTURE_" in line or
                                     "HW4-C2 UART_LINE " in line or
                                     "HW4-READY-A READY_POLICY " in line),
                                "HOME_UNEXPECTED_UART_TRANSITION")
            self.po.require(s.memory and s.memory[-1]["stage"] == "after_shot",
                            "HOME_MEMORY_NOT_RECORDED")
            new = set((s.folder / "screenshots").glob("*.png")) - original
            self.po.require(len(new) == 1 and s.watcher.bad == 0,
                            "HOME_PNG_COUNT_OR_CRC_INVALID")
            src = next(iter(new))
            name = f"{cid}_{stage}.png"
            dst = s.folder / "screenshots" / name
            self.po.require(not dst.exists(), "REFUSE_SHOT_OVERWRITE")
            src.rename(dst)
            rec = {"scenario": cid, "stage": stage,
                   "id": meta["id"], "seq": meta["seq"], "sha": meta["sha"],
                   "orientation": meta["orient"],
                   "png": "screenshots/" + name,
                   "png_sha256": self.po.sha256(dst),
                   "status": "LOGICAL_VRAM_VERIFIED", "trigger": "HOME_E3"}
            s.shots.append(rec)
            self.event("SHOT", "CRC_OK", rec["png"] + " sha256=" + rec["png_sha256"])
            self.check("SHOT_" + stage, "HOME_E3 LOGICAL_VRAM_VERIFIED " + rec["png"])
        finally:
            s.awaiting_shot = False
            s.shot_metadata = None

    def run(self):
        self.s.emit("RUN")
        echo = self.wait("HW4-C2 UART_LINE ")
        m = self.po.UART_LINE.search(echo)
        self.po.require(m is not None and int(m.group(1)) == 3
                        and m.group(2) == "52554e", "RUN_UART_ECHO_WRONG")
        start = parse_fields(self.wait("HW4-RUN-B RUN_START "), "HW4-RUN-B RUN_START ")
        self.po.require(start.get("sha") == EXPECTED_HEAD and
                        start.get("budget") == "none", "RUN_START_WRONG_SHA")
        self.check("RUN_STARTED", "sha=" + EXPECTED_HEAD)

    def first_yield(self, seconds: float = 45) -> int:
        text = self.wait("HW4-RUN-B YIELD ", seconds)
        f = parse_fields(text, "HW4-RUN-B YIELD ")
        self.po.require(f.get("sha") == EXPECTED_HEAD and
                        f.get("steps", "").isdigit() and int(f["steps"]) > 0,
                        "YIELD_INVALID")
        return int(f["steps"])

    def transition(self, action: str) -> int:
        line = self.wait("HW4-ESC-BREAK-B1 ESC_TRANSITION action=" + action + " ")
        f = parse_fields(line, "HW4-ESC-BREAK-B1 ESC_TRANSITION ")
        self.po.require(f.get("action") == action and
                        f.get("sha") == EXPECTED_HEAD and
                        f.get("steps", "").isdigit(), "ESC_TRANSITION_INVALID")
        steps = int(f["steps"])
        self.check("ESC_" + action, "steps=" + str(steps))
        return steps

    def pause(self, *, seconds: float = 1.1, visual_label: str | None = None) -> int:
        self.send_raw(b"\x1b", "CPC_ESC_ISOLATED")
        steps = self.transition("PAUSE")
        if visual_label is not None:
            self.event("VISUAL", visual_label,
                       f"UART_CONFIRMATION steps={steps}; pause {seconds:.0f}s. "
                       "PO: dernier NOMBRE fige, 2 photos TFT espacees; "
                       "MANUAL_PO_VISUAL_PENDING")
        self.observe(seconds, forbidden=("HW4-RUN-B YIELD ",
                                         "HW4-RUN-B RUN_TERMINAL ",
                                         "HW4-ESC-BREAK-B1 ESC_TRANSITION "))
        self.check("PAUSED_STABLE",
                   f"steps={steps}; no subsequent YIELD/TERMINAL for {seconds}s")
        if visual_label is not None:
            self.event("VISUAL", "PAUSE_UART_STABLE",
                       f"steps={steps}; duration={seconds:.0f}s; "
                       "aucun YIELD/TERMINAL/ESC_TRANSITION; TFT NON_VERIFIE")
        return steps

    def resume(self, paused_steps: int) -> None:
        self.send_raw(b"x", "RESUME_PRINTABLE_X")
        steps = self.transition("RESUME")
        self.po.require(steps == paused_steps, "STEP_ADVANCED_DURING_PAUSE")
        self.check("RESUME_SAME_STEP", f"steps={steps}")

    def negatives(self):
        # Distinct UART writes, not the terminal keyboard's cooked ESC.
        for name, chunks in (
            ("ARROW_LEFT_FRAGMENTED", (b"\x1b", b"[", b"D")),
            ("HOME_CSI", (b"\x1b[1~",)),
            ("DELETE_CSI", (b"\x1b[3~",)),
            ("CSI_OVERSIZE", (b"\x1b[" + b"1" * 24 + b"D",)),
            ("CTRL_C_NOT_ESC", (b"\x03",)),
        ):
            for c in chunks:
                self.send_raw(c, name)
                # Fragments are deliberately <50 ms apart, not a CPC timing claim.
                if len(chunks) > 1:
                    time.sleep(0.005)
            self.observe(0.18, forbidden=("HW4-ESC-BREAK-B1 ESC_TRANSITION ",
                                          "HW4-RUN-B RUN_TERMINAL "))
            self.check("NEG_" + name, "no PAUSE/RESUME/BREAK observed")

    def break_cpc(self, paused_steps: int, valid_lines: set[int]) -> None:
        self.send_raw(b"\x1b", "CPC_ESC_SECOND_WHILE_PAUSED")
        line = self.wait("HW4-ESC-BREAK-B1 CPC_BREAK ")
        b = parse_fields(line, "HW4-ESC-BREAK-B1 CPC_BREAK ")
        self.po.require(b.get("sha") == EXPECTED_HEAD and
                        b.get("stop_calls") == "1" and
                        b.get("line_source") == "BSR_COMMITTED_STATEMENT" and
                        b.get("steps") == str(paused_steps) and
                        b.get("line", "").isdigit() and
                        int(b["line"]) in valid_lines, "CPC_BREAK_ORIGIN_INVALID")
        term = check_terminal(self.wait("HW4-RUN-B RUN_TERMINAL "),
                              EXPECTED_HEAD, "CPC_ESC_DOUBLE")
        self.po.require(term["steps"] == str(paused_steps),
                        "STEP_AFTER_CPC_BREAK")
        self.check("DOUBLE_ESC_BREAK", f"line={b['line']} stop_calls=1 steps={paused_steps}")
        self.finish_run()

    def break_host(self, payloads: tuple[bytes, ...], source: str) -> None:
        for chunk in payloads:
            self.send_raw(chunk, "HOST_BREAK_FRAGMENT")
            if chunk != payloads[-1]:
                time.sleep(0.05)
        term = check_terminal(self.wait("HW4-RUN-B RUN_TERMINAL "),
                              EXPECTED_HEAD, source)
        self.check("HOST_BREAK", f"source={source} steps={term['steps']} stop_calls=1")
        self.finish_run()

    def finish_run(self):
        ready = self.wait("HW4-READY-A READY_POLICY ")
        f = parse_fields(ready, "HW4-READY-A READY_POLICY ")
        self.po.require(f.get("transition") == "RUN_RETURN" and
                        f.get("emitted") == "1", "NOT_SINGLE_RUN_READY")
        self.wait("HW4-C3-B2 INPUT_READY ")
        self.po.require(any(m["stage"] == "run_terminal" for m in self.s.memory),
                        "NO_RUN_TERMINAL_MEMORY")
        self.check("READY_RETURN", "RUN_RETURN emitted=1 and INPUT_READY")

    def finish_case(self, cid: str, *, capture: bool = True):
        self.command("LIST", "LIST_RETURN")
        if capture:
            self.shot(cid, "AFTER_BREAK")
        case = self.result["scenarios"][-1]
        self.po.require(case["id"] == cid, "CASE_ORDER_DRIFT")
        case["status"] = "AUTO_UART_CRC_CANDIDATE"
        self.event("CASE", "END", cid + " AUTO_UART_CRC_CANDIDATE")
        self.active = None

    def run_cases(self):
        cid = "SILENT_ESC"
        self.load(cid, ("10 GOTO 10",))
        self.shot(cid, "BEFORE_RUN")
        self.run()
        y = self.first_yield()
        self.check("SILENT_LOOP_PROGRESS", f"YIELD steps={y}")
        self.negatives()
        pause1 = self.pause()
        self.resume(pause1)
        # Require scheduler progress, then pause and verify no advance.
        progressed = self.first_yield()
        self.po.require(progressed > pause1, "NO_RUN_PROGRESS_AFTER_RESUME")
        pause2 = self.pause()
        self.po.require(pause2 > pause1, "NO_STEP_GROWTH_AFTER_RESUME")
        self.break_cpc(pause2, {10})
        self.finish_case(cid)

        cid = "VISIBLE_AB"
        self.load(cid, VISUAL_COUNTER_LINES if self.visual_observation else DEFAULT_AB_LINES)
        self.shot(cid, "BEFORE_RUN")
        self.run()
        if self.visual_observation:
            self.event("VISUAL", "RUN_VISIBLE",
                       "RUN_START confirme UART; voir les NOMBRES croitre avec B sur le TFT; "
                       "MANUAL_PO_VISUAL_PENDING")
        y = self.first_yield()
        self.check("VISIBLE_LOOP_PROGRESS", f"YIELD steps={y}")
        if self.visual_observation:
            pause1 = self.pause(seconds=VISUAL_HOLD_SECONDS,
                                visual_label="PAUSE_1_CONFIRMED")
            self.resume(pause1)
            self.event("VISUAL", "RESUME_CONFIRMED",
                       f"UART_CONFIRMATION steps={pause1}; "
                       f"regarder les NOMBRES augmenter pendant {VISUAL_PROGRESS_SECONDS:.0f}s; "
                       "TFT NON_VERIFIE")
            progressed = self.observe_progress(VISUAL_PROGRESS_SECONDS, pause1)
            self.event("VISUAL", "RESUME_PROGRESS_CONFIRMED",
                       f"UART_YIELD steps={pause1}->{progressed}; TFT NON_VERIFIE")
            pause2 = self.pause(seconds=VISUAL_HOLD_SECONDS,
                                visual_label="PAUSE_2_CONFIRMED")
        else:
            pause1 = self.pause(seconds=1.5)
            self.resume(pause1)
            progressed = self.first_yield(60)
            self.po.require(progressed > pause1, "VISIBLE_NO_PROGRESS_AFTER_RESUME")
            pause2 = self.pause(seconds=1.0)
        self.po.require(pause2 > pause1, "VISIBLE_NO_STEP_GROWTH")
        self.break_cpc(pause2, {10, 20})
        if self.visual_observation:
            self.event("VISUAL", "BREAK_CONFIRMED",
                       f"UART_CPC_BREAK steps={pause2}; Ready unique confirme; "
                       "regarder Break in 10/20 et Ready; MANUAL_PO_VISUAL_PENDING")
        self.finish_case(cid)

        cid = "HOST_BREAK_PAUSED"
        self.load(cid, ("10 GOTO 10",))
        self.run()
        self.first_yield()
        self.pause(seconds=0.5)
        self.break_host((b"!Br", b"eAk\r\n"), "UART_CR")
        self.finish_case(cid)

        cid = "HOST_BREAK_LF"
        self.load(cid, ("10 GOTO 10",))
        self.run()
        self.first_yield()
        self.break_host((b"!BREAK\n",), "UART_LF")
        self.finish_case(cid)


def write_report(folder: Path, result: dict) -> None:
    lines = [
        "# Rapport HW4-ESC-BREAK-B1 — réception CYD automatisée",
        "",
        f"**Statut hôte UART/CRC : {result['status']}**",
        "",
        f"- HEAD exigé : `{EXPECTED_HEAD}`",
        f"- HEAD observé : `{result.get('head', 'NON_VÉRIFIÉ')}`",
        f"- Mode : `{result.get('mode', 'NON_VÉRIFIÉ')}`",
        "- Cible : ESP32 CYD / ESP-IDF v5.5.6 / CONSOLE / SPI40 (demande)",
        "- Source : événements UART réels + PNG VRAM logique, CRC exigé",
        "- Le PNG n'est PAS une lecture des pixels physiques du TFT.",
        "- `!SHOT` n'est PAS accepté pendant RUN ou PAUSED.",
        "",
        "## Scénarios contrôlés",
        "",
        "| Scénario | Statut hôte | Contrôles PASS |",
        "|---|---|---:|",
    ]
    for c in result["scenarios"]:
        lines.append(f"| {c['id']} | {c['status']} | {len(c.get('checks', []))} |")
    lines += ["", "## Détail des assertions réellement vérifiées", ""]
    for c in result["scenarios"]:
        lines.append("### " + c["id"] + " — " + c["status"])
        lines.append("")
        for check in c.get("checks", []):
            lines.append("- [x] **" + check["name"] + "** : " + check["details"])
        if c["status"] != "AUTO_UART_CRC_CANDIDATE":
            lines.append("- [ ] Scénario interrompu ou incomplet")
        lines.append("")
    lines += ["## Captures logiques avec empreintes", ""]
    for s in result.get("shots", []):
        lines.append(f"- `{s['png']}` — SHA-256 `{s['png_sha256']}` — `LOGICAL_VRAM_VERIFIED`")
    lines += ["", "## Diagnostics mémoire réellement reçus", "",
              "| Stage firmware | Heap libre | Plus grand bloc | Pile | DMA timeouts | DMA fault | LCD |",
              "|---|---:|---:|---:|---:|---:|---|"]
    for m in result.get("memory", []):
        lines.append("| " + " | ".join(
            str(m.get(k, "MANQUANT")) for k in
            ("stage", "heap8_free", "heap8_largest", "stack_margin_bytes",
             "dma_timeouts", "dma_fault", "lcd_error")) + " |")
    lines += ["", "## Réception physique PO obligatoire", "",
              "- [ ] TFT photographié pendant RUN, PAUSED et BROKEN (2 photos PAUSED espacées)",
              "- [ ] En mode visuel, dernier NOMBRE fige pendant PAUSE 15s",
               "- [ ] Nombres croissants pendant RUN et RESUME 6s (B intercalaire)",
              "- [ ] Touche ESC / reprise x / double ESC correspond aux octets TX enregistrés",
              "- [ ] LCD réel : orientation, couleurs, curseur comparés aux PNG logiques",
              "- [ ] Tactile fonctionnel, aucune anomalie FreeRTOS/heap/stack/DMA",
              "- [ ] Cas ANSI fragmentés conformes aux comportements du terminal réel",
              "- [ ] Pas de faux `Break in N`, un seul Ready, LIST intact",
              "",
              "Mode observation longue demande : " + str(result.get("visual_observation", False)),
               "MANUAL_PO_VISUAL_PENDING (aucun auto-PASS de la dalle)", "",
               "Observations et photos PO :", "",
              "*(à compléter — aucune qualification ON_DEVICE_PASS automatique)*", "",
              "## Anomalies et limites", ""]
    lines += [f"- {error}" for error in result.get("errors", [])] or ["- Aucune anomalie hôte signalée"]
    lines += ["", "## Archives",
              "",
              "- `uart.raw.log` : RX octets exacts (aucun message hôte mélangé)",
              "- `uart.tx.jsonl` : TX hex et horodatages",
              "- `host-events.jsonl` : progression ordonnée",
              "- `results.json`, `manifest.json` : états structurés",
              "- `screenshots/` : PNG CRC-validés",
              "- `SHA256SUMS` et ZIP : preuves vérifiables",
              ""]
    (folder / "rapport_B1_PO.md").write_text("\n".join(lines), encoding="utf-8")


def run(argv=None) -> int:
    global EXPECTED_HEAD
    ap = argparse.ArgumentParser(description=__doc__)
    modes = ap.add_mutually_exclusive_group()
    modes.add_argument("--flash", action="store_true",
                       help="build+flash une fois, puis boot attesté")
    modes.add_argument("--existing-firmware", action="store_true",
                       help="boot attesté, ne flashe pas")
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--expected-head", metavar="FULL_SHA",
                    help="SHA complet autorisé par le GO FLASH Pilotage; obligatoire")
    ap.add_argument("--manual-reset", action="store_true")
    ap.add_argument("--output-root", type=Path)
    ap.add_argument("--boot-timeout", type=float, default=70)
    ap.add_argument("--command-timeout", type=float, default=70)
    ap.add_argument("--shot-timeout", type=float, default=160)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--visual-observation", action="store_true",
                    help=("VISIBLE_AB seulement: compteur croissant, PAUSE 15s x2 et RESUME 6s; "
                          "photos TFT manuelles, aucun second lecteur UART"))
    args = ap.parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    if args.expected_head is None or SHA_RE.fullmatch(args.expected_head) is None:
        ap.error("--expected-head <SHA-40-hex> obligatoire; aucun GO implicite")
    EXPECTED_HEAD = args.expected_head
    if not args.dry_run and not (args.flash or args.existing_firmware):
        ap.error("Indiquer explicitement --flash ou --existing-firmware")
    if args.visual_observation:
        print("[VISUAL] COMPTEUR_CROISSANT: NOMBRES croissent pendant RUN/RESUME, figes en PAUSE 15s x2, RESUME 6s; "
              "UART/CRC automatiques, TFT non valide automatiquement", flush=True)
    if min(args.boot_timeout, args.command_timeout, args.shot_timeout) <= 0:
        ap.error("Délais strictement positifs")
    root, po = setup_imports()
    head = po.identity()
    po.require(SHA_RE.fullmatch(head) is not None and head == EXPECTED_HEAD,
               f"REFUSE_HEAD: exact {EXPECTED_HEAD} requis, obtenu {head}")
    if args.dry_run:
        print(json.dumps({"status": "DRY_RUN_ONLY_NO_DEVICE", "head": head,
                          "scenarios": list(SCENARIOS), "expected_png": EXPECTED_PNG,
                          "note": "HOME E3 (ESC[H); PNG avant RUN/après BREAK uniquement",
                           "visual_observation": args.visual_observation,
                           "visual_hold_seconds": VISUAL_HOLD_SECONDS if args.visual_observation else None,
                           "visual_resume_seconds": VISUAL_PROGRESS_SECONDS if args.visual_observation else None,
                           "manual_visual_status": "MANUAL_PO_VISUAL_PENDING",
                            "visible_basic_lines": list(VISUAL_COUNTER_LINES if args.visual_observation
                                                        else DEFAULT_AB_LINES)},
                         indent=2, ensure_ascii=False))
        return 0
    folder = None
    session = None
    events = None
    phase = "INIT"
    root_out = args.output_root or (root / "cyd-campaigns")
    result = {
        "schema": 1, "campaign": "HW4_ESC_BREAK_B1_PO_AUTO", "status": "INCOMPLETE",
        "classification": "AUTO_UART_CRC", "manual": "MANUAL_PO_VISUAL_PENDING",
        "visual_observation": args.visual_observation,
        "visual_hold_seconds": VISUAL_HOLD_SECONDS if args.visual_observation else None,
        "visual_resume_seconds": VISUAL_PROGRESS_SECONDS if args.visual_observation else None,
        "visible_basic_lines": list(VISUAL_COUNTER_LINES if args.visual_observation
                                    else DEFAULT_AB_LINES),
        "head": head, "expected_main": EXPECTED_MAIN, "port": args.port,
        "mode": "flash" if args.flash else "existing_firmware",
        "expected_png_count": EXPECTED_PNG, "shots": [], "scenarios": [],
        "memory": [], "errors": [], "started_utc": po.utc(),
        "runner_sha256": po.sha256(Path(__file__)),
        "scenario_sources": [{"id": c,
                              "path": Path(__file__).name,
                              "sha256": po.sha256(Path(__file__))}
                             for c in SCENARIOS]
    }
    try:
        folder = po.make_folder(root_out, "esc_break_b1_po", head)
        po.write_json(folder / "manifest.json", {
            "schema": 1, "campaign": result["campaign"], "head": head,
            "source_branch": "feat/hw4-esc-break-b1-console",
            "scenarios": list(SCENARIOS), "expected_png_count": EXPECTED_PNG,
            "runner_sha256": result["runner_sha256"],
            "visual_observation": args.visual_observation,
            "visual_hold_seconds": result["visual_hold_seconds"],
            "visual_resume_seconds": result["visual_resume_seconds"],
            "visible_basic_lines": result["visible_basic_lines"],
            "manual_visual_status": "MANUAL_PO_VISUAL_PENDING",
            "scope": "RUN_ESC_PAUSE_RESUME_DOUBLE_ESC_AND_HOST_FALLBACK",
            "limitations": ["HOME_E3_SHOT_ONLY_WHEN_NOT_RUNNING",
                            "NO_SHOT_DURING_RUN_OR_PAUSED",
                            "LOGICAL_VRAM_IS_NOT_PHYSICAL_TFT"],
            "started_utc": result["started_utc"]})
        events = po.HostEvents(folder)
        events.log("BEGIN", "VERIFIED_SOURCE", f"SHA={head}")
        # Refuser un moniteur concurrent / pyserial absent AVANT le flash.
        phase = "PREFLIGHT"
        po.collision_guard(args.port)
        try:
            import serial
        except ImportError as exc:
            raise po.Incomplete("PYSERIAL_MISSING: python3 -m pip install pyserial") from exc
        if args.flash:
            phase = "BUILD_FLASH"
            fw = po.run_idf(folder, head, args.port, progress=events.log)
            cache = (folder / "_idf_build" / "CMakeCache.txt").read_text()
            po.require("CYD_LCD_SPI_HZ:STRING=40000000" in cache and
                       "CYD_LCD_SPI20_OPT_IN:BOOL=OFF" in cache,
                       "BUILD_NOT_CONSOLE_SPI40")
        else:
            events.log("BUILD", "SKIP", "existing firmware, boot proof required")
            events.log("FLASH", "SKIP", "existing firmware, boot proof required")
            fw = {"mode": "existing_firmware"}
        result["firmware"] = fw
        phase = "UART"
        po.require(po.identity() == head, "SOURCE_CHANGED_AFTER_BUILD")
        po.collision_guard(args.port)
        port = serial.Serial(port=None, baudrate=115200, timeout=0.10,
                             write_timeout=5, exclusive=True)
        port.dtr = False
        port.rts = False
        port.port = args.port

        class Spi40Session(po.Session):
            def inspect(self, raw: bytes, line: str) -> None:
                if "HW4-DISP-PROFILE BOOT " in line:
                    fields = parse_fields(line, "HW4-DISP-PROFILE BOOT ")
                    po.require(fields.get("sha") == head and
                               fields.get("spi_request_hz") == "40000000" and
                               fields.get("variant") == "SPI40",
                               "BOOT_NOT_CONSOLE_SPI40")
                super().inspect(raw, line)

        with port:
            if not port.is_open:
                port.open()
            session = Spi40Session(port, folder, head, fw.get("binary_version"),
                                   args.boot_timeout, args.command_timeout,
                                   args.shot_timeout)
            events.log("UART", "OPEN", f"exclusive=1 port={args.port} baud=115200")
            session.arm_boot()
            phase = "BOOT"
            if args.manual_reset:
                events.log("RESET", "MANUAL_WAIT", "Appuyer une seule fois sur RESET")
            else:
                events.log("RESET", "AUTO_START", "RTS=EN, DTR=GPIO0 released")
                po.auto_reset(port)
                events.log("RESET", "AUTO_DONE", "nouveau boot attendu")
            version = session.boot()
            result["observed_app_version"] = version
            events.log("BOOT", "VERIFIED", f"HEAD={head} version={version}")
            phase = "SCENARIOS"
            driver = Driver(po, session, events, result, args.command_timeout,
                            visual_observation=args.visual_observation)
            driver.run_cases()
            phase = "VERIFY"
            po.require(po.identity() == head, "SOURCE_CHANGED_DURING_CAMPAIGN")
            po.require(len(session.shots) == EXPECTED_PNG,
                       f"PNG_COUNT_MISMATCH: {len(session.shots)}/{EXPECTED_PNG}")
            po.require(session.watcher.bad == 0 and not session.watcher.active,
                       "SHOT_INVALID_OR_INCOMPLETE")
            po.require(all(c["status"] == "AUTO_UART_CRC_CANDIDATE"
                           for c in result["scenarios"]) and
                       len(result["scenarios"]) == len(SCENARIOS),
                       "SCENARIO_INCOMPLETE")
            result["status"] = "PO_REVIEW_PENDING"
    except (Exception, KeyboardInterrupt) as exc:
        result["status"] = "INCOMPLETE"
        reason = "INTERRUPTED_BY_OPERATOR" if isinstance(exc, KeyboardInterrupt) else str(exc)
        result["errors"].append(f"phase={phase} reason={reason}")
        if events:
            events.log(phase, "FAIL", reason)
        else:
            print("INCOMPLETE: " + reason, file=sys.stderr)
    finally:
        if session is not None:
            result["shots"] = session.shots
            result["memory"] = session.memory
            result["rx_bytes"] = session.rx_bytes
            result["tx_count"] = session.tx_count
            session.close()
        if folder is not None:
            result["completed_utc"] = po.utc()
            if events:
                events.log("ARCHIVE", "START", f"folder={folder}")
            try:
                write_report(folder, result)
                archive = po.finalize(folder, result, events=events)
                print(f"[SUMMARY] {result['status']} ZIP={archive} "
                      f"SHA256={po.sha256(archive)}")
            except Exception as exc:
                result["status"] = "INCOMPLETE"
                print("ARCHIVE_FAILED: " + str(exc), file=sys.stderr)
            if events:
                events.close()
    return 0 if result["status"] == "PO_REVIEW_PENDING" else 2


if __name__ == "__main__":
    raise SystemExit(run())