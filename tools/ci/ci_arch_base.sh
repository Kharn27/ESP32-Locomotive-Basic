#!/usr/bin/env bash
# CI-OPT1-C1: compute a nontrivial, verified diff base for the checked-out commit.
# CI_ARCH_EVENT, CI_ARCH_BEFORE, CI_ARCH_BASE_REF, CI_ARCH_REF and
# CI_ARCH_EXPECTED_HEAD are injected by GitHub Actions; tested standalone.
set -euo pipefail
fail() { printf 'CI_ARCH_BASE_REJECTED %s\n' "$*" >&2; exit 1; }
head="$(git rev-parse --verify 'HEAD^{commit}')" || fail "HEAD_NOT_A_COMMIT"
expected="${CI_ARCH_EXPECTED_HEAD:-}"
if [[ -n "$expected" && "$expected" != "$head" ]]; then
    fail "WRONG_CHECKOUT expected=$expected actual=$head"
fi
event="${CI_ARCH_EVENT:-}"
case "$event" in
  push)
    [[ "${CI_ARCH_REF:-}" == refs/heads/main ]] || fail "PUSH_NOT_MAIN"
    before="${CI_ARCH_BEFORE:-}"
    [[ "$before" =~ ^[[:xdigit:]]{40}$ ]] || fail "PUSH_BEFORE_MISSING_OR_INVALID"
    [[ "$before" != 0000000000000000000000000000000000000000 ]] || fail "PUSH_BEFORE_ZERO"
    git cat-file -e "$before^{commit}" 2>/dev/null || fail "PUSH_BEFORE_NOT_FETCHED $before"
    git merge-base --is-ancestor "$before" "$head" || fail "PUSH_BEFORE_NOT_ANCESTOR"
    base="$before"
    ;;
  pull_request)
    [[ "${CI_ARCH_BASE_REF:-}" == main ]] || fail "PR_BASE_NOT_MAIN"
    git rev-parse --verify 'refs/remotes/origin/main^{commit}' >/dev/null ||
      fail "PR_REMOTE_MAIN_NOT_FETCHED"
    base="$(git merge-base refs/remotes/origin/main "$head")" ||
      fail "PR_NO_MERGE_BASE"
    ;;
  workflow_dispatch)
    if [[ "${CI_ARCH_REF:-}" == refs/heads/main ]]; then
        base="$(git rev-parse --verify 'HEAD^1')" || fail "DISPATCH_MAIN_NO_PARENT"
    elif [[ "${CI_ARCH_REF:-}" == refs/heads/* ]]; then
        git rev-parse --verify 'refs/remotes/origin/main^{commit}' >/dev/null ||
          fail "DISPATCH_BRANCH_MAIN_UNAVAILABLE"
        base="$(git merge-base refs/remotes/origin/main "$head")" ||
          fail "DISPATCH_BRANCH_NO_MERGE_BASE"
    else
        fail "DISPATCH_UNSUPPORTED_REF ${CI_ARCH_REF:-empty}"
    fi
    ;;
  *) fail "UNSUPPORTED_EVENT ${event:-empty}" ;;
esac
[[ "$base" =~ ^[[:xdigit:]]{40}$ ]] || fail "BASE_INVALID"
git cat-file -e "$base^{commit}" 2>/dev/null || fail "BASE_UNAVAILABLE"
[[ "$base" != "$head" ]] || fail "BASE_EQUALS_HEAD event=$event"
git merge-base --is-ancestor "$base" "$head" || fail "BASE_NOT_ANCESTOR"
printf 'CI_ARCH_BASE_VERIFIED event=%s base=%s head=%s\n' "$event" "$base" "$head" >&2
printf '%s\n' "$base"
