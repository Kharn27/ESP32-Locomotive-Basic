#!/usr/bin/env bash
# Issue #341, additive laboratory witness ONLY. No historical gate changes.
set -euo pipefail
ROOT="${GITHUB_WORKSPACE:?GitHub-hosted checkout required}"
PR_NUMBER="${C5_PR_NUMBER:?real GitHub PR number required}"
EXPECTED_BASE=03f83c39e6f9ed4daeddb1ed93a989a35d726e30
IMAGE=espressif/idf@sha256:bf72fe7a15c22849a9a94147301165a545fb8905d97c176cf748e3e4614cac84
OUT="$ROOT/reports/hw4-mem-c5"
mkdir -p "$OUT"
trap 'rc=$?; printf "C5_BUILD_EXIT=%s\n" "$rc" > "$OUT/build-exit.txt"; if [ "$rc" -ne 0 ]; then echo "C5_MEASUREMENT_INVALID rc=$rc"; fi' EXIT
test "$(git -C "$ROOT" rev-parse HEAD)" = "${GITHUB_SHA:?workflow SHA required}"
test "$(git -C "$ROOT" status --porcelain --untracked-files=no)" = ""
test "$(git -C "$ROOT" ls-remote origin refs/heads/main | cut -f1)" = "$EXPECTED_BASE" || {
  echo "STOP: main drift from C5-approved 03f83"; exit 6;
}
echo "C5_MANDATE_MAIN=$EXPECTED_BASE"
curl -fsS --max-time 30 --retry 2 \
 -H 'Accept: application/vnd.github+json' \
 -H "Authorization: Bearer ${GH_TOKEN:?token needed}" \
 "https://api.github.com/repos/$GITHUB_REPOSITORY/pulls/$PR_NUMBER" > "$OUT/pr-live.json"
BASE="$(jq -r '.base.sha' "$OUT/pr-live.json")"
HEAD="$(jq -r '.head.sha' "$OUT/pr-live.json")"
test "$BASE" = "$EXPECTED_BASE" || { echo "STOP: PR GitHub base differs"; exit 6; }
test -z "${C5_EXPECTED_HEAD:-}" || test "$HEAD" = "$C5_EXPECTED_HEAD" || {
  echo "STOP: PR GitHub HEAD differs from C5 expected witness"; exit 6;
}
test "$HEAD" != "$BASE"
echo "C5_REAL_GITHUB_PR=$PR_NUMBER BASE=$BASE HEAD=$HEAD"
git -C "$ROOT" fetch --no-tags origin \
 "+refs/pull/$PR_NUMBER/head:refs/remotes/origin/c5-provenance-head" \
 > "$OUT/fetch.log" 2>&1
test "$(git -C "$ROOT" rev-parse refs/remotes/origin/c5-provenance-head)" = "$HEAD" || {
  echo "STOP: pulled PR head differs from live GitHub"; exit 6;
}
for label in base head; do
  if [ "$label" = base ]; then SHA="$BASE"; else SHA="$HEAD"; fi
  SRC="$ROOT/.c5-worktrees/$label"
  git -C "$ROOT" worktree add --detach "$SRC" "$SHA" > "$OUT/worktree-$label.log" 2>&1
  test "$(git -C "$SRC" rev-parse HEAD)" = "$SHA"
  printf '%s\n' "$(git -C "$SRC" rev-parse HEAD^{tree})" > "$OUT/$label-tree.txt"
done
python3 tools/ci/hw4_mem_c5_provenance.py \
 --live-pr "$OUT/pr-live.json" --repo "$GITHUB_REPOSITORY" \
 --pr-number "$PR_NUMBER" --base-dir "$ROOT/.c5-worktrees/base" \
 --head-dir "$ROOT/.c5-worktrees/head" --expected-base "$BASE" \
 --output "$OUT/provenance.json"
docker pull "$IMAGE" > "$OUT/docker-pull.log" 2>&1
docker image inspect "$IMAGE" --format '{{json .RepoDigests}}' > "$OUT/docker-repodigests.json"
grep -F 'sha256:bf72fe7a15c22849a9a94147301165a545fb8905d97c176cf748e3e4614cac84' "$OUT/docker-repodigests.json"
IMAGE_ID="$(docker image inspect "$IMAGE" --format '{{.Id}}')"
printf '%s\n' "$IMAGE_ID" > "$OUT/docker-image-id.txt"
for label in base head; do
  SRC="$ROOT/.c5-worktrees/$label"
  if [ "$label" = base ]; then SHA="$BASE"; else SHA="$HEAD"; fi
  TREE="$(cat "$OUT/$label-tree.txt")"
  F="$SRC/firmware/esp32_display_probe"
  for variant in spi40 spi20; do
    if [ "$variant" = spi40 ]; then HZ=40000000; else HZ=20000000; fi
    R="$OUT/$label/$variant"
    mkdir -p "$R"
    BUILD="build-c5-$label-$variant"
    CFG="sdkconfig.c5-$label-$variant"
    test ! -e "$F/$BUILD" && test ! -e "$F/$CFG"
    docker run --rm -v "$ROOT:$ROOT" -w "$F" \
      -e IDF_GIT_SAFE_DIR="$SRC" \
      -e C5_OUT="$R" -e C5_BUILD="$BUILD" -e C5_CFG="$CFG" \
      -e C5_HZ="$HZ" -e C5_VARIANT="$variant" -e C5_LABEL="$label" \
      -e C5_SOURCE="$SHA" -e C5_TREE="$TREE" -e C5_IMAGE_ID="$IMAGE_ID" -e C5_ROOT="$ROOT" \
      "$IMAGE" bash -lc '
        set -euo pipefail
        idf.py --version > "$C5_OUT/idf-version.txt"
        grep -Fx "ESP-IDF v5.5.6" "$C5_OUT/idf-version.txt"
        xtensa-esp-elf-gcc --version > "$C5_OUT/gcc-version.txt"
        xtensa-esp-elf-ld --version > "$C5_OUT/ld-version.txt"
        idf.py -B "$C5_BUILD" -DSDKCONFIG="$PWD/$C5_CFG" \
          -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ="$C5_HZ" \
          set-target esp32 > "$C5_OUT/set-target.log" 2>&1 || {
            tail -100 "$C5_OUT/set-target.log"; exit 1; }
        idf.py -B "$C5_BUILD" -DSDKCONFIG="$PWD/$C5_CFG" \
          -DLOCO_CYD_PROFILE=CONSOLE -DCYD_LCD_SPI_HZ="$C5_HZ" \
          build > "$C5_OUT/build.log" 2>&1 || {
            tail -100 "$C5_OUT/build.log"; exit 1; }
        cp "$C5_BUILD/CMakeCache.txt" "$C5_OUT/CMakeCache.txt"
        cp "$C5_BUILD/compile_commands.json" "$C5_OUT/compile_commands.json"
        cp "$PWD/$C5_CFG" "$C5_OUT/sdkconfig"
        cp "$C5_BUILD/loco_esp32_display_probe.elf" "$C5_OUT/firmware.elf"
        cp "$C5_BUILD/loco_esp32_display_probe.bin" "$C5_OUT/firmware.bin"
        xtensa-esp-elf-size -A "$C5_OUT/firmware.elf" > "$C5_OUT/sections.txt"
        xtensa-esp-elf-readelf -h "$C5_OUT/firmware.elf" > "$C5_OUT/readelf-header.txt"
        grep -E "Machine:.*Xtensa" "$C5_OUT/readelf-header.txt"
        python3 $C5_ROOT/tools/ci/verify_esp_app_version.py \
          "$C5_OUT/firmware.bin" "$C5_SOURCE" loco_esp32_display_probe \
          > "$C5_OUT/app-version.log"
        python3 $C5_ROOT/tools/ci/hw4_mem_c5_capture.py \
          --out "$C5_OUT" --source-sha "$C5_SOURCE" --source-tree "$C5_TREE" \
          --label "$C5_LABEL" --variant "$C5_VARIANT" --image-id "$C5_IMAGE_ID"
      ' > "$R/docker-output.log" 2>&1 || {
        tail -120 "$R/docker-output.log"; exit 9;
      }
    echo "C5_XTENSA_BUILD_PASS source=$SHA variant=$variant"
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
echo "C5_REAL_PAIR_STABLE=PASS four-independent-builds"
