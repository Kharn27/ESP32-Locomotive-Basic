#!/usr/bin/env bash
# CI-OPT1-C1: isolated real Git repos; exercise the same scripts used by CI-ARCH.
# No production fixture, source, branch or remote is mutated.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
base_script="$ROOT/tools/ci/ci_arch_base.sh"
changes_script="$ROOT/tools/ci/ci_arch_changes.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
passed=0
fail() { echo "CI_ARCH_C1_TEST_FAILURE $*" >&2; exit 1; }
setup() {
    local name="$1"
    work="$tmp/$name"
    git init -q -b main "$work"
    git -C "$work" config user.name CI-Arch-Test
    git -C "$work" config user.email ci-arch@example.invalid
    mkdir -p "$work"/{core,video,docs,tests/fixtures/cpc6128/old_archive,tests/oracles}
    printf 'original\n' > "$work/tests/fixtures/cpc6128/old_archive/program.bin"
    echo 'core' > "$work/core/basic.c"
    echo 'video' > "$work/video/cpc_text.c"
    echo 'original' > "$work/tests/oracles/old_oracle.py"
    echo 'docs' > "$work/docs/README.md"
    git -C "$work" add -A
    git -C "$work" commit -qm initial
    old="$(git -C "$work" rev-parse HEAD)"
    git init -q --bare "$tmp/$name.git"
    git -C "$work" remote add origin "$tmp/$name.git"
    git -C "$work" push -q -u origin main
}
new_commit() {
    git -C "$work" add -A
    git -C "$work" commit -qm update
    new="$(git -C "$work" rev-parse HEAD)"
    git -C "$work" push -q origin main
    [[ "$(git -C "$work" rev-parse origin/main)" == "$new" ]] ||
      fail "ORIGIN_MAIN_NOT_HEAD"
}
base_for() {
    ( cd "$work"; CI_ARCH_EVENT="$1" CI_ARCH_BEFORE="${2:-}" \
      CI_ARCH_REF="${3:-refs/heads/main}" CI_ARCH_BASE_REF="${4:-main}" \
      CI_ARCH_EXPECTED_HEAD="$new" bash "$base_script" )
}
expect_pass() {
    local marker="$1"; shift
    local log
    if ! log="$("$@" 2>&1)"; then fail "$marker SHOULD_PASS $log"; fi
    printf 'CI_ARCH_C1_PASS %s\n' "$marker"
    passed=$((passed + 1))
}
expect_reject() {
    local marker="$1" token="$2"; shift 2
    local log
    if log="$("$@" 2>&1)"; then fail "$marker SHOULD_FAIL $log"; fi
    [[ "$log" == *"$token"* ]] || fail "$marker WRONG_REJECTION $log"
    printf 'CI_ARCH_C1_EXPECTED_REJECTION %s (%s)\n' "$marker" "$token"
    passed=$((passed + 1))
}
check_changes() { (cd "$work"; CI_ARCH_BASE="$old" bash "$changes_script"); }

# Reproduce the bug: origin/main == HEAD after a push, but BEFORE is older.
setup push_fixture; printf 'tamper\n' > "$work/tests/fixtures/cpc6128/old_archive/program.bin"; new_commit
[[ "$(git -C "$work" merge-base origin/main HEAD)" == "$new" ]] || fail "OLD_BUG_NOT_REPRODUCED"
[[ "$(base_for push "$old")" == "$old" ]] || fail "PUSH_BASE_NOT_BEFORE"
expect_reject push_historical_archive EXISTING_CPC_PROOF_CHANGED check_changes
expect_reject push_before_missing PUSH_BEFORE_MISSING_OR_INVALID base_for push ''
expect_reject push_before_zero PUSH_BEFORE_ZERO base_for push 0000000000000000000000000000000000000000
expect_reject push_before_unknown PUSH_BEFORE_NOT_FETCHED base_for push 1111111111111111111111111111111111111111
expect_reject push_before_head BASE_EQUALS_HEAD base_for push "$new"
# An existing but unrelated commit must not masquerade as a previous push SHA.
git -C "$work" checkout -qb unrelated "$old"
echo 'off-branch' > "$work/docs/unrelated.md"
git -C "$work" add -A
git -C "$work" commit -qm unrelated
unrelated="$(git -C "$work" rev-parse HEAD)"
git -C "$work" checkout -q main
expect_reject push_before_nonancestor PUSH_BEFORE_NOT_ANCESTOR base_for push "$unrelated"
expect_reject push_wrong_checkout WRONG_CHECKOUT \
    env CI_ARCH_EVENT=push CI_ARCH_REF=refs/heads/main CI_ARCH_BEFORE="$old" \
        CI_ARCH_EXPECTED_HEAD="$unrelated" bash "$base_script"

# Simultaneous core/HW4 edit is forbidden even if origin/main is the same HEAD.
setup push_core_hw4; echo 'core2' > "$work/core/basic.c"; echo 'video2' > "$work/video/cpc_text.c"; new_commit
[[ "$(base_for push "$old")" == "$old" ]] || fail "PUSH_CORE_BASE"
expect_reject push_core_hw4 CORE_AND_HW4_CHANGED_TOGETHER check_changes
setup push_allowed; echo 'new docs' > "$work/docs/README.md"; new_commit
[[ "$(base_for push "$old")" == "$old" ]] || fail "PUSH_ALLOWED_BASE"
expect_pass push_docs_only check_changes
# New captures may be added *only* under newly introduced archive namespace.
setup push_new_archive; mkdir -p "$work/tests/fixtures/cpc6128/new_archive"; echo 'new' > "$work/tests/fixtures/cpc6128/new_archive/program.bin"; new_commit
expect_pass push_new_archive check_changes
setup push_old_extension; echo 'malicious' > "$work/tests/fixtures/cpc6128/old_archive/new.txt"; new_commit
expect_reject push_extend_old_archive OLD_ARCHIVE_ADDITION_FORBIDDEN check_changes
setup push_oracle_change; echo 'changed' > "$work/tests/oracles/old_oracle.py"; new_commit
expect_reject push_modify_old_oracle EXISTING_ORACLE_CHANGED check_changes
# Pull request: origin/main remains at initial HEAD, PR HEAD advances only locally.
setup pr_archive; echo 'tamper' > "$work/tests/fixtures/cpc6128/old_archive/program.bin"
git -C "$work" add -A; git -C "$work" commit -qm change; new="$(git -C "$work" rev-parse HEAD)"
[[ "$(base_for pull_request unused refs/pull/116/merge main)" == "$old" ]] || fail "PR_MERGE_BASE_WRONG"
expect_reject pr_historical_archive EXISTING_CPC_PROOF_CHANGED check_changes
expect_reject pr_missing_main PR_BASE_NOT_MAIN base_for pull_request unused refs/pull/116/merge develop
setup pr_allowed; echo 'docs PR' > "$work/docs/README.md"
git -C "$work" add -A; git -C "$work" commit -qm change; new="$(git -C "$work" rev-parse HEAD)"
[[ "$(base_for pull_request unused refs/pull/116/merge main)" == "$old" ]] || fail "PR_ALLOWED_BASE"
expect_pass pr_docs_only check_changes
setup pr_core_hw4; echo 'core PR' > "$work/core/basic.c"; echo 'video PR' > "$work/video/cpc_text.c"
git -C "$work" add -A; git -C "$work" commit -qm change; new="$(git -C "$work" rev-parse HEAD)"
expect_reject pr_core_hw4 CORE_AND_HW4_CHANGED_TOGETHER check_changes

# workflow_dispatch: on main inspect HEAD^; on branch inspect merge-base.
setup dispatch_main; echo 'tamper' > "$work/tests/fixtures/cpc6128/old_archive/program.bin"; new_commit
[[ "$(base_for workflow_dispatch '' refs/heads/main)" == "$old" ]] || fail "DISPATCH_MAIN_BASE_WRONG"
expect_reject dispatch_main_archive EXISTING_CPC_PROOF_CHANGED check_changes
setup dispatch_branch; echo 'changed' > "$work/core/basic.c"
git -C "$work" add -A; git -C "$work" commit -qm change; new="$(git -C "$work" rev-parse HEAD)"
[[ "$(base_for workflow_dispatch '' refs/heads/feature)" == "$old" ]] || fail "DISPATCH_BRANCH_BASE_WRONG"
expect_pass dispatch_branch_core_only check_changes
setup dispatch_branch_synced; new="$old"
expect_reject dispatch_branch_no_changes BASE_EQUALS_HEAD \
    base_for workflow_dispatch '' refs/heads/feature

expect_reject dispatch_invalid_ref DISPATCH_UNSUPPORTED_REF base_for workflow_dispatch '' refs/tags/latest
# No parent or no PR difference must never pass as an empty HEAD-to-HEAD diff.
setup dispatch_no_parent; new="$old"
expect_reject dispatch_no_parent DISPATCH_MAIN_NO_PARENT base_for workflow_dispatch '' refs/heads/main
expect_reject pr_base_equals_head BASE_EQUALS_HEAD base_for pull_request unused refs/pull/116/merge main
printf 'CI_ARCH_C1_SELF_TEST_PASS cases=%s\n' "$passed"
