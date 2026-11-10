#!/usr/bin/env python3
"""HW4-LCD-F1-A: isolated conservative DMA lifetime *model*, NOT ESP-IDF.

The model is intentionally independent of the real driver, whose source SHA and
ESP-IDF API contracts are audited in docs/HW4-LCD-F1-A-sticky-dma-safety-audit.md.
No GPIO/DMA/SPI access, no automatic recovery, no hardware fault injection.
Run: python3 -m unittest discover -s tests -p 'test_hw4_lcd_f1_*.py' -v
"""
from dataclasses import dataclass
from enum import Enum, auto
import unittest


class Phase(Enum):
    UNINITIALIZED = auto()
    IDLE = auto()
    DMA_SUBMITTED = auto()
    COMPLETE = auto()
    FAULT_STICKY = auto()


class Violation(RuntimeError):
    pass


@dataclass
class LcdModel:
    """Abstract ownership; QUIESCENCE_UNPROVEN is evidence, not an IDF state."""

    phase: Phase = Phase.UNINITIALIZED
    pinned: bool = False
    semaphore_alive: bool = False
    panel_alive: bool = False
    bus_owned: bool = False
    backlight_on: bool = False
    fault: bool = False
    semaphore_credit: int = 0  # FreeRTOS binary semaphore: 0 or 1
    callback_calls: int = 0
    timeout_count: int = 0
    transfer_count: int = 0
    last_error: str = "ESP_OK"
    outstanding_unproven: bool = False
    quiescence_proven: bool = False
    attempt_count: int = 0

    def initialize(self):
        if self.phase is not Phase.UNINITIALIZED or self.fault or self.pinned:
            raise Violation("INIT_INVALID_STATE")
        self.pinned = self.semaphore_alive = self.panel_alive = self.bus_owned = True
        self.phase = Phase.IDLE

    def band(self):
        return "DRIVER_OWNED_5120_BYTES" if self.panel_alive and not self.fault else None

    def set_backlight(self, enabled):
        if not self.panel_alive or self.fault:
            raise Violation("BACKLIGHT_INVALID_STATE")
        self.backlight_on = bool(enabled)

    def begin(self):
        if self.fault or self.phase is not Phase.IDLE:
            raise Violation("SEND_INVALID_STATE")
        if not self.band():
            raise Violation("NO_VALID_BAND")
        # Production drains exactly one token with xSemaphoreTake(done, 0).
        self.semaphore_credit = 0
        self.phase = Phase.DMA_SUBMITTED
        self.outstanding_unproven = True
        self.attempt_count += 1

    def isr_done(self):
        # The production callback uses only its semaphore context, never a
        # transaction generation, and can run AFTER a waiter times out.
        if not self.semaphore_alive:
            raise Violation("ISR_TARGET_DELETED")
        self.callback_calls += 1
        self.semaphore_credit = 1  # duplicate notifications coalesce

    def complete_wait(self):
        if self.phase is not Phase.DMA_SUBMITTED:
            raise Violation("NO_WAITING_SEND")
        if self.semaphore_credit != 1:
            raise Violation("UNSIGNALED_COMPLETION")
        self.semaphore_credit = 0
        self.phase = Phase.COMPLETE
        self.outstanding_unproven = False
        self.transfer_count += 1
        self.last_error = "ESP_OK"
        # Synchronous caller returns; current transaction is complete in
        # this MODEL only. No recovery is inferred from this branch.
        self.phase = Phase.IDLE

    def _sticky(self, error):
        if self.phase is not Phase.DMA_SUBMITTED:
            raise Violation("NO_SUBMITTED_OPERATION")
        self.last_error = error
        self.fault = True
        self.backlight_on = False
        self.phase = Phase.FAULT_STICKY
        # Even an immediate submit error does not prove no queued DMA and
        # cannot authorize reuse/free/reset without separate evidence.
        self.outstanding_unproven = True

    def submit_error(self):
        self._sticky("ESP_FAIL")

    def timeout(self):
        self.timeout_count += 1
        self._sticky("ESP_ERR_TIMEOUT")

    def diagnostic(self):
        return {"initialized": self.panel_alive, "dma_fault": self.fault,
                "transfers": self.transfer_count,
                "timeouts": self.timeout_count, "last_error": self.last_error,
                "band_pinned": self.pinned, "sem_alive": self.semaphore_alive,
                "quiescence": "UNPROVEN" if not self.quiescence_proven else "PROVEN"}

    def prohibit_recovery(self, operation):
        if operation not in ("reuse", "free", "reset", "reinit", "retry"):
            raise ValueError(operation)
        if self.fault or self.outstanding_unproven or not self.quiescence_proven:
            raise Violation(operation.upper() + "_QUIESCENCE_UNPROVEN")
        # Deliberately NO implementation of recovery. Neither one late ISR
        # nor a semaphore credit supplies the required quiescence proof.
        raise Violation("NO_RECOVERY_IMPLEMENTED")

    def check(self):
        assert 0 <= self.semaphore_credit <= 1
        if self.fault:
            assert self.phase is Phase.FAULT_STICKY
            assert not self.backlight_on
            assert self.pinned and self.semaphore_alive and self.bus_owned
            assert self.band() is None
            assert not self.quiescence_proven


class TestStickyDmaModel(unittest.TestCase):
    def new(self):
        m = LcdModel()
        self.assertIsNone(m.band())
        with self.assertRaisesRegex(Violation, "BACKLIGHT_INVALID_STATE"):
            m.set_backlight(True)
        m.initialize()
        m.set_backlight(True)
        return m

    def no_recovery(self, m):
        m.check()
        for op in ("reuse", "free", "reset", "reinit", "retry"):
            with self.subTest(op=op):
                with self.assertRaisesRegex(Violation, "QUIESCENCE_UNPROVEN"):
                    m.prohibit_recovery(op)
        with self.assertRaisesRegex(Violation, "INIT_INVALID_STATE"):
            m.initialize()
        with self.assertRaisesRegex(Violation, "BACKLIGHT_INVALID_STATE"):
            m.set_backlight(True)
        with self.assertRaisesRegex(Violation, "SEND_INVALID_STATE"):
            m.begin()
        self.assertIsNone(m.band())
        self.assertTrue(m.diagnostic()["dma_fault"])
        self.assertEqual(m.diagnostic()["quiescence"], "UNPROVEN")

    def test_success_next_band_and_counters(self):
        m = self.new()
        for i in range(3):
            self.assertIsNotNone(m.band())
            m.begin()
            self.assertEqual(m.phase, Phase.DMA_SUBMITTED)
            m.isr_done()
            m.complete_wait()
            self.assertEqual(m.transfer_count, i + 1)
        self.assertEqual(m.diagnostic()["timeouts"], 0)
        self.assertFalse(m.fault)
        m.check()

    def test_success_rejects_unsignaled_completion(self):
        m = self.new()
        m.begin()
        with self.assertRaisesRegex(Violation, "UNSIGNALED_COMPLETION"):
            m.complete_wait()
        m.timeout()
        self.no_recovery(m)

    def test_submit_error_sticky_even_without_isr(self):
        m = self.new()
        m.begin()
        m.submit_error()
        self.assertEqual(m.diagnostic()["last_error"], "ESP_FAIL")
        self.assertEqual(m.transfer_count, 0)
        self.no_recovery(m)

    def test_timeout_retains_dma_and_semaphore(self):
        m = self.new()
        m.begin()
        m.timeout()
        self.assertEqual(m.diagnostic()["last_error"], "ESP_ERR_TIMEOUT")
        self.assertEqual(m.diagnostic()["timeouts"], 1)
        self.assertEqual(m.diagnostic()["transfers"], 0)
        self.no_recovery(m)

    def test_isr_late_after_timeout_not_quiescence(self):
        m = self.new()
        m.begin()
        m.timeout()
        m.isr_done()
        self.assertEqual(m.semaphore_credit, 1)
        self.assertEqual(m.callback_calls, 1)
        self.no_recovery(m)
        self.assertEqual(m.transfer_count, 0)

    def test_two_late_isr_notifications_do_not_clear_fault(self):
        m = self.new()
        m.begin()
        m.timeout()
        m.isr_done()
        m.isr_done()
        self.assertEqual(m.callback_calls, 2)
        self.assertEqual(m.semaphore_credit, 1)
        self.no_recovery(m)

    def test_isr_after_submit_error_not_assumed_impossible(self):
        m = self.new()
        m.begin()
        m.submit_error()
        m.isr_done()
        self.no_recovery(m)

    def test_spurious_stale_credit_drained_before_send(self):
        m = self.new()
        m.isr_done()
        self.assertEqual(m.semaphore_credit, 1)
        m.begin()
        self.assertEqual(m.semaphore_credit, 0)
        with self.assertRaisesRegex(Violation, "UNSIGNALED_COMPLETION"):
            m.complete_wait()
        m.timeout()
        self.no_recovery(m)

    def test_duplicate_after_success_binary_semaphore(self):
        m = self.new()
        m.begin()
        m.isr_done()
        m.complete_wait()
        m.isr_done()
        m.isr_done()
        self.assertEqual(m.semaphore_credit, 1)
        m.begin()
        self.assertEqual(m.semaphore_credit, 0)
        m.timeout()
        self.no_recovery(m)

    def test_illegal_parallel_send_no_ownership_claim(self):
        m = self.new()
        m.begin()
        with self.assertRaisesRegex(Violation, "SEND_INVALID_STATE"):
            m.begin()
        m.timeout()
        self.no_recovery(m)

    def test_cannot_promote_manual_quiescence_from_callback(self):
        m = self.new()
        m.begin()
        m.timeout()
        for _ in range(4):
            m.isr_done()
        self.assertFalse(m.quiescence_proven)
        self.no_recovery(m)


if __name__ == "__main__":
    unittest.main()
