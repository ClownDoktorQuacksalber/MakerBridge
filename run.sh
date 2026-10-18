#!/bin/sh
# MakerBridge - RPG Maker 2000/2003 -> RPG Maker MZ converter (Linux, macOS)
#
#   ./run.sh                 inspect the RM2k project (default command)
#   ./run.sh convert         write the MZ project
#   ./run.sh convert "<src>" "<dst>"
#
# Every run writes a timestamped log to log/.
cd "$(dirname "$0")" || exit 1
mkdir -p log
CMD="${1:-inspect}"
[ $# -gt 0 ] && shift
echo "[MakerBridge] running: $CMD"
python3 -X utf8 -m makerbridge "$CMD" "$@"
RC=$?
echo
echo "[MakerBridge] exit code $RC"
echo "[MakerBridge] logs in $(pwd)/log"
exit $RC
