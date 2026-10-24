#!/usr/bin/env bash
# sotc: run the game once and dump the presented frame at the given seconds (raw -> out/dump).
# usage: tools/sotc_shots.sh total_seconds t1 t2 ...
set -uo pipefail
cd -- "$(dirname -- "$0")/.."
export MSYS2_ROOT=${MSYS2_ROOT:-/i/msys64}
export PATH="$MSYS2_ROOT/clang64/bin:$MSYS2_ROOT/usr/bin:$PATH"
game=${SOTC_GAME_DIR:-"$(dirname "$0")/../../CUSA08809"}
total=$1; shift
rm -rf out/dump; mkdir -p out/dump
export BB_FRAME_DUMP_TRIGGER=out/dump.trigger BB_DUMP_DIR=out/dump
timeout "$total" out/bb-probe.exe out/boot-linked.bin --content-profile out/content.bin --sotc-cpu out/sotc-cpu.bin \
    --app0 "$game" --user out/user > out/run.txt 2>&1 &
pid=$!
start=$SECONDS
for t in "$@"; do
    while (( SECONDS - start < t )); do sleep 1; kill -0 $pid 2>/dev/null || break 2; done
    touch out/dump.trigger
done
wait $pid; echo "rc=$?"
ls out/dump
