"""The graphical front end: pick a game, pick where it goes, press Convert.

Plain Tkinter, so it runs wherever Python does (Windows, Linux, macOS)
without anything to install.  The pipeline runs on a worker thread; its log,
the step it is on and the counts of warnings and errors reach the window
through a queue, so a long run over a few hundred maps stays responsive.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, font as tkfont, messagebox, ttk

from . import project
from .convert import convert_project, find_template

SUPPORT_URL = "https://buymeacoffee.com/clowndoktorquacksalber"
AUTHOR = "Clown Doktor Quacksalber"

STEPS = [
    ("convert", "Konvertieren", "Datenbank, Maps, Events, Tilesets und Grafiken", True),
    ("transcode", "Audio umwandeln", "MIDI, WAV und MP3 nach OGG (braucht ffmpeg)", True),
    ("fixup", "Fehlende Dateien abfangen", "fehlende Sounds leeren, fehlende Bilder ersetzen", True),
    ("verify", "Prüfen", "kontrolliert, ob MV/MZ das Projekt laden kann", True),
    ("package", "Spiel bauen", "Game.exe zum Testen (veröffentlichen im MZ-Editor)", True),
]

ENCODINGS = [
    ("cp1252", "Westeuropäisch (Deutsch, Englisch, ...)"),
    ("cp932", "Japanisch"),
    ("cp949", "Koreanisch"),
    ("cp936", "Chinesisch (vereinfacht)"),
    ("cp950", "Chinesisch (traditionell)"),
    ("cp1251", "Kyrillisch"),
    ("cp1250", "Mitteleuropäisch"),
    ("utf-8", "UTF-8"),
]

# Colours of the dark theme.
BG = "#15161c"
CARD = "#1f2129"
FIELD = "#2a2c37"
LINE = "#33364a"
TEXT = "#e7e7ee"
MUTED = "#8e91a6"
ACCENT = "#f5a524"
ACCENT_HOVER = "#ffb84d"
OK = "#5fd08e"
WARN = "#f2c94c"
ERR = "#f06a6a"
COFFEE = "#ffdd00"

STATE_ICON = {"wait": "○", "run": "◐", "done": "✓", "fail": "✗", "skip": "–"}
STATE_COLOUR = {"wait": MUTED, "run": ACCENT, "done": OK, "fail": ERR, "skip": MUTED}


# -- platform helpers --------------------------------------------------------

def open_path(path: str) -> None:
    """Show a folder in the system's file manager."""
    if sys.platform.startswith("win"):
        os.startfile(path)                                  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def settings_path() -> str:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "makerbridge", "gui.json")


def load_settings() -> dict:
    try:
        with open(settings_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(settings_path()), exist_ok=True)
        with open(settings_path(), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
    except OSError:
        pass


def find_game_exe(folder: str) -> str | None:
    try:
        for entry in os.listdir(folder):
            if entry.lower() == "game.exe":
                return os.path.join(folder, entry)
    except OSError:
        pass
    return None


def describe_project(path: str, encoding: str) -> dict:
    """What the window shows about a game before converting it: engine and
    version, title and number of maps.  Reads only the database."""
    ldb = os.path.join(path, "RPG_RT.ldb")
    if not os.path.isfile(ldb):
        return {"ok": False, "error": "In diesem Ordner liegt keine RPG_RT.ldb."}
    from .lcf import model
    with open(ldb, "rb") as fh:
        db = model.read_database(fh.read(), encoding)
    rm2k3 = db.get("_engine") == "rm2k3"
    english = project._english_engine(path, db)
    db["_english"] = english
    updated = project._major_updated(path, db, encoding)
    engine = "RPG Maker 2003" if rm2k3 else "RPG Maker 2000 (experimentell, ungetestet)"
    if english:
        engine += " · 1.10+ (englisches Update)" if rm2k3 else " · 1.6x (englisches Update)"
    elif updated:
        engine += " · 1.05+" if rm2k3 else " · Value!"
    else:
        engine += " · alte Version"
    ini = project._read_ini(os.path.join(path, "RPG_RT.ini"), encoding)
    maps = sum(1 for entry in os.listdir(path) if re.match(r"(?i)^Map\d{4}\.lmu$", entry))
    return {
        "ok": True,
        "engine": engine,
        "title": ini.get("GameTitle") or os.path.basename(path.rstrip("/\\")),
        "maps": maps,
        "actors": len(db.get("actors") or {}),
        "events": len(db.get("common_events") or {}),
    }


def missing_tools() -> str:
    """What the audio step needs and the system lacks, for a hint in the window."""
    from .audio import find_ffmpeg, find_fluidsynth, find_soundfont
    missing = []
    if not find_ffmpeg():
        missing.append("ffmpeg (Musik umwandeln)")
    if not (find_fluidsynth() and find_soundfont()):
        missing.append("FluidSynth (MIDI-Musik)")
    return " und ".join(missing)


TEMPLATE_HELP = ("Lege im RPG Maker MZ ein neues, leeres Projekt an und wähle hier "
                 "dessen Ordner. Daraus kommt die Engine (js/, index.html), ohne die "
                 "das Projekt nicht startet und keine Game.exe gebaut wird.")


def describe_template(path: str) -> tuple[str, bool]:
    """The line under the template field, and whether the template is usable."""
    from .mv import engine as engines
    if not path:
        return "⚠  keine Vorlage gefunden. " + TEMPLATE_HELP, False
    found = engines.detect(path) if os.path.isdir(path) else None
    if not found:
        return "⚠  kein MV/MZ-Projekt (js/rmmz_core.js fehlt). " + TEMPLATE_HELP, False
    if found.key != "mz":
        return f"✓  {found.label} (experimentell, ungetestet)", True
    return f"✓  {found.label} · ein frisches, leeres MZ-Projekt ist ideal", True


def runtime_missing() -> bool:
    """Whether „Spiel bauen“ will fail for lack of the MZ editor's NW.js."""
    from .mv import engine as engines
    return engines.find_runtime(engines.MZ) is None


# -- logging into the window -------------------------------------------------

class QueueHandler(logging.Handler):
    def __init__(self, target: queue.Queue) -> None:
        super().__init__()
        self.target = target

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.target.put(("log", record.levelno, self.format(record)))
        except Exception:                                   # noqa: BLE001
            pass


# -- the window --------------------------------------------------------------

class App(tk.Frame):
    def __init__(self, master: tk.Tk, tool_root: str) -> None:
        super().__init__(master, bg=BG)
        self.master = master
        self.tool_root = tool_root
        self.pack(fill="both", expand=True)

        self.messages: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.started_at = 0.0
        self.counts = {"warn": 0, "err": 0}
        self.log_lines: list[tuple[int, str]] = []

        saved = load_settings()
        self.source = tk.StringVar(value=saved.get("source", ""))
        self.target = tk.StringVar(value=saved.get("target", ""))
        self.game_dir = tk.StringVar(value=saved.get("game_dir", ""))
        self.template = tk.StringVar(value=saved.get("template", "")
                                     or find_template(tool_root) or "")
        self.encoding = tk.StringVar(value=saved.get("encoding", project.DEFAULT_ENCODING))
        self.rtp = tk.StringVar(value=saved.get("rtp", ""))
        self.soundfont = tk.StringVar(value=saved.get("soundfont", ""))
        self.only_problems = tk.BooleanVar(value=False)
        self.show_advanced = tk.BooleanVar(value=False)
        saved_steps = saved.get("steps") or {}
        self.steps = {name: tk.BooleanVar(value=saved_steps.get(name, on))
                      for name, _, _, on in STEPS}
        self.step_icons: dict[str, tk.Label] = {}
        self._current = ""
        self._project_job = None

        self._fonts()
        self._styles()
        self._build()
        if not self.source.get():
            self._guess_defaults()
        self._refresh_project()
        self._refresh_template()
        self.after(100, self._drain)
        master.protocol("WM_DELETE_WINDOW", self._close)

    # -- look ----------------------------------------------------------------
    def _fonts(self) -> None:
        families = set(tkfont.families())
        for family in ("Segoe UI", "Inter", "Ubuntu", "Cantarell", "Noto Sans",
                       "DejaVu Sans", "Helvetica"):
            if family in families:
                break
        else:
            family = tkfont.nametofont("TkDefaultFont").actual("family")
        mono = next((f for f in ("Cascadia Mono", "Consolas", "JetBrains Mono",
                                 "DejaVu Sans Mono", "Monospace", "Courier New")
                     if f in families), "TkFixedFont")
        self.f_body = (family, 10)
        self.f_small = (family, 9)
        self.f_bold = (family, 10, "bold")
        self.f_head = (family, 11, "bold")
        self.f_title = (family, 20, "bold")
        self.f_button = (family, 12, "bold")
        self.f_mono = (mono, 9)
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            try:
                tkfont.nametofont(name).configure(family=family, size=10)
            except tk.TclError:
                pass

    def _styles(self) -> None:
        style = ttk.Style(self.master)
        style.theme_use("clam")
        style.configure(".", background=CARD, foreground=TEXT, fieldbackground=FIELD,
                        bordercolor=LINE, lightcolor=LINE, darkcolor=LINE,
                        troughcolor=FIELD, focuscolor=ACCENT, font=self.f_body)
        style.configure("TEntry", fieldbackground=FIELD, foreground=TEXT,
                        insertcolor=TEXT, padding=6)
        style.configure("TCombobox", fieldbackground=FIELD, foreground=TEXT,
                        background=FIELD, arrowcolor=TEXT, padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", FIELD)],
                  foreground=[("readonly", TEXT)])
        self.master.option_add("*TCombobox*Listbox.background", FIELD)
        self.master.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.master.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        style.configure("TCheckbutton", background=CARD, foreground=TEXT,
                        indicatorbackground=FIELD, indicatorforeground=ACCENT,
                        font=self.f_bold)
        style.map("TCheckbutton", background=[("active", CARD)],
                  indicatorbackground=[("selected", FIELD)])
        style.configure("Plain.TCheckbutton", font=self.f_body)
        style.configure("Card.TButton", background=FIELD, foreground=TEXT,
                        bordercolor=LINE, padding=(10, 5))
        style.map("Card.TButton", background=[("active", LINE)])
        style.configure("Accent.TButton", background=ACCENT, foreground="#1b1b1b",
                        bordercolor=ACCENT, padding=(22, 10), font=self.f_button)
        style.map("Accent.TButton", background=[("disabled", LINE), ("active", ACCENT_HOVER)],
                  foreground=[("disabled", MUTED)])
        style.configure("Coffee.TButton", background=COFFEE, foreground="#1b1b1b",
                        bordercolor=COFFEE, padding=(12, 6), font=self.f_bold)
        style.map("Coffee.TButton", background=[("active", "#ffe94d")])
        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=FIELD,
                        bordercolor=FIELD, lightcolor=ACCENT, darkcolor=ACCENT, thickness=8)
        style.configure("Vertical.TScrollbar", background=FIELD, troughcolor=CARD,
                        arrowcolor=MUTED, bordercolor=CARD)

    def _card(self, parent, title: str, number: str | None = None) -> tk.Frame:
        outer = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        head = tk.Frame(outer, bg=CARD)
        head.pack(fill="x", padx=14, pady=(10, 4))
        if number:
            tk.Label(head, text=number, bg=ACCENT, fg="#1b1b1b", font=self.f_bold,
                     width=2).pack(side="left", padx=(0, 8))
        tk.Label(head, text=title, bg=CARD, fg=TEXT, font=self.f_head).pack(side="left")
        body = tk.Frame(outer, bg=CARD)
        body.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        outer.body = body
        return outer

    def _form(self, parent) -> tk.Frame:
        """A grid of label / field / button rows whose hints line up."""
        form = tk.Frame(parent, bg=CARD)
        form.columnconfigure(1, weight=1)
        form.next_row = 0
        return form

    def _path_row(self, form, label: str, var: tk.StringVar, command,
                  hint: str = "") -> tk.Label:
        row = form.next_row
        tk.Label(form, text=label, bg=CARD, fg=MUTED, font=self.f_body,
                 anchor="w").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=(4, 0))
        ttk.Entry(form, textvariable=var).grid(row=row, column=1, sticky="ew", pady=(4, 0))
        ttk.Button(form, text="Durchsuchen", style="Card.TButton",
                   command=command).grid(row=row, column=2, padx=(8, 0), pady=(4, 0))
        info = tk.Label(form, text=hint, bg=CARD, fg=MUTED, font=self.f_small,
                        anchor="w", justify="left")
        info.grid(row=row + 1, column=1, columnspan=2, sticky="w")
        form.next_row = row + 2
        return info

    # -- layout --------------------------------------------------------------
    def _build(self) -> None:
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=18, pady=(14, 6))
        titles = tk.Frame(header, bg=BG)
        titles.pack(side="left")
        tk.Label(titles, text="MakerBridge", bg=BG, fg=TEXT, font=self.f_title).pack(anchor="w")
        tk.Label(titles, text="RPG Maker 2000 / 2003  →  RPG Maker MZ",
                 bg=BG, fg=MUTED, font=self.f_body).pack(anchor="w")
        ttk.Button(header, text="☕  Unterstützen", style="Coffee.TButton",
                   command=lambda: webbrowser.open(SUPPORT_URL)).pack(side="right")
        tk.Frame(self, bg=ACCENT, height=2).pack(fill="x", padx=18, pady=(4, 10))

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18)
        body.columnconfigure(0, weight=1, uniform="col")
        body.columnconfigure(1, weight=1, uniform="col")
        body.rowconfigure(3, weight=1)

        # 1  the game
        game = self._card(body, "Spiel auswählen", "1")
        game.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 10))
        form = self._form(game.body)
        form.pack(fill="x")
        self._path_row(form, "RM2k-Projekt", self.source, self._pick_source,
                       "der Ordner mit der RPG_RT.ldb")
        self.project_info = tk.Frame(game.body, bg=CARD)
        self.project_info.pack(fill="x", pady=(8, 0))
        self.project_status = tk.Label(self.project_info, bg=CARD, fg=MUTED,
                                       font=self.f_bold, anchor="w")
        self.project_status.pack(fill="x")
        self.project_details = tk.Label(self.project_info, bg=CARD, fg=MUTED,
                                        font=self.f_body, anchor="w", justify="left")
        self.project_details.pack(fill="x")

        # 2  where it goes
        out = self._card(body, "Ziel", "2")
        out.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 10))
        form = self._form(out.body)
        form.pack(fill="x")
        self._path_row(form, "MZ-Projekt", self.target, self._pick_target,
                       "das konvertierte Projekt, zum Öffnen im Editor")
        self._path_row(form, "Spielordner", self.game_dir, self._pick_game,
                       "hier landet die spielbare Version (optional)")
        self.template_info = self._path_row(form, "Engine-Vorlage", self.template,
                                            self._pick_template)
        self.template_info.config(wraplength=360)

        # 3  steps and options
        steps = self._card(body, "Schritte", "3")
        steps.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
        grid = tk.Frame(steps.body, bg=CARD)
        grid.pack(side="left", anchor="n")
        for i, (name, label, hint, _) in enumerate(STEPS):
            icon = tk.Label(grid, text=STATE_ICON["wait"], bg=CARD, fg=MUTED,
                            font=self.f_head, width=2)
            icon.grid(row=i, column=0, sticky="w")
            self.step_icons[name] = icon
            ttk.Checkbutton(grid, text=label, variable=self.steps[name]).grid(
                row=i, column=1, sticky="w", padx=(2, 12))
            tk.Label(grid, text=hint, bg=CARD, fg=MUTED, font=self.f_small).grid(
                row=i, column=2, sticky="w")
        missing = missing_tools()
        if missing:
            setup = ("„MakerBridge.bat setup“" if sys.platform.startswith("win")
                     else "„./MakerBridge.sh setup“")
            tk.Label(grid, text=f"⚠  {missing} fehlt – starte {setup}, um es zu installieren.",
                     bg=CARD, fg=WARN, font=self.f_small).grid(
                         row=len(STEPS), column=0, columnspan=3, sticky="w", pady=(8, 0))
        side = tk.Frame(steps.body, bg=CARD)
        side.pack(side="left", fill="both", expand=True, padx=(28, 0))
        ttk.Checkbutton(side, text="Erweiterte Einstellungen", style="Plain.TCheckbutton",
                        variable=self.show_advanced, command=self._toggle_advanced
                        ).pack(anchor="w")
        self.advanced = self._form(side)
        tk.Label(self.advanced, text="Textkodierung", bg=CARD, fg=MUTED,
                 anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=(4, 0))
        self.encoding_box = ttk.Combobox(
            self.advanced, state="readonly",
            values=[f"{code}  –  {name}" for code, name in ENCODINGS])
        self.encoding_box.grid(row=0, column=1, columnspan=2, sticky="ew", pady=(4, 0))
        self.encoding_box.bind("<<ComboboxSelected>>", self._encoding_chosen)
        tk.Label(self.advanced, text="nur für Spiele, die nicht westeuropäisch sind",
                 bg=CARD, fg=MUTED, font=self.f_small).grid(row=1, column=1, columnspan=2,
                                                            sticky="w")
        self.advanced.next_row = 2
        self._show_encoding()
        self._path_row(self.advanced, "RTP-Ordner", self.rtp, self._pick_rtp,
                       "nur nötig, wenn das RTP nicht installiert ist")
        self._path_row(self.advanced, "Soundfont", self.soundfont, self._pick_soundfont,
                       "Klangbank für MIDI-Musik (.sf2/.sf3/.dls)")

        # action bar
        action = tk.Frame(body, bg=BG)
        action.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self.run_button = ttk.Button(action, text="▶  Konvertieren", style="Accent.TButton",
                                     command=self._start)
        self.run_button.pack(side="left")
        progress_box = tk.Frame(action, bg=BG)
        progress_box.pack(side="left", fill="x", expand=True, padx=(16, 0))
        self.progress = ttk.Progressbar(progress_box, maximum=len(STEPS),
                                        style="Horizontal.TProgressbar")
        self.progress.pack(fill="x")
        self.status = tk.Label(progress_box, text="bereit", bg=BG, fg=MUTED,
                               font=self.f_body, anchor="w")
        self.status.pack(fill="x", pady=(4, 0))

        # the log
        logcard = self._card(body, "Protokoll")
        logcard.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
        tools = tk.Frame(logcard.body, bg=CARD)
        tools.pack(fill="x", pady=(0, 6))
        ttk.Checkbutton(tools, text="nur Warnungen und Fehler", style="Plain.TCheckbutton",
                        variable=self.only_problems, command=self._refilter).pack(side="left")
        ttk.Button(tools, text="Kopieren", style="Card.TButton",
                   command=self._copy_log).pack(side="right")
        ttk.Button(tools, text="Log-Ordner", style="Card.TButton",
                   command=lambda: self._open(os.path.join(self.tool_root, "log"))
                   ).pack(side="right", padx=6)
        self.summary = tk.Label(tools, text="", bg=CARD, fg=MUTED, font=self.f_body)
        self.summary.pack(side="right", padx=10)
        text_box = tk.Frame(logcard.body, bg=CARD)
        text_box.pack(fill="both", expand=True)
        self.log = tk.Text(text_box, height=8, wrap="none", bg="#101116", fg="#cfd0da",
                           insertbackground=TEXT, relief="flat", borderwidth=0,
                           font=self.f_mono, padx=8, pady=6)
        self.log.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(text_box, command=self.log.yview, style="Vertical.TScrollbar")
        scroll.pack(side="right", fill="y")
        self.log["yscrollcommand"] = scroll.set
        self.log.tag_configure("WARNING", foreground=WARN)
        self.log.tag_configure("ERROR", foreground=ERR)
        self.log.tag_configure("STEP", foreground=ACCENT, font=(self.f_mono[0], 9, "bold"))
        self.log.configure(state="disabled")

        # footer
        footer = tk.Frame(self, bg=BG)
        # Packed before the body, so a small screen squeezes the log, not this.
        footer.pack(side="bottom", fill="x", padx=18, pady=(0, 12), before=body)
        ttk.Button(footer, text="Ausgabe öffnen", style="Card.TButton",
                   command=lambda: self._open(self.target.get())).pack(side="left")
        ttk.Button(footer, text="Spiel starten", style="Card.TButton",
                   command=self._play).pack(side="left", padx=8)
        credit = tk.Label(footer, text=f"© {AUTHOR}  ·  GPL-3.0  ·  {SUPPORT_URL.split('//')[1]}",
                          bg=BG, fg=MUTED, font=self.f_small, cursor="hand2")
        credit.pack(side="right")
        credit.bind("<Button-1>", lambda _e: webbrowser.open(SUPPORT_URL))

        self.source.trace_add("write", lambda *_: self._schedule_project())
        self.template.trace_add("write", lambda *_: self._refresh_template())

    # -- small actions -------------------------------------------------------
    def _toggle_advanced(self) -> None:
        if self.show_advanced.get():
            self.advanced.pack(fill="x", pady=(4, 0))
        else:
            self.advanced.pack_forget()

    def _show_encoding(self) -> None:
        code = self.encoding.get()
        for index, (value, _) in enumerate(ENCODINGS):
            if value == code:
                self.encoding_box.current(index)
                return
        self.encoding_box.set(code)

    def _encoding_chosen(self, _event=None) -> None:
        self.encoding.set(ENCODINGS[self.encoding_box.current()][0])
        self._refresh_project()

    def _open(self, path: str) -> None:
        if path and os.path.isdir(path):
            try:
                open_path(path)
            except OSError as exc:
                messagebox.showerror("Öffnen fehlgeschlagen", str(exc))
        else:
            messagebox.showinfo("Noch nichts da", "Dieser Ordner existiert noch nicht.")

    def _copy_log(self) -> None:
        self.clipboard_clear()
        self.clipboard_append("\n".join(text for _, text in self.log_lines))
        self.status.config(text="Protokoll in die Zwischenablage kopiert")

    def _guess_defaults(self) -> None:
        """Offer the first RM2k game sitting next to the tool."""
        base = os.path.dirname(self.tool_root)
        try:
            for entry in sorted(os.listdir(base)):
                candidate = os.path.join(base, entry)
                if os.path.isfile(os.path.join(candidate, "RPG_RT.ldb")):
                    self._set_source(candidate)
                    return
        except OSError:
            pass

    def _set_source(self, path: str) -> None:
        self.source.set(path)
        stem = path.rstrip("/\\")
        self.target.set(stem + "_MZ")
        self.game_dir.set(stem + "_Game")

    def _pick(self, title: str) -> str:
        return filedialog.askdirectory(title=title, parent=self.master)

    def _pick_source(self) -> None:
        chosen = self._pick("Ordner des RPG Maker 2000/2003-Spiels (mit RPG_RT.ldb)")
        if chosen:
            self._set_source(chosen)

    def _pick_target(self) -> None:
        chosen = self._pick("Zielordner für das MZ-Projekt")
        if chosen:
            self.target.set(chosen)

    def _pick_game(self) -> None:
        chosen = self._pick("Ordner für die spielbare Version")
        if chosen:
            self.game_dir.set(chosen)

    def _pick_template(self) -> None:
        chosen = self._pick("Ein RPG Maker MZ-Projekt als Engine-Vorlage")
        if chosen:
            self.template.set(chosen)

    def _pick_rtp(self) -> None:
        chosen = self._pick("RTP-Ordner von RPG Maker 2000/2003")
        if chosen:
            self.rtp.set(chosen)

    def _pick_soundfont(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Soundfont wählen", parent=self.master,
            filetypes=[("Soundfont", "*.sf2 *.sf3 *.dls"), ("Alle Dateien", "*")])
        if chosen:
            self.soundfont.set(chosen)

    def _play(self) -> None:
        exe = find_game_exe(self.game_dir.get())
        if not exe:
            messagebox.showinfo("Noch kein Spiel",
                                "Im Spielordner liegt noch keine Game.exe.\n"
                                "Lass den Schritt „Spiel bauen“ mitlaufen.")
            return
        if sys.platform.startswith("win"):
            subprocess.Popen([exe], cwd=os.path.dirname(exe))
            return
        wine = shutil.which("wine")
        if wine:
            subprocess.Popen([wine, exe], cwd=os.path.dirname(exe))
        else:
            messagebox.showinfo(
                "Wine fehlt",
                "Das gebaute Spiel ist eine Windows-Anwendung, wie sie RPG Maker "
                "MV/MZ erzeugt. Unter Linux startest du es mit Wine "
                "(z. B. „sudo apt install wine“).")

    # -- project and template info --------------------------------------------
    def _schedule_project(self) -> None:
        if getattr(self, "_project_job", None):
            self.after_cancel(self._project_job)
        self._project_job = self.after(400, self._refresh_project)

    def _refresh_project(self) -> None:
        self._project_job = None
        path, encoding = self.source.get().strip(), self.encoding.get()
        if not path:
            self._show_project({"ok": None})
            return
        self.project_status.config(text="lese Projekt …", fg=MUTED)
        self.project_details.config(text="")

        def work():
            try:
                info = describe_project(path, encoding)
            except Exception as exc:                        # noqa: BLE001
                info = {"ok": False, "error": f"Konnte das Projekt nicht lesen: {exc}"}
            self.messages.put(("project", path, info))
        threading.Thread(target=work, daemon=True).start()

    def _show_project(self, info: dict) -> None:
        if info.get("ok") is None:
            self.project_status.config(text="Wähle den Ordner eines RPG Maker 2000/2003-Spiels.",
                                       fg=MUTED)
            self.project_details.config(text="")
        elif not info["ok"]:
            self.project_status.config(text="✗  " + info["error"], fg=ERR)
            self.project_details.config(text="")
        else:
            self.project_status.config(text=f"✓  {info['title']}", fg=OK)
            self.project_details.config(
                text=f"{info['engine']}\n{info['maps']} Maps · {info['actors']} Helden · "
                     f"{info['events']} Common Events")

    def _refresh_template(self) -> None:
        text, ok = describe_template(self.template.get().strip())
        self.template_info.config(text=text, fg=MUTED if ok else WARN)

    # -- running -------------------------------------------------------------
    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        source = self.source.get().strip()
        if not os.path.isfile(os.path.join(source, "RPG_RT.ldb")):
            messagebox.showerror("Kein Spiel gewählt",
                                 "Bitte den Ordner eines RPG Maker 2000/2003-Spiels wählen "
                                 "(der Ordner mit der RPG_RT.ldb).")
            return
        if not self.target.get().strip():
            messagebox.showerror("Kein Ziel", "Bitte einen Zielordner für das Projekt wählen.")
            return
        if not any(var.get() for var in self.steps.values()):
            messagebox.showinfo("Nichts zu tun", "Bitte mindestens einen Schritt auswählen.")
            return
        if not self._preflight():
            return
        self._remember()
        self.log_lines.clear()
        self.counts = {"warn": 0, "err": 0}
        self._refilter()
        for name in self.step_icons:
            self._set_step(name, "wait" if self.steps[name].get() else "skip")
        self.summary.config(text="")
        self.progress["value"] = 0
        self.run_button.state(["disabled"])
        self.started_at = time.time()
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def _preflight(self) -> bool:
        """Warn about what will leave the result unplayable; the user may go on."""
        problems = []
        if self.steps["convert"].get():
            _, ok = describe_template(self.template.get().strip())
            if not ok:
                problems.append("Keine gültige Engine-Vorlage.\n" + TEMPLATE_HELP)
        if (self.steps["package"].get() and self.game_dir.get().strip()
                and runtime_missing()):
            problems.append("RPG Maker MZ wurde nicht gefunden (Ordner nwjs-win der "
                            "Installation). Ohne ihn kann „Spiel bauen“ keine "
                            "Game.exe erzeugen.")
        if not problems:
            return True
        return messagebox.askyesno(
            "Voraussetzung fehlt",
            "\n\n".join(problems) + "\n\nTrotzdem fortfahren? Das Projekt enthält "
            "dann nur data/ und img/ und lässt sich weder starten noch als Spiel bauen.",
            icon="warning", parent=self.master)

    def _remember(self) -> None:
        save_settings({
            "source": self.source.get(), "target": self.target.get(),
            "game_dir": self.game_dir.get(), "template": self.template.get(),
            "encoding": self.encoding.get(), "rtp": self.rtp.get(),
            "soundfont": self.soundfont.get(),
            "steps": {name: var.get() for name, var in self.steps.items()},
        })

    def _run(self) -> None:
        handler = QueueHandler(self.messages)
        handler.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        file_handler = None
        try:
            log_dir = os.path.join(self.tool_root, "log")
            os.makedirs(log_dir, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            file_handler = logging.FileHandler(os.path.join(log_dir, f"gui-{stamp}.log"),
                                               encoding="utf-8")
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)-7s %(name)-22s %(message)s", "%H:%M:%S"))
            root.addHandler(file_handler)
        except OSError:
            file_handler = None
        log = logging.getLogger("makerbridge")
        target = self.target.get().strip()
        failed = False
        done = 0
        for index, (name, label, _, _) in enumerate(STEPS):
            if not self.steps[name].get():
                continue
            self.messages.put(("step", name, "run", label, done))
            try:
                ok = self._run_step(name, target, log)
            except BaseException as exc:                    # noqa: BLE001 - UI boundary
                log.error("%s: %s", type(exc).__name__, exc)
                ok = False
            done += 1
            self.messages.put(("step", name, "done" if ok else "fail", label, done))
            if not ok:
                failed = True
                if name in ("convert", "verify"):
                    rest = [later for n, later, _, _ in STEPS[index + 1:]
                            if self.steps[n].get()]
                    if rest:
                        log.warning("„%s“ fehlgeschlagen, daher übersprungen: %s",
                                    label, ", ".join(rest))
                    break                                   # nothing sensible follows
        root.removeHandler(handler)
        if file_handler:
            root.removeHandler(file_handler)
            file_handler.close()
        self.messages.put(("finished", failed))

    def _run_step(self, name: str, target: str, log) -> bool:
        if name == "convert":
            rtp = [self.rtp.get().strip()] if self.rtp.get().strip() else None
            proj = project.load(self.source.get().strip(), self.encoding.get(), rtp=rtp)
            template = self.template.get().strip() or find_template(
                self.tool_root, exclude=(target,))
            convert_project(proj, target, log, overwrite=True, template=template or None)
            return True
        if name == "transcode":
            from .audio import transcode
            return not transcode(target, log, soundfont=self.soundfont.get().strip() or None)
        if name == "fixup":
            from .fixup import fixup
            return not fixup(target, log)
        if name == "verify":
            from .verify import verify
            return not verify(target, log)
        if name == "package":
            if not self.game_dir.get().strip():
                log.warning("kein Spielordner angegeben, „Spiel bauen“ übersprungen")
                return True
            from .package import build
            return not build(target, self.game_dir.get().strip(), log, overwrite=True)
        return True

    def _set_step(self, name: str, state: str) -> None:
        icon = self.step_icons[name]
        icon.config(text=STATE_ICON[state], fg=STATE_COLOUR[state])

    def _append(self, level: int, text: str) -> None:
        self.log_lines.append((level, text))
        if self.only_problems.get() and level < logging.WARNING:
            return
        tag = ("STEP" if level < 0 else "ERROR" if level >= logging.ERROR
               else "WARNING" if level >= logging.WARNING else "")
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _refilter(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        lines, self.log_lines = self.log_lines, []
        for level, text in lines:
            self._append(level, text)

    def _elapsed(self) -> str:
        seconds = int(time.time() - self.started_at)
        return f"{seconds // 60}:{seconds % 60:02d}"

    def _drain(self) -> None:
        try:
            while True:
                message = self.messages.get_nowait()
                kind = message[0]
                if kind == "log":
                    _, level, text = message
                    if level >= logging.ERROR:
                        self.counts["err"] += 1
                    elif level >= logging.WARNING:
                        self.counts["warn"] += 1
                    self._append(level, text)
                elif kind == "step":
                    _, name, state, label, done = message
                    self._set_step(name, state)
                    self.progress["value"] = done
                    if state == "run":
                        total = sum(1 for var in self.steps.values() if var.get())
                        self._current = f"Schritt {done + 1}/{total} · {label}"
                        self._append(-1, f"── {label} ──")
                elif kind == "project":
                    _, path, info = message
                    if path == self.source.get().strip():
                        self._show_project(info)
                elif kind == "finished":
                    self._finish(message[1])
        except queue.Empty:
            pass
        if self.worker and self.worker.is_alive():
            self.status.config(text=f"{getattr(self, '_current', '')} · {self._elapsed()}",
                               fg=TEXT)
        self.after(100, self._drain)

    def _finish(self, failed: bool) -> None:
        self.run_button.state(["!disabled"])
        self.progress["value"] = len(STEPS)
        warn, err = self.counts["warn"], self.counts["err"]
        counts = f"{warn} Warnung{'en' if warn != 1 else ''}, {err} Fehler"
        if failed:
            self.status.config(text=f"✗  Abgebrochen nach {self._elapsed()} · {counts}", fg=ERR)
        else:
            self.status.config(text=f"✓  Fertig in {self._elapsed()} · {counts}",
                               fg=WARN if warn else OK)
        self.summary.config(text=counts, fg=ERR if err else WARN if warn else OK)

    def _close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Konvertierung läuft",
                                       "Die Konvertierung läuft noch. Trotzdem beenden?"):
                return
        self._remember()
        self.master.destroy()


def dpi_aware() -> None:
    """Sharp text on Windows with display scaling (125 %, 150 %, ...): without
    this Windows draws the window small and stretches it, blurred."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def main() -> int:
    tool_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dpi_aware()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Kein Fenster möglich ({exc}). Unter Linux fehlt vielleicht python3-tk "
              "oder eine grafische Sitzung.", file=sys.stderr)
        return 1
    root.title("MakerBridge – RPG Maker 2000/2003 → MZ")
    root.configure(bg=BG)
    # Window size in "96 dpi pixels", grown with the screen's scaling.
    scale = max(1.0, float(root.tk.call("tk", "scaling")) / (96 / 72))
    width, height = int(1040 * scale), int(860 * scale)
    width = min(width, root.winfo_screenwidth() - 40)
    height = min(height, root.winfo_screenheight() - 80)
    root.geometry(f"{width}x{height}")
    root.minsize(int(860 * scale) if int(860 * scale) < width else width,
                 int(640 * scale) if int(640 * scale) < height else height)
    App(root, tool_root)
    root.mainloop()
    return 0
