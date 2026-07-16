#!/usr/bin/env bash
set -euo pipefail

SRC="/Users/dennis/Projects/FlightTracker/esp32/FlightTracker"
DST="/Users/dennis/Documents/Arduino/projects/sketch_jun8a/FlightTracker"

if [[ ! -d "$SRC" ]]; then
  echo "ERROR: source directory not found: $SRC" >&2
  exit 1
fi

if [[ ! -d "$DST" ]]; then
  echo "ERROR: destination directory not found: $DST" >&2
  exit 1
fi

count=0
for f in "$SRC"/*.ino "$SRC"/*.h "$SRC"/*.cpp; do
  [[ -e "$f" ]] || continue
  cp "$f" "$DST/"
  echo "  copied: $(basename "$f")"
  (( count++ ))
done

echo "Done — $count file(s) synced to $DST"
