"""Build the RPG Maker MV data/*.json database from an RM2k project.

RM2k keeps weapons, shields, armour, helmets and accessories in one Item
table; MV splits them into Items / Weapons / Armors.  :class:`IdMaps` records
how every RM2k id was redistributed so the event translator can rewrite
item references consistently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..lcf import model
from ..lcf.model import parse_array
from ..lcf.schema import (ANIMATION_CELL, ANIMATION_FRAME, ANIMATION_TIMING,
                           ENEMY_ACTION, LEARNING, WEAPON_ANIMATION)
from . import battlecmd

log = logging.getLogger(__name__)

# RM2k item "type" field
IT_NORMAL, IT_WEAPON, IT_SHIELD, IT_ARMOR, IT_HELMET, IT_ACCESSORY = range(6)
IT_MEDICINE, IT_BOOK, IT_SEED, IT_SPECIAL, IT_SWITCH = 6, 7, 8, 9, 10

# MV's equipment types: 2 shield, 3 head, 4 body, 5 accessory.
ARMOR_TYPES = {IT_SHIELD: 2, IT_ARMOR: 4, IT_HELMET: 3, IT_ACCESSORY: 5}

# MV stat order: maxhp maxmp atk def mat mdf agi luk
# RM2k stat order: maxhp maxsp attack defense spirit agility
RM2K_STATS = 6
RM2K_LEVELS = 50
MV_LEVELS = 100


@dataclass
class IdMaps:
    """RM2k item id -> ("item" | "weapon" | "armor", new id)."""
    items: dict[int, tuple[str, int]] = field(default_factory=dict)
    skills: dict[int, int] = field(default_factory=dict)
    actors: dict[int, int] = field(default_factory=dict)
    enemies: dict[int, int] = field(default_factory=dict)
    troops: dict[int, int] = field(default_factory=dict)
    states: dict[int, int] = field(default_factory=dict)
    animations: dict[int, int] = field(default_factory=dict)
    common_events: dict[int, int] = field(default_factory=dict)
    tilesets: dict[int, int] = field(default_factory=dict)
    maps: dict[int, int] = field(default_factory=dict)
    # RM2003 class id -> MV class id; MV's first classes are one per actor.
    classes: dict[int, int] = field(default_factory=dict)
    # RM2003 battle command id -> {name, type, stype}; empty for RM2000.
    battle_commands: dict[int, dict] = field(default_factory=dict)


def _audio(music: dict | None, default_volume: int = 100) -> dict:
    music = music or {}
    name = music.get("name", "")
    if name.strip().lower() == "(off)":
        name = ""          # RM2k's sentinel for "no track"
    return {
        "name": name,
        "pan": _clamp(music.get("balance", 50) * 2 - 100, -100, 100),
        "pitch": _clamp(music.get("tempo", 100), 50, 150),
        "volume": _clamp(music.get("volume", default_volume), 0, 100),
    }


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _stat_curve(parameters: list[int], stat_index: int) -> list[int]:
    """One MV 100-entry stat curve from RM2k's 6x50 parameter block."""
    # Six stats one after the other: 50 levels each in RM2000, 99 in RM2003.
    per_stat = len(parameters or []) // RM2K_STATS
    if per_stat < 1:
        return [1] * MV_LEVELS
    base = stat_index * per_stat
    levels = parameters[base:base + per_stat]
    # MV indexes the curve by level, entry 0 is unused; RM2k level 1 is index 0.
    curve = [levels[0]] + levels
    curve += [levels[-1]] * (MV_LEVELS - len(curve))
    low = 1 if stat_index == 0 else 0
    return [max(low, int(v)) for v in curve[:MV_LEVELS]]


def build(project, log) -> tuple[dict[str, object], IdMaps]:
    db = project.database
    maps = IdMaps()
    maps.battle_commands = battlecmd.commands(db, project.encoding)
    out: dict[str, object] = {}

    # Ids first: items name skills, states and heroes, heroes name items.
    for index, rm_id in enumerate(sorted(db.get("actors", {})), 1):
        maps.actors[rm_id] = index
    for index, rm_id in enumerate(sorted(db.get("skills", {})), RESERVED_SKILLS + 1):
        maps.skills[rm_id] = index
    for index, rm_id in enumerate(sorted(db.get("animations", {})), 1):
        maps.animations[rm_id] = index
    out["States.json"] = _states(db, maps)
    items, weapons, armors = _items(db, maps, log)
    out["Items.json"] = items
    out["Weapons.json"] = weapons
    out["Armors.json"] = armors
    out["Actors.json"] = _actors(db, maps)
    out["Classes.json"] = _classes(db, maps)
    out["Skills.json"] = _skills(db, maps)
    out["Enemies.json"] = _enemies(db, maps)
    out["Troops.json"] = _troops(db, maps)
    out["Animations.json"] = _animations(db, maps)
    return out, maps


# --- shared helpers ---------------------------------------------------------

def _v(record: dict, key: str, default):
    """A field, or RM2k's default when the chunk was left out of the file."""
    value = record.get(key)
    return default if value is None else value


def _flags(values) -> list[int]:
    """RM2k stores sets as one byte per entry; return the 1-based ids set."""
    return [i + 1 for i, flag in enumerate(values or []) if flag]


# Rank letters A..E are stored 0..4; a rank that is not stored is C.
RANK_DEFAULT = 2
RATE_KEYS = ("a_rate", "b_rate", "c_rate", "d_rate", "e_rate")
STATE_RATE_DEFAULTS = (100, 80, 60, 30, 0)
ATTRIBUTE_RATE_DEFAULTS = (300, 200, 100, 50, 0)


def _rank_traits(ranks, table: dict, code: int, id_map: dict | None,
                 defaults: tuple) -> list:
    """State or attribute resistance ranks -> MV rate traits (13 or 11)."""
    traits = []
    for rm_id, record in sorted(table.items()):
        rank = ranks[rm_id - 1] if ranks and rm_id - 1 < len(ranks) else RANK_DEFAULT
        rate = _v(record, RATE_KEYS[_clamp(rank, 0, 4)], defaults[_clamp(rank, 0, 4)])
        if rate == 100:
            continue
        data_id = id_map.get(rm_id, rm_id) if id_map else rm_id
        traits.append({"code": code, "dataId": data_id, "value": rate / 100})
    return traits


# MV reserves the first skills: 1 is what "Attack" uses, 2 "Guard".  The RM2k
# skills follow, so an RM2k skill never takes their place.
SKILL_ATTACK, SKILL_GUARD, SKILL_WAIT, SKILL_ESCAPE = 1, 2, 3, 4
SKILL_DUAL_ATTACK, SKILL_CHARGE, SKILL_SELF_DESTRUCT = 5, 6, 7
RESERVED_SKILLS = 7

# MV trait codes used below.
T_ELEMENT_RATE, T_STATE_RATE, T_STATE_RESIST = 11, 13, 14
T_PARAM_RATE, T_XPARAM, T_SPARAM = 21, 22, 23
T_ATTACK_ELEMENT, T_ATTACK_STATE = 31, 32
T_ADD_STYPE = 41
T_EQUIP_WTYPE, T_EQUIP_ATYPE, T_LOCK_EQUIP, T_SLOT_TYPE = 51, 52, 53, 55
T_SPECIAL_FLAG = 62
T_ATTACK_TIMES, T_SEAL_EQUIP, T_PARTY_ABILITY = 34, 54, 64
SP_MCR, SP_FDR = 4, 8                 # MP cost rate, floor damage rate
XP_CEV = 3                            # critical evasion
ABILITY_RAISE_PREEMPTIVE = 3        # MV party abilities: 3 raises first strike
ETYPE_SHIELD = 2
XP_HIT, XP_EVA, XP_CRI, XP_MRF, XP_HRG, XP_MRG = 0, 1, 2, 5, 7, 8
SP_GRD = 1
FLAG_AUTO_BATTLE, FLAG_GUARD = 0, 1

# MV param index of RM2k's attack, defense, spirit (both mat and mdf), agility.
STAT_PARAMS = {"attack": (2,), "defense": (3,), "spirit": (4, 5), "agility": (6,)}


# --- actors / classes -------------------------------------------------------

def _rm2k3(db: dict) -> bool:
    return db.get("_engine") == "rm2k3"


def _actors(db: dict, maps: IdMaps) -> list:
    out: list = [None]
    for rm_id, actor in sorted(db.get("actors", {}).items()):
        index = maps.actors[rm_id]
        name = actor.get("name") or actor.get("title") or f"Actor {rm_id}"
        if not actor.get("name") and actor.get("title"):
            log.info("actor %d has no name; using its title %r", rm_id, actor["title"])
        out.append({
            "id": index,
            "name": name,
            "nickname": actor.get("title", "") if actor.get("name") else "",
            "note": "",
            "profile": "",
            "classId": index,
            "initialLevel": max(1, _v(actor, "initial_level", 1)),
            # liblcf rpg::Actor::Setup: 99 levels in RM2003, 50 in RM2000.
            "maxLevel": max(1, _v(actor, "final_level", 99 if _rm2k3(db) else 50)),
            "characterName": actor.get("character_name", ""),
            "characterIndex": _v(actor, "character_index", 0),
            "faceName": actor.get("face_name", ""),
            "faceIndex": _v(actor, "face_index", 0),
            "battlerName": "",
            "equips": _initial_equips(actor, maps),
            "traits": [],
        })
        if actor.get("transparent"):
            out[-1]["rm2kTransparent"] = True     # drawn see-through
        # The RM2003 class it starts in, for class-restricted equipment.
        out[-1]["rm2kClass"] = _v(actor, "class_id", 0)
        unarmed = _v(actor, "unarmed_animation", 1)
        if unarmed != 1:
            # The animation of a hero fighting without a weapon; RM2kCompat.js.
            out[-1]["rm2kUnarmedAnimation"] = maps.animations.get(unarmed, 0)
    return out


def _initial_equips(actor: dict, maps: IdMaps) -> list[int]:
    """RM2k: weapon, shield, armour, helmet, accessory.  MV's slots: weapon,
    shield (a second weapon for two-weapon heroes), head, body, accessory."""
    weapon, shield, body, helmet, accessory = (
        list(actor.get("initial_equipment") or []) + [0] * 5)[:5]
    out = []
    for rm_id in (weapon, shield, helmet, body, accessory):
        mapped = maps.items.get(rm_id)
        out.append(mapped[1] if mapped and mapped[0] != "item" else 0)
    return out


def _classes(db: dict, maps: IdMaps) -> list:
    """Every actor gets its own class, carrying its stats and skills (RM2000
    has no classes, and an RM2003 hero keeps its own copy of them).  RM2003's
    class table follows, for "change class"."""
    out: list = [None]
    for rm_id, actor in sorted(db.get("actors", {}).items()):
        out.append(_class_entry(actor, maps.actors[rm_id],
                                actor.get("skill_name") or actor.get("title") or "Class",
                                db, maps, 300 if _rm2k3(db) else 30))
    for rm_id, record in sorted(db.get("classes", {}).items()):
        maps.classes[rm_id] = len(out)
        out.append(_class_entry(record, len(out), record.get("name", ""), db, maps, 300))
        out[-1]["rm2kClassId"] = rm_id
    return out


def _class_entry(actor: dict, mv_id: int, name: str, db: dict, maps: IdMaps,
                 exp_default: int) -> dict:
    params = actor.get("parameters") or []
    # Plain skills stay usable from the menu; the RM2003 subsets the hero
    # fights with are added on top.
    stypes = [battlecmd.PLAIN_STYPE]
    for command_id in battlecmd.actor_commands(actor) or []:
        stype = maps.battle_commands.get(command_id, {}).get("stype", 0)
        if stype and stype not in stypes:
            stypes.append(stype)
    curves = [
        _stat_curve(params, 0),   # maxhp
        _stat_curve(params, 1),   # maxmp  <- RM2k SP
        _stat_curve(params, 2),   # atk
        _stat_curve(params, 3),   # def
        _stat_curve(params, 4),   # mat    <- RM2k spirit
        _stat_curve(params, 4),   # mdf    <- RM2k spirit again
        _stat_curve(params, 5),   # agi
        [10] * MV_LEVELS,         # luk has no RM2k equivalent
    ]
    critical = _v(actor, "critical_hit_chance", 30) if _v(actor, "critical_hit", True) else 0
    traits = [
        # RM2k hits 90% of the time unarmed; a weapon adds its own
        # difference from that.
        {"code": T_XPARAM, "dataId": XP_HIT, "value": 0.9},
        {"code": T_XPARAM, "dataId": XP_CRI, "value": 1 / critical if critical else 0},
        {"code": T_EQUIP_WTYPE, "dataId": 1, "value": 0},
        {"code": T_EQUIP_ATYPE, "dataId": 1, "value": 0},
    ]
    traits += [{"code": T_ADD_STYPE, "dataId": s, "value": 0} for s in stypes]
    if actor.get("two_weapon"):
        traits.append({"code": T_SLOT_TYPE, "dataId": 1, "value": 0})
    if actor.get("lock_equipment"):
        traits += [{"code": T_LOCK_EQUIP, "dataId": e, "value": 0} for e in range(1, 6)]
    if actor.get("super_guard"):
        traits.append({"code": T_SPARAM, "dataId": SP_GRD, "value": 2})
    if actor.get("auto_battle"):
        traits.append({"code": T_SPECIAL_FLAG, "dataId": FLAG_AUTO_BATTLE, "value": 0})
    traits += _rank_traits(actor.get("state_ranks"), db.get("states", {}),
                           T_STATE_RATE, maps.states, STATE_RATE_DEFAULTS)
    traits += _rank_traits(actor.get("attribute_ranks"), db.get("attributes", {}),
                           T_ELEMENT_RATE, None, ATTRIBUTE_RATE_DEFAULTS)
    return {
        "id": mv_id,
        "name": name,
        "note": "",
        "expParams": _exp_params(actor, exp_default),
        # The exact RM2k experience curve, used by RM2kCompat.js.
        "rm2kExp": [_v(actor, "exp_base", exp_default), _v(actor, "exp_inflation", exp_default),
                    _v(actor, "exp_correction", 0)],
        "params": curves,
        "learnings": _learnings(actor, maps),
        "traits": traits,
    }


def _learnings(actor: dict, maps: IdMaps) -> list:
    raw = actor.get("skills") or ""
    if not raw:
        return []
    entries = parse_array(bytes.fromhex(raw), LEARNING, "cp1252")
    out = []
    for entry in sorted(entries.values(), key=lambda e: _v(e, "level", 1)):
        skill = maps.skills.get(_v(entry, "skill_id", 0))
        if skill:
            out.append({"level": max(1, _v(entry, "level", 1)), "note": "",
                        "skillId": skill})
    return out


def _exp_params(actor: dict, exp_default: int) -> list[int]:
    """MV: [basis, extra, accelerationA, accelerationB].

    RM2k uses a different curve (base / inflation / correction), so this is an
    approximation that keeps the overall growth in the same ballpark.
    """
    base = max(1, _v(actor, "exp_base", exp_default))
    inflation = max(0, _v(actor, "exp_inflation", exp_default))
    return [base, inflation, 30, 30]


# --- skills -----------------------------------------------------------------

SKILL_TELEPORT, SKILL_ESCAPE_TYPE, SKILL_SWITCH = 1, 2, 3
MV_DAMAGE_NONE, MV_HP_DAMAGE, MV_MP_DAMAGE = 0, 1, 2
MV_HP_RECOVER, MV_MP_RECOVER, MV_HP_DRAIN, MV_MP_DRAIN = 3, 4, 5, 6
E_RECOVER_HP, E_RECOVER_MP, E_ADD_STATE, E_REMOVE_STATE = 11, 12, 21, 22
E_ADD_BUFF, E_ADD_DEBUFF, E_SPECIAL, E_GROW, E_LEARN = 31, 32, 41, 42, 43
SPECIAL_ESCAPE = 0
BUFF_TURNS = 5


def _skills(db: dict, maps: IdMaps) -> list:
    guard_state = len(db.get("states", {})) + 1
    out: list = [None] + _reserved_skills(guard_state)
    for rm_id, skill in sorted(db.get("skills", {}).items()):
        index = maps.skills[rm_id]
        scope = _v(skill, "scope", 0)
        offensive = scope in (0, 1)
        kind = _v(skill, "type", 0)
        entry = {
            "id": index,
            "name": skill.get("name", ""),
            "description": skill.get("description", ""),
            "note": "",
            "iconIndex": 0,
            "animationId": _v(skill, "animation_id", 1),
            "damage": _skill_damage(skill, offensive),
            "effects": _skill_effects(skill, offensive, maps),
            # RM2k rolls the skill's own hit chance and nothing else.
            "hitType": 0,
            "message1": skill.get("using_message1", ""),
            "message2": skill.get("using_message2", ""),
            "mpCost": _v(skill, "sp_cost", 0),
            "tpCost": 0,
            "tpGain": 0,
            "occasion": 1 if offensive else 0,      # attacks only in battle
            "repeats": 1,
            "requiredWtypeId1": 0,
            "requiredWtypeId2": 0,
            "scope": _scope(scope),
            "speed": 0,
            "stypeId": battlecmd.skill_stype(kind, maps.battle_commands),
            "successRate": _v(skill, "hit", 100),
        }
        if kind in (SKILL_TELEPORT, SKILL_ESCAPE_TYPE):
            # Outside battle they move the party (RM2kCompat.js): teleport
            # to a chosen destination, escape back to the escape point.
            entry["rm2kTravel"] = "teleport" if kind == SKILL_TELEPORT else "escape"
            # Both only work on the map (EasyRPG Algo::IsSkillUsable).
            entry["scope"] = 11
            entry["occasion"] = 2
        if kind == SKILL_SWITCH:
            # RM2kCompat.js turns the switch on when the skill is used.
            entry["rm2kSwitch"] = _v(skill, "switch_id", 1)
            entry["scope"] = 11
            entry["occasion"] = _occasion(_v(skill, "occasion_field", True),
                                          _v(skill, "occasion_battle", False))
        # States can block skills by their physical / magical rate.
        entry["rm2kRates"] = [_v(skill, "physical_rate", 0), _v(skill, "magical_rate", 3)]
        entry.update(_stat_changes(skill, offensive))
        # The pose and movement of each hero using it; RM2kCompat.js.
        heroes = {a: list(v) for a, v in _hero_animation(
            skill.get("battler_animation_data"), maps, db).items() if v != (3, 0)}
        if heroes:
            entry["rm2kCba"] = heroes
        if _v(skill, "sp_type", 0) == 1:
            # RM2003 can cost a percentage of max SP; RM2kCompat.js reads it.
            entry["rm2kMpPercent"] = _v(skill, "sp_percent", 0)
        out.append(entry)
    return out


def _skill_damage(skill: dict, offensive: bool) -> dict:
    """RM2k: power + attack*phys/20 + spirit*magic/40, minus the target's
    defense*phys/40 + spirit*magic/80 unless defense is ignored."""
    power = _v(skill, "power", 0)
    phys = _v(skill, "physical_rate", 0)
    magic = _v(skill, "magical_rate", 3)
    formula = f"{power} + a.atk * {phys} / 20 + a.mat * {magic} / 40"
    if offensive and not skill.get("ignore_defense"):
        formula = f"{formula} - (b.def * {phys} / 40 + b.mdf * {magic} / 80)"
    absorb = bool(skill.get("absorb_damage"))
    if skill.get("affect_hp", False):
        kind = (MV_HP_DRAIN if absorb else MV_HP_DAMAGE) if offensive else MV_HP_RECOVER
    elif skill.get("affect_sp"):
        kind = (MV_MP_DRAIN if absorb else MV_MP_DAMAGE) if offensive else MV_MP_RECOVER
    else:
        kind = MV_DAMAGE_NONE
    attributes = _flags(skill.get("attribute_effects"))
    return {
        "critical": False,
        "elementId": attributes[0] if attributes else 0,
        # Kept without HP/SP effect too: stat changes use the same value.
        "formula": formula,
        "type": kind,
        "variance": _v(skill, "variance", 4) * 5,
    }


def _stat_changes(skill: dict, offensive: bool) -> dict:
    """Attack, defense, spirit and agility change by the skill's effect for
    the rest of the battle (EasyRPG Game_BattlerAlgorithm::Skill); MV params
    2 atk, 3 def, 4/5 spirit, 6 agi.  RM2kCompat.js applies them."""
    params = [p for key, ps in STAT_PARAMS.items() if skill.get(f"affect_{key}") for p in ps]
    if not params:
        return {}
    return {"rm2kStats": params, "rm2kStatSign": -1 if offensive else 1}


def _skill_effects(skill: dict, offensive: bool, maps: IdMaps) -> list:
    effects = []
    # Attacks inflict their states; support skills cure them.  "Reverse"
    # swaps the two.
    add = offensive != bool(skill.get("reverse_state_effect"))
    for state in _flags(skill.get("state_effects")):
        effects.append({"code": E_ADD_STATE if add else E_REMOVE_STATE,
                        "dataId": maps.states.get(state, state), "value1": 1, "value2": 0})
    if _v(skill, "type", 0) == SKILL_ESCAPE_TYPE:
        effects.append({"code": E_SPECIAL, "dataId": SPECIAL_ESCAPE, "value1": 1, "value2": 0})
    return effects


def _reserved_skills(guard_state: int) -> list:
    """The skills MV expects at fixed ids, built to RM2k's rules."""
    def skill(index, name, scope, damage, effects, speed=0, hit_type=0):
        return {"id": index, "name": name, "description": "", "note": "",
                "iconIndex": 0, "animationId": -1 if index == SKILL_ATTACK else 0,
                "damage": damage, "effects": effects, "hitType": hit_type,
                "message1": "", "message2": "", "mpCost": 0, "tpCost": 0,
                "tpGain": 0, "occasion": 1, "repeats": 1,
                "requiredWtypeId1": 0, "requiredWtypeId2": 0, "scope": scope,
                "speed": speed, "stypeId": 0, "successRate": 100}
    none = {"critical": False, "elementId": 0, "formula": "0", "type": 0, "variance": 0}
    return [
        # RM2k's normal attack: half the attack minus a quarter of the defense.
        skill(SKILL_ATTACK, "Angriff", 1,
              {"critical": True, "elementId": -1, "formula": "a.atk / 2 - b.def / 4",
               "type": MV_HP_DAMAGE, "variance": 20}, [], hit_type=1),
        skill(SKILL_GUARD, "Verteidigen", 11, none,
              [{"code": E_ADD_STATE, "dataId": guard_state, "value1": 1, "value2": 0}],
              speed=2000),
        # Enemy actions RM2k has and MV lacks: doing nothing, and fleeing.
        skill(SKILL_WAIT, "Abwarten", 11, none, []),
        skill(SKILL_ESCAPE, "Flucht", 11, none,
              [{"code": E_SPECIAL, "dataId": SPECIAL_ESCAPE, "value1": 1, "value2": 0}]),
        # Enemy basic actions (EasyRPG EnemyAi MakeBasicAction): two normal
        # attacks; charging, which doubles the next normal attack
        # (RM2kCompat.js); and self-destruction, attack minus half the
        # defense against the whole party, after which the enemy is gone.
        dict(skill(SKILL_DUAL_ATTACK, "Doppelangriff", 1,
                   {"critical": True, "elementId": -1, "formula": "a.atk / 2 - b.def / 4",
                    "type": MV_HP_DAMAGE, "variance": 20}, [], hit_type=1),
             repeats=2, animationId=-1),
        dict(skill(SKILL_CHARGE, "Aufladen", 11, none, []), rm2kCharge=True),
        dict(skill(SKILL_SELF_DESTRUCT, "Selbstzerstörung", 2,
                   {"critical": False, "elementId": 0, "formula": "Math.max(0, a.atk - b.def / 2)",
                    "type": MV_HP_DAMAGE, "variance": 20}, []),
             rm2kSelfDestruct=True),
    ]


def _occasion(field: bool, battle: bool) -> int:
    """MV occasion: 0 always, 1 battle only, 2 menu only, 3 never."""
    if field and battle:
        return 0
    return 2 if field else 1 if battle else 3


def _scope(rm_scope: int) -> int:
    """RM2k: 0 single enemy, 1 all enemies, 2 self, 3 single ally, 4 all allies."""
    return {0: 1, 1: 2, 2: 11, 3: 7, 4: 8}.get(rm_scope, 1)


# --- items / weapons / armors ----------------------------------------------

def _items(db: dict, maps: IdMaps, log) -> tuple[list, list, list]:
    items: list = [None]
    weapons: list = [None]
    armors: list = [None]
    # Ids first, so a book or special item can point at any skill.
    for rm_id, item in sorted(db.get("items", {}).items()):
        kind = _v(item, "type", IT_NORMAL)
        if kind == IT_WEAPON:
            weapons.append(None)
            maps.items[rm_id] = ("weapon", len(weapons) - 1)
        elif kind in ARMOR_TYPES:
            armors.append(None)
            maps.items[rm_id] = ("armor", len(armors) - 1)
        else:
            items.append(None)
            maps.items[rm_id] = ("item", len(items) - 1)

    for rm_id, item in sorted(db.get("items", {}).items()):
        kind = _v(item, "type", IT_NORMAL)
        table, index = maps.items[rm_id]
        common = {
            "id": index,
            "name": item.get("name", ""),
            "description": item.get("description", ""),
            "note": "",
            "iconIndex": 0,
            "price": _v(item, "price", 0),
        }
        if table != "item":
            common["params"] = _equip_params(item)
            common["traits"] = _equip_traits(item, kind, maps)
            if item.get("cursed") and _rm2k3(db):
                common["rm2kCursed"] = True          # cannot be taken off
        if kind not in (IT_NORMAL, IT_SWITCH):
            # Who may equip or use it; RM2kCompat.js checks the list.
            common.update(_users(item, maps, db))
        if table == "weapon":
            weapons[index] = {**common, "animationId": _v(item, "animation_id", 1),
                              "etypeId": 1, "wtypeId": 1}
            # Attacking everyone, never missing and an SP price per swing
            # are not traits in MV; RM2kCompat.js reads these.
            if item.get("attack_all"):
                weapons[index]["rm2kAttackAll"] = True
            if item.get("ignore_evasion"):
                weapons[index]["rm2kIgnoreEvasion"] = True
            if _v(item, "sp_cost", 0):
                weapons[index]["rm2kSpCost"] = _v(item, "sp_cost", 0)
            hits = _weapon_hits(item, maps, db)
            if hits:
                weapons[index]["rm2kHits"] = hits
        elif table == "armor":
            armors[index] = {**common, "atypeId": 1, "etypeId": ARMOR_TYPES[kind]}
        else:
            items[index] = _usable_item(item, kind, common, maps, db)
        if table != "item":
            common["traits"] += _armor_state_traits(item, kind, maps, db)
        # How far each hero moves when attacking with it / using it.
        moves = {a: v[1] for a, v in _hero_animation(item.get("animation_data"), maps, db).items()
                 if v[1]}
        if moves and table != "armor":
            (weapons if table == "weapon" else items)[index]["rm2kMove"] = moves
    _skill_equipment(db, maps, items, weapons, armors, log)
    log.info("items split: %d item(s), %d weapon(s), %d armor(s)",
             len(items) - 1, len(weapons) - 1, len(armors) - 1)
    return items, weapons, armors


def _hero_animation(raw: str | None, maps: IdMaps, db: dict) -> dict:
    """RM2003 per-hero battle animation settings of a skill or item:
    MV actor id -> (pose, 0-based, liblcf default 3 = "skill"; movement:
    0 none, 1 step, 2 jump, 3 to the target)."""
    if not raw or not _rm2k3(db):
        return {}
    out = {}
    for rm_actor, entry in parse_array(bytes.fromhex(raw), WEAPON_ANIMATION, "cp1252").items():
        if rm_actor in maps.actors:
            out[str(maps.actors[rm_actor])] = (_v(entry, "pose", 3), _v(entry, "movement", 0))
    return out


def _weapon_hits(item: dict, maps: IdMaps, db: dict) -> dict:
    """Hits of a normal attack with this weapon, per hero (EasyRPG
    Algo::GetNumberOfAttacks): 2 for "attacks twice", times the hero's own
    "number of attacks" setting in RM2003.  Only heroes that differ."""
    raw = item.get("animation_data")
    if not raw or not _rm2k3(db):
        return {}
    base = 2 if item.get("dual_attack") else 1
    out = {}
    for rm_actor, entry in parse_array(bytes.fromhex(raw), WEAPON_ANIMATION, "cp1252").items():
        hits = base * (_v(entry, "attacks", 0) + 1)
        if hits != base and rm_actor in maps.actors:
            out[str(maps.actors[rm_actor])] = hits
    return out


def _skill_equipment(db: dict, maps: IdMaps, items: list, weapons: list, armors: list,
                     log) -> None:
    """RM2003 equipment marked "use skill" casts its skill when used from
    the item list, without being used up (EasyRPG Game_Party::UseItem): in
    battle by whoever carries or wears it, on the map only if the skill
    aims at allies (Game_Party::IsItemUsable).  MV can only use items, so
    each one gets a stand-in item; RM2kCompat.js lists it for the
    equipment and checks that the party has it."""
    if not _rm2k3(db):
        return
    for rm_id, item in sorted(db.get("items", {}).items()):
        table, index = maps.items[rm_id]
        if table == "item" or not item.get("use_skill"):
            continue
        skill = db.get("skills", {}).get(_v(item, "skill_id", 1))
        if skill is None:
            continue
        rm_scope = _v(skill, "scope", 0)
        offensive = rm_scope in (0, 1)
        proxy = {
            "id": len(items),
            "name": item.get("name", ""),
            "description": item.get("description", ""),
            "note": "",
            "iconIndex": 0,
            "price": 0,
            "animationId": maps.animations.get(_v(skill, "animation_id", 1), 0),
            "consumable": False,
            "damage": _skill_damage(skill, offensive),
            "effects": _skill_effects(skill, offensive, maps),
            "hitType": 0,
            "itypeId": 1,
            # Battle always; the map only for skills on allies.
            "occasion": 0 if rm_scope in (2, 3, 4) else 1,
            "repeats": 1,
            "scope": _scope(rm_scope),
            "speed": 0,
            "successRate": _v(skill, "hit", 100),
            "tpGain": 0,
            "rm2kEquipProxy": [table, index],
            "rm2kRates": [_v(skill, "physical_rate", 0), _v(skill, "magical_rate", 3)],
        }
        proxy.update(_stat_changes(skill, offensive))
        items.append(proxy)
        (weapons if table == "weapon" else armors)[index]["rm2kSkillItem"] = proxy["id"]
        log.info("equipment %r casts skill %r from the item list", item.get("name", ""),
                 skill.get("name", ""))


def _users(item: dict, maps: IdMaps, db: dict) -> dict:
    """RM2003 can restrict items by class instead of by hero.  Ids past the
    end of the stored list are allowed (EasyRPG Game_Actor::IsItemUsable:
    liblcf trims trailing entries); class index 0 is "no class"."""
    if _rm2k3(db) and _v(db.get("system") or {}, "equipment_setting", 0) == 1:
        class_set = list(item.get("class_set") or [])
        if any(not flag for flag in class_set):
            return {"rm2kClassSet": [1 if flag else 0 for flag in class_set]}
        return {}
    actor_set = item.get("actor_set") or []
    flagged = set(_flags(actor_set))
    allowed = [mv for rm, mv in sorted(maps.actors.items())
               if rm in flagged or rm > len(actor_set)]
    return {"rm2kActors": allowed} if len(allowed) < len(maps.actors) else {}


def _usable_item(item: dict, kind: int, common: dict, maps: IdMaps, db: dict) -> dict:
    """Medicine, books, seeds, special (casts a skill) and switch items."""
    entry = {
        **common,
        "animationId": _v(item, "animation_id", 1),
        "consumable": _v(item, "uses", 1) != 0,
        # RM2k items can last several uses; RM2kCompat.js counts them.
        "rm2kUses": _v(item, "uses", 1),
        "damage": {"critical": False, "elementId": 0, "formula": "0",
                   "type": 0, "variance": 20},
        "effects": [],
        "hitType": 0,
        "itypeId": 1,
        # Plain items cannot be used at all.
        "occasion": 3 if kind == IT_NORMAL else 0,
        "repeats": 1,
        "scope": 8 if item.get("entire_party") else 7,
        "speed": 0, "successRate": 100, "tpGain": 0,
    }
    effects = entry["effects"]
    if kind == IT_MEDICINE:
        if item.get("ko_only"):
            entry["scope"] = 10 if item.get("entire_party") else 9   # dead allies
        hp, hp_rate = _v(item, "recover_hp", 0), _v(item, "recover_hp_rate", 0)
        if hp or hp_rate:
            effects.append({"code": E_RECOVER_HP, "dataId": 0, "value1": hp_rate / 100, "value2": hp})
        sp, sp_rate = _v(item, "recover_sp", 0), _v(item, "recover_sp_rate", 0)
        if sp or sp_rate:
            effects.append({"code": E_RECOVER_MP, "dataId": 0, "value1": sp_rate / 100, "value2": sp})
        for state in _flags(item.get("state_set")):
            effects.append({"code": E_REMOVE_STATE, "dataId": maps.states.get(state, state),
                            "value1": 1, "value2": 0})
        if item.get("occasion_field1"):
            entry["occasion"] = 2                     # only from the menu
    elif kind == IT_BOOK:
        skill = maps.skills.get(_v(item, "skill_id", 1))
        if skill:
            effects.append({"code": E_LEARN, "dataId": skill, "value1": 1, "value2": 0})
        entry["occasion"] = 2
    elif kind == IT_SEED:
        for key, param in (("max_hp_points", 0), ("max_sp_points", 1), ("atk_points2", 2),
                           ("def_points2", 3), ("spi_points2", 4), ("spi_points2", 5),
                           ("agi_points2", 6)):
            if _v(item, key, 0):
                effects.append({"code": E_GROW, "dataId": param, "value1": _v(item, key, 0),
                                "value2": 0})
        entry["occasion"] = 2
    elif kind == IT_SPECIAL:
        # Casts a skill: take over what the skill does.
        rm_skill = _v(item, "skill_id", 1)
        skill = db.get("skills", {}).get(rm_skill, {})
        offensive = _v(skill, "scope", 0) in (0, 1)
        entry.update(_stat_changes(skill, offensive))
        entry.update(damage=_skill_damage(skill, offensive),
                     effects=_skill_effects(skill, offensive, maps),
                     scope=_scope(_v(skill, "scope", 0)),
                     animationId=_v(skill, "animation_id", 1),
                     # The skill's own hit chance (EasyRPG CalcSkillToHit).
                     successRate=_v(skill, "hit", 100),
                     occasion=1 if offensive else 0)
    elif kind == IT_SWITCH:
        entry.update(itypeId=2, scope=11, rm2kSwitch=_v(item, "switch_id", 1),
                     occasion=_occasion(_v(item, "occasion_field2", True),
                                        _v(item, "occasion_battle", False)))
    return entry


def _equip_params(item: dict) -> list[int]:
    return [
        0, 0,
        _v(item, "atk_points", 0), _v(item, "def_points", 0),
        _v(item, "spi_points", 0), _v(item, "spi_points", 0),
        _v(item, "agi_points", 0), 0,
    ]


def _equip_traits(item: dict, kind: int, maps: IdMaps) -> list:
    traits = []
    if kind == IT_WEAPON:
        # RM2k weapons carry their own hit chance (90 if unset).
        hit = _v(item, "hit", 90)
        if hit != 90:
            traits.append({"code": T_XPARAM, "dataId": XP_HIT, "value": (hit - 90) / 100})
        critical = _v(item, "critical_hit", 0)
        if critical:
            traits.append({"code": T_XPARAM, "dataId": XP_CRI, "value": critical / 100})
        for attribute in _flags(item.get("attribute_set")):
            traits.append({"code": T_ATTACK_ELEMENT, "dataId": attribute, "value": 0})
        chance = _v(item, "state_chance", 0)
        for state in _flags(item.get("state_set")):
            traits.append({"code": T_ATTACK_STATE, "dataId": maps.states.get(state, state),
                           "value": chance / 100})
    else:
        # Armour halves the attributes it lists; its state protection is
        # added by _armor_state_traits.
        for attribute in _flags(item.get("attribute_set")):
            traits.append({"code": T_ELEMENT_RATE, "dataId": attribute, "value": 0.5})
    if item.get("raise_evasion"):
        traits.append({"code": T_XPARAM, "dataId": XP_EVA, "value": 0.25})
    if kind == IT_WEAPON:
        if item.get("dual_attack"):
            traits.append({"code": T_ATTACK_TIMES, "dataId": 0, "value": 1})
        if item.get("preemptive"):
            traits.append({"code": T_PARTY_ABILITY, "dataId": ABILITY_RAISE_PREEMPTIVE, "value": 0})
        if item.get("two_handed"):
            # Both hands: no shield next to it.
            traits.append({"code": T_SEAL_EQUIP, "dataId": ETYPE_SHIELD, "value": 0})
    else:
        if item.get("prevent_critical"):
            traits.append({"code": T_XPARAM, "dataId": XP_CEV, "value": 1})
        if item.get("half_sp_cost"):
            traits.append({"code": T_SPARAM, "dataId": SP_MCR, "value": 0.5})
        if item.get("no_terrain_damage"):
            traits.append({"code": T_SPARAM, "dataId": SP_FDR, "value": 0})
    return traits


def _armor_state_traits(item: dict, kind: int, maps: IdMaps, db: dict) -> list:
    """Armour lowers the chance of the states it lists by its state chance
    (EasyRPG Game_Actor::GetStateProbability); RM2003's "reverse" armour
    inflicts them instead and protects from nothing."""
    if kind == IT_WEAPON or (_rm2k3(db) and item.get("reverse_state_effect")):
        return []
    rate = (100 - _clamp(_v(item, "state_chance", 0), 0, 100)) / 100
    if rate >= 1:
        return []
    return [{"code": T_STATE_RATE, "dataId": maps.states.get(state, state), "value": rate}
            for state in _flags(item.get("state_set"))]


# --- enemies ----------------------------------------------------------------

# MV enemy action conditions.
C_ALWAYS, C_TURN, C_HP, C_MP, C_PARTY_LEVEL, C_SWITCH = 0, 1, 2, 3, 5, 6
BASIC_ACTION_SKILL = {0: SKILL_ATTACK, 1: SKILL_DUAL_ATTACK, 2: SKILL_GUARD, 3: SKILL_WAIT,
                      4: SKILL_CHARGE, 5: SKILL_SELF_DESTRUCT, 6: SKILL_ESCAPE, 7: SKILL_WAIT}
KIND_BASIC, KIND_SKILL, KIND_TRANSFORM = 0, 1, 2


def _enemies(db: dict, maps: IdMaps) -> list:
    out: list = [None]
    for index, rm_id in enumerate(sorted(db.get("enemies", {})), 1):
        maps.enemies[rm_id] = index      # first: actions transform into others
    for index, (rm_id, enemy) in enumerate(sorted(db.get("enemies", {}).items()), 1):
        spirit = _v(enemy, "spirit", 10)
        critical = _v(enemy, "critical_hit_chance", 30) if enemy.get("critical_hit") else 0
        traits = [
            # RM2k enemies hit 90% of the time, 70% with "misses often".
            {"code": T_XPARAM, "dataId": XP_HIT, "value": 0.7 if enemy.get("miss") else 0.9},
            {"code": T_XPARAM, "dataId": XP_CRI, "value": 1 / critical if critical else 0},
        ]
        traits += _rank_traits(enemy.get("state_ranks"), db.get("states", {}),
                               T_STATE_RATE, maps.states, STATE_RATE_DEFAULTS)
        traits += _rank_traits(enemy.get("attribute_ranks"), db.get("attributes", {}),
                               T_ELEMENT_RATE, None, ATTRIBUTE_RATE_DEFAULTS)
        out.append({
            "id": index,
            "name": enemy.get("name", ""),
            "note": "",
            "battlerName": enemy.get("battler_name", ""),
            "battlerHue": _v(enemy, "battler_hue", 0),
            "exp": _v(enemy, "exp", 0),
            "gold": _v(enemy, "gold", 0),
            "params": [
                max(1, _v(enemy, "max_hp", 10)), _v(enemy, "max_sp", 10),
                _v(enemy, "attack", 10), _v(enemy, "defense", 10),
                spirit, spirit, _v(enemy, "agility", 10), 10,
            ],
            "actions": _enemy_actions(enemy, maps),
            # Drawn half see-through / bobbing in the air; RM2kCompat.js.
            "rm2kTransparent": bool(enemy.get("transparent")),
            "rm2kFlying": bool(enemy.get("levitate")),
            "dropItems": _drops(enemy, maps),
            "traits": traits,
        })
    return out


def _enemy_actions(enemy: dict, maps: IdMaps) -> list:
    """RM2k picks among the valid actions whose priority is within 10 of the
    best; MV among those within 3 of its best rating, so the scale is
    squeezed to keep that window."""
    raw = enemy.get("actions") or ""
    entries = parse_array(bytes.fromhex(raw), ENEMY_ACTION, "cp1252") if raw else {}
    actions = []
    top = max((_v(e, "rating", 50) for e in entries.values()), default=50)
    for entry in entries.values():
        kind = _v(entry, "kind", 0)
        transform = None
        if kind == KIND_SKILL:
            skill = maps.skills.get(_v(entry, "skill_id", 1), SKILL_ATTACK)
        elif kind == KIND_BASIC:
            skill = BASIC_ACTION_SKILL.get(_v(entry, "basic", 1), SKILL_ATTACK)
        else:
            # Transforming: RM2kCompat.js turns the enemy into the other one.
            skill = SKILL_WAIT
            transform = maps.enemies.get(_v(entry, "enemy_id", 1))
        action = {"skillId": skill,
                  "rating": _clamp(9 - round((top - _v(entry, "rating", 50)) * 3 / 10), 1, 9)}
        action.update(_action_condition(entry))
        if transform:
            action["rm2kTransform"] = transform
        # The exact RM2k condition, checked by RM2kCompat.js.
        condition = _v(entry, "condition_type", 0)
        if condition:
            action["rm2kCondition"] = [condition, _v(entry, "condition_param1", 0),
                                       _v(entry, "condition_param2", 0),
                                       _v(entry, "switch_id", 1)]
        # Switches the action turns on or off afterwards: RM2kCompat.js.
        if entry.get("switch_on"):
            action["rm2kSwitchOn"] = _v(entry, "switch_on_id", 1)
        if entry.get("switch_off"):
            action["rm2kSwitchOff"] = _v(entry, "switch_off_id", 1)
        actions.append(action)
    # An enemy without actions does nothing in RPG_RT, as in MV.
    return actions


def _action_condition(entry: dict) -> dict:
    kind = _v(entry, "condition_type", 0)
    a = _v(entry, "condition_param1", 0)
    b = _v(entry, "condition_param2", 0)
    if kind == 1:
        return {"conditionType": C_SWITCH, "conditionParam1": _v(entry, "switch_id", 1),
                "conditionParam2": 0}
    if kind == 2:
        # RM2k: turn A * X + B (EasyRPG EnemyAi IsActionValid); MV: A + B * X.
        return {"conditionType": C_TURN, "conditionParam1": b, "conditionParam2": a}
    if kind in (4, 5):
        return {"conditionType": C_HP if kind == 4 else C_MP,
                "conditionParam1": a / 100, "conditionParam2": b / 100}
    if kind == 6:
        return {"conditionType": C_PARTY_LEVEL, "conditionParam1": a, "conditionParam2": 0}
    # 3 (enemy count) and 7 (party fatigue) have no MV condition; the
    # exact check is RM2kCompat.js's (rm2kCondition).
    return {"conditionType": C_ALWAYS, "conditionParam1": 0, "conditionParam2": 0}


def _drops(enemy: dict, maps: IdMaps) -> list:
    drop_id = _v(enemy, "drop_id", 0)
    if not drop_id or drop_id not in maps.items:
        return [{"dataId": 1, "denominator": 1, "kind": 0}] * 3
    kind_name, new_id = maps.items[drop_id]
    kind = {"item": 1, "weapon": 2, "armor": 3}[kind_name]
    prob = max(1, _v(enemy, "drop_prob", 100))
    drops = [{"dataId": new_id, "denominator": max(1, round(100 / prob)), "kind": kind}]
    drops += [{"dataId": 1, "denominator": 1, "kind": 0}] * 2
    return drops


def _troops(db: dict, maps: IdMaps) -> list:
    out: list = [None]
    for index, (rm_id, troop) in enumerate(sorted(db.get("troops", {}).items()), 1):
        maps.troops[rm_id] = index
        members = []
        for member in troop.get("members", []):
            enemy_id = maps.enemies.get(member.get("enemy_id", 1))
            if not enemy_id:
                continue
            members.append({
                "enemyId": enemy_id,
                "x": member.get("x", 0),
                "y": member.get("y", 0),
                "hidden": bool(member.get("invisible", False)),
            })
        out.append({
            "id": index,
            "name": troop.get("name", ""),
            "members": members,
            "pages": [{
                "conditions": {"actorHp": 0, "actorId": 1, "actorValid": False,
                               "enemyHp": 0, "enemyIndex": 0, "enemyValid": False,
                               "switchId": 1, "switchValid": False,
                               "turnA": 0, "turnB": 0, "turnEnding": False,
                               "turnValid": False},
                "list": [{"code": 0, "indent": 0, "parameters": []}],
                "span": 0,
            }],
        })
    return out


# --- states -----------------------------------------------------------------

# RM2k restriction -> MV: 0 none, 1 cannot act (MV 4), 2 attacks enemies at
# random (MV 1), 3 attacks allies at random (MV 3).
STATE_RESTRICTION = {0: 0, 1: 4, 2: 1, 3: 3}
STATE_KEEPS_AFTER_BATTLE = 1
AFFECT_HALF, AFFECT_DOUBLE = 0, 1
CHANGE_LOSE, CHANGE_GAIN = 0, 1


def _states(db: dict, maps: IdMaps) -> list:
    out: list = [None]
    for index, (rm_id, state) in enumerate(sorted(db.get("states", {}).items()), 1):
        maps.states[rm_id] = index
    for rm_id, state in sorted(db.get("states", {}).items()):
        hold = _v(state, "hold_turn", 0)
        release = _v(state, "auto_release_prob", 0)
        by_damage = _v(state, "release_by_damage", 0)
        entry = {
            "id": maps.states[rm_id],
            "name": state.get("name", ""),
            "note": "",
            "iconIndex": 0,
            # From the turn after hold_turn RM2k rolls auto_release_prob%
            # each turn (EasyRPG Game_Battler::BattleStateHeal); MV picks a
            # duration up front, spread around the same average.
            "autoRemovalTiming": 2 if release else 0,
            "minTurns": hold + 1,
            "maxTurns": hold + 1 + (round(2 * (100 - release) / release) if release else 0),
            "chanceByDamage": by_damage or 100,
            "removeByDamage": bool(by_damage),
            "messageType": 1,
            "message1": state.get("message_actor", ""),
            "message2": state.get("message_enemy", ""),
            "message3": state.get("message_affected", ""),
            "message4": state.get("message_recovery", ""),
            "motion": 0,
            "overlay": 0,
            "priority": _clamp(_v(state, "priority", 50), 0, 100),
            "releaseByDamage": bool(by_damage),
            "removeAtBattleEnd": _v(state, "type", 0) != STATE_KEEPS_AFTER_BATTLE,
            "removeByRestriction": False,
            "removeByWalking": False,
            "restriction": STATE_RESTRICTION.get(_v(state, "restriction", 0), 0),
            "stepsToRemove": 100,
            "traits": _state_traits(state),
        }
        # Hit chance and dodging work as in RPG_RT; RM2kCompat.js.
        if _v(state, "reduce_hit_ratio", 100) != 100:
            entry["rm2kHitRatio"] = _v(state, "reduce_hit_ratio", 100)
        if state.get("avoid_attacks"):
            entry["rm2kEvadeAll"] = True
        # Skills whose physical / magical rate reaches the level are sealed
        # (EasyRPG Game_Battler::IsSkillUsable).
        if _rm2k3(db):
            # The battle pose a hero shows while the state is its most
            # important one (EasyRPG Sprite_Actor: battler_animation_id + 1,
            # 101 = the unset 100 means "bad status").
            pose = _v(state, "battler_animation_id", 100) + 1
            entry["rm2kPose"] = 7 if pose == 101 else pose
        if state.get("cursed"):
            entry["rm2kCursed"] = True      # RM2003: equipment cannot change
        if state.get("restrict_skill"):
            entry["rm2kSealPhysical"] = _v(state, "restrict_skill_level", 0)
        if state.get("restrict_magic"):
            entry["rm2kSealMagical"] = _v(state, "restrict_magic_level", 0)
        # Fixed HP/SP changes per turn and per steps on the map have no MV
        # trait; RM2kCompat.js applies them.
        for stat in ("hp", "sp"):
            kind = _v(state, f"{stat}_change_type", CHANGE_LOSE)   # unset means "lose"
            if kind not in (CHANGE_LOSE, CHANGE_GAIN):
                continue
            sign = -1 if kind == CHANGE_LOSE else 1
            if _v(state, f"{stat}_change_val", 0):
                entry[f"rm2k{stat.title()}Turn"] = sign * _v(state, f"{stat}_change_val", 0)
            steps = _v(state, f"{stat}_change_map_steps", 0)
            if steps and _v(state, f"{stat}_change_map_val", 0):
                entry[f"rm2k{stat.title()}Map"] = [steps, sign * _v(state, f"{stat}_change_map_val", 0)]
        out.append(entry)
    out.append(_guard_state(len(out)))
    return out


def _state_traits(state: dict) -> list:
    traits = []
    # RM2000 has no choice: the stats are halved.
    effect = _v(state, "affect_type", AFFECT_HALF)
    if effect in (AFFECT_HALF, AFFECT_DOUBLE):
        rate = 0.5 if effect == AFFECT_HALF else 2.0
        for key, params in STAT_PARAMS.items():
            if state.get(f"affect_{key}"):
                traits += [{"code": T_PARAM_RATE, "dataId": p, "value": rate} for p in params]
    if state.get("reflect_magic"):
        traits.append({"code": T_XPARAM, "dataId": XP_MRF, "value": 1})
    for stat, xparam in (("hp", XP_HRG), ("sp", XP_MRG)):
        kind = _v(state, f"{stat}_change_type", CHANGE_LOSE)   # unset means "lose"
        percent = _v(state, f"{stat}_change_max", 0)
        if kind in (CHANGE_LOSE, CHANGE_GAIN) and percent:
            sign = -1 if kind == CHANGE_LOSE else 1
            traits.append({"code": T_XPARAM, "dataId": xparam, "value": sign * percent / 100})
    return traits


def _guard_state(index: int) -> dict:
    """What MV's guard skill applies: the guard flag until the turn ends."""
    return {
        "id": index, "name": "Verteidigung", "note": "", "iconIndex": 0,
        "autoRemovalTiming": 2, "minTurns": 1, "maxTurns": 1,
        "chanceByDamage": 100, "removeByDamage": False, "messageType": 1,
        "message1": "", "message2": "", "message3": "", "message4": "",
        "motion": 0, "overlay": 0, "priority": 0, "releaseByDamage": False,
        "removeAtBattleEnd": True, "removeByRestriction": True,
        "removeByWalking": False, "restriction": 0, "stepsToRemove": 100,
        "traits": [{"code": T_SPECIAL_FLAG, "dataId": FLAG_GUARD, "value": 0}],
    }


# RM2k plays animations on a 320x240 screen with 96px cells; the sheets are
# doubled to MV's 192px cells, so each cell's zoom makes up the remaining
# screen-size difference.  A cell has one zoom for both axes, so its offset
# must be scaled by that same factor on both axes too: MV's taller screen
# (624/240 = 2.6 against 816/320 = 2.55) would otherwise open a gap of about
# two RM2k pixels between cells stacked on top of each other.
ANIM_SCREEN_X = ANIM_SCREEN_Y = 816 / 320
ANIM_CELL_FACTOR = ANIM_SCREEN_X / 2
ANIM_SCOPE_SCREEN = 1
MV_POSITION_SCREEN = 3
FLASH_FRAMES = 3


def _animations(db: dict, maps: IdMaps) -> list:
    out: list = [None]
    for index, (rm_id, anim) in enumerate(sorted(db.get("animations", {}).items()), 1):
        maps.animations[rm_id] = index
        position = _clamp(_v(anim, "position", 2), 0, 2)
        if _v(anim, "scope", 0) == ANIM_SCOPE_SCREEN:
            position = MV_POSITION_SCREEN
        out.append({
            "id": index,
            "name": anim.get("name", ""),
            "animation1Name": anim.get("animation_name", ""),
            "animation1Hue": 0,
            "animation2Name": "",
            "animation2Hue": 0,
            "frames": _animation_frames(anim.get("frames") or "", bool(anim.get("large"))),
            "position": position,
            "timings": _animation_timings(anim.get("timings") or ""),
        })
    return out


def _animation_frames(raw: str, large: bool = False) -> list:
    """Each MV cell: [pattern, x, y, scale %, rotation, mirror, opacity, blend].

    RM2003's large animations have 128px cells; their sheets are scaled to
    the same 192px cells, so the zoom makes up the difference (EasyRPG
    BattleAnimation: size = large ? 128 : 96)."""
    factor = ANIM_CELL_FACTOR * (128 / 96 if large else 1)
    frames = []
    for _, frame in sorted(parse_array(bytes.fromhex(raw), ANIMATION_FRAME, "cp1252").items()
                           if raw else []):
        cells = []
        raw_cells = frame.get("cells") or ""
        for _, cell in sorted(parse_array(bytes.fromhex(raw_cells), ANIMATION_CELL, "cp1252").items()
                              if raw_cells else []):
            if not _v(cell, "valid", True):
                continue
            cells.append([
                _v(cell, "cell_id", 0),
                round(_v(cell, "x", 0) * ANIM_SCREEN_X),
                round(_v(cell, "y", 0) * ANIM_SCREEN_Y),
                round(_v(cell, "zoom", 100) * factor),
                0, 0,
                round(255 * (100 - _clamp(_v(cell, "transparency", 0), 0, 100)) / 100),
                0,
            ])
        frames.append(cells)
    return frames


def _animation_timings(raw: str) -> list:
    timings = []
    for _, timing in sorted(parse_array(bytes.fromhex(raw), ANIMATION_TIMING, "cp1252").items()
                            if raw else []):
        sound = model.read_sound(timing.get("se") or "", "cp1252")
        se = None
        if sound.get("name") and sound["name"].strip().lower() != "(off)":
            se = {"name": sound["name"], "volume": _clamp(sound.get("volume", 100), 0, 100),
                  "pitch": _clamp(sound.get("tempo", 100), 50, 150),
                  "pan": _clamp(sound.get("balance", 50) * 2 - 100, -100, 100)}
        scope = _clamp(_v(timing, "flash_scope", 0), 0, 2)
        timings.append({
            "frame": max(0, _v(timing, "frame", 0) - 1),        # RM2k counts from 1
            "se": se,
            "flashScope": scope,
            "flashColor": [_v(timing, "flash_red", 31) * 8, _v(timing, "flash_green", 31) * 8,
                           _v(timing, "flash_blue", 31) * 8, _v(timing, "flash_power", 31) * 8],
            "flashDuration": FLASH_FRAMES if scope else 0,
        })
    return timings
