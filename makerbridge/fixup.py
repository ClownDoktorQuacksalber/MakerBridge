"""Make the project survive assets the original never shipped.

RM2k loaded a lot of graphics and sounds from a shared RTP install, so a
converted project refers to files that simply are not there.  MV does not
shrug that off: the first time it needs one it stops with a "Loading Error"
dialog, which is enough to make the title screen unusable.

Two repairs, both reversible by re-running ``convert``:

* a missing **sound** has its name blanked, so MV never asks for it;
* a missing **image** gets a transparent placeholder of the right shape, so
  MV loads something and the event stays where it is.
"""

from __future__ import annotations

import json
import logging
import os
import re

log = logging.getLogger(__name__)

AUDIO_KINDS = ("bgm", "bgs", "me", "se")
IMAGE_KINDS = ("characters", "faces", "enemies", "pictures", "parallaxes",
               "titles1", "titles2", "animations", "sv_actors", "sv_enemies")

# Which audio folder the engine asks for, per field.  RM2k keeps every track
# in one Music folder, so a fanfare used as an ME has to be put where the
# engine will look for it.
AUDIO_FIELD_KIND = {
    "bgm": "bgm", "bgs": "bgs", "me": "me", "se": "se",
    "titleBgm": "bgm", "battleBgm": "bgm",
    "gameoverMe": "me", "defeatMe": "me", "victoryMe": "me",
}
AUDIO_COMMAND_KIND = {241: "bgm", 245: "bgs", 249: "me", 250: "se", 44: "se"}
MV_CHANGE_VEHICLE_BGM, MV_CHANGE_VEHICLE_IMAGE = 140, 323
MV_SCRIPT, MV_SCRIPT_MORE = 355, 655

# System music and sounds changed by events become script calls
# (mv/events.py); the record is the JSON object in the call.  Which folder
# the engine reads it from depends on the setter.
SCRIPT_AUDIO = re.compile(
    r'(\$gameSystem\.(setBattleBgm|setVictoryMe|setDefeatMe|rm2kSetSound|rm2kSetMusic)'
    r'\((?:[^{()]*?,\s*)?)(\{.*?\})(\);)')
SCRIPT_AUDIO_KIND = {"setBattleBgm": "bgm", "setVictoryMe": "me", "setDefeatMe": "me",
                     "rm2kSetSound": "se", "rm2kSetMusic": "me"}

# Transparent placeholder geometry per folder.  Character and face sheets must
# keep MV's grid proportions or the engine slices them wrongly.
PLACEHOLDER_SIZE = {
    "characters": (576, 384),   # 4x2 characters of 3x4 frames at 48x48
    "faces": (576, 288),        # 4x2 faces at 144x144
    "enemies": (64, 64),
    "pictures": (1, 1),
    "parallaxes": (816, 624),
    "titles1": (816, 624),
    "titles2": (816, 624),
    "animations": (960, 960),   # 5x5 cells at 192px, MV's large-animation grid
    "sv_actors": (576, 384),    # 9x6 motion cells of 64px
}


def fixup(target: str, log, stub_images: bool = True,
          blank_audio: bool = True) -> int:
    data_dir = os.path.join(target, "data")
    if not os.path.isdir(data_dir):
        log.error("no data/ folder in %s", target)
        return 1

    pending = _untranscoded(target)
    if pending:
        log.error("%d audio file(s) are still mid/wav/mp3. Blanking now would "
                  "throw away references to tracks that do exist - run "
                  "transcode first, then fixup.", pending)
        return 1

    have = {kind: _listing(os.path.join(target, "img", kind), PLAYABLE_IMAGE)
            for kind in IMAGE_KINDS}
    have.update({kind: _listing(os.path.join(target, "audio", kind),
                                PLAYABLE_AUDIO)
                 for kind in AUDIO_KINDS})
    # RM2k ran on a case-insensitive filesystem, so a project happily refers to
    # "people1" when the file is "People1.png".  Map the lower-cased name back
    # to the real spelling instead of only tolerating it, so the result also
    # works when the game is served from a case-sensitive filesystem.
    folded = {kind: {name.lower(): name for name in names}
              for kind, names in have.items()}
    state = {"audio": 0, "relinked": 0, "recased": 0, "moved": 0,
             "images": set()}

    def audio(node, kind: str) -> None:
        """Resolve an {name, volume, pitch, pan} record against ``audio/<kind>``.

        The folder matters: the engine asks for a BGM under audio/bgm and a
        victory fanfare under audio/me, and RM2k kept both in one Music
        folder.  Looking the name up "anywhere" hides exactly that mismatch.
        """
        if not blank_audio or not isinstance(node, dict):
            return
        name = node.get("name")
        if not isinstance(name, str) or not name:
            return

        actual = folded[kind].get(name.lower())
        if actual is not None:
            if actual != name:
                node["name"] = actual
                state["recased"] += 1
            return

        # RM2k keeps every track in one folder; the engine splits them up, so
        # a fanfare used as an ME has to be placed where the engine looks.
        moved = _borrow(target, kind, name, folded, have)
        if moved:
            node["name"] = moved
            state["moved"] += 1
            return

        # Some RM2k projects carry "<track>.link.wav" placeholder stubs, so the
        # stored name ends in ".link" while the real track sits next to it.
        if name.lower().endswith(".link"):
            real = folded[kind].get(name[:-5].lower())
            if real is not None:
                node["name"] = real
                state["relinked"] += 1
                return
        node["name"] = ""
        state["audio"] += 1

    def image(kind: str, name) -> None:
        if not isinstance(name, str) or not name:
            return None
        actual = folded[kind].get(name.lower())
        if actual is None:
            state["images"].add((kind, name))
            return None
        if actual != name:
            state["recased"] += 1
            return actual
        return None

    changed_files = 0
    for entry in sorted(os.listdir(data_dir)):
        if not entry.endswith(".json"):
            continue
        path = os.path.join(data_dir, entry)
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        keys = ("audio", "relinked", "recased", "moved")
        before = tuple(state[k] for k in keys)
        _walk(payload, audio, image)
        if tuple(state[k] for k in keys) != before:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
            changed_files += 1

    if state["recased"]:
        log.info("corrected %d reference(s) that differed from the real file "
                 "name only in capitalisation", state["recased"])
    if state["moved"]:
        log.info("copied %d track(s) into the folder the engine asks for "
                 "(RM2k keeps BGM and ME together, the engine does not)",
                 state["moved"])
    if state["relinked"]:
        log.info("repointed %d reference(s) from a '.link' placeholder to the "
                 "real track next to it", state["relinked"])
    if state["audio"]:
        log.info("blanked %d reference(s) to sounds that were never shipped, "
                 "across %d file(s)", state["audio"], changed_files)

    missing = sorted(state["images"])
    if missing and stub_images:
        made = _write_placeholders(target, missing, log)
        log.info("wrote %d transparent placeholder image(s)", made)
    elif missing:
        log.warning("%d image(s) are still missing; MV will stop when it needs "
                    "one of them", len(missing))
    for kind, name in missing:
        log.debug("    placeholder img/%s/%s.png", kind, name)
    return 0


def _walk(node, audio, image) -> None:
    """Visit every asset reference in an MV data structure."""
    if isinstance(node, list):
        for item in node:
            _walk(item, audio, image)
        return
    if not isinstance(node, dict):
        return

    for key, kind in AUDIO_FIELD_KIND.items():
        if isinstance(node.get(key), dict):
            audio(node[key], kind)
    if isinstance(node.get("sounds"), list):
        for sound in node["sounds"]:
            audio(sound, "se")

    for key, kind in (("characterName", "characters"), ("faceName", "faces"),
                      ("parallaxName", "parallaxes"),
                      ("title1Name", "titles1"), ("title2Name", "titles2"),
                      ("animation1Name", "animations"),
                      ("animation2Name", "animations")):
        corrected = image(kind, node.get(key))
        if corrected is not None:
            node[key] = corrected

    battler = node.get("battlerName")
    if isinstance(battler, str) and battler:
        # An actor fights with an sv_actors sheet, an enemy with an image in
        # enemies/ - the field name alone does not say which.
        corrected = image("sv_actors" if "equips" in node else "enemies", battler)
        if corrected is not None:
            node["battlerName"] = corrected

    code = node.get("code")
    params = node.get("parameters")
    if isinstance(code, int) and isinstance(params, list):
        _command(code, params, audio, image)

    for value in node.values():
        if isinstance(value, (list, dict)):
            _walk(value, audio, image)


def _command(code: int, params: list, audio, image) -> None:
    def fix(index: int, kind: str) -> None:
        if len(params) > index:
            corrected = image(kind, params[index])
            if corrected is not None:
                params[index] = corrected

    if code in (231, 232):
        fix(1, "pictures")
    elif code == MV_CHANGE_VEHICLE_BGM and len(params) > 1 and isinstance(params[1], dict):
        audio(params[1], "bgm")
    elif code == MV_CHANGE_VEHICLE_IMAGE:
        fix(1, "characters")
    elif code in (MV_SCRIPT, MV_SCRIPT_MORE) and params and isinstance(params[0], str):
        params[0] = _script_audio(params[0], audio)
    elif code in AUDIO_COMMAND_KIND and params and isinstance(params[0], dict):
        audio(params[0], AUDIO_COMMAND_KIND[code])
    elif code == 322:
        fix(1, "characters")
        fix(3, "faces")
        fix(5, "sv_actors")
    elif code == 284:
        fix(0, "parallaxes")
    elif code == 41:                            # move route: change image
        fix(0, "characters")



def _script_audio(script: str, audio) -> str:
    """Resolve the audio records inside the script calls events.py writes
    for "Change System BGM / SE", rewriting the call if one changed."""
    def one(match):
        try:
            record = json.loads(match.group(3))
        except ValueError:
            return match.group(0)
        if not isinstance(record, dict):
            return match.group(0)
        before = dict(record)
        audio(record, SCRIPT_AUDIO_KIND[match.group(2)])
        if record == before:
            return match.group(0)
        return (match.group(1) + json.dumps(record, ensure_ascii=False)
                + match.group(4))
    return SCRIPT_AUDIO.sub(one, script)


def _write_placeholders(target: str, missing: list[tuple[str, str]], log) -> int:
    from PIL import Image

    made = 0
    for kind, name in missing:
        folder = os.path.join(target, "img", kind)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name + ".png")
        if os.path.isfile(path):
            continue
        size = PLACEHOLDER_SIZE.get(kind, (48, 48))
        try:
            Image.new("RGBA", size, (0, 0, 0, 0)).save(path)
            made += 1
        except OSError as exc:
            log.error("could not write placeholder %s: %s", path, exc)
    return made


# MV only ever requests these, because it appends the extension itself.  A
# leftover .wav or .mid with the right stem does NOT make a name loadable.
PLAYABLE_AUDIO = {".ogg", ".m4a"}
PLAYABLE_IMAGE = {".png", ".rpgmvp"}
# What convert copies but the engine cannot play until "transcode" ran.
UNTRANSCODED_EXT = (".mid", ".midi", ".wav", ".mp3", ".wma")


def _borrow(target: str, kind: str, name: str, folded: dict, have: dict):
    """Copy a track from another audio folder into the one being asked for."""
    import shutil
    for other in AUDIO_KINDS:
        if other == kind:
            continue
        actual = folded[other].get(name.lower())
        if actual is None:
            continue
        for extension in PLAYABLE_AUDIO:
            source = os.path.join(target, "audio", other, actual + extension)
            if not os.path.isfile(source):
                continue
            destination_dir = os.path.join(target, "audio", kind)
            os.makedirs(destination_dir, exist_ok=True)
            try:
                shutil.copy2(source, os.path.join(destination_dir,
                                                  actual + extension))
            except OSError:
                return None
            folded[kind][actual.lower()] = actual
            have[kind].add(actual)
            return actual
    return None


def _untranscoded(target: str) -> int:
    """Audio still in a format the engine never requests.

    Running fixup before transcode is the one ordering that silently ruins a
    project: every track still looks missing, so every reference to it gets
    blanked even though the file is right there.
    """
    count = 0
    for kind in AUDIO_KINDS:
        folder = os.path.join(target, "audio", kind)
        try:
            entries = os.listdir(folder)
        except OSError:
            continue
        for entry in entries:
            stem, ext = os.path.splitext(entry)
            if ext.lower() in UNTRANSCODED_EXT:
                # Already converted next to it?  Then it is just a leftover.
                if not any(os.path.isfile(os.path.join(folder, stem + playable))
                           for playable in PLAYABLE_AUDIO):
                    count += 1
    return count


def _listing(folder: str, extensions: set[str]) -> set[str]:
    try:
        entries = os.listdir(folder)
    except OSError:
        return set()
    out = set()
    for entry in entries:
        stem, ext = os.path.splitext(entry)
        if ext.lower() in extensions:
            out.add(stem)
    return out
