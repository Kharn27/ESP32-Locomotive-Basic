#!/usr/bin/env python3
"""P0 #322: squash provenance allowlist regressions; no CPC files mutated."""
import hashlib
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
import j1_25_a_data_read_restore_evidence as oracle


def require(condition, tag):
    if not condition:
        raise AssertionError("J1.25-A-P1 "+tag)


def main():
    p=oracle.provenance_is_authorized
    expected=oracle.EXTERNAL_ACQUISITION_HEAD
    seal=oracle.EXTERNAL_MANIFEST_SHA256
    squash=oracle.SQUASH_INTEGRATION_SHA
    base=oracle.BASE
    dest=ROOT/"tests/fixtures/cpc6128/j1_25_a_data_read_restore"
    real=dest/"manifest.json"
    require(hashlib.sha256(real.read_bytes()).hexdigest()==seal,
            "HISTORIC_MANIFEST_UNCHANGED")
    require(oracle.ancestor(squash),"EXACT_SQUASH_NOT_IN_CURRENT_HISTORY")
    require(oracle.ancestor(base),"BASE_NOT_ANCESTOR")
    # Independently prove the *actual* post-squash situation, not a fake mock.
    require(not oracle.ancestor(expected),"HISTORIC_ACQUISITION_STILL_ANCESTOR")
    require(p(base,False),"NORMAL_ANCESTOR_REJECTED")
    require(not p(expected,False),"UNSEALED_SQUASH_BYPASS")
    require(p(expected,True,seal,expected),"EXACT_SQUASH_SEAL_REJECTED")
    require(not p(expected,True,"0"*64,expected),"FAKE_SEAL_ACCEPTED")
    require(not p(expected,True,seal,"0"*40),"FAKE_EXPECTED_HEAD_ACCEPTED")
    require(not p("0"*40,True,seal,expected),"FAKE_ACQUISITION_ACCEPTED")
    require(not p(None,True,seal,expected),"INVALID_HEAD_TYPE_ACCEPTED")
    require(not p(base,True,seal,base),"RESEALED_REAL_ANCESTOR_ACCEPTED")
    require(not p(expected,True,hashlib.sha256(b"forged").hexdigest(),
                  expected),"COORDINATED_MANIFEST_ACCEPTED")
    # The correct SHA/HEAD alone is NOT sufficient on unrelated checkouts.
    with patch.object(oracle,"ancestor",return_value=False):
        require(not p(expected,True,seal,expected),"UNRELATED_REPO_BYPASS")
    with patch.object(oracle,"ancestor",side_effect=lambda c:c==base):
        require(p(base,False),"STRICT_ORIGINAL_ANCESTRY_REGRESSION")
        require(not p(expected,True,seal,expected),"UNRELATED_SQUASH_BYPASS")
    # Fail-closed absent archive under both unsealed and permanent seal modes.
    with TemporaryDirectory(prefix="j125-p1-empty-") as tmp:
        for sealed in (False,True):
            try:
                oracle.verify(Path(tmp),seal if sealed else None,
                              expected if sealed else None)
            except oracle.OracleError as exc:
                require("ABSENT" in str(exc),"MISSING_ARCHIVE_WRONG_CAUSE")
            else:
                raise AssertionError("MISSING_ARCHIVE_ACCEPTED")
    print("J1.25-A-P1 SQUASH_SCOPE_PASS 14_CONTRACT_CHECKS "
          "REAL_HEAD_AND_SEAL_PINNED UNSEALED_STRICT ABSENT_ARCHIVE_REJECTED",
          flush=True)


if __name__=="__main__":
    main()
