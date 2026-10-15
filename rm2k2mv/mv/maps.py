"""Convert RM2k maps, the map tree and the system record into MV JSON."""

from __future__ import annotations

import copy
import logging
import struct

from ..lcf import model
from . import battlecmd
from .database import _audio, _clamp

log = logging.getLogger(__name__)

MV_LAYERS = 6          # MV stores width*height*6 tile slots
LAYER_GROUND = 0
LAYER_UPPER = 2

# RM2k facing (0 up, 1 right, 2 down, 3 left) -> MV (8 up, 6 right, 2 down, 4 left)
DIRECTION = {0: 8, 1: 6, 2: 2, 3: 4}
# RM2k move type -> MV moveType (0 fixed, 1 random, 2 approach, 3 custom)
MOVE_TYPE = {0: 0, 1: 1, 4: 2, 6: 3}

# RM2k page condition flag bits
COND_SWITCH_A = 0x01
COND_SWITCH_B = 0x02
COND_VARIABLE = 0x04
COND_ITEM = 0x08
COND_ACTOR = 0x10
COND_TIMER = 0x20
COND_TIMER2 = 0x40         # RM2003

# RM2k map tree: music 0 "same as parent", 1 "left to events", 2 its own.
MUSIC_PARENT, MUSIC_EVENT, MUSIC_OWN = 0, 1, 2
MAP_TYPE_AREA = 2
LAYER_REGION = 5
DEFAULT_ENCOUNTER_STEPS = 25
ENCOUNTER_WEIGHT = 10
# RM2k "move type" 2 up/down, 3 left/right and 5 away from the hero have no
# MV move type; they become repeating custom routes.
MOVE_VERTICAL, MOVE_HORIZONTAL, MOVE_AWAY = 2, 3, 5
MV_MOVE_CUSTOM = 3
# RM2k animation type 5 turns the event round on the spot.
ANIM_SPIN = 5
# RM2k draws a "translucent" event at 5/8 opacity.
TRANSLUCENT_OPACITY = 160


def build_map_infos(project, id_maps, log) -> list:
    infos = project.maptree.get("map_infos", {})
    highest = max(infos) if infos else 0
    out: list = [None] * (highest + 1)
    skipped_areas = 0
    order = {map_id: pos for pos, map_id in
             enumerate(project.maptree.get("tree_order", []), 1)}

    for map_id, info in sorted(infos.items()):
        if map_id == 0:
            continue
        if info.get("type", 1) == 2:
            skipped_areas += 1
            continue
        if map_id not in project.maps:
            log.warning("map tree lists map %d (%r) but there is no .lmu file",
                        map_id, info.get("name", ""))
            continue
        id_maps.maps[map_id] = map_id
        out[map_id] = {
            "id": map_id,
            "name": info.get("name", f"MAP{map_id:03d}"),
            "parentId": info.get("parent_id", 0),
            "order": order.get(map_id, map_id),
            "expanded": bool(info.get("expanded_node", False)),
            "scrollX": 0,
            "scrollY": 0,
        }
    for entry in out:
        if entry and entry["parentId"] and (entry["parentId"] >= len(out)
                                            or out[entry["parentId"]] is None):
            # The parent is an area, the root or a map without .lmu file.
            entry["parentId"] = 0
    if skipped_areas:
        log.info("skipped %d map-tree area(s); MV has no equivalent", skipped_areas)
    return out


def build_map(project, map_id: int, data: dict, tileset_id: int,
              tile_ids: dict[int, int], translator, id_maps, log) -> dict:
    width, height = data["width"], data["height"]
    grid = [0] * (width * height * MV_LAYERS)

    missing = set()
    for position, value in enumerate(data["lower_layer"]):
        mv_id = tile_ids.get(value)
        if mv_id is None:
            missing.add(value)
            continue
        grid[LAYER_GROUND * width * height + position] = mv_id
    for position, value in enumerate(data["upper_layer"]):
        mv_id = tile_ids.get(value)
        if mv_id is None:
            missing.add(value)
            continue
        grid[LAYER_UPPER * width * height + position] = mv_id
    if missing:
        log.warning("map %d: %d tile id(s) had no tileset slot: %s",
                    map_id, len(missing), sorted(missing)[:10])

    music, autoplay = _map_music(project, map_id)
    encounters, steps = _encounters(project, map_id, grid, width, height, id_maps)
    battleback = _map_battleback(project, map_id)

    return {
        "autoplayBgm": autoplay,
        "autoplayBgs": False,
        "battleback1Name": battleback,
        "battleback2Name": "",
        "bgm": _audio(music),
        "bgs": _audio(None, 0),
        "disableDashing": True,         # RM2k has no dashing
        "displayName": "",
        "encounterList": encounters,
        "encounterStep": steps,
        # Encounter rate 0: no random battles until an event changes it.
        "rm2kEncounterOff": (project.map_info(map_id).get("encounter_steps") or 0) <= 0
        and project.map_info(map_id).get("encounter_steps") is not None,
        "height": height,
        "width": width,
        "note": f"converted from RM2k Map{map_id:04d}.lmu",
        "parallaxLoopX": data.get("parallax_loop_x", False),
        "parallaxLoopY": data.get("parallax_loop_y", False),
        "parallaxName": data.get("parallax_name", "") if data.get("parallax_flag") else "",
        "parallaxShow": True,
        # RM2k only scrolls the background by itself with "auto scroll" on.
        "parallaxSx": parallax_speed(data.get("parallax_sx", 0)) if data.get("parallax_auto_x") else 0,
        "parallaxSy": parallax_speed(data.get("parallax_sy", 0)) if data.get("parallax_auto_y") else 0,
        "scrollType": _clamp(data.get("scroll_type", 0), 0, 3),
        "specifyBattleback": bool(battleback),
        "tilesetId": tileset_id,
        "data": grid,
        "events": _events(data, translator, id_maps, map_id, log, tile_ids),
        # Whether teleport, escape and saving work here; RM2kCompat.js.
        "rm2kPermissions": {key: _permission(project, map_id, key)
                            for key in ("teleport", "escape", "save")},
    }


# RM2k map tree permissions: 0 same as the parent map, 1 allowed, 2 not.
PERMIT_PARENT, PERMIT_YES, PERMIT_NO = 0, 1, 2


def _map_battleback(project, map_id: int) -> str:
    """The map's own battle background: "same as parent" walks up the map
    tree, "terrain" leaves it to the terrain (EasyRPG Game_Map::SetupBattle)."""
    seen = set()
    while map_id and map_id not in seen:
        seen.add(map_id)
        info = project.map_info(map_id)
        kind = info.get("background_type", 0)
        if kind == 2:
            return info.get("background_name", "")
        if kind == 1:
            break
        map_id = info.get("parent_id", 0)
    return ""


def _permission(project, map_id: int, key: str) -> bool:
    seen = set()
    while map_id and map_id not in seen:
        seen.add(map_id)
        info = project.map_info(map_id)
        value = info.get(key) or PERMIT_PARENT
        if value != PERMIT_PARENT:
            return value == PERMIT_YES
        map_id = info.get("parent_id", 0)
    return True


def _map_music(project, map_id: int) -> tuple[dict, bool]:
    """The music MV should start on entering the map, and whether to.

    "Same as parent" walks up the map tree; "left to events" means the map
    does not touch the music at all.
    """
    seen = set()
    while map_id and map_id not in seen:
        seen.add(map_id)
        info = project.map_info(map_id)
        kind = info.get("music_type", MUSIC_PARENT)
        if kind == MUSIC_OWN:
            music = model.read_music(info.get("music", ""), project.encoding)
            return _audio(music), True
        if kind == MUSIC_EVENT:
            break
        map_id = info.get("parent_id", 0)
    return _audio(None), False


def _troop_ids(info: dict, id_maps, with_rm: bool = False) -> list:
    raw = info.get("encounters") or ""
    if not raw or raw == "00":
        return []
    entries = model.parse_array(bytes.fromhex(raw), {0x01: ("troop_id", "int")}, "cp1252")
    out = []
    for entry in entries.values():
        rm_id = entry.get("troop_id", 0)
        troop = id_maps.troops.get(rm_id)
        if troop:
            out.append((rm_id, troop) if with_rm else troop)
    return out


MAX_REGION = 255


def _encounters(project, map_id: int, grid: list, width: int, height: int,
                id_maps) -> tuple[list, int]:
    """Random battles of the map and of the areas drawn on it.

    RPG_RT picks from every troop of the map plus those of every area
    covering the hero's square, leaving out troops whose terrain set
    excludes the terrain under the hero (EasyRPG Game_Map::GetEncountersAt).
    MV has regions for that: each distinct combination of covering areas
    (and, where some troop cares, terrain) gets a region painted into the
    region layer, and every troop lists all regions it may appear in.
    """
    from .tiles import chipset_arrays
    from ..lcf import const

    info = project.map_info(map_id)
    # liblcf: a missing value means 25; 0 switches random battles off.
    steps = info.get("encounter_steps")
    steps = DEFAULT_ENCOUNTER_STEPS if steps is None else steps
    # The troops are kept: "Change Encounter Rate" can switch battles on
    # later (RM2kCompat.js reads "rm2kEncounterOff").
    off = steps <= 0
    steps = DEFAULT_ENCOUNTER_STEPS if off else steps

    troops_db = project.database.get("troops", {})

    def terrain_ok(rm_troop: int, terrain: int) -> bool:
        terrain_set = (troops_db.get(rm_troop) or {}).get("terrain_set") or []
        return terrain - 1 >= len(terrain_set) or terrain < 1 or bool(terrain_set[terrain - 1])

    def restricted(rm_troop: int) -> bool:
        terrain_set = (troops_db.get(rm_troop) or {}).get("terrain_set") or []
        return not all(terrain_set)

    own = _troop_ids(info, id_maps, with_rm=True)
    areas = []                                    # [(rect, troops)]
    for area_id, area in sorted(project.maptree.get("map_infos", {}).items()):
        if area.get("type") != MAP_TYPE_AREA or area.get("parent_id") != map_id:
            continue
        troops = _troop_ids(area, id_maps, with_rm=True)
        rect = bytes.fromhex(area.get("area_rect") or "")
        if troops and len(rect) == 16:
            areas.append((struct.unpack("<4i", rect), troops))

    by_terrain = any(restricted(rm) for rm, _ in own) or any(
        restricted(rm) for _, troops in areas for rm, _ in troops)
    everywhere = any(restricted(rm) for rm, _ in own)

    terrain_at = None
    if by_terrain:
        data = project.maps.get(map_id) or {}
        chipset = project.database.get("chipsets", {}).get(data.get("chipset_id"), {})
        terrain_data = chipset_arrays(chipset)[0]
        lower = data.get("lower_layer") or []

        def _terrain(x, y):
            try:
                slot = const.decode_lower_tile(lower[y * width + x])[1]
            except (IndexError, ValueError):
                slot = 0
            return terrain_data[slot] if slot < len(terrain_data) else 1
        terrain_at = _terrain

    keys: dict[tuple, int] = {}
    cell_keys = {}
    for y in range(height):
        for x in range(width):
            covering = frozenset(i for i, ((left, top, right, bottom), _) in enumerate(areas)
                                 if left <= x < right and top <= y < bottom)
            if not covering and not everywhere:
                continue
            key = (covering, terrain_at(x, y) if terrain_at else None)
            cell_keys[(x, y)] = key
            if key not in keys:
                keys[key] = len(keys) + 1
    if len(keys) > MAX_REGION:
        log.warning("map %d: %d area/terrain combinations for random battles, "
                    "MV has %d regions; terrain limits on troops are ignored",
                    map_id, len(keys), MAX_REGION)
        keys, cell_keys, terrain_at, everywhere = {}, {}, None, False
        for y in range(height):
            for x in range(width):
                covering = frozenset(i for i, ((left, top, right, bottom), _) in enumerate(areas)
                                     if left <= x < right and top <= y < bottom)
                if covering:
                    key = (covering, None)
                    cell_keys[(x, y)] = key
                    keys.setdefault(key, len(keys) + 1)
        if len(keys) > MAX_REGION:
            log.warning("map %d: more than %d overlapping area combinations; "
                        "areas past that get no random battles", map_id, MAX_REGION)
    for (x, y), key in cell_keys.items():
        region = keys[key]
        if region <= MAX_REGION:
            grid[(LAYER_REGION * height + y) * width + x] = region

    def regions(source, rm_troop) -> list[int]:
        return sorted(r for (covering, terrain), r in keys.items()
                      if r <= MAX_REGION
                      and (source is None or source in covering)
                      and (terrain is None or terrain_ok(rm_troop, terrain)))

    encounters = []
    for rm_troop, troop in own:
        if everywhere and terrain_at and restricted(rm_troop):
            region_set = regions(None, rm_troop)
            if not region_set:
                continue           # its terrains never occur here
        else:
            region_set = []        # anywhere on the map
        encounters.append({"regionSet": region_set, "troopId": troop,
                           "weight": ENCOUNTER_WEIGHT})
    for index, (_, troops) in enumerate(areas):
        for rm_troop, troop in troops:
            region_set = regions(index, rm_troop)
            if region_set:
                encounters.append({"regionSet": region_set, "troopId": troop,
                                   "weight": ENCOUNTER_WEIGHT})
    return encounters, max(1, steps)


def _events(data: dict, translator, id_maps, map_id: int, log,
            tile_ids: dict[int, int] | None = None) -> list:
    events = data.get("events", [])
    highest = max((e["id"] for e in events), default=0)
    out: list = [None] * (highest + 1)
    for event in events:
        pages = [_page(p, translator, f"map {map_id} event {event['id']}",
                       id_maps, tile_ids or {})
                 for p in event.get("pages", [])]
        if not pages:
            pages = [_page({}, translator, "", id_maps, tile_ids or {})]
        out[event["id"]] = {
            "id": event["id"],
            "name": event.get("name", "") or f"EV{event['id']:03d}",
            "note": "",
            "x": event.get("x", 0),
            "y": event.get("y", 0),
            "pages": pages,
        }
    return out


# RM2k3 page condition chunk 0x0A: how the variable is compared.  Missing
# means ">=", the only comparison RM2k 2000 and MV know.
COND_VARIABLE_OP = "0x0A"
VARIABLE_OP_GE = 1


def _conditions(condition: dict, flags: int, id_maps=None) -> dict:
    actor = condition.get("actor_id", 1) or 1
    item = condition.get("item_id", 1) or 1
    mapped_item = id_maps.items.get(item) if id_maps else None
    out = {
        "actorId": id_maps.actors.get(actor, actor) if id_maps else actor,
        "actorValid": bool(flags & COND_ACTOR),
        "itemId": mapped_item[1] if mapped_item else item,
        "itemValid": bool(flags & COND_ITEM),
        "selfSwitchCh": "A",
        "selfSwitchValid": False,
        "switch1Id": condition.get("switch_a_id", 1) or 1,
        "switch1Valid": bool(flags & COND_SWITCH_A),
        "switch2Id": condition.get("switch_b_id", 1) or 1,
        "switch2Valid": bool(flags & COND_SWITCH_B),
        "variableId": condition.get("variable_id", 1) or 1,
        "variableValid": bool(flags & COND_VARIABLE),
        "variableValue": condition.get("variable_value", 0),
    }
    raw_op = (condition.get("_unknown") or {}).get(COND_VARIABLE_OP)
    if raw_op and out["variableValid"]:
        op = int(raw_op[:2], 16)
        # MV ignores keys it does not know; RM2kCompat.js reads this one
        # (0 =, 1 >=, 2 <=, 3 >, 4 <, 5 !=).
        if op != VARIABLE_OP_GE:
            out["rm2kVariableOp"] = op
    if out["itemValid"] and mapped_item and mapped_item[0] != "item":
        # MV pages only test items; weapons and armour go to RM2kCompat.js.
        out["itemValid"] = False
        out["rm2kEquipItem"] = list(mapped_item)
    # "Timer at most n seconds": MV pages cannot test the timer.
    # Both timers can be required at once; RM2kCompat.js checks each.
    if flags & COND_TIMER:
        out["rm2kTimer"] = condition.get("timer_sec", 0)
    if flags & COND_TIMER2:
        out["rm2kTimer2"] = condition.get("timer2_sec", 0)
    return out


def _page(page: dict, translator, where: str, id_maps=None,
          tile_ids: dict[int, int] | None = None) -> dict:
    condition = page.get("condition", {}) or {}
    flags = condition.get("flags", 0)
    route = page.get("move_route", {}) or {}
    frequency = page.get("move_frequency", 3)
    move_type = page.get("move_type", 0)
    name = page.get("character_name", "") or ""
    # Without a sprite sheet the index picks a tile of the chipset's upper
    # layer, drawn in the event's place.
    tile = 0 if name else (tile_ids or {}).get(10000 + (page.get("character_index") or 0), 0)
    move_route = _move_route(route, translator, frequency)
    if move_type in (MOVE_VERTICAL, MOVE_HORIZONTAL):
        axis = "true" if move_type == MOVE_VERTICAL else "false"
        move_route = {"list": [{"code": 45, "parameters": [f"this.rm2kMoveAxis({axis});"]},
                               {"code": 0, "parameters": []}],
                      "repeat": True, "skippable": True, "wait": False}
    elif move_type == MOVE_AWAY:
        move_route = {"list": [{"code": 11, "parameters": []}, {"code": 0, "parameters": []}],
                      "repeat": True, "skippable": True, "wait": False}
    page_out = {
        "conditions": _conditions(condition, flags, id_maps),
        "directionFix": page.get("animation_type", 0) in (2, 3, 4),
        "image": {
            "characterIndex": (page.get("character_index") or 0) if name else 0,
            "characterName": name,
            "direction": DIRECTION.get(page.get("character_direction", 2), 2),
            "pattern": _clamp(page.get("character_pattern", 1), 0, 2),
            "tileId": tile,
        },
        "list": translator.translate(page.get("event_commands", []) or [], where),
        "moveFrequency": _clamp(page.get("move_frequency", 3), 1, 5),
        "moveRoute": move_route,
        "moveSpeed": _clamp(page.get("move_speed", 3), 1, 6),
        "moveType": MOVE_TYPE.get(move_type, MV_MOVE_CUSTOM),
        "priorityType": _clamp(page.get("layer", 1), 0, 2),
        "stepAnime": page.get("animation_type", 0) in (1, 3),
        # MV decides event collision from priorityType, exactly as RM2k decides
        # it from the layer, so "through" stays off and the layer does the work.
        "through": False,
        "trigger": _clamp(page.get("trigger", 0), 0, 4),
        "walkAnime": page.get("animation_type", 0) not in (4, 5),
    }
    # MV pages have no opacity or spinning; RM2kCompat.js reads these.
    if page.get("translucent"):
        page_out["rm2kOpacity"] = TRANSLUCENT_OPACITY
    if page.get("animation_type", 0) == ANIM_SPIN:
        page_out["rm2kSpin"] = True
    if page.get("overlap_forbidden"):
        page_out["rm2kNoOverlap"] = True
    return page_out


def _move_route(route: dict, translator, frequency: int = 8) -> dict:
    return {
        "list": translator.move_steps(route.get("commands", []) or [], frequency),
        "repeat": bool(route.get("repeat", True)),
        "skippable": bool(route.get("skippable", False)),
        "wait": False,
    }


# --- System.json ------------------------------------------------------------

def _battle_set(db: dict, actor: dict) -> int:
    """A hero's battle animation set: its class's, else its own (EasyRPG
    Game_Actor::GetBattleAnimationId; liblcf defaults 1)."""
    klass = (db.get("classes") or {}).get(actor.get("class_id") or 0)
    set_id = klass.get("battler_animation") if klass is not None else actor.get("battler_animation")
    return 1 if set_id is None else set_id


def _pose_strips(project, id_maps) -> dict:
    from . import svbattler
    db = project.database
    if db.get("_engine") != "rm2k3":
        return {}
    by_set = svbattler.custom_poses(project)
    return {id_maps.actors[rm_id]: by_set[str(_battle_set(db, actor))]
            for rm_id, actor in (db.get("actors") or {}).items()
            if rm_id in id_maps.actors and str(_battle_set(db, actor)) in by_set}


def _pose_animations(project, id_maps) -> dict:
    """The battle animation set of each hero: its class's, else its own
    (EasyRPG Game_Actor::GetBattleAnimationId; liblcf defaults 1)."""
    from . import svbattler
    db = project.database
    if db.get("_engine") != "rm2k3":
        return {}
    by_set = svbattler.pose_animations(project, id_maps.animations)
    classes = db.get("classes") or {}
    out = {}
    for rm_id, actor in (db.get("actors") or {}).items():
        klass = classes.get(actor.get("class_id") or 0)
        if klass is not None:
            set_id = klass.get("battler_animation")
        else:
            set_id = actor.get("battler_animation")
        motions = by_set.get(str(1 if set_id is None else set_id))
        if motions and rm_id in id_maps.actors:
            out[id_maps.actors[rm_id]] = motions
    return out


def plugin_data(project, id_maps) -> dict:
    """What RM2kCompat.js needs from the database at runtime."""
    db = project.database
    system = db.get("system", {})
    actors = {}
    for rm_id, actor in db.get("actors", {}).items():
        commands = battlecmd.actor_commands(actor)
        if commands is not None and rm_id in id_maps.actors:
            actors[id_maps.actors[rm_id]] = commands
    class_commands = {}
    for rm_id, record in db.get("classes", {}).items():
        commands = battlecmd.actor_commands(record)
        if commands is not None and rm_id in id_maps.classes:
            class_commands[id_maps.classes[rm_id]] = commands
    return {
        "rm2k3": db.get("_engine") == "rm2k3",
        # "Fight / Auto / Escape": the name of RPG_RT's auto battle option.
        "autoBattleTerm": (db.get("terms") or {}).get("0x66") or "Auto",
        # RM2003 battle poses that are a battle animation: actor -> motion -> id.
        "poseAnimations": _pose_animations(project, id_maps),
        # RM2003 poses past the standard twelve: actor -> pose -> strip file
        # in img/sv_actors ("" = nothing drawn, the hero is invisible).
        "poseStrips": _pose_strips(project, id_maps),
        # RM2003 1.11+ can start the game without the title screen.
        "showTitle": bool(system.get("show_title", True)),
        # RM2003 heroes stand where the database puts them in battle.
        "actorBattle": {id_maps.actors[rm_id]: [actor.get("battle_x") or 220,
                                                actor.get("battle_y") or 120]
                        for rm_id, actor in db.get("actors", {}).items()
                        if rm_id in id_maps.actors}
                       if db.get("_engine") == "rm2k3" else {},
        "terrains": _terrains(db, project.encoding),
        "alwaysOnSwitch": max(db.get("switches", {}) or [0]) + 1,
        # RM2003 screen frame overlay, converted to img/system/Frame_<name>.
        "frame": ("Frame_" + system.get("frame_name", "")) if system.get("show_frame")
                 and system.get("frame_name") else "",
        "classCommands": class_commands,
        # RM2k item id -> [kind, MV id], for commands that take the item
        # from a variable at run time.
        "items": {str(k): list(v) for k, v in id_maps.items.items()},
        # MV skill id = RM2k skill id + this (MV reserves the first ones).
        "skillOffset": min(id_maps.skills.values(), default=1) - min(id_maps.skills, default=1),
        # System transitions: teleport out/in, battle start out/in, end out/in.
        "transitions": [system.get(k, 0) or 0 for k in (
            "transition_out", "transition_in", "battle_start_fadeout",
            "battle_start_fadein", "battle_end_fadeout", "battle_end_fadein")],
        "commands": {str(k): v for k, v in id_maps.battle_commands.items()},
        "actors": actors if id_maps.battle_commands else {},
        # A picture's RPG_RT flags unless RM2003 1.10+ sets its own: 1 erase
        # on map change, 2 erase at battle end, 16/32/64 affected by screen
        # tint / flash / shake (EasyRPG Game_Pictures::ShowParams).
        "pictureFlags": 1 | 32 | 64,
        # The updated runtimes (RM2000 Value!, RM2003 1.05+) draw battle
        # animations above pictures; the old ones draw pictures on top and
        # ignore the position when moving a picture fixed to the map.
        "picturesBelowAnimations": bool(db.get("_major_updated")),
        "picturesFixedMoveBug": not db.get("_major_updated"),
        # Before the English updates RPG_RT holds picture commands back
        # while a message is open (EasyRPG: CommandShowPicture).
        "picturesWaitForMessage": not db.get("_english"),
        "textColors": _text_colors(project, system.get("system_name", "")),
        "innMusic": _shipped_music(project, system.get("inn_music", "")),
    }


def _shipped_music(project, raw: str) -> dict:
    """A music record for RM2kCompat.js, blanked when the track exists
    neither in the game nor in the RTP: the plugin hands it straight to
    AudioManager, and MV stops with a load error on a missing file."""
    from ..assets import AUDIO_EXT

    track = _audio(model.read_music(raw, project.encoding))
    name = track.get("name")
    if name and name.lower() != "(off)" and not project.find_asset("music", name, AUDIO_EXT):
        track["name"] = ""
    return track


def _text_colors(project, system_name: str) -> list[str]:
    """The 20 message colours of RM2k's system graphic, as CSS colours.

    \\C[n] picks one of them; they sit in the bottom two rows of the 160x80
    sheet, ten 16px cells per row, each a vertical gradient - its average is
    what the text looks like from a distance.
    """
    path = project.find_asset("system", system_name)
    if not path:
        return []
    from ..xyz import XyzError, open_image
    try:
        image = open_image(path).convert("RGB")
    except (OSError, XyzError):
        return []
    if image.size != (160, 80):
        return []
    colors = []
    for n in range(20):
        x, y = (n % 10) * 16, 48 + (n // 10) * 16
        cell = list(image.crop((x, y, x + 16, y + 16)).getdata())
        r, g, b = (sum(p[i] for p in cell) // len(cell) for i in range(3))
        colors.append(f"#{r:02x}{g:02x}{b:02x}")
    return colors


def _terrain_layers(terrain: dict, get) -> list:
    layers = []
    for key in ("a", "b"):
        if key == "b" and not get("background_b", False):
            break
        layers.append([
            get(f"background_{key}_name", ""),
            parallax_speed(get(f"background_{key}_scrollh_speed", 0))
            if get(f"background_{key}_scrollh", False) else 0,
            parallax_speed(get(f"background_{key}_scrollv_speed", 0))
            if get(f"background_{key}_scrollv", False) else 0,
        ])
    return layers


def parallax_speed(rm_speed: int) -> float:
    """RM2k scroll speed (-8..8) -> MV parallax speed.

    RPG_RT moves a panorama by 2^|speed| sixteenths of a pixel every frame,
    halved on screen (EasyRPG: Game_Map::Parallax), in 320x240 pixels.  MV
    moves it by speed / 4 of its own pixels, and the panoramas are scaled by
    3: so MV speed = 4 * 3 * 2^|s| / 32.  A positive speed scrolls the
    image to the left in both.
    """
    if not rm_speed:
        return 0
    magnitude = 3 * (1 << min(abs(rm_speed), 8)) / 8
    return magnitude if rm_speed > 0 else -magnitude


def _terrains(db: dict, encoding: str) -> dict:
    """RM2k terrains with the defaults the file leaves out."""
    out = {}
    for rm_id, terrain in db.get("terrains", {}).items():
        def get(key, default):
            value = terrain.get(key)
            return default if value is None else value
        step = model.read_sound(terrain.get("footstep") or "", encoding)
        out[rm_id] = {
            "damage": get("damage", 0),
            "encounterRate": get("encounter_rate", 100),
            "background": get("background_name", ""),
            "boat": bool(get("boat_pass", False)),
            "ship": bool(get("ship_pass", False)),
            "airshipPass": bool(get("airship_pass", True)),
            "airshipLand": bool(get("airship_land", True)),
            "bush": get("bush_depth", 0),
            "footstep": _audio(step, 100) if step.get("name") and
                        step["name"].strip().lower() != "(off)" else None,
            "damageSound": bool(get("on_damage_se", False)),
            # RM2003 layered backgrounds: [name, scroll x, scroll y] per layer.
            "layers": _terrain_layers(terrain, get) if get("background_type", 0) == 1 else None,
        }
    return out


# What a reference MV/MZ project may contribute to System.json: engine and
# editor settings only.  Everything about *that* game (its weapon types,
# test battlers, autosave, ids, encryption) stays out.
REFERENCE_SYSTEM_KEYS = (
    "advanced", "attackMotions", "editor", "equipTypes", "faceSize",
    "iconSize", "itemCategories", "magicSkills", "menuCommands",
    "optExtraExp", "optFloorDeath", "optKeyItemsNumber", "optMessageSkip",
    "optSlipDeath", "optSplashScreen", "skillTypes", "sounds", "terms",
    "tileSize", "titleCommandWindow", "windowTone", "currencyUnit",
)
# Keys of "advanced" that identify the reference game rather than the engine.
_ADVANCED_IDENTITY = ("gameId",)

# Code page -> MV/MZ locale.  The locale only picks the language family
# (MZ: Japanese/Chinese/Korean/Russian text handling and fonts).
_LOCALES = {
    "cp932": "ja_JP", "shift_jis": "ja_JP", "euc_jp": "ja_JP",
    "gbk": "zh_CN", "gb2312": "zh_CN", "cp936": "zh_CN", "gb18030": "zh_CN",
    "big5": "zh_TW", "cp950": "zh_TW",
    "cp949": "ko_KR", "euc_kr": "ko_KR",
    "cp1251": "ru_RU", "koi8_r": "ru_RU", "cp866": "ru_RU",
    "cp1250": "pl_PL", "cp1253": "el_GR", "cp1254": "tr_TR",
    "cp1255": "he_IL", "cp1256": "ar_SA", "cp1257": "lt_LT",
    "cp874": "th_TH", "cp1258": "vi_VN",
}
_NON_WESTERN = ("ja", "zh", "ko", "ru", "el", "he", "ar", "th", "vi", "tr", "pl", "lt")


def locale_for(encoding: str, reference: str | None = None) -> str:
    """MV/MZ locale for a project read with ``encoding``.

    A Western code page (cp1252) does not say which language: the
    reference project's locale is kept when it is a Western one too (most
    likely the user's own editor language), else en_US."""
    import codecs

    try:
        name = codecs.lookup(encoding).name
    except LookupError:
        name = encoding.lower()
    name = name.replace("-", "_")
    if name in _LOCALES:
        return _LOCALES[name]
    if reference and isinstance(reference, str) and \
            reference.split("_")[0].lower() not in _NON_WESTERN:
        return reference
    return "en_US"


def _reference_base(reference: dict | None) -> dict:
    import random

    base = _blank_system()
    for key in REFERENCE_SYSTEM_KEYS:
        if reference and key in reference:
            base[key] = copy.deepcopy(reference[key])
    if isinstance(base.get("advanced"), dict):
        for key in _ADVANCED_IDENTITY:
            base["advanced"].pop(key, None)
        # A fresh id: MZ keys save files and local storage on it, so a
        # shared one would let two games read each other's saves.
        base["advanced"]["gameId"] = random.randint(10_000_000, 99_999_999)
    base["versionId"] = random.randint(10_000_000, 99_999_999)
    return base


def build_system(project, id_maps, reference: dict | None, log) -> dict:
    db = project.database
    system = db.get("system", {})
    terms = db.get("terms", {})
    start = project.maptree.get("start", {})
    encoding = project.encoding

    base = _reference_base(reference)
    ref_locale = (reference or {}).get("locale")
    # An empty starting party is a real setting, not missing data: plenty of
    # RM2k projects assemble the party through events.  Substituting actor 1
    # would hand the player a hero the original never gave them.
    actors = [id_maps.actors.get(a) for a in (system.get("party") or [])]
    actors = [a for a in actors if a]
    if not actors:
        log.info("the project starts with an empty party; leaving it empty")

    base.update({
        "gameTitle": project.game_title,
        "startMapId": id_maps.maps.get(start.get("party_map_id", 1),
                                       start.get("party_map_id", 1)),
        "startX": start.get("party_x", 0),
        "startY": start.get("party_y", 0),
        "partyMembers": actors,
        "title1Name": system.get("title_name", ""),
        "title2Name": "",
        "battleback1Name": "",
        "battleback2Name": "",
        "optSideView": False,
        "locale": locale_for(encoding, ref_locale),
        "switches": _names(db.get("switches", {}), "Switch") + ["RM2k: always on"],
        "variables": _names(db.get("variables", {}), "Variable"),
        "titleBgm": _audio(model.read_music(system.get("title_music", ""), encoding)),
        "battleBgm": _audio(model.read_music(system.get("battle_music", ""), encoding)),
        "gameoverMe": _audio(model.read_music(system.get("gameover_music", ""), encoding)),
        "defeatMe": _audio(model.read_music(system.get("gameover_music", ""), encoding)),
        "victoryMe": _audio(model.read_music(system.get("battle_end_music", ""), encoding)),
    })
    if id_maps.battle_commands:
        plain = (base.get("skillTypes") or ["", "Fertigkeiten"])[1:2] or ["Fertigkeiten"]
        base["skillTypes"] = battlecmd.skill_type_names(id_maps.battle_commands,
                                                        plain[0])
    base["elements"] = [""] + [a.get("name", "")
                               for a in db.get("attributes", {}).values()]
    base["editMapId"] = base["startMapId"]
    base["sounds"] = _sounds(system, encoding, base.get("sounds"))
    if terms:
        base.setdefault("terms", {})
        base["currencyUnit"] = _term(terms, "0x5F") or base.get("currencyUnit", "G")
        _apply_terms(base, terms)
    _apply_vehicles(base, project, id_maps)
    # RM2k windows are opaque; MZ draws them see-through by default.
    if "advanced" in base:
        base["advanced"]["windowOpacity"] = 255
    base["optDisplayTp"] = False          # RM2k has no TP
    base["optDrawTitle"] = False          # RM2k never writes the title text
    base["optAutosave"] = False           # nor saves by itself
    base["optSideView"] = False           # RM2003 turns it on in convert.py
    base["battleSystem"] = 0              # turn based (convert.py: RM2003 ATB)
    # RM2k has no weapon or armour types; every weapon is type 1, every
    # armour type 1, named after the database's equipment terms.
    base["weaponTypes"] = ["", _term(terms, "0x88") or "Weapon"]
    base["armorTypes"] = ["", _term(terms, "0x8A") or "Armor"]
    base["testBattlers"] = [{"actorId": a, "equips": [0, 0, 0, 0, 0], "level": 1}
                            for a in actors]
    base["testTroopId"] = 1
    base["battlerName"] = ""
    base["battlerHue"] = 0
    base["optFollowers"] = False          # nor party members trailing the hero
    # Nor MV's separate weapon sprite next to an attacking battler.
    for motion in base.get("attackMotions") or []:
        motion["weaponImageId"] = 0
    return base


# RM2k database terms (chunk id) -> MV.  RM2k builds its messages by
# appending the term to a name or number; MV formats with %1, %2.
_BASIC_TERMS = {0: "0x7B", 1: "0x80", 2: "0x7C", 3: "0x81", 4: "0x7D", 5: "0x82",
                8: "0x7F", 9: "0x7F"}
_COMMAND_TERMS = {0: "0x65", 1: "0x67", 2: "0x68", 3: "0x69", 4: "0x6A", 5: "0x6B",
                  6: "0x6C", 7: "0x76", 8: "0x78", 9: "0x6E", 10: "0x70", 12: "0x88",
                  15: "0x6C", 18: "0x72", 19: "0x73", 20: "0x75", 24: "0x2B", 25: "0x2C"}
_PARAM_TERMS = {0: "0x7C", 1: "0x7D", 2: "0x84", 3: "0x85", 4: "0x86", 5: "0x86", 6: "0x87"}
_MESSAGE_TERMS = {
    # MV key: (template around the RM2k term, term)
    "preemptive": ("{}", "0x02"),
    "escapeFailure": ("{}", "0x04"),
    "victory": ("{}", "0x05"),
    "defeat": ("{}", "0x06"),
    "obtainExp": ("%1{}", "0x07"),
    "obtainItem": ("%1{}", "0x0A"),
    "levelUp": ("%1 %2 %3{}", "0x24"),
    "obtainSkill": ("%1{}", "0x25"),
    "possession": ("{}", "0x5C"),
    "saveMessage": ("{}", "0x92"),
    "loadMessage": ("{}", "0x93"),
    "file": ("{}", "0x94"),
    "evasion": ("%1{}", "0x1B"),
    "useItem": ("%1{}", "0x1C"),
    "actorDamage": ("%1 %2{}", "0x16"),
    "enemyDamage": ("%1 %2{}", "0x14"),
    "actorNoDamage": ("%1{}", "0x17"),
    "enemyNoDamage": ("%1{}", "0x15"),
    "escapeStart": ("%1{}", "0x12"),
}
# MV equipment type names: weapon, shield, head, body, accessory.
_EQUIP_TERMS = {1: "0x88", 2: "0x89", 3: "0x8B", 4: "0x8A", 5: "0x8C"}


def _term(terms: dict, key: str) -> str:
    """A term, or "" when it is missing or never translated.

    Western projects often keep some of RM2k's Japanese default terms; read
    with a Western code page they come out as mojibake, and MV's own
    wording is better than that.
    """
    text = terms.get(key) or ""
    return "" if model.untranslated_japanese(text) else text


def _apply_terms(base: dict, terms: dict) -> None:
    mv = base["terms"]
    for table, mapping in (("basic", _BASIC_TERMS), ("commands", _COMMAND_TERMS),
                           ("params", _PARAM_TERMS)):
        values = mv.get(table)
        if not isinstance(values, list):
            continue
        for index, key in mapping.items():
            text = _term(terms, key)
            if text and index < len(values):
                values[index] = text
    messages = mv.get("messages")
    if isinstance(messages, dict):
        for name, (template, key) in _MESSAGE_TERMS.items():
            text = _term(terms, key)
            if text:
                messages[name] = template.format(text)
        gold_a, gold_b = _term(terms, "0x08"), _term(terms, "0x09")
        if gold_a or gold_b:
            messages["obtainGold"] = f"{gold_a}%1\\G{gold_b}"
    equip = base.get("equipTypes")
    if isinstance(equip, list):
        for index, key in _EQUIP_TERMS.items():
            text = _term(terms, key)
            if text and index < len(equip):
                equip[index] = text


def _apply_vehicles(base: dict, project, id_maps) -> None:
    """RM2k's skiff, ship and airship are MV's boat, ship and airship."""
    system = project.database.get("system", {})
    start = project.maptree.get("start", {})
    for mv_key, rm_start, rm_system in (("boat", "skiff", "boat"), ("ship", "boat", "ship"),
                                        ("airship", "airship", "airship")):
        vehicle = base.setdefault(mv_key, {})
        map_id = start.get(f"{rm_start}_map_id", 0) or 0
        vehicle.update({
            "characterName": system.get(f"{rm_system}_name", "") or "",
            "characterIndex": system.get(f"{rm_system}_index", 0) or 0,
            "bgm": _audio(model.read_music(system.get(f"{rm_system}_music", ""),
                                           project.encoding)),
            "startMapId": id_maps.maps.get(map_id, 0) if map_id else 0,
            "startX": start.get(f"{rm_start}_x", 0) or 0,
            "startY": start.get(f"{rm_start}_y", 0) or 0,
        })


# MV keeps 24 system sounds in a fixed order; these are the slots RM2k has a
# counterpart for.
_SOUND_SLOTS = {
    0: "cursor_se", 1: "decision_se", 2: "cancel_se", 3: "buzzer_se",
    7: "battle_se", 8: "escape_se", 9: "enemy_attack_se",
    10: "enemy_damaged_se", 11: "enemy_death_se", 14: "actor_damaged_se",
    18: "dodge_se", 22: "item_se",
}


def _sounds(system: dict, encoding: str, existing: list | None) -> list:
    sounds = list(existing) if existing and len(existing) >= 24 else [
        {"name": "", "pan": 0, "pitch": 100, "volume": 90} for _ in range(24)]
    for slot, field in _SOUND_SLOTS.items():
        raw = system.get(field)
        if raw:
            sounds[slot] = _audio(model.read_sound(raw, encoding))
    return sounds


def _names(table: dict, prefix: str) -> list[str]:
    highest = max(table) if table else 0
    out = [""] * (highest + 1)
    for index, record in table.items():
        out[index] = record.get("name", "") or f"{prefix} {index}"
    return out


def _blank_system() -> dict:
    sound = {"name": "", "pan": 0, "pitch": 100, "volume": 90}
    vehicle = {"bgm": dict(sound), "characterIndex": 0, "characterName": "",
               "startMapId": 0, "startX": 0, "startY": 0}
    return {
        "airship": dict(vehicle), "boat": dict(vehicle), "ship": dict(vehicle),
        "armorTypes": ["", "General"], "attackMotions": [],
        "battleBgm": dict(sound), "battleback1Name": "", "battleback2Name": "",
        "battlerHue": 0, "battlerName": "", "currencyUnit": "G",
        "defeatMe": dict(sound), "editMapId": 1, "elements": [""],
        "equipTypes": ["", "Weapon", "Shield", "Armor", "Helmet", "Accessory"],
        "gameTitle": "", "gameoverMe": dict(sound), "locale": "en_US",
        "magicSkills": [1], "menuCommands": [True] * 6,
        "optDisplayTp": False, "optDrawTitle": False, "optExtraExp": False,
        "optFloorDeath": False, "optFollowers": True, "optSideView": False,
        "optSlipDeath": False, "optTransparent": False,
        "partyMembers": [1], "skillTypes": ["", "Magic"],
        "sounds": [dict(sound) for _ in range(24)],
        "startMapId": 1, "startX": 0, "startY": 0,
        "switches": [""], "variables": [""],
        "terms": {"basic": [], "commands": [], "params": [], "messages": {}},
        "testBattlers": [], "testTroopId": 1,
        "title1Name": "", "title2Name": "", "titleBgm": dict(sound),
        "victoryMe": dict(sound), "weaponTypes": ["", "General"],
    }
