#!/bin/sh
# Usage: ig-queue/queue_add.sh <carousel-dir>
# Copies <carousel-dir>/out/upload into ig-queue/queue/NN-<name>/ (next free NN),
# converts PNG slides to JPEG (the API only accepts JPEG images) and writes
# post.json with approved=false.
set -e
SRC=${1%/}; Q="$(dirname "$0")/queue"
[ -d "$SRC/out/upload" ] || { echo "No $SRC/out/upload — run split-carousel.sh first"; exit 1; }
[ -f "$SRC/out/upload/caption.txt" ] || { echo "No caption.txt in $SRC/out/upload"; exit 1; }
mkdir -p "$Q"
NAME=$(basename "$SRC" | sed 's/^carousel-//')
if ls -d "$Q"/*-"$NAME" >/dev/null 2>&1; then echo "$NAME is already queued"; exit 1; fi
N=$(ls "$Q" | grep -c . || true); N=$(printf %02d $((N+1)))
D="$Q/$N-$NAME"; mkdir "$D"
for f in "$SRC"/out/upload/*; do
  case "$f" in
    *.png) sips -s format jpeg -s formatOptions 95 "$f" --out "$D/$(basename "${f%.png}").jpg" >/dev/null ;;
    *) cp "$f" "$D/" ;;
  esac
done
printf '{\n  "source": "%s",\n  "approved": false\n}\n' "$(basename "$SRC")" > "$D/post.json"
echo "Queued $D: $(ls "$D" | tr '\n' ' ')"
