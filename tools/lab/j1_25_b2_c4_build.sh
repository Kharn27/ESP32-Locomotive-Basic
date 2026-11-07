#!/usr/bin/env bash
# J1.25-B2-C4 lab only, Issue #338. Adaptation of C3 proven recipe. Never merge.
set -euo pipefail
CASE="${1:?usage: c4_build.sh e500|main_e008}"
ROOT="${GITHUB_WORKSPACE:?GitHub-hosted runner expected}"
BASE=21e95a7197413923bb5976067a0419bc729c20c1
B1=4d261f2a76374ab99a4dd7415cae7a097330c46b
E500=e500864b3be612a325559259250f41cc35b5252b
E008=e0085a9e2d3b601359fc44fcfa3ea83430fc7056
C1=64b0087d5087903fee175c4f149c65a65bb43fe6
MAIN=ae07e039a08f6fff66f752228dc2ebed3fcf4220
OUT="$ROOT/reports/c4/$CASE"
mkdir -p "$OUT"
trap 'rc=$?; printf "%s\n" "$rc" > "$OUT/job-exit.txt"; if [ "$rc" -ne 0 ]; then echo "C4 MEASUREMENT_INVALID case=$CASE exit=$rc"; fi' EXIT
test "$(git -C "$ROOT" rev-parse HEAD)" = "${GITHUB_SHA:?expected exact lab commit}"
test "$(git -C "$ROOT" status --porcelain --untracked-files=no)" = ""
case "$CASE" in
  e500) REV="$E500";;
  ref) REV="$BASE";;
  b1) REV="$B1";;
  main_e008) REV="$E008";;
  c1) REV="$C1";;
  main_ae07|combo) REV="$MAIN";;
  *) echo "Unknown C4 variant $CASE" >&2; exit 2;;
esac
for sha in "$BASE" "$B1" "$E500" "$E008" "$C1" "$MAIN"; do
  git -C "$ROOT" cat-file -e "$sha^{commit}"
done
git -C "$ROOT" fetch --no-tags origin \
  +refs/pull/330/head:refs/remotes/origin/c3-pr330 \
  > "$OUT/pr330-fetch.log" 2>&1
test "$(git -C "$ROOT" rev-parse refs/remotes/origin/c3-pr330)" = "$C1"
test "$(git -C "$ROOT" merge-base "$MAIN" "$C1")" = "$B1"
# Gate introduced after the frozen ELF commit: pin script against current
# main, NOT against the older baseline commit (where this file did not exist).
git -C "$ROOT" show "$MAIN:tools/ci/hw4_render_a_memory.py" | sha256sum > "$OUT/main-gate-sha256.txt"
sha256sum "$ROOT/tools/ci/hw4_render_a_memory.py" | sed "s@  .*@  -@" > "$OUT/lab-gate-sha256.txt"
sed -i 's@  .*@  -@' "$OUT/main-gate-sha256.txt"
cmp -s "$OUT/main-gate-sha256.txt" "$OUT/lab-gate-sha256.txt" || {
 echo "Historical gate comparator modified in laboratory" >&2; exit 8;
}
SRC="$ROOT/.c4-worktrees/$CASE"
git -C "$ROOT" worktree add --detach "$SRC" "$REV" > "$OUT/worktree.log" 2>&1
test "$(git -C "$SRC" rev-parse HEAD)" = "$REV"
{
 echo "case=$CASE"
 echo "source_ref=$REV"
 echo "main_source=$MAIN"
 echo "c1_source=$C1"
 echo "merge_base=$B1"
 echo "lab_workflow=$GITHUB_SHA"
} > "$OUT/provenance.txt"
if [ "$CASE" = combo ]; then
  set +e
  git -C "$SRC" -c user.name='C3 disposable lab' \
    -c user.email='c3-lab@example.invalid' \
    merge --no-commit --no-ff "$C1" \
    > "$OUT/synthetic-merge.log" 2>&1
  MERGE_RC=$?
  set -e
  printf 'merge_exit=%s\n' "$MERGE_RC" >> "$OUT/provenance.txt"
  git -C "$SRC" status --short > "$OUT/synthetic-merge-status.txt"
  if [ "$MERGE_RC" -ne 0 ]; then
    echo "STOP: synthetic merge conflict; no silent resolution" >&2
    exit 4
  fi
  git -C "$SRC" write-tree > "$OUT/synthetic-tree.txt"
  git -C "$SRC" -c user.name='C3 disposable lab' \
    -c user.email='c3-lab@example.invalid' -c commit.gpgsign=false \
    commit -m 'C3 temporary experiment: ae07 + PR330, NEVER PUSH' \
    > "$OUT/synthetic-commit.log" 2>&1
  printf 'synthetic_local_commit=%s\n' "$(git -C "$SRC" rev-parse HEAD)" >> "$OUT/provenance.txt"
  printf 'synthetic_tree=%s\n' "$(git -C "$SRC" rev-parse HEAD^{tree})" >> "$OUT/provenance.txt"
  git -C "$SRC" rev-list --parents -n 1 HEAD > "$OUT/synthetic-parents.txt"
  test "$(awk '{print $2}' "$OUT/synthetic-parents.txt")" = "$MAIN"
  test "$(awk '{print $3}' "$OUT/synthetic-parents.txt")" = "$C1"
  test "$(git -C "$SRC" rev-parse HEAD^{tree})" = "$(cat "$OUT/synthetic-tree.txt")"
fi
git -C "$SRC" rev-parse HEAD > "$OUT/checked-out-head.txt"
git -C "$SRC" rev-parse HEAD^{tree} > "$OUT/tree.txt"
docker pull espressif/idf@sha256:bf72fe7a15c22849a9a94147301165a545fb8905d97c176cf748e3e4614cac84 > "$OUT/docker-pull.log" 2>&1
docker image inspect espressif/idf@sha256:bf72fe7a15c22849a9a94147301165a545fb8905d97c176cf748e3e4614cac84 \
  --format '{{json .RepoDigests}}' > "$OUT/docker-repodigests.json"
grep -q 'sha256:bf72fe7a15c22849a9a94147301165a545fb8905d97c176cf748e3e4614cac84' "$OUT/docker-repodigests.json"
docker image inspect espressif/idf@sha256:bf72fe7a15c22849a9a94147301165a545fb8905d97c176cf748e3e4614cac84 \
  --format '{{.Id}}' > "$OUT/docker-image-id.txt"
docker version > "$OUT/docker-version.txt"
for run in 1 2; do
  R="$OUT/run$run"
  F="$SRC/firmware/esp32_display_probe"
  mkdir -p "$R"
  printf '%s\n' "$REV" > "$R/source-sha.txt"
  printf '%s\n' "$(git -C "$SRC" rev-parse HEAD)" > "$R/build-head.txt"
  printf '%s\n' "$(git -C "$SRC" rev-parse HEAD^{tree})" > "$R/source-tree.txt"
  BUILD="build-c4-spi40-run$run"
  CONFIG="sdkconfig.c4-spi40-run$run"
  test ! -e "$F/$BUILD" && test ! -e "$F/$CONFIG"
  docker run --rm \
    -v "$ROOT:$ROOT" -w "$F" \
    -e IDF_GIT_SAFE_DIR="$SRC" -e C3_OUT="$R" \
    -e C3_BUILD="$BUILD" -e C3_CONFIG="$CONFIG" \
    espressif/idf@sha256:bf72fe7a15c22849a9a94147301165a545fb8905d97c176cf748e3e4614cac84 bash -lc '
      set -euo pipefail
      idf.py --version | tee "$C3_OUT/idf-version.txt"
      grep -Fx "ESP-IDF v5.5.6" "$C3_OUT/idf-version.txt"
      xtensa-esp-elf-gcc --version > "$C3_OUT/gcc-version.txt"
      xtensa-esp-elf-ld --version > "$C3_OUT/ld-version.txt"
      xtensa-esp-elf-objdump --version > "$C3_OUT/objdump-version.txt"
      idf.py -B "$C3_BUILD" -DSDKCONFIG="$PWD/$C3_CONFIG" \
        -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=40000000 \
        set-target esp32 > "$C3_OUT/set-target.log" 2>&1 || {
        tail -120 "$C3_OUT/set-target.log"; exit 1;
      }
      idf.py -B "$C3_BUILD" -DSDKCONFIG="$PWD/$C3_CONFIG" \
        -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ=40000000 \
        build > "$C3_OUT/build.log" 2>&1 || {
        tail -120 "$C3_OUT/build.log"; exit 1;
      }
      grep -Fx "LOCO_CYD_PROFILE:STRING=CONSOLE" "$C3_BUILD/CMakeCache.txt"
      grep -Fx "CYD_LCD_SPI_HZ:STRING=40000000" "$C3_BUILD/CMakeCache.txt"
      grep -F -- "-DLCD_CLOCK_HZ=40000000U" "$C3_BUILD/compile_commands.json" > /dev/null
      cp "$C3_BUILD/CMakeCache.txt" "$C3_OUT/CMakeCache.txt"
      cp "$C3_BUILD/compile_commands.json" "$C3_OUT/compile_commands.json"
      cp "$PWD/$C3_CONFIG" "$C3_OUT/sdkconfig"
      cp "$C3_BUILD/loco_esp32_display_probe.elf" "$C3_OUT/firmware.elf"
      cp "$C3_BUILD/loco_esp32_display_probe.bin" "$C3_OUT/firmware.bin"
      cp "$C3_BUILD/loco_esp32_display_probe.map" "$C3_OUT/firmware.map"
      gzip -n -6 "$C3_OUT/firmware.map"
      idf.py -B "$C3_BUILD" size > "$C3_OUT/idf-size.txt" 2>&1
      idf.py -B "$C3_BUILD" size-components > "$C3_OUT/size-components.txt" 2>&1
      xtensa-esp-elf-size -A "$C3_OUT/firmware.elf" > "$C3_OUT/sections.txt"
      xtensa-esp-elf-nm -S --defined-only "$C3_OUT/firmware.elf" > "$C3_OUT/symbols.txt"
      xtensa-esp-elf-readelf -SW "$C3_OUT/firmware.elf" > "$C3_OUT/readelf-sections.txt"
      xtensa-esp-elf-objdump -drwC -j .iram0.text \
        "$C3_OUT/firmware.elf" > "$C3_OUT/iram-disassembly.txt"
      grep -E "l32r|call8|callx" "$C3_OUT/iram-disassembly.txt" \
        > "$C3_OUT/iram-calls.txt" || true
      sha256sum "$C3_OUT/firmware.elf" "$C3_OUT/firmware.bin" \
        "$C3_OUT/sections.txt" "$C3_OUT/sdkconfig" "$C3_OUT/CMakeCache.txt" \
        > "$C3_OUT/digests.txt"
      printf "SPI40_STRICT=PASS\n" > "$C3_OUT/config-verdict.txt"
    ' > "$R/docker-output.log" 2>&1 || {
      tail -140 "$R/docker-output.log"; exit 9;
    }
  test -s "$R/sections.txt" && test -s "$R/firmware.elf"
  test "$(cat "$R/config-verdict.txt")" = "SPI40_STRICT=PASS"
  echo "C4 build PASS case=$CASE repetition=$run"
done
printf "C4_CASE_PASS %s 2/2\n" "$CASE" | tee "$OUT/case-verdict.txt"
