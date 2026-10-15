"""Battle events: the pages of an RM2k troop -> MV troop pages.

RM2k stores them inside each troop as an array of pages, each with a
condition record and an ordinary command list.  MV's own page conditions
cannot express RM2k's (HP ranges, second switch, variable, fatigue, a
battler's own turns, the command a hero used), so every page carries its
RM2k condition as "rm2kCondition" and RM2kCompat.js checks it the way
RPG_RT does (EasyRPG Game_Interpreter_Battle::AreConditionsMet).  The MV
conditions are filled in as far as they go, for the editor.
"""

from __future__ import annotations

from ..lcf.model import parse_array, parse_struct

PAGE = {0x02: ("condition", "raw"), 0x0C: ("event_commands", "cmds")}
CONDITION = {
    0x01: ("flags", "raw"),
    0x02: ("switch_a_id", "int"), 0x03: ("switch_b_id", "int"),
    0x04: ("variable_id", "int"), 0x05: ("variable_value", "int"),
    0x06: ("turn_a", "int"), 0x07: ("turn_b", "int"),
    0x08: ("fatigue_min", "int"), 0x09: ("fatigue_max", "int"),
    0x0A: ("enemy_id", "int"), 0x0B: ("enemy_hp_min", "int"), 0x0C: ("enemy_hp_max", "int"),
    0x0D: ("actor_id", "int"), 0x0E: ("actor_hp_min", "int"), 0x0F: ("actor_hp_max", "int"),
    0x10: ("turn_enemy_id", "int"), 0x11: ("turn_enemy_a", "int"), 0x12: ("turn_enemy_b", "int"),
    0x13: ("turn_actor_id", "int"), 0x14: ("turn_actor_a", "int"), 0x15: ("turn_actor_b", "int"),
    0x16: ("command_actor_id", "int"), 0x17: ("command_id", "int"),
}

# First flag byte (RM2000 has only this one).
SWITCH_A, SWITCH_B, VARIABLE, TURN = 0x01, 0x02, 0x04, 0x08
FATIGUE, ENEMY_HP, ACTOR_HP, TURN_ENEMY = 0x10, 0x20, 0x40, 0x80
# Second flag byte, RM2003.
TURN_ACTOR, COMMAND_ACTOR = 0x01, 0x02

SPAN_TURN = 1


def build_pages(troop: dict, translator, ids, encoding: str) -> list[dict] | None:
    """MV pages for one troop, or None if it has no battle events."""
    raw = troop.get("pages")
    if not raw:
        return None
    pages = parse_array(bytes.fromhex(raw), PAGE, encoding)
    out = []
    for page_id in sorted(pages):
        page = pages[page_id]
        condition = (parse_struct(bytes.fromhex(page["condition"]), CONDITION, encoding)
                     if page.get("condition") else {})
        flag_bytes = bytes.fromhex(condition.get("flags") or "00")
        first = flag_bytes[0]
        second = flag_bytes[1] if len(flag_bytes) > 1 else 0
        mv = {"actorHp": 0, "actorId": 1, "actorValid": False,
              "enemyHp": 0, "enemyIndex": 0, "enemyValid": False,
              "switchId": 1, "switchValid": False,
              "turnA": 0, "turnB": 0, "turnEnding": False, "turnValid": False}
        if first & SWITCH_A:
            mv.update(switchValid=True, switchId=condition.get("switch_a_id", 1))
        # RM2k turns are "A * X + B" (EasyRPG Game_Battle::CheckTurns),
        # MV's "A + B * X".
        if first & TURN:
            mv.update(turnValid=True, turnA=condition.get("turn_b", 0),
                      turnB=condition.get("turn_a", 0))
        elif first & TURN_ENEMY:
            # "After enemy n's turn A + B*X": MV only counts whole turns.
            mv.update(turnValid=True, turnA=condition.get("turn_enemy_b", 0),
                      turnB=condition.get("turn_enemy_a", 0))
        elif second & TURN_ACTOR:
            mv.update(turnValid=True, turnA=condition.get("turn_actor_b", 0),
                      turnB=condition.get("turn_actor_a", 0))
        if first & ENEMY_HP:
            # RM2k asks for HP within min..max percent; MV for "at most".
            mv.update(enemyValid=True, enemyIndex=condition.get("enemy_id", 0),
                      enemyHp=condition.get("enemy_hp_max", 100))
        if first & ACTOR_HP:
            actor = condition.get("actor_id", 1)
            mv.update(actorValid=True, actorId=ids.actors.get(actor, actor),
                      actorHp=condition.get("actor_hp_max", 100))

        commands = translator.translate(page.get("event_commands") or [],
                                        f"troop {troop.get('name', '')} page {page_id}")
        out.append({"conditions": mv, "list": commands, "span": SPAN_TURN,
                    "rm2kCondition": _rm2k_condition(condition, first, second, ids)})
    return out


def _rm2k_condition(c: dict, first: int, second: int, ids) -> dict:
    """The page's RM2k condition with liblcf's defaults filled in.  An empty
    one never runs, as in RPG_RT."""
    def get(key, default):
        value = c.get(key)
        return default if value is None else value

    def actor(key):
        rm_id = get(key, 1)
        return ids.actors.get(rm_id, rm_id)

    out: dict = {}
    if first & SWITCH_A:
        out["switchA"] = get("switch_a_id", 1)
    if first & SWITCH_B:
        out["switchB"] = get("switch_b_id", 1)
    if first & VARIABLE:
        out["variable"] = [get("variable_id", 1), get("variable_value", 0)]
    if first & TURN:
        out["turn"] = [get("turn_a", 0), get("turn_b", 0)]
    if first & FATIGUE:
        out["fatigue"] = [get("fatigue_min", 0), get("fatigue_max", 100)]
    if first & ENEMY_HP:
        out["enemyHp"] = [get("enemy_id", 0), get("enemy_hp_min", 0), get("enemy_hp_max", 100)]
    if first & ACTOR_HP:
        out["actorHp"] = [actor("actor_id"), get("actor_hp_min", 0), get("actor_hp_max", 100)]
    if first & TURN_ENEMY:
        out["turnEnemy"] = [get("turn_enemy_id", 0), get("turn_enemy_a", 0),
                            get("turn_enemy_b", 0)]
    if second & TURN_ACTOR:
        out["turnActor"] = [actor("turn_actor_id"), get("turn_actor_a", 0),
                            get("turn_actor_b", 0)]
    if second & COMMAND_ACTOR:
        out["command"] = [actor("command_actor_id"), get("command_id", 1)]
    return out
