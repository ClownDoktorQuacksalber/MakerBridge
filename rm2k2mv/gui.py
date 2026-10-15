"""A small Tkinter front end for the converter.

Pick a folder, pick a destination, press Convert.  The pipeline runs on a
worker thread and the log lands in the window as it happens, so a long run
over a few hundred maps still shows progress.
"""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import project
from .convert import convert_project, find_template

STEPS = [
    ("convert", "Daten, Tilesets und Grafiken konvertieren", True),
    ("transcode", "Audio nach OGG wandeln (braucht ffmpeg)", True),
    ("fixup", "Fehlende Dateien abfangen", True),
    ("verify", "Ergebnis pruefen", True),
    ("package", "Spielbares Game.exe bauen", True),
]


class QueueHandler(logging.Handler):
    def __init__(self, target: queue.Queue) -> None:
        super().__init__()
        self.target = target

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.target.put((record.levelno, self.format(record)))
        except Exception:
            pass


class App(ttk.Frame):
    def __init__(self, master: tk.Tk, tool_root: str) -> None:
        super().__init__(master, padding=12)
        self.tool_root = tool_root
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        self.messages: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None

        base = os.path.dirname(tool_root)
        self.source = tk.StringVar()
        self.target = tk.StringVar()
        self.game_dir = tk.StringVar()
        self.template = tk.StringVar(value=find_template(tool_root) or "")
        self.encoding = tk.StringVar(value=project.DEFAULT_ENCODING)
        self.steps = {name: tk.BooleanVar(value=on) for name, _, on in STEPS}

        row = 0
        row = self._path_row(row, "RM2k-Projekt", self.source,
                             "Ordner mit RPG_RT.ldb", self._pick_source)
        row = self._path_row(row, "MV-Ausgabe", self.target,
                             "Zielordner fuer das MV-Projekt", self._pick_target)
        row = self._path_row(row, "Spiel-Ordner", self.game_dir,
                             "Ordner fuer Game.exe (optional)", self._pick_game)
        row = self._path_row(row, "MV-Vorlage", self.template,
                             "bestehendes MV-Projekt, liefert js/ und index.html",
                             self._pick_template)

        options = ttk.LabelFrame(self, text="Schritte", padding=8)
        options.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(10, 4))
        for i, (name, label, _) in enumerate(STEPS):
            ttk.Checkbutton(options, text=label,
                            variable=self.steps[name]).grid(row=i, column=0,
                                                            sticky="w")
        ttk.Label(options, text="Textkodierung").grid(row=0, column=1,
                                                      sticky="e", padx=(24, 4))
        ttk.Combobox(options, textvariable=self.encoding, width=10,
                     values=["cp1252", "cp932", "cp949", "cp1251", "utf-8"]
                     ).grid(row=0, column=2, sticky="w")
        row += 1

        buttons = ttk.Frame(self)
        buttons.grid(row=row, column=0, columnspan=3, sticky="ew", pady=6)
        self.run_button = ttk.Button(buttons, text="Konvertieren",
                                     command=self._start)
        self.run_button.pack(side="left")
        ttk.Button(buttons, text="Ausgabe oeffnen",
                   command=self._open_target).pack(side="left", padx=6)
        ttk.Button(buttons, text="Spiel starten",
                   command=self._play).pack(side="left")
        self.progress = ttk.Progressbar(buttons, mode="indeterminate", length=160)
        self.progress.pack(side="right")
        row += 1

        self.log = tk.Text(self, height=20, wrap="none", background="#101014",
                           foreground="#d8d8d8", insertbackground="#d8d8d8")
        self.log.grid(row=row, column=0, columnspan=3, sticky="nsew")
        self.rowconfigure(row, weight=1)
        scroll = ttk.Scrollbar(self, command=self.log.yview)
        scroll.grid(row=row, column=3, sticky="ns")
        self.log["yscrollcommand"] = scroll.set
        self.log.tag_configure("WARNING", foreground="#e8c37a")
        self.log.tag_configure("ERROR", foreground="#f08a8a")

        self.status = ttk.Label(self, text="bereit")
        self.status.grid(row=row + 1, column=0, columnspan=3, sticky="w",
                         pady=(6, 0))

        self._guess_defaults(base)
        self.after(100, self._drain)

    # -- layout helpers -----------------------------------------------------
    def _path_row(self, row: int, label: str, var: tk.StringVar, hint: str,
                  command) -> int:
        ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=2)
        entry = ttk.Entry(self, textvariable=var)
        entry.grid(row=row, column=1, sticky="ew", padx=6)
        ttk.Button(self, text="...", width=3, command=command).grid(row=row,
                                                                    column=2)
        ttk.Label(self, text=hint, foreground="#777").grid(row=row + 1, column=1,
                                                           sticky="w", padx=6)
        return row + 2

    def _guess_defaults(self, base: str) -> None:
        """Offer the first RM2k project sitting next to the tool."""
        try:
            for entry in sorted(os.listdir(base)):
                candidate = os.path.join(base, entry)
                if os.path.isfile(os.path.join(candidate, "RPG_RT.ldb")):
                    self.source.set(candidate)
                    self.target.set(candidate + "_MV")
                    self.game_dir.set(candidate + "_Game")
                    break
        except OSError:
            pass

    def _pick_source(self) -> None:
        chosen = filedialog.askdirectory(title="RM2k-Projektordner waehlen")
        if not chosen:
            return
        self.source.set(chosen)
        if not os.path.isfile(os.path.join(chosen, "RPG_RT.ldb")):
            messagebox.showwarning(
                "Kein RM2k-Projekt",
                "In diesem Ordner liegt keine RPG_RT.ldb.")
        self.target.set(chosen.rstrip("/\\") + "_MV")
        self.game_dir.set(chosen.rstrip("/\\") + "_Game")

    def _pick_target(self) -> None:
        chosen = filedialog.askdirectory(title="Zielordner waehlen")
        if chosen:
            self.target.set(chosen)

    def _pick_game(self) -> None:
        chosen = filedialog.askdirectory(title="Ordner fuer Game.exe")
        if chosen:
            self.game_dir.set(chosen)

    def _pick_template(self) -> None:
        chosen = filedialog.askdirectory(title="MV-Projekt als Vorlage")
        if chosen:
            self.template.set(chosen)

    def _open_target(self) -> None:
        path = self.target.get()
        if os.path.isdir(path):
            os.startfile(path)                       # noqa: S606 - Windows shell
        else:
            messagebox.showinfo("Noch nichts da", "Der Zielordner existiert nicht.")

    def _play(self) -> None:
        exe = os.path.join(self.game_dir.get(), "Game.exe")
        if not os.path.isfile(exe):
            messagebox.showinfo("Kein Spiel",
                                "Game.exe wurde noch nicht gebaut.")
            return
        subprocess.Popen([exe], cwd=os.path.dirname(exe))

    # -- running ------------------------------------------------------------
    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        source = self.source.get()
        if not os.path.isfile(os.path.join(source, "RPG_RT.ldb")):
            messagebox.showerror("Kein RM2k-Projekt",
                                 "Bitte einen Ordner mit RPG_RT.ldb waehlen.")
            return
        self.log.delete("1.0", "end")
        self.run_button.state(["disabled"])
        self.progress.start(12)
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def _run(self) -> None:
        handler = QueueHandler(self.messages)
        handler.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        log = logging.getLogger("rm2k2mv")
        failed = False
        try:
            target = self.target.get()
            if self.steps["convert"].get():
                proj = project.load(self.source.get(), self.encoding.get())
                convert_project(proj, target, log, overwrite=True,
                                template=self.template.get() or None)
            if self.steps["transcode"].get():
                from .audio import transcode
                transcode(target, log)
            if self.steps["fixup"].get():
                from .fixup import fixup
                fixup(target, log)
            if self.steps["verify"].get():
                from .verify import verify
                if verify(target, log):
                    failed = True
            if self.steps["package"].get() and self.game_dir.get():
                from .package import build
                if build(target, self.game_dir.get(), log, overwrite=True):
                    failed = True
        except Exception as exc:                      # noqa: BLE001 - UI boundary
            log.error("%s: %s", type(exc).__name__, exc)
            failed = True
        finally:
            root.removeHandler(handler)
            self.messages.put((None, "fertig mit Fehlern" if failed else "fertig"))

    def _drain(self) -> None:
        try:
            while True:
                level, text = self.messages.get_nowait()
                if level is None:
                    self.progress.stop()
                    self.run_button.state(["!disabled"])
                    self.status.config(text=text)
                    continue
                tag = ("ERROR" if level >= logging.ERROR
                       else "WARNING" if level >= logging.WARNING else "")
                self.log.insert("end", text + "\n", tag)
                self.log.see("end")
        except queue.Empty:
            pass
        self.after(100, self._drain)


def main() -> int:
    tool_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root = tk.Tk()
    root.title("rm2k2mv - RPG Maker 2000 nach MV")
    root.geometry("900x720")
    try:
        root.call("ttk::style", "theme", "use", "vista")
    except tk.TclError:
        pass
    App(root, tool_root)
    root.mainloop()
    return 0
