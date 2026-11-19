# gomoku_ui.py
"""
Интерфейс «Крестики-нолики: Пять в ряд» — бесконечное поле на canvas.

Запуск:
    python play.py
или
    python gomoku.py

Отладочные инструменты временно расположены в боковой панели на месте
кнопок выбора силы ИИ. Подробное назначение каждой кнопки — в окне
«Правила игры», раздел «Кнопки и отладка».
"""

import json
import os
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog

from gomoku import (
    Board, PLAYER_X, PLAYER_O, EMPTY, WIN_LENGTH,
    player_name, get_best_move, DEBUG_LOG,
)

# ---------------------------------------------------------------- палитра

BG        = "#e8edf3"
BG_DEEP   = "#dbe3ec"
PANEL     = "#ffffff"
PANEL_HI  = "#f5f7fa"
SURFACE   = "#f0f3f7"
SURF_HI   = "#e4e9f0"
LINE      = "#d6dde7"
LINE_HI   = "#b8c3d1"
TEXT      = "#131a24"
MUTED     = "#5d6877"
DIM       = "#8994a4"
ACCENT    = "#4338ca"
ACCENT_H  = "#3730a3"
ACCENT_S  = "#eef0ff"
X_COLOR   = "#2563eb"
O_COLOR   = "#2e8b57"
LAST_C    = "#d32f2f"
WIN_C     = "#0f9a68"
WARN      = "#b45309"
INFO      = "#0e7490"
DANGER    = "#b23a2e"
BOARD_A   = "#fbfcff"
BOARD_B   = "#edf2f8"
GRID_AX   = "#96a6b1"
GRID_5    = "#a5b5be"
GRID_1    = "#bfcbd3"
BANNER_BG = "#f7c948"
BANNER_BR = "#8a4b2f"
BANNER_T  = "#6b2737"

BASE      = 46
MIN_ZOOM  = 0.55
MAX_ZOOM  = 2.35
STATE_FILE = "gomoku_ui_state.json"


def other(p):
    return PLAYER_O if p == PLAYER_X else PLAYER_X


def mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    a = c1.lstrip("#"); b = c2.lstrip("#")
    r = round(int(a[0:2], 16) * (1 - t) + int(b[0:2], 16) * t)
    g = round(int(a[2:4], 16) * (1 - t) + int(b[2:4], 16) * t)
    bl = round(int(a[4:6], 16) * (1 - t) + int(b[4:6], 16) * t)
    return "#%02x%02x%02x" % (r, g, bl)


def round_rect(cv, x0, y0, x1, y1, r, **kw):
    r = max(0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    pts = [
        x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
        x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
        x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
    ]
    return cv.create_polygon(pts, smooth=True, splinesteps=18, **kw)


def plural(n, one, few, many):
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return few
    return many


def coord(v):
    return "−" + str(abs(v)) if v < 0 else str(v)


# ---------------------------------------------------------------- кнопки

class Chip(tk.Canvas):
    """Округлая кнопка/пилюля с полным контролем цвета и откликом на наведение."""

    STYLES = {
        "primary":   (ACCENT,  "#ffffff", ACCENT_H, ACCENT_H),
        "secondary": (SURFACE, TEXT,      SURF_HI,  LINE_HI),
        "ghost":     (PANEL,   MUTED,     PANEL_HI, LINE),
        "danger":    (DANGER,  "#ffffff", "#9c3126", "#9c3126"),
        "toggle":    (SURFACE, MUTED,     SURF_HI,  LINE_HI),
        "toggle_on": (ACCENT,  "#ffffff", ACCENT_H, ACCENT_H),
    }

    def __init__(self, master, text, command=None, kind="secondary",
                 height=38, radius=10, font=None, parent_bg=None):
        self.pbg = parent_bg or master.cget("bg")
        super().__init__(master, height=height, bg=self.pbg,
                         highlightthickness=0, bd=0, takefocus=0)
        self.text = text
        self.command = command
        self.kind = kind
        self.radius = radius
        self.font = font
        self.enabled = True
        self._hover = False
        self._press = False
        self._h = height
        self.bind("<Configure>", lambda e: self._redraw())
        if command is not None:
            self.configure(cursor="hand2")
            self.bind("<Enter>", self._enter)
            self.bind("<Leave>", self._leave)
            self.bind("<ButtonPress-1>", self._down)
            self.bind("<ButtonRelease-1>", self._up)
        self._redraw()

    def _enter(self, _):
        if self.enabled:
            self._hover = True
            self._redraw()

    def _leave(self, _):
        self._hover = False
        self._press = False
        self._redraw()

    def _down(self, _):
        if self.enabled:
            self._press = True
            self._redraw()

    def _up(self, e):
        was = self._press
        self._press = False
        self._redraw()
        if was and self.enabled and self.command and 0 <= e.x <= self.winfo_width() \
                and 0 <= e.y <= self.winfo_height():
            self.command()

    def set_text(self, text):
        if text != self.text:
            self.text = text
            self._redraw()

    def set_kind(self, kind):
        if kind != self.kind:
            self.kind = kind
            self._redraw()

    def set_enabled(self, on):
        on = bool(on)
        if on != self.enabled:
            self.enabled = on
            self._hover = False
            self._press = False
            self.configure(cursor="hand2" if (on and self.command) else "")
            self._redraw()

    def _redraw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self._h
        if w <= 1:
            w = max(90, len(self.text) * 8 + 26)
        bg, fg, hov, br = self.STYLES.get(self.kind, self.STYLES["secondary"])
        if not self.enabled:
            bg, fg, br = SURF_HI, DIM, LINE
        elif self._press:
            bg, br = hov, hov
        elif self._hover:
            bg = hov
        round_rect(self, 1, 1, w - 1, h - 1, self.radius,
                   fill=bg, outline=br, width=1)
        dy = 1 if (self._press and self.enabled) else 0
        self.create_text(w / 2, h / 2 + dy, text=self.text, fill=fg,
                         font=self.font, anchor="center")


class PlayerChip(tk.Canvas):
    """Овал игрока: символ знака + имя. Клик до старта меняет, кто играет X."""

    def __init__(self, master, mark, on_click, font_sym, font_name, parent_bg=None):
        super().__init__(master, height=46, bg=parent_bg or master.cget("bg"),
                         highlightthickness=0, bd=0, takefocus=0)
        self.mark = mark
        self.on_click = on_click
        self.font_sym = font_sym
        self.font_name = font_name
        self.name = ""
        self.active = False
        self.editable = True
        self._hover = False
        self.configure(cursor="hand2")
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonRelease-1>", self._click)
        self._redraw()

    def _enter(self, _):
        if self.editable:
            self._hover = True
            self._redraw()

    def _leave(self, _):
        self._hover = False
        self._redraw()

    def _click(self, _):
        if self.editable and self.on_click:
            self.on_click()

    def update(self, name, active, editable):
        self.name = name
        self.active = active
        self.editable = editable
        self.configure(cursor="hand2" if editable else "")
        self._redraw()

    def _redraw(self):
        self.delete("all")
        w = self.winfo_width()
        if w <= 1:
            w = 150
        h = 46
        if self.active:
            bg, br = ACCENT_S, ACCENT
        elif self._hover and self.editable:
            bg, br = PANEL_HI, LINE_HI
        else:
            bg, br = PANEL, LINE
        round_rect(self, 1, 1, w - 1, h - 1, 13, fill=bg, outline=br, width=1)
        col = X_COLOR if self.mark == PLAYER_X else O_COLOR
        self.create_text(18, h / 2, text=player_name(self.mark), fill=col,
                         font=self.font_sym, anchor="w")
        name = self.name
        avail = w - 46
        while name and self.font_name.measure(name) > avail:
            name = name[:-1]
        if name != self.name:
            name = name[:-1] + "…" if len(name) > 1 else "…"
        self.create_text(40, h / 2, text=name, fill=TEXT,
                         font=self.font_name, anchor="w")
        if self.active:
            self.create_oval(w - 15, h / 2 - 3, w - 9, h / 2 + 3,
                             fill=col, outline="")


# ---------------------------------------------------------------- окно

class GomokuApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Крестики-нолики: Пять в ряд")
        self.root.configure(bg=BG)
        self.root.geometry("1240x820")
        self.root.minsize(940, 620)

        self.F_TITLE = tkfont.Font(family="Segoe UI", size=17, weight="bold")
        self.F_SUB   = tkfont.Font(family="Segoe UI", size=9)
        self.F_UI    = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.F_SMALL = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        self.F_TINY  = tkfont.Font(family="Segoe UI", size=8)
        self.F_STAT  = tkfont.Font(family="Segoe UI", size=13, weight="bold")
        self.F_EYE   = tkfont.Font(family="Segoe UI", size=8, weight="bold")
        self.F_SYM   = tkfont.Font(family="Segoe UI", size=14, weight="bold")
        self.F_NAME  = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self.F_BAN   = tkfont.Font(family="Segoe UI", size=22, weight="bold")
        self.F_BANS  = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self.F_MONO  = tkfont.Font(family="Consolas", size=9)
        self.F_MONOB = tkfont.Font(family="Consolas", size=10, weight="bold")
        self.F_BODY  = tkfont.Font(family="Segoe UI", size=10)
        self.F_H3    = tkfont.Font(family="Segoe UI", size=11, weight="bold")

        self.board = Board()
        self.mode = "ai"
        self.human_is_x = True
        self.pvp_swap = False
        self.started = False
        self.finished = False
        self.result = None
        self.win_line = []
        self.win_start = 0.0
        self.turn = PLAYER_X
        self.thinking = False
        self.gen = 0
        self.last_move = None
        self.redo_stack = []
        self.move_records = []
        self.game_log = []
        self.last_analysis = ""
        self.status_note = ""
        self.records = {}
        self.record_snapshot = None
        self.anim = {}
        self.view = {"x": 0.0, "y": 0.0, "zoom": 1.0}
        self.view_anim = None
        self.hover = None
        self.drag = None
        self.width = 0
        self.height = 0
        self._raf = False
        self._hud_hits = []
        self._hint_on = True
        self._help_win = None
        self._an_win = None
        self._rec_win = None
        self._reset_armed = False

        self._load_state()
        self._build()
        self._sync()
        self.root.after(60, self._first_layout)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------- состояние

    @property
    def human_mark(self):
        if self.mode == "pvp":
            return PLAYER_X
        return PLAYER_X if self.human_is_x else PLAYER_O

    @property
    def ai_mark(self):
        return other(self.human_mark)

    def name_of(self, mark):
        if self.mode == "pvp":
            first = "Игрок 2" if self.pvp_swap else "Игрок 1"
            second = "Игрок 1" if self.pvp_swap else "Игрок 2"
            return first if mark == PLAYER_X else second
        return "Вы" if mark == self.human_mark else "Компьютер"

    def x_count(self):
        return sum(1 for _, _, p in self.board.move_history if p == PLAYER_X)

    def _state_path(self):
        try:
            return os.path.join(os.path.dirname(os.path.abspath(__file__)), STATE_FILE)
        except Exception:
            return STATE_FILE

    def _load_state(self):
        try:
            with open(self._state_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            self.mode = "pvp" if data.get("mode") == "pvp" else "ai"
            self.human_is_x = bool(data.get("human_is_x", True))
            self.pvp_swap = bool(data.get("pvp_swap", False))
            rec = data.get("records") or {}
            if isinstance(rec, dict):
                for k, v in rec.items():
                    if isinstance(v, dict):
                        self.records[str(k)] = {
                            "wins": max(0, int(v.get("wins", 0))),
                            "losses": max(0, int(v.get("losses", 0))),
                            "best": v.get("best") if isinstance(v.get("best"), int) else None,
                        }
        except Exception:
            pass

    def _save_state(self):
        try:
            with open(self._state_path(), "w", encoding="utf-8") as f:
                json.dump({
                    "mode": self.mode,
                    "human_is_x": self.human_is_x,
                    "pvp_swap": self.pvp_swap,
                    "records": self.records,
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _on_close(self):
        self.gen += 1
        self._save_state()
        self.root.destroy()

    # ------------------------------------------------------- построение

    def _build(self):
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True, padx=18, pady=(14, 16))

        top = tk.Frame(outer, bg=BG)
        top.pack(fill=tk.X, side=tk.TOP)

        logo = tk.Canvas(top, width=46, height=46, bg=BG,
                         highlightthickness=0, bd=0)
        logo.pack(side=tk.LEFT)
        round_rect(logo, 1, 1, 45, 45, 14, fill=PANEL, outline=LINE_HI)
        logo.create_text(15, 24, text="X", fill=X_COLOR, font=self.F_SYM)
        logo.create_text(32, 24, text="O", fill=O_COLOR, font=self.F_SYM)

        titles = tk.Frame(top, bg=BG)
        titles.pack(side=tk.LEFT, padx=(12, 0))
        tk.Label(titles, text="Крестики-нолики: Пять в ряд", bg=BG, fg=TEXT,
                 font=self.F_TITLE, anchor="w").pack(anchor="w")
        tk.Label(titles, text="Бесконечное поле · тяните мышью · колесо — масштаб",
                 bg=BG, fg=MUTED, font=self.F_SUB, anchor="w").pack(anchor="w")

        acts = tk.Frame(top, bg=BG)
        acts.pack(side=tk.RIGHT)
        self.btn_records = Chip(acts, "Статистика", self.open_records, "ghost",
                                height=32, radius=16, font=self.F_SMALL, parent_bg=BG)
        self.btn_records.pack(side=tk.RIGHT, padx=(6, 0))
        self.btn_records.configure(width=104)
        self.btn_help = Chip(acts, "?", self.open_help, "ghost", height=32,
                             radius=16, font=self.F_UI, parent_bg=BG)
        self.btn_help.configure(width=34)
        self.btn_help.pack(side=tk.RIGHT)

        body = tk.Frame(outer, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        self.board_frame = tk.Frame(body, bg=LINE, bd=0, highlightthickness=1,
                                    highlightbackground=LINE, highlightcolor=LINE)
        self.board_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(self.board_frame, bg=BOARD_A, highlightthickness=0,
                                bd=0, takefocus=1, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        side = tk.Frame(body, bg=PANEL, width=326, highlightthickness=1,
                        highlightbackground=LINE, highlightcolor=LINE)
        side.pack(side=tk.RIGHT, fill=tk.Y, padx=(16, 0))
        side.pack_propagate(False)
        inner = tk.Frame(side, bg=PANEL)
        inner.pack(fill=tk.BOTH, expand=True, padx=15, pady=14)

        # карточка состояния
        sc = tk.Frame(inner, bg=PANEL_HI, highlightthickness=1,
                      highlightbackground=LINE, highlightcolor=LINE)
        sc.pack(fill=tk.X)
        sci = tk.Frame(sc, bg=PANEL_HI)
        sci.pack(fill=tk.X, padx=13, pady=(11, 10))
        head = tk.Frame(sci, bg=PANEL_HI)
        head.pack(fill=tk.X)
        self.dot = tk.Canvas(head, width=10, height=10, bg=PANEL_HI,
                             highlightthickness=0, bd=0)
        self.dot.pack(side=tk.LEFT, pady=(2, 0))
        self.kicker = tk.Label(head, text="", bg=PANEL_HI, fg=DIM,
                               font=self.F_EYE, anchor="w")
        self.kicker.pack(side=tk.LEFT, padx=(7, 0))
        self.status = tk.Label(sci, text="", bg=PANEL_HI, fg=TEXT,
                               font=self.F_STAT, anchor="w", justify="left",
                               wraplength=272)
        self.status.pack(fill=tk.X, pady=(5, 0))
        self.moves_line = tk.Label(sci, text="", bg=PANEL_HI, fg=ACCENT,
                                   font=self.F_SMALL, anchor="w")
        self.moves_line.pack(fill=tk.X, pady=(7, 0))
        self.meta = tk.Label(sci, text="", bg=PANEL_HI, fg=DIM,
                             font=self.F_TINY, anchor="w")
        self.meta.pack(fill=tk.X, pady=(2, 0))
        self.sc = sc
        self.sci = sci

        # игроки
        pl = tk.Frame(inner, bg=PANEL)
        pl.pack(fill=tk.X, pady=(13, 0))
        plh = tk.Frame(pl, bg=PANEL)
        plh.pack(fill=tk.X)
        tk.Label(plh, text="ИГРОКИ", bg=PANEL, fg=MUTED,
                 font=self.F_EYE).pack(side=tk.LEFT)
        self.swap_btn = Chip(plh, "⇄", self.swap_players, "ghost", height=24,
                             radius=8, font=self.F_SMALL)
        self.swap_btn.configure(width=30)
        self.swap_btn.pack(side=tk.RIGHT)
        self.pl_hint = tk.Label(pl, text="Щёлкните по овалу — кто играет X",
                                bg=PANEL, fg=DIM, font=self.F_TINY, anchor="w")
        self.pl_hint.pack(fill=tk.X, pady=(3, 5))
        rows = tk.Frame(pl, bg=PANEL)
        rows.pack(fill=tk.X)
        rows.columnconfigure(0, weight=1, uniform="p")
        rows.columnconfigure(1, weight=1, uniform="p")
        self.chip_x = PlayerChip(rows, PLAYER_X, lambda: self.pick_x(PLAYER_X),
                                 self.F_SYM, self.F_NAME)
        self.chip_x.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.chip_o = PlayerChip(rows, PLAYER_O, lambda: self.pick_x(PLAYER_O),
                                 self.F_SYM, self.F_NAME)
        self.chip_o.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # режим
        md = tk.Frame(inner, bg=PANEL)
        md.pack(fill=tk.X, pady=(13, 0))
        tk.Label(md, text="РЕЖИМ ПАРТИИ", bg=PANEL, fg=MUTED,
                 font=self.F_EYE).pack(anchor="w", pady=(0, 5))
        mrow = tk.Frame(md, bg=PANEL)
        mrow.pack(fill=tk.X)
        mrow.columnconfigure(0, weight=1, uniform="m")
        mrow.columnconfigure(1, weight=1, uniform="m")
        self.mode_ai = Chip(mrow, "С компьютером", lambda: self.set_mode("ai"),
                            "toggle", height=34, radius=9, font=self.F_SMALL)
        self.mode_ai.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.mode_pvp = Chip(mrow, "Два игрока", lambda: self.set_mode("pvp"),
                             "toggle", height=34, radius=9, font=self.F_SMALL)
        self.mode_pvp.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # отладочные инструменты (временно на месте кнопок сложности)
        dbg = tk.Frame(inner, bg=PANEL)
        dbg.pack(fill=tk.X, pady=(13, 0))
        dh = tk.Frame(dbg, bg=PANEL)
        dh.pack(fill=tk.X)
        tk.Label(dh, text="ОТЛАДКА", bg=PANEL, fg=MUTED,
                 font=self.F_EYE).pack(side=tk.LEFT)
        tk.Label(dh, text="временно", bg=PANEL, fg=DIM,
                 font=self.F_TINY).pack(side=tk.RIGHT)
        grid = tk.Frame(dbg, bg=PANEL)
        grid.pack(fill=tk.X, pady=(6, 0))
        for c in range(3):
            grid.columnconfigure(c, weight=1, uniform="d")
        specs = [
            ("Анализ 1", self.copy_analysis, 0, 0),
            ("Партия 2", self.copy_game, 0, 1),
            ("Всё 3", self.copy_all, 0, 2),
            ("Просмотр A", self.open_analyses, 1, 0),
            ("Сохранить S", self.save_game, 1, 1),
            ("Центр C", self.center_last, 1, 2),
        ]
        self.dbg_btns = []
        for text, cmd, r, c in specs:
            b = Chip(grid, text, cmd, "secondary", height=30, radius=8,
                     font=self.F_TINY)
            b.grid(row=r, column=c, sticky="ew",
                   padx=(0 if c == 0 else 3, 0 if c == 2 else 3), pady=(0, 5))
            self.dbg_btns.append(b)

        # действия
        ac = tk.Frame(inner, bg=PANEL)
        ac.pack(fill=tk.X, pady=(10, 0))
        self.primary = Chip(ac, "Начать игру", self.primary_action, "primary",
                            height=42, radius=10, font=self.F_UI)
        self.primary.pack(fill=tk.X)
        pair = tk.Frame(ac, bg=PANEL)
        pair.pack(fill=tk.X, pady=(7, 0))
        pair.columnconfigure(0, weight=1, uniform="a")
        pair.columnconfigure(1, weight=1, uniform="a")
        self.undo_btn = Chip(pair, "Отменить ход", self.undo, "secondary",
                             height=38, radius=9, font=self.F_SMALL)
        self.undo_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.redo_btn = Chip(pair, "Вернуть ход", self.redo, "secondary",
                             height=38, radius=9, font=self.F_SMALL)
        self.redo_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.resume_btn = Chip(ac, "Ход ИИ — продолжить", self.resume_ai,
                               "secondary", height=36, radius=9, font=self.F_SMALL)
        self.resume_btn.pack(fill=tk.X, pady=(7, 0))
        self.rules_btn = Chip(ac, "Правила игры", self.open_help, "ghost",
                              height=34, radius=9, font=self.F_SMALL)
        self.rules_btn.pack(fill=tk.X, pady=(7, 0))

        foot = tk.Frame(inner, bg=PANEL)
        foot.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))
        tk.Label(foot, text="U / Ctrl+Z — отменить · Y — вернуть · ? — правила",
                 bg=PANEL, fg=DIM, font=self.F_TINY, wraplength=290,
                 justify="left").pack(anchor="w")

        self._bind()

    def _bind(self):
        cv = self.canvas
        cv.bind("<Configure>", self._on_resize)
        cv.bind("<ButtonPress-1>", self._on_down)
        cv.bind("<B1-Motion>", self._on_move_drag)
        cv.bind("<ButtonRelease-1>", self._on_up)
        cv.bind("<Motion>", self._on_hover)
        cv.bind("<Leave>", lambda e: self._clear_hover())
        cv.bind("<MouseWheel>", self._on_wheel)
        cv.bind("<ButtonPress-2>", self._on_pan_start)
        cv.bind("<B2-Motion>", self._on_pan_move)
        cv.bind("<ButtonPress-3>", self._on_pan_start)
        cv.bind("<B3-Motion>", self._on_pan_move)
        cv.bind("<ButtonRelease-2>", lambda e: setattr(self, "drag", None))
        cv.bind("<ButtonRelease-3>", lambda e: setattr(self, "drag", None))
        self.root.bind("<Key>", self._on_key)

    def _first_layout(self):
        self.width = max(1, self.canvas.winfo_width())
        self.height = max(1, self.canvas.winfo_height())
        self.view["x"] = self.width / 2 - BASE / 2
        self.view["y"] = self.height / 2 - BASE / 2
        self.schedule()

    # ------------------------------------------------------- геометрия

    def cs(self):
        return BASE * self.view["zoom"]

    def sx(self, x):
        return self.view["x"] + x * self.cs()

    def sy(self, y):
        return self.view["y"] + y * self.cs()

    def wx(self, px):
        return (px - self.view["x"]) / self.cs()

    def wy(self, py):
        return (py - self.view["y"]) / self.cs()

    def _on_resize(self, e):
        w, h = max(1, e.width), max(1, e.height)
        if w == self.width and h == self.height:
            return
        if self.width:
            self.view["x"] += (w - self.width) / 2
            self.view["y"] += (h - self.height) / 2
        else:
            self.view["x"] = w / 2 - BASE / 2
            self.view["y"] = h / 2 - BASE / 2
        self.width, self.height = w, h
        self.hover = None
        self.schedule()

    def set_zoom_at(self, z, px=None, py=None):
        z = max(MIN_ZOOM, min(MAX_ZOOM, z))
        if px is None:
            px = self.width / 2
        if py is None:
            py = self.height / 2
        wx, wy = self.wx(px), self.wy(py)
        self.view["zoom"] = z
        self.view["x"] = px - wx * BASE * z
        self.view["y"] = py - wy * BASE * z
        self.view_anim = None
        self.schedule()

    def animate_to(self, target, dur=0.30):
        if not self.width:
            self.view.update(target)
            return
        self.view_anim = {"from": dict(self.view), "to": target,
                          "t0": time.perf_counter(), "dur": dur}
        self.schedule()

    def fit_to_moves(self, animate=True):
        moves = self.board.move_history
        if not moves:
            target = {"x": self.width / 2 - BASE / 2,
                      "y": self.height / 2 - BASE / 2, "zoom": 1.0}
        else:
            xs = [m[0] for m in moves]
            ys = [m[1] for m in moves]
            span_x = (max(xs) - min(xs) + 4) * BASE
            span_y = (max(ys) - min(ys) + 4) * BASE
            z = min((self.width - 100) / max(1, span_x),
                    (self.height - 100) / max(1, span_y), 1.15)
            z = max(MIN_ZOOM, min(1.15, z))
            cx = (min(xs) + max(xs)) / 2 + 0.5
            cy = (min(ys) + max(ys)) / 2 + 0.5
            target = {"x": self.width / 2 - cx * BASE * z,
                      "y": self.height / 2 - cy * BASE * z, "zoom": z}
        if animate:
            self.animate_to(target)
        else:
            self.view.update(target)
            self.view_anim = None
            self.schedule()

    def center_last(self):
        if self.last_move:
            x, y, _ = self.last_move
            z = self.view["zoom"]
            self.animate_to({"x": self.width / 2 - (x + 0.5) * BASE * z,
                             "y": self.height / 2 - (y + 0.5) * BASE * z,
                             "zoom": z})
        else:
            self.fit_to_moves(True)

    def ensure_visible(self, x, y):
        cs = self.cs()
        px = self.sx(x) + cs / 2
        py = self.sy(y) + cs / 2
        m = 70
        if m < px < self.width - m and m < py < self.height - m:
            return
        z = self.view["zoom"]
        self.animate_to({"x": self.width / 2 - (x + 0.5) * BASE * z,
                         "y": self.height / 2 - (y + 0.5) * BASE * z,
                         "zoom": z})

    def ensure_line_visible(self):
        if not self.win_line:
            return
        m = 64
        for x, y in self.win_line:
            px, py = self.sx(x) + self.cs() / 2, self.sy(y) + self.cs() / 2
            if not (m < px < self.width - m and m < py < self.height - m):
                self.fit_to_moves(True)
                return

    # ------------------------------------------------------- отрисовка

    def schedule(self):
        if self._raf:
            return
        self._raf = True
        self.root.after(0, self._frame)

    def _frame(self):
        self._raf = False
        ts = time.perf_counter()
        self.draw(ts)
        if self._has_anim(ts):
            self._raf = True
            self.root.after(16, self._frame)

    def _has_anim(self, ts):
        if self.view_anim:
            return True
        if self.win_line and ts - self.win_start < 0.62:
            return True
        for born in list(self.anim.values()):
            if ts - born < 0.24:
                return True
        return False

    def draw(self, ts=None):
        ts = ts or time.perf_counter()
        cv = self.canvas
        if self.width <= 1:
            return
        if self.view_anim:
            a = self.view_anim
            t = max(0.0, min(1.0, (ts - a["t0"]) / a["dur"]))
            e = 1 - (1 - t) ** 3
            for k in ("x", "y", "zoom"):
                self.view[k] = a["from"][k] + (a["to"][k] - a["from"][k]) * e
            if t >= 1:
                self.view_anim = None
        cv.delete("all")
        self._hud_hits = []
        self._draw_bg()
        self._draw_fills()
        self._draw_grid()
        self._draw_labels()
        self._draw_stones(ts)
        self._draw_win(ts)
        self._draw_ghost()
        self._draw_hud()

    def _draw_bg(self):
        cv = self.canvas
        n = 64
        h = self.height
        for i in range(n):
            t = i / (n - 1)
            base = mix(BOARD_A, BOARD_B, t)
            glow = max(0.0, 1 - abs(t - 0.42) / 0.62)
            col = mix(base, "#ffffff", glow * 0.55)
            y0 = h * i / n
            cv.create_rectangle(0, y0, self.width, h * (i + 1) / n + 1,
                                fill=col, outline="")

    def _draw_fills(self):
        cv = self.canvas
        cs = self.cs()
        for x, y in self.win_line:
            px, py = self.sx(x), self.sy(y)
            if px > self.width or px + cs < 0 or py > self.height or py + cs < 0:
                continue
            cv.create_rectangle(px + 1, py + 1, px + cs - 1, py + cs - 1,
                                fill=mix(WIN_C, BOARD_A, 0.88), outline="")
        if self.hover and self._can_place():
            hx = int(self.wx(self.hover[0]) // 1)
            hy = int(self.wy(self.hover[1]) // 1)
            if self.board.is_empty(hx, hy):
                px, py = self.sx(hx), self.sy(hy)
                cv.create_rectangle(px + 1, py + 1, px + cs - 1, py + cs - 1,
                                    fill=mix(INFO, BOARD_A, 0.93), outline="")

    def _draw_grid(self):
        cv = self.canvas
        cs = self.cs()
        x0 = int((0 - self.view["x"]) // cs) - 1
        x1 = int((self.width - self.view["x"]) // cs) + 2
        y0 = int((0 - self.view["y"]) // cs) - 1
        y1 = int((self.height - self.view["y"]) // cs) + 2
        for x in range(x0, x1 + 1):
            px = round(self.sx(x)) + 0.5
            col = GRID_AX if x == 0 else (GRID_5 if x % 5 == 0 else GRID_1)
            cv.create_line(px, 0, px, self.height, fill=col)
        for y in range(y0, y1 + 1):
            py = round(self.sy(y)) + 0.5
            col = GRID_AX if y == 0 else (GRID_5 if y % 5 == 0 else GRID_1)
            cv.create_line(0, py, self.width, py, fill=col)

    def _draw_labels(self):
        cs = self.cs()
        if cs < 27:
            return
        cv = self.canvas
        col = mix(DIM, BOARD_A, 0.30)
        x0 = int((0 - self.view["x"]) // cs)
        x1 = int((self.width - self.view["x"]) // cs)
        y0 = int((0 - self.view["y"]) // cs)
        y1 = int((self.height - self.view["y"]) // cs)
        start = (x0 // 5) * 5
        for x in range(start, x1 + 1, 5):
            if x == 0:
                continue
            px = self.sx(x) + cs / 2
            if 30 < px < self.width - 30:
                cv.create_text(px, 9, text=coord(x), fill=col,
                               font=self.F_TINY, anchor="n")
        start = (y0 // 5) * 5
        for y in range(start, y1 + 1, 5):
            if y == 0:
                continue
            py = self.sy(y) + cs / 2
            if 30 < py < self.height - 30:
                cv.create_text(9, py, text=coord(y), fill=col,
                               font=self.F_TINY, anchor="w")

    def _mark(self, cx, cy, mark, cs, color, scale=1.0, glow=False):
        cv = self.canvas
        half = cs * 0.29 * scale
        if mark == PLAYER_X:
            w = max(2, cs * 0.10 * scale)
            if glow:
                soft = mix(color, BOARD_A, 0.72)
                cv.create_line(cx - half, cy - half, cx + half, cy + half,
                               fill=soft, width=w + 6, capstyle=tk.ROUND)
                cv.create_line(cx + half, cy - half, cx - half, cy + half,
                               fill=soft, width=w + 6, capstyle=tk.ROUND)
            cv.create_line(cx - half, cy - half, cx + half, cy + half,
                           fill=color, width=w, capstyle=tk.ROUND)
            cv.create_line(cx + half, cy - half, cx - half, cy + half,
                           fill=color, width=w, capstyle=tk.ROUND)
        else:
            w = max(2, cs * 0.09 * scale)
            if glow:
                soft = mix(color, BOARD_A, 0.72)
                cv.create_oval(cx - half, cy - half, cx + half, cy + half,
                               outline=soft, width=w + 6)
            cv.create_oval(cx - half, cy - half, cx + half, cy + half,
                           outline=color, width=w)

    def _draw_stones(self, ts):
        cs = self.cs()
        pad = cs * 1.2
        for x, y, p in self.board.move_history:
            cx = self.sx(x) + cs / 2
            cy = self.sy(y) + cs / 2
            if cx < -pad or cx > self.width + pad or cy < -pad or cy > self.height + pad:
                continue
            scale, alpha = 1.0, 1.0
            born = self.anim.get((x, y))
            if born is not None:
                age = ts - born
                if 0 <= age < 0.23:
                    t = age / 0.23
                    e = 1 - (1 - t) ** 3
                    scale = 0.62 + 0.38 * e
                    alpha = e
                elif age >= 0.23:
                    self.anim.pop((x, y), None)
            is_last = self.last_move and self.last_move[:2] == (x, y)
            base = LAST_C if is_last else (X_COLOR if p == PLAYER_X else O_COLOR)
            col = mix(base, BOARD_A, 1 - alpha)
            self._mark(cx, cy, p, cs, col, scale, glow=bool(is_last))

    def _draw_win(self, ts):
        if not self.win_line:
            return
        cs = self.cs()
        t = max(0.0, min(1.0, (ts - self.win_start) / 0.43))
        e = 1 - (1 - t) ** 3
        x1, y1 = self.win_line[0]
        x2, y2 = self.win_line[-1]
        ax = self.sx(x1) + cs / 2
        ay = self.sy(y1) + cs / 2
        bx = self.sx(x2) + cs / 2
        by = self.sy(y2) + cs / 2
        dx, dy = bx - ax, by - ay
        ln = (dx * dx + dy * dy) ** 0.5 or 1
        over = cs * 0.3
        sx = ax - dx / ln * over
        sy = ay - dy / ln * over
        fx = ax + dx * e + dx / ln * over * e
        fy = ay + dy * e + dy / ln * over * e
        cv = self.canvas
        cv.create_line(sx, sy, fx, fy, fill=mix(WIN_C, BOARD_A, 0.80),
                       width=max(10, cs * 0.34), capstyle=tk.ROUND)
        cv.create_line(sx, sy, fx, fy, fill=WIN_C,
                       width=max(2, cs * 0.055), capstyle=tk.ROUND)

    def _draw_ghost(self):
        if not self.hover or not self._can_place():
            return
        hx = int(self.wx(self.hover[0]) // 1)
        hy = int(self.wy(self.hover[1]) // 1)
        if not self.board.is_empty(hx, hy):
            return
        cs = self.cs()
        mark = self.turn if self.mode == "pvp" else self.human_mark
        base = X_COLOR if mark == PLAYER_X else O_COLOR
        self._mark(self.sx(hx) + cs / 2, self.sy(hy) + cs / 2, mark, cs,
                   mix(base, BOARD_A, 0.76), 0.92)

    # ------------------------------------------------------- HUD

    def _pill(self, x, y, text, fg, anchor="w", border=None, font=None):
        font = font or self.F_TINY
        tw = font.measure(text)
        w = tw + 20
        h = 24
        x0 = x if anchor == "w" else x - w
        cv = self.canvas
        round_rect(cv, x0, y, x0 + w, y + h, 12,
                   fill=mix(PANEL, BOARD_A, 0.12),
                   outline=border or LINE, width=1)
        cv.create_text(x0 + 10, y + h / 2, text=text, fill=fg,
                       font=font, anchor="w")
        return x0, y, x0 + w, y + h

    def _hud_button(self, x0, y0, w, h, text, action, font=None, fg=None):
        cv = self.canvas
        hot = self.hover and x0 <= self.hover[0] <= x0 + w and y0 <= self.hover[1] <= y0 + h
        round_rect(cv, x0, y0, x0 + w, y0 + h, 10,
                   fill=PANEL if hot else mix(PANEL, BOARD_A, 0.18),
                   outline=ACCENT if hot else LINE_HI, width=1)
        cv.create_text(x0 + w / 2, y0 + h / 2, text=text,
                       fill=(ACCENT if hot else (fg or MUTED)),
                       font=font or self.F_UI, anchor="center")
        self._hud_hits.append((x0, y0, x0 + w, y0 + h, action))

    def _draw_hud(self):
        cv = self.canvas
        cx = int(self.wx(self.width / 2) // 1)
        cy = int(self.wy(self.height / 2) // 1)
        self._pill(14, 12, "поле ∞ · %s : %s" % (coord(cx), coord(cy)), MUTED)
        if self.last_move:
            lx, ly, lp = self.last_move
            txt = "последний: %s · %s : %s" % (player_name(lp), coord(lx), coord(ly))
            self._pill(self.width - 14, 12, txt, LAST_C, anchor="e",
                       border=mix(LAST_C, PANEL, 0.55))
        else:
            self._pill(self.width - 14, 12, "последний ход —", DIM, anchor="e")

        if self.finished and self.result is not None:
            title = "ПОБЕДА!"
            n = self.x_count()
            who = self.name_of(self.result)
            if self.mode == "pvp":
                sub = "%s собрал пять · за %d %s" % (who, n, plural(n, "ход", "хода", "ходов"))
            elif self.result == self.human_mark:
                sub = "Вы собрали пять · за %d %s" % (n, plural(n, "ход", "хода", "ходов"))
            else:
                sub = "%s собрал пять · за %d %s" % (who, n, plural(n, "ход", "хода", "ходов"))
            w = max(280, self.F_BANS.measure(sub) + 56)
            h = 74
            x0 = (self.width - w) / 2
            y0 = 52
            round_rect(cv, x0, y0 + 4, x0 + w, y0 + h + 4, 16,
                       fill=mix(BANNER_BR, BOARD_B, 0.72), outline="")
            round_rect(cv, x0, y0, x0 + w, y0 + h, 16,
                       fill=BANNER_BG, outline=BANNER_BR, width=2)
            cv.create_text(self.width / 2, y0 + 26, text=title,
                           fill=BANNER_T, font=self.F_BAN)
            cv.create_text(self.width / 2, y0 + 54, text=sub,
                           fill=DANGER, font=self.F_BANS)

        bw, bh, gap = 36, 32, 6
        zw = 58
        total = bw * 3 + zw + gap * 3
        x = (self.width - total) / 2
        y = self.height - 14 - bh
        self._hud_button(x, y, bw, bh, "−",
                         lambda: self.set_zoom_at(self.view["zoom"] / 1.18))
        x += bw + gap
        self._hud_button(x, y, zw, bh, "%d%%" % round(self.view["zoom"] * 100),
                         lambda: self.set_zoom_at(1.0), font=self.F_SMALL)
        x += zw + gap
        self._hud_button(x, y, bw, bh, "+",
                         lambda: self.set_zoom_at(self.view["zoom"] * 1.18))
        x += bw + gap
        self._hud_button(x, y, bw, bh, "⌖", self.center_last)

        if self._hint_on and self.started:
            txt = "Тяните поле левой кнопкой · колесо — масштаб"
            tw = self.F_TINY.measure(txt) + 22
            x0 = (self.width - tw) / 2
            y0 = y - 32
            round_rect(cv, x0, y0, x0 + tw, y0 + 24, 12,
                       fill=mix(PANEL, BOARD_A, 0.10), outline=LINE)
            cv.create_text(self.width / 2, y0 + 12, text=txt, fill=INFO,
                           font=self.F_TINY)

    def _hit_hud(self, px, py):
        for x0, y0, x1, y1, action in self._hud_hits:
            if x0 <= px <= x1 and y0 <= py <= y1:
                return action
        return None

    # ------------------------------------------------------- ввод

    def _can_place(self):
        if not self.started or self.finished or self.thinking:
            return False
        if self.mode == "pvp":
            return True
        return self.turn == self.human_mark

    def _clear_hover(self):
        if self.hover is not None:
            self.hover = None
            self.schedule()

    def _on_down(self, e):
        self.canvas.focus_set()
        action = self._hit_hud(e.x, e.y)
        if action:
            action()
            self.drag = None
            return
        self.drag = {"sx": e.x, "sy": e.y, "lx": e.x, "ly": e.y, "moved": False}
        self.hover = (e.x, e.y)

    def _on_move_drag(self, e):
        if not self.drag:
            return
        d = self.drag
        if abs(e.x - d["sx"]) + abs(e.y - d["sy"]) > 5:
            d["moved"] = True
        if d["moved"]:
            self.view["x"] += e.x - d["lx"]
            self.view["y"] += e.y - d["ly"]
            self.view_anim = None
            self.hover = None
            self._hint_on = False
            self.canvas.configure(cursor="fleur")
        d["lx"], d["ly"] = e.x, e.y
        self.schedule()

    def _on_up(self, e):
        d = self.drag
        self.drag = None
        self.canvas.configure(cursor="crosshair")
        if not d:
            return
        if not d["moved"]:
            self.tap(e.x, e.y)
        self.hover = (e.x, e.y)
        self.schedule()

    def _on_pan_start(self, e):
        self.drag = {"sx": e.x, "sy": e.y, "lx": e.x, "ly": e.y, "moved": True}

    def _on_pan_move(self, e):
        if not self.drag:
            return
        self.view["x"] += e.x - self.drag["lx"]
        self.view["y"] += e.y - self.drag["ly"]
        self.drag["lx"], self.drag["ly"] = e.x, e.y
        self.view_anim = None
        self._hint_on = False
        self.schedule()

    def _on_hover(self, e):
        if self.drag and self.drag.get("moved"):
            return
        self.hover = (e.x, e.y)
        self.canvas.configure(cursor="hand2" if self._hit_hud(e.x, e.y)
                              else "crosshair")
        self.schedule()

    def _on_wheel(self, e):
        steps = e.delta / 120.0
        self._hint_on = False
        self.set_zoom_at(self.view["zoom"] * (1.16 ** steps), e.x, e.y)

    def tap(self, px, py):
        if not self.started:
            self.note("Сначала нажмите «Начать игру»")
            return
        if not self._can_place():
            if self.thinking:
                self.note("Компьютер думает — подождите")
            elif self.finished:
                self.note("Партия окончена — нажмите «Новая игра»")
            else:
                self.note("Сейчас ход ИИ — нажмите «Ход ИИ — продолжить»")
            return
        x = int(self.wx(px) // 1)
        y = int(self.wy(py) // 1)
        if not self.board.is_empty(x, y):
            self.note("Клетка %s : %s уже занята" % (coord(x), coord(y)))
            return
        self.human_move(x, y)

    def _on_key(self, e):
        if self._help_win or self._an_win or self._rec_win:
            if e.keysym == "Escape":
                for w in (self._help_win, self._an_win, self._rec_win):
                    if w:
                        w.destroy()
            return
        k = e.keysym
        step = BASE * 0.6
        if k == "Left":
            self.view["x"] += step
        elif k == "Right":
            self.view["x"] -= step
        elif k == "Up":
            self.view["y"] += step
        elif k == "Down":
            self.view["y"] -= step
        elif k in ("plus", "KP_Add", "equal"):
            self.set_zoom_at(self.view["zoom"] * 1.18); return
        elif k in ("minus", "KP_Subtract"):
            self.set_zoom_at(self.view["zoom"] / 1.18); return
        elif k in ("0", "Home"):
            self.fit_to_moves(True); return
        elif k in ("c", "C", "с", "С"):
            self.center_last(); return
        elif k in ("u", "U", "г", "Г") or (e.state & 4 and k.lower() == "z"):
            self.undo(); return
        elif k in ("y", "Y", "н", "Н"):
            self.redo(); return
        elif k in ("n", "N", "т", "Т"):
            self.primary_action(); return
        elif k in ("question", "F1", "h", "H"):
            self.open_help(); return
        elif k == "1":
            self.copy_analysis(); return
        elif k == "2":
            self.copy_game(); return
        elif k == "3":
            self.copy_all(); return
        elif k in ("a", "A", "ф", "Ф"):
            self.open_analyses(); return
        elif k in ("s", "S", "ы", "Ы"):
            self.save_game(); return
        else:
            return
        self.view_anim = None
        self.schedule()

    # ------------------------------------------------------- партия

    def note(self, text):
        self.status_note = text
        self._sync()
        self.root.after(2600, lambda: self._clear_note(text))

    def _clear_note(self, text):
        if self.status_note == text:
            self.status_note = ""
            self._sync()

    def pick_x(self, mark):
        if self.started:
            return
        if self.mode == "pvp":
            self.pvp_swap = (mark == PLAYER_O)
        else:
            self.human_is_x = (mark == PLAYER_X)
        self._save_state()
        self._sync()

    def swap_players(self):
        if self.started:
            return
        if self.mode == "pvp":
            self.pvp_swap = not self.pvp_swap
        else:
            self.human_is_x = not self.human_is_x
        self._save_state()
        self._sync()

    def set_mode(self, mode):
        if self.started or mode == self.mode:
            return
        self.mode = mode
        self._save_state()
        self._sync()

    def primary_action(self):
        if not self.started:
            self.begin_game()
        else:
            self.to_setup()

    def _fresh(self):
        self.gen += 1
        self.thinking = False
        self.board = Board()
        self.turn = PLAYER_X
        self.finished = False
        self.result = None
        self.win_line = []
        self.last_move = None
        self.redo_stack = []
        self.move_records = []
        self.game_log = []
        self.last_analysis = ""
        self.record_snapshot = None
        self.anim = {}
        self.hover = None
        self.status_note = ""

    def begin_game(self):
        self._fresh()
        self.started = True
        self._hint_on = True
        self.fit_to_moves(False)
        self._save_state()
        self._sync()
        self.schedule()
        if self.mode == "ai" and self.ai_mark == PLAYER_X:
            self.start_ai()

    def to_setup(self):
        self._fresh()
        self.started = False
        self.fit_to_moves(False)
        self._sync()
        self.schedule()

    def winner_line(self, x, y, p):
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            cells = [(x, y)]
            nx, ny = x + dx, y + dy
            while self.board.get_cell(nx, ny) == p:
                cells.append((nx, ny))
                nx += dx
                ny += dy
            nx, ny = x - dx, y - dy
            while self.board.get_cell(nx, ny) == p:
                cells.insert(0, (nx, ny))
                nx -= dx
                ny -= dy
            if len(cells) >= WIN_LENGTH:
                return cells
        return None

    def place(self, x, y, p, analysis="", elapsed=None):
        if not self.board.make_move(x, y, p):
            return False
        self.last_move = (x, y, p)
        self.turn = p
        n = len(self.board.move_history)
        self.move_records.append({"n": n, "player": p, "move": (x, y),
                                  "analysis": analysis, "elapsed": elapsed})
        self.game_log.append("%d. %s (%s, %s)" % (n, player_name(p), coord(x), coord(y)))
        self.anim[(x, y)] = time.perf_counter()
        self.ensure_visible(x, y)
        self._sync()
        self.schedule()
        return True

    def after_move(self, x, y, p):
        line = self.winner_line(x, y, p)
        if line:
            self.finish(p, line)
            return
        if self.mode == "pvp":
            self.turn = other(p)
            self.thinking = False
            self._sync()
            self.schedule()
            return
        if p == self.human_mark:
            self.turn = self.ai_mark
            self.start_ai()
        else:
            self.turn = self.human_mark
            self.thinking = False
            self._sync()

    def human_move(self, x, y):
        if not self._can_place():
            return False
        p = self.turn if self.mode == "pvp" else self.human_mark
        self.redo_stack = []
        self._hint_on = False
        if not self.place(x, y, p):
            return False
        self.after_move(x, y, p)
        return True

    def start_ai(self):
        if self.finished or self.thinking or self.mode != "ai":
            return
        self.thinking = True
        self.status_note = ""
        self.gen += 1
        gen = self.gen
        snap = self.board.copy()
        ai = self.ai_mark
        self._sync()
        self.schedule()
        t0 = time.perf_counter()

        def work():
            try:
                move = get_best_move(snap, ai)
                text = "\n".join(DEBUG_LOG)
                err = None
            except Exception as exc:
                move, text, err = None, "", "%s: %s" % (type(exc).__name__, exc)
            dt = time.perf_counter() - t0
            self.root.after(0, lambda: self.ai_done(gen, move, text, err, dt))

        threading.Thread(target=work, daemon=True).start()

    def ai_done(self, gen, move, analysis, err, elapsed):
        if gen != self.gen:
            return
        self.thinking = False
        self.last_analysis = analysis
        if err or move is None:
            self.turn = self.human_mark
            self.note("Ошибка поиска: %s" % (err or "ход не найден"))
            self.schedule()
            return
        self.place(move[0], move[1], self.ai_mark, analysis, elapsed)
        self.after_move(move[0], move[1], self.ai_mark)

    def resume_ai(self):
        if not self.started or self.finished or self.thinking:
            return
        if self.mode != "ai" or self.turn != self.ai_mark:
            return
        self.redo_stack = []
        self.start_ai()

    def finish(self, p, line):
        self.finished = True
        self.thinking = True
        self.gen += 1
        self.thinking = False
        self.result = p
        self.turn = p
        self.win_line = line
        self.win_start = time.perf_counter()
        self.record_snapshot = json.loads(json.dumps(self.records))
        total = len(self.board.move_history)
        if self.mode == "pvp":
            self._rec_win(self.name_of(p), self.x_count())
            self._rec_loss(self.name_of(other(p)))
        elif p == self.human_mark:
            self._rec_win(self.name_of(self.human_mark), self.x_count())
        else:
            self._rec_loss(self.name_of(self.human_mark))
        self._save_state()
        self._hint_on = False
        self._sync()
        self.schedule()
        gen = self.gen
        self.root.after(560, lambda: self._after_win(gen))

    def _after_win(self, gen):
        if gen == self.gen and self.finished:
            self.ensure_line_visible()

    def _rec_win(self, name, moves):
        r = self.records.setdefault(name, {"wins": 0, "losses": 0, "best": None})
        r["wins"] += 1
        if moves > 0 and (r["best"] is None or moves < r["best"]):
            r["best"] = moves

    def _rec_loss(self, name):
        r = self.records.setdefault(name, {"wins": 0, "losses": 0, "best": None})
        r["losses"] += 1

    def undo(self):
        if not self.started or not self.board.move_history:
            return
        self.gen += 1
        self.thinking = False
        was_finished = self.finished
        x, y, p = self.board.undo_move()
        rec = self.move_records.pop() if self.move_records else None
        if self.game_log:
            self.game_log.pop()
        self.redo_stack.append({"move": (x, y, p), "rec": rec})
        self.anim.pop((x, y), None)
        self.turn = p
        self.finished = False
        self.result = None
        self.win_line = []
        self.last_move = self.board.move_history[-1] if self.board.move_history else None
        if was_finished and self.record_snapshot is not None:
            self.records = self.record_snapshot
            self.record_snapshot = None
            self._save_state()
        self.note("Ход отменён · %s" % player_name(p))
        self._sync()
        self.schedule()

    def redo(self):
        if not self.started or not self.redo_stack:
            return
        self.gen += 1
        self.thinking = False
        item = self.redo_stack.pop()
        x, y, p = item["move"]
        rec = item["rec"] or {}
        if not self.place(x, y, p, rec.get("analysis", ""), rec.get("elapsed")):
            return
        line = self.winner_line(x, y, p)
        if line:
            self.finish(p, line)
            return
        self.turn = other(p)
        self.finished = False
        self.result = None
        self.win_line = []
        self.note("Ход восстановлен · %s" % player_name(p))
        self._sync()
        self.schedule()

    # ------------------------------------------------------- синхронизация

    def _sync(self):
        editing = not self.started
        self.chip_x.update(self.name_of(PLAYER_X), self.turn == PLAYER_X and not self.finished, editing)
        self.chip_o.update(self.name_of(PLAYER_O), self.turn == PLAYER_O and not self.finished, editing)
        self.swap_btn.set_enabled(editing)
        self.pl_hint.configure(
            text="Щёлкните по овалу — кто играет X" if editing
            else "Состав фиксируется на всю партию")
        self.mode_ai.set_kind("toggle_on" if self.mode == "ai" else "toggle")
        self.mode_pvp.set_kind("toggle_on" if self.mode == "pvp" else "toggle")
        self.mode_ai.set_enabled(editing)
        self.mode_pvp.set_enabled(editing)

        self.primary.set_text("Начать игру" if not self.started else "Новая игра")
        self.undo_btn.set_enabled(self.started and bool(self.board.move_history))
        self.redo_btn.set_enabled(self.started and bool(self.redo_stack))
        self.resume_btn.set_enabled(self.started and not self.finished
                                    and not self.thinking and self.mode == "ai"
                                    and self.turn == self.ai_mark)

        n = self.x_count()
        total = len(self.board.move_history)
        self.moves_line.configure(text="Ходов: %d" % n)
        if self.last_move:
            lx, ly, lp = self.last_move
            last = "последний: %s · %s : %s" % (player_name(lp), coord(lx), coord(ly))
        else:
            last = "последний: —"
        self.meta.configure(text="полуходов: %d · %s" % (total, last))

        bg, dot = PANEL_HI, ACCENT
        if self.status_note:
            kick, text = "Сообщение", self.status_note
            bg, dot = mix(WARN, PANEL, 0.90), WARN
        elif not self.started:
            kick = "Новая партия"
            text = "Выберите, кто играет X, и начните игру"
        elif self.finished and self.result is not None:
            who = self.name_of(self.result)
            if self.mode == "pvp":
                kick, text = "Победа", "%s собрал пять" % who
                bg, dot = mix(WIN_C, PANEL, 0.90), WIN_C
            elif self.result == self.human_mark:
                kick, text = "Победа", "Вы собрали пять"
                bg, dot = mix(WIN_C, PANEL, 0.90), WIN_C
            else:
                kick, text = "Поражение", "%s собрал пять" % who
                bg, dot = mix(DANGER, PANEL, 0.90), DANGER
        elif self.thinking:
            kick = "Компьютер · %s" % player_name(self.ai_mark)
            text = "Думает…"
            bg, dot = mix(INFO, PANEL, 0.90), INFO
        elif self.mode == "pvp":
            kick = "Ход: %s" % self.name_of(self.turn)
            text = "Ставьте %s в свободную клетку" % player_name(self.turn)
            dot = X_COLOR if self.turn == PLAYER_X else O_COLOR
        elif self.turn == self.ai_mark:
            kick, text = "Пауза", "Нажмите «Ход ИИ — продолжить»"
            bg, dot = mix(WARN, PANEL, 0.92), WARN
        else:
            kick = "Ваш ход · %s" % player_name(self.human_mark)
            text = ("Ставьте %s в любую свободную клетку" % player_name(self.human_mark)
                    if total else "Соберите пять %s подряд" % player_name(self.human_mark))
            dot = X_COLOR if self.human_mark == PLAYER_X else O_COLOR

        self.kicker.configure(text=kick.upper(), bg=bg)
        self.status.configure(text=text, bg=bg)
        self.moves_line.configure(bg=bg)
        self.meta.configure(bg=bg)
        self.sc.configure(highlightbackground=LINE)
        for w in (self.sc, self.sci, self.kicker.master):
            w.configure(bg=bg)
        self.dot.configure(bg=bg)
        self.dot.delete("all")
        self.dot.create_oval(1, 1, 9, 9, fill=dot, outline="")

    # ------------------------------------------------------- окна

    def _modal(self, title, w, h):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=PANEL)
        win.transient(self.root)
        win.geometry("%dx%d" % (w, h))
        win.minsize(min(w, 520), min(h, 420))
        x = self.root.winfo_rootx() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - h) // 2
        win.geometry("+%d+%d" % (max(0, x), max(0, y)))
        win.grab_set()
        return win

    def _scroller(self, parent):
        frame = tk.Frame(parent, bg=PANEL)
        sb = tk.Scrollbar(frame, orient="vertical", bg=SURF_HI, troughcolor=PANEL_HI,
                          activebackground=ACCENT, highlightthickness=0, bd=0,
                          relief="flat", elementborderwidth=0, width=12)
        txt = tk.Text(frame, wrap="word", bg=PANEL, fg=TEXT, font=self.F_BODY,
                      bd=0, highlightthickness=0, padx=18, pady=16,
                      spacing1=2, spacing3=5, yscrollcommand=sb.set, cursor="arrow")
        sb.configure(command=txt.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        return frame, txt

    def open_help(self):
        if self._help_win:
            self._help_win.lift()
            return
        win = self._modal("Правила игры", 720, 660)
        self._help_win = win
        head = tk.Frame(win, bg=PANEL_HI)
        head.pack(fill=tk.X)
        tk.Label(head, text="Правила и управление", bg=PANEL_HI, fg=TEXT,
                 font=self.F_TITLE).pack(side=tk.LEFT, padx=18, pady=14)
        Chip(head, "✕", win.destroy, "ghost", height=30, radius=15,
             font=self.F_UI, parent_bg=PANEL_HI).pack(side=tk.RIGHT, padx=14)
        frame, txt = self._scroller(win)
        frame.pack(fill=tk.BOTH, expand=True)
        txt.tag_configure("h2", font=self.F_H3, foreground=ACCENT, spacing1=12, spacing3=4)
        txt.tag_configure("b", foreground=MUTED)
        txt.tag_configure("k", font=self.F_MONOB, foreground=TEXT)
        txt.tag_configure("warn", foreground=WARN, font=self.F_SMALL)

        def h2(s):
            txt.insert("end", s + "\n", "h2")

        def p(s):
            txt.insert("end", s + "\n", "b")

        def kv(k, s):
            txt.insert("end", k + " — ", "k")
            txt.insert("end", s + "\n", "b")

        h2("Правила игры")
        p("Бесконечное поле. Соберите пять своих знаков подряд по горизонтали, "
          "вертикали или любой диагонали. Знаки ставятся в центры клеток. "
          "Первым всегда ходит X.")
        h2("Перед партией")
        p("В панели справа щёлкните по овалу игрока — так выбирается, кто играет "
          "крестиками. Ниже выбирается режим: «С компьютером» или «Два игрока». "
          "Состав и режим доступны только до начала партии. Затем нажмите «Начать игру».")
        h2("Ход и поле")
        p("Коснитесь свободной клетки левой кнопкой мыши. Зажав левую кнопку, "
          "тяните поле — оно перемещается в окне. Колесо мыши меняет масштаб "
          "относительно точки под курсором. Кнопки − / % / + / ⌖ внизу поля "
          "дублируют масштаб и центрирование.")
        h2("Два игрока")
        p("X и O ходят по очереди на одном экране. Имена «Игрок 1» и «Игрок 2» "
          "меняются местами тем же щелчком по овалу до старта.")
        h2("Счёт ходов")
        p("Строка «Ходов: N» считает ходы крестиков, а не полуходы. Общее число "
          "полуходов показано ниже мелким шрифтом вместе с последним ходом.")
        h2("Кнопки: основная панель")
        kv("Начать игру", "запускает партию с выбранным составом. Во время партии "
                          "кнопка называется «Новая игра» и возвращает к настройке "
                          "состава, очищая поле.")
        kv("Отменить ход", "снимает один последний полуход. Нажимайте подряд, чтобы "
                           "дойти до самого начала партии. Работает и после победы: "
                           "результат и статистика откатываются.")
        kv("Вернуть ход", "возвращает снятые полуходы по одному, в обратном порядке. "
                          "Список возврата очищается, как только сделан новый ход.")
        kv("Ход ИИ — продолжить", "появляется активной, если после отмены или возврата "
                                  "очередь за компьютером. Нажмите, чтобы партия "
                                  "продолжилась с текущей позиции. Без этого шага "
                                  "отмена не «отыгрывается» автоматически.")
        kv("Правила игры", "это окно.")
        kv("Статистика", "таблица побед, поражений и лучшего числа ходов. Записи "
                         "хранятся на этом устройстве.")
        kv("⇄", "меняет игроков местами, то же, что щелчок по овалу.")
        h2("Кнопки: отладка (временно на месте выбора силы ИИ)")
        txt.insert("end", "Эти кнопки нужны для проверки движка и в итоговой версии "
                          "будут скрыты.\n", "warn")
        kv("Анализ 1", "копирует в буфер полный разбор последнего хода ИИ: шаги поиска, "
                       "найденные угрозы, точки достройки, оценки. Нажимать сразу "
                       "после хода компьютера, если он выглядит ошибочным.")
        kv("Партия 2", "копирует список всех ходов в текстовом виде — удобно вставить "
                       "в сообщение или сохранить как протокол.")
        kv("Всё 3", "копирует разборы всех ходов ИИ подряд, с номерами и временем. "
                    "Нажимать в конце партии для полного разбора.")
        kv("Просмотр A", "открывает окно со списком ходов ИИ слева и полным анализом "
                         "выбранного хода справа. Основной инструмент разбора: "
                         "позволяет найти, на каком ходу оценка впервые стала плохой.")
        kv("Сохранить S", "пишет JSON со всеми ходами, анализами и временем обдумывания. "
                          "Этот файл можно загрузить как тестовую позицию.")
        kv("Центр C", "наводит камеру на последний ход. Полезно, если компьютер "
                      "сыграл далеко за пределами видимой области.")
        h2("Клавиши")
        kv("стрелки", "сдвиг поля")
        kv("+ / −", "масштаб")
        kv("0 или Home", "вписать все камни в окно")
        kv("C", "центрировать на последнем ходе")
        kv("U или Ctrl+Z", "отменить ход")
        kv("Y", "вернуть ход")
        kv("N", "начать / новая игра")
        kv("? или F1", "это окно")
        kv("1 / 2 / 3 / A / S", "отладочные действия")
        txt.configure(state="disabled")
        Chip(win, "Понятно", win.destroy, "primary", height=40,
             font=self.F_UI).pack(fill=tk.X, padx=18, pady=14)

        def close():
            self._help_win = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", close)
        for b in win.winfo_children():
            pass
        win.bind("<Escape>", lambda e: close())
        self._help_close = close
        win.after(50, lambda: None)
        # кнопки закрытия используют ту же уборку
        for child in win.winfo_children():
            if isinstance(child, Chip):
                child.command = close
        head_children = [c for c in win.winfo_children() if isinstance(c, tk.Frame)]
        if head_children:
            for c in head_children[0].winfo_children():
                if isinstance(c, Chip):
                    c.command = close

    def open_analyses(self):
        if self._an_win:
            self._an_win.lift()
            return
        recs = [r for r in self.move_records if r["analysis"]]
        if not recs:
            self.note("Анализов пока нет — сделайте ход ИИ")
            return
        win = self._modal("Анализы ходов ИИ", 1000, 640)
        self._an_win = win
        head = tk.Frame(win, bg=PANEL_HI)
        head.pack(fill=tk.X)
        tk.Label(head, text="Разбор ходов компьютера", bg=PANEL_HI, fg=TEXT,
                 font=self.F_TITLE).pack(side=tk.LEFT, padx=18, pady=12)
        body = tk.Frame(win, bg=PANEL)
        body.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)

        left = tk.Frame(body, bg=PANEL)
        left.pack(side=tk.LEFT, fill=tk.Y)
        lsb = tk.Scrollbar(left, orient="vertical", bg=SURF_HI, troughcolor=PANEL_HI,
                           activebackground=ACCENT, highlightthickness=0, bd=0,
                           relief="flat", width=11)
        lb = tk.Listbox(left, width=30, bg=PANEL_HI, fg=TEXT, font=self.F_MONO,
                        bd=0, highlightthickness=1, highlightbackground=LINE,
                        selectbackground=ACCENT, selectforeground="#ffffff",
                        activestyle="none", yscrollcommand=lsb.set)
        lsb.configure(command=lb.yview)
        lb.pack(side=tk.LEFT, fill=tk.Y)
        lsb.pack(side=tk.LEFT, fill=tk.Y)

        right = tk.Frame(body, bg=PANEL)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))
        rsb = tk.Scrollbar(right, orient="vertical", bg=SURF_HI, troughcolor=PANEL_HI,
                           activebackground=ACCENT, highlightthickness=0, bd=0,
                           relief="flat", width=11)
        txt = tk.Text(right, wrap="none", bg=PANEL_HI, fg=TEXT, font=self.F_MONO,
                      bd=0, highlightthickness=1, highlightbackground=LINE,
                      padx=12, pady=10, yscrollcommand=rsb.set, cursor="arrow")
        hsb = tk.Scrollbar(right, orient="horizontal", bg=SURF_HI, troughcolor=PANEL_HI,
                           activebackground=ACCENT, highlightthickness=0, bd=0,
                           relief="flat", width=11)
        rsb.configure(command=txt.yview)
        hsb.configure(command=txt.xview)
        txt.configure(xscrollcommand=hsb.set)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        rsb.pack(side=tk.RIGHT, fill=tk.Y)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for r in recs:
            t = r["elapsed"]
            lb.insert("end", "%3d. %s %-11s %s" % (
                r["n"], player_name(r["player"]), str(r["move"]),
                ("%.2fs" % t) if t is not None else ""))

        def select(_=None):
            sel = lb.curselection()
            if not sel:
                return
            r = recs[sel[0]]
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            txt.insert("end", r["analysis"])
            txt.configure(state="disabled")

        lb.bind("<<ListboxSelect>>", select)
        lb.selection_set(0)
        select()

        def close():
            self._an_win = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", close)
        win.bind("<Escape>", lambda e: close())
        Chip(win, "Закрыть", close, "secondary", height=36,
             font=self.F_SMALL).pack(fill=tk.X, padx=14, pady=(0, 12))

    def open_records(self):
        if self._rec_win:
            self._rec_win.lift()
            return
        win = self._modal("Статистика", 620, 520)
        self._rec_win = win
        head = tk.Frame(win, bg=PANEL_HI)
        head.pack(fill=tk.X)
        tk.Label(head, text="Рекорды игроков", bg=PANEL_HI, fg=TEXT,
                 font=self.F_TITLE).pack(side=tk.LEFT, padx=18, pady=12)
        body = tk.Frame(win, bg=PANEL)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)
        tk.Label(body, text="Победы, поражения и лучшее число ходов X, за которое "
                            "собрано пять в ряд.", bg=PANEL, fg=MUTED,
                 font=self.F_BODY, justify="left", wraplength=560).pack(anchor="w")
        box = tk.Frame(body, bg=PANEL_HI, highlightthickness=1,
                       highlightbackground=LINE)
        box.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        sb = tk.Scrollbar(box, orient="vertical", bg=SURF_HI, troughcolor=PANEL_HI,
                          activebackground=ACCENT, highlightthickness=0, bd=0,
                          relief="flat", width=11)
        txt = tk.Text(box, height=10, bg=PANEL_HI, fg=TEXT, font=self.F_MONO,
                      bd=0, highlightthickness=0, padx=12, pady=10,
                      yscrollcommand=sb.set, cursor="arrow")
        sb.configure(command=txt.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        txt.tag_configure("hd", foreground=DIM, font=self.F_MONOB)
        txt.tag_configure("w", foreground=X_COLOR, font=self.F_MONOB)
        txt.tag_configure("l", foreground=O_COLOR)
        txt.tag_configure("bst", foreground=WIN_C, font=self.F_MONOB)

        rows = sorted(self.records.items(),
                      key=lambda kv: (-kv[1]["wins"],
                                      kv[1]["best"] if kv[1]["best"] else 10 ** 9,
                                      kv[0]))
        txt.insert("end", "%-3s %-22s %7s %9s %8s\n" % ("#", "Игрок", "Победы", "Пораж.", "Мин."), "hd")
        txt.insert("end", "─" * 54 + "\n", "hd")
        if not rows:
            txt.insert("end", "\nПока нет сыгранных партий.\n", "l")
        for i, (name, r) in enumerate(rows, 1):
            nm = name if len(name) <= 22 else name[:21] + "…"
            txt.insert("end", "%-3d %-22s " % (i, nm))
            txt.insert("end", "%7d " % r["wins"], "w")
            txt.insert("end", "%9d " % r["losses"], "l")
            txt.insert("end", "%8s\n" % (r["best"] if r["best"] else "—"), "bst")
        txt.configure(state="disabled")

        btns = tk.Frame(win, bg=PANEL)
        btns.pack(fill=tk.X, padx=16, pady=12)

        def close():
            self._rec_win = None
            self._reset_armed = False
            win.destroy()

        def reset():
            if not self._reset_armed:
                self._reset_armed = True
                rb.set_text("Точно сбросить?")
                rb.set_kind("danger")
                win.after(6000, lambda: (rb.set_text("Сбросить таблицу"),
                                         rb.set_kind("secondary"),
                                         setattr(self, "_reset_armed", False)))
                return
            self.records = {}
            self._save_state()
            self._reset_armed = False
            close()
            self.open_records()

        rb = Chip(btns, "Сбросить таблицу", reset, "secondary", height=36,
                  font=self.F_SMALL)
        rb.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        Chip(btns, "Закрыть", close, "primary", height=36,
             font=self.F_SMALL).pack(side=tk.LEFT, fill=tk.X, expand=True)
        win.protocol("WM_DELETE_WINDOW", close)
        win.bind("<Escape>", lambda e: close())

    # ------------------------------------------------------- буфер / файлы

    def _clip(self, text, msg):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.note(msg)

    def copy_analysis(self):
        self._clip(self.last_analysis or "(анализа ещё нет)",
                   "Анализ последнего хода скопирован")

    def copy_game(self):
        self._clip("\n".join(self.game_log) or "(партия пуста)",
                   "Список ходов скопирован (%d)" % len(self.game_log))

    def copy_all(self):
        parts = []
        for r in self.move_records:
            head = "=== Ход %d: %s %s" % (r["n"], player_name(r["player"]), r["move"])
            if r["elapsed"] is not None:
                head += " (%.2f с)" % r["elapsed"]
            parts.append(head + " ===")
            parts.append(r["analysis"] or "(ход игрока — без анализа)")
            parts.append("")
        self._clip("\n".join(parts) or "(партия пуста)",
                   "Скопированы разборы: %d ходов" % len(self.move_records))

    def save_game(self):
        if not self.move_records:
            self.note("Партия пуста — нечего сохранять")
            return
        path = filedialog.asksaveasfilename(
            title="Сохранить партию и анализы", defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Все файлы", "*.*")],
            initialfile="gomoku_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
        if not path:
            return
        data = {
            "saved": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": self.mode,
            "human": player_name(self.human_mark),
            "x_player": self.name_of(PLAYER_X),
            "o_player": self.name_of(PLAYER_O),
            "x_moves": self.x_count(),
            "moves": [{"n": r["n"], "player": player_name(r["player"]),
                       "x": r["move"][0], "y": r["move"][1],
                       "elapsed": r["elapsed"], "analysis": r["analysis"]}
                      for r in self.move_records],
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.note("Сохранено: %s" % os.path.basename(path))
        except Exception as exc:
            self.note("Не удалось сохранить: %s" % exc)

    def run(self):
        self.root.mainloop()


def main():
    GomokuApp().run()


if __name__ == "__main__":
    main()