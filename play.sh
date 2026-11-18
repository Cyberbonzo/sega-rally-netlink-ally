#!/bin/sh
set -eu
cd "$(dirname "$(readlink -f "$0")")"
if [ -n "${RALLY_CUE:-}" ]; then
    cue=$RALLY_CUE
elif [ -f media/disc.cue ]; then
    cue=$PWD/media/disc.cue
else
    IFS= read -r cue < cue.path
fi
export SR_NETLINK_RACE_BOOT=1 SR_NETLINK_WIDE=1
mkdir -p saves logs
exec ./sega-rally-netlink --cue "$cue" --fullscreen --interp --settings "$PWD/controls.ini" --out "$PWD/logs" --save "$PWD/saves/cabinet.bup" "$@" > logs/game.log 2>&1
