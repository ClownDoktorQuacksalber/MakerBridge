"""Structural report over a loaded RM2k project.

This is the feedback loop for the converter: it checks the assumptions the
conversion relies on (tile id ranges, chipset array lengths, asset files that
actually exist) and lists every event command code in the project so nothing
silently disappears during translation.
"""

from __future__ import annotations

import collections
import logging
import os

from .lcf import const
from .project import Rm2kProject

# Event command codes, as established from their parameter signatures in real
# projects (see docs/FORMAT.md).  A trailing "?" marks a reading that fits the
# data but has no second, independent confirmation yet.
COMMAND_NAMES = {
    0: "(empty)", 10: "BlockEnd",
    1009: "?RM2003 unknown",
    10110: "ShowMessage", 20110: "ShowMessage_2",
    10120: "MessageOptions", 10130: "ChangeFaceGraphic",
    10140: "ShowChoice", 20140: "ShowChoiceOption", 20141: "ShowChoiceEnd",
    10150: "InputNumber",
    10210: "ControlSwitches", 10220: "ControlVars", 10230: "TimerOperation",
    10310: "ChangeGold", 10320: "ChangeItems", 10330: "ChangePartyMembers",
    10410: "?ChangeExp", 10420: "?ChangeLevel", 10430: "ChangeParameters",
    10440: "ChangeSkills", 10450: "ChangeEquipment",
    10460: "?ChangeHP", 10470: "?ChangeSP", 10480: "?ChangeCondition",
    10490: "FullHeal", 10500: "?SimulatedAttack",
    10630: "ChangeSpriteAssociation",
    10660: "ChangeSystemBGM", 10670: "?ChangeSystemSFX",
    10680: "?ChangeSystemGraphics", 10690: "?ChangeScreenTransitions",
    10710: "EnemyEncounter", 10720: "?OpenShop", 10730: "?ShowInn",
    10740: "EnterHeroName",
    10810: "Teleport", 10820: "MemorizeLocation", 10830: "RecallToLocation",
    10840: "?EnterExitVehicle", 10850: "?SetVehicleLocation",
    10860: "ChangeEventLocation", 10870: "?TradeEventLocations",
    10910: "StoreTerrainID", 10920: "StoreEventID",
    11010: "EraseScreen", 11020: "ShowScreen",
    11030: "TintScreen", 11040: "FlashScreen", 11050: "ShakeScreen",
    11060: "PanScreen", 11070: "WeatherEffects",
    11110: "ShowPicture", 11120: "MovePicture", 11130: "ErasePicture",
    11210: "ShowBattleAnimation",
    11310: "PlayerVisibility", 11320: "FlashSprite", 11330: "MoveEvent",
    11340: "ProceedWithMovement", 11350: "?HaltAllMovement",
    11410: "Wait",
    11510: "PlayBGM", 11520: "FadeOutBGM", 11530: "MemorizeBGM",
    11540: "PlayMemorizedBGM", 11550: "PlaySound", 11560: "PlayMovie",
    11610: "KeyInputProc",
    11710: "ChangeMapTileset", 11720: "ChangePBG", 11750: "TileSubstitution",
    11910: "?ChangeMonsterHP", 11920: "?ChangeMonsterMP",
    11930: "?ChangeMonsterCondition", 11950: "?ChangeBattleBG",
    11960: "?ShowBattleAnimation_B",
    12010: "ConditionalBranch", 22010: "ElseBranch", 22011: "EndBranch",
    12110: "Label", 12120: "JumpToLabel",
    12210: "Loop", 22210: "EndLoop", 12220: "BreakLoop",
    12310: "EndEventProcessing", 12320: "EraseEvent", 12330: "CallEvent",
    12410: "Comment", 22410: "Comment_2",
    12420: "GameOver",
    12510: "?unknown",
}


def report(proj: Rm2kProject, log: logging.Logger) -> None:
    log.info("=" * 70)
    log.info("project: %s", proj.game_title)
    log.info("root:    %s", proj.root)
    log.info("=" * 70)

    _report_database(proj, log)
    _report_maptree(proj, log)
    _report_tiles(proj, log)
    _report_commands(proj, log)
    _report_assets(proj, log)


def _report_database(proj: Rm2kProject, log) -> None:
    db = proj.database
    log.info("-- database --")
    for key in ("actors", "skills", "items", "enemies", "troops", "terrains",
                "attributes", "states", "animations", "chipsets", "switches",
                "variables", "common_events"):
        log.info("   %-14s %4d", key, len(db.get(key, {})))
    log.info("   %-14s %4d", "terms", len(db.get("terms", {})))

    unknown = collections.Counter()
    for table in ("actors", "skills", "items", "enemies", "troops", "states",
                  "chipsets", "common_events"):
        for rec in db.get(table, {}).values():
            for cid in rec.get("_unknown", {}):
                unknown[f"{table}{cid}"] += 1
    if unknown:
        log.info("   unmapped record chunks (kept as hex in the dump):")
        for key, count in sorted(unknown.items()):
            log.info("      %-28s x%d", key, count)


def _report_maptree(proj: Rm2kProject, log) -> None:
    infos = proj.maptree.get("map_infos", {})
    types = collections.Counter(i.get("type", 1) for i in infos.values())
    log.info("-- map tree --")
    log.info("   entries %d (root=%d, maps=%d, areas=%d)",
             len(infos), types.get(0, 0), types.get(1, 0), types.get(2, 0))
    log.info("   .lmu files %d", len(proj.maps))
    start = proj.maptree.get("start", {})
    log.info("   party start: map %s at (%s, %s)",
             start.get("party_map_id"), start.get("party_x"), start.get("party_y"))


def _report_tiles(proj: Rm2kProject, log) -> None:
    log.info("-- tiles --")
    chipset_use = collections.Counter()
    slot_use: dict[int, collections.Counter] = collections.defaultdict(
        collections.Counter)
    bad = 0
    for map_id, data in proj.maps.items():
        cs = data["chipset_id"]
        chipset_use[cs] += 1
        for value in data["lower_layer"]:
            try:
                _, slot, _ = const.decode_lower_tile(value)
            except ValueError:
                bad += 1
                log.error("map %d: lower tile id %d out of range", map_id, value)
                continue
            slot_use[cs][slot] += 1
        for value in data["upper_layer"]:
            try:
                const.decode_upper_tile(value)
            except ValueError:
                bad += 1
                log.error("map %d: upper tile id %d out of range", map_id, value)
    log.info("   tile ids out of range: %d", bad)
    chipsets = proj.database.get("chipsets", {})
    for cs_id in sorted(chipset_use):
        cs = chipsets.get(cs_id, {})
        name = cs.get("name", "?")
        file_name = cs.get("chipset_name", "")
        found = proj.find_asset("chipset", file_name)
        log.info("   chipset %d %-14r file=%-16r maps=%-3d %s",
                 cs_id, name, file_name, chipset_use[cs_id],
                 "" if found else "<<< IMAGE MISSING")
        autotiles = sorted(s for s in slot_use[cs_id] if s < const.N_AUTOTILE_SLOTS)
        log.info("      autotile slots used: %s", autotiles)


def _report_commands(proj: Rm2kProject, log) -> None:
    log.info("-- event commands --")
    codes = collections.Counter()
    pages = events = 0
    for data in proj.maps.values():
        for event in data["events"]:
            events += 1
            for page in event["pages"]:
                pages += 1
                for cmd in page.get("event_commands", []) or []:
                    codes[cmd["code"]] += 1
    for ce in proj.database.get("common_events", {}).values():
        for cmd in ce.get("event_commands", []) or []:
            codes[cmd["code"]] += 1
    log.info("   map events %d, pages %d, distinct command codes %d",
             events, pages, len(codes))
    for code, count in sorted(codes.items(), key=lambda kv: -kv[1]):
        log.info("      %-6d %-26s x%d", code,
                 COMMAND_NAMES.get(code, "<unknown>"), count)
    unknown = [c for c in codes if c not in COMMAND_NAMES]
    if unknown:
        log.warning("   command codes with no known name: %s", sorted(unknown))


def _report_assets(proj: Rm2kProject, log) -> None:
    log.info("-- assets --")
    for kind in ("chipset", "charset", "faceset", "picture", "panorama",
                 "battle", "system", "title", "music", "sound", "movie"):
        directory = proj.asset_dirs.get(kind)
        if not directory:
            continue
        try:
            n = len(os.listdir(directory))
        except OSError:
            n = -1
        log.info("   %-10s %3d files", kind, n)

    missing: set[tuple[str, str]] = set()
    for data in proj.maps.values():
        for event in data["events"]:
            for page in event["pages"]:
                name = page.get("character_name")
                if name and not proj.find_asset("charset", name):
                    missing.add(("charset", name))
    for actor in proj.database.get("actors", {}).values():
        for kind, key in (("charset", "character_name"), ("faceset", "face_name")):
            name = actor.get(key)
            if name and not proj.find_asset(kind, name):
                missing.add((kind, name))
    if missing:
        log.warning("   referenced but not on disk:")
        for kind, name in sorted(missing):
            log.warning("      %-8s %s", kind, name)
