#!/usr/bin/env bash
# Issue #341, additive laboratory witness ONLY. No historical gate changes.
set -euo pipefail
ROOT="${GITHUB_WORKSPACE:?GitHub-hosted checkout required}"
PR_NUMBER="${C7_PR_NUMBER:?real GitHub PR number required}"
IMAGE=espressif/idf@sha256:bf72fe7a15c22849a9a94147301165a545fb8905d97c176cf748e3e4614cac84
OUT="$ROOT/reports/hw4-mem-c7"
mkdir -p "$OUT"
trap 'rc=$?; printf "C7_BUILD_EXIT=%s\n" "$rc" > "$OUT/build-exit.txt"; if [ "$rc" -ne 0 ]; then echo "C7_MEASUREMENT_INVALID rc=$rc"; fi' EXIT
test "$(git -C "$ROOT" rev-parse HEAD)" = "${C7_WORKFLOW_HEAD:?checkout HEAD required}"
test "$(git -C "$ROOT" status --porcelain --untracked-files=no)" = ""
curl -fsS --max-time 30 --retry 2 \
 -H 'Accept: application/vnd.github+json' \
 -H "Authorization: Bearer ${GH_TOKEN:?token needed}" \
 "https://api.github.com/repos/$GITHUB_REPOSITORY/pulls/$PR_NUMBER" > "$OUT/pr-live.json"
BASE="$(jq -r '.base.sha' "$OUT/pr-live.json")"
HEAD="$(jq -r '.head.sha' "$OUT/pr-live.json")"
test "$(jq -r '.state' "$OUT/pr-live.json")" = open
test "$(jq -r '.base.ref' "$OUT/pr-live.json")" = main
test "$(jq -r '.base.repo.full_name' "$OUT/pr-live.json")" = "$GITHUB_REPOSITORY"
EXPECTED_BASE="$BASE"
test "$(git -C "$ROOT" ls-remote origin refs/heads/main | cut -f1)" = "$EXPECTED_BASE" || {
  echo "STOP: main drift from live GitHub PR base"; exit 6;
}
echo "C7_ACTUAL_MAIN=$EXPECTED_BASE"
test -z "${C7_EXPECTED_HEAD:-}" || test "$HEAD" = "$C7_EXPECTED_HEAD" || {
  echo "STOP: PR GitHub HEAD differs from C7 expected witness"; exit 6;
}
test "$HEAD" != "$BASE"
echo "C7_REAL_GITHUB_PR=$PR_NUMBER BASE=$BASE HEAD=$HEAD"
git -C "$ROOT" fetch --no-tags origin \
 "+refs/pull/$PR_NUMBER/head:refs/remotes/origin/c7-provenance-head" \
 > "$OUT/fetch.log" 2>&1
test "$(git -C "$ROOT" rev-parse refs/remotes/origin/c7-provenance-head)" = "$HEAD" || {
  echo "STOP: pulled PR head differs from live GitHub"; exit 6;
}
for label in base head; do
  if [ "$label" = base ]; then SHA="$BASE"; else SHA="$HEAD"; fi
  SRC="$ROOT/.c7-worktrees/$label"
  git -C "$ROOT" worktree add --detach "$SRC" "$SHA" > "$OUT/worktree-$label.log" 2>&1
  test "$(git -C "$SRC" rev-parse HEAD)" = "$SHA"
  printf '%s\n' "$(git -C "$SRC" rev-parse HEAD^{tree})" > "$OUT/$label-tree.txt"
done
python3 tools/ci/hw4_mem_c7_provenance.py \
 --live-pr "$OUT/pr-live.json" --repo "$GITHUB_REPOSITORY" \
 --pr-number "$PR_NUMBER" --base-dir "$ROOT/.c7-worktrees/base" \
 --head-dir "$ROOT/.c7-worktrees/head" --expected-base "$BASE" \
 --output "$OUT/provenance.json"
docker pull "$IMAGE" > "$OUT/docker-pull.log" 2>&1
docker image inspect "$IMAGE" --format '{{json .RepoDigests}}' > "$OUT/docker-repodigests.json"
grep -F 'sha256:bf72fe7a15c22849a9a94147301165a545fb8905d97c176cf748e3e4614cac84' "$OUT/docker-repodigests.json"
IMAGE_ID="$(docker image inspect "$IMAGE" --format '{{.Id}}')"
printf '%s\n' "$IMAGE_ID" > "$OUT/docker-image-id.txt"
for label in base head; do
  SRC="$ROOT/.c7-worktrees/$label"
  if [ "$label" = base ]; then SHA="$BASE"; else SHA="$HEAD"; fi
  TREE="$(cat "$OUT/$label-tree.txt")"
  F="$SRC/firmware/esp32_display_probe"
  for variant in spi40 spi20; do
    if [ "$variant" = spi40 ]; then HZ=40000000; FALLBACK=OFF; else HZ=20000000; FALLBACK=ON; fi
    R="$OUT/$label/$variant"
    mkdir -p "$R"
    BUILD="build-c7-$label-$variant"
    CFG="sdkconfig.c7-$label-$variant"
    test ! -e "$F/$BUILD" && test ! -e "$F/$CFG"
    docker run --rm -v "$ROOT:$ROOT" -w "$F" \
      -e IDF_GIT_SAFE_DIR="$SRC" \
      -e C7_OUT="$R" -e C7_BUILD="$BUILD" -e C7_CFG="$CFG" \
      -e C7_HZ="$HZ" -e C7_FALLBACK="$FALLBACK" -e C7_VARIANT="$variant" -e C7_LABEL="$label" \
      -e C7_SOURCE="$SHA" -e C7_TREE="$TREE" -e C7_IMAGE_ID="$IMAGE_ID" -e C7_ROOT="$ROOT" \
      "$IMAGE" bash -lc '
        set -euo pipefail
        idf.py --version > "$C7_OUT/idf-version.txt"
        grep -Fx "ESP-IDF v5.5.6" "$C7_OUT/idf-version.txt"
        xtensa-esp-elf-gcc --version > "$C7_OUT/gcc-version.txt"
        xtensa-esp-elf-ld --version > "$C7_OUT/ld-version.txt"
        idf.py -B "$C7_BUILD" -DSDKCONFIG="$PWD/$C7_CFG" \
          -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ="$C7_HZ" -DCYD_LCD_SPI20_OPT_IN="$C7_FALLBACK" \
          set-target esp32 > "$C7_OUT/set-target.log" 2>&1 || {
            tail -100 "$C7_OUT/set-target.log"; exit 1; }
        idf.py -B "$C7_BUILD" -DSDKCONFIG="$PWD/$C7_CFG" \
          -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ="$C7_HZ" -DCYD_LCD_SPI20_OPT_IN="$C7_FALLBACK" \
          build > "$C7_OUT/build.log" 2>&1 || {
            tail -100 "$C7_OUT/build.log"; exit 1; }
        cp "$C7_BUILD/CMakeCache.txt" "$C7_OUT/CMakeCache.txt"
        cp "$C7_BUILD/compile_commands.json" "$C7_OUT/compile_commands.json"
        cp "$PWD/$C7_CFG" "$C7_OUT/sdkconfig"
        cp "$C7_BUILD/loco_esp32_display_probe.elf" "$C7_OUT/firmware.elf"
        cp "$C7_BUILD/loco_esp32_display_probe.bin" "$C7_OUT/firmware.bin"
        xtensa-esp-elf-size -A "$C7_OUT/firmware.elf" > "$C7_OUT/sections.txt"
        xtensa-esp-elf-size -A "$C7_OUT/firmware.elf" | cmp -s - "$C7_OUT/sections.txt"
        xtensa-esp-elf-readelf -h "$C7_OUT/firmware.elf" > "$C7_OUT/readelf-header.txt"
        grep -E "Machine:.*Xtensa" "$C7_OUT/readelf-header.txt"
        grep -Fx "CYD_LCD_SPI20_OPT_IN:BOOL=$C7_FALLBACK" "$C7_OUT/CMakeCache.txt"
        grep -F -- "-DLCD_CLOCK_HZ=$C7_HZ""U" "$C7_OUT/compile_commands.json" > /dev/null
        python3 $C7_ROOT/tools/ci/verify_esp_app_version.py \
          "$C7_OUT/firmware.bin" "$C7_SOURCE" loco_esp32_display_probe \
          > "$C7_OUT/app-version.log"
        python3 $C7_ROOT/tools/ci/hw4_mem_c7_capture.py \
          --out "$C7_OUT" --source-sha "$C7_SOURCE" --source-tree "$C7_TREE" \
          --label "$C7_LABEL" --variant "$C7_VARIANT" --image-id "$C7_IMAGE_ID"
      ' > "$R/docker-output.log" 2>&1 || {
        tail -120 "$R/docker-output.log"; exit 9;
      }
    echo "C7_XTENSA_BUILD_PASS source=$SHA variant=$variant"
  done
done
# Live refs must STILL match after four builds, not just at invocation start.
curl -fsS --max-time 30 --retry 2 \
 -H 'Accept: application/vnd.github+json' \
 -H "Authorization: Bearer $GH_TOKEN" \
 "https://api.github.com/repos/$GITHUB_REPOSITORY/pulls/$PR_NUMBER" > "$OUT/pr-final.json"
test "$(jq -r '.base.sha' "$OUT/pr-final.json")" = "$BASE" || {
  echo "STOP: GitHub PR base drift during build"; exit 6;
}
test "$(jq -r '.head.sha' "$OUT/pr-final.json")" = "$HEAD" || {
  echo "STOP: GitHub PR HEAD drift during build"; exit 6;
}
test "$(git -C "$ROOT" ls-remote origin refs/heads/main | cut -f1)" = "$EXPECTED_BASE" || {
  echo "STOP: main advanced during build"; exit 6;
}
echo "C7_REAL_PAIR_STABLE=PASS four-independent-builds"


# #379: replay unchanged old memory gates against independently rebuilt frozen
# references. Exit 1 is a real HISTORICAL_FAILURE, never a historic PASS.
case "${C7_MODE:?mode required}" in
  render) HIST_SHA=21e95a7197413923bb5976067a0419bc729c20c1; HIST_DRAM=54864 ;;
  c3) HIST_SHA=989ec54989537a31c3a9be8074f1ce7c47708f17; HIST_DRAM=54168 ;;
  *) echo "FAIL_CLOSED: unknown C7 mode"; exit 2 ;;
esac
HIST="$ROOT/.c7-worktrees/historical"
git -C "$ROOT" cat-file -e "$HIST_SHA^{commit}"
git -C "$ROOT" worktree add --detach "$HIST" "$HIST_SHA" > "$OUT/worktree-historical.log" 2>&1
test "$(git -C "$HIST" rev-parse HEAD)" = "$HIST_SHA"
HIST_F="$HIST/firmware/esp32_display_probe"
mkdir -p "$OUT/historical"
docker run --rm -v "$ROOT:$ROOT" -w "$HIST_F" \
  -e IDF_GIT_SAFE_DIR="$HIST" -e C7_OUT="$OUT/historical" -e HIST_SHA="$HIST_SHA" -e C7_ROOT="$ROOT" \
  "$IMAGE" bash -lc '
    set -euo pipefail
    idf.py --version | grep -Fx "ESP-IDF v5.5.6"
    idf.py -B build-c7-historical -DSDKCONFIG="$PWD/sdkconfig.c7-historical" \
      -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=40000000 \
      set-target esp32 > "$C7_OUT/configure.log" 2>&1 || { tail -100 "$C7_OUT/configure.log"; exit 1; }
    idf.py -B build-c7-historical -DSDKCONFIG="$PWD/sdkconfig.c7-historical" \
      -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=40000000 \
      build > "$C7_OUT/build.log" 2>&1 || { tail -100 "$C7_OUT/build.log"; exit 1; }
    cp build-c7-historical/loco_esp32_display_probe.elf "$C7_OUT/historical.elf"
    cp build-c7-historical/loco_esp32_display_probe.bin "$C7_OUT/historical.bin"
    xtensa-esp-elf-size -A "$C7_OUT/historical.elf" > "$C7_OUT/sections.txt"
    python3 "$C7_ROOT/tools/ci/verify_esp_app_version.py" \
      "$C7_OUT/historical.bin" "$HIST_SHA" loco_esp32_display_probe
  ' > "$OUT/historical/docker-output.log" 2>&1 || {
    tail -100 "$OUT/historical/docker-output.log"; exit 9;
  }
python3 - "$OUT/historical/sections.txt" "$HIST_DRAM" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, "tools/ci")
from hw4_a0_compare_memory import read_size
m=read_size(Path(sys.argv[1]))
assert m["iram"] == 67331 and m["dram"] == int(sys.argv[2]), m
print("C7_FROZEN_HISTORICAL_REAL_ELF=PASS",m)
PY
LEGACY_LOG="$OUT/historical/legacy-$C7_MODE.log"
set +e
if [ "$C7_MODE" = render ]; then
  python3 tools/ci/hw4_render_a_memory.py \
    --baseline "$OUT/historical/sections.txt" \
    --optimized "$OUT/head/spi40/sections.txt" > "$LEGACY_LOG" 2>&1
else
  python3 tools/ci/hw4_disp_spi_variants.py \
    --base-sections "$OUT/historical/sections.txt" \
    --spi40-sections "$OUT/head/spi40/sections.txt" \
    --spi40-cache "$OUT/head/spi40/CMakeCache.txt" \
    --spi40-commands "$OUT/head/spi40/compile_commands.json" \
    --spi40-bin "$OUT/head/spi40/firmware.bin" \
    --spi20-sections "$OUT/head/spi20/sections.txt" \
    --spi20-cache "$OUT/head/spi20/CMakeCache.txt" \
    --spi20-commands "$OUT/head/spi20/compile_commands.json" \
    --spi20-bin "$OUT/head/spi20/firmware.bin" > "$LEGACY_LOG" 2>&1
fi
legacy_rc=$?
set -e
printf 'HISTORICAL_GATE=%s EXIT_CODE=%s OLD_SHA=%s\n' "$C7_MODE" "$legacy_rc" "$HIST_SHA" | tee "$OUT/historical/exit-code.txt"
cat "$LEGACY_LOG"
if [ "$legacy_rc" -eq 1 ]; then
  if [ "$C7_MODE" = render ]; then
    grep -Fq 'RENDER-A introduces unauthorized incremental IRAM' "$LEGACY_LOG"
  else
    grep -Fq 'IRAM changed' "$LEGACY_LOG"
  fi
  # An old comparator fails as historically designed; a new incremental pass
  # must never relabel that old return code as an old PASS.
  echo "HISTORICAL_FAILURE=TRUE old_exit=1 mode=$C7_MODE"
elif [ "$legacy_rc" -eq 0 ]; then
  echo "HISTORICAL_FAILURE=FALSE old_exit=0 mode=$C7_MODE"
else
  echo "MEASUREMENT_INVALID: unexpected historical comparator exit $legacy_rc"
  exit 2
fi

# Fetch authoritative GitHub refs again AFTER both historical and PR builds.
curl -fsS --max-time 30 --retry 2 \
  -H 'Accept: application/vnd.github+json' \
  -H "Authorization: Bearer ${GH_TOKEN:?GH_TOKEN required}" \
  "https://api.github.com/repos/$GITHUB_REPOSITORY/pulls/$PR_NUMBER" > "$OUT/pr-final.json"
test "$(jq -r '.base.sha' "$OUT/pr-final.json")" = "$BASE"
test "$(jq -r '.head.sha' "$OUT/pr-final.json")" = "$HEAD"
test "$(git -C "$ROOT" ls-remote origin refs/heads/main | cut -f1)" = "$BASE"
mkdir -p "$OUT/verdict"
python3 tools/ci/hw4_mem_c7_v2.py \
  --root "$OUT" --provenance "$OUT/provenance.json" \
  --live-pr-start "$OUT/pr-live.json" --live-pr "$OUT/pr-final.json" \
  --repo "$GITHUB_REPOSITORY" --pr-number "$PR_NUMBER" \
  --base-checkout "$ROOT/.c7-worktrees/base" --head-checkout "$ROOT/.c7-worktrees/head" \
  --output "$OUT/verdict" | tee "$OUT/verdict/console.log"
# Comparator exit is enforced by pipefail; no legacy or incremental error masking.
cat "$OUT/verdict/verdict.md" >> "$GITHUB_STEP_SUMMARY"
printf '\n**Historical comparator: real FAILURE (rc=1), +220 B debt, ROOT_CAUSE_UNVERIFIED.**\n' >> "$GITHUB_STEP_SUMMARY"
echo "C7_REAL_FIVE_XTENSA_BUILDS=PASS mode=$C7_MODE BASE_SHA=$BASE HEAD_SHA=$HEAD"
