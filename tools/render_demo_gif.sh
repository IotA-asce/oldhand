#!/bin/bash
# Render the demo GIF from the VHS tape.
#
# VHS 0.12.0 captures frames correctly and then never invokes ffmpeg: it
# prints "Creating ...gif", exits 0, and writes nothing (see
# examples/demo/README.md). This script does the half VHS skips -- it lets
# VHS record, keeps the PNG frames it drops into $TMPDIR before VHS deletes
# them, and encodes them itself.
#
#   ./tools/render_demo_gif.sh
#
# Delete this script once VHS ships a release that encodes on its own.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAPE="$ROOT/examples/demo/oldhand-demo.tape"
TARGET="$ROOT/docs/img/oldhand-demo.gif"
FRAMES="$(mktemp -d -t oldhand-frames)"
trap 'rm -rf "$FRAMES"' EXIT

command -v vhs >/dev/null || { echo "vhs not installed: brew install vhs" >&2; exit 1; }
command -v ffmpeg >/dev/null || { echo "ffmpeg not installed" >&2; exit 1; }

cd "$ROOT"
vhs "$TAPE" >/dev/null 2>&1 &
VHS_PID=$!

# VHS only appends frames, so copying repeatedly while it runs is safe and
# avoids racing its cleanup.
while kill -0 "$VHS_PID" 2>/dev/null; do
  DIR=$(ls -dt "${TMPDIR:-/tmp}"/vhs[0-9]* 2>/dev/null | head -1 || true)
  [ -n "${DIR:-}" ] && cp "$DIR"/frame-text-*.png "$FRAMES"/ 2>/dev/null || true
  sleep 0.4
done
wait "$VHS_PID" 2>/dev/null || true

COUNT=$(find "$FRAMES" -name 'frame-text-*.png' | wc -l | tr -d ' ')
[ "$COUNT" -gt 100 ] || { echo "only $COUNT frames captured; refusing to encode" >&2; exit 1; }

cd "$FRAMES"
ffmpeg -hide_banner -loglevel error -framerate 50 -pattern_type glob -i 'frame-text-*.png' \
  -vf "fps=12,scale=860:-1:flags=lanczos,pad=iw+48:ih+48:24:24:color=#0d1117,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" \
  -loop 0 -y "$TARGET"

echo "wrote $TARGET from $COUNT frames ($(du -h "$TARGET" | cut -f1))"
