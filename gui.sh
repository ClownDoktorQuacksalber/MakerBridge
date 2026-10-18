#!/bin/sh
# rm2k2mv - grafische Oberflaeche fuer Linux und macOS.
# Braucht Python 3.10+ mit Tkinter (Debian/Ubuntu: sudo apt install python3-tk)
# und Pillow (pip install Pillow). Fuer die Kommandozeile siehe run.sh.
cd "$(dirname "$0")" || exit 1
mkdir -p log
exec python3 -X utf8 -m rm2k2mv gui "$@"
