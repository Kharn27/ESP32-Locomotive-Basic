#!/usr/bin/env bash
# Capture UART CYD / HW4-SCROLL-A0 sans toucher au firmware ni au SHA testé.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$ROOT/firmware/esp32_display_probe"
PORT="${1:-/dev/ttyUSB0}"
LOG="${2:-$ROOT/hw4-scroll-a0-c2-$(date +%Y%m%d-%H%M%S).uart.log}"

if [[ ! -d "$PROJECT" ]]; then
    printf 'Erreur : placer ce fichier a la racine du depot ESP32-Locomotive-Basic.\n' >&2
    exit 1
fi
if ! command -v idf.py >/dev/null 2>&1; then
    printf 'Erreur : idf.py introuvable. Active ton environnement ESP-IDF v5.5.6.\n' >&2
    exit 1
fi
if ! command -v script >/dev/null 2>&1; then
    printf 'Erreur : commande script absente (Debian : paquet util-linux).\n' >&2
    exit 1
fi
if [[ -e "$LOG" ]]; then
    printf 'Erreur : le fichier existe deja, rien ne sera ecrase : %s\n' "$LOG" >&2
    exit 1
fi

printf -v PORT_QUOTED '%q' "$PORT"
printf '\n=== CYD UART : %s ===\n' "$PORT"
printf 'Journal : %s\n' "$LOG"
printf 'Un seul boot HW4-C2 START dans le journal ; ne pas appuyer sur EN si le boot apparait deja.\n'
printf 'Pour sortir du monitor : Ctrl+].\n\n'

cd -- "$PROJECT"
script -q -f -e -c "idf.py -p $PORT_QUOTED monitor" "$LOG"
printf '\nJournal enregistre : %s\n' "$LOG"
