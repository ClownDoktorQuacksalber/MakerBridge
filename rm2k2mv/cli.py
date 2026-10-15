"""Command line interface for the RPG Maker 2000 -> MV converter."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import os
import sys
import traceback

from . import project

LOG_DIR_NAME = "log"


def _setup_logging(tool_root: str, command: str, verbose: bool) -> str:
    log_dir = os.path.join(tool_root, LOG_DIR_NAME)
    os.makedirs(log_dir, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(log_dir, f"{command}-{stamp}.log")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)-22s %(message)s", "%H:%M:%S"))
    root.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.DEBUG if verbose else logging.INFO)
    sh.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
    root.addHandler(sh)

    # Keep a stable name so a tail/editor can always watch the newest run.
    latest = os.path.join(log_dir, f"{command}-latest.log")
    try:
        with open(latest, "w", encoding="utf-8") as fh2:
            fh2.write(f"see {os.path.basename(path)}\n")
    except OSError:
        pass
    return path


class _Counter(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.counts = {"WARNING": 0, "ERROR": 0, "CRITICAL": 0}

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelname in self.counts:
            self.counts[record.levelname] += 1


def _json_default(obj):
    if isinstance(obj, bytes):
        return obj.hex()
    raise TypeError(f"not JSON serialisable: {type(obj).__name__}")


def cmd_dump(args, log) -> int:
    if not require_source(args, log):
        return 1
    proj = project.load(args.source, args.encoding)
    out_dir = args.out or os.path.join(args.tool_root, "dump")
    os.makedirs(out_dir, exist_ok=True)

    def write(name: str, payload) -> None:
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=1, ensure_ascii=False,
                      default=_json_default)
        log.info("wrote %s (%d bytes)", name, os.path.getsize(path))

    write("database.json", proj.database)
    write("maptree.json", proj.maptree)
    maps_dir = os.path.join(out_dir, "maps")
    os.makedirs(maps_dir, exist_ok=True)
    for map_id, data in proj.maps.items():
        path = os.path.join(maps_dir, f"Map{map_id:04d}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, ensure_ascii=False,
                      default=_json_default)
    log.info("wrote %d map dumps to %s", len(proj.maps), maps_dir)
    return 0


def cmd_inspect(args, log) -> int:
    if not require_source(args, log):
        return 1
    from .inspect import report
    proj = project.load(args.source, args.encoding)
    report(proj, log)
    return 0


def cmd_convert(args, log) -> int:
    if not require_source(args, log):
        return 1
    from .convert import convert_project
    proj = project.load(args.source, args.encoding, rtp=args.rtp)
    convert_project(proj, args.target, log, overwrite=args.overwrite,
                    skip_assets=args.skip_assets, template=args.template)
    return 0


def cmd_verify(args, log) -> int:
    if not args.target:
        log.error("no MV project named. Pass one: run.bat %s \"<folder>\"",
                  args.command)
        return 1
    from .verify import verify
    return 0 if verify(args.target, log) == 0 else 1


def cmd_transcode(args, log) -> int:
    if not args.target:
        log.error("no MV project named. Pass one: run.bat %s \"<folder>\"",
                  args.command)
        return 1
    from .audio import transcode
    return transcode(args.target, log, ffmpeg=args.ffmpeg,
                     keep_sources=args.keep, quality=args.quality,
                     soundfont=args.soundfont, fluidsynth=args.fluidsynth)


def cmd_fixup(args, log) -> int:
    if not args.target:
        log.error("no MV project named. Pass one: run.bat %s \"<folder>\"",
                  args.command)
        return 1
    from .fixup import fixup
    return fixup(args.target, log, stub_images=not args.no_stubs)


def cmd_package(args, log) -> int:
    if not args.source or not args.target:
        log.error("name the MV project and the output folder: "
                  "run.bat package \"<mv project>\" \"<game folder>\"")
        return 1
    from .package import build
    return build(args.source, args.target, log, runtime=args.runtime,
                 overwrite=args.overwrite)


def cmd_gui(args, log) -> int:
    from .gui import main as gui_main
    return gui_main()


def discover_projects(tool_root: str) -> list[str]:
    """Every RM2k project sitting next to the tool."""
    base = os.path.dirname(tool_root)
    found = []
    try:
        for entry in sorted(os.listdir(base)):
            candidate = os.path.join(base, entry)
            if os.path.isfile(os.path.join(candidate, "RPG_RT.ldb")):
                found.append(candidate)
    except OSError:
        pass
    return found


def require_source(args, log) -> bool:
    """A bare command may only guess the project when there is just one.

    Picking the alphabetically first of several would quietly convert the
    wrong game the moment another project is dropped next to the tool.
    """
    if getattr(args, "source", None):
        return True
    candidates = discover_projects(args.tool_root)
    if not candidates:
        log.error("no RM2k project found next to the tool. Name one: "
                  "run.bat %s \"<folder with RPG_RT.ldb>\"", args.command)
    else:
        log.error("several RM2k projects are next to the tool, so none is "
                  "assumed. Name the one you mean:")
        for candidate in candidates:
            log.error("    run.bat %s \"%s\"", args.command, candidate)
    return False


def build_parser(tool_root: str) -> argparse.ArgumentParser:
    candidates = discover_projects(tool_root)
    default_source = candidates[0] if len(candidates) == 1 else None
    # Name the outputs after the project, so several conversions can live side
    # by side instead of all landing in one shared folder.
    default_mv = default_source.rstrip("\\/") + "_MV" if default_source else None
    default_game = (default_source.rstrip("\\/") + "_Game"
                    if default_source else None)
    p = argparse.ArgumentParser(
        prog="rm2k2mv",
        description="Convert an RPG Maker 2000 project (liblcf format) to "
                    "RPG Maker MV JSON.")
    p.add_argument("--encoding", default=project.DEFAULT_ENCODING,
                   help="text encoding of the RM2k project (default: cp1252)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("dump", help="decode the project to intermediate JSON")
    d.add_argument("source", nargs="?", default=default_source)
    d.add_argument("-o", "--out")
    d.set_defaults(func=cmd_dump)

    i = sub.add_parser("inspect", help="report structure and anything suspicious")
    i.add_argument("source", nargs="?", default=default_source)
    i.set_defaults(func=cmd_inspect)

    c = sub.add_parser("convert", help="write an RPG Maker MV project")
    c.add_argument("source", nargs="?", default=default_source)
    c.add_argument("target", nargs="?",
                   default=default_mv)
    c.add_argument("--overwrite", action="store_true",
                   help="allow writing into a non-empty target directory")
    c.add_argument("--skip-assets", action="store_true",
                   help="only write data/*.json, leave img/ and audio/ alone")
    c.add_argument("--template",
                   help="existing MV project to copy js/ and index.html from "
                        "(default: the first one found next to the tool)")
    c.add_argument("--rtp", action="append", metavar="DIR",
                   help="RPG Maker 2000/2003 RTP folder to take assets from that "
                        "the game does not ship (repeatable; default: the "
                        "installed RTP from the registry or RPG2K_RTP_PATH / "
                        "RPG2K3_RTP_PATH / RPG_RTP_PATH)")
    c.set_defaults(func=cmd_convert)

    v = sub.add_parser("verify", help="check a converted MV project")
    v.add_argument("target", nargs="?", default=default_mv)
    v.set_defaults(func=cmd_verify)

    t = sub.add_parser("transcode",
                       help="convert the copied audio to ogg so MV can play it")
    t.add_argument("target", nargs="?", default=default_mv)
    t.add_argument("--ffmpeg", help="path to ffmpeg.exe")
    t.add_argument("--keep", action="store_true",
                   help="keep the original mid/wav/mp3 files")
    t.add_argument("--quality", type=int, default=4,
                   help="libvorbis quality 0-10 (default 4)")
    t.add_argument("--soundfont",
                   help="sf2/sf3/dls bank for MIDI (default: a soundfont in "
                        "tools/, else Windows' gm.dls)")
    t.add_argument("--fluidsynth", help="path to fluidsynth.exe")
    t.set_defaults(func=cmd_transcode)

    fx = sub.add_parser("fixup",
                        help="blank missing sounds and stub missing images so "
                             "MV does not stop with a load error")
    fx.add_argument("target", nargs="?", default=default_mv)
    fx.add_argument("--no-stubs", action="store_true",
                    help="only blank sounds, do not write placeholder images")
    fx.set_defaults(func=cmd_fixup)

    k = sub.add_parser("package",
                       help="wrap the project in MV's NW.js runtime (Game.exe)")
    k.add_argument("source", nargs="?", default=default_mv)
    k.add_argument("target", nargs="?",
                   default=default_game)
    k.add_argument("--runtime", help="path to RPG Maker MV's nwjs-win folder")
    k.add_argument("--overwrite", action="store_true")
    k.set_defaults(func=cmd_package)

    g = sub.add_parser("gui", help="open the window-based front end")
    g.set_defaults(func=cmd_gui)
    return p


def main(argv: list[str] | None = None) -> int:
    tool_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser = build_parser(tool_root)
    args = parser.parse_args(argv)
    args.tool_root = tool_root

    log_path = _setup_logging(tool_root, args.command, args.verbose)
    counter = _Counter()
    logging.getLogger().addHandler(counter)
    log = logging.getLogger("rm2k2mv")

    log.info("rm2k2mv %s", args.command)
    log.info("log file: %s", log_path)
    log.info("source:   %s", getattr(args, "source", "-"))
    if getattr(args, "target", None):
        log.info("target:   %s", args.target)

    try:
        rc = args.func(args, log)
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        log.critical("%s: %s", type(exc).__name__, exc)
        log.debug("%s", traceback.format_exc())
        rc = 1

    log.info("done: %d warning(s), %d error(s)",
             counter.counts["WARNING"],
             counter.counts["ERROR"] + counter.counts["CRITICAL"])
    log.info("full log: %s", log_path)
    return rc
