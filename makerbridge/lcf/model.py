"""Turn LCF binary files into plain Python dicts.

The result is deliberately close to the on-disk structure: field names from
``schema``, defaults left out (absent chunk == RM2k default), and anything the
schema does not know kept under ``_unknown`` as hex.  Conversion to RPG Maker
MV happens a layer up, in :mod:`makerbridge.mv`.
"""

from __future__ import annotations

from typing import Any

from . import const, schema as S
from .reader import (
    LcfError, Reader, as_int16_array, decode_string, read_signature,
)

SIG_DATABASE = "LcfDataBase"
SIG_MAPTREE = "LcfMapTree"
SIG_MAPUNIT = "LcfMapUnit"


class EventCommand(dict):
    """One entry of an event command stream."""


def parse_command_stream(payload: bytes, enc: str) -> list[dict]:
    """Decode a run of event commands.

    Layout per command: code, indent, string (length-prefixed), parameter
    count, parameters -- all compressed integers except the string body.  The
    stream has no element count; it simply fills the chunk.
    """
    r = Reader(payload)
    out: list[dict] = []
    while not r.eof():
        code = r.ber()
        indent = r.ber()
        text = decode_string(r.bytes(r.ber()), enc)
        params = [to_signed(r.ber()) for _ in range(r.ber())]
        out.append({"code": code, "indent": indent, "string": text,
                    "parameters": params})
    return out


# Shift-JIS lead bytes of hiragana (0x82) and katakana (0x83), as a
# Western code page shows them.
_KANA_LEADS = ("\u201a", "\u0192")


def untranslated_japanese(text: str) -> bool:
    """True for one of RM2k's Japanese default texts read as Western text.

    Western games often leave some database defaults untranslated; their
    Shift-JIS bytes come out as mojibake such as "‚Í“|‚ê‚½!".  Bytes the
    code page cannot map at all leave U+FFFD behind.  An umlaut alone
    must not count - "ä" is a Shift-JIS lead byte too - so the text has to
    carry kana lead bytes and decode to Japanese.
    """
    if not text:
        return False
    if "\ufffd" in text:
        return True
    if sum(text.count(lead) for lead in _KANA_LEADS) < 2:
        return False
    try:
        japanese = text.encode("cp1252").decode("cp932")
    except (UnicodeError, LookupError):
        return False
    return any("\u3040" <= ch <= "\u30ff" for ch in japanese)


def to_signed(value: int) -> int:
    """Compressed integers are unsigned; RM2k stores negatives as 32-bit two's complement."""
    return value - (1 << 32) if value >= (1 << 31) else value


def parse_record(chunks: dict[int, bytes], sch: dict, enc: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    unknown: dict[str, str] = {}
    for cid, payload in chunks.items():
        entry = sch.get(cid)
        if entry is None:
            unknown[f"0x{cid:02X}"] = payload.hex()
            continue
        name, kind = entry
        try:
            out[name] = _decode(payload, kind, enc)
        except LcfError as exc:
            unknown[f"0x{cid:02X}"] = payload.hex()
            out.setdefault("_errors", []).append(f"{name}: {exc}")
    if unknown:
        out["_unknown"] = unknown
    return out


def _decode(payload: bytes, kind: str, enc: str) -> Any:
    if kind == "int":
        return to_signed(Reader(payload).ber())
    if kind == "bool":
        return bool(Reader(payload).ber())
    if kind == "str":
        return decode_string(payload, enc)
    if kind == "i16":
        return as_int16_array(payload)
    if kind == "u8":
        return list(payload)
    if kind == "ber":
        r = Reader(payload)
        vals = []
        while not r.eof():
            vals.append(r.ber())
        return vals
    if kind == "cmds":
        return parse_command_stream(payload, enc)
    return payload.hex()


def parse_array(payload: bytes, sch: dict, enc: str) -> dict[int, dict]:
    """A counted array of structs, keyed by the id stored with each entry."""
    r = Reader(payload)
    count = r.ber()
    out: dict[int, dict] = {}
    for _ in range(count):
        entry_id = r.ber()
        out[entry_id] = parse_record(r.struct_chunks(), sch, enc)
    if not r.eof():
        raise LcfError(f"array had {r.remaining()} trailing bytes")
    return out


def parse_struct(payload: bytes, sch: dict, enc: str) -> dict:
    return parse_record(Reader(payload).struct_chunks(), sch, enc)


# --- RPG_RT.ldb -------------------------------------------------------------

_LDB_ARRAYS = {
    const.LDB_ACTOR: ("actors", S.ACTOR),
    const.LDB_SKILL: ("skills", S.SKILL),
    const.LDB_ITEM: ("items", S.ITEM),
    const.LDB_ENEMY: ("enemies", S.ENEMY),
    const.LDB_TROOP: ("troops", S.TROOP),
    const.LDB_TERRAIN: ("terrains", S.TERRAIN),
    const.LDB_ATTRIBUTE: ("attributes", S.ATTRIBUTE),
    const.LDB_STATE: ("states", S.STATE),
    const.LDB_ANIMATION: ("animations", S.ANIMATION),
    const.LDB_CHIPSET: ("chipsets", S.CHIPSET),
    const.LDB_SWITCHES: ("switches", S.NAMED),
    const.LDB_VARIABLES: ("variables", S.NAMED),
    const.LDB_COMMONEVENT: ("common_events", S.COMMON_EVENT),
    # RPG Maker 2003 adds these; RM2000 files simply do not carry them.
    0x1E: ("classes", S.CLASS),
    0x20: ("battler_animations", S.BATTLER_ANIMATION),
}


def read_database(data: bytes, enc: str) -> dict:
    sig, off = read_signature(data)
    if sig != SIG_DATABASE:
        raise LcfError(f"expected {SIG_DATABASE}, got {sig!r}")
    db: dict[str, Any] = {"_signature": sig}
    for cid, payload in Reader(data, off).chunks():
        if cid in _LDB_ARRAYS:
            name, sch = _LDB_ARRAYS[cid]
            db[name] = parse_array(payload, sch, enc)
        elif cid == const.LDB_SYSTEM:
            db["system"] = parse_struct(payload, S.SYSTEM, enc)
        elif cid == const.LDB_TERMS:
            db["terms"] = _terms(payload, enc)
        else:
            db.setdefault("_unknown", {})[f"0x{cid:02X}"] = payload.hex()
    _expand_troops(db, enc)
    _expand_battler_animations(db, enc)
    db["_engine"] = "rm2k3" if "classes" in db else "rm2k"
    return db


def _expand_battler_animations(db: dict, enc: str) -> None:
    """RM2003 keeps the battle poses as a nested array per animation set."""
    for entry in db.get("battler_animations", {}).values():
        raw = entry.pop("poses", None)
        poses: dict[int, dict] = {}
        if isinstance(raw, str) and raw:
            try:
                poses = parse_array(bytes.fromhex(raw), S.BATTLER_POSE, enc)
            except LcfError:
                poses = {}
        entry["poses"] = poses
        entry.pop("weapons", None)


def _terms(payload: bytes, enc: str) -> dict[str, str]:
    """Terms is a flat struct of ~120 strings; keep them keyed by chunk id."""
    return {f"0x{cid:02X}": decode_string(p, enc)
            for cid, p in Reader(payload).chunks()}


def _expand_troops(db: dict, enc: str) -> None:
    for troop in db.get("troops", {}).values():
        raw = troop.pop("members", None)
        if isinstance(raw, str) and raw:
            try:
                troop["members"] = list(
                    parse_array(bytes.fromhex(raw), S.TROOP_MEMBER, enc).values())
            except LcfError:
                troop["members"] = []
        else:
            troop["members"] = []


# --- RPG_RT.lmt -------------------------------------------------------------

def read_maptree(data: bytes, enc: str) -> dict:
    sig, off = read_signature(data)
    if sig != SIG_MAPTREE:
        raise LcfError(f"expected {SIG_MAPTREE}, got {sig!r}")
    r = Reader(data, off)
    count = r.ber()
    infos: dict[int, dict] = {}
    for _ in range(count):
        map_id = r.ber()
        infos[map_id] = parse_record(r.struct_chunks(), S.MAP_INFO, enc)
    order_count = r.ber()
    order = [r.ber() for _ in range(order_count)]
    active_node = r.ber()
    start = parse_record(r.struct_chunks(), {
        0x01: ("party_map_id", "int"),
        0x02: ("party_x", "int"),
        0x03: ("party_y", "int"),
        0x0B: ("skiff_map_id", "int"),
        0x0C: ("skiff_x", "int"),
        0x0D: ("skiff_y", "int"),
        0x15: ("boat_map_id", "int"),
        0x16: ("boat_x", "int"),
        0x17: ("boat_y", "int"),
        0x1F: ("airship_map_id", "int"),
        0x20: ("airship_x", "int"),
        0x21: ("airship_y", "int"),
    }, enc)
    return {"_signature": sig, "map_infos": infos, "tree_order": order,
            "active_node": active_node, "start": start,
            "_trailing_bytes": r.remaining()}


# --- MapXXXX.lmu ------------------------------------------------------------

def read_mapunit(data: bytes, enc: str) -> dict:
    sig, off = read_signature(data)
    if sig != SIG_MAPUNIT:
        raise LcfError(f"expected {SIG_MAPUNIT}, got {sig!r}")
    chunks = Reader(data, off).struct_chunks()

    def num(cid: int) -> int:
        if cid in chunks:
            return Reader(chunks[cid]).ber()
        return const.LMU_DEFAULTS.get(cid, 0)

    width, height = num(const.LMU_WIDTH), num(const.LMU_HEIGHT)
    lower = as_int16_array(chunks[const.LMU_LOWER_LAYER])
    upper = as_int16_array(chunks[const.LMU_UPPER_LAYER])
    if len(lower) != width * height or len(upper) != width * height:
        raise LcfError(
            f"layer size mismatch: {width}x{height} but "
            f"{len(lower)}/{len(upper)} tiles")

    out = {
        "_signature": sig,
        "chipset_id": num(const.LMU_CHIPSET_ID),
        "width": width,
        "height": height,
        "scroll_type": num(const.LMU_SCROLL_TYPE),
        "parallax_flag": bool(num(const.LMU_PARALLAX_FLAG)),
        "parallax_name": decode_string(chunks.get(const.LMU_PARALLAX_NAME, b""), enc),
        "parallax_loop_x": bool(num(const.LMU_PARALLAX_LOOP_X)),
        "parallax_loop_y": bool(num(const.LMU_PARALLAX_LOOP_Y)),
        "parallax_auto_x": bool(num(const.LMU_PARALLAX_AUTO_LOOP_X)),
        "parallax_auto_y": bool(num(const.LMU_PARALLAX_AUTO_LOOP_Y)),
        # Negative speeds scroll the other way; stored as 32-bit unsigned.
        "parallax_sx": to_signed(num(const.LMU_PARALLAX_SX)),
        "parallax_sy": to_signed(num(const.LMU_PARALLAX_SY)),
        "lower_layer": lower,
        "upper_layer": upper,
        "save_count": num(const.LMU_SAVE_COUNT),
        "events": [],
    }
    if const.LMU_EVENTS in chunks:
        out["events"] = _events(chunks[const.LMU_EVENTS], enc)
    return out


def _events(payload: bytes, enc: str) -> list[dict]:
    events = []
    for event_id, rec in parse_array(payload, S.MAP_EVENT, enc).items():
        pages_hex = rec.pop("pages", "")
        pages = []
        if pages_hex:
            for page_id, page in parse_array(
                    bytes.fromhex(pages_hex), S.MAP_EVENT_PAGE, enc).items():
                cond_hex = page.pop("condition", "")
                page["id"] = page_id
                page["condition"] = (
                    parse_struct(bytes.fromhex(cond_hex),
                                 S.MAP_EVENT_PAGE_CONDITION, enc)
                    if cond_hex else {})
                page["move_route"] = _move_route(page.pop("move_route", ""), enc)
                pages.append(page)
        rec["id"] = event_id
        rec["pages"] = pages
        events.append(rec)
    return events


# Move-route commands are a different, much terser encoding than event
# commands: a run of 1-byte opcodes, with extra operands only for the four
# codes below.  Verified against all 4293 move routes in the reference
# project: every stream parses to exactly the declared command count.
# Verified by decoding all 2369 inline routes in the reference project: 2367
# consume exactly, and the embedded strings come out as real charset and sound
# file names ("IR-Klaue", "Bite", ...).
MOVE_CMD_OPERANDS = {
    32: "i",      # switch ON   -> switch id
    33: "i",      # switch OFF  -> switch id
    34: "si",     # change graphic -> charset name, charset index
    35: "siii",   # play sound  -> name, volume, tempo, balance
}


def decode_move_values(values: list[int], enc: str = "cp1252") -> list[dict]:
    """Decode a move route that RM2k inlined into event-command parameters.

    Same opcode stream as a move-route chunk, but already split into integers,
    with strings stored as a length followed by one integer per character.
    """
    # Each integer here is one *byte* of the original chunk, so numbers of
    # 128 and up (switch 242, say) still span several values in BER form.
    # Reading them as one value leaves the rest behind as bogus opcodes.
    out: list[dict] = []
    i = 0

    def ber() -> int:
        nonlocal i
        value = 0
        while True:
            byte = values[i]
            i += 1
            value = (value << 7) | (byte & 0x7F)
            if not byte & 0x80:
                return value

    while i < len(values):
        code = ber()
        text = ""
        params: list[int] = []
        for operand in MOVE_CMD_OPERANDS.get(code, ""):
            if operand == "s":
                length = ber()
                text = decode_string(bytes(v & 0xFF for v in values[i:i + length]), enc)
                i += length
            else:
                params.append(to_signed(ber()))
        out.append({"code": code, "string": text, "parameters": params})
    return out


def parse_move_commands(payload: bytes, enc: str) -> list[dict]:
    r = Reader(payload)
    out: list[dict] = []
    while not r.eof():
        code = r.ber()
        text = ""
        params: list[int] = []
        for operand in MOVE_CMD_OPERANDS.get(code, ""):
            if operand == "s":
                text = decode_string(r.bytes(r.ber()), enc)
            else:
                params.append(to_signed(r.ber()))
        out.append({"code": code, "string": text, "parameters": params})
    return out


def _move_route(hexstr: str, enc: str) -> dict:
    if not hexstr:
        return {}
    chunks = Reader(bytes.fromhex(hexstr)).struct_chunks()
    out: dict[str, Any] = {}
    commands = parse_move_commands(chunks.get(0x0C, b""), enc)
    out["commands"] = commands
    declared = Reader(chunks[0x0B]).ber() if 0x0B in chunks else 0
    if declared != len(commands):
        out["_count_mismatch"] = [declared, len(commands)]
    # liblcf: repeat defaults to True, skippable to False when omitted.
    out["repeat"] = bool(Reader(chunks[0x15]).ber()) if 0x15 in chunks else True
    out["skippable"] = bool(Reader(chunks[0x16]).ber()) if 0x16 in chunks else False
    return out


def read_music(hexstr: str, enc: str) -> dict:
    if not hexstr:
        return {}
    return parse_struct(bytes.fromhex(hexstr), S.MUSIC, enc)


def read_sound(hexstr: str, enc: str) -> dict:
    if not hexstr:
        return {}
    return parse_struct(bytes.fromhex(hexstr), S.SOUND, enc)
