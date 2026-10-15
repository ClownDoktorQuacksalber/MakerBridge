"""Declarative field schemas for the LCF records.

Each schema maps chunk_id -> (field_name, kind).  Kinds:

  int   compressed integer      bool  compressed integer as bool
  str   text (project encoding) i16   int16 little-endian array
  u8    byte array              ber   run of compressed integers
  cmds  event command stream    raw   bytes, kept verbatim

Chunks absent from a record take the RM2k default, which is why records are
sparse: liblcf omits any field equal to its default.  Chunks not listed in a
schema are preserved under "_unknown" so the intermediate dump stays lossless.
"""

from __future__ import annotations

ACTOR = {
    0x01: ("name", "str"),
    0x02: ("title", "str"),
    0x03: ("character_name", "str"),
    0x04: ("character_index", "int"),
    0x05: ("transparent", "bool"),
    0x07: ("initial_level", "int"),
    0x08: ("final_level", "int"),
    0x09: ("critical_hit", "bool"),
    0x0A: ("critical_hit_chance", "int"),
    0x0F: ("face_name", "str"),
    0x10: ("face_index", "int"),
    0x15: ("two_weapon", "bool"),
    0x16: ("lock_equipment", "bool"),
    0x17: ("auto_battle", "bool"),
    0x18: ("super_guard", "bool"),
    0x1F: ("parameters", "i16"),
    0x29: ("exp_base", "int"),
    0x2A: ("exp_inflation", "int"),
    0x2B: ("exp_correction", "int"),
    0x33: ("initial_equipment", "i16"),   # weapon, shield, armour, helmet, accessory
    0x38: ("unarmed_animation", "int"),
    0x39: ("class_id", "int"),            # RM2003
    0x3B: ("battle_x", "int"),            # RM2003 battle position (centre,
    0x3C: ("battle_y", "int"),            # on the 320x240 screen)
    0x3E: ("battler_animation", "int"),   # RM2003
    0x3F: ("skills", "raw"),              # array of LEARNING
    0x42: ("rename_skill", "bool"),
    0x43: ("skill_name", "str"),
    0x48: ("state_ranks", "u8"),
    0x4A: ("attribute_ranks", "u8"),
}

# One "learns this skill at that level" entry of an actor or class.
LEARNING = {
    0x01: ("level", "int"),
    0x02: ("skill_id", "int"),
}

SKILL = {
    0x01: ("name", "str"),
    0x02: ("description", "str"),
    0x03: ("using_message1", "str"),
    0x04: ("using_message2", "str"),
    0x07: ("failure_message", "int"),
    0x08: ("type", "int"),                # 0 normal, 1 teleport, 2 escape, 3 switch, 4+ subset
    0x09: ("sp_type", "int"),             # RM2003: 0 fixed, 1 percent
    0x0A: ("sp_percent", "int"),
    0x0B: ("sp_cost", "int"),
    0x0C: ("scope", "int"),
    0x0D: ("switch_id", "int"),
    0x0E: ("animation_id", "int"),
    0x10: ("sound_effect", "raw"),
    0x12: ("occasion_field", "bool"),
    0x13: ("occasion_battle", "bool"),
    0x14: ("reverse_state_effect", "bool"),
    0x15: ("physical_rate", "int"),
    0x16: ("magical_rate", "int"),
    0x17: ("variance", "int"),
    0x18: ("power", "int"),
    0x19: ("hit", "int"),
    0x1F: ("affect_hp", "bool"),
    0x20: ("affect_sp", "bool"),
    0x21: ("affect_attack", "bool"),
    0x22: ("affect_defense", "bool"),
    0x23: ("affect_spirit", "bool"),
    0x24: ("affect_agility", "bool"),
    0x25: ("absorb_damage", "bool"),
    0x26: ("ignore_defense", "bool"),
    0x2A: ("state_effects", "u8"),
    0x2C: ("attribute_effects", "u8"),
    0x2D: ("affect_attr_defence", "bool"),
    0x32: ("battler_animation_data", "raw"),   # RM2003: per hero, WEAPON_ANIMATION
}

ITEM = {
    0x01: ("name", "str"),
    0x02: ("description", "str"),
    0x03: ("type", "int"),
    0x05: ("price", "int"),
    0x06: ("uses", "int"),
    0x0B: ("atk_points", "int"),
    0x0C: ("def_points", "int"),
    0x0D: ("spi_points", "int"),
    0x0E: ("agi_points", "int"),
    0x0F: ("two_handed", "bool"),
    0x10: ("sp_cost", "int"),
    0x11: ("hit", "int"),
    0x12: ("critical_hit", "int"),
    0x14: ("animation_id", "int"),
    0x15: ("preemptive", "bool"),
    0x16: ("dual_attack", "bool"),
    0x17: ("attack_all", "bool"),
    0x18: ("ignore_evasion", "bool"),
    0x19: ("prevent_critical", "bool"),
    0x1A: ("raise_evasion", "bool"),
    0x1B: ("half_sp_cost", "bool"),
    0x1C: ("no_terrain_damage", "bool"),
    0x1D: ("cursed", "bool"),             # RM2003: cannot be taken off
    0x1F: ("entire_party", "bool"),
    0x20: ("recover_hp_rate", "int"),
    0x21: ("recover_hp", "int"),
    0x22: ("recover_sp_rate", "int"),
    0x23: ("recover_sp", "int"),
    0x25: ("occasion_field1", "bool"),
    0x26: ("ko_only", "bool"),
    0x29: ("max_hp_points", "int"),
    0x2A: ("max_sp_points", "int"),
    0x2B: ("atk_points2", "int"),         # seeds: permanent gains
    0x2C: ("def_points2", "int"),
    0x2D: ("spi_points2", "int"),
    0x2E: ("agi_points2", "int"),
    0x33: ("using_message", "int"),
    0x35: ("skill_id", "int"),
    0x37: ("switch_id", "int"),
    0x39: ("occasion_field2", "bool"),
    0x3A: ("occasion_battle", "bool"),
    0x3E: ("actor_set", "u8"),            # who may equip / use it
    0x40: ("state_set", "u8"),
    0x42: ("attribute_set", "u8"),
    0x43: ("state_chance", "int"),
    0x44: ("reverse_state_effect", "bool"),
    0x46: ("animation_data", "raw"),      # RM2003: per hero, see WEAPON_ANIMATION
    0x47: ("use_skill", "bool"),          # RM2003: equipment casts its skill
    0x49: ("class_set", "u8"),            # RM2003: classes that may equip it
}

# RM2003: how a hero uses a weapon (liblcf BattlerAnimationItemSkill), one
# entry per hero id.
WEAPON_ANIMATION = {
    0x03: ("type", "int"),
    0x04: ("weapon_animation_id", "int"),
    0x05: ("movement", "int"),
    0x06: ("after_image", "int"),
    0x07: ("attacks", "int"),             # extra hits: 0 one, 1 two, 2 three...
    0x08: ("ranged", "bool"),
    0x09: ("ranged_animation_id", "int"),
    0x0C: ("ranged_speed", "int"),
    0x0D: ("battle_animation_id", "int"),
    0x0E: ("pose", "int"),
}

ENEMY = {
    0x01: ("name", "str"),
    0x02: ("battler_name", "str"),
    0x03: ("battler_hue", "int"),
    0x04: ("max_hp", "int"),
    0x05: ("max_sp", "int"),
    0x06: ("attack", "int"),
    0x07: ("defense", "int"),
    0x08: ("spirit", "int"),
    0x09: ("agility", "int"),
    0x0A: ("transparent", "bool"),
    0x0B: ("exp", "int"),
    0x0C: ("gold", "int"),
    0x0D: ("drop_id", "int"),
    0x0E: ("drop_prob", "int"),
    0x15: ("critical_hit", "bool"),
    0x16: ("critical_hit_chance", "int"),
    0x1A: ("miss", "bool"),
    0x1C: ("levitate", "bool"),
    0x20: ("state_ranks", "u8"),
    0x22: ("attribute_ranks", "u8"),
    0x2A: ("actions", "raw"),             # array of ENEMY_ACTION
}

ENEMY_ACTION = {
    0x01: ("kind", "int"),                # 0 basic, 1 skill, 2 transform
    0x02: ("basic", "int"),               # 0 attack, 1 double, 2 defend, 3 observe,
                                          # 4 charge, 5 self-destruct, 6 escape, 7 nothing
    0x03: ("skill_id", "int"),
    0x04: ("enemy_id", "int"),
    0x05: ("condition_type", "int"),      # 0 always, 1 switch, 2 turns, 3 party size,
                                          # 4 own HP %, 5 own SP %, 6 party level, 7 fatigue
    0x06: ("condition_param1", "int"),
    0x07: ("condition_param2", "int"),
    0x08: ("switch_id", "int"),
    0x09: ("switch_on", "bool"),
    0x0A: ("switch_on_id", "int"),
    0x0B: ("switch_off", "bool"),
    0x0C: ("switch_off_id", "int"),
    0x0D: ("rating", "int"),
}

TROOP = {
    0x01: ("name", "str"),
    0x02: ("members", "raw"),
    0x03: ("auto_alignment", "bool"),
    0x05: ("terrain_set", "u8"),
    0x0B: ("pages", "raw"),
}

TROOP_MEMBER = {
    0x01: ("enemy_id", "int"),
    0x02: ("x", "int"),
    0x03: ("y", "int"),
    0x04: ("invisible", "bool"),
}

TERRAIN = {
    0x01: ("name", "str"),
    0x02: ("damage", "int"),
    0x03: ("encounter_rate", "int"),      # percent of the map's rate
    0x04: ("background_name", "str"),
    0x05: ("boat_pass", "bool"),
    0x06: ("ship_pass", "bool"),
    0x07: ("airship_pass", "bool"),
    0x09: ("airship_land", "bool"),
    0x0B: ("bush_depth", "int"),          # 0 none, 1 third, 2 half, 3 two thirds
    0x0F: ("footstep", "raw"),            # RM2003 sound
    0x10: ("on_damage_se", "bool"),
    # RM2003: 0 the background image, 1 two scrolling layers (from Frame/)
    0x11: ("background_type", "int"),
    0x15: ("background_a_name", "str"),
    0x16: ("background_a_scrollh", "bool"),
    0x17: ("background_a_scrollv", "bool"),
    0x18: ("background_a_scrollh_speed", "int"),
    0x19: ("background_a_scrollv_speed", "int"),
    0x1E: ("background_b", "bool"),
    0x1F: ("background_b_name", "str"),
    0x20: ("background_b_scrollh", "bool"),
    0x21: ("background_b_scrollv", "bool"),
    0x22: ("background_b_scrollh_speed", "int"),
    0x23: ("background_b_scrollv_speed", "int"),
}

ATTRIBUTE = {
    0x01: ("name", "str"),
    0x02: ("type", "int"),
    0x0B: ("a_rate", "int"),
    0x0C: ("b_rate", "int"),
    0x0D: ("c_rate", "int"),
    0x0E: ("d_rate", "int"),
    0x0F: ("e_rate", "int"),
}

STATE = {
    0x01: ("name", "str"),
    0x02: ("type", "int"),                # 0 ends with the battle, 1 persists
    0x03: ("color", "int"),
    0x04: ("priority", "int"),
    0x05: ("restriction", "int"),         # 0 none, 1 cannot act, 2 attacks enemies, 3 attacks allies
    0x0B: ("a_rate", "int"),
    0x0C: ("b_rate", "int"),
    0x0D: ("c_rate", "int"),
    0x0E: ("d_rate", "int"),
    0x0F: ("e_rate", "int"),
    0x15: ("hold_turn", "int"),
    0x16: ("auto_release_prob", "int"),
    0x17: ("release_by_damage", "int"),
    0x1E: ("affect_type", "int"),         # 0 halve, 1 double, 2 unchanged
    0x1F: ("affect_attack", "bool"),
    0x20: ("affect_defense", "bool"),
    0x21: ("affect_spirit", "bool"),
    0x22: ("affect_agility", "bool"),
    0x23: ("reduce_hit_ratio", "int"),
    0x24: ("avoid_attacks", "bool"),
    0x25: ("reflect_magic", "bool"),
    0x26: ("cursed", "bool"),
    0x27: ("battler_animation_id", "int"),
    0x29: ("restrict_skill", "bool"),
    0x2A: ("restrict_skill_level", "int"),
    0x2B: ("restrict_magic", "bool"),
    0x2C: ("restrict_magic_level", "int"),
    0x2D: ("hp_change_type", "int"),      # 0 lose, 1 gain, 2 none
    0x2E: ("sp_change_type", "int"),
    0x33: ("message_actor", "str"),
    0x34: ("message_enemy", "str"),
    0x35: ("message_already", "str"),
    0x36: ("message_affected", "str"),
    0x37: ("message_recovery", "str"),
    0x3D: ("hp_change_max", "int"),       # percent of max HP per turn
    0x3E: ("hp_change_val", "int"),       # fixed amount per turn
    0x3F: ("hp_change_map_steps", "int"),
    0x40: ("hp_change_map_val", "int"),
    0x41: ("sp_change_max", "int"),
    0x42: ("sp_change_val", "int"),
    0x43: ("sp_change_map_steps", "int"),
    0x44: ("sp_change_map_val", "int"),
}

ANIMATION = {
    0x01: ("name", "str"),
    0x02: ("animation_name", "str"),
    0x03: ("large", "bool"),
    0x06: ("timings", "raw"),
    0x09: ("scope", "int"),
    0x0A: ("position", "int"),
    0x0C: ("frames", "raw"),
}

# Battle animations: frames of cells, plus timings for sound and flashes.
ANIMATION_FRAME = {
    0x01: ("cells", "raw"),
}
ANIMATION_CELL = {
    0x01: ("valid", "bool"),
    0x02: ("cell_id", "int"),
    0x03: ("x", "int"),
    0x04: ("y", "int"),
    0x05: ("zoom", "int"),
    0x0A: ("transparency", "int"),
}
ANIMATION_TIMING = {
    0x01: ("frame", "int"),
    0x02: ("se", "raw"),
    0x03: ("flash_scope", "int"),         # 0 none, 1 target, 2 screen
    0x04: ("flash_red", "int"),
    0x05: ("flash_green", "int"),
    0x06: ("flash_blue", "int"),
    0x07: ("flash_power", "int"),
}

CHIPSET = {
    0x01: ("name", "str"),
    0x02: ("chipset_name", "str"),
    0x03: ("terrain_data", "i16"),
    0x04: ("passable_data_lower", "u8"),
    0x05: ("passable_data_upper", "u8"),
    0x0B: ("animation_type", "int"),
    0x0C: ("animation_speed", "int"),
}

COMMON_EVENT = {
    0x01: ("name", "str"),
    0x0B: ("trigger", "int"),
    0x0C: ("switch_flag", "bool"),
    0x0D: ("switch_id", "int"),
    0x15: ("event_commands_size", "int"),
    0x16: ("event_commands", "cmds"),
}

NAMED = {0x01: ("name", "str")}

# Derived from the reference project, where every value identifies itself:
# 0x11 is 'bg2' (a file in Title/), 0x13 is 'IR-Sys' (the window skin in
# System/), and the audio block reads title/battle/battle-end/inn/boat/ship/
# airship/gameover then the SE list in RM2k's own menu order.
SYSTEM = {
    0x0B: ("boat_name", "str"),
    0x0C: ("ship_name", "str"),
    0x0D: ("airship_name", "str"),
    0x0E: ("boat_index", "int"),
    0x0F: ("ship_index", "int"),
    0x10: ("airship_index", "int"),
    0x11: ("title_name", "str"),
    0x12: ("gameover_name", "str"),
    0x13: ("system_name", "str"),
    0x14: ("system2_name", "str"),
    0x15: ("party_size", "int"),
    0x16: ("party", "i16"),
    0x1B: ("menu_commands", "i16"),       # RM2003 main menu layout
    0x1F: ("title_music", "raw"),
    0x20: ("battle_music", "raw"),
    0x21: ("battle_end_music", "raw"),
    0x22: ("inn_music", "raw"),
    0x23: ("boat_music", "raw"),
    0x24: ("ship_music", "raw"),
    0x25: ("airship_music", "raw"),
    0x26: ("gameover_music", "raw"),
    0x29: ("cursor_se", "raw"),
    0x2A: ("decision_se", "raw"),
    0x2B: ("cancel_se", "raw"),
    0x2C: ("buzzer_se", "raw"),
    0x2D: ("battle_se", "raw"),
    0x2E: ("escape_se", "raw"),
    0x2F: ("enemy_attack_se", "raw"),
    0x30: ("enemy_damaged_se", "raw"),
    0x31: ("actor_damaged_se", "raw"),
    0x32: ("dodge_se", "raw"),
    0x33: ("enemy_death_se", "raw"),
    0x34: ("item_se", "raw"),
    0x3D: ("transition_out", "int"),
    0x3E: ("transition_in", "int"),
    0x3F: ("battle_start_fadeout", "int"),
    0x40: ("battle_start_fadein", "int"),
    0x41: ("battle_end_fadeout", "int"),
    0x42: ("battle_end_fadein", "int"),
    0x47: ("message_stretch", "int"),     # 0 stretch, 1 tile the window background
    0x48: ("font_id", "int"),
    0x51: ("selected_condition", "int"),
    0x52: ("selected_hero", "int"),
    0x54: ("battle_test_background", "str"),
    0x55: ("battle_test_party", "raw"),
    0x5B: ("save_count", "int"),
    0x61: ("equipment_setting", "int"),   # RM2003: 0 by hero, 1 by class
    0x63: ("show_frame", "bool"),         # RM2003 screen frame overlay
    0x64: ("frame_name", "str"),
    0x65: ("invert_animations", "bool"),
    0x6F: ("show_title", "bool"),
}

MAP_INFO = {
    0x01: ("name", "str"),
    0x02: ("parent_id", "int"),
    0x03: ("indentation", "int"),
    0x04: ("type", "int"),
    0x05: ("scrollbar_x", "int"),
    0x06: ("scrollbar_y", "int"),
    0x07: ("expanded_node", "bool"),
    0x0B: ("music_type", "int"),
    0x0C: ("music", "raw"),
    # Battle background: 0 same as the parent map, 1 the terrain's, 2 own.
    0x15: ("background_type", "int"),
    0x16: ("background_name", "str"),
    # 0 same as the parent map, 1 allowed, 2 forbidden.
    0x1F: ("teleport", "int"),
    0x20: ("escape", "int"),
    0x21: ("save", "int"),
    0x29: ("encounters", "raw"),        # array of {0x01 troop id}
    0x2C: ("encounter_steps", "int"),
    0x33: ("area_rect", "raw"),         # areas: left, top, right, bottom
}

MAP_EVENT = {
    0x01: ("name", "str"),
    0x02: ("x", "int"),
    0x03: ("y", "int"),
    0x05: ("pages", "raw"),
}

MAP_EVENT_PAGE = {
    0x02: ("condition", "raw"),
    0x15: ("character_name", "str"),
    0x16: ("character_index", "int"),
    0x17: ("character_direction", "int"),
    0x18: ("character_pattern", "int"),
    0x19: ("translucent", "int"),
    0x1F: ("move_type", "int"),
    0x20: ("move_frequency", "int"),
    0x21: ("trigger", "int"),
    0x22: ("layer", "int"),
    0x23: ("overlap_forbidden", "bool"),
    0x24: ("animation_type", "int"),
    0x25: ("move_speed", "int"),
    0x29: ("move_route", "raw"),
    0x2B: ("move_route_repeated", "bool"),
    0x2C: ("move_route_skippable", "bool"),
    0x33: ("event_commands_size", "int"),
    0x34: ("event_commands", "cmds"),
}

MAP_EVENT_PAGE_CONDITION = {
    0x01: ("flags", "int"),
    0x02: ("switch_a_id", "int"),
    0x03: ("switch_b_id", "int"),
    0x04: ("variable_id", "int"),
    0x05: ("variable_value", "int"),
    0x06: ("item_id", "int"),
    0x07: ("actor_id", "int"),
    0x08: ("timer_sec", "int"),
    0x09: ("timer2_sec", "int"),
}

MUSIC = {
    0x01: ("name", "str"),
    0x02: ("fadein", "int"),
    0x03: ("volume", "int"),
    0x04: ("tempo", "int"),
    0x05: ("balance", "int"),
}

SOUND = {
    0x01: ("name", "str"),
    0x03: ("volume", "int"),
    0x04: ("tempo", "int"),
    0x05: ("balance", "int"),
}


# --- RPG Maker 2003 only ----------------------------------------------------
# 0x1E Class, 0x20 BattlerAnimation.  Chunk 0x3E of a class is the battle
# animation set it uses: in the reference project class 13 points at set 14
# and class 14 at set 13, which rules out the id simply doubling as the index.
CLASS = {
    0x01: ("name", "str"),
    0x15: ("two_weapon", "bool"),
    0x16: ("lock_equipment", "bool"),
    0x17: ("auto_battle", "bool"),
    0x18: ("super_guard", "bool"),
    0x1F: ("parameters", "i16"),
    0x29: ("exp_base", "int"),
    0x2A: ("exp_inflation", "int"),
    0x2B: ("exp_correction", "int"),
    0x3E: ("battler_animation", "int"),
    0x3F: ("skills", "raw"),
    0x48: ("state_ranks", "u8"),
    0x4A: ("attribute_ranks", "u8"),
    0x50: ("battle_commands", "raw"),
}

BATTLER_ANIMATION = {
    0x01: ("name", "str"),
    0x0A: ("poses", "raw"),
    0x0B: ("weapons", "raw"),
}

# One entry per pose; the array index is the pose, in RM2003's fixed order:
# 1 idle, 2 attack right, 3 attack left, 4 skill, 5 dead, 6 damage,
# 7 bad status, 8 defending, 9 walk left, 10 walk right, 11 victory, 12 item.
BATTLER_POSE = {
    0x01: ("name", "str"),
    0x02: ("battler_name", "str"),   # file in BattleCharSet/
    0x03: ("row", "int"),            # row inside that 3x8 sheet
    0x04: ("animation_type", "int"), # 0 the sheet's row, 1 a battle animation
    0x05: ("battle_animation_id", "int"),
}
