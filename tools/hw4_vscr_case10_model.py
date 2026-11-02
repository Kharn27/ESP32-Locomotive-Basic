#!/usr/bin/env python3
"""HW4 A1-P0: hypothetical ILI9341 scan-line model, NEVER hardware authority.

A model of the controller's 320-line VSCR space with a *hypothesized*
240-line contiguous visible slice, reversed in panel Y for case 10.
Neither the visible slice nor the VSCR axis is proven on the CYD.
No IO, DMA, LCD driver import, or extra framebuffer in firmware.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

SCAN_LINES = 320  # ILI9341 datasheet VSCRDEF sum; NOT TFT visible height
WIDTH = 320
HEIGHT = 240
TOP = 20
VIEW = 200
BOTTOM = 20
ROW = 8


class ModelReject(ValueError):
    """Reject a configuration or unsafe operation without making a write."""


@dataclass(frozen=True)
class Candidate:
    # Both positions are unverified hypotheses, not actual GRAM readbacks.
    visible_start: int | None = None
    case: int = 10
    swap_xy: bool = False
    mirror_x: bool = False
    mirror_y: bool = True
    scan_axis_y: bool | None = None  # UNKNOWN is deliberately rejected
    top: int = TOP
    height: int = VIEW
    bottom: int = BOTTOM
    width: int = WIDTH
    visible_height: int = HEIGHT


@dataclass(frozen=True)
class Assessment:
    status: str
    reason: str
    fallback: bool = True  # the software model can NEVER activate hardware
    tfa: int | None = None
    vsa: int | None = None
    bfa: int | None = None


def assess(c: Candidate, *, dma_ok: bool = True, lcd_fault: bool = False,
           capabilities_known: bool = False) -> Assessment:
    """Safety gate. A plausible model is still CONTROLLER_UNVERIFIED."""
    def reject(why: str) -> Assessment:
        return Assessment("MODEL_NOT_FEASIBLE", why)

    if not dma_ok or lcd_fault:
        return reject("DMA_FAIL_STOP_OR_STICKY_LCD_FAULT")
    if (c.case, c.swap_xy, c.mirror_x, c.mirror_y) != (10, False, False, True):
        return reject("CASE10_ORIENTATION_NOT_ESTABLISHED")
    if c.scan_axis_y is not True:
        return reject("VSCR_AXIS_Y_UNPROVEN_OR_MISMATCHED")
    if (c.width, c.visible_height, c.top, c.height, c.bottom) != (320, 240, 20, 200, 20):
        return reject("CPC_WINDOW_OR_MARGINS_CHANGED")
    if c.visible_start not in (0, 80):
        return reject("VISIBLE_240_OF_320_POSITION_UNPROVEN")
    tfa = c.visible_start + c.bottom  # reverse-Y: bottom physical is first in scan space
    vsa = c.height
    bfa = SCAN_LINES - tfa - vsa
    if tfa < 0 or vsa <= 0 or bfa < 0 or tfa + vsa + bfa != SCAN_LINES:
        return reject("VSCRDEF_SUM_OR_RANGE_INVALID")
    # "Known" cannot be proven by this script; even external claims need PO.
    detail = "CONDITIONAL_SCAN_AXIS_AND_VISIBLE_SLICE_ONLY"
    if not capabilities_known:
        detail += ";CONTROLLER_CAPABILITY_UNKNOWN"
    else:
        detail += ";CLAIM_NOT_INDEPENDENTLY_VERIFIED"
    return Assessment("MODEL_FEASIBLE_CONTROLLER_UNVERIFIED", detail,
                      True, tfa, vsa, bfa)


class Case10Model:
    """Independent abstract RGB *row labels*, not an RGB565 framebuffer.

    physical(Y) -> hypothetical scan row -> scroll pointer -> GRAM row.
    Pixels are deliberately reduced to immutable per-raster labels. This
    exercises permutation/writes but NOT color rendering or controller MADCTL.
    """
    def __init__(self, candidate: Candidate):
        self.plan = assess(candidate)
        if self.plan.status != "MODEL_FEASIBLE_CONTROLLER_UNVERIFIED":
            raise ModelReject(self.plan.reason)
        self.cfg = candidate
        self.gram: list[str] = [f"HIDDEN:{i}" for i in range(SCAN_LINES)]
        self.offset = 0
        self.generation = 0
        self.sticky_fault = False
        self.cursor: tuple[int, int] | None = None  # overlay; never in GRAM
        self.logical = ([f"TOP:{y}" for y in range(TOP)]
                        + [f"ROW:{y}" for y in range(VIEW)]
                        + [f"BOTTOM:{y}" for y in range(BOTTOM)])
        self._rewrite_visible()

    def _address(self, physical_y: int) -> int:
        if not 0 <= physical_y < HEIGHT:
            raise ModelReject("INVALID_PHYSICAL_ROW")
        # Explicit hypothesis: reverse visible rows (MY=1) in a 320-line scan.
        scan = self.cfg.visible_start + HEIGHT - 1 - physical_y
        assert self.plan.tfa is not None and self.plan.vsa is not None
        if self.plan.tfa <= scan < self.plan.tfa + self.plan.vsa:
            scan = self.plan.tfa + ((scan - self.plan.tfa + self.offset) % self.plan.vsa)
        return scan

    def _rewrite_visible(self) -> None:
        for y in range(HEIGHT):
            self.gram[self._address(y)] = self.logical[y]

    def physical(self) -> list[str]:
        return [self.gram[self._address(y)] for y in range(HEIGHT)]

    def shot(self) -> list[str]:
        """Like !SHOT, read logical rows, never GRAM or cursor hardware."""
        return self.logical.copy()

    def visible_with_cursor(self) -> list[str]:
        visible = self.physical()
        if self.cursor is not None:
            x, y = self.cursor
            visible[y] = f"OVERLAY:x{x}:" + visible[y]
        return visible

    def set_cursor(self, x: int, y: int) -> None:
        if not 0 <= x < WIDTH or not TOP <= y < TOP + VIEW:
            raise ModelReject("INVALID_CURSOR")
        self.cursor = (x, y)

    def write_raster(self, physical_y: int, label: str, *, generation: int | None = None) -> int:
        if self.sticky_fault:
            raise ModelReject("STICKY_FAULT_NO_RETRY")
        if generation is not None and generation != self.generation:
            raise ModelReject("STALE_DIRTY_ADDRESS_AFTER_SCROLL")
        if not TOP <= physical_y < TOP + VIEW:
            raise ModelReject("MARGIN_WRITE_FORBIDDEN")
        self.logical[physical_y] = label
        address = self._address(physical_y)
        self.gram[address] = label
        return address

    def scroll(self, direction: str, rows: int = 1, *, dma_ok: bool = True) -> int:
        if self.sticky_fault:
            raise ModelReject("STICKY_FAULT_NO_RETRY")
        if not dma_ok:
            self.sticky_fault = True
            raise ModelReject("DMA_FAILURE_LATCHED_NO_RETRY")
        if direction not in ("up", "down") or not 1 <= rows <= 25:
            raise ModelReject("INVALID_DIRECTION_OR_ROW_COUNT")
        shift = rows * ROW
        old = self.logical[TOP:TOP + VIEW]
        if direction == "up":
            self.logical[TOP:TOP + VIEW] = old[shift:] + ["PAPER"] * shift
            self.offset = (self.offset - shift) % VIEW
            exposed = range(TOP + VIEW - shift, TOP + VIEW)
        else:
            self.logical[TOP:TOP + VIEW] = ["PAPER"] * shift + old[:VIEW - shift]
            self.offset = (self.offset + shift) % VIEW
            exposed = range(TOP, TOP + shift)
        self.generation += 1
        for y in exposed:
            self.gram[self._address(y)] = self.logical[y]
        return shift * WIDTH * 2  # hypothetical payload only; no commands or other dirties

    def clear(self) -> None:
        """Hypothetical disable/!CLS/MODE transition: normalize then repaint."""
        if self.sticky_fault:
            raise ModelReject("STICKY_FAULT_NO_RETRY")
        self.offset = 0
        self.generation += 1
        self.logical[TOP:TOP + VIEW] = ["PAPER"] * VIEW
        self._rewrite_visible()

    def disable(self) -> None:
        """Restore canonical linear mapping BEFORE ordinary full repaint."""
        if self.sticky_fault:
            raise ModelReject("STICKY_FAULT_NO_RETRY")
        self.offset = 0
        self.generation += 1
        self._rewrite_visible()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visible-start", type=int, choices=(0, 80),
                        help="assumed GRAM start of 240 visible lines; omission = UNKNOWN")
    parser.add_argument("--assume-vscr-is-physical-y", action="store_true",
                        help="hypothesis only; NOT a CYD observation")
    args = parser.parse_args()
    plan = assess(Candidate(visible_start=args.visible_start,
                            scan_axis_y=True if args.assume_vscr_is_physical_y else None))
    print(json.dumps(plan.__dict__, sort_keys=True))
    # Never claim hardware can be enabled from an offline CLI.


if __name__ == "__main__":
    main()
