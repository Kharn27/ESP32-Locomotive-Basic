#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for cc in gcc clang; do
  for san in off on; do
    out="$(mktemp)"
    trap 'rm -f "$out"' EXIT
    flags=(-std=c99 -Wall -Wextra -Wpedantic -Wconversion -Werror)
    if [[ "$san" == on ]]; then flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
    "$cc" "${flags[@]}" -Ifirmware/components/cyd_ili9341/include tests/test_hw4_vscr_p1_policy.c -o "$out"
    "$out"
    rm -f "$out"
    trap - EXIT
    printf 'P1 HOST PASS compiler=%s sanitizers=%s\n' "$cc" "$san"
  done
done
