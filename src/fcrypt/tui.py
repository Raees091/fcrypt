"""
fcrypt TUI: a terminal file browser to encrypt/decrypt files.

Run:  python -m fcrypt        (from inside the project dir)
  or: python fcrypt/app.py

Keys (browser):
  up/down, j/k   move          PgUp/PgDn   page
  enter / l      open dir / act on file
  backspace / h  go to parent dir
  e              encrypt selected file
  d              decrypt selected file
  .              toggle hidden files
  g / G          jump to top / bottom
  ~             go to home directory
  /              filter by typing (esc to clear)
  q              quit
"""

from __future__ import annotations

import curses
import os
import string
from curses import textpad

from . import core


# ----------------------------- helpers ------------------------------------

def human_size(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    f = float(n)
    for u in units:
        if f < 1024 or u == units[-1]:
            return f"{f:.0f} {u}" if u == "B" else f"{f:.1f} {u}"
        f /= 1024
    return f"{n} B"


KIND_BY_EXT = {
    "text": {".txt", ".md", ".csv", ".log", ".json", ".xml", ".yaml", ".yml",
             ".ini", ".cfg", ".py", ".js", ".ts", ".c", ".cpp", ".h", ".java",
             ".go", ".rs", ".sh", ".html", ".css"},
    "image": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg",
              ".tiff", ".ico"},
    "pdf": {".pdf"},
    "doc": {".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".ppt", ".pptx",
            ".pages", ".key", ".numbers"},
    "archive": {".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz"},
    "audio": {".mp3", ".wav", ".flac", ".ogg", ".m4a"},
    "video": {".mp4", ".mkv", ".mov", ".avi", ".webm"},
}


def file_kind(name: str) -> str:
    if name.endswith(core.ENC_SUFFIX):
        return "locked"
    ext = os.path.splitext(name)[1].lower()
    for kind, exts in KIND_BY_EXT.items():
        if ext in exts:
            return kind
    return "file"


ICON = {
    "dir": "[D]", "locked": "[#]", "text": "[T]", "image": "[I]",
    "pdf": "[P]", "doc": "[W]", "archive": "[A]", "audio": "[M]",
    "video": "[V]", "file": "[ ]", "up": "[^]",
}


# ----------------------------- app ----------------------------------------

class App:
    def __init__(self, start_dir: str):
        self.cwd = os.path.abspath(start_dir)
        self.entries: list[dict] = []
        self.idx = 0
        self.top = 0
        self.show_hidden = False
        self.filter = ""
        self.status = "Ready. Press ? for help, q to quit."
        self.status_attr = 0

    # ----- data -----
    def load(self):
        try:
            names = os.listdir(self.cwd)
        except OSError as e:
            self.set_status(f"Cannot read directory: {e}", error=True)
            names = []

        dirs, files = [], []
        for name in names:
            if not self.show_hidden and name.startswith("."):
                continue
            if self.filter and self.filter.lower() not in name.lower():
                continue
            full = os.path.join(self.cwd, name)
            try:
                isdir = os.path.isdir(full)
                size = 0 if isdir else os.path.getsize(full)
            except OSError:
                continue
            entry = {"name": name, "path": full, "isdir": isdir, "size": size}
            (dirs if isdir else files).append(entry)

        dirs.sort(key=lambda e: e["name"].lower())
        files.sort(key=lambda e: e["name"].lower())

        self.entries = []
        parent = os.path.dirname(self.cwd)
        if parent != self.cwd:
            self.entries.append({"name": "..", "path": parent, "isdir": True,
                                 "size": 0, "up": True})
        self.entries += dirs + files
        self.idx = min(self.idx, max(0, len(self.entries) - 1))
        # prefer starting on the first real entry, not ".."
        if self.idx == 0 and self.entries and self.entries[0].get("up") \
                and len(self.entries) > 1:
            self.idx = 1
        self.top = 0

    def set_status(self, msg: str, error=False, ok=False):
        self.status = msg
        if error:
            self.status_attr = curses.color_pair(5) | curses.A_BOLD
        elif ok:
            self.status_attr = curses.color_pair(4) | curses.A_BOLD
        else:
            self.status_attr = curses.color_pair(6)

    @property
    def current(self):
        if 0 <= self.idx < len(self.entries):
            return self.entries[self.idx]
        return None

    # ----- drawing -----
    @staticmethod
    def _safe_addstr(scr, y, x, text, attr=0):
        """addstr that never raises on the bottom-right corner / overflow."""
        h, w = scr.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return
        # leave the very last cell on the last row untouched
        avail = w - x
        if y == h - 1:
            avail -= 1
        if avail <= 0:
            return
        try:
            scr.addstr(y, x, text[:avail], attr)
        except curses.error:
            pass

    def draw(self, scr):
        scr.erase()
        h, w = scr.getmaxyx()

        # header
        title = " fcrypt  -  secure file encryption "
        self._safe_addstr(scr, 0, 0, title.ljust(w),
                          curses.color_pair(1) | curses.A_BOLD)

        path_line = " " + self.cwd
        if self.filter:
            path_line += f"   (filter: {self.filter})"
        self._safe_addstr(scr, 1, 0, path_line.ljust(w), curses.color_pair(2))

        list_top = 3
        list_h = h - list_top - 2
        if list_h < 1:
            list_h = 1

        if self.idx < self.top:
            self.top = self.idx
        elif self.idx >= self.top + list_h:
            self.top = self.idx - list_h + 1

        visible = self.entries[self.top : self.top + list_h]
        for i, e in enumerate(visible):
            row = list_top + i
            real = self.top + i
            selected = real == self.idx

            if e.get("up"):
                kind = "up"
            elif e["isdir"]:
                kind = "dir"
            else:
                kind = file_kind(e["name"])

            icon = ICON.get(kind, "[ ]")
            name = e["name"] + ("/" if e["isdir"] and not e.get("up") else "")
            size = "" if e["isdir"] else human_size(e["size"])

            line = f" {icon} {name}"
            maxname = w - 14
            if len(line) > maxname:
                line = line[: maxname - 1] + "~"
            line = line.ljust(w - 12)
            line += size.rjust(11) + " "
            line = line[:w]

            attr = self._kind_attr(kind)
            if selected:
                attr = curses.color_pair(3) | curses.A_BOLD
            self._safe_addstr(scr, row, 0, line, attr)

        # scroll indicator
        if len(self.entries) > list_h:
            info = f"{self.idx+1}/{len(self.entries)}"
            self._safe_addstr(scr, list_top - 1, max(0, w - len(info) - 1),
                              info, curses.color_pair(2))

        # help line
        help_line = (" e encrypt  d decrypt  enter open  bksp up  "
                     ". hidden  / filter  ? help  q quit ")
        self._safe_addstr(scr, h - 2, 0, help_line.ljust(w), curses.color_pair(2))

        # status
        self._safe_addstr(scr, h - 1, 0, (" " + self.status).ljust(w),
                          self.status_attr)

        scr.noutrefresh()
        curses.doupdate()

    def _kind_attr(self, kind):
        if kind in ("dir", "up"):
            return curses.color_pair(7) | curses.A_BOLD
        if kind == "locked":
            return curses.color_pair(4) | curses.A_BOLD
        return curses.A_NORMAL

    # ----- prompts -----
    def prompt(self, scr, label: str, hidden=False) -> str | None:
        h, w = scr.getmaxyx()
        curses.curs_set(1)
        win = curses.newwin(3, w, h - 3, 0)
        win.attron(curses.color_pair(1))
        win.addstr(0, 0, (" " + label).ljust(w)[:w])
        win.attroff(curses.color_pair(1))
        win.refresh()

        buf = []
        win.move(1, 1)
        while True:
            ch = win.getch()
            if ch in (10, 13):  # enter
                break
            if ch == 27:  # esc
                curses.curs_set(0)
                return None
            if ch in (curses.KEY_BACKSPACE, 127, 8):
                if buf:
                    buf.pop()
            elif 32 <= ch <= 126:
                buf.append(chr(ch))
            else:
                continue
            shown = ("*" * len(buf)) if hidden else "".join(buf)
            win.move(1, 0)
            win.clrtoeol()
            win.addstr(1, 1, shown[: w - 2])
            win.refresh()
        curses.curs_set(0)
        return "".join(buf)

    def confirm(self, scr, question: str) -> bool:
        ans = self.prompt(scr, question + " (y/N): ")
        return bool(ans) and ans.strip().lower() in ("y", "yes")

    # ----- actions -----
    def do_encrypt(self, scr):
        e = self.current
        if not e or e["isdir"]:
            self.set_status("Select a file to encrypt.", error=True)
            return
        if e["name"].endswith(core.ENC_SUFFIX):
            self.set_status("That file is already encrypted.", error=True)
            return

        pw1 = self.prompt(scr, f"Password to encrypt '{e['name']}':", hidden=True)
        if pw1 is None:
            self.set_status("Encryption cancelled.")
            return
        if not pw1:
            self.set_status("Empty password not allowed.", error=True)
            return
        pw2 = self.prompt(scr, "Confirm password:", hidden=True)
        if pw2 is None:
            self.set_status("Encryption cancelled.")
            return
        if pw1 != pw2:
            self.set_status("Passwords do not match.", error=True)
            return

        out = e["path"] + core.ENC_SUFFIX
        overwrite = False
        if os.path.exists(out):
            if not self.confirm(scr, f"{os.path.basename(out)} exists. Overwrite?"):
                self.set_status("Encryption cancelled.")
                return
            overwrite = True

        try:
            res = core.encrypt_file(e["path"], pw1, overwrite=overwrite)
        except core.FcryptError as err:
            self.set_status(str(err), error=True)
            return
        self.load()
        self.set_status(
            f"Encrypted -> {os.path.basename(res.out_path)} "
            f"({human_size(res.in_bytes)} -> {human_size(res.out_bytes)})",
            ok=True,
        )

    def do_decrypt(self, scr):
        e = self.current
        if not e or e["isdir"]:
            self.set_status("Select a file to decrypt.", error=True)
            return
        if not core.is_encrypted_file(e["path"]):
            self.set_status("Not an fcrypt file (no FCRYPT header).", error=True)
            return

        pw = self.prompt(scr, f"Password to decrypt '{e['name']}':", hidden=True)
        if pw is None:
            self.set_status("Decryption cancelled.")
            return

        try:
            res = core.decrypt_file(e["path"], pw)
        except core.WrongPasswordError:
            self.set_status("Wrong password or corrupted file.", error=True)
            return
        except core.FcryptError as err:
            self.set_status(str(err), error=True)
            return
        self.load()
        self.set_status(
            f"Decrypted -> {os.path.basename(res.out_path)} "
            f"(original: {res.original_name})",
            ok=True,
        )

    def show_help(self, scr):
        h, w = scr.getmaxyx()
        lines = [
            "  fcrypt - help",
            "",
            "  Navigation",
            "    up/down or j/k   move selection",
            "    PgUp / PgDn      page up / down",
            "    g / G            jump to top / bottom",
            "    enter / l        open directory",
            "    backspace / h    go to parent directory",
            "    ~                go to home directory",
            "",
            "  Actions",
            "    e                encrypt the selected file",
            "    d                decrypt the selected file",
            "    .                toggle hidden files",
            "    /                filter list (type, enter to apply)",
            "    r                refresh listing",
            "    q                quit",
            "",
            "  Encryption: AES-256-GCM with scrypt key derivation.",
            "  Encrypted files get a .fcr extension and store the",
            "  original filename securely inside the container.",
            "",
            "  Press any key to return...",
        ]
        bh = min(len(lines) + 2, h)
        bw = min(max(len(l) for l in lines) + 4, w)
        y0 = (h - bh) // 2
        x0 = (w - bw) // 2
        win = curses.newwin(bh, bw, y0, x0)
        win.box()
        for i, line in enumerate(lines[: bh - 2]):
            win.attron(curses.color_pair(1) if i == 0 else curses.A_NORMAL)
            win.addstr(i + 1, 1, line[: bw - 2])
            win.attroff(curses.color_pair(1) if i == 0 else curses.A_NORMAL)
        win.refresh()
        win.getch()

    def filter_mode(self, scr):
        res = self.prompt(scr, "Filter (empty to clear):")
        if res is None:
            return
        self.filter = res.strip()
        self.idx = 0
        self.load()
        if self.filter:
            self.set_status(f"Filtering by '{self.filter}'. Press / then enter to clear.")
        else:
            self.set_status("Filter cleared.")

    # ----- main loop -----
    def run(self, scr):
        curses.curs_set(0)
        init_colors()
        self.load()
        while True:
            self.draw(scr)
            ch = scr.getch()

            if ch in (ord("q"), ord("Q")):
                break
            elif ch in (curses.KEY_DOWN, ord("j")):
                self.idx = min(self.idx + 1, len(self.entries) - 1)
            elif ch in (curses.KEY_UP, ord("k")):
                self.idx = max(self.idx - 1, 0)
            elif ch == curses.KEY_NPAGE:
                self.idx = min(self.idx + 10, len(self.entries) - 1)
            elif ch == curses.KEY_PPAGE:
                self.idx = max(self.idx - 10, 0)
            elif ch == ord("g"):
                self.idx = 0
            elif ch == ord("G"):
                self.idx = len(self.entries) - 1
            elif ch in (curses.KEY_ENTER, 10, 13, ord("l"), curses.KEY_RIGHT):
                e = self.current
                if e and e["isdir"]:
                    self.cwd = e["path"]
                    self.idx = 0
                    self.filter = ""
                    self.load()
            elif ch in (curses.KEY_BACKSPACE, 127, 8, ord("h"), curses.KEY_LEFT):
                parent = os.path.dirname(self.cwd)
                if parent != self.cwd:
                    self.cwd = parent
                    self.idx = 0
                    self.filter = ""
                    self.load()
            elif ch == ord("~"):
                self.cwd = os.path.expanduser("~")
                self.idx = 0
                self.filter = ""
                self.load()
            elif ch == ord("."):
                self.show_hidden = not self.show_hidden
                self.load()
                self.set_status(f"Hidden files: {'on' if self.show_hidden else 'off'}")
            elif ch in (ord("e"), ord("E")):
                self.do_encrypt(scr)
            elif ch in (ord("d"), ord("D")):
                self.do_decrypt(scr)
            elif ch == ord("/"):
                self.filter_mode(scr)
            elif ch in (ord("r"), ord("R")):
                self.load()
                self.set_status("Refreshed.")
            elif ch in (ord("?"),):
                self.show_help(scr)
            elif ch == curses.KEY_RESIZE:
                pass


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)    # header
    curses.init_pair(2, curses.COLOR_CYAN, -1)                    # path/help
    curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_GREEN)   # selection
    curses.init_pair(4, curses.COLOR_GREEN, -1)                   # ok / locked
    curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_RED)     # error
    curses.init_pair(6, curses.COLOR_WHITE, -1)                   # status
    curses.init_pair(7, curses.COLOR_BLUE, -1)                    # dirs


def main(start_dir: str | None = None):
    start = start_dir or os.getcwd()
    app = App(start)
    curses.wrapper(app.run)
