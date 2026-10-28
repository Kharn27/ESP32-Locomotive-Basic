#!/usr/bin/env bash
# CI-OPT1-C1: real diff-dependent archive and core/HW4 checks.
# Independent from the historical absolute-path, driver and runtime checks.
set -euo pipefail
fail() { printf 'CI_ARCH_CHANGE_REJECTED %s\n' "$*" >&2; exit 1; }
base="${CI_ARCH_BASE:-}"
[[ "$base" =~ ^[[:xdigit:]]{40}$ ]] || fail "MISSING_BASE"
git cat-file -e "$base^{commit}" 2>/dev/null || fail "BASE_NOT_A_COMMIT"
head="$(git rev-parse --verify 'HEAD^{commit}')"
[[ "$base" != "$head" ]] || fail "BASE_EQUALS_HEAD"
git merge-base --is-ancestor "$base" "$head" || fail "BASE_NOT_ANCESTOR"
# Capture the command's exit code, unlike process substitution (which can hide it).
fixture_changes="$(git diff --name-status --no-renames "$base" "$head" -- tests/fixtures/cpc6128/)" ||
  fail "FIXTURE_DIFF_FAILED"
while IFS=$'\t' read -r status path; do
    [[ -n "$status" ]] || continue
    [[ "$status" == A ]] || fail "EXISTING_CPC_PROOF_CHANGED $status $path"
    case "$path" in
      tests/fixtures/cpc6128/*/*)
        relative="${path#tests/fixtures/cpc6128/}"
        folder="tests/fixtures/cpc6128/${relative%%/*}"
        if git cat-file -e "$base:$folder" 2>/dev/null; then
            fail "OLD_ARCHIVE_ADDITION_FORBIDDEN $path"
        fi
        ;;
      *) fail "UNSCOPED_CPC_ADDITION $path" ;;
    esac
done <<< "$fixture_changes"
oracle_changes="$(git diff --name-status --no-renames "$base" "$head" -- tests/oracles/)" ||
  fail "ORACLE_DIFF_FAILED"
while IFS=$'\t' read -r status path; do
    [[ -n "$status" ]] || continue
    [[ "$status" == A ]] || fail "EXISTING_ORACLE_CHANGED $status $path"
done <<< "$oracle_changes"
hw4_changes="$(git diff --name-only --no-renames "$base" "$head" -- \
  io/ video/ firmware/ tests/test_hw4_c2_integration.c tests/test_hw4_c1_integration.c)" ||
  fail "HW4_DIFF_FAILED"
if [[ -n "$hw4_changes" ]] && ! git diff --quiet "$base" "$head" -- core/; then
    fail "CORE_AND_HW4_CHANGED_TOGETHER"
fi
printf 'CI_ARCH_CHANGE_GUARDS_PASS base=%s head=%s\n' "$base" "$head"
