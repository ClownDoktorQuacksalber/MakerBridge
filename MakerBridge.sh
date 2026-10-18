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
    echo "MakerBridge - setup"
    echo "==================="
    [ -n "$need_python" ] && echo "  missing: Python 3.10 or newer (required)"
    [ -n "$need_venv" ] && [ -z "$need_python" ] && echo "  missing: Python environments (venv) (required)"
    [ -n "$need_tk" ] && [ -z "$need_python" ] && echo "  missing: Tkinter, for the window (required)"
    [ -n "$need_ffmpeg" ] && echo "  missing: ffmpeg, to convert the music (recommended)"
    [ -n "$need_synth" ] && echo "  missing: FluidSynth and a soundfont, for MIDI music (recommended)"
    [ "$manager" = "dnf" ] && [ -n "$need_ffmpeg" ] &&
        echo "  Note: on Fedora, ffmpeg comes from the RPM Fusion repository."
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
        echo "Please install the missing parts with your system's package manager."
        [ -z "$required" ]
        return
    fi
    echo "Install with:"
    echo "  $command"
    printf "Run it now? [Y/n] "
    read -r answer
    case $answer in
        n|N|no|No|nein|Nein)
            if [ -z "$required" ]; then
                : > log/no-optional
                echo "Ok - you can catch up on it later with ./MakerBridge.sh setup."
                return 0
            fi
            return 1 ;;
    esac
    $command && rm -f log/no-optional
}

setup() {
    say ""
    say "MakerBridge - setup"
    say "==================="
    # A broken environment (its Python is gone) is made again.
    if [ -x "$VPY" ] && ! "$VPY" -c 'import sys' 2>/dev/null; then
        rm -rf "$VENV"
    fi
    system_packages
    install_system || {
        echo "MakerBridge cannot start yet: Python 3.10+ with venv and Tkinter is missing."
        exit 1
    }
    find_python
    if [ ! -x "$VPY" ]; then
        echo "Setting up MakerBridge (its own Python environment in .venv) ..."
        "$PY" -m venv "$VENV" || { echo "The Python environment could not be created."; exit 1; }
    fi
    if ! "$VPY" -c 'import tkinter' 2>/dev/null; then
        echo "Tkinter is still missing - please run ./MakerBridge.sh setup."
        exit 1
    fi
    if ! "$VPY" -c 'import PIL' 2>/dev/null; then
        echo "Installing Pillow (image processing) into the MakerBridge environment ..."
        "$VPY" -m pip install --disable-pip-version-check --quiet -r requirements.txt || {
            echo "Pillow could not be installed. Check your internet connection."
            exit 1
        }
    fi
    say "[ok] all set ($VENV)"
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
