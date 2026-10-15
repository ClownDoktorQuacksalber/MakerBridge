"""RM2003 battle commands -> MV skill types plus a table for RM2kCompat.js.

RM2003 gives every hero a list of battle commands (Attack, Defend, Item,
Escape and named "skill subsets" like "Telekinese") taken from a table in the
database.  A skill whose type is 4 or above belongs to the n-th subset, in the
order the subset commands appear in that table; types 0..3 (normal, teleport,
escape, switch) are the plain skills.

MV has a fixed battle menu, so the subsets become MV skill types and
RM2kCompat.js builds each hero's battle menu from the original list.
"""

from __future__ import annotations

import struct

from ..lcf.model import parse_array, parse_struct

# RPG_RT.ldb top-level chunk holding the RM2003 battle command table.
LDB_BATTLE_COMMANDS = "0x1D"
COMMAND_LIST_CHUNK = 0x0A
COMMAND_SCHEMA = {0x01: ("name", "str"), 0x02: ("type", "int")}
# Actor chunk with the hero's commands: int32 command ids, -1 ends the list.
ACTOR_COMMANDS = "0x50"

TYPE_ATTACK, TYPE_SKILL, TYPE_SUBSET = 0, 1, 2
FIRST_SUBSET_SKILL_TYPE = 4
PLAIN_STYPE = 1        # MV skill type for RM2003's plain skills


def commands(db: dict, encoding: str) -> dict[int, dict]:
    """Command id -> {"name", "type", "stype"}; empty for RM2000 projects."""
    raw = (db.get("_unknown") or {}).get(LDB_BATTLE_COMMANDS)
    if not raw:
        return {}
    table = parse_struct(bytes.fromhex(raw), {COMMAND_LIST_CHUNK: ("list", "raw")},
                         encoding)
    if not table.get("list"):
        return {}
    entries = parse_array(bytes.fromhex(table["list"]), COMMAND_SCHEMA, encoding)
    out: dict[int, dict] = {}
    next_stype = PLAIN_STYPE + 1
    for command_id in sorted(entries):
        entry = entries[command_id]
        kind = entry.get("type", 0)
        stype = 0
        if kind == TYPE_SKILL:
            stype = PLAIN_STYPE
        elif kind == TYPE_SUBSET:
            stype = next_stype
            next_stype += 1
        out[command_id] = {"name": entry.get("name", ""), "type": kind, "stype": stype}
    return out


def skill_type_names(table: dict[int, dict], plain_name: str) -> list[str]:
    """MV's System.json "skillTypes": index 1 the plain skills, then subsets."""
    names = ["", plain_name]
    for entry in sorted(table.values(), key=lambda e: e["stype"]):
        if entry["type"] == TYPE_SUBSET:
            names.append(entry["name"])
    return names


def skill_stype(rm_type: int, table: dict[int, dict]) -> int:
    """MV skill type for an RM2003 skill type."""
    subsets = sum(1 for e in table.values() if e["type"] == TYPE_SUBSET)
    index = rm_type - FIRST_SUBSET_SKILL_TYPE
    if 0 <= index < subsets:
        return PLAIN_STYPE + 1 + index
    return PLAIN_STYPE


def actor_commands(actor: dict) -> list[int] | None:
    """The hero's command ids in menu order, or None if the actor has none."""
    # Actors keep the list in an undecoded chunk, RM2003 classes in a field.
    raw = actor.get("battle_commands") or (actor.get("_unknown") or {}).get(ACTOR_COMMANDS)
    if not raw:
        return None
    data = bytes.fromhex(raw)
    ids = []
    for (value,) in struct.iter_unpack("<i", data[:len(data) // 4 * 4]):
        if value == -1:
            break
        if value > 0:
            ids.append(value)
    return ids
