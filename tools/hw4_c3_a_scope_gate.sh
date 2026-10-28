#!/usr/bin/env bash
# HW4-C3-A-C1: narrow PR scope, never exempt the historical CPC archives.
set -euo pipefail
if test "$#" -ne 2; then echo "USAGE: bash tools/hw4_c3_a_scope_gate.sh BASE HEAD" >&2; exit 2; fi
base="$1"
head="$2"
# Every byte of oracle provenance and native J1 core must match the
# current integration base. No ESP32 probe, HAL, transport or UART mutations.
git diff --exit-code "$base" "$head" -- \
  core/ hal/ io/ tests/fixtures/ tests/oracles/ \
  firmware/components/
# These are the ONLY allowed graphics changes on this specifically named
# HW4-C3-A PR. The other historical branches retain their strict gates.
changed="$(git diff --name-only "$base" "$head" -- video/ firmware/)"
extra="$(printf '%s\n' "$changed" | grep -Ev \
  '^(video/cpc_boot\.(c|h)|firmware/esp32_display_probe/main/(CMakeLists\.txt|cpc_font\.c|hw4_c2_console\.c|main\.c))$' || true)"
if test -n "$extra"; then
    printf 'HW4-C3-A OUT_OF_SCOPE_GRAPHICS_DIFF:\n%s\n' "$extra" >&2
    exit 1
fi
test -f video/cpc_boot.c
test -f video/cpc_boot.h
test -f firmware/esp32_display_probe/main/hw4_c2_console.c
test ! -e firmware/esp32_loco/CMakeLists.txt
echo "HW4-C3-A SCOPE_PASS base=$base head=$head oracle=IMMUTABLE core=IMMUTABLE transport=IMMUTABLE"
