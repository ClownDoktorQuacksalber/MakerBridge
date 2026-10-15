"""Load a complete RPG Maker 2000 project from disk."""

from __future__ import annotations

import logging
import os
import re
import struct
from dataclasses import dataclass, field

from .lcf import model
from .lcf.reader import LcfError

log = logging.getLogger(__name__)

MAP_FILE_RE = re.compile(r"^Map(\d{4})\.lmu$", re.IGNORECASE)

# RM2k stores text in the ANSI codepage of the machine it was authored on.
# Western-European projects are cp1252; the CLI can override this.
DEFAULT_ENCODING = "cp1252"

ASSET_DIRS = [
    "Backdrop", "Battle", "BattleCharSet", "BattleWeapon", "CharSet",
    "ChipSet", "FaceSet", "Frame", "GameOver", "Monster", "Movie", "Music",
    "Panorama", "Picture", "Sound", "System", "System2", "Title",
]


@dataclass
class Rm2kProject:
    root: str
    encoding: str
    database: dict
    maptree: dict
    maps: dict[int, dict] = field(default_factory=dict)
    ini: dict[str, str] = field(default_factory=dict)
    asset_dirs: dict[str, str] = field(default_factory=dict)
    # Installed RTP folders, searched after the game's own (RPG_RT did too).
    rtp_dirs: list[str] = field(default_factory=list)
    # kind -> file names converted from the RTP, for the log.
    rtp_used: dict[str, set] = field(default_factory=dict)

    @property
    def game_title(self) -> str:
        return self.ini.get("GameTitle") or os.path.basename(self.root)

    def map_ids(self) -> list[int]:
        return sorted(self.maps)

    def map_info(self, map_id: int) -> dict:
        return self.maptree.get("map_infos", {}).get(map_id, {})

    def find_asset(self, kind: str, name: str, exts=(".png", ".bmp", ".xyz")) -> str | None:
        """Case-insensitive lookup of an asset in the game's RM2k folders,
        then in the installed RTP (see :attr:`rtp_dirs`)."""
        if not name:
            return None
        directory = self.asset_dirs.get(kind.lower())
        target = name.lower()
        if directory:
            try:
                entries = os.listdir(directory)
            except OSError:
                entries = []
            for entry in entries:
                stem, ext = os.path.splitext(entry)
                if stem.lower() == target and (not exts or ext.lower() in exts):
                    return os.path.join(directory, entry)
        for entry, path in self._rtp_index().get(kind.lower(), {}).get(target, []):
            if not exts or os.path.splitext(entry)[1].lower() in exts:
                return path
        return None

    def asset_files(self, kind: str, exts=None) -> list[tuple[str, str]]:
        """(file name, path) of every file of one asset kind to convert: the
        game's own folder plus the RTP files the project refers to that the
        game does not ship itself.  RPG_RT fell back to the RTP for those."""
        kind = kind.lower()
        out: list[tuple[str, str]] = []
        own: set[str] = set()
        directory = self.asset_dirs.get(kind)
        if directory:
            try:
                entries = sorted(os.listdir(directory))
            except OSError:
                entries = []
            for entry in entries:
                full = os.path.join(directory, entry)
                if not os.path.isfile(full):
                    continue
                if exts and os.path.splitext(entry)[1].lower() not in exts:
                    continue
                out.append((entry, full))
                own.add(os.path.splitext(entry)[0].lower())
        index = self._rtp_index().get(kind, {})
        if index:
            referenced = self.referenced_names()
            for stem in sorted(index):
                if stem in own or stem not in referenced:
                    continue
                for entry, path in index[stem]:
                    if exts and os.path.splitext(entry)[1].lower() not in exts:
                        continue
                    out.append((entry, path))
                    self.rtp_used.setdefault(kind, set()).add(entry)
                    break
        return out

    def from_rtp(self, path: str) -> bool:
        return any(os.path.normcase(path).startswith(os.path.normcase(d) + os.sep)
                   for d in self.rtp_dirs)

    def _rtp_index(self) -> dict[str, dict[str, list[tuple[str, str]]]]:
        """kind -> lower-case stem -> [(file name, path)], first RTP first."""
        cached = getattr(self, "_rtp_cache", None)
        if cached is not None:
            return cached
        index: dict[str, dict[str, list[tuple[str, str]]]] = {}
        for rtp in getattr(self, "rtp_dirs", []) or []:
            try:
                folders = sorted(os.listdir(rtp))
            except OSError:
                continue
            for folder in folders:
                full = os.path.join(rtp, folder)
                if not os.path.isdir(full):
                    continue
                kind = index.setdefault(folder.lower(), {})
                for entry in sorted(os.listdir(full)):
                    if not os.path.isfile(os.path.join(full, entry)):
                        continue
                    stem = os.path.splitext(entry)[0].lower()
                    kind.setdefault(stem, []).append((entry, os.path.join(full, entry)))
        self._rtp_cache = index
        return index

    def referenced_names(self) -> set[str]:
        """Lower-case RTP file stems the project's data mentions anywhere.

        Asset names hide in many places (database records, map tree music,
        event command strings, move routes, binary sub-records kept as hex),
        so instead of decoding each, every RTP stem is looked up in all the
        project's text and raw bytes.  A false hit only copies one file too
        many."""
        cached = getattr(self, "_referenced", None)
        if cached is not None:
            return cached
        found: set[str] = set()
        index = self._rtp_index()
        if index:
            corpus = _corpus(self, self.encoding)
            for kind in index.values():
                for stem in kind:
                    if stem and stem.encode(self.encoding, "replace") in corpus:
                        found.add(stem)
        self._referenced = found
        return found


_HEX = re.compile(r"(?:[0-9a-fA-F]{2}){2,}")
# RM2k "Move Event" (11330) keeps its route inline as one integer per byte.
MOVE_EVENT_CODE = 11330


def _corpus(project, encoding: str) -> bytes:
    """All text and raw bytes of the project, lower-cased, for name search."""
    parts: list[bytes] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if node.get("code") == MOVE_EVENT_CODE and isinstance(node.get("parameters"), list):
                parts.append(bytes(v & 0xFF for v in node["parameters"] if isinstance(v, int)))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            if node and all(isinstance(v, int) for v in node):
                return
            for value in node:
                walk(value)
        elif isinstance(node, str) and node:
            if _HEX.fullmatch(node):
                parts.append(bytes.fromhex(node))
            parts.append(node.encode(encoding, "replace"))

    walk(project.database)
    walk(project.maptree)
    walk(project.ini)
    for data in project.maps.values():
        walk({k: v for k, v in data.items() if k not in ("lower_layer", "upper_layer")})
    return b"\0".join(parts).lower()


# Where the RPG Maker 2000 / 2003 installers record their RTP.
RTP_REGISTRY = {
    "rm2k": [(r"Software\ASCII\RPG2000", "RuntimePackagePath"),
             (r"Software\WOW6432Node\ASCII\RPG2000", "RuntimePackagePath")],
    "rm2k3": [(r"Software\Enterbrain\RPG2003", "RUNTIMEPACKAGEPATH"),
              (r"Software\WOW6432Node\Enterbrain\RPG2003", "RUNTIMEPACKAGEPATH")],
}
RTP_ENV = {"rm2k": "RPG2K_RTP_PATH", "rm2k3": "RPG2K3_RTP_PATH"}


def _registry_value(path: str, name: str) -> list[str]:
    try:
        import winreg
    except ImportError:
        return []
    out = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, path) as key:
                value, _ = winreg.QueryValueEx(key, name)
        except OSError:
            continue
        if isinstance(value, str) and value:
            out.append(value)
    return out


def find_rtp(engine: str, explicit=None) -> list[str]:
    """RTP folders to fall back on, best first: the ones named on the
    command line, then the engine's own RTP (environment, registry), then
    the generic RPG_RTP_PATH, then the other engine's RTP."""
    other = "rm2k" if engine == "rm2k3" else "rm2k3"
    if isinstance(explicit, str):
        explicit = [explicit]
    explicit = list(explicit or [])
    candidates: list[str] = list(explicit)
    for which in (engine, None, other):
        if which is None:
            candidates.append(os.environ.get("RPG_RTP_PATH", ""))
            continue
        candidates.append(os.environ.get(RTP_ENV[which], ""))
        for path, name in RTP_REGISTRY[which]:
            candidates += _registry_value(path, name)
    out: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        full = os.path.abspath(candidate)
        if os.path.isdir(full):
            if full not in out:
                out.append(full)
        elif candidate in explicit:
            log.warning("RTP folder %s does not exist", candidate)
    return out


def _exe_version(path: str) -> tuple[int, int, int, int] | None:
    """File version from RPG_RT.exe's VERSIONINFO, or None (old builds have none)."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    at = data.find(b"\xbd\x04\xef\xfe")          # VS_FIXEDFILEINFO signature
    if at < 0 or at + 16 > len(data):
        return None
    ms, ls = struct.unpack_from("<II", data, at + 8)
    return ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF


def _rpg_rt(root: str) -> str | None:
    for entry in os.listdir(root):
        if entry.lower() == "rpg_rt.exe":
            return os.path.join(root, entry)
    return None


def _english_engine(root: str, database: dict) -> bool:
    """RPG Maker 2003 1.10+ or RPG Maker 2000 1.6x - the official English
    releases, whose runtime added picture layers, sprite sheets and more
    (EasyRPG: EngineEnglish, told apart the same way)."""
    exe = _rpg_rt(root)
    version = _exe_version(exe) if exe else None
    rm2k3 = database.get("_engine") == "rm2k3"
    if version and version[0] == 1:
        return version[1] == (1 if rm2k3 else 6)
    if rm2k3:
        return any(entry.lower() == "ultimate_rt_eb.dll" for entry in os.listdir(root))
    raw = (database.get("_unknown") or {}).get("0x1A") or ""
    return bool(raw) and int(raw[:2], 16) >= 1     # LDB format version


# RPG_RT.exe sizes above which a build without VERSIONINFO is the updated
# runtime (EasyRPG FileFinder: RpgrtMajorUpdateThreshold).
MAJOR_UPDATE_EXE_SIZE = {"rm2k": 735000, "rm2k3": 927000}


def _major_updated(root: str, database: dict, encoding: str) -> bool:
    """RPG Maker 2000 "Value!" (1.50+) or RPG Maker 2003 1.05+.

    These runtimes draw pictures below battle animations and fixed the
    "move picture" bug for pictures that scroll with the map (EasyRPG:
    EngineMajorUpdated, detected the same way)."""
    if database.get("_english"):
        return True
    exe = _rpg_rt(root)
    version = _exe_version(exe) if exe else None
    if version and version[:2] == (1, 0):
        return version[2] >= 5
    # Without a version: MP3 music only plays in the updated runtimes ...
    music = next((os.path.join(root, e) for e in os.listdir(root) if e.lower() == "music"), None)
    if music and os.path.isdir(music) and any(e.lower().endswith(".mp3") for e in os.listdir(music)):
        return True
    # ... else the updated RPG_RT.exe is the bigger one.
    engine = "rm2k3" if database.get("_engine") == "rm2k3" else "rm2k"
    if exe:
        return os.path.getsize(exe) > MAJOR_UPDATE_EXE_SIZE[engine]
    # No runtime at all: Japanese and RPG Maker 2003 games mostly use the newer one.
    return engine == "rm2k3" or encoding.lower() in ("cp932", "shift_jis", "sjis")


def _read_ini(path: str, encoding: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if not os.path.isfile(path):
        return out
    with open(path, "r", encoding=encoding, errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith((";", "[")):
                continue
            key, sep, value = line.partition("=")
            if sep:
                out[key.strip()] = value.strip()
    return out


def load(root: str, encoding: str = DEFAULT_ENCODING, rtp=None) -> Rm2kProject:
    root = os.path.abspath(root)
    ldb = os.path.join(root, "RPG_RT.ldb")
    lmt = os.path.join(root, "RPG_RT.lmt")
    if not os.path.isfile(ldb):
        raise FileNotFoundError(f"RPG_RT.ldb not found in {root}")
    if not os.path.isfile(lmt):
        raise FileNotFoundError(f"RPG_RT.lmt not found in {root}")

    log.info("reading database %s", os.path.basename(ldb))
    database = model.read_database(open(ldb, "rb").read(), encoding)
    database["_english"] = _english_engine(root, database)
    database["_major_updated"] = _major_updated(root, database, encoding)
    log.info("engine: %s%s", "RPG Maker 2003" if database["_engine"] == "rm2k3"
             else "RPG Maker 2000", " (official English update, 1.10+/1.6x)"
             if database["_english"] else " (updated runtime, 1.05+/Value!)"
             if database["_major_updated"] else " (old runtime)")
    log.info("reading map tree %s", os.path.basename(lmt))
    maptree = model.read_maptree(open(lmt, "rb").read(), encoding)

    maps: dict[int, dict] = {}
    for entry in sorted(os.listdir(root)):
        m = MAP_FILE_RE.match(entry)
        if not m:
            continue
        map_id = int(m.group(1))
        try:
            maps[map_id] = model.read_mapunit(
                open(os.path.join(root, entry), "rb").read(), encoding)
        except (LcfError, OSError) as exc:
            log.error("map %s failed to parse: %s", entry, exc)
    log.info("read %d maps", len(maps))

    asset_dirs: dict[str, str] = {}
    for entry in os.listdir(root):
        full = os.path.join(root, entry)
        if os.path.isdir(full):
            asset_dirs[entry.lower()] = full

    project = Rm2kProject(
        root=root,
        encoding=encoding,
        database=database,
        maptree=maptree,
        maps=maps,
        ini=_read_ini(os.path.join(root, "RPG_RT.ini"), encoding),
        asset_dirs=asset_dirs,
    )
    project.rtp_dirs = find_rtp(database.get("_engine") or "rm2k", rtp)
    if project.rtp_dirs:
        log.info("RTP: %s", "; ".join(project.rtp_dirs))
    else:
        log.info("no RTP installed or named (--rtp); assets the game does not "
                 "ship stay missing")
    _sanity_check(project)
    return project


def _sanity_check(project: Rm2kProject) -> None:
    """Log anything that suggests our reading of the format is off."""
    db = project.database
    for name in ("actors", "skills", "items", "enemies", "troops", "chipsets"):
        log.info("  %-14s %d", name, len(db.get(name, {})))

    infos = project.maptree.get("map_infos", {})
    missing = [i for i in project.maps if i not in infos]
    if missing:
        log.warning("maps without a map-tree entry: %s", missing)
    orphan = [i for i, info in infos.items()
              if i and info.get("type", 1) == 1 and i not in project.maps]
    if orphan:
        log.warning("map-tree entries without a .lmu file: %s", orphan)

    trailing = project.maptree.get("_trailing_bytes", 0)
    if trailing:
        log.warning("map tree had %d unparsed trailing bytes", trailing)

    chipsets = db.get("chipsets", {})
    for cid, cs in chipsets.items():
        lower = cs.get("passable_data_lower") or []
        upper = cs.get("passable_data_upper") or []
        terrain = cs.get("terrain_data") or []
        if lower and len(lower) != 162:
            log.warning("chipset %d: passable_data_lower has %d entries, expected 162",
                        cid, len(lower))
        if upper and len(upper) != 144:
            log.warning("chipset %d: passable_data_upper has %d entries, expected 144",
                        cid, len(upper))
        if terrain and len(terrain) != 162:
            log.warning("chipset %d: terrain_data has %d entries, expected 162",
                        cid, len(terrain))
