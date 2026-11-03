#!/usr/bin/env bash
# Execute from any directory. No changes outside the temporary build dir.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
for compiler in gcc clang; do
  command -v "$compiler" >/dev/null
  for san in off on; do
    flags=(-std=c99 -O1 -g -Wall -Wextra -Werror -pedantic)
    if [[ "$san" == on ]]; then
      flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer)
    fi
    "$compiler" "${flags[@]}" -I"$root/firmware/esp32_display_probe/main" \
      "$root/firmware/esp32_display_probe/main/hw4_batch16_dma.c" \
      "$root/tests/test_hw4_batch16_dma.c" -o "$tmp/a1-$compiler-$san"
    "$tmp/a1-$compiler-$san"
    echo "HW4-A1-C0 HOST_${compiler^^}_${san^^}=PASS"
  done
done
