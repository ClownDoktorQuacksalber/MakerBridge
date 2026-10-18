"""Translate RM2k event command streams into RPG Maker MV command lists.

Command codes were identified from their parameter signatures in the reference
project rather than taken on faith; see docs/FORMAT.md.  Anything this module
cannot translate is emitted as an MV comment that still carries the original
code and parameters, so a feature is never lost silently - it just needs a
human.  :func:`Translator.unsupported` reports what was left over.
"""

from __future__ import annotations

import collections
import json
import logging
import re

from .maps import parallax_speed

log = logging.getLogger(__name__)

# --- RM2k command codes -----------------------------------------------------
NOP = 0
BLOCK_END = 10
SHOW_MESSAGE = 10110
SHOW_MESSAGE_2 = 20110
MESSAGE_OPTIONS = 10120
SHOW_CHOICE = 10140
CHOICE_OPTION = 20140
CHOICE_END = 20141
CANCEL_SLOT = 4            # CHOICE_OPTION slot of the "on cancel" branch
INPUT_NUMBER = 10150
CONTROL_SWITCHES = 10210
CONTROL_VARS = 10220
CHANGE_GOLD = 10310
CHANGE_ITEMS = 10320
CHANGE_PARTY = 10330
CHANGE_FACE = 10130
TIMER_OPERATION = 10230
CHANGE_PARAMETERS = 10430
CHANGE_SKILLS = 10440
CHANGE_EQUIPMENT = 10450
FULL_HEAL = 10490
CHANGE_SPRITE = 10630
CHANGE_EXP = 10410
CHANGE_LEVEL = 10420
CHANGE_HERO_NAME = 10610
CHANGE_HERO_TITLE = 10620
CHANGE_FACE_GRAPHIC = 10640
CHANGE_VEHICLE_GRAPHIC = 10650
CHANGE_SYSTEM_SE = 10670
ENTER_EXIT_VEHICLE = 10840
SET_VEHICLE_LOCATION = 10850
HALT_ALL_MOVEMENT = 11350
CHANGE_BATTLE_COMMANDS = 1009       # RM2003
FORCE_FLEE, ENABLE_COMBO, CHANGE_CLASS = 1006, 1007, 1008         # RM2003
OPEN_LOAD_MENU, EXIT_GAME, TOGGLE_ATB, TOGGLE_FULLSCREEN, OPEN_OPTIONS = (
    5001, 5002, 5003, 5004, 5005)                                 # RM2003 1.10+
CHANGE_HP, CHANGE_SP, CHANGE_CONDITION, SIMULATED_ATTACK = 10460, 10470, 10480, 10500
CHANGE_SYSTEM_GRAPHICS, CHANGE_TRANSITIONS = 10680, 10690
CHANGE_ENCOUNTER_STEPS = 11740
TELEPORT_TARGETS, TELEPORT_ACCESS, ESCAPE_TARGET, ESCAPE_ACCESS = 11810, 11820, 11830, 11840
MONSTER_HP, MONSTER_SP, MONSTER_CONDITION, SHOW_HIDDEN_MONSTER = 13110, 13120, 13130, 13150
CHANGE_BATTLE_BG = 13210
# Battle-event variants (RM2003 troop pages).
BATTLE_CALL_COMMON = 1005
BATTLE_SHOW_ANIMATION = 13260
BATTLE_CONDITIONAL, BATTLE_ELSE, BATTLE_END_BRANCH = 13310, 23310, 23311
BATTLE_TERMINATE = 13410
# Branches after a battle, shop or inn with "custom handlers" on.  They nest
# exactly like MV's own: marker at the command's indent, body one deeper.
BATTLE_VICTORY, BATTLE_ESCAPE, BATTLE_DEFEAT, BATTLE_END = 20710, 20711, 20712, 20713
SHOP_DEALT, SHOP_NOT_DEALT, SHOP_END = 20720, 20721, 20722
INN_STAYED, INN_NOT_STAYED, INN_END = 20730, 20731, 20732
CHANGE_SYSTEM_BGM = 10660
ENEMY_ENCOUNTER = 10710
OPEN_SHOP = 10720
SHOW_INN = 10730
ENTER_HERO_NAME = 10740
GAME_OVER = 12420
UNKNOWN_10690 = 10690
TELEPORT = 10810
MEMORIZE_LOCATION = 10820
RECALL_TO_LOCATION = 10830
CHANGE_EVENT_LOCATION = 10860
SWAP_EVENTS = 10870
STORE_TERRAIN_ID = 10910
STORE_EVENT_ID = 10920
ERASE_SCREEN = 11010
SHOW_SCREEN = 11020
WEATHER = 11070
MEMORIZE_BGM = 11530
PLAY_MEMORIZED_BGM = 11540
CHANGE_TILESET = 11710
TINT_SCREEN = 11030
FLASH_SCREEN = 11040
SHAKE_SCREEN = 11050
PAN_SCREEN = 11060
SHOW_PICTURE = 11110
MOVE_PICTURE = 11120
ERASE_PICTURE = 11130
SHOW_ANIMATION = 11210
PLAYER_VISIBILITY = 11310
FLASH_SPRITE = 11320
MOVE_EVENT = 11330
PROCEED_MOVEMENT = 11340
WAIT = 11410
PLAY_BGM = 11510
FADEOUT_BGM = 11520
PLAY_SOUND = 11550
PLAY_MOVIE = 11560
KEY_INPUT = 11610
CHANGE_PARALLAX = 11720
TILE_SUBSTITUTION = 11750
CONDITIONAL = 12010
ELSE_BRANCH = 22010
END_BRANCH = 22011
LABEL = 12110
JUMP_TO_LABEL = 12120
LOOP = 12210
END_LOOP = 22210
BREAK_LOOP = 12220
END_EVENT = 12310
ERASE_EVENT = 12320
CALL_EVENT = 12330
COMMENT = 12410
OPEN_SAVE_MENU = 11910
SAVE_ACCESS = 11930
OPEN_MAIN_MENU = 11950
MENU_ACCESS = 11960
RETURN_TO_TITLE = 12510
COMMENT_2 = 22410

# RM2k character references
REF_PLAYER = 10001
REF_BOAT, REF_SHIP, REF_AIRSHIP = 10002, 10003, 10004
REF_THIS_EVENT = 10005
# The vehicles as MV character ids RM2kCompat.js resolves ($gameMap.boat()...).
VEHICLE_REFS = {REF_BOAT: -2, REF_SHIP: -3, REF_AIRSHIP: -4}
VEHICLE_JS = {-2: "$gameMap.boat()", -3: "$gameMap.ship()", -4: "$gameMap.airship()"}

# RM2k move-route opcode -> MV move-route code
MOVE_MAP = {
    0: 4, 1: 3, 2: 1, 3: 2,           # up / right / down / left
    4: 8, 5: 6, 6: 5, 7: 7,           # diagonals
    8: 9, 9: 10, 10: 11, 11: 12,      # random / toward / away / forward
    12: 19, 13: 18, 14: 16, 15: 17,   # face up / right / down / left
    16: 20, 17: 21, 18: 22, 19: 23,   # turn 90R / 90L / 180 / 90 random
    20: 24, 21: 25, 22: 26,           # face random / toward / away
    23: 15,                           # wait
    26: 35, 27: 36,                   # lock / unlock facing
    36: 37, 37: 38,                   # walk everywhere on / off
    38: 32, 39: 31,                   # stop / start walk animation
}

# MV command codes
MV_TEXT, MV_TEXT_LINE = 101, 401
MV_CHOICES, MV_WHEN, MV_WHEN_CANCEL, MV_CHOICES_END = 102, 402, 403, 404
MV_INPUT_NUMBER = 103
MV_COMMENT, MV_COMMENT_LINE = 108, 408
MV_IF, MV_ELSE, MV_END_IF = 111, 411, 412
MV_LOOP, MV_REPEAT_ABOVE, MV_BREAK_LOOP = 112, 413, 113
MV_EXIT_EVENT = 115
MV_COMMON_EVENT = 117
MV_LABEL, MV_JUMP_LABEL = 118, 119
MV_SWITCHES, MV_VARIABLES = 121, 122
MV_GOLD, MV_ITEMS, MV_WEAPONS, MV_ARMORS = 125, 126, 127, 128
MV_CHANGE_PARTY = 129
MV_TRANSFER = 201
MV_SET_EVENT_LOCATION = 203
MV_SET_MOVE_ROUTE = 205
MV_WAIT_MOVE = 206
MV_TRANSPARENCY = 211
MV_SHOW_ANIMATION = 212
MV_ERASE_EVENT = 214
MV_TINT, MV_FLASH, MV_SHAKE = 223, 224, 225
MV_WAIT = 230
MV_SHOW_PICTURE, MV_MOVE_PICTURE, MV_ERASE_PICTURE = 231, 232, 235
MV_ROTATE_PICTURE, MV_TINT_PICTURE = 233, 234
MV_CHANGE_EXP, MV_CHANGE_LEVEL = 315, 316
MV_CHANGE_NAME, MV_CHANGE_NICKNAME = 320, 324
MV_CHANGE_VEHICLE_IMAGE, MV_CHANGE_VEHICLE_BGM = 323, 140
MV_SET_VEHICLE_LOCATION, MV_VEHICLE_ON_OFF = 202, 206
MV_SHOP, MV_SHOP_ITEM = 302, 605
MV_BATTLE_WIN, MV_BATTLE_ESCAPE, MV_BATTLE_LOSE, MV_BATTLE_END = 601, 602, 603, 604
MV_FADEOUT, MV_FADEIN, MV_RECOVER = 221, 222, 314
MV_BATTLE_ANIMATION, MV_ABORT_BATTLE = 337, 340
MV_CHANGE_HP, MV_CHANGE_MP, MV_CHANGE_STATE = 311, 312, 313
MV_CHANGE_CLASS = 321
MV_ENEMY_HP, MV_ENEMY_MP, MV_ENEMY_STATE, MV_ENEMY_APPEAR = 331, 332, 333, 335
MV_SAVE_ACCESS, MV_MENU_ACCESS = 134, 135
MV_OPEN_MENU, MV_OPEN_SAVE, MV_RETURN_TO_TITLE = 351, 352, 354
MV_PLAY_BGM, MV_FADEOUT_BGM = 241, 242
MV_PLAY_SE = 250
MV_PLAY_MOVIE = 261
MV_CHANGE_PARALLAX = 284
MV_CHANGE_ACTOR_IMAGES = 322
MV_SCRIPT = 355

# RM2k facing (0 up, 1 right, 2 down, 3 left) -> MV (8, 6, 2, 4)
_FACING = {0: 8, 1: 6, 2: 2, 3: 4}

# \N[n] in message text: the actor's name.
_ACTOR_NAME = re.compile(r"(\\[Nn])\[(\d+)\]")

# RM2k actor property -> MV actor game-data index.  RM2k has no "luck", and
# its single "spirit" stat answers for both of MV's mat and mdf.
_ACTOR_STAT = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 10}

# RM2k character property (1 x, 2 y, 3 facing, 4 screen x, 5 screen y)
# -> MV character game-data index.  RM2k's 0 ("map id") has no counterpart.
_CHARACTER_PROP = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4}

# RM2k "other" data (0 money, 1 timer seconds, 2 party size, 3 saves,
# 4 battles, 5 victories, 6 defeats, 7 escapes, 8 music position)
# -> MV "other" game-data index (0 map, 1 party size, 2 gold, 3 steps,
# 4 play time, 5 timer, 6 saves, 7 battles, 8 wins, 9 escapes).
_OTHER_DATA = {0: 2, 1: 5, 2: 1, 3: 6, 4: 7, 5: 8, 7: 9}
# The ones MV does not count, kept by RM2kCompat.js.
_OTHER_JS = {6: "($gameSystem._rm2kDefeats || 0)", 8: "0",
             9: "$gameSystem.rm2kTimer2()"}

# The same two tables as JavaScript, for the operands that have to be scripted.
_ACTOR_FIELD = {0: "level", 1: "currentExp()", 2: "hp", 3: "mp", 4: "mhp",
                5: "mmp", 6: "atk", 7: "def", 8: "mat", 9: "agi"}
_CHARACTER_FIELD = {1: "x", 2: "y", 3: "direction()", 4: "screenX()",
                    5: "screenY()"}
# RM2k actor properties 10..14: the RM2k id of the weapon, shield, armour,
# helmet and accessory worn -> RM2k slot number for rm2kEquippedId().
_ACTOR_EQUIP_SLOT = {10: 0, 11: 1, 12: 2, 13: 3, 14: 4}
# RM2003 battle operand: enemy property -> Game_Enemy field.
_ENEMY_FIELD = {0: "hp", 1: "mp", 2: "mhp", 3: "mmp", 4: "atk", 5: "def",
                6: "mat", 7: "agi"}

MV_SCROLL_MAP = 204
MV_CHANGE_EQUIPMENT = 319
MV_CONTROL_TIMER = 124
MV_FADEOUT_SCREEN = 221
MV_FADEIN_SCREEN = 222
MV_WEATHER = 236
MV_CHANGE_TILESET = 282
MV_RECOVER_ALL = 314
MV_CHANGE_PARAMETER = 317
MV_CHANGE_SKILL = 318
MV_BATTLE = 301
MV_SHOP = 302
MV_NAME_INPUT = 303
MV_GAME_OVER = 353

# RM2k system music slots; only the two MZ/MV can actually change are mapped.
SYSTEM_BGM_SETTER = {0: "setBattleBgm", 1: "setVictoryMe"}
# RM2k system music slots 3..5 are the boat, ship and airship themes.
SYSTEM_BGM_VEHICLE = {3: 0, 4: 1, 5: 2}
SYSTEM_BGM_INN, SYSTEM_BGM_GAMEOVER = 2, 6
# The slots MV/MZ play as an ME: victory, inn, game over.
SYSTEM_BGM_AS_ME = (1, SYSTEM_BGM_INN, SYSTEM_BGM_GAMEOVER)
# RM2k system sound slot -> MV's $dataSystem.sounds index.
SYSTEM_SE_SLOT = {0: 0, 1: 1, 2: 2, 3: 3, 4: 7, 5: 8, 6: 9, 7: 10, 8: 14,
                  9: 18, 10: 11, 11: 22}
# Terms (chunk ids in RPG_RT.ldb) for the two inn styles: text before the
# price, after it, the question, then the yes and no answers.
INN_TERMS = {0: ("0x50", "0x51", "0x52", "0x53", "0x54"),
             1: ("0x55", "0x56", "0x57", "0x58", "0x59")}
CURRENCY_TERM = "0x5F"
# RM2k move opcodes 0..7 as (dx, dy), for working out where a jump lands.
MOVE_OFFSETS = {0: (0, -1), 1: (1, 0), 2: (0, 1), 3: (-1, 0),
                4: (1, -1), 5: (1, 1), 6: (-1, 1), 7: (-1, -1)}
FACE_OPCODES = {12, 13, 14, 15}

# RM2k stat order (maxhp, maxsp, attack, defense, spirit, agility) onto MV's
# (maxhp, maxmp, atk, def, mat, mdf, agi, luk).
PARAM_MAP = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 6}
# RM2k weather (0 none, 1 rain, 2 snow) onto MV's named types.
# RM2k weather: 0 none, 1 rain, 2 snow, 3 fog, 4 sandstorm.  MV has no fog;
# a sandstorm is closest to MV's storm.
WEATHER_MAP = {0: "none", 1: "rain", 2: "snow", 3: "none", 4: "storm"}
# RM2k teleport facing (RM2003) -> MV direction; 0 keeps the current one.
TELEPORT_FACING = {0: 0, 1: 8, 2: 6, 3: 2, 4: 4}

# A movie name's own extension; MV/MZ append the one they play.
MOVIE_EXTENSION = re.compile(r"\.(avi|mpe?g|wmv|mp4|webm|ogv|mov)$", re.IGNORECASE)

# Suffix of the opaque copies of pictures (see Translator.opaque_pictures).
OPAQUE_SUFFIX = "__rm2kopaque"

# RM2k transitions 19 ("instant") and 20 ("none") cut instead of fading.
INSTANT_TRANSITIONS = (19, 20)

# RM2k's wait unit is 1/10 s; MV counts frames at 60 fps.
WAIT_FRAMES = 6
# RM2k screens are 320x240, MV's default is 816x624.
PICTURE_SCALE = 816 / 320


class Translator:
    """Stateful because RM2k spreads some concepts over several commands."""

    def __init__(self, id_maps, log=log, terms: dict | None = None,
                 database: dict | None = None):
        self.ids = id_maps
        self.log = log
        self.terms = terms or {}
        database = database or {}
        rm2k3 = database.get("_engine") == "rm2k3"
        # RM2003 1.10+ picture options (variables, sprite sheets, layers).
        self.picture_extensions = rm2k3 and bool(database.get("_english"))
        # Before 1.10 RM2003 gave a picture's lower half its own transparency.
        self.bottom_transparency = rm2k3 and not database.get("_english")
        self.max_picture_id = 0
        self.picture_ids_from_variables = False
        # Pictures shown with "transparent colour" off: assets.py writes an
        # opaque copy of each, named with OPAQUE_SUFFIX; names a variable
        # completes are matched as (prefix, number of digits).
        self.opaque_pictures: set[str] = set()
        self.opaque_patterns: set[tuple[str, int]] = set()
        self._unsupported: collections.Counter = collections.Counter()
        self.rm2k3 = rm2k3
        # RM2000 1.6x (EasyRPG: RPG2kE) words the inn greeting with %V/%U.
        self.rm2k_english = not rm2k3 and bool(database.get("_english"))
        # Music RM2k keeps with the BGM but MV/MZ play as an ME (victory, inn
        # and game over themes changed by event): convert copies these into
        # audio/me as well.
        self.me_music: set[str] = set()
        # Indents at which a battle with "escape ends the event" still waits
        # for its defeat branch, where the escape branch has to go.
        self._escape_exits: set[int] = set()
        self._choice_index = 0
        self._face_name = ""
        self._face_index = 0

    @property
    def unsupported(self) -> collections.Counter:
        return self._unsupported

    # -- entry point --------------------------------------------------------
    def translate(self, commands: list[dict], where: str = "") -> list[dict]:
        out: list[dict] = []
        index = 0
        while index < len(commands):
            index = self._one(commands, index, out, where)
        out.append({"code": 0, "indent": 0, "parameters": []})
        return out

    def _one(self, commands: list[dict], index: int, out: list, where: str) -> int:
        cmd = commands[index]
        code = cmd["code"]
        indent = cmd["indent"]
        params = cmd["parameters"]
        text = cmd["string"]
        emit = lambda c, p=(): out.append(
            {"code": c, "indent": indent, "parameters": list(p)})

        if code in (NOP, BLOCK_END):
            emit(0)
        elif code == MESSAGE_OPTIONS:
            # RM2k: [transparent, 0 top / 1 middle / 2 bottom, 0 fixed /
            # 1 avoid covering the hero, other events keep moving].  Game
            # state in RM2k, so RM2kCompat.js keeps it and applies it to every
            # message that follows while playing - the converter would only
            # see the order it happens to walk the events in.
            values = (list(params) + [0, 2, 0, 0])[:4]
            emit(MV_SCRIPT, [f"$gameSystem.rm2kSetMessageOptions("
                             f"{'true' if values[0] else 'false'}, "
                             f"{_clamp(values[1], 0, 2)}, "
                             f"{'true' if values[2] == 0 else 'false'}, "
                             f"{'true' if values[3] else 'false'});"])
        elif code == CHANGE_FACE:
            # In RM2k the portrait is global game state that lasts until it is
            # changed again, while MV carries it on each message.  Baking it in
            # would make the result depend on the order the converter happens
            # to walk the events, so it is set at runtime instead and
            # RM2kCompat.js applies it to messages that carry none.
            # RM2k: [index, on the right, mirrored]
            emit(MV_SCRIPT, [f"this.rm2kSetFace({_js_string(text)}, "
                             f"{params[0] if params else 0}, "
                             f"{'true' if len(params) > 1 and params[1] else 'false'}, "
                             f"{'true' if len(params) > 2 and params[2] else 'false'});"])
        elif code == SHOW_MESSAGE:
            # Five parameters: MZ reads a speaker name as the fifth and MV
            # simply ignores anything past the fourth.
            # Window and position are RM2k game state, applied by
            # RM2kCompat.js (see MESSAGE_OPTIONS); these are MV's defaults.
            emit(MV_TEXT, ["", 0, 0, 2, ""])
            emit(MV_TEXT_LINE, [self._text(text)])
            lines = 1
            while index + 1 < len(commands) and commands[index + 1]["code"] == SHOW_MESSAGE_2:
                index += 1
                lines += 1
                out.append({"code": MV_TEXT_LINE, "indent": indent,
                            "parameters": [self._text(commands[index]["string"])]})
            # RPG_RT puts the choices or the number input into the message
            # only when they fit in its four lines; otherwise they follow in
            # a box of their own.  MV merges whatever comes next, so a
            # comment keeps them apart.
            if index + 1 < len(commands):
                following = commands[index + 1]
                if ((following["code"] == SHOW_CHOICE
                        and lines + _choice_count(commands, index + 1) > 4)
                        or (following["code"] == INPUT_NUMBER and lines >= 4)):
                    emit(MV_COMMENT, ["[MakerBridge] does not fit into the message"])
        elif code == SHOW_MESSAGE_2:
            emit(MV_TEXT_LINE, [self._text(text)])
        elif code == SHOW_CHOICE:
            index = self._choices(commands, index, out, indent)
        elif code == CHOICE_OPTION:
            # Its own slot number, not a running count: choices can nest.
            slot = params[0] if params else 0
            if slot >= CANCEL_SLOT:
                emit(MV_WHEN_CANCEL)
            else:
                emit(MV_WHEN, [slot, self._text(text)])
        elif code == CHOICE_END:
            emit(MV_CHOICES_END)
        elif code == INPUT_NUMBER:
            emit(MV_INPUT_NUMBER, [params[1] if len(params) > 1 else 1,
                                   params[0] if params else 1])
        elif code == CONTROL_SWITCHES:
            self._switches(params, emit)
        elif code == CONTROL_VARS:
            self._variables(params, emit, where)
        elif code == CHANGE_GOLD:
            # RM2k: [0 gain / 1 lose, 0 literal / 1 variable, amount]
            emit(MV_GOLD, [params[0] if params else 0,
                           1 if len(params) > 1 and params[1] else 0,
                           params[2] if len(params) > 2 else 0])
        elif code == CHANGE_ITEMS:
            self._items(params, emit)
        elif code == CHANGE_PARTY:
            if len(params) > 1 and params[1]:       # actor id in a variable
                verb = "removeActor" if params[0] else "addActor"
                emit(MV_SCRIPT, [f"$gameParty.{verb}($gameVariables.value({params[2]}));"])
            else:
                actor = self.ids.actors.get(params[2] if len(params) > 2 else 1, 1)
                emit(MV_CHANGE_PARTY, [actor, params[0] if params else 0, 0])
        elif code == CHANGE_SPRITE:
            # MV's "Change Actor Images" sets face and battler as well and
            # would blank them; RM2k changes only the walking sprite.
            # RM2k: [actor, index, translucent]; RM2kCompat.js draws the
            # hero translucent while that actor leads.
            actor = self.ids.actors.get(params[0] if params else 1, 1)
            emit(MV_SCRIPT, [f"$gameActors.actor({actor}).setCharacterImage("
                             f"{_js_string(text)}, {params[1] if len(params) > 1 else 0}); "
                             f"$gameActors.actor({actor})._rm2kTransparent = "
                             f"{'true' if len(params) > 2 and params[2] else 'false'}; "
                             "$gamePlayer.refresh();"])
        elif code == CHANGE_FACE_GRAPHIC:
            actor = self.ids.actors.get(params[0] if params else 1, 1)
            emit(MV_SCRIPT, [f"$gameActors.actor({actor}).setFaceImage("
                             f"{_js_string(text)}, {params[1] if len(params) > 1 else 0});"])
        elif code in (CHANGE_EXP, CHANGE_LEVEL):
            self._exp_or_level(code, params, emit)
        elif code == CHANGE_HERO_NAME:
            emit(MV_CHANGE_NAME, [self.ids.actors.get(params[0] if params else 1, 1), text])
        elif code == CHANGE_HERO_TITLE:
            emit(MV_CHANGE_NICKNAME,
                 [self.ids.actors.get(params[0] if params else 1, 1), text])
        elif code == CHANGE_VEHICLE_GRAPHIC:
            emit(MV_CHANGE_VEHICLE_IMAGE, [_clamp(params[0] if params else 0, 0, 2),
                                           text, params[1] if len(params) > 1 else 0])
        elif code == ENTER_EXIT_VEHICLE:
            emit(MV_VEHICLE_ON_OFF)
        elif code == SET_VEHICLE_LOCATION:
            # RM2k: [vehicle, 0 literal / 1 variables, map, x, y]
            by_variable = 1 if (len(params) > 1 and params[1]) else 0
            map_id = params[2] if len(params) > 2 else 0
            if not by_variable:
                map_id = self.ids.maps.get(map_id, map_id)
            if params and params[0] < 0:
                # Vehicle -1 is the party itself (RPG_RT's id of "no
                # vehicle"): it moves without a transition.
                x = params[3] if len(params) > 3 else 0
                y = params[4] if len(params) > 4 else 0
                if by_variable:
                    where = (f"$gameVariables.value({map_id}), $gameVariables.value({x}), "
                             f"$gameVariables.value({y})")
                else:
                    where = f"{map_id}, {x}, {y}"
                emit(MV_SCRIPT, [f"this.rm2kMoveParty({where});"])
                return index + 1
            emit(MV_SET_VEHICLE_LOCATION,
                 [_clamp(params[0] if params else 0, 0, 2), by_variable, map_id,
                  params[3] if len(params) > 3 else 0,
                  params[4] if len(params) > 4 else 0])
        elif code == CHANGE_SYSTEM_SE:
            slot = SYSTEM_SE_SLOT.get(params[0] if params else -1)
            if slot is None:
                self._unsupported[code] += 1
                emit(MV_COMMENT, [f"[MakerBridge] system sound {params} has no MV slot"])
            else:
                sound = _audio(text, list(params[1:]), bgm=False)
                emit(MV_SCRIPT, [f"$gameSystem.rm2kSetSound({slot}, "
                                 f"{json.dumps(sound, ensure_ascii=False)});"])
        elif code == HALT_ALL_MOVEMENT:
            emit(MV_SCRIPT, ["this.rm2kHaltAllMoves();"])
        elif code == CHANGE_BATTLE_COMMANDS:
            # RM2003: [actor mode, actor, command, 1 add / 0 remove];
            # command 0 with "remove" clears the list.  RM2kCompat.js keeps
            # the lists.
            add = "true" if len(params) > 3 and params[3] else "false"
            emit(MV_SCRIPT, [f"{self._actors_js(params)}.forEach(function(a) {{ if (a) "
                             f"a.rm2kChangeCommand({params[2] if len(params) > 2 else 0}, "
                             f"{add}); }});"])
        elif code == CHANGE_HP:
            # RM2k: [actor mode, actor, 0 gain / 1 lose, 0 literal / 1
            # variable, amount, may kill]
            emit(MV_CHANGE_HP, self._actor_target(params) + [
                params[2] if len(params) > 2 else 0, 1 if len(params) > 3 and params[3] else 0,
                params[4] if len(params) > 4 else 0, bool(params[5]) if len(params) > 5 else False])
        elif code == CHANGE_SP:
            emit(MV_CHANGE_MP, self._actor_target(params) + [
                params[2] if len(params) > 2 else 0, 1 if len(params) > 3 and params[3] else 0,
                params[4] if len(params) > 4 else 0])
        elif code == CHANGE_CONDITION:
            # RM2k: [actor mode, actor, 0 add / 1 remove, state]
            state = params[3] if len(params) > 3 else 1
            emit(MV_CHANGE_STATE, self._actor_target(params) + [
                params[2] if len(params) > 2 else 0, self.ids.states.get(state, state)])
        elif code == SIMULATED_ATTACK:
            # RM2k: [actor mode, actor, attack, defense %, spirit %,
            # variance, store damage, variable]
            values = (list(params) + [0] * 8)[:8]
            emit(MV_SCRIPT, [f"this.rm2kSimulatedAttack({self._actors_js(params)}, "
                             f"{values[2]}, {values[3]}, {values[4]}, {values[5]}, "
                             f"{values[7] if values[6] else 0});"])
        elif code == CHANGE_SYSTEM_GRAPHICS:
            # The window skin; RM2kCompat.js loads the converted one.
            emit(MV_SCRIPT, [f"$gameSystem.rm2kSetWindowskin({_js_string(text)});"])
        elif code == CHANGE_TRANSITIONS:
            # RM2k: [which (0/1 teleport out/in, 2/3 battle start, 4/5 battle
            # end), transition type]
            emit(MV_SCRIPT, [f"$gameSystem.rm2kSetTransition("
                             f"{params[0] if params else 0}, {params[1] if len(params) > 1 else 0});"])
        elif code == CHANGE_ENCOUNTER_STEPS:
            emit(MV_SCRIPT, [f"$gameMap.rm2kSetEncounterStep({params[0] if params else 25});"])
        elif code in (TELEPORT_TARGETS, ESCAPE_TARGET):
            self._travel_target(code, params, emit)
        elif code in (TELEPORT_ACCESS, ESCAPE_ACCESS):
            kind = "teleport" if code == TELEPORT_ACCESS else "escape"
            emit(MV_SCRIPT, [f"$gameSystem.rm2kAllow(\"{kind}\", "
                             f"{'true' if params and params[0] else 'false'});"])
        elif code == MONSTER_HP:
            self._monster_points(params, emit, hp=True)
        elif code == MONSTER_SP:
            self._monster_points(params, emit, hp=False)
        elif code == MONSTER_CONDITION:
            state = params[2] if len(params) > 2 else 1
            emit(MV_ENEMY_STATE, [params[0] if params else 0,
                                  params[1] if len(params) > 1 else 0,
                                  self.ids.states.get(state, state)])
        elif code == SHOW_HIDDEN_MONSTER:
            emit(MV_ENEMY_APPEAR, [params[0] if params else 0])
        elif code == CHANGE_BATTLE_BG:
            emit(MV_SCRIPT, [f"$gameTemp.rm2kBattleback = {_js_string(text)}; "
                             "this.rm2kRefreshBattleback();"])
        elif code == FORCE_FLEE:
            # RM2003: [0 party / 1 all enemies / 2 one enemy, enemy, 0 obey
            # / 1 ignore the battle condition].  Only a pincer or surround
            # condition stops a flight, and converted battles have none, so
            # the third value changes nothing here.
            who = params[0] if params else 0
            if who == 0:
                emit(MV_SCRIPT, ["BattleManager.rm2kForceEscape();"])
            elif who == 1:
                emit(MV_SCRIPT, ["$gameTroop.members().forEach(function(e) { "
                                 "if (e.isAlive() && e.isAppeared()) { e.escape(); } });"])
            else:
                emit(MV_SCRIPT, [f"var e = $gameTroop.members()[{params[1] if len(params) > 1 else 0}]; "
                                 "if (e && e.isAlive() && e.isAppeared()) { e.escape(); }"])
        elif code == ENABLE_COMBO:
            # RM2003: [actor, battle command, number of hits]
            actor = self.ids.actors.get(params[0] if params else 1, 1)
            emit(MV_SCRIPT, [f"$gameActors.actor({actor}).rm2kSetCombo("
                             f"{params[1] if len(params) > 1 else 0}, "
                             f"{params[2] if len(params) > 2 else 1});"])
        elif code == CHANGE_CLASS:
            # RM2003 (EasyRPG CommandChangeClass): [actor mode, actor, class
            # (0 none: the hero's own), 0 keep level / 1 back to 1, skills
            # 0 keep / 1 replace / 2 add, stats 0 keep / 1 halve / 2 class
            # at level 1 / 3 class at current level, show message]
            values = (list(params) + [0] * 7)[:7]
            class_id = self.ids.classes.get(values[2], 0) if values[2] else 0
            emit(MV_SCRIPT, [f"this.rm2kChangeClass({self._actors_js(params)}, {class_id}, "
                             f"{1 if values[3] else 0}, {values[4]}, {values[5]}, "
                             f"{'true' if values[6] else 'false'});"])
        elif code == OPEN_LOAD_MENU:
            emit(MV_SCRIPT, ["SceneManager.push(Scene_Load);"])
        elif code == EXIT_GAME:
            emit(MV_SCRIPT, ["SceneManager.exit();"])
        elif code == TOGGLE_ATB:
            emit(MV_SCRIPT, ["$gameSystem._rm2kAtbWait = !$gameSystem._rm2kAtbWait;"])
        elif code == TOGGLE_FULLSCREEN:
            emit(MV_SCRIPT, ["Graphics._switchFullScreen();"])
        elif code == OPEN_OPTIONS:
            emit(MV_SCRIPT, ["SceneManager.push(Scene_Options);"])
        elif code == BATTLE_CALL_COMMON:
            common = params[0] if params else 1
            emit(MV_COMMON_EVENT, [self.ids.common_events.get(common, common)])
        elif code == BATTLE_CONDITIONAL:
            self._battle_conditional(params, emit)
        elif code == BATTLE_ELSE:
            emit(MV_ELSE)
        elif code == BATTLE_END_BRANCH:
            emit(MV_END_IF)
        elif code == BATTLE_TERMINATE:
            emit(MV_ABORT_BATTLE)
        elif code == BATTLE_SHOW_ANIMATION:
            # RM2003: [animation, target (-1 all; enemies counted from 0,
            # allies from 1), wait, 1 allies].  RM2kCompat.js shows it and
            # waits for it.
            anim = self.ids.animations.get(params[0] if params else 1, 1)
            target = params[1] if len(params) > 1 else -1
            wait = len(params) > 2 and params[2]
            allies = self.rm2k3 and len(params) > 3 and params[3]
            emit(MV_SCRIPT, [f"this.rm2kBattleAnimation({anim}, {target}, "
                             f"{'true' if allies else 'false'}, {'true' if wait else 'false'});"])
        elif code == OPEN_SHOP:
            self._shop(params, emit)
        elif code == SHOW_INN:
            self._inn(params, out, indent)
        elif code in (BATTLE_VICTORY, BATTLE_ESCAPE, BATTLE_DEFEAT, BATTLE_END):
            if code != BATTLE_VICTORY and indent in self._escape_exits:
                self._escape_exits.discard(indent)
                if code != BATTLE_ESCAPE:
                    # "Escape ends the event" with a defeat branch: RPG_RT
                    # writes no escape branch, but fleeing still ends it.
                    emit(MV_BATTLE_ESCAPE)
                    out.append({"code": MV_EXIT_EVENT, "indent": indent + 1, "parameters": []})
                    out.append({"code": 0, "indent": indent + 1, "parameters": []})
            emit({BATTLE_VICTORY: MV_BATTLE_WIN, BATTLE_ESCAPE: MV_BATTLE_ESCAPE,
                  BATTLE_DEFEAT: MV_BATTLE_LOSE, BATTLE_END: MV_BATTLE_END}[code])
        elif code in (SHOP_DEALT, INN_STAYED):
            flag = "_rm2kShopDealt" if code == SHOP_DEALT else "_rm2kInnStayed"
            emit(MV_IF, [12, f"!!$gameTemp.{flag}"])
        elif code in (SHOP_NOT_DEALT, INN_NOT_STAYED):
            emit(MV_ELSE)
        elif code in (SHOP_END, INN_END):
            emit(MV_END_IF)
        elif code == TELEPORT:
            map_id = self.ids.maps.get(params[0], params[0]) if params else 1
            # RM2003 can turn the hero: 0 keep, 1 up, 2 right, 3 down, 4 left.
            facing = TELEPORT_FACING.get(params[3] if len(params) > 3 else 0, 0)
            emit(MV_TRANSFER, [0, map_id,
                               params[1] if len(params) > 1 else 0,
                               params[2] if len(params) > 2 else 0, facing, 0])
        elif code == CHANGE_EVENT_LOCATION:
            # RM2k: [event, 0 literal / 1 variables, x, y, (RM2003) facing
            # 0 keep / 1 up / 2 right / 3 down / 4 left]; MV takes the same
            # two modes as 0 and 1.  RPG_RT turns the event only when the
            # place is literal.
            by_variable = 1 if (len(params) > 1 and params[1]) else 0
            facing = 0
            if self.rm2k3 and not by_variable and len(params) > 4:
                facing = TELEPORT_FACING.get(params[4], 0)
            emit(MV_SET_EVENT_LOCATION,
                 [self._event_ref(params[0] if params else REF_THIS_EVENT),
                  by_variable,
                  params[2] if len(params) > 2 else 0,
                  params[3] if len(params) > 3 else 0, facing])
        elif code == SWAP_EVENTS:
            # MV's "exchange with another event" is location mode 2.
            emit(MV_SET_EVENT_LOCATION,
                 [self._event_ref(params[0] if params else REF_THIS_EVENT), 2,
                  self._event_ref(params[1] if len(params) > 1 else REF_THIS_EVENT),
                  0, 0])
        elif code == TINT_SCREEN:
            r, g, b, s = (params + [100] * 4)[:4]
            emit(MV_TINT, [[_tone(r), _tone(g), _tone(b), 255 - _clamp(s * 255 // 100, 0, 255)],
                           (params[4] if len(params) > 4 else 0) * WAIT_FRAMES,
                           bool(params[5]) if len(params) > 5 else False])
        elif code == FLASH_SCREEN:
            # RM2003 adds a seventh value: 0 once, 1 begin (repeats until
            # ended), 2 end.  RM2kCompat.js does the repeating.
            r, g, b, p = (params + [31] * 4)[:4]
            color = [r * 8, g * 8, b * 8, p * 8]
            frames = (params[4] if len(params) > 4 else 0) * WAIT_FRAMES
            mode = params[6] if self.rm2k3 and len(params) > 6 else 0
            if mode == 1:
                emit(MV_SCRIPT, [f"$gameScreen.rm2kFlashBegin({json.dumps(color)}, {frames});"])
            elif mode == 2:
                emit(MV_SCRIPT, ["$gameScreen.rm2kFlashEnd();"])
            else:
                emit(MV_FLASH, [color, frames,
                                bool(params[5]) if len(params) > 5 else False])
        elif code == SHAKE_SCREEN:
            # RM2003 adds a fifth value: 0 once, 1 begin (until stopped),
            # 2 stop; "once" with no duration stops it too.  Stopping lets
            # the screen settle the way MV ends any shake.
            strength = params[0] if params else 5
            speed = params[1] if len(params) > 1 else 5
            tenths = params[2] if len(params) > 2 else 10
            mode = params[4] if self.rm2k3 and len(params) > 4 else 0
            if mode == 2 or (mode == 0 and tenths <= 0):
                emit(MV_SCRIPT, ["$gameScreen._shakeDuration = 0;"])
            elif mode == 1:
                emit(MV_SCRIPT, [f"$gameScreen.startShake({strength}, {speed}, 1000000000);"])
            else:
                emit(MV_SHAKE, [strength, speed, tenths * WAIT_FRAMES,
                                bool(params[3]) if len(params) > 3 else False])
        elif code == SHOW_PICTURE:
            self._show_picture(text, params, emit)
        elif code == MOVE_PICTURE:
            self._move_picture(params, emit)
        elif code == ERASE_PICTURE:
            self._erase_picture(params, emit)
        elif code == SHOW_ANIMATION:
            anim = self.ids.animations.get(params[0] if params else 1, 1)
            emit(MV_SHOW_ANIMATION,
                 [self._event_ref(params[1] if len(params) > 1 else REF_THIS_EVENT),
                  anim, bool(params[2]) if len(params) > 2 else False])
        elif code == PLAYER_VISIBILITY:
            # RM2k: 0 hides the hero, 1 shows it.  MV: 0 = transparent.
            emit(MV_TRANSPARENCY, [1 if (params and params[0]) else 0])
        elif code == MOVE_EVENT:
            self._move_event(params, emit)
        elif code == PROCEED_MOVEMENT:
            # Wait until every forced move route has finished.  (MV's 206,
            # used here before, is "get on/off vehicle", not a wait.)
            emit(MV_SCRIPT, ["this.rm2kWaitAllMoves();"])
        elif code == WAIT:
            if self.rm2k3 and len(params) > 1 and params[1]:
                # RM2003: until the decision key (EasyRPG wait_key_enter).
                emit(MV_SCRIPT, ['this.rm2kKeyInput(0, true, {"ok": true}, 0);'])
            else:
                emit(MV_WAIT, [max(1, (params[0] if params else 1) * WAIT_FRAMES)])
        elif code == PLAY_BGM:
            emit(MV_PLAY_BGM, [_audio(text, params, bgm=True)])
        elif code == FADEOUT_BGM:
            emit(MV_FADEOUT_BGM, [max(1, (params[0] if params else 1000) // 1000)])
        elif code == PLAY_SOUND:
            emit(MV_PLAY_SE, [_audio(text, params, bgm=False)])
        elif code == PLAY_MOVIE:
            # MV/MZ add the extension of the format they play themselves.
            emit(MV_PLAY_MOVIE, [MOVIE_EXTENSION.sub("", text)])
        elif code == CHANGE_PARALLAX:
            emit(MV_CHANGE_PARALLAX,
                 # RM2k: [loop x, loop y, auto x, speed x, auto y, speed y]
                 [text, bool(params[0]) if params else False,
                  bool(params[1]) if len(params) > 1 else False,
                  (parallax_speed(params[3]) if len(params) > 3 and params[2] else 0),
                  (parallax_speed(params[5]) if len(params) > 5 and params[4] else 0)])
        elif code == CONDITIONAL:
            self._conditional(params, emit, where, text)
        elif code == ELSE_BRANCH:
            emit(MV_ELSE)
        elif code == END_BRANCH:
            emit(MV_END_IF)
        elif code == LABEL:
            emit(MV_LABEL, [str(params[0] if params else 0)])
        elif code == JUMP_TO_LABEL:
            emit(MV_JUMP_LABEL, [str(params[0] if params else 0)])
        elif code == LOOP:
            emit(MV_LOOP)
        elif code == END_LOOP:
            emit(MV_REPEAT_ABOVE)
        elif code == BREAK_LOOP:
            emit(MV_BREAK_LOOP)
        elif code == END_EVENT:
            emit(MV_EXIT_EVENT)
        elif code == ERASE_EVENT:
            emit(MV_ERASE_EVENT)
        elif code == CALL_EVENT:
            self._call_event(params, emit)
        elif code in (COMMENT, COMMENT_2):
            emit(MV_COMMENT if code == COMMENT else MV_COMMENT_LINE, [text])
        elif code == CHANGE_EQUIPMENT:
            self._equipment(params, emit)
        elif code == PAN_SCREEN:
            # RM2k: [0 lock / 1 unlock / 2 pan / 3 back to the hero,
            #        direction, distance, speed, wait]
            kind = params[0] if params else 0
            speed = _clamp(params[3] if len(params) > 3 else 4, 1, 6)
            wait = bool(params[4]) if len(params) > 4 else False
            if kind == 2:
                # The fourth value is MZ's "wait"; MV ignores it.
                emit(MV_SCROLL_MAP, [_FACING.get(params[1] if len(params) > 1 else 0, 2),
                                     params[2] if len(params) > 2 else 1, speed, wait])
            elif kind in (0, 1):
                # Locked, the screen stays put while the hero walks on.
                emit(MV_SCRIPT, [f"$gameMap._rm2kPanLocked = {'true' if kind == 0 else 'false'};"])
            else:
                emit(MV_SCRIPT, [f"this.rm2kPanReset({speed}, {'true' if wait else 'false'});"])
        elif code == KEY_INPUT:
            # Only the keys it asks about count; RM2kCompat.js does the
            # reading and waiting, in RPG_RT's order.
            variable = params[0] if params else 1
            wait = bool(params[1]) if len(params) > 1 else False
            keys, time_variable = _key_input_layout(params, self.rm2k3)
            emit(MV_SCRIPT, [f"this.rm2kKeyInput({variable}, {'true' if wait else 'false'}, "
                             f"{json.dumps(keys)}, {time_variable});"])
        elif code == FLASH_SPRITE:
            # No MV command for this; RM2kCompat.js adds the behaviour.
            target = self._event_ref(params[0] if params else REF_THIS_EVENT)
            r, g, b, power = (list(params[1:5]) + [31] * 4)[:4]
            duration = params[5] if len(params) > 5 else 10
            emit(MV_SCRIPT,
                 [f"this.rm2kFlashCharacter({target}, {r}, {g}, {b}, "
                  f"{power}, {duration * WAIT_FRAMES});"])
            if len(params) > 6 and params[6]:
                emit(MV_WAIT, [max(1, duration * WAIT_FRAMES)])
        elif code == TILE_SUBSTITUTION:
            # RM2k: [0 lower / 1 upper layer, old chipset tile, new one];
            # RM2kCompat.js swaps the tiles on the map and keeps the change.
            emit(MV_SCRIPT, [f"$gameMap.rm2kSubstitute({params[0] if params else 0}, "
                             f"{params[1] if len(params) > 1 else 0}, "
                             f"{params[2] if len(params) > 2 else 0});"])
        elif code in (ERASE_SCREEN, SHOW_SCREEN):
            # The parameter is a transition, -1 meaning the system's one.
            # MV can only fade; "instant" and "none" become a cut.
            transition = params[0] if params else -1
            erase = code == ERASE_SCREEN
            if transition in INSTANT_TRANSITIONS:
                emit(MV_SCRIPT, [f"$gameScreen.startFade{'Out' if erase else 'In'}(1);"])
            elif transition == -1:
                emit(MV_SCRIPT, [f"this.rm2kSystemTransition({'true' if erase else 'false'});"])
            else:
                emit(MV_FADEOUT_SCREEN if erase else MV_FADEIN_SCREEN)
        elif code == WEATHER:
            kind = WEATHER_MAP.get(params[0] if params else 0, "none")
            # RM2k strength 0 weak, 1 medium, 2 strong; MV power 1..9.
            power = _clamp(((params[1] if len(params) > 1 else 0) + 1) * 3, 1, 9)
            emit(MV_WEATHER, [kind, power, 60, False])
        elif code == CHANGE_TILESET:
            rm_id = params[0] if params else 1
            emit(MV_CHANGE_TILESET, [self.ids.tilesets.get(rm_id, rm_id)])
        elif code == FULL_HEAL:
            emit(MV_RECOVER_ALL, self._actor_target(params))
        elif code == CHANGE_SKILLS:
            self._change_skills(params, emit)
        elif code == CHANGE_PARAMETERS:
            self._change_parameters(params, emit)
        elif code == TIMER_OPERATION:
            self._timer(params, emit)
        elif code == MEMORIZE_LOCATION:
            a, b, c2 = (list(params) + [1, 2, 3])[:3]
            emit(MV_SCRIPT, [f"$gameVariables.setValue({a}, $gameMap.mapId()); "
                             f"$gameVariables.setValue({b}, $gamePlayer.x); "
                             f"$gameVariables.setValue({c2}, $gamePlayer.y);"])
        elif code == RECALL_TO_LOCATION:
            a, b, c2 = (list(params) + [1, 2, 3])[:3]
            emit(MV_TRANSFER, [1, a, b, c2, 0, 0])
        elif code == STORE_TERRAIN_ID:
            self._store_at_position(params, emit, "$gameMap.rm2kTerrainId")
        elif code == STORE_EVENT_ID:
            self._store_at_position(params, emit, "$gameMap.eventIdXy")
        elif code == GAME_OVER:
            emit(MV_GAME_OVER)
        elif code == ENEMY_ENCOUNTER:
            self._battle(text, params, emit, out, indent)
        elif code == ENTER_HERO_NAME:
            actor = self.ids.actors.get(params[0] if params else 1, 1)
            emit(MV_NAME_INPUT, [actor, 8])
        elif code == CHANGE_SYSTEM_BGM:
            self._system_bgm(text, params, emit)
        elif code == OPEN_SAVE_MENU:
            emit(MV_OPEN_SAVE)
        elif code == OPEN_MAIN_MENU:
            emit(MV_OPEN_MENU)
        elif code == SAVE_ACCESS:
            emit(MV_SAVE_ACCESS, [1 if (params and params[0]) else 0])  # 1 allow, both engines
        elif code == MENU_ACCESS:
            emit(MV_MENU_ACCESS, [1 if (params and params[0]) else 0])
        elif code == RETURN_TO_TITLE:
            emit(MV_RETURN_TO_TITLE)
        elif code == MEMORIZE_BGM:
            emit(MV_SCRIPT, ["$gameSystem.saveBgm();"])
        elif code == PLAY_MEMORIZED_BGM:
            emit(MV_SCRIPT, ["$gameSystem.replayBgm();"])
        else:
            self._unsupported[code] += 1
            emit(MV_COMMENT, [f"[MakerBridge] unsupported RM2k command {code}"])
            detail = f"params={params}" + (f" string={text!r}" if text else "")
            out.append({"code": MV_COMMENT_LINE, "indent": indent,
                        "parameters": [detail]})
        return index + 1

    # -- helpers ------------------------------------------------------------
    def _event_ref(self, ref: int) -> int:
        """RM2k character reference -> MV event id (-1 player, 0 this event).

        The boat, ship and airship become -2, -3 and -4, which
        RM2kCompat.js teaches Game_Interpreter.character() - so every MV
        command that takes a character (move route, location, animation,
        facing, character data) reaches the vehicle."""
        if ref == REF_PLAYER:
            return -1
        if ref == REF_THIS_EVENT:
            return 0
        if ref in VEHICLE_REFS:
            return VEHICLE_REFS[ref]
        return ref

    def _text(self, text: str) -> str:
        """\\N[n] names RM2k actor n; MV numbers actors itself."""
        return _ACTOR_NAME.sub(
            lambda m: f"{m.group(1)}[{self.ids.actors.get(int(m.group(2)), int(m.group(2)))}]",
            text)

    def _choices(self, commands, index, out, indent) -> int:
        # The options are not next to each other: every one is followed by
        # the commands it runs.  Collect the markers at this choice's own
        # indent up to its end marker; each carries its slot (0..3, 4 is the
        # cancel branch).
        cmd = commands[index]
        options: dict[int, str] = {}
        for look in range(index + 1, len(commands)):
            other = commands[look]
            if other["indent"] != indent:
                continue
            if other["code"] == CHOICE_END:
                break
            if other["code"] == CHOICE_OPTION:
                slot = other["parameters"][0] if other["parameters"] else len(options)
                if slot < CANCEL_SLOT:
                    options[slot] = self._text(other["string"])
        if not options:
            options = dict(enumerate(cmd["string"].split("/")))
        labels = [options.get(i, "") for i in range(max(options) + 1)]
        # RM2k: 0 cancel not allowed, 1..4 acts like that option, 5 its own
        # branch.  MV: -1, 0..3, -2.
        rm_cancel = cmd["parameters"][0] if cmd["parameters"] else 0
        cancel = -1 if rm_cancel == 0 else -2 if rm_cancel == 5 else rm_cancel - 1
        out.append({"code": MV_CHOICES, "indent": indent,
                    "parameters": [labels, cancel, 0, 2, 0]})
        return index

    def _switches(self, params, emit) -> None:
        """RM2k mode: 0 one, 1 a range, 2 the switch a *variable* points at."""
        mode, start, end, op = (params + [0, 1, 1, 0])[:4]
        if mode == 0:
            end = start         # RPG_RT reads only the first id here
        if mode == 2:
            emit(MV_SCRIPT, [f"this.rm2kSetSwitchIndirect({start}, {op});"])
            return
        if op == 2:   # toggle has no MV counterpart
            emit(MV_SCRIPT, [f"for (var i={start}; i<={end}; i++) "
                             f"$gameSwitches.setValue(i, !$gameSwitches.value(i));"])
            return
        emit(MV_SWITCHES, [start, end, 0 if op == 0 else 1])

    def _operand_js(self, operand_type: int, a: int, b: int) -> str:
        """JavaScript for an RM2k operand, for the cases MV cannot express."""
        if operand_type == 0:
            return str(a)
        if operand_type == 1:
            return f"$gameVariables.value({a})"
        if operand_type == 2:
            return f"$gameVariables.value($gameVariables.value({a}))"
        if operand_type == 3:
            low, high = min(a, b), max(a, b)
            return f"(Math.randomInt({high - low + 1}) + {low})"
        if operand_type == 4:
            mapped = self.ids.items.get(a)
            if mapped:
                table = {"item": "$dataItems", "weapon": "$dataWeapons",
                         "armor": "$dataArmors"}[mapped[0]]
                if b == 1:                  # how many party members wear it
                    return self._equipped_count_js(mapped)
                return f"$gameParty.numItems({table}[{mapped[1]}])"
            return "0"
        if operand_type == 5:
            actor = self.ids.actors.get(a, a)
            if b in _ACTOR_EQUIP_SLOT:
                return f"this.rm2kEquippedId({actor}, {_ACTOR_EQUIP_SLOT[b]})"
            field = _ACTOR_FIELD.get(b)
            if field:
                return f"($gameActors.actor({actor}) ? $gameActors.actor({actor}).{field} : 0)"
        if operand_type == 6:
            if b == 0:
                return self._map_id_js(a)
            field = _CHARACTER_FIELD.get(b)
            if field:
                if b in (4, 5):
                    return f"this.rm2kScreenPos({self._event_ref(a)}, {'true' if b == 5 else 'false'})"
                return f"{self._character_js(a)}.{field}"
        if operand_type == 7:
            # The "other" data is chosen by the first value (EasyRPG
            # ControlVariables::Other(parameters[5])).
            return {0: "$gameParty.gold()", 1: "$gameTimer.seconds()",
                    2: "$gameParty.size()", 3: "$gameSystem.saveCount()",
                    4: "$gameSystem.battleCount()", 5: "$gameSystem.winCount()",
                    7: "$gameSystem.escapeCount()"}.get(a, _OTHER_JS.get(a, "0"))
        if operand_type == 8:
            # Battle: [enemy index from 0, 0 HP / 1 SP / 2 max HP / 3 max SP
            # / 4 attack / 5 defence / 6 spirit / 7 agility].
            field = _ENEMY_FIELD.get(b)
            if field:
                return (f"($gameTroop.members()[{a}] ? "
                        f"$gameTroop.members()[{a}].{field} : 0)")
        self._unsupported[CONTROL_VARS] += 1
        return "0"

    def _equipped_count_js(self, mapped) -> str:
        """How many of the party's heroes wear an item (EasyRPG
        Game_Party::GetEquippedItemCount); plain items are never worn."""
        if mapped[0] == "item":
            return "0"
        table = "$dataWeapons" if mapped[0] == "weapon" else "$dataArmors"
        return (f"$gameParty.members().reduce(function(n, a) {{ return n + "
                f"a.equips().filter(function(e) {{ return e === {table}[{mapped[1]}]; }})"
                f".length; }}, 0)")

    def _map_id_js(self, ref: int) -> str:
        """The map a character is on.  RPG_RT 2000 answers 0 for events."""
        target = self._event_ref(ref)
        if target in VEHICLE_JS:
            return f"{VEHICLE_JS[target]}._mapId"
        if target >= 0 and not self.rm2k3:
            return "0"
        return "$gameMap.mapId()"

    def _character_js(self, ref: int) -> str:
        target = self._event_ref(ref)
        if target in VEHICLE_JS:
            return VEHICLE_JS[target]
        if target < 0:
            return "$gamePlayer"
        if target == 0:
            return "$gameMap.event(this._eventId)"
        return f"$gameMap.event({target})"

    def _variables(self, params, emit, where) -> None:
        """RM2k: [0 one / 1 a range / 2 the variable a variable names, first,
        last, operation, operand type, a, b].  The arithmetic itself (RPG_RT
        division, the value limits) is RM2kCompat.js's operateVariable."""
        mode, start, end, op, operand_type = (params + [0] * 5)[:5]
        a = params[5] if len(params) > 5 else 0
        b = params[6] if len(params) > 6 else 0
        if mode == 0:
            end = start
        if op > 5:
            # 6..10 are the Maniac Patch's bit operations.
            self._unsupported[CONTROL_VARS] += 1
            emit(MV_COMMENT, [f"[MakerBridge] Maniac Patch variable operation {op} "
                              f"(params={params})"])
            return
        if mode == 2:
            # The target is the variable whose id sits in variable `start`.
            # MV has no indirect form, so the whole operation goes to script.
            emit(MV_SCRIPT, [f"this.rm2kSetVarIndirect({start}, {op}, "
                             f"{self._operand_js(operand_type, a, b)});"])
            return
        if start != end and (operand_type in (2, 3)
                             or (operand_type == 1 and start <= a <= end)):
            # RPG_RT reads these again for every variable of a range: each
            # gets its own random number, and a source inside the range is
            # read after it changed.  MV works the value out once.
            emit(MV_SCRIPT, [f"for (var i = {start}; i <= {end}; i++) {{ "
                             f"this.operateVariable(i, {op}, "
                             f"{self._operand_js(operand_type, a, b)}); }}"])
            return

        def script(js: str) -> None:
            emit(MV_VARIABLES, [start, end, op, 4, js])

        if operand_type == 0:                       # constant
            emit(MV_VARIABLES, [start, end, op, 0, a])
        elif operand_type == 1:                     # another variable
            emit(MV_VARIABLES, [start, end, op, 1, a])
        elif operand_type == 2:                     # the variable a variable names
            script(f"$gameVariables.value($gameVariables.value({a}))")
        elif operand_type == 3:                     # random in range
            # RPG_RT accepts the bounds either way round; MV does not.
            emit(MV_VARIABLES, [start, end, op, 2, min(a, b), max(a, b)])
        elif operand_type == 4:                     # an item: held / worn
            mapped = self.ids.items.get(a)
            if not mapped:
                self._unsupported[CONTROL_VARS] += 1
                emit(MV_COMMENT, [f"[MakerBridge] unknown item {a} in variable op"])
                return
            if b == 1:
                script(self._equipped_count_js(mapped))
                return
            kind, new_id = mapped
            data_type = {"item": 0, "weapon": 1, "armor": 2}[kind]
            emit(MV_VARIABLES, [start, end, op, 3, data_type, new_id, 0])
        elif operand_type == 5:                     # actor property
            actor = self.ids.actors.get(a, a)
            if b in _ACTOR_STAT:
                emit(MV_VARIABLES, [start, end, op, 3, 3, actor, _ACTOR_STAT[b]])
            elif b in _ACTOR_EQUIP_SLOT:
                # The RM2k id of what is worn in a slot.
                script(self._operand_js(5, a, b))
            else:
                self._unsupported[CONTROL_VARS] += 1
                emit(MV_COMMENT, [f"[MakerBridge] actor property {b} in variable op "
                                  f"(params={params})"])
        elif operand_type == 6:                     # character position / facing
            prop = _CHARACTER_PROP.get(b)
            if b == 0:                              # the map it is on
                script(self._map_id_js(a))
            elif b in (4, 5):
                # Pictures placed from these are scaled by RM2kCompat.js, so
                # the value has to stay in RM2k's 320x240 screen units.
                script(self._operand_js(6, a, b))
            elif prop is not None:
                emit(MV_VARIABLES, [start, end, op, 3, 5, self._event_ref(a), prop])
            else:
                self._unsupported[CONTROL_VARS] += 1
                emit(MV_COMMENT, [f"[MakerBridge] character property {b} in variable op "
                                  f"(params={params})"])
        elif operand_type == 7:                     # misc game data
            # Chosen by the first value (EasyRPG ControlVariables::Other(p[5])).
            other = _OTHER_DATA.get(a)
            if other is not None:
                emit(MV_VARIABLES, [start, end, op, 3, 7, other, 0])
            elif a in _OTHER_JS:
                script(_OTHER_JS[a])
            else:
                self._unsupported[CONTROL_VARS] += 1
                emit(MV_COMMENT, [f"[MakerBridge] game data {a} in variable op "
                                  f"(params={params})"])
        elif operand_type == 8 and b in _ENEMY_FIELD:   # RM2003: an enemy
            script(self._operand_js(8, a, b))
        else:
            self._unsupported[CONTROL_VARS] += 1
            emit(MV_COMMENT, [f"[MakerBridge] variable operand type {operand_type} "
                              f"not translated (params={params})"])

    def _items(self, params, emit) -> None:
        op, id_type, item_id, amount_type, amount = (params + [0] * 5)[:5]
        if id_type:
            # The item id is in a variable; RM2kCompat.js knows the split
            # into items, weapons and armour.
            count = f"$gameVariables.value({amount})" if amount_type else str(amount)
            emit(MV_SCRIPT, [f"this.rm2kGainRm2kItem($gameVariables.value({item_id}), "
                             f"{'-' if op else ''}{count});"])
            return
        mapped = self.ids.items.get(item_id)
        if mapped is None:
            self._unsupported[CHANGE_ITEMS] += 1
            emit(MV_COMMENT, [f"[MakerBridge] unknown RM2k item {item_id}"])
            return
        kind, new_id = mapped
        code = {"item": MV_ITEMS, "weapon": MV_WEAPONS, "armor": MV_ARMORS}[kind]
        args = [new_id, op, amount_type, amount]
        if kind != "item":
            args.append(False)          # MV: "include equipment"
        emit(code, args)

    def _equipment(self, params, emit) -> None:
        """RM2k: [actor mode, actor, 0 equip / 1 remove, ...]
        equip:  [..., 0 literal / 1 variable, item]
        remove: [..., slot 0 weapon, 1 shield, 2 armour, 3 helmet,
                 4 accessory, 5 everything].
        MV's own command needs one fixed actor and an item the party owns,
        so RM2kCompat.js does it - and finds the right slot by the item's
        equipment type, which the converter cannot see here."""
        actors = self._actors_js(params)
        operation = params[2] if len(params) > 2 else 0
        if operation == 0:
            by_variable = len(params) > 3 and params[3]
            item_id = params[4] if len(params) > 4 else 0
            if by_variable:
                emit(MV_SCRIPT, [f"this.rm2kEquipRm2kItem({actors}, $gameVariables.value({item_id}));"])
                return
            mapped = self.ids.items.get(item_id)
            if not mapped or mapped[0] == "item":
                self._unsupported[CHANGE_EQUIPMENT] += 1
                emit(MV_COMMENT, [f"[MakerBridge] cannot equip RM2k item {item_id}"])
                return
            emit(MV_SCRIPT, [f"this.rm2kEquip({actors}, \"{mapped[0]}\", {mapped[1]});"])
        else:
            slot = params[3] if len(params) > 3 else 0
            emit(MV_SCRIPT, [f"this.rm2kUnequip({actors}, {slot});"])

    def _call_event(self, params, emit) -> None:
        """RM2k: 0 = common event, 1 = a page of a map event, 2 = both by variable."""
        mode = params[0] if params else 0
        a = params[1] if len(params) > 1 else 0
        b = params[2] if len(params) > 2 else 0
        if mode == 0:
            emit(MV_COMMON_EVENT, [self.ids.common_events.get(a, a)])
        elif mode == 1:
            emit(MV_SCRIPT,
                 [f"this.rm2kCallEventPage({self._event_ref(a)}, {b});"])
        elif mode == 2:
            emit(MV_SCRIPT,
                 [f"this.rm2kCallEventPage($gameVariables.value({a}), "
                  f"$gameVariables.value({b}));"])
        else:
            self._unsupported[CALL_EVENT] += 1
            emit(MV_COMMENT, [f"[MakerBridge] call event mode {mode} "
                              f"(params={params}) needs manual porting"])

    def _battle(self, text, params, emit, out, indent) -> None:
        """RM2k: [mode, troop, background mode, escape, defeat, terminate].

        The string is the battle background; MV has no slot for it on the
        command, so the map's backdrop is switched just before the fight.
        """
        # Escape: 0 not allowed, 1 allowed and it ends the event, 2 allowed
        # with its own branch.  Defeat: 0 game over, 1 its own branch.
        by_variable = 1 if (params and params[0] == 1) else 0
        troop = params[1] if len(params) > 1 else 1
        if not by_variable:
            troop = self.ids.troops.get(troop, troop)
        escape = params[3] if len(params) > 3 else 0
        can_lose = bool(params[4]) if len(params) > 4 else False
        background = params[2] if len(params) > 2 else 0
        # For this one battle only, as in RM2k; MV's own command would keep
        # the backdrop for every later encounter on the map too.
        backdrop = _js_string(text) if background == 1 and text else "null"
        # Background mode 2 takes the backdrop of a terrain (parameter 8).
        terrain = params[8] if background == 2 and len(params) > 8 else 0
        # "First strike" (parameter 5): the party acts first, MV's preemptive.
        first = "true" if len(params) > 5 and params[5] else "false"
        condition = params[6] if len(params) > 6 and self.rm2k3 else 0
        emit(MV_SCRIPT, [f"$gameTemp.rm2kBattleback = {backdrop}; "
                         f"$gameTemp.rm2kBattleTerrain = {terrain}; "
                         f"$gameTemp.rm2kFirstStrike = {first}; "
                         # RM2003 condition: 1 initiative, 2 back attack,
                         # 3 surround, 4 pincers.
                         f"$gameTemp.rm2kBattleCondition = {condition};"])
        emit(MV_BATTLE, [by_variable, troop, escape != 0, can_lose])
        if escape == 1 and not can_lose:
            # RM2k writes no branches here, but fleeing ends the event.
            for code, depth in ((MV_BATTLE_WIN, 0), (0, 1), (MV_BATTLE_ESCAPE, 0),
                                (MV_EXIT_EVENT, 1), (0, 1), (MV_BATTLE_END, 0)):
                out.append({"code": code, "indent": indent + depth, "parameters": []})
        elif escape == 1:
            # Fleeing ends the event here too (EasyRPG abort_on_escape), but
            # RM2k's own victory and defeat branches follow: the escape
            # branch goes in when the defeat one is reached.
            self._escape_exits.add(indent)

    def _system_bgm(self, text, params, emit) -> None:
        """RM2k can swap the battle or victory theme at runtime."""
        slot = params[0] if params else 0
        track = _audio(text, list(params[1:]), bgm=True)
        if slot in SYSTEM_BGM_AS_ME and track["name"]:
            # Played with AudioManager.playMe, which looks in audio/me.
            self.me_music.add(track["name"])
        setter = SYSTEM_BGM_SETTER.get(slot)
        if setter is not None:
            emit(MV_SCRIPT, [f"$gameSystem.{setter}("
                             f"{json.dumps(track, ensure_ascii=False)});"])
        elif slot in SYSTEM_BGM_VEHICLE:
            emit(MV_CHANGE_VEHICLE_BGM, [SYSTEM_BGM_VEHICLE[slot], track])
        elif slot in (SYSTEM_BGM_INN, SYSTEM_BGM_GAMEOVER):
            # MV has no setter for these; RM2kCompat.js keeps them in the
            # save and the inn and game over screens play them.
            kind = "inn" if slot == SYSTEM_BGM_INN else "gameover"
            emit(MV_SCRIPT, [f"$gameSystem.rm2kSetMusic(\"{kind}\", "
                             f"{json.dumps(track, ensure_ascii=False)});"])
        else:
            self._unsupported[CHANGE_SYSTEM_BGM] += 1
            emit(MV_COMMENT, [f"[MakerBridge] system music slot {slot} "
                              f"({text!r}) has no MV counterpart"])

    def _exp_or_level(self, code, params, emit) -> None:
        """RM2k: [0 party / 1 actor / 2 actor in variable, actor, 0 add /
        1 subtract, 0 literal / 1 variable, amount, show level-up message].
        MV takes the same values with the target split into type and id."""
        mode = params[0] if params else 0
        actor = params[1] if len(params) > 1 else 0
        if mode == 0:
            target = [0, 0]                      # MV: fixed id 0 = whole party
        elif mode == 1:
            target = [0, self.ids.actors.get(actor, actor)]
        else:
            target = [1, actor]
        rest = (list(params[2:6]) + [0, 0, 0, 0])[:4]
        rest[3] = bool(rest[3])
        emit(MV_CHANGE_EXP if code == CHANGE_EXP else MV_CHANGE_LEVEL, target + rest)

    def _shop(self, params, emit) -> None:
        """RM2k: [0 buy+sell / 1 buy only / 2 sell only, message style,
        custom branches, unused, item ids...]."""
        kind = params[0] if params else 0
        goods = []
        for rm_id in params[4:]:
            mapped = self.ids.items.get(rm_id)
            if mapped:
                table = {"item": 0, "weapon": 1, "armor": 2}[mapped[0]]
                goods.append([table, mapped[1], 0, 0])
        emit(MV_SCRIPT, [f"$gameTemp._rm2kShopDealt = false; "
                         f"$gameTemp._rm2kShopSellOnly = {'true' if kind == 2 else 'false'};"])
        # MV needs a first entry even in a shop that only buys from the hero;
        # id 0 is skipped when the list is drawn.
        first = goods[0] if goods else [0, 0, 0, 0]
        emit(MV_SHOP, first + [kind == 1])
        for entry in goods[1:]:
            emit(MV_SHOP_ITEM, entry)

    def _inn(self, params, out, indent) -> None:
        """RM2k: [message style, price, custom branches].

        MV has no inn, so it is built from what it does have: the greeting
        from the database terms, a yes/no choice, paying, a fade with the
        inn music while the party is healed, and a flag for the branches.
        A free inn asks nothing and the party stays at once (EasyRPG
        CommandShowInn).
        """
        style = 1 if params and params[0] else 0
        price = params[1] if len(params) > 1 else 0
        before, after, question, yes, no = (self.terms.get(k) or ""
                                            for k in INN_TERMS[style])
        currency = self.terms.get(CURRENCY_TERM) or ""
        stayed = "$gameTemp._rm2kInnStayed = true;"
        refused = "$gameTemp._rm2kInnStayed = false;"

        def add(code, depth, parameters=()):
            out.append({"code": code, "indent": indent + depth,
                        "parameters": list(parameters)})

        def stay(depth):
            if price:
                add(MV_GOLD, depth, [1, 0, price])
            add(MV_FADEOUT, depth)
            add(MV_SCRIPT, depth, ["this.rm2kPlayInnMusic();"])
            add(MV_RECOVER, depth, [0, 0])
            add(MV_WAIT, depth, [60])
            add(MV_FADEIN, depth)
            add(MV_SCRIPT, depth, [stayed])

        if price <= 0:
            stay(0)
            return
        if self.rm2k_english:
            # RM2000 1.6x: %V is the price, %U the currency, in the first
            # and the third greeting.
            def fill(term):
                return term.replace("%V", str(price)).replace("%U", currency)
            lines = [fill(before), fill(question)]
        else:
            lines = [f"{before} {price}{currency} {after}", question]
        add(MV_SCRIPT, 0, [refused])
        add(MV_TEXT, 0, ["", 0, 0, 2, ""])
        for line in lines:
            if line:
                add(MV_TEXT_LINE, 0, [line])
        add(MV_CHOICES, 0, [[yes or "Ja", no or "Nein"], 1, 0, 2, 0])
        add(MV_WHEN, 0, [0, yes or "Ja"])
        add(MV_IF, 1, [7, price, 0])                 # gold >= price
        stay(2)
        add(0, 2)
        add(MV_END_IF, 1)
        add(0, 1)
        add(MV_WHEN, 0, [1, no or "Nein"])
        add(0, 1)
        add(MV_CHOICES_END, 0)

    def _actor_target(self, params) -> list:
        """RM2k [mode, id]: 0 whole party, 1 this actor, 2 the actor whose id
        is in variable `id`.  MV: [0 fixed / 1 variable, id], fixed 0 = party."""
        mode = params[0] if params else 0
        value = params[1] if len(params) > 1 else 1
        if mode == 0:
            return [0, 0]
        if mode == 2:
            return [1, value]
        return [0, self.ids.actors.get(value, value)]

    def _actors_js(self, params) -> str:
        """The same target as a JavaScript array of Game_Actors."""
        kind, value = self._actor_target(params)
        if kind == 1:
            return f"[$gameActors.actor($gameVariables.value({value}))]"
        if value == 0:
            return "$gameParty.members()"
        return f"[$gameActors.actor({value})]"

    def _change_skills(self, params, emit) -> None:
        """RM2k: [actor mode, actor, 0 learn / 1 forget, 0 literal /
        1 variable, skill]."""
        operation = params[2] if len(params) > 2 else 0
        skill = params[4] if len(params) > 4 else 0
        if len(params) > 3 and params[3]:
            # MV takes no skill from a variable; the skill ids are shifted
            # by the reserved ones, which RM2kCompat.js knows.
            verb = "forgetSkill" if operation else "learnSkill"
            emit(MV_SCRIPT, [f"{self._actors_js(params)}.forEach(function(a) {{ if (a) "
                             f"a.{verb}($gameVariables.value({skill}) + RM2K_SKILL_OFFSET); }});"])
            return
        emit(MV_CHANGE_SKILL, self._actor_target(params) + [
            0 if operation == 0 else 1, self.ids.skills.get(skill, skill)])

    def _change_parameters(self, params, emit) -> None:
        """RM2k: [actor mode, actor, 0 raise / 1 lower, stat, 0 literal /
        1 variable, amount]."""
        operation = params[2] if len(params) > 2 else 0
        stat = params[3] if len(params) > 3 else 0
        value_mode = params[4] if len(params) > 4 else 0
        value = params[5] if len(params) > 5 else 0
        target = self._actor_target(params)
        for param in ((4, 5) if stat == 4 else (PARAM_MAP.get(stat, 0),)):
            # RM2k's spirit stands for both of MV's magic stats.
            emit(MV_CHANGE_PARAMETER, target + [param, 0 if operation == 0 else 1,
                                                1 if value_mode else 0, value])

    def _monster_points(self, params, emit, hp: bool) -> None:
        """RM2003: [enemy, 0 gain / 1 lose, 0 literal / 1 variable /
        2 percent (HP only), amount, may kill]."""
        enemy, op, kind, value = (list(params) + [0, 0, 0, 0])[:4]
        if kind == 2 and hp:
            # A share of the *current* HP (EasyRPG CommandChangeMonsterHP);
            # Game_Interpreter.changeHp keeps 1 HP unless it may kill and
            # lets a beaten enemy collapse.
            sign = "-" if op else ""
            lethal = "true" if len(params) > 4 and params[4] else "false"
            emit(MV_SCRIPT, [f"var e = $gameTroop.members()[{enemy}]; if (e && e.isAlive()) "
                             f"{{ this.changeHp(e, {sign}Math.floor(e.hp * {value} / 100), "
                             f"{lethal}); }}"])
            return
        kind = min(kind, 1)
        args = [enemy, op, 1 if kind else 0, value]
        if hp:
            args.append(bool(params[4]) if len(params) > 4 else False)
        emit(MV_ENEMY_HP if hp else MV_ENEMY_MP, args)

    def _travel_target(self, code, params, emit) -> None:
        """Where the teleport and escape skills lead.
        Teleport: [0 add / 1 remove, map, x, y, switch on, switch];
        escape:   [map, x, y, switch on, switch]  (EasyRPG)."""
        values = (list(params) + [0] * 6)[:6]
        if code == TELEPORT_TARGETS:
            remove, rm_map, x, y, switch_on, switch = values
            map_id = self.ids.maps.get(rm_map, rm_map)
            emit(MV_SCRIPT, [f"$gameSystem.rm2kTeleportTarget({map_id}, {x}, {y}, "
                             f"{switch if switch_on else 0}, "
                             f"{'false' if remove else 'true'});"])
        else:
            map_id = self.ids.maps.get(values[0], values[0])
            switch = values[4] if values[3] else 0
            emit(MV_SCRIPT, [f"$gameSystem.rm2kEscapeTarget({map_id}, {values[1]}, "
                             f"{values[2]}, {switch});"])

    def _timer(self, params, emit) -> None:
        """RM2k: [0 set / 1 start / 2 stop, set: 0 literal / 1 variable,
        seconds, start: visible, runs in battle, (RM2003) timer 0 / 1].

        As in RPG_RT (EasyRPG Game_Party::SetTimer / StartTimer): setting
        changes the time at once, running or not; starting resumes from
        whatever is left; stopping keeps it.  MV's own timer command can
        only start afresh, so RM2kCompat.js does all three - and keeps the
        second RM2003 timer, which MV lacks.
        """
        values = (list(params) + [0] * 6)[:6]
        operation, by_variable, value, visible, battle, which = values
        seconds = f"$gameVariables.value({value})" if by_variable else str(value)
        if operation != 0:
            seconds = "0"
        flags = f"{'true' if visible else 'false'}, {'true' if battle else 'false'}"
        target = ("$gameSystem.rm2kTimer2Op" if self.rm2k3 and which == 1
                  else "$gameTimer.rm2kTimerOp")
        emit(MV_SCRIPT, [f"{target}({operation}, {seconds}, {flags});"])

    def _store_at_position(self, params, emit, call: str) -> None:
        """RM2k: [mode, x, y, result]; mode 1 reads x and y from variables."""
        mode = params[0] if params else 0
        x = params[1] if len(params) > 1 else 0
        y = params[2] if len(params) > 2 else 0
        result = params[3] if len(params) > 3 else 1
        xs = f"$gameVariables.value({x})" if mode else str(x)
        ys = f"$gameVariables.value({y})" if mode else str(y)
        emit(MV_SCRIPT,
             [f"$gameVariables.setValue({result}, {call}({xs}, {ys}));"])

    def _picture_id(self, pic_id: int, from_variable: bool) -> None:
        if from_variable:
            self.picture_ids_from_variables = True
        else:
            self.max_picture_id = max(self.max_picture_id, pic_id)

    def _show_picture(self, text, params, emit) -> None:
        # RM2k parameter 1 says whether x and y are literal pixels or the ids
        # of variables holding them; 86% of the calls in a real project use
        # variables, so reading them as coordinates puts pictures anywhere.
        # Coordinates stay in RM2k's 320x240 space here - RM2kCompat.js scales
        # them at runtime, which is the only way to also catch the ones a
        # variable supplies.
        #
        # Everything MV's own command has no field for - colour, effect,
        # "fixed to map", RM2003's bottom transparency and the 1.10+ options
        # - rides along as an eleventh parameter that RM2kCompat.js reads
        # (MV ignores it).
        def get(index, default=0):
            return params[index] if len(params) > index else default

        pic_id = get(0, 1)
        from_variable = 1 if get(1) else 0
        x, y = get(2), get(3)
        zoom = _clamp(get(5, 100), 0, 2000)
        top = _clamp(get(6), 0, 100)
        name = text
        if len(params) > 7 and not params[7] and text:
            # "Use transparent colour" off: palette index 0 stays visible.
            self.opaque_pictures.add(text)
            name = text + OPAQUE_SUFFIX
        ext: dict = {}
        if get(4):
            ext["fixed"] = True               # scrolls with the map
        effects = _picture_effects(params)
        if effects:
            tint, effect, power = effects
            if tint != [100, 100, 100, 100]:
                ext["tint"] = tint
            if effect:
                ext["fx"] = [effect, power]
        if self.bottom_transparency:
            # RM2003 before 1.10: the lower half has its own transparency.
            ext["bottom"] = _opacity(_clamp(get(14), 0, 100) if len(params) > 14 else top)
        id_from_variable = False
        if self.picture_extensions and len(params) > 16:
            id_from_variable = get(17) == 1
            if id_from_variable:
                ext["idVar"] = True
            if get(19):
                # The last <digits> characters of the name are replaced by a
                # variable's value, zero padded.
                ext["nameVar"] = [get(19), get(18)]
                if name.endswith(OPAQUE_SUFFIX):
                    self.opaque_patterns.add((text[:max(0, len(text) - get(18))], get(18)))
            if get(20) == 1:
                ext["zoomVar"] = get(5)
            if get(21) == 1:
                ext["opacityVar"] = get(6)
            cols = get(22)
            if cols > 0:
                rows = max(1, get(23))
                if get(24) == 2:          # animate
                    ext["sheet"] = [cols, rows, 0, max(0, get(25)), bool(get(26))]
                elif get(24) == 1:        # frame from a variable
                    ext["sheet"] = [cols, rows, 0, 0, False]
                    ext["frameVar"] = get(25)
                else:
                    ext["sheet"] = [cols, rows, get(25) - 1, 0, False]
            ext["layer"] = [get(27), get(28)]
            ext["flags"] = get(29)
        self._picture_id(pic_id, id_from_variable)
        emit(MV_SHOW_PICTURE,
             [pic_id, name, 1, from_variable, x, y, zoom, zoom, _opacity(top), 0, ext])

    def _move_picture(self, params, emit) -> None:
        # MV reads twelve parameters here (rpg_objects.js, command232):
        # id, unused, origin, x/y type, x, y, scaleX, scaleY, opacity,
        # blend mode, duration, wait.  Eleven shifts every later value by one.
        # MZ adds the easing as the thirteenth; the RM2k extras follow it.
        def get(index, default=0):
            return params[index] if len(params) > index else default

        pic_id = get(0, 1)
        from_variable = 1 if get(1) else 0
        x, y = get(2), get(3)
        zoom = _clamp(get(5, 100), 0, 2000)
        top = _clamp(get(6), 0, 100)
        duration = max(1, get(14, 1) * WAIT_FRAMES)
        wait = bool(get(15))
        ext: dict = {}
        effects = _picture_effects(params)
        if effects:
            tint, effect, power = effects
            ext["tint"] = tint
            ext["fx"] = [effect, power]
        if self.bottom_transparency:
            ext["bottom"] = _opacity(_clamp(get(16), 0, 100) if len(params) > 16 else top)
        id_from_variable = False
        if self.picture_extensions and len(params) > 17:
            id_from_variable = get(17) == 1
            if id_from_variable:
                ext["idVar"] = True
            if get(20) == 1:
                ext["zoomVar"] = get(5)
            if get(21) == 1:
                ext["opacityVar"] = get(6)
        self._picture_id(pic_id, id_from_variable)
        emit(MV_MOVE_PICTURE,
             [pic_id, 0, 1, from_variable, x, y, zoom, zoom, _opacity(top), 0,
              duration, wait, 0, ext])

    def _erase_picture(self, params, emit) -> None:
        pic_id = params[0] if params else 1
        kind = params[1] if self.picture_extensions and len(params) > 1 else 0
        if kind == 0:
            self._picture_id(pic_id, False)
            emit(MV_ERASE_PICTURE, [pic_id])
        elif kind == 1:                   # the id is in a variable
            self._picture_id(pic_id, True)
            emit(MV_ERASE_PICTURE, [pic_id, {"idVar": True}])
        elif kind == 2:                   # a range of ids
            last = params[2] if len(params) > 2 else pic_id
            self._picture_id(max(pic_id, last), False)
            emit(MV_ERASE_PICTURE, [pic_id, {"to": last}])
        else:
            # 3-5 are Maniac Patch forms; plain RPG_RT does nothing.
            self._unsupported[ERASE_PICTURE] += 1
            emit(MV_COMMENT, [f"[MakerBridge] Maniac Patch erase picture {params}"])

    def _move_event(self, params, emit) -> None:
        from ..lcf.model import decode_move_values

        if not params:
            return
        target = self._event_ref(params[0])
        repeat = bool(params[2]) if len(params) > 2 else False
        skippable = bool(params[3]) if len(params) > 3 else False
        try:
            commands = decode_move_values(params[4:])
        except IndexError:
            self._unsupported[MOVE_EVENT] += 1
            emit(MV_COMMENT, [f"[MakerBridge] unreadable inline move route {params}"])
            return
        frequency = params[1] if len(params) > 1 else 8
        emit(MV_SET_MOVE_ROUTE,
             [target, {"list": self.move_steps(commands, frequency), "repeat": repeat,
                       "skippable": skippable, "wait": False}])

    def move_steps(self, commands: list[dict], frequency: int = 8) -> list[dict]:
        """RM2k move-route opcodes -> MV move-route steps."""
        steps: list[dict] = []
        jump: list[int] | None = None       # opcodes between begin and end jump
        for command in commands:
            code = command["code"]
            text = command.get("string", "")
            args = command.get("parameters", [])
            if code == 24:                            # begin jump
                jump = []
            elif code == 25:                          # end jump
                steps.extend(_jump_steps(jump or []))
                jump = None
            elif jump is not None:
                jump.append(code)
            elif code == 23:                          # wait
                # 20 frames plus the pause RM2k puts between steps at this
                # move frequency (none at the highest, 8).
                pause = 0 if frequency >= 8 else 1 << (9 - max(1, frequency))
                steps.append({"code": 15, "parameters": [20 + pause]})
            elif code in (32, 33):                      # switch on / off
                steps.append({"code": 27 if code == 32 else 28,
                              "parameters": [args[0] if args else 1]})
            elif code == 34:                          # change graphic
                steps.append({"code": 41,
                              "parameters": [text, args[0] if args else 0]})
            elif code == 35:                          # play sound effect
                steps.append({"code": 44, "parameters": [_audio(text, args, False)]})
            elif code in (28, 29):                    # speed up / down
                delta = "+ 1" if code == 28 else "- 1"
                steps.append({"code": 45, "parameters": [
                    f"this.setMoveSpeed(Math.max(1, Math.min(6, "
                    f"this._moveSpeed {delta})));"]})
            elif code in (30, 31):                    # frequency up / down
                delta = "+ 1" if code == 30 else "- 1"
                steps.append({"code": 45, "parameters": [
                    f"this.setMoveFrequency(Math.max(1, Math.min(5, "
                    f"this._moveFrequency {delta})));"]})
            elif code in (40, 41):                    # transparency up / down
                delta = "- 45" if code == 40 else "+ 45"
                steps.append({"code": 45, "parameters": [
                    f"this.setOpacity(Math.max(0, Math.min(255, "
                    f"this.opacity() {delta})));"]})
            else:
                mv_code = MOVE_MAP.get(code)
                if mv_code is None:
                    self._unsupported[MOVE_EVENT] += 1
                    steps.append({"code": 45, "parameters":
                                  [f"/* MakerBridge: move opcode {code} */"]})
                else:
                    steps.append({"code": mv_code, "parameters": []})
        if jump is not None:                          # route ended mid-jump
            steps.extend(_jump_steps(jump))
        steps.append({"code": 0, "parameters": []})
        return steps

    def _conditional(self, params, emit, where, text: str = "") -> None:
        kind = params[0] if params else 0
        a = params[1] if len(params) > 1 else 0
        b = params[2] if len(params) > 2 else 0
        c = params[3] if len(params) > 3 else 0
        d = params[4] if len(params) > 4 else 0
        if kind == 0:                       # switch
            emit(MV_IF, [0, a, 0 if b == 0 else 1])
        elif kind == 1:                     # variable
            emit(MV_IF, [1, a, 0 if b == 0 else 1, c, d])
        elif kind == 2:                     # timer
            # RM2k: 0 at least, 1 at most.  RPG_RT compares the time left
            # even when the timer is stopped; MV's own test is false then.
            emit(MV_IF, [12, f"$gameTimer.seconds() {'<=' if b else '>='} {a}"])
        elif kind == 3:                     # gold
            emit(MV_IF, [7, a, 0 if b == 0 else 1])
        elif kind == 4:                     # item held
            mapped = self.ids.items.get(a)
            if not mapped:
                self._fallback_condition(params, emit)
            elif b:                         # RM2k 1 = "does not have"
                table = {"item": "$dataItems", "weapon": "$dataWeapons",
                         "armor": "$dataArmors"}[mapped[0]]
                emit(MV_IF, [12, f"!$gameParty.hasItem({table}[{mapped[1]}], true)"])
            elif mapped[0] == "item":
                emit(MV_IF, [8, mapped[1]])
            else:
                emit(MV_IF, [9 if mapped[0] == "weapon" else 10, mapped[1], True])
        elif kind == 5:                     # actor property
            self._actor_condition(a, b, c, emit, params, text)
        elif kind == 6:                     # character facing a direction
            emit(MV_IF, [6, self._event_ref(a), _FACING.get(b, 2)])
        elif kind == 7 and 0 <= a <= 2:     # riding a vehicle
            # RM2k and MV both number them 0 boat, 1 ship, 2 airship.
            emit(MV_IF, [13, a])
        elif kind == 8:                     # started with the decision key
            emit(MV_IF, [12, "this.rm2kStartedByKey()"])
        elif kind == 9:                     # music has played through once
            emit(MV_IF, [12, "AudioManager.rm2kBgmLooped()"])
        elif kind == 10:                    # RM2003 second timer
            emit(MV_IF, [12, f"$gameSystem.rm2kTimer2() {'<=' if b else '>='} {a}"])
        elif kind == 11:                    # RM2003: 0 saved, 1 test play,
            emit(MV_IF, [12, {0: "DataManager.isAnySavefileExists()",  # 2 ATB wait,
                              1: "$gameTemp.isPlaytest()",         # 3 fullscreen
                              2: "!!$gameSystem._rm2kAtbWait",
                              3: "Graphics._isFullScreen()"}.get(a, "false")])
        else:
            self._fallback_condition(params, emit)

    def _actor_condition(self, actor_id, subtype, value, emit, params, text="") -> None:
        """RM2k: 0 in party, 1 name, 2 level, 3 HP, 4 skill, 5 equipment, 6 state."""
        actor = self.ids.actors.get(actor_id, actor_id)
        if subtype == 0:
            emit(MV_IF, [4, actor, 0])
        elif subtype == 4:
            emit(MV_IF, [4, actor, 3, self.ids.skills.get(value, value)])
        elif subtype == 5:
            mapped = self.ids.items.get(value)
            if mapped and mapped[0] in ("weapon", "armor"):
                emit(MV_IF, [4, actor, 4 if mapped[0] == "weapon" else 5, mapped[1]])
            else:
                self._fallback_condition(params, emit)
        elif subtype == 6:
            emit(MV_IF, [4, actor, 6, self.ids.states.get(value, value)])
        elif subtype == 2:
            emit(MV_IF, [12, f"$gameActors.actor({actor}).level >= {value}"])
        elif subtype == 3:
            emit(MV_IF, [12, f"$gameActors.actor({actor}).hp >= {value}"])
        elif subtype == 1:                  # name is the command's text
            emit(MV_IF, [4, actor, 1, text])
        else:
            self._fallback_condition(params, emit)

    def _battle_conditional(self, params, emit) -> None:
        """RM2003 battle branch: 0 switch and 1 variable as on maps, then
        2 hero can act, 3 enemy can act, 4 enemy is targeted, 5 hero uses
        a command."""
        kind = params[0] if params else 0
        a = params[1] if len(params) > 1 else 0
        if kind in (0, 1):
            self._conditional(params, emit, "")
        elif kind == 2:
            actor = self.ids.actors.get(a, a)
            emit(MV_IF, [12, f"$gameActors.actor({actor}).canMove()"])
        elif kind == 3:
            emit(MV_IF, [12, f"!!$gameTroop.members()[{a}] && "
                             f"$gameTroop.members()[{a}].canMove()"])
        elif kind == 4:
            emit(MV_IF, [12, f"$gameTemp.rm2kIsTargeted($gameTroop.members()[{a}])"])
        elif kind == 5:
            actor = self.ids.actors.get(a, a)
            command = params[2] if len(params) > 2 else 0
            emit(MV_IF, [12, f"$gameTemp.rm2kUsesCommand({actor}, {command})"])
        else:
            self._fallback_condition(params, emit)

    def _fallback_condition(self, params, emit) -> None:
        self._unsupported[CONDITIONAL] += 1
        emit(MV_IF, [12, "true /* MakerBridge: condition "
                         f"{params} not translated */"])


def _js_string(text: str) -> str:
    """Quote a value for embedding in a generated script command."""
    return json.dumps(text, ensure_ascii=False)


def _key_input_layout(params: list, rm2k3: bool) -> tuple[dict, int]:
    """Key Input Processing's keys, laid out by engine and version as RPG_RT
    reads them (EasyRPG CommandKeyInputProc), and the variable that gets the
    waiting time in tenths of a second (0 for none).

    Always: [variable, wait, all arrows (old versions), decision, cancel].
    RM2000 1.50+ (6+ values): shift 5, down 6, left 7, right 8, up 9.
    RM2003 with exactly 10 values (an RM2000 1.50 project) reads the same.
    Other RM2003: numbers 5, operators 6, time variable 7, store time 8,
    and from 1.05 (more than 10 values) shift 9, down 10, left 11,
    right 12, up 13 instead of the all-arrows flag.
    """
    def flag(i: int) -> bool:
        return len(params) > i and bool(params[i])

    keys = {"down": False, "left": False, "right": False, "up": False,
            "ok": flag(3), "cancel": flag(4), "shift": False,
            "numbers": False, "operators": False}
    time_variable = 0
    if not rm2k3 or len(params) == 10:
        if len(params) < 6:
            for name in ("down", "left", "right", "up"):
                keys[name] = flag(2)
        else:
            keys["shift"] = flag(5)
            for name, i in (("down", 6), ("left", 7), ("right", 8), ("up", 9)):
                keys[name] = flag(i)
    else:
        if len(params) <= 10:
            for name in ("down", "left", "right", "up"):
                keys[name] = flag(2)
        else:
            keys["shift"] = flag(9)
            for name, i in (("down", 10), ("left", 11), ("right", 12), ("up", 13)):
                keys[name] = flag(i)
        keys["numbers"] = flag(5)
        keys["operators"] = flag(6)
        if flag(8) and len(params) > 7:
            time_variable = params[7]
    return keys, time_variable


def _choice_count(commands: list[dict], index: int) -> int:
    """How many options the Show Choices at ``index`` has (cancel aside)."""
    cmd = commands[index]
    slots = set()
    for look in range(index + 1, len(commands)):
        other = commands[look]
        if other["indent"] != cmd["indent"]:
            continue
        if other["code"] == CHOICE_END:
            break
        if other["code"] == CHOICE_OPTION:
            slot = other["parameters"][0] if other["parameters"] else len(slots)
            if slot < CANCEL_SLOT:
                slots.add(slot)
    if not slots:
        return len([part for part in cmd["string"].split("/")]) if cmd["string"] else 0
    return max(slots) + 1


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _jump_steps(opcodes: list[int]) -> list[dict]:
    """The moves between RM2k's "begin jump" and "end jump" -> one MV jump.

    RM2k sums the moves into a single leap; MV wants that leap as an offset.
    Turns in between only change the facing, so they go first.  Moves whose
    direction is only known while playing (random, toward the hero, forward)
    are left to RM2kCompat.js.
    """
    dx = dy = 0
    turns = []
    for code in opcodes:
        if code in MOVE_OFFSETS:
            dx += MOVE_OFFSETS[code][0]
            dy += MOVE_OFFSETS[code][1]
        elif code in FACE_OPCODES:
            turns.append({"code": MOVE_MAP[code], "parameters": []})
        else:
            return [{"code": 45, "parameters": [f"this.rm2kJump({json.dumps(opcodes)});"]}]
    return turns + [{"code": 14, "parameters": [dx, dy]}]


def _opacity(transparency: int) -> int:
    """RM2k transparency 0..100 % -> MV opacity 0..255."""
    return 255 - _clamp(transparency * 255 // 100, 0, 255)


def _picture_effects(params) -> tuple[list[int], int, int] | None:
    """RM2k picture colour and effect -> ([red, green, blue, saturation], effect, power).

    Show and Move Picture share the layout from index 8 on: red, green,
    blue, saturation (0..200 around a neutral 100), then the effect
    (0 none, 1 rotation, 2 wave) and its power.  RM2kCompat.js applies them
    the way RPG_RT does.  Returns None for a record whose values are out of
    range, so a damaged one cannot black out or spin a picture.
    """
    if len(params) < 14:
        return None
    r, g, b, sat, effect, power = params[8:14]
    # RM2003 leaves garbage in the power when there is no effect, so it only
    # counts against a record that actually uses one.
    if not (all(0 <= v <= 200 for v in (r, g, b, sat)) and 0 <= effect <= 2
            and (effect == 0 or 0 <= power <= 10)):
        return None
    return [r, g, b, sat], effect, power if effect else 0


def _tone(value: int) -> int:
    """RM2k tint channels run 0..200 around a neutral 100; MV uses -255..255."""
    return _clamp(round((value - 100) * 255 / 100), -255, 255)


def _audio(name: str, params: list[int], bgm: bool) -> dict:
    if name.strip().lower() == "(off)":
        name = ""          # RM2k's sentinel for "no track"
    if bgm:
        volume = params[1] if len(params) > 1 else 100
        tempo = params[2] if len(params) > 2 else 100
        balance = params[3] if len(params) > 3 else 50
    else:
        volume = params[0] if params else 100
        tempo = params[1] if len(params) > 1 else 100
        balance = params[2] if len(params) > 2 else 50
    return {
        "name": name,
        "volume": _clamp(volume, 0, 100),
        "pitch": _clamp(tempo, 50, 150),
        "pan": _clamp(balance * 2 - 100, -100, 100),
    }
