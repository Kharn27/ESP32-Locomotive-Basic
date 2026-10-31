#!/usr/bin/env bash
# Capture interactive UART CYD + automatic PNG extraction for HW4-SHOT-A.
# Host-only tooling: does not alter ESP32 firmware or the P0 decoder.
set -euo pipefail

ROOT="${LOCO_CYD_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)}"
PROJECT="$ROOT/firmware/esp32_display_probe"
PORT="${1:-/dev/ttyUSB0}"
LOG="${2:-$ROOT/hw4-scroll-a0-c2-$(date +%Y%m%d-%H%M%S).uart.log}"
OUT_DIR="${3:-$(dirname -- "$LOG")}"
WATCHER="${LOCO_CYD_WATCHER:-$ROOT/tools/hw4_shot_watch.py}"
DECODE="$ROOT/tools/hw4_shot_decode.py"
WATCH_LOG="${LOG}.shot-events.log"

if [[ ! -d "$PROJECT" ]]; then
    printf 'Erreur : depot introuvable : %s\n' "$PROJECT" >&2
    exit 1
fi
for app in idf.py script python3; do
    if ! command -v "$app" >/dev/null 2>&1; then
        printf 'Erreur : commande introuvable : %s\n' "$app" >&2
        exit 1
    fi
done
for file in "$WATCHER" "$DECODE"; do
    if [[ ! -f "$file" ]]; then
        printf 'Erreur : outil manquant : %s\n' "$file" >&2
        exit 1
    fi
done
if [[ -e "$LOG" || -e "$WATCH_LOG" ]]; then
    printf 'Erreur : journal deja existant, aucun ecrasement : %s\n' "$LOG" >&2
    exit 1
fi
mkdir -p -- "$(dirname -- "$LOG")" "$OUT_DIR"

printf -v PORT_QUOTED '%q' "$PORT"
printf '\n=== CYD UART : %s ===\n' "$PORT"
printf 'Journal brut : %s\n' "$LOG"
printf 'PNG automatiques : %s\n' "$OUT_DIR"
printf 'Evenements capture : %s\n' "$WATCH_LOG"
printf 'IMPORTANT : conserver un journal distinct par boot.\n'
printf 'Sortie moniteur : Ctrl+].\n\n'

# Keep the IDF monitor interactive; watcher tails the flushed script log.
# Diagnostics are in a separate file, not injected into the UART stream.
PYTHONPATH="$ROOT/tools${PYTHONPATH:+:$PYTHONPATH}" python3 -u "$WATCHER" "$LOG" "$OUT_DIR" >"$WATCH_LOG" 2>&1 &
watch_pid=$!

stop_watcher() {
    if [[ -n "${watch_pid:-}" ]]; then
        kill -TERM "$watch_pid" 2>/dev/null || true
        wait "$watch_pid" 2>/dev/null || true
        watch_pid=""
    fi
}
trap stop_watcher EXIT

cd -- "$PROJECT"
set +e
script -q -f -e -c "idf.py -p $PORT_QUOTED monitor" "$LOG"
monitor_status=$?
set -e

stop_watcher
trap - EXIT
printf '\nJournal UART conserve : %s\n' "$LOG"
printf 'PNG : %s\n' "$OUT_DIR"
if [[ -s "$WATCH_LOG" ]]; then
    printf '\n=== Resultats captures automatiques ===\n'
    cat -- "$WATCH_LOG"
fi
exit "$monitor_status"
