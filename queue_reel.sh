#!/bin/sh
# Usage: ig-queue/queue_reel.sh <reel-dir>
# Copies the newest render in <reel-dir>/renders/ and <reel-dir>/caption.txt into
# ig-queue/queue/NN-<reel-name>/ (next free NN) with post.json approved=true.
set -e
SRC=${1%/}; Q="$(cd "$(dirname "$0")" && pwd)/queue"
MP4=$(ls -t "$SRC"/renders/*.mp4 2>/dev/null | head -1)
[ -n "$MP4" ] || { echo "No render in $SRC/renders"; exit 1; }
[ -f "$SRC/caption.txt" ] || { echo "No $SRC/caption.txt"; exit 1; }
NAME=$(basename "$SRC")
if ls -d "$Q"/*-"$NAME" >/dev/null 2>&1; then echo "$NAME is already queued"; exit 1; fi
LAST=$(ls "$Q" | sed -n 's/^\([0-9][0-9]\)-.*/\1/p' | sort -n | tail -1)
N=$(printf %02d $((10#$LAST + 1)))
D="$Q/$N-$NAME"; mkdir "$D"
cp "$MP4" "$D/01.mp4"; cp "$SRC/caption.txt" "$D/caption.txt"
printf '{\n  "source": "%s",\n  "type": "reel",\n  "approved": true\n}\n' "$NAME" > "$D/post.json"
echo "Queued $D ($(basename "$MP4"))"
