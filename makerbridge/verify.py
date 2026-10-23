"""Check a converted project against what RPG Maker MV expects.

Catches the mistakes that are easy to make and hard to see: a map whose data
array is the wrong length, a tile id pointing past the end of its tileset, an
event referring to a character sheet that was never copied, a start position
on a map that does not exist.
"""

from __future__ import annotations

import json
import os
import re

from .mv import engine as engines

# Map001.json .. Map999.json, and Map1000.json+ for big projects.
MAP_FILE = re.compile(r"^Map(\d{3,})\.json$")


def _map_id(entry: str) -> int | None:
    match = MAP_FILE.match(entry)
    return int(match.group(1)) if match else None

REQUIRED = [
    "Actors.json", "Classes.json", "Skills.json", "Items.json", "Weapons.json",
    "Armors.json", "Enemies.json", "Troops.json", "States.json",
    "Animations.json", "Tilesets.json", "CommonEvents.json", "System.json",
    "MapInfos.json",
]

MV_LAYERS = 6
# Tile ids the converter emits: 0 means "no tile", 1..1023 are the B/C/D/E
# sheets and 1536..1663 is A5, which doubles as room for baked autotiles.
PLAIN_TILE_RANGE = (1, 1024)
A5_TILE_RANGE = (1536, 1664)


def _tile_id_ok(tile_id: int) -> bool:
    if tile_id == 0:
        return True
    return (PLAIN_TILE_RANGE[0] <= tile_id < PLAIN_TILE_RANGE[1]
            or A5_TILE_RANGE[0] <= tile_id < A5_TILE_RANGE[1])


def _load(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def verify(target: str, log) -> int:
    data_dir = os.path.join(target, "data")
    if not os.path.isdir(data_dir):
        log.error("no data/ folder in %s", target)
        return 1

    problems = 0
    log.info("verifying %s", target)

    files = {}
    for name in REQUIRED:
        path = os.path.join(data_dir, name)
        if not os.path.isfile(path):
            log.error("missing data/%s", name)
            problems += 1
            continue
        try:
            files[name] = _load(path)
        except ValueError as exc:
            log.error("data/%s is not valid JSON: %s", name, exc)
            problems += 1
    if "Tilesets.json" not in files or "MapInfos.json" not in files:
        return problems + 1

    problems += _check_runtime(target, log)
    problems += _check_tilesets(target, files["Tilesets.json"], log)
    problems += _check_maps(target, data_dir, files, log)
    problems += _check_system(files, log)
    problems += _check_assets(target, data_dir, files, log)
    problems += _check_command_arity(data_dir, files, log)

    if problems:
        log.warning("verification finished with %d problem(s)", problems)
    else:
        found = engines.detect(target)
        log.info("verification passed: the project looks loadable by %s",
                 found.label if found else "MV/MZ")
    return problems


def _check_runtime(target: str, log) -> int:
    problems = 0
    for item in ("js", "index.html"):
        if not os.path.exists(os.path.join(target, item)):
            log.warning("no %s - the project has data but cannot be launched "
                        "until you copy the MV runtime in", item)
            problems += 1
    return problems


def _check_tilesets(target: str, tilesets: list, log) -> int:
    problems = 0
    image_dir = os.path.join(target, "img", "tilesets")
    for tileset in tilesets:
        if not tileset:
            continue
        flags = tileset.get("flags") or []
        if len(flags) != 8192:
            log.error("tileset %d has %d flags, MV expects 8192",
                      tileset["id"], len(flags))
            problems += 1
        names = tileset.get("tilesetNames") or []
        if len(names) != 9:
            log.error("tileset %d has %d tilesetNames, MV expects 9",
                      tileset["id"], len(names))
            problems += 1
        for name in names[5:]:
            if name and not os.path.isfile(os.path.join(image_dir, name + ".png")):
                log.error("tileset %d references missing image img/tilesets/%s.png",
                          tileset["id"], name)
                problems += 1
    return problems


def _check_maps(target: str, data_dir: str, files: dict, log) -> int:
    problems = 0
    tilesets = files["Tilesets.json"]
    infos = files["MapInfos.json"]

    listed = {i for i, entry in enumerate(infos) if entry}
    on_disk = set()
    for entry in sorted(os.listdir(data_dir)):
        map_id = _map_id(entry)
        if map_id is not None:
            on_disk.add(map_id)

    for map_id in sorted(listed - on_disk):
        log.error("MapInfos lists map %d but data/Map%03d.json is missing",
                  map_id, map_id)
        problems += 1
    for map_id in sorted(on_disk - listed):
        log.warning("data/Map%03d.json exists but MapInfos does not list it",
                    map_id)
        problems += 1

    for map_id in sorted(on_disk & listed):
        payload = _load(os.path.join(data_dir, f"Map{map_id:03d}.json"))
        width, height = payload["width"], payload["height"]
        expected = width * height * MV_LAYERS
        if len(payload["data"]) != expected:
            log.error("map %d: data has %d entries, expected %d (%dx%d x %d layers)",
                      map_id, len(payload["data"]), expected, width, height, MV_LAYERS)
            problems += 1
        tileset_id = payload.get("tilesetId", 0)
        if tileset_id >= len(tilesets) or not tilesets[tileset_id]:
            log.error("map %d references tileset %d which does not exist",
                      map_id, tileset_id)
            problems += 1
            continue
        over = [t for t in payload["data"] if not _tile_id_ok(t)]
        if over:
            log.error("map %d: %d tile id(s) outside the sheets the converter "
                      "writes (0, 1-1023, 1536-1663), e.g. %s",
                      map_id, len(over), sorted(set(over))[:5])
            problems += 1
        for event in payload.get("events") or []:
            if not event:
                continue
            for page in event.get("pages") or []:
                commands = page.get("list") or []
                if not commands or commands[-1].get("code") != 0:
                    log.error("map %d event %d: command list does not end with "
                              "code 0", map_id, event["id"])
                    problems += 1
    return problems


def _check_system(files: dict, log) -> int:
    problems = 0
    system = files.get("System.json") or {}
    infos = files["MapInfos.json"]
    start = system.get("startMapId", 0)
    if start >= len(infos) or not infos[start]:
        log.error("System.startMapId is %d but there is no such map", start)
        problems += 1
    actors = files.get("Actors.json") or []
    for actor_id in system.get("partyMembers") or []:
        if actor_id >= len(actors) or not actors[actor_id]:
            log.error("System.partyMembers references actor %d which does not exist",
                      actor_id)
            problems += 1
    return problems


# How many parameters Game_Interpreter reads per command (rpg_objects.js).
# Commands whose arity depends on a discriminator (111, 122, 205 ...) are left
# out; the rest are fixed, and getting one wrong shifts every later value, so
# MV ends up reading a parameter that is not there.
# Picture commands carry RM2kCompat.js's extra values as one trailing
# object (after MZ's easing for Move Picture); MV ignores it.
RM2K_EXTENSION_AT = {231: 10, 232: 13, 235: 1}


def _rm2k_extension(code: int, params: list, expected: int) -> bool:
    at = RM2K_EXTENSION_AT.get(code)
    return (at is not None and len(params) == at + 1
            and isinstance(params[at], dict))


MV_COMMAND_ARITY = {
    0: 0, 101: 5, 401: 1, 102: 5, 402: 2, 403: 0, 404: 0, 103: 2,
    108: 1, 408: 1, 112: 0, 113: 0, 413: 0, 115: 0, 117: 1, 118: 1, 119: 1,
    121: 3, 124: 2, 125: 3, 126: 4, 127: 5, 128: 5, 129: 3,
    201: 6, 203: 5, 206: 0, 211: 1, 212: 3, 214: 0,
    221: 0, 222: 0, 223: 3, 224: 3, 225: 4, 230: 1,
    231: 10, 232: 12, 235: 1, 236: 4,
    241: 1, 242: 1, 245: 1, 249: 1, 250: 1, 251: 0, 261: 1,
    282: 1, 284: 5,
    301: 4, 303: 2,
    314: 2, 317: 6, 318: 4, 319: 3, 322: 6,
    353: 0, 354: 0, 355: 1, 655: 1,
}


def _check_command_arity(data_dir: str, files: dict, log) -> int:
    counts: dict[tuple, int] = {}
    example: dict[tuple, str] = {}

    def scan(commands, where: str) -> None:
        for command in commands or []:
            code = command.get("code")
            params = command.get("parameters")
            expected = MV_COMMAND_ARITY.get(code)
            if expected is None or not isinstance(params, list):
                continue
            if len(params) != expected and not _rm2k_extension(code, params, expected):
                key = (code, len(params), expected)
                counts[key] = counts.get(key, 0) + 1
                example.setdefault(key, where)

    for common in files.get("CommonEvents.json") or []:
        if common:
            scan(common.get("list"), f"common event {common['id']}")
    for troop in files.get("Troops.json") or []:
        if troop:
            for page in troop.get("pages") or []:
                scan(page.get("list"), f"troop {troop['id']}")
    for entry in sorted(os.listdir(data_dir)):
        if _map_id(entry) is None:
            continue
        payload = _load(os.path.join(data_dir, entry))
        for event in payload.get("events") or []:
            if not event:
                continue
            for page in event.get("pages") or []:
                scan(page.get("list"), f"{entry} event {event['id']}")

    if counts:
        total = sum(counts.values())
        log.error("%d command(s) carry the wrong number of parameters; MV reads "
                  "past the end of the list and crashes:", total)
        for (code, got, expected), n in sorted(counts.items(),
                                               key=lambda kv: -kv[1]):
            log.error("    code %-4d has %d, MV expects %d  (x%d, e.g. %s)",
                      code, got, expected, n, example[(code, got, expected)])
    return sum(counts.values())


from .fixup import SCRIPT_AUDIO, SCRIPT_AUDIO_KIND  # noqa: E402


def _check_assets(target: str, data_dir: str, files: dict, log) -> int:
    """Every name the data refers to must exist, or MV stops when it loads it."""
    have = {kind: _listing(os.path.join(target, "img", kind), PLAYABLE_IMAGE)
            for kind in ("characters", "faces", "enemies", "pictures",
                         "parallaxes", "titles1", "titles2", "animations",
                         "sv_actors", "sv_enemies")}
    have.update({kind: _listing(os.path.join(target, "audio", kind),
                                PLAYABLE_AUDIO)
                 for kind in ("bgm", "bgs", "me", "se")})
    missing: dict[str, set[str]] = {kind: set() for kind in have}

    def need(kind: str, name) -> None:
        if isinstance(name, str) and name and name not in have[kind]:
            missing[kind].add(name)

    def scan(commands) -> None:
        for command in commands or []:
            code = command.get("code")
            params = command.get("parameters") or []
            if code in (231, 232) and len(params) > 1:
                need("pictures", params[1])
            elif code == 241 and params and isinstance(params[0], dict):
                need("bgm", params[0].get("name"))
            elif code == 245 and params and isinstance(params[0], dict):
                need("bgs", params[0].get("name"))
            elif code in (249, 250) and params and isinstance(params[0], dict):
                need("me" if code == 249 else "se", params[0].get("name"))
            elif code == 261 and params:
                pass                      # movies live outside img/ and audio/
            elif code == 322 and len(params) > 3:
                need("characters", params[1])
                need("faces", params[3])
                if len(params) > 5 and side_view:
                    need("sv_actors", params[5])
            elif code == 140 and len(params) > 1 and isinstance(params[1], dict):
                need("bgm", params[1].get("name"))
            elif code == 323 and len(params) > 1:
                need("characters", params[1])
            elif code in (355, 655) and params and isinstance(params[0], str):
                for match in SCRIPT_AUDIO.finditer(params[0]):
                    try:
                        record = json.loads(match.group(3))
                    except ValueError:
                        continue
                    if isinstance(record, dict):
                        need(SCRIPT_AUDIO_KIND[match.group(2)], record.get("name"))
            elif code == 205 and len(params) > 1 and isinstance(params[1], dict):
                scan_route(params[1].get("list"))

    def scan_route(steps) -> None:
        for step in steps or []:
            params = step.get("parameters") or []
            if step.get("code") == 41 and params:
                need("characters", params[0])
            elif step.get("code") == 44 and params and isinstance(params[0], dict):
                need("se", params[0].get("name"))

    # In side view MV/MZ load enemies from sv_enemies/ and actors' battle
    # sheets from sv_actors/; a missing one stops the battle.
    side_view = bool((files.get("System.json") or {}).get("optSideView"))
    for actor in files.get("Actors.json") or []:
        if actor:
            need("characters", actor.get("characterName"))
            need("faces", actor.get("faceName"))
            if side_view:
                need("sv_actors", actor.get("battlerName"))
    for enemy in files.get("Enemies.json") or []:
        if enemy:
            need("sv_enemies" if side_view else "enemies", enemy.get("battlerName"))
    for animation in files.get("Animations.json") or []:
        if animation:
            need("animations", animation.get("animation1Name"))
            need("animations", animation.get("animation2Name"))
    for common in files.get("CommonEvents.json") or []:
        if common:
            scan(common.get("list"))

    system = files.get("System.json") or {}
    need("titles1", system.get("title1Name"))
    need("titles2", system.get("title2Name"))
    for key in ("titleBgm", "battleBgm"):
        need("bgm", (system.get(key) or {}).get("name"))
    for key in ("gameoverMe", "defeatMe", "victoryMe"):
        need("me", (system.get(key) or {}).get("name"))
    for sound in system.get("sounds") or []:
        need("se", (sound or {}).get("name"))
    for vehicle in ("boat", "ship", "airship"):
        record = system.get(vehicle) or {}
        need("characters", record.get("characterName"))
        need("bgm", (record.get("bgm") or {}).get("name"))

    for entry in sorted(os.listdir(data_dir)):
        if _map_id(entry) is None:
            continue
        payload = _load(os.path.join(data_dir, entry))
        need("parallaxes", payload.get("parallaxName"))
        need("bgm", (payload.get("bgm") or {}).get("name"))
        need("bgs", (payload.get("bgs") or {}).get("name"))
        for event in payload.get("events") or []:
            if not event:
                continue
            for page in event.get("pages") or []:
                need("characters", page.get("image", {}).get("characterName"))
                scan(page.get("list"))
                scan_route((page.get("moveRoute") or {}).get("list"))

    total = sum(len(v) for v in missing.values())
    if total:
        log.warning("%d asset name(s) are referenced but not present. MV stops "
                    "with a load error when it first needs one of these:", total)
        for kind in sorted(missing):
            if not missing[kind]:
                continue
            folder = "audio" if kind in ("bgm", "bgs", "me", "se") else "img"
            log.warning("   %s/%s (%d):", folder, kind, len(missing[kind]))
            for name in sorted(missing[kind]):
                log.warning("        %s", name)
    return total


# MV appends the extension itself, so only these count as loadable.  A
# leftover .wav or .mid with a matching stem does not help.
PLAYABLE_AUDIO = {".ogg", ".m4a"}
PLAYABLE_IMAGE = {".png", ".rpgmvp"}


def _listing(folder: str, extensions: set[str] | None = None) -> set[str]:
    try:
        entries = os.listdir(folder)
    except OSError:
        return set()
    out = set()
    for entry in entries:
        stem, ext = os.path.splitext(entry)
        if extensions is None or ext.lower() in extensions:
            out.add(stem)
    return out
