#!/bin/sh
# ---------------------------------------------------------------------------
# MakerBridge - RPG Maker 2000/2003 -> RPG Maker MZ   (Linux, macOS)
#
#   ./MakerBridge.sh                 opens the window
#   ./MakerBridge.sh setup           checks and installs what is needed
#   ./MakerBridge.sh convert ...     command line (see ./MakerBridge.sh --help)
#
# On the first start MakerBridge sets itself up: it creates its own Python
# environment .venv in this folder and installs Pillow there - the system's
# Python is left alone.  What only the system can provide (Python with
# Tkinter, ffmpeg, FluidSynth) is installed with its package manager after
# asking.  Deleting the folder removes everything MakerBridge added itself.
# ---------------------------------------------------------------------------
cd "$(dirname "$0")" || exit 1
mkdir -p log
VENV="$(pwd)/.venv"
VPY="$VENV/bin/python"
VERBOSE=
[ "$1" = "setup" ] && VERBOSE=1

say() { if [ -n "$VERBOSE" ]; then echo "$@"; fi; }

# -- the system's Python 3.10+ ----------------------------------------------
find_python() {
    PY=
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 &&
           "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            PY=$candidate
            return
        fi
    done
}

# -- what is missing, installed with the system's package manager -----------
system_packages() {
    need_python=; need_venv=; need_tk=; need_ffmpeg=; need_synth=
    find_python
    if [ -z "$PY" ]; then
        need_python=1; need_venv=1; need_tk=1
    else
        [ -x "$VPY" ] || "$PY" -c 'import venv, ensurepip' 2>/dev/null || need_venv=1
        "$PY" -c 'import tkinter' 2>/dev/null || need_tk=1
    fi
    command -v ffmpeg >/dev/null 2>&1 || need_ffmpeg=1
    command -v fluidsynth >/dev/null 2>&1 || need_synth=1
    if [ -z "$need_synth" ] && [ -n "$PY" ] &&
       ! "$PY" -c 'import sys; from makerbridge.audio import find_soundfont; sys.exit(0 if find_soundfont() else 1)' 2>/dev/null; then
        need_synth=1
    fi
}

install_system() {
    required="$need_python$need_venv$need_tk"
    optional="$need_ffmpeg$need_synth"
    [ -z "$required$optional" ] && return 0
    # Optional parts are offered once; "no" is remembered.
    if [ -z "$required" ] && [ -z "$VERBOSE" ] && [ -f log/no-optional ]; then
        return 0
    fi
    if [ "$(uname)" = "Darwin" ]; then manager=brew
    elif command -v apt-get >/dev/null 2>&1; then manager=apt
    elif command -v dnf >/dev/null 2>&1; then manager=dnf
    elif command -v pacman >/dev/null 2>&1; then manager=pacman
    elif command -v zypper >/dev/null 2>&1; then manager=zypper
    else manager=
    fi
    packages=
    add() { packages="$packages $1"; }
    case $manager in
        apt)
            [ -n "$need_python" ] && add python3
            [ -n "$need_venv" ] && add python3-venv
            [ -n "$need_tk" ] && add python3-tk
            [ -n "$need_ffmpeg" ] && add ffmpeg
            [ -n "$need_synth" ] && add "fluidsynth fluid-soundfont-gm" ;;
        dnf)
            [ -n "$need_python$need_venv" ] && add python3
            [ -n "$need_tk" ] && add python3-tkinter
            [ -n "$need_ffmpeg" ] && add ffmpeg
            [ -n "$need_synth" ] && add "fluidsynth fluid-soundfont-gm" ;;
        pacman)
            [ -n "$need_python$need_venv" ] && add python
            [ -n "$need_tk" ] && add tk
            [ -n "$need_ffmpeg" ] && add ffmpeg
            [ -n "$need_synth" ] && add "fluidsynth soundfont-fluid" ;;
        zypper)
            [ -n "$need_python$need_venv" ] && add python3
            [ -n "$need_tk" ] && add python3-tk
            [ -n "$need_ffmpeg" ] && add ffmpeg
            [ -n "$need_synth" ] && add "fluidsynth fluid-soundfont" ;;
        brew)
            [ -n "$need_python$need_venv$need_tk" ] && add python-tk
            [ -n "$need_ffmpeg" ] && add ffmpeg
            [ -n "$need_synth" ] && add fluid-synth ;;
    esac
    echo
    echo "MakerBridge - Einrichtung"
    echo "========================="
    [ -n "$need_python" ] && echo "  fehlt: Python 3.10 oder neuer (Pflicht)"
    [ -n "$need_venv" ] && [ -z "$need_python" ] && echo "  fehlt: Python-Umgebungen (venv) (Pflicht)"
    [ -n "$need_tk" ] && [ -z "$need_python" ] && echo "  fehlt: Tkinter, fuer das Fenster (Pflicht)"
    [ -n "$need_ffmpeg" ] && echo "  fehlt: ffmpeg, um die Musik umzuwandeln (empfohlen)"
    [ -n "$need_synth" ] && echo "  fehlt: FluidSynth und eine Klangbank, fuer MIDI-Musik (empfohlen)"
    [ "$manager" = "dnf" ] && [ -n "$need_ffmpeg" ] &&
        echo "  Hinweis: ffmpeg kommt fuer Fedora aus der Paketquelle RPM Fusion."
    echo
    case $manager in
        brew) command="brew install$packages" ;;
        apt) command="sudo apt-get install -y$packages" ;;
        dnf) command="sudo dnf install -y$packages" ;;
        pacman) command="sudo pacman -S --needed$packages" ;;
        zypper) command="sudo zypper install -y$packages" ;;
        *) command= ;;
    esac
    if [ -z "$command" ] || [ -z "$packages" ]; then
        echo "Bitte die fehlenden Teile mit dem Paketmanager deines Systems installieren."
        [ -z "$required" ]
        return
    fi
    echo "Installieren mit:"
    echo "  $command"
    printf "Jetzt ausfuehren? [J/n] "
    read -r answer
    case $answer in
        n|N|nein|Nein)
            if [ -z "$required" ]; then
                : > log/no-optional
                echo "Ok - mit ./MakerBridge.sh setup kannst du es spaeter nachholen."
                return 0
            fi
            return 1 ;;
    esac
    $command && rm -f log/no-optional
}

setup() {
    say ""
    say "MakerBridge - Einrichtung"
    say "========================="
    # A broken environment (its Python is gone) is made again.
    if [ -x "$VPY" ] && ! "$VPY" -c 'import sys' 2>/dev/null; then
        rm -rf "$VENV"
    fi
    system_packages
    install_system || {
        echo "MakerBridge kann noch nicht starten: Python 3.10+ mit venv und Tkinter fehlt."
        exit 1
    }
    find_python
    if [ ! -x "$VPY" ]; then
        echo "Richte MakerBridge ein (eigene Python-Umgebung in .venv) ..."
        "$PY" -m venv "$VENV" || { echo "Die Python-Umgebung konnte nicht angelegt werden."; exit 1; }
    fi
    if ! "$VPY" -c 'import tkinter' 2>/dev/null; then
        echo "Tkinter fehlt noch - bitte ./MakerBridge.sh setup ausfuehren."
        exit 1
    fi
    if ! "$VPY" -c 'import PIL' 2>/dev/null; then
        echo "Installiere Pillow (Bildbearbeitung) in die MakerBridge-Umgebung ..."
        "$VPY" -m pip install --disable-pip-version-check --quiet -r requirements.txt || {
            echo "Pillow konnte nicht installiert werden. Pruefe die Internetverbindung."
            exit 1
        }
    fi
    say "[ok] alles bereit ($VENV)"
}

setup
case "$1" in
    "") exec "$VPY" -X utf8 -m makerbridge gui ;;
    setup) exit 0 ;;
    *)
        echo "[MakerBridge] $*"
        "$VPY" -X utf8 -m makerbridge "$@"
        rc=$?
        echo
        echo "[MakerBridge] exit code $rc, logs in $(pwd)/log"
        exit $rc ;;
esac
