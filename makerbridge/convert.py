"""Drive the whole RM2k -> MV conversion."""

from __future__ import annotations

import json
import os
import re
import shutil

from . import assets
from .lcf import const
from .mv import (database, engine as engines, events, maps as mvmaps, plugin, troops,
                 svbattler)
from .mv.tiles import TilesetBuilder, SHEET_NAME_INDEX, build_group, chipset_arrays

SAFE_NAME = re.compile(r"[^A-Za-z0-9_\-]+")


def _safe(name: str, fallback: str) -> str:
    cleaned = SAFE_NAME.sub("_", name).strip("_")
    return cleaned or fallback


def _write_json(path: str, payload) -> int:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    return os.path.getsize(path)


def find_template(tool_root: str, exclude=()) -> str | None:
    """An existing MV or MZ project to borrow the engine runtime from,
    never one inside ``exclude`` (the conversion target)."""
    return engines.find_template(os.path.dirname(tool_root), exclude=exclude)


def convert_project(project, target: str, log, overwrite: bool = False,
                    skip_assets: bool = False, template: str | None = None) -> None:
    target = os.path.abspath(target)
    if os.path.isdir(target) and os.listdir(target) and not overwrite:
        raise SystemExit(
            f"target {target} is not empty; pass --overwrite to write into it")
    os.makedirs(os.path.join(target, "data"), exist_ok=True)

    tool_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if template and (engines._inside(template, target) or engines._inside(target, template)):
        log.warning("template %s overlaps the target %s; looking for another "
                    "one", template, target)
        template = None
    template = template or find_template(tool_root, exclude=[target])
    engine = engines.detect(template) if template else None
    if template and engine:
        log.info("target engine: %s (runtime from %s)", engine.label, template)
        _copy_runtime(engine, template, target, log)
    elif template:
        log.error("%s has neither js/rpg_core.js nor js/rmmz_core.js, so it is "
                  "not an MV or MZ project; its runtime was not copied", template)
    else:
        log.warning("no MV or MZ project found to copy the runtime from; "
                    "the output will contain data/ and img/ only")

    log.info("-- database --")
    data_files, id_maps = database.build(project, log)

    log.info("-- tilesets --")
    # Tilesets are generated rather than copied, so they are written even with
    # --skip-assets; that flag is about the bulk media copy.
    tilesets, tile_lookup, tile_runtime = _build_tilesets(project, target, id_maps, log,
                                            skip_assets=False)
    data_files["Tilesets.json"] = tilesets

    log.info("-- maps --")
    translator = events.Translator(id_maps, log,
                                   terms=project.database.get("terms", {}),
                                   database=project.database)
    map_infos = mvmaps.build_map_infos(project, id_maps, log)
    data_files["MapInfos.json"] = map_infos

    data_files["CommonEvents.json"] = _common_events(project, translator, id_maps)
    _place_troop_members(project, data_files["Troops.json"], data_files["Enemies.json"], log)
    for rm_id, troop in sorted(project.database.get("troops", {}).items()):
        pages = troops.build_pages(troop, translator, id_maps, project.encoding)
        if pages and rm_id in id_maps.troops:
            data_files["Troops.json"][id_maps.troops[rm_id]]["pages"] = pages

    reference = _load_reference_system(template)
    data_files["System.json"] = mvmaps.build_system(project, id_maps, reference, log)
    _untranslated_texts(data_files, template, log)
    if engine and engine.key == "mz":
        _name_placeholders(data_files)

    if project.database.get("_engine") == "rm2k3":
        # RM2003 fights in side view, so the converted project should too.
        data_files["System.json"]["optSideView"] = True
        # RM2003's ATB waits while a command menu is open: MZ's "time
        # progress (wait)".  MV has no such field and ignores it.
        data_files["System.json"]["battleSystem"] = 2
        sv_names = ({} if skip_assets
                    else svbattler.build_all(project, target, log))
        _assign_sv_battlers(project, data_files["Actors.json"], sv_names, log)

    total_events = 0
    for map_id in sorted(project.maps):
        if map_id not in id_maps.maps:
            continue
        data = project.maps[map_id]
        chipset_id = data["chipset_id"]
        tileset_id = id_maps.tilesets.get(chipset_id, 1)
        payload = mvmaps.build_map(project, map_id, data, tileset_id,
                                   tile_lookup.get(chipset_id, {}),
                                   translator, id_maps, log)
        total_events += sum(1 for e in payload["events"] if e)
        _write_json(os.path.join(target, "data", f"Map{map_id:03d}.json"), payload)
    log.info("wrote %d map(s), %d event(s)", len(id_maps.maps), total_events)

    for name, payload in data_files.items():
        size = _write_json(os.path.join(target, "data", name), payload)
        log.info("   data/%-18s %8d bytes", name, size)

    if not skip_assets:
        log.info("-- media --")
        assets.convert_images(project, target, log,
                              opaque_pictures=translator.opaque_pictures,
                              opaque_patterns=translator.opaque_patterns)
        _convert_frames(project, target, log)
        assets.copy_audio(project, target, log, me_names=_me_music(project, translator))
        assets.copy_movies(project, target, log)

    runtime_data = mvmaps.plugin_data(project, id_maps)
    runtime_data["tilesets"] = tile_runtime
    # MV draws 100 pictures; RM2003 numbers them up to 1000.
    runtime_data["maxPictures"] = max(
        100, translator.max_picture_id,
        1000 if translator.picture_ids_from_variables else 0)
    plugin.write(target, log, data=runtime_data)
    if engine:
        _stamp_title(target, data_files["System.json"].get("gameTitle") or "", log)
    _report_unsupported(translator, log)
    log.info("MV project written to %s", target)


def _me_music(project, translator) -> set[str]:
    """Music/ tracks the converted game plays as an ME (from audio/me):
    the victory, game over and inn themes, from the database and from
    "Change System BGM" commands."""
    from .lcf import model

    system = project.database.get("system", {})
    names = set(getattr(translator, "me_music", ()) or ())
    for key in ("battle_end_music", "gameover_music", "inn_music"):
        name = model.read_music(system.get(key) or "", project.encoding).get("name")
        if name:
            names.add(name)
    return names


def _assign_sv_battlers(project, actors: list, sv_names: dict, log) -> None:
    """Point each MV/MZ actor at the sheet its RM2003 class fights with.

    The chain is actor -> class -> the class's battle animation set.  That
    last hop is a real field, not the class id: in the reference project
    class 13 uses set 14 and class 14 uses set 13.
    """
    classes = project.database.get("classes") or {}
    rm_actors = sorted(project.database.get("actors") or {})
    assigned = 0
    for index, rm_id in enumerate(rm_actors, 1):
        if index >= len(actors) or not actors[index]:
            continue
        record = project.database["actors"][rm_id]
        class_id = record.get("class_id") or 0
        # EasyRPG Game_Actor::GetBattleAnimationId: the class's set when the
        # actor has a class, else the actor's own (liblcf default 1); 0 -> 1.
        if class_id and class_id in classes:
            set_id = classes[class_id].get("battler_animation") or 0
        else:
            set_id = record.get("battler_animation", 1)
        set_id = set_id or 1
        name = sv_names.get(set_id)
        if name:
            actors[index]["battlerName"] = name
            assigned += 1
    if sv_names:
        log.info("%d of %d actor(s) got a side-view battler", assigned,
                 len(rm_actors))


def _copy_runtime(engine, template: str, target: str, log) -> None:
    copied = []
    for item in engine.runtime_items:
        src = os.path.join(template, item)
        dst = os.path.join(target, item)
        if not os.path.exists(src):
            continue
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        copied.append(item)
    for folder in engine.runtime_img:
        src = os.path.join(template, "img", folder)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(target, "img", folder),
                            dirs_exist_ok=True)
    log.info("copied the %s runtime (%s)", engine.label, ", ".join(copied))


def _stamp_title(target: str, title: str, log) -> None:
    """Put the game's title where the template's own name would show.

    index.html and package.json come from the template, so the window and
    the browser tab are otherwise named after whatever project that was."""
    if not title:
        return
    page = os.path.join(target, "index.html")
    if os.path.isfile(page):
        with open(page, encoding="utf-8") as fh:
            html = fh.read()
        escaped = (title.replace("&", "&amp;").replace("<", "&lt;")
                   .replace(">", "&gt;"))
        stamped = re.sub(r"<title>.*?</title>", lambda _: f"<title>{escaped}</title>",
                         html, count=1, flags=re.S)
        if stamped != html:
            with open(page, "w", encoding="utf-8") as fh:
                fh.write(stamped)
    manifest_path = os.path.join(target, "package.json")
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
        except (OSError, ValueError):
            return
        # NW.js keeps the save data and settings under "name", so a name the
        # template already has stays; only an empty one is filled in.
        if not manifest.get("name"):
            manifest["name"] = title
        manifest.setdefault("window", {})["title"] = title
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=4, ensure_ascii=False)
    log.info("named the window and page %r", title)


def _load_reference_system(template: str | None) -> dict | None:
    if not template:
        return None
    path = os.path.join(template, "data", "System.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


CHANGE_CHIPSET = 11710       # RM2k "Change Chipset": parameters [chipset id]


def _chipset_changes(project, log) -> tuple[dict[int, set[int]], set[int]]:
    """Chipsets named in "Change Chipset" commands.

    Returns ({map id: targets used by that map's own events}, targets used
    by common events and battle events, which can run on any map)."""
    from .lcf.model import parse_array
    from .mv.troops import PAGE

    def targets(commands) -> set[int]:
        return {(c.get("parameters") or [1])[0] for c in commands or []
                if c.get("code") == CHANGE_CHIPSET and (c.get("parameters") or [1])[0] > 0}

    per_map: dict[int, set[int]] = {}
    for map_id, data in project.maps.items():
        found = set()
        for event in data.get("events", []) or []:
            for page in event.get("pages", []) or []:
                found |= targets(page.get("event_commands"))
        if found:
            per_map[map_id] = found
    anywhere: set[int] = set()
    for event in (project.database.get("common_events") or {}).values():
        anywhere |= targets(event.get("event_commands"))
    for troop in (project.database.get("troops") or {}).values():
        raw = troop.get("pages")
        if not raw:
            continue
        try:
            pages = parse_array(bytes.fromhex(raw), PAGE, project.encoding)
        except Exception:                         # noqa: BLE001 - best effort
            continue
        for page in pages.values():
            anywhere |= targets(page.get("event_commands"))
    return per_map, anywhere


def _chipset_groups(project, builders: dict, per_map: dict, anywhere: set,
                    log) -> list[list[int]]:
    """Chipsets that must share one tile id layout.

    A map that switches its chipset keeps its tile data, so the map's own
    chipset and every chipset it may switch to need the same ids for the
    same RM2k tile values.  Switches made by common or battle events can
    happen on any map; those targets are tied to every map chipset as long as
    the shared layout still fits MV's sheets, else only to each other."""
    from .mv.tiles import group_capacity_ok

    parent = {cid: cid for cid in builders}

    def find(c):
        while parent[c] != c:
            parent[c] = parent[parent[c]]
            c = parent[c]
        return c

    def union(a, b):
        parent[find(a)] = find(b)

    for map_id, found in per_map.items():
        own = project.maps[map_id]["chipset_id"]
        for target in found:
            if target in builders:
                union(own, target)
    if anywhere:
        trial = dict(parent)
        everything = sorted(c for c in anywhere | {d["chipset_id"] for d in project.maps.values()}
                            if c in builders)
        for cid in everything[1:]:
            union(everything[0], cid)
        if group_capacity_ok([builders[c] for c in everything]):
            log.info("Change Chipset in common/battle events: chipsets %s share "
                     "one tile layout", everything)
        else:
            parent.clear()
            parent.update(trial)
            ordered = sorted(c for c in anywhere if c in builders)
            for cid in ordered[1:]:
                union(ordered[0], cid)
            log.warning("Change Chipset in common/battle events (to %s): the "
                        "chipsets of all maps do not fit one shared tile "
                        "layout; after such a switch autotiles may show the "
                        "wrong pieces", ordered)
    groups: dict[int, list[int]] = {}
    for cid in sorted(builders):
        groups.setdefault(find(cid), []).append(cid)
    out = []
    for members in groups.values():
        if len(members) > 1 and not group_capacity_ok([builders[c] for c in members]):
            log.warning("chipsets %s are switched between by Change Chipset but "
                        "their autotiles do not fit one shared layout; built "
                        "separately", members)
            out += [[c] for c in members]
        else:
            out.append(members)
    return out


def _build_tilesets(project, target: str, id_maps, log, skip_assets: bool):
    chipsets = project.database.get("chipsets", {})
    used: dict[int, TilesetBuilder] = {}

    def builder(chipset_id: int) -> TilesetBuilder:
        if chipset_id not in used:
            used[chipset_id] = TilesetBuilder(
                project, chipset_id, chipsets.get(chipset_id, {}))
        return used[chipset_id]

    for data in project.maps.values():
        builder(data["chipset_id"]).note_map(data)
    # Chipsets reached only through "Change Chipset" need a tileset too,
    # carrying the autotile pieces of the maps that switch to them.
    per_map, anywhere = _chipset_changes(project, log)
    for map_id, found in per_map.items():
        for cid in found:
            if cid in chipsets:
                builder(cid).note_map(project.maps[map_id])
    for cid in anywhere:
        if cid in chipsets:
            builder(cid)
    missing = sorted(c for c in {c for f in per_map.values() for c in f} | anywhere
                     if c not in chipsets)
    if missing:
        log.warning("Change Chipset names chipset(s) %s that the database does "
                    "not have", missing)

    # MV ids follow the chipset ids, whatever order the groups get built in.
    mv_ids = {cid: index for index, cid in enumerate(sorted(used), 1)}
    id_maps.tilesets.update(mv_ids)
    out: list = [None] * (len(mv_ids) + 1)
    lookup: dict[int, dict[int, int]] = {}
    runtime: dict[int, dict] = {}
    image_dir = os.path.join(target, "img", "tilesets")
    os.makedirs(image_dir, exist_ok=True)
    # Chipset names are not unique ("Tech 4" twice, "wüste" and "w?ste" both
    # clean to the same stem), and the sheets are files named after them, so
    # a duplicate would silently overwrite the first chipset's images.
    # Windows compares file names case-insensitively, so the check does too.
    stems: dict[int, str] = {}
    stems_taken: set[str] = set()
    for chipset_id in sorted(used):
        record = chipsets.get(chipset_id, {})
        stem = _safe(record.get("name") or f"Chipset{chipset_id}", f"Chipset{chipset_id}")
        if stem.lower() in stems_taken:
            stem = f"{stem}_{chipset_id}"
        stems_taken.add(stem.lower())
        stems[chipset_id] = stem

    for members in _chipset_groups(project, used, per_map, anywhere, log):
        if len(members) > 1:
            log.info("   chipsets %s share one tile layout (Change Chipset)", members)
        # Built and written group by group: a project can have a hundred
        # chipsets, and their sheets together would not fit in memory.
        for chipset_id, build in zip(members, build_group([used[c] for c in members])):
            mv_id = mv_ids[chipset_id]
            lookup[chipset_id] = build.tile_ids
            stem = stems[chipset_id]
            names = [""] * 9
            for key, index in SHEET_NAME_INDEX.items():
                sheet = build.sheets.get(key)
                if sheet is None or sheet.getbbox() is None:
                    continue              # leave unused sheets unnamed
                names[index] = f"{stem}_{key}"
                if not skip_assets:
                    sheet.save(os.path.join(image_dir, f"{stem}_{key}.png"))
            build.sheets = {}
            out[mv_id] = {
                "id": mv_id,
                "name": build.name or f"Chipset {chipset_id}",
                "mode": 1,
                "note": f"converted from RM2k chipset {chipset_id}",
                "flags": build.flags,
                "tilesetNames": names,
            }
            runtime[mv_id] = _tileset_runtime(build, chipsets.get(chipset_id, {}))
            log.info("   tileset %d <- chipset %d (%s)", mv_id, chipset_id, stem)
    return out, lookup, runtime


# RM2k chipset passability bits: four directions, "above the hero".
PASS_DIRECTIONS, PASS_UPPER_MASK = 0x0F, 0x1F


def _tileset_runtime(build, chipset: dict) -> dict:
    """What RM2kCompat.js needs per tileset while playing.

    animation: which baked tiles cycle through which frames.
    terrain:   MV tile id -> RM2k terrain id, for the terrain features MV
               lacks (damage, bushes, vehicles, battle backgrounds); MV's own
               terrain tag only reaches 7.
    lower, upper: MV id of each plain chipset tile, for "tile substitution".
    """
    terrain_data, lower_pass, upper_pass = chipset_arrays(chipset)
    terrain, low, up = {}, {}, {}
    for value, mv_id in build.tile_ids.items():
        if not mv_id:
            continue
        if value >= const.BLOCK_UPPER:
            index = value - const.BLOCK_UPPER
            up[mv_id] = (upper_pass[index] if index < len(upper_pass) else 0x0F) & PASS_UPPER_MASK
            continue
        kind, slot, variation = const.decode_lower_tile(value)
        terrain[mv_id] = terrain_data[slot] if slot < len(terrain_data) else 1
        flags = lower_pass[slot] if slot < len(lower_pass) else 0x0F
        # RM2k: a "wall" terrain block lets everything onto the pieces whose
        # top edge is open (the walkable top of the wall).
        if kind == "terrain" and const.wall_top_open(slot, variation, flags):
            low[mv_id] = PASS_DIRECTIONS
        else:
            low[mv_id] = flags & PASS_DIRECTIONS
    return {
        "animation": build.animation,
        "terrain": terrain,
        # RM2k passability, checked by RM2kCompat.js with RM2k's own rule:
        # MV's flags cannot say "drawn above the hero, yet blocks this way".
        "pass": {"up": up, "low": low},
        "lower": [build.tile_ids.get(const.BLOCK_LOWER + i, 0) for i in range(const.N_LOWER_PLAIN)],
        "upper": [build.tile_ids.get(const.BLOCK_UPPER + i, 0) for i in range(const.N_UPPER_PLAIN)],
    }


def _common_events(project, translator, id_maps) -> list:
    table = project.database.get("common_events", {})
    highest = max(table) if table else 0
    out: list = [None] * (highest + 1)
    # RM2k trigger: 3 autostart, 4 parallel, 5 call -> MV 1 autorun, 2 parallel,
    # 0 none (checked against which common events the events call).
    trigger_map = {3: 1, 4: 2, 5: 0}
    # RM2k runs an autostart or parallel common event without a switch if
    # none is ticked; MV always tests one, so those get a switch that
    # RM2kCompat.js keeps on.
    always_on = always_on_switch(project)
    for rm_id, event in sorted(table.items()):
        id_maps.common_events[rm_id] = rm_id
        trigger = trigger_map.get(event.get("trigger", 0), 0)
        switch = event.get("switch_id", 1) if event.get("switch_flag") else always_on
        out[rm_id] = {
            "id": rm_id,
            "name": event.get("name", "") or f"Common {rm_id}",
            "switchId": max(1, switch) if trigger else 1,
            "trigger": trigger,
            "list": translator.translate(event.get("event_commands", []) or [],
                                         f"common event {rm_id}"),
        }
    for index, entry in enumerate(out):
        if entry is None and index:
            out[index] = {"id": index, "name": "", "switchId": 1, "trigger": 0,
                          "list": [{"code": 0, "indent": 0, "parameters": []}]}
    return out


def _place_troop_members(project, troop_list: list, enemy_list: list, log) -> None:
    """Move monsters from RM2k's 320x240 battle screen onto MV's.

    RM2k stores the centre of the monster's image; MV the middle of its
    bottom edge.  So the image height is needed, at the scale the monster
    pictures are converted with.
    """
    from .xyz import XyzError, open_image

    heights: dict[str, int] = {}

    def height(name: str) -> int:
        if name not in heights:
            heights[name] = 0
            path = project.find_asset("monster", name)
            if path:
                try:
                    heights[name] = open_image(path).size[1]
                except (OSError, XyzError):
                    pass
        return heights[name]

    for troop in troop_list:
        if not troop:
            continue
        for member in troop["members"]:
            enemy = enemy_list[member["enemyId"]] if member["enemyId"] < len(enemy_list) else None
            half = height(enemy["battlerName"]) // 2 if enemy and enemy["battlerName"] else 0
            member["x"] = round(member["x"] * assets.SCREEN_SCALE)
            member["y"] = round((member["y"] + half) * 624 / 240)


def _untranslated_texts(data_files: dict, template: str | None, log) -> None:
    """Drop RM2k's untranslated Japanese defaults from battle messages.

    Shown as they are they would be mojibake.  The death state's messages
    come from the MV/MZ template instead (same state id, same meaning);
    every other such message is left empty, which MV simply skips.
    """
    from .lcf.model import untranslated_japanese

    fallback = {}
    if template:
        path = os.path.join(template, "data", "States.json")
        try:
            with open(path, encoding="utf-8") as fh:
                states = json.load(fh)
            if len(states) > 1 and states[1]:
                fallback = states[1]
        except (OSError, ValueError):
            pass
    replaced = 0
    for table, keys in (("States.json", ("message1", "message2", "message3", "message4")),
                        ("Skills.json", ("message1", "message2"))):
        for entry in data_files.get(table) or []:
            if not entry:
                continue
            for key in keys:
                if untranslated_japanese(entry.get(key, "")):
                    use = fallback.get(key, "") if table == "States.json" and entry["id"] == 1 else ""
                    entry[key] = use
                    replaced += 1
    if replaced:
        log.info("replaced %d untranslated Japanese default message(s)", replaced)


def _name_placeholders(data_files: dict) -> None:
    """RM2k appends a battle message to the battler's name ("Kenzi, Trick
    gezaubert").  MV does the same, MZ only puts the name where the text
    says %1 - so for MZ it goes in front of every message that follows a
    name: a skill's first line and the four state messages."""
    def named(text: str) -> str:
        return text if not text or "%1" in text else "%1" + text

    for skill in data_files.get("Skills.json") or []:
        if skill:
            skill["message1"] = named(skill.get("message1", ""))
    for state in data_files.get("States.json") or []:
        if state:
            for key in ("message1", "message2", "message3", "message4"):
                state[key] = named(state.get(key, ""))


def always_on_switch(project) -> int:
    """The id after the project's last switch, reserved as "always on"."""
    return max(project.database.get("switches", {}) or [0]) + 1


def _convert_frames(project, target: str, log) -> None:
    """RM2003's screen frame overlays (Frame/), stretched to MV's screen."""
    from .xyz import IMAGE_EXTENSIONS, XyzError, open_image

    files = project.asset_files("frame", IMAGE_EXTENSIONS)
    if not files:
        return
    dest = os.path.join(target, "img", "system")
    os.makedirs(dest, exist_ok=True)
    written = 0
    for entry, path in files:
        stem = os.path.splitext(entry)[0]
        try:
            raw = open_image(path)
        except (OSError, XyzError) as exc:
            log.error("frame/%s could not be read: %s", entry, exc)
            continue
        image = assets._load_rgba(raw).resize((816, 624), 0)
        image.save(os.path.join(dest, "Frame_" + stem + ".png"))
        # RM2003 terrains can use frames as two scrolling battle layers;
        # EasyRPG (background.cpp) draws the back one opaque and only the
        # front one with palette index 0 see-through.
        for layer, picture in (("battlebacks1", raw.convert("RGBA").resize((816, 624), 0)),
                               ("battlebacks2", image)):
            folder = os.path.join(target, "img", layer)
            os.makedirs(folder, exist_ok=True)
            picture.save(os.path.join(folder, stem + ".png"))
        written += 1
    if written:
        log.info("img/system         %3d frame overlay(s) from frame/", written)


def _report_unsupported(translator, log) -> None:
    leftovers = translator.unsupported
    if not leftovers:
        log.info("every event command was translated")
        return
    total = sum(leftovers.values())
    log.warning("-- %d event command(s) could not be translated --", total)
    log.warning("   they became MV comments carrying the original parameters:")
    for code, count in leftovers.most_common():
        log.warning("      RM2k code %-6d x%d", code, count)
