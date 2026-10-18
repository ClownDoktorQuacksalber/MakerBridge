#!/bin/sh
# rm2k2mv - RPG Maker 2000/2003 -> RPG Maker MV/MZ converter (Linux, macOS)
#
#   ./run.sh                 inspect the RM2k project (default command)
#   ./run.sh convert         write the MV/MZ project
#   ./run.sh convert "<src>" "<dst>"
#
# Every run writes a timestamped log to log/.
cd "$(dirname "$0")" || exit 1
mkdir -p log
CMD="${1:-inspect}"
[ $# -gt 0 ] && shift
echo "[rm2k2mv] running: $CMD"
python3 -X utf8 -m rm2k2mv "$CMD" "$@"
RC=$?
echo
echo "[rm2k2mv] exit code $RC"
echo "[rm2k2mv] logs in $(pwd)/log"
exit $RC
