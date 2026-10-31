#!/bin/sh
# Standalone C99 build until PR #220 releases both CMakeLists.txt files.
set -eu
cd "$(dirname "$0")/.."
CC=${CC:-cc}
OUT=${OUT:-/tmp/hw4-run-break-a-test}
if [ "${SANITIZERS:-}" = "1" ]; then
    "$CC" -std=c99 -Wall -Wextra -Wpedantic -Wconversion -Werror -O1 -g \
      -fsanitize=address,undefined -fno-omit-frame-pointer \
      -Icore -Iintegration core/*.c integration/hw4_run_scheduler.c \
      tests/test_hw4_run_scheduler.c -lm -o "$OUT"
else
    "$CC" -std=c99 -Wall -Wextra -Wpedantic -Wconversion -Werror \
      -Icore -Iintegration core/*.c integration/hw4_run_scheduler.c \
      tests/test_hw4_run_scheduler.c -lm -o "$OUT"
fi
"$OUT"
