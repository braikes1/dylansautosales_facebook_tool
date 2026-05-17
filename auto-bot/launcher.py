"""
Auto Bot Launcher — DAS Facebook Tool
Double-click this (or the compiled AutoBot.exe) to:
  1. Enter/save your OpenAI API key on first run.
  2. Start the local FastAPI server in the background.
  3. See step-by-step instructions for loading the Chrome extension.
"""
import os
import sys
import json
import shutil
import asyncio
import threading
import webbrowser
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

# ── Windows asyncio fix — must happen before ANY uvicorn/anyio import ─────────
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ── resource / install paths ──────────────────────────────────────────────────

def _resource(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


INSTALL_DIR = os.path.join(os.path.expanduser("~"), "AutoBot")
EXT_DIR     = os.path.join(INSTALL_DIR, "extension")
CONFIG_FILE = os.path.join(INSTALL_DIR, "config.json")

# ── palette ───────────────────────────────────────────────────────────────────
BG      = "#0f172a"
PANEL   = "#1e293b"
BORDER  = "#334155"
ACCENT  = "#3b82f6"
RED     = "#ef4444"
GREEN   = "#22c55e"
TEXT    = "#f1f5f9"
MUTED   = "#94a3b8"
LINK    = "#60a5fa"

# ── config helpers ────────────────────────────────────────────────────────────

def _load_config() -> dict:
    try:
        with open(CONFIG_FILE) as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_config(cfg: dict) -> None:
    os.makedirs(INSTALL_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as fh:
        json.dump(cfg, fh, indent=2)


# ── server state ──────────────────────────────────────────────────────────────
_server_started = False


def _launch_server(api_key: str) -> None:
    global _server_started
    if _server_started:
        return

    os.environ["OPENAI_API_KEY"] = api_key

    api_dir = _resource("api")
    if api_dir not in sys.path:
        sys.path.insert(0, api_dir)

    try:
        import uvicorn
        import fastapi
        import openai
        import bs4
        import requests as _req
        import pydantic
        import starlette
        import anyio
        import httpx
        from main import app

        def _run():
            uvicorn.run(app, host="127.0.0.1", port=8001, log_level="error")

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        # Wait up to 8 seconds for the server to actually bind to the port
        import time
        import urllib.request
        for _ in range(16):
            time.sleep(0.5)
            try:
                urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=1)
                _server_started = True
                return
            except Exception:
                pass

        # If we get here the server never came up
        messagebox.showerror(
            "Server Error",
            "The API server failed to start.\n\n"
            "Please close this app and try again.\n"
            "If the problem persists, restart your computer."
        )

    except Exception as exc:
        messagebox.showerror(
            "Server Error",
            f"Failed to start the API server:\n\n{exc}\n\n"
            "Make sure your OpenAI API key is correct.",
        )


# ── widget helpers ────────────────────────────────────────────────────────────

def _lbl(parent, text, size=10, color=TEXT, bold=False, wrap=520, anchor="w", pady=0):
    font = ("Segoe UI", size, "bold" if bold else "normal")
    w = tk.Label(parent, text=text, font=font, bg=BG, fg=color,
                 wraplength=wrap, justify="left", anchor=anchor)
    w.pack(anchor="w", pady=pady)
    return w


def _sep(parent):
    tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=10)


def _btn(parent, text, cmd, primary=False, side="left", padx=0, pady=6):
    bg = ACCENT if primary else PANEL
    b = tk.Button(parent, text=text, command=cmd,
                  bg=bg, fg=TEXT, activebackground="#2563eb" if primary else BORDER,
                  activeforeground=TEXT, font=("Segoe UI", 10, "bold" if primary else "normal"),
                  relief="flat", cursor="hand2", padx=18, pady=pady)
    b.pack(side=side, padx=padx)
    return b


# ── main application ──────────────────────────────────────────────────────────

class AutoBotApp:

    def __init__(self) -> None:
        self.config: dict = _load_config()
        self._sync_extension()

        self.root = tk.Tk()
        self.root.title("Auto Bot — DAS Facebook Tool")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self._frame: tk.Frame | None = None

        if self.config.get("api_key"):
            self._page_main()
        else:
            self._page_setup()

        self.root.mainloop()

    def _sync_extension(self) -> None:
        src = _resource("extension")
        if not os.path.isdir(src):
            return
        if os.path.isdir(EXT_DIR):
            shutil.rmtree(EXT_DIR)
        shutil.copytree(src, EXT_DIR)

    def _clear(self, w: int = 560, h: int = 500) -> tk.Frame:
        if self._frame:
            self._frame.destroy()
        self.root.geometry(f"{w}x{h}")
        self._center()
        f = tk.Frame(self.root, bg=BG)
        f.pack(fill="both", expand=True, padx=36, pady=28)
        self._frame = f
        return f

    def _center(self) -> None:
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        ww = self.root.winfo_reqwidth()
        wh = self.root.winfo_reqheight()
        self.root.geometry(f"+{(sw - ww) // 2}+{(sh - wh) // 2}")

    def _page_setup(self) -> None:
        f = self._clear(540, 430)

        row = tk.Frame(f, bg=BG)
        row.pack(anchor="w", pady=(0, 6))
        tk.Label(row, text="🤖", font=("Segoe UI", 28), bg=BG).pack(side="left")
        tk.Label(row, text="  Auto Bot", font=("Segoe UI", 22, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Label(row, text="  DAS Facebook Tool", font=("Segoe UI", 12),
                 bg=BG, fg=MUTED).pack(side="left", padx=(4, 0))

        _sep(f)
        _lbl(f, "Enter your OpenAI API Key", size=12, bold=True, pady=(4, 2))
        _lbl(f, "Your key is stored only on this computer and never shared.",
             color=MUTED, pady=(0, 10))

        ef = tk.Frame(f, bg=BG)
        ef.pack(anchor="w", fill="x", pady=(0, 4))

        self._key_var = tk.StringVar()
        entry = tk.Entry(ef, textvariable=self._key_var, show="•",
                         font=("Consolas", 10), width=46,
                         bg=PANEL, fg=TEXT, insertbackground=TEXT,
                         relief="flat", bd=10)
        entry.pack(side="left")
        entry.focus_set()

        show_var = tk.BooleanVar()
        def _toggle():
            entry.config(show="" if show_var.get() else "•")
        tk.Checkbutton(ef, text="Show", variable=show_var, command=_toggle,
                       bg=BG, fg=MUTED, selectcolor=PANEL,
                       activebackground=BG, font=("Segoe UI", 9)).pack(side="left", padx=8)

        link = tk.Label(f, text="→  Get your key at platform.openai.com/api-keys",
                        font=("Segoe UI", 9), bg=BG, fg=LINK, cursor="hand2")
        link.pack(anchor="w", pady=(0, 20))
        link.bind("<Button-1>", lambda _: webbrowser.open("https://platform.openai.com/api-keys"))

        def _save():
            key = self._key_var.get().strip()
            if not key.startswith("sk-"):
                messagebox.showerror(
                    "Invalid Key",
                    "Please enter a valid OpenAI API key.\nIt should start with  sk-")
                return
            self.config["api_key"] = key
            _save_config(self.config)
            self._page_starting()

        _sep(f)
        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(anchor="w")
        _btn(btn_row, "  Save & Start Server  ", _save, primary=True)
        self.root.bind("<Return>", lambda _: _save())

    def _page_starting(self) -> None:
        f = self._clear(440, 230)
        _lbl(f, "Starting server…", size=16, bold=True, pady=(30, 8))
        _lbl(f, "Launching the local API server. Please wait.", color=MUTED)
        bar = ttk.Progressbar(f, mode="indeterminate", length=360)
        bar.pack(pady=18)
        bar.start(12)

        def _do():
            _launch_server(self.config["api_key"])
            self.root.after(0, self._page_main)

        threading.Thread(target=_do, daemon=True).start()

    def _page_main(self) -> None:
        if not _server_started:
            _launch_server(self.config.get("api_key", ""))

        f = self._clear(580, 530)

        hrow = tk.Frame(f, bg=BG)
        hrow.pack(fill="x", pady=(0, 4))
        tk.Label(hrow, text="🤖  Auto Bot", font=("Segoe UI", 18, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        dot_col  = GREEN if _server_started else RED
        dot_text = "●  Server running  ·  http://127.0.0.1:8001" if _server_started \
                   else "●  Server not running"
        tk.Label(hrow, text=dot_text, font=("Segoe UI", 9),
                 bg=BG, fg=dot_col).pack(side="left", padx=16)

        _sep(f)

        _lbl(f, "Install the Chrome Extension", size=12, bold=True, pady=(0, 4))
        _lbl(f, "Do this once on each computer, then you're all set.",
             color=MUTED, pady=(0, 8))

        steps_box = tk.Frame(f, bg=PANEL, bd=0)
        steps_box.pack(fill="x", pady=(0, 12))
        steps_text = (
            "  1.  Open Google Chrome\n"
            "  2.  In the address bar type:   chrome://extensions   and press Enter\n"
            "  3.  Turn on  Developer Mode  (toggle in the top-right corner)\n"
            "  4.  Click  Load unpacked\n"
            "  5.  Navigate to the folder shown below and click  Select Folder"
        )
        tk.Label(steps_box, text=steps_text, font=("Segoe UI", 10),
                 bg=PANEL, fg=TEXT, justify="left",
                 padx=16, pady=14).pack(anchor="w")

        _lbl(f, "Extension folder:", bold=True, pady=(0, 2))
        prow = tk.Frame(f, bg=BG)
        prow.pack(fill="x", pady=(0, 14))

        path_entry = tk.Entry(prow, font=("Consolas", 9), width=48,
                              bg=PANEL, fg=MUTED, relief="flat", bd=8,
                              readonlybackground=PANEL)
        path_entry.pack(side="left")
        path_entry.insert(0, EXT_DIR)
        path_entry.config(state="readonly")

        copy_btn = _btn(prow, "Copy Path", lambda: None, side="left", padx=(6, 4))

        def _copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(EXT_DIR)
            copy_btn.config(text="Copied ✓")
            self.root.after(2000, lambda: copy_btn.config(text="Copy Path"))

        copy_btn.config(command=_copy)
        _btn(prow, "Open Folder", lambda: os.startfile(INSTALL_DIR), side="left", padx=(0, 0))

        _sep(f)
        brow = tk.Frame(f, bg=BG)
        brow.pack(anchor="w")

        _btn(brow, "Open chrome://extensions",
             lambda: subprocess.Popen(["start", "chrome", "--new-tab",
                                       "chrome://extensions"], shell=True),
             primary=True, side="left", padx=(0, 8))

        def _change_key():
            if messagebox.askyesno("Change API Key",
                                   "This will require you to re-enter your "
                                   "OpenAI API key and restart the server.\n\nContinue?"):
                self.config.pop("api_key", None)
                _save_config(self.config)
                self._page_setup()

        _btn(brow, "Change API Key", _change_key, side="left", padx=(0, 8))

        note = tk.Label(f,
            text="Keep this window open while using Auto Bot in Chrome.",
            font=("Segoe UI", 9, "italic"), bg=BG, fg=MUTED)
        note.pack(anchor="w", pady=(14, 0))


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    AutoBotApp()
