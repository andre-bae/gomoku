# gomoku_ui.py
"""
Интерфейс «Крестики-нолики: Пять в ряд» — бесконечное поле на canvas.

Запуск:  python gomoku.py   (или python gomoku_ui.py)

Исправлено в этой версии:
  * критический сбой запуска: внутренний кэш ширины виджета больше не
    перезаписывает служебное поле tkinter `_w` (из-за этого Tk получал
    команду «0» и падал с invalid command name "0");
  * у всех canvas-виджетов задана явная ширина — иначе Tk подставлял
    умолчание 378 px и распира панель;
  * производительность: фон кэшируется, скругления — обычные полигоны,
    единый цикл отрисовки 60 к/с со склейкой событий, перерисовка только
    при реальном изменении подсветки, прореживание сетки, отсечение камней;
  * боковая панель 352 px (300 на узком окне): верх прокручивается
    собственным скроллбаром, блок действий закреплён снизу — «Отменить»
    и «Повторить» доступны всегда.

Назначение каждой кнопки — в окне «Правила игры», раздел «Кнопки и отладка».
"""

import json
import math
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
FRAME_MS  = 16
STATE_FILE = "gomoku_ui_state.json"


def other(p):
    return PLAYER_O if p == PLAYER_X else PLAYER_X


def mix(c1, c2, t):
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    a = c1.lstrip("#")
    b = c2.lstrip("#")
    r = round(int(a[0:2], 16) * (1 - t) + int(b[0:2], 16) * t)
    g = round(int(a[2:4], 16) * (1 - t) + int(b[2:4], 16) * t)
    bl = round(int(a[4:6], 16) * (1 - t) + int(b[4:6], 16) * t)
    return "#%02x%02x%02x" % (r, g, bl)


def rr_points(x0, y0, x1, y1, r, steps=3):
    r = max(0.0, min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
    pts = [x0 + r, y0, x1 - r, y0]

    def arc(cx, cy, a0, a1):
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            pts.append(cx + r * math.cos(a))
            pts.append(cy + r * math.sin(a))

    arc(x1 - r, y0 + r, -90, 0)
    pts.append(x1)
    pts.append(y1 - r)
    arc(x1 - r, y1 - r, 0, 90)
    pts.append(x0 + r)
    pts.append(y1)
    arc(x0 + r, y1 - r, 90, 180)
    pts.append(x0)
    pts.append(y0 + r)
    arc(x0 + r, y0 + r, 180, 270)
    return pts


def round_rect(cv, x0, y0, x1, y1, r, **kw):
    if r <= 0.6 or (x1 - x0) < 2 or (y1 - y0) < 2:
        return cv.create_rectangle(x0, y0, x1, y1, **kw)
    return cv.create_polygon(rr_points(x0, y0, x1, y1, r), **kw)


def plural(n, one, few, many):
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return few
    return many


def coord(v):
    return "−" + str(abs(v)) if v < 0 else str(v)


_MEASURE = {}


def measure(font, text):
    key = (id(font), text)
    val = _MEASURE.get(key)
    if val is None:
        if len(_MEASURE) > 4096:
            _MEASURE.clear()
        val = font.measure(text)
        _MEASURE[key] = val
    return val


# ---------------------------------------------------------------- кнопки

class Chip(tk.Canvas):
    """Округлая кнопка. Ширина кэшируется в _cw: поле _w принадлежит tkinter."""

    STYLES = {
        "primary":   (ACCENT,  "#ffffff", ACCENT_H, ACCENT_H),
        "secondary": (SURFACE, TEXT,      SURF_HI,  LINE_HI),
        "ghost":     (PANEL,   MUTED,     PANEL_HI, LINE),
        "danger":    (DANGER,  "#ffffff", "#9c3126", "#9c3126"),
        "toggle":    (SURFACE, MUTED,     SURF_HI,  LINE_HI),
        "toggle_on": (ACCENT,  "#ffffff", ACCENT_H, ACCENT_H),
    }

    def __init__(self, master, text, command=None, kind="secondary",
                 height=38, radius=10, font=None, parent_bg=None, width=None):
        pbg = parent_bg or master.cget("bg")
        nat = width if width else max(38, measure(font, text) + 28 if font else 120)
        super().__init__(master, width=nat, height=height, bg=pbg,
                         highlightthickness=0, bd=0, takefocus=0)
        self.pbg = pbg
        self.text = text
        self.command = command
        self.kind = kind
        self.radius = radius
        self.font = font
        self.enabled = True
        self._hover = False
        self._press = False
        self._h = height
        self._nat = nat
        self._cw = 0
        self.bind("<Configure>", self._conf)
        if command is not None:
            self.configure(cursor="hand2")
            self.bind("<Enter>", self._enter)
            self.bind("<Leave>", self._leave)
            self.bind("<ButtonPress-1>", self._down)
            self.bind("<ButtonRelease-1>", self._up)
        self._redraw()

    def _conf(self, e):
        if e.width != self._cw:
            self._cw = e.width
            self._redraw()

    def _enter(self, _):
        if self.enabled and not self._hover:
            self._hover = True
            self._redraw()

    def _leave(self, _):
        if self._hover or self._press:
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
        if was and self.enabled and self.command and \
                0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
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
        w = self._cw or self._nat
        h = self._h
        bg, fg, hov, br = self.STYLES.get(self.kind, self.STYLES["secondary"])
        if not self.enabled:
            bg, fg, br = SURF_HI, DIM, LINE
        elif self._press:
            bg, br = hov, hov
        elif self._hover:
            bg = hov
        round_rect(self, 1, 1, w - 1, h - 1, self.radius,
                   fill=bg, outline=br, width=1)
        self.create_text(w / 2, h / 2 + (1 if self._press and self.enabled else 0),
                         text=self.text, fill=fg, font=self.font, anchor="center")


class PlayerChip(tk.Canvas):
    def __init__(self, master, mark, on_click, font_sym, font_name, parent_bg=None):
        super().__init__(master, width=140, height=46,
                         bg=parent_bg or master.cget("bg"),
                         highlightthickness=0, bd=0, takefocus=0)
        self.mark = mark
        self.on_click = on_click
        self.font_sym = font_sym
        self.font_name = font_name
        self.name = ""
        self.active = False
        self.editable = True
        self._hover = False
        self._cw = 0
        self._short = ""
        self._short_key = None
        self.configure(cursor="hand2")
        self.bind("<Configure>", self._conf)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonRelease-1>", self._click)
        self._redraw()

    def _conf(self, e):
        if e.width != self._cw:
            self._cw = e.width
            self._redraw()

    def _enter(self, _):
        if self.editable and not self._hover:
            self._hover = True
            self._redraw()

    def _leave(self, _):
        if self._hover:
            self._hover = False
            self._redraw()

    def _click(self, _):
        if self.editable and self.on_click:
            self.on_click()

    def set_state(self, name, active, editable):
        if (name, active, editable) != (self.name, self.active, self.editable):
            self.name = name
            self.active = active
            self.editable = editable
            self.configure(cursor="hand2" if editable else "")
            self._redraw()

    def _fit(self, w):
        key = (self.name, w)
        if self._short_key == key:
            return self._short
        avail = max(10, w - 48)
        name = self.name
        if measure(self.font_name, name) > avail:
            lo, hi = 0, len(name)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if measure(self.font_name, name[:mid] + "…") <= avail:
                    lo = mid
                else:
                    hi = mid - 1
            name = (name[:lo] + "…") if lo else "…"
        self._short_key = key
        self._short = name
        return name

    def _redraw(self):
        self.delete("all")
        w = self._cw or 140
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
        self.create_text(40, h / 2, text=self._fit(w), fill=TEXT,
                         font=self.font_name, anchor="w")
        if self.active:
            self.create_oval(w - 15, h / 2 - 3, w - 9, h / 2 + 3,
                             fill=col, outline="")


# ---------------------------------------------------------------- приложение

class GomokuApp:
    SIDE_W = 352
    SIDE_NARROW = 300

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Крестики-нолики: Пять в ряд")
        self.root.configure(bg=BG)
        self.root.geometry("1240x820")
        self.root.minsize(900, 560)

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
        self._loop = False
        self._dirty = True
        self._last_draw = 0.0
        self._bg_size = None
        self._hud_hits = []
        self._hover_key = None
        self._cursor = "crosshair"
        self._hint_on = True
        self._help_win = None
        self._an_win = None
        self._rec_win = None
        self._reset_armed = False
        self._side_w = self.SIDE_W
        self._sy = 0
        self._content_h = 1
        self._view_h = 1
        self._sb_drag = None
        self._sb_hover = False

        self._load_state()
        self._build()
        self._sync()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(40, self._first_layout)

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
                        best = v.get("best")
                        self.records[str(k)] = {
                            "wins": max(0, int(v.get("wins", 0))),
                            "losses": max(0, int(v.get("losses", 0))),
                            "best": best if isinstance(best, int) and best > 0 else None,
                        }
        except Exception:
            pass

    def _save_state(self):
        try:
            with open(self._state_path(), "w", encoding="utf-8") as f:
                json.dump({"mode": self.mode, "human_is_x": self.human_is_x,
                           "pvp_swap": self.pvp_swap, "records": self.records},
                          f, ensure_ascii=False, indent=2)
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

        logo = tk.Canvas(top, width=46, height=46, bg=BG, highlightthickness=0, bd=0)
        logo.pack(side=tk.LEFT)
        round_rect(logo, 1, 1, 45, 45, 14, fill=PANEL, outline=LINE_HI, width=1)
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
                                height=32, radius=16, font=self.F_SMALL,
                                parent_bg=BG, width=104)
        self.btn_records.pack(side=tk.RIGHT, padx=(6, 0))
        self.btn_help = Chip(acts, "?", self.open_help, "ghost", height=32,
                             radius=16, font=self.F_UI, parent_bg=BG, width=34)
        self.btn_help.pack(side=tk.RIGHT)

        body = tk.Frame(outer, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        self.side = tk.Frame(body, bg=PANEL, width=self._side_w,
                             highlightthickness=1, highlightbackground=LINE,
                             highlightcolor=LINE)
        self.side.pack(side=tk.RIGHT, fill=tk.Y, padx=(16, 0))
        self.side.pack_propagate(False)

        self.board_frame = tk.Frame(body, bg=LINE, highlightthickness=1,
                                    highlightbackground=LINE, highlightcolor=LINE)
        self.board_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(self.board_frame, width=320, height=240,
                                bg=BOARD_A, highlightthickness=0, bd=0,
                                takefocus=1, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        actions = tk.Frame(self.side, bg=PANEL)
        actions.pack(side=tk.BOTTOM, fill=tk.X, padx=15, pady=(8, 14))
        tk.Frame(self.side, bg=LINE, height=1).pack(side=tk.BOTTOM, fill=tk.X,
                                                    padx=15)

        self.primary = Chip(actions, "Начать игру", self.primary_action, "primary",
                            height=42, radius=10, font=self.F_UI)
        self.primary.pack(fill=tk.X)
        pair = tk.Frame(actions, bg=PANEL)
        pair.pack(fill=tk.X, pady=(7, 0))
        pair.columnconfigure(0, weight=1, uniform="a")
        pair.columnconfigure(1, weight=1, uniform="a")
        self.undo_btn = Chip(pair, "↶ Отменить", self.undo, "secondary",
                             height=38, radius=9, font=self.F_SMALL, width=100)
        self.undo_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.redo_btn = Chip(pair, "↷ Повторить", self.redo, "secondary",
                             height=38, radius=9, font=self.F_SMALL, width=100)
        self.redo_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.resume_btn = Chip(actions, "Ход ИИ — продолжить", self.resume_ai,
                               "secondary", height=36, radius=9, font=self.F_SMALL)
        self.resume_btn.pack(fill=tk.X, pady=(7, 0))
        self.rules_btn = Chip(actions, "Правила игры", self.open_help, "ghost",
                              height=34, radius=9, font=self.F_SMALL)
        self.rules_btn.pack(fill=tk.X, pady=(7, 0))
        tk.Label(actions, text="U — отменить · Y — повторить · ? — правила",
                 bg=PANEL, fg=DIM, font=self.F_TINY, anchor="w").pack(fill=tk.X,
                                                                      pady=(8, 0))

        wrap = tk.Frame(self.side, bg=PANEL)
        wrap.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=(15, 9), pady=(14, 6))
        self._scv = tk.Canvas(wrap, width=10, height=10, bg=PANEL,
                              highlightthickness=0, bd=0, takefocus=0)
        self._sbar = tk.Canvas(wrap, width=8, height=10, bg=PANEL,
                               highlightthickness=0, bd=0, takefocus=0)
        self._sbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(4, 0))
        self._scv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inner = tk.Frame(self._scv, bg=PANEL)
        self._inner = inner
        self._swin = self._scv.create_window(0, 0, anchor="nw", window=inner)
        inner.bind("<Configure>", self._content_conf)
        self._scv.bind("<Configure>", self._scroll_conf)
        self._sbar.bind("<Configure>", lambda e: self._draw_sbar())
        self._sbar.bind("<ButtonPress-1>", self._sb_down)
        self._sbar.bind("<B1-Motion>", self._sb_move)
        self._sbar.bind("<ButtonRelease-1>", lambda e: setattr(self, "_sb_drag", None))
        self._sbar.bind("<Enter>", self._sb_enter)
        self._sbar.bind("<Leave>", self._sb_leave)

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
        self.status = tk.Label(sci, text="", bg=PANEL_HI, fg=TEXT, font=self.F_STAT,
                               anchor="w", justify="left", wraplength=270)
        self.status.pack(fill=tk.X, pady=(5, 0))
        self.moves_line = tk.Label(sci, text="", bg=PANEL_HI, fg=ACCENT,
                                   font=self.F_SMALL, anchor="w")
        self.moves_line.pack(fill=tk.X, pady=(7, 0))
        self.meta = tk.Label(sci, text="", bg=PANEL_HI, fg=DIM, font=self.F_TINY,
                             anchor="w")
        self.meta.pack(fill=tk.X, pady=(2, 0))
        self.sc, self.sci, self.status_head = sc, sci, head

        pl = tk.Frame(inner, bg=PANEL)
        pl.pack(fill=tk.X, pady=(13, 0))
        plh = tk.Frame(pl, bg=PANEL)
        plh.pack(fill=tk.X)
        tk.Label(plh, text="ИГРОКИ", bg=PANEL, fg=MUTED,
                 font=self.F_EYE).pack(side=tk.LEFT)
        self.swap_btn = Chip(plh, "⇄", self.swap_players, "ghost", height=24,
                             radius=8, font=self.F_SMALL, width=30)
        self.swap_btn.pack(side=tk.RIGHT)
        self.pl_hint = tk.Label(pl, text="", bg=PANEL, fg=DIM, font=self.F_TINY,
                                anchor="w")
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

        md = tk.Frame(inner, bg=PANEL)
        md.pack(fill=tk.X, pady=(13, 0))
        tk.Label(md, text="РЕЖИМ ПАРТИИ", bg=PANEL, fg=MUTED,
                 font=self.F_EYE).pack(anchor="w", pady=(0, 5))
        mrow = tk.Frame(md, bg=PANEL)
        mrow.pack(fill=tk.X)
        mrow.columnconfigure(0, weight=1, uniform="m")
        mrow.columnconfigure(1, weight=1, uniform="m")
        self.mode_ai = Chip(mrow, "С компьютером", lambda: self.set_mode("ai"),
                            "toggle", height=34, radius=9, font=self.F_SMALL,
                            width=100)
        self.mode_ai.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.mode_pvp = Chip(mrow, "Два игрока", lambda: self.set_mode("pvp"),
                             "toggle", height=34, radius=9, font=self.F_SMALL,
                             width=100)
        self.mode_pvp.grid(row=0, column=1, sticky="ew", padx=(4, 0))

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
        specs = [("Анализ 1", self.copy_analysis, 0, 0),
                 ("Партия 2", self.copy_game, 0, 1),
                 ("Всё 3", self.copy_all, 0, 2),
                 ("Просмотр A", self.open_analyses, 1, 0),
                 ("Сохранить S", self.save_game, 1, 1),
                 ("Центр C", self.center_last, 1, 2)]
        for text, cmd, r, c in specs:
            b = Chip(grid, text, cmd, "secondary", height=30, radius=8,
                     font=self.F_TINY, width=70)
            b.grid(row=r, column=c, sticky="ew",
                   padx=(0 if c == 0 else 3, 0 if c == 2 else 3), pady=(0, 5))

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
        self.root.bind("<MouseWheel>", self._on_root_wheel)
        self.root.bind("<Configure>", self._on_root_conf)

    def _on_root_conf(self, e):
        if e.widget is not self.root:
            return
        want = self.SIDE_W if e.width >= 1080 else self.SIDE_NARROW
        if want != self._side_w:
            self._side_w = want
            self.side.configure(width=want)

    def _first_layout(self):
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        if self.width <= 1:
            self.width, self.height = w, h
            self.view["x"] = w / 2 - BASE / 2
            self.view["y"] = h / 2 - BASE / 2
        self.schedule()

    # ------------------------------------------------------- прокрутка панели

    def _content_conf(self, e):
        self._content_h = max(1, e.height)
        self._scv.configure(scrollregion=(0, 0, e.width, self._content_h))
        self._clamp_scroll()
        self._draw_sbar()

    def _scroll_conf(self, e):
        self._view_h = max(1, e.height)
        self._scv.itemconfigure(self._swin, width=e.width)
        self.status.configure(wraplength=max(170, e.width - 32))
        self._clamp_scroll()
        self._draw_sbar()

    def _max_scroll(self):
        return max(0, self._content_h - self._view_h)

    def _clamp_scroll(self):
        m = self._max_scroll()
        self._sy = 0 if self._sy < 0 else (m if self._sy > m else self._sy)
        if self._content_h > 0:
            self._scv.yview_moveto(self._sy / self._content_h)

    def _scroll_by(self, dy):
        if self._max_scroll() <= 0:
            return
        self._sy += dy
        self._clamp_scroll()
        self._draw_sbar()

    def _draw_sbar(self):
        sb = self._sbar
        sb.delete("all")
        h = sb.winfo_height()
        if h <= 1 or self._max_scroll() <= 0:
            return
        round_rect(sb, 1, 0, 7, h, 3, fill=SURFACE, outline="")
        th = max(30, h * self._view_h / self._content_h)
        ty = (self._sy / self._max_scroll()) * (h - th)
        round_rect(sb, 1, ty, 7, ty + th, 3,
                   fill=ACCENT if (self._sb_hover or self._sb_drag) else LINE_HI,
                   outline="")

    def _sb_enter(self, _):
        self._sb_hover = True
        self._draw_sbar()

    def _sb_leave(self, _):
        self._sb_hover = False
        self._draw_sbar()

    def _sb_down(self, e):
        if self._max_scroll() <= 0:
            return
        h = self._sbar.winfo_height()
        th = max(30, h * self._view_h / self._content_h)
        ty = (self._sy / self._max_scroll()) * (h - th)
        if ty <= e.y <= ty + th:
            self._sb_drag = (e.y, self._sy)
        else:
            self._sy = (e.y - th / 2) / max(1, h - th) * self._max_scroll()
            self._clamp_scroll()
            self._draw_sbar()
            self._sb_drag = (e.y, self._sy)

    def _sb_move(self, e):
        if not self._sb_drag:
            return
        y0, s0 = self._sb_drag
        h = self._sbar.winfo_height()
        th = max(30, h * self._view_h / self._content_h)
        self._sy = s0 + (e.y - y0) / max(1, h - th) * self._max_scroll()
        self._clamp_scroll()
        self._draw_sbar()

    def _on_root_wheel(self, e):
        if self._help_win or self._an_win or self._rec_win:
            return
        try:
            x0 = self._scv.winfo_rootx()
            y0 = self._scv.winfo_rooty()
        except Exception:
            return
        if x0 <= e.x_root <= x0 + self._scv.winfo_width() and \
                y0 <= e.y_root <= y0 + self._scv.winfo_height():
            self._scroll_by(-40 if e.delta > 0 else 40)

    # ------------------------------------------------------- геометрия поля

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
        if self.width > 1:
            self.view["x"] += (w - self.width) / 2
            self.view["y"] += (h - self.height) / 2
        else:
            self.view["x"] = w / 2 - BASE / 2
            self.view["y"] = h / 2 - BASE / 2
        self.width, self.height = w, h
        self.hover = None
        self._hover_key = None
        self.schedule()

    def set_zoom_at(self, z, px=None, py=None):
        z = max(MIN_ZOOM, min(MAX_ZOOM, z))
        if abs(z - self.view["zoom"]) < 1e-6:
            return
        px = self.width / 2 if px is None else px
        py = self.height / 2 if py is None else py
        wx, wy = self.wx(px), self.wy(py)
        self.view["zoom"] = z
        self.view["x"] = px - wx * BASE * z
        self.view["y"] = py - wy * BASE * z
        self.view_anim = None
        self._hover_key = None
        self.schedule()

    def animate_to(self, target, dur=0.30):
        if self.width <= 1:
            self.view.update(target)
            self.schedule()
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
        px, py = self.sx(x) + cs / 2, self.sy(y) + cs / 2
        m = 70
        if m < px < self.width - m and m < py < self.height - m:
            return
        z = self.view["zoom"]
        self.animate_to({"x": self.width / 2 - (x + 0.5) * BASE * z,
                         "y": self.height / 2 - (y + 0.5) * BASE * z, "zoom": z})

    def ensure_line_visible(self):
        m = 64
        for x, y in self.win_line:
            px, py = self.sx(x) + self.cs() / 2, self.sy(y) + self.cs() / 2
            if not (m < px < self.width - m and m < py < self.height - m):
                self.fit_to_moves(True)
                return

    # ------------------------------------------------------- цикл отрисовки

    def schedule(self):
        self._dirty = True
        if self._loop:
            return
        wait = FRAME_MS / 1000.0 - (time.perf_counter() - self._last_draw)
        delay = int(wait * 1000) + 1 if wait > 0 else 0
        self._loop = True
        self.root.after(delay, self._tick)

    def _tick(self):
        self._loop = False
        ts = time.perf_counter()
        anim = self._has_anim(ts)
        if self._dirty or anim:
            self._dirty = False
            self._last_draw = ts
            self.draw(ts)
            anim = self._has_anim(ts)
        if anim or self._dirty:
            self._loop = True
            self.root.after(FRAME_MS, self._tick)

    def _has_anim(self, ts):
        if self.view_anim:
            return True
        if self.win_line and ts - self.win_start < 0.62:
            return True
        for born in self.anim.values():
            if ts - born < 0.24:
                return True
        return False

    def _dragging(self):
        return bool(self.drag and self.drag.get("moved"))

    def draw(self, ts=None):
        ts = ts if ts is not None else time.perf_counter()
        if self.width <= 1:
            return
        if self.view_anim:
            a = self.view_anim
            t = (ts - a["t0"]) / a["dur"]
            t = 0.0 if t < 0 else (1.0 if t > 1 else t)
            e = 1 - (1 - t) ** 3
            for k in ("x", "y", "zoom"):
                self.view[k] = a["from"][k] + (a["to"][k] - a["from"][k]) * e
            if t >= 1:
                self.view_anim = None
        cv = self.canvas
        if self._bg_size != (self.width, self.height):
            cv.delete("bg")
            self._draw_bg()
            self._bg_size = (self.width, self.height)
        cv.delete("dyn")
        self._hud_hits = []
        self._draw_fills()
        self._draw_grid()
        if not self._dragging():
            self._draw_labels()
        self._draw_stones(ts)
        self._draw_win(ts)
        self._draw_ghost()
        self._draw_hud()

    def _draw_bg(self):
        cv = self.canvas
        n = 26
        h = self.height
        for i in range(n):
            t = i / (n - 1)
            base = mix(BOARD_A, BOARD_B, t)
            glow = max(0.0, 1 - abs(t - 0.42) / 0.62)
            col = mix(base, "#ffffff", glow * 0.55)
            cv.create_rectangle(0, h * i / n, self.width, h * (i + 1) / n + 1,
                                fill=col, outline="", tags="bg")

    def _draw_fills(self):
        cv = self.canvas
        cs = self.cs()
        for x, y in self.win_line:
            px, py = self.sx(x), self.sy(y)
            if px > self.width or px + cs < 0 or py > self.height or py + cs < 0:
                continue
            cv.create_rectangle(px + 1, py + 1, px + cs - 1, py + cs - 1,
                                fill=mix(WIN_C, BOARD_A, 0.88), outline="",
                                tags="dyn")
        if self.hover and self._can_place():
            hx = int(math.floor(self.wx(self.hover[0])))
            hy = int(math.floor(self.wy(self.hover[1])))
            if self.board.is_empty(hx, hy):
                px, py = self.sx(hx), self.sy(hy)
                cv.create_rectangle(px + 1, py + 1, px + cs - 1, py + cs - 1,
                                    fill=mix(INFO, BOARD_A, 0.93), outline="",
                                    tags="dyn")

    def _draw_grid(self):
        cv = self.canvas
        cs = self.cs()
        step = 1 if cs >= 15 else 5
        x0 = int(math.floor((0 - self.view["x"]) / cs)) - 1
        x1 = int(math.ceil((self.width - self.view["x"]) / cs)) + 1
        y0 = int(math.floor((0 - self.view["y"]) / cs)) - 1
        y1 = int(math.ceil((self.height - self.view["y"]) / cs)) + 1
        for x in range(x0, x1 + 1):
            if step > 1 and x % 5 and x != 0:
                continue
            px = round(self.sx(x)) + 0.5
            col = GRID_AX if x == 0 else (GRID_5 if x % 5 == 0 else GRID_1)
            cv.create_line(px, 0, px, self.height, fill=col, tags="dyn")
        for y in range(y0, y1 + 1):
            if step > 1 and y % 5 and y != 0:
                continue
            py = round(self.sy(y)) + 0.5
            col = GRID_AX if y == 0 else (GRID_5 if y % 5 == 0 else GRID_1)
            cv.create_line(0, py, self.width, py, fill=col, tags="dyn")

    def _draw_labels(self):
        cs = self.cs()
        if cs < 27:
            return
        cv = self.canvas
        col = mix(DIM, BOARD_A, 0.30)
        x0 = int(math.floor((0 - self.view["x"]) / cs))
        x1 = int(math.floor((self.width - self.view["x"]) / cs))
        y0 = int(math.floor((0 - self.view["y"]) / cs))
        y1 = int(math.floor((self.height - self.view["y"]) / cs))
        for x in range((x0 // 5) * 5, x1 + 1, 5):
            if x == 0:
                continue
            px = self.sx(x) + cs / 2
            if 30 < px < self.width - 30:
                cv.create_text(px, 9, text=coord(x), fill=col,
                               font=self.F_TINY, anchor="n", tags="dyn")
        for y in range((y0 // 5) * 5, y1 + 1, 5):
            if y == 0:
                continue
            py = self.sy(y) + cs / 2
            if 30 < py < self.height - 30:
                cv.create_text(9, py, text=coord(y), fill=col,
                               font=self.F_TINY, anchor="w", tags="dyn")

    def _mark(self, cx, cy, mark, cs, color, scale=1.0, glow=False):
        cv = self.canvas
        half = cs * 0.29 * scale
        if mark == PLAYER_X:
            w = max(2, cs * 0.10 * scale)
            if glow:
                soft = mix(color, BOARD_A, 0.72)
                cv.create_line(cx - half, cy - half, cx + half, cy + half,
                               fill=soft, width=w + 6, capstyle=tk.ROUND, tags="dyn")
                cv.create_line(cx + half, cy - half, cx - half, cy + half,
                               fill=soft, width=w + 6, capstyle=tk.ROUND, tags="dyn")
            cv.create_line(cx - half, cy - half, cx + half, cy + half,
                           fill=color, width=w, capstyle=tk.ROUND, tags="dyn")
            cv.create_line(cx + half, cy - half, cx - half, cy + half,
                           fill=color, width=w, capstyle=tk.ROUND, tags="dyn")
        else:
            w = max(2, cs * 0.09 * scale)
            if glow:
                cv.create_oval(cx - half, cy - half, cx + half, cy + half,
                               outline=mix(color, BOARD_A, 0.72), width=w + 6,
                               tags="dyn")
            cv.create_oval(cx - half, cy - half, cx + half, cy + half,
                           outline=color, width=w, tags="dyn")

    def _draw_stones(self, ts):
        cs = self.cs()
        pad = cs * 1.2
        glow_ok = cs >= 20
        last = self.last_move[:2] if self.last_move else None
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
                    e = 1 - (1 - age / 0.23) ** 3
                    scale = 0.62 + 0.38 * e
                    alpha = e
                elif age >= 0.23:
                    self.anim.pop((x, y), None)
            is_last = last == (x, y)
            base = LAST_C if is_last else (X_COLOR if p == PLAYER_X else O_COLOR)
            col = mix(base, BOARD_A, 1 - alpha)
            self._mark(cx, cy, p, cs, col, scale, glow=is_last and glow_ok)

    def _draw_win(self, ts):
        if not self.win_line:
            return
        cs = self.cs()
        t = (ts - self.win_start) / 0.43
        t = 0.0 if t < 0 else (1.0 if t > 1 else t)
        e = 1 - (1 - t) ** 3
        x1, y1 = self.win_line[0]
        x2, y2 = self.win_line[-1]
        ax, ay = self.sx(x1) + cs / 2, self.sy(y1) + cs / 2
        bx, by = self.sx(x2) + cs / 2, self.sy(y2) + cs / 2
        dx, dy = bx - ax, by - ay
        ln = math.hypot(dx, dy) or 1
        over = cs * 0.3
        sx, sy = ax - dx / ln * over, ay - dy / ln * over
        fx, fy = ax + dx * e + dx / ln * over * e, ay + dy * e + dy / ln * over * e
        cv = self.canvas
        cv.create_line(sx, sy, fx, fy, fill=mix(WIN_C, BOARD_A, 0.80),
                       width=max(10, cs * 0.34), capstyle=tk.ROUND, tags="dyn")
        cv.create_line(sx, sy, fx, fy, fill=WIN_C, width=max(2, cs * 0.055),
                       capstyle=tk.ROUND, tags="dyn")

    def _draw_ghost(self):
        if not self.hover or not self._can_place() or self._dragging():
            return
        hx = int(math.floor(self.wx(self.hover[0])))
        hy = int(math.floor(self.wy(self.hover[1])))
        if not self.board.is_empty(hx, hy):
            return
        cs = self.cs()
        mark = self.turn if self.mode == "pvp" else self.human_mark
        base = X_COLOR if mark == PLAYER_X else O_COLOR
        self._mark(self.sx(hx) + cs / 2, self.sy(hy) + cs / 2, mark, cs,
                   mix(base, BOARD_A, 0.76), 0.92)

    # ------------------------------------------------------- HUD

    def _pill(self, x, y, text, fg, anchor="w", border=None):
        w = measure(self.F_TINY, text) + 20
        h = 24
        x0 = x if anchor == "w" else x - w
        round_rect(self.canvas, x0, y, x0 + w, y + h, 12,
                   fill=mix(PANEL, BOARD_A, 0.12), outline=border or LINE,
                   width=1, tags="dyn")
        self.canvas.create_text(x0 + 10, y + h / 2, text=text, fill=fg,
                                font=self.F_TINY, anchor="w", tags="dyn")

    def _hud_button(self, x0, y0, w, h, text, action, font=None, idx=0):
        hot = self._hover_key is not None and self._hover_key[2] == idx
        round_rect(self.canvas, x0, y0, x0 + w, y0 + h, 10,
                   fill=PANEL if hot else mix(PANEL, BOARD_A, 0.18),
                   outline=ACCENT if hot else LINE_HI, width=1, tags="dyn")
        self.canvas.create_text(x0 + w / 2, y0 + h / 2, text=text,
                                fill=ACCENT if hot else MUTED,
                                font=font or self.F_UI, anchor="center", tags="dyn")
        self._hud_hits.append((x0, y0, x0 + w, y0 + h, action))

    def _draw_hud(self):
        cv = self.canvas
        cx = int(math.floor(self.wx(self.width / 2)))
        cy = int(math.floor(self.wy(self.height / 2)))
        self._pill(14, 12, "поле ∞ · %s : %s" % (coord(cx), coord(cy)), MUTED)
        if self.last_move:
            lx, ly, lp = self.last_move
            self._pill(self.width - 14, 12,
                       "последний: %s · %s : %s" % (player_name(lp), coord(lx), coord(ly)),
                       LAST_C, anchor="e", border=mix(LAST_C, PANEL, 0.55))
        else:
            self._pill(self.width - 14, 12, "последний ход —", DIM, anchor="e")

        if self.finished and self.result is not None:
            n = self.x_count()
            who = self.name_of(self.result)
            tail = "за %d %s" % (n, plural(n, "ход", "хода", "ходов"))
            sub = ("Вы собрали пять · " + tail) if (
                self.mode == "ai" and self.result == self.human_mark) else (
                "%s собрал пять · %s" % (who, tail))
            w = max(280, measure(self.F_BANS, sub) + 56)
            h = 74
            x0 = (self.width - w) / 2
            y0 = 52
            round_rect(cv, x0, y0 + 4, x0 + w, y0 + h + 4, 16,
                       fill=mix(BANNER_BR, BOARD_B, 0.72), outline="", tags="dyn")
            round_rect(cv, x0, y0, x0 + w, y0 + h, 16,
                       fill=BANNER_BG, outline=BANNER_BR, width=2, tags="dyn")
            cv.create_text(self.width / 2, y0 + 26, text="ПОБЕДА!",
                           fill=BANNER_T, font=self.F_BAN, tags="dyn")
            cv.create_text(self.width / 2, y0 + 54, text=sub,
                           fill=DANGER, font=self.F_BANS, tags="dyn")

        bw, bh, gap, zw = 36, 32, 6, 58
        total = bw * 3 + zw + gap * 3
        x = (self.width - total) / 2
        y = self.height - 14 - bh
        self._hud_button(x, y, bw, bh, "−",
                         lambda: self.set_zoom_at(self.view["zoom"] / 1.18), idx=1)
        x += bw + gap
        self._hud_button(x, y, zw, bh, "%d%%" % round(self.view["zoom"] * 100),
                         lambda: self.set_zoom_at(1.0), font=self.F_SMALL, idx=2)
        x += zw + gap
        self._hud_button(x, y, bw, bh, "+",
                         lambda: self.set_zoom_at(self.view["zoom"] * 1.18), idx=3)
        x += bw + gap
        self._hud_button(x, y, bw, bh, "⌖", self.center_last, idx=4)

        if self._hint_on and self.started and not self._dragging():
            txt = "Тяните поле левой кнопкой · колесо — масштаб"
            tw = measure(self.F_TINY, txt) + 22
            x0 = (self.width - tw) / 2
            y0 = y - 32
            round_rect(cv, x0, y0, x0 + tw, y0 + 24, 12,
                       fill=mix(PANEL, BOARD_A, 0.10), outline=LINE,
                       width=1, tags="dyn")
            cv.create_text(self.width / 2, y0 + 12, text=txt, fill=INFO,
                           font=self.F_TINY, tags="dyn")

    def _hit_hud(self, px, py):
        for i, (x0, y0, x1, y1, action) in enumerate(self._hud_hits, 1):
            if x0 <= px <= x1 and y0 <= py <= y1:
                return i, action
        return 0, None

    # ------------------------------------------------------- ввод

    def _can_place(self):
        if not self.started or self.finished or self.thinking:
            return False
        return True if self.mode == "pvp" else self.turn == self.human_mark

    def _set_cursor(self, cur):
        if cur != self._cursor:
            self._cursor = cur
            self.canvas.configure(cursor=cur)

    def _clear_hover(self):
        if self.hover is not None:
            self.hover = None
            self._hover_key = None
            self.schedule()

    def _on_down(self, e):
        self.canvas.focus_set()
        _, action = self._hit_hud(e.x, e.y)
        if action:
            action()
            self.drag = None
            return
        self.drag = {"sx": e.x, "sy": e.y, "lx": e.x, "ly": e.y, "moved": False}
        self.hover = (e.x, e.y)

    def _on_move_drag(self, e):
        d = self.drag
        if not d:
            return
        if abs(e.x - d["sx"]) + abs(e.y - d["sy"]) > 5:
            d["moved"] = True
        if d["moved"]:
            self.view["x"] += e.x - d["lx"]
            self.view["y"] += e.y - d["ly"]
            self.view_anim = None
            self.hover = None
            self._hover_key = None
            self._hint_on = False
            self._set_cursor("fleur")
        d["lx"], d["ly"] = e.x, e.y
        self.schedule()

    def _on_up(self, e):
        d = self.drag
        self.drag = None
        self._set_cursor("crosshair")
        if not d:
            return
        if not d["moved"]:
            self.tap(e.x, e.y)
        self.hover = (e.x, e.y)
        self._hover_key = None
        self.schedule()

    def _on_pan_start(self, e):
        self.drag = {"sx": e.x, "sy": e.y, "lx": e.x, "ly": e.y, "moved": True}
        self._set_cursor("fleur")

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
        if self._dragging():
            return
        idx, _ = self._hit_hud(e.x, e.y)
        if idx:
            key = (None, None, idx)
        elif self._can_place():
            key = (int(math.floor(self.wx(e.x))), int(math.floor(self.wy(e.y))), 0)
        else:
            key = (None, None, 0)
        self.hover = (e.x, e.y)
        self._set_cursor("hand2" if idx else "crosshair")
        if key != self._hover_key:
            self._hover_key = key
            self.schedule()

    def _on_wheel(self, e):
        self._hint_on = False
        self.set_zoom_at(self.view["zoom"] * (1.16 ** (e.delta / 120.0)), e.x, e.y)
        return "break"

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
        x = int(math.floor(self.wx(px)))
        y = int(math.floor(self.wy(py)))
        if not self.board.is_empty(x, y):
            self.note("Клетка %s : %s уже занята" % (coord(x), coord(y)))
            return
        self.human_move(x, y)

    def _on_key(self, e):
        if self._help_win or self._an_win or self._rec_win:
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
            self.set_zoom_at(self.view["zoom"] * 1.18)
            return
        elif k in ("minus", "KP_Subtract"):
            self.set_zoom_at(self.view["zoom"] / 1.18)
            return
        elif k in ("0", "Home"):
            self.fit_to_moves(True)
            return
        elif k in ("c", "C", "с", "С"):
            self.center_last()
            return
        elif k in ("u", "U", "г", "Г") or (e.state & 4 and k.lower() == "z"):
            self.undo()
            return
        elif k in ("y", "Y", "н", "Н"):
            self.redo()
            return
        elif k in ("n", "N", "т", "Т"):
            self.primary_action()
            return
        elif k in ("question", "F1", "h", "H"):
            self.open_help()
            return
        elif k == "1":
            self.copy_analysis()
            return
        elif k == "2":
            self.copy_game()
            return
        elif k == "3":
            self.copy_all()
            return
        elif k in ("a", "A", "ф", "Ф"):
            self.open_analyses()
            return
        elif k in ("s", "S", "ы", "Ы"):
            self.save_game()
            return
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
        if self.started:
            self.to_setup()
        else:
            self.begin_game()

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
        self._hover_key = None
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
            try:
                self.root.after(0, lambda: self.ai_done(gen, move, text, err, dt))
            except Exception:
                pass

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
        self.gen += 1
        self.finished = True
        self.thinking = False
        self.result = p
        self.turn = p
        self.win_line = line
        self.win_start = time.perf_counter()
        self.record_snapshot = json.loads(json.dumps(self.records))
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
        self.chip_x.set_state(self.name_of(PLAYER_X),
                              self.turn == PLAYER_X and not self.finished, editing)
        self.chip_o.set_state(self.name_of(PLAYER_O),
                              self.turn == PLAYER_O and not self.finished, editing)
        self.swap_btn.set_enabled(editing)
        self.pl_hint.configure(text="Щёлкните по овалу — кто играет X" if editing
                               else "Состав фиксируется на всю партию")
        self.mode_ai.set_kind("toggle_on" if self.mode == "ai" else "toggle")
        self.mode_pvp.set_kind("toggle_on" if self.mode == "pvp" else "toggle")
        self.mode_ai.set_enabled(editing)
        self.mode_pvp.set_enabled(editing)
        self.primary.set_text("Новая игра" if self.started else "Начать игру")
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
            kick, text = "Новая партия", "Выберите, кто играет X, и начните игру"
        elif self.finished and self.result is not None:
            who = self.name_of(self.result)
            if self.mode == "ai" and self.result != self.human_mark:
                kick, text = "Поражение", "%s собрал пять" % who
                bg, dot = mix(DANGER, PANEL, 0.90), DANGER
            else:
                kick = "Победа"
                text = "Вы собрали пять" if self.mode == "ai" else "%s собрал пять" % who
                bg, dot = mix(WIN_C, PANEL, 0.90), WIN_C
        elif self.thinking:
            kick, text = "Компьютер · %s" % player_name(self.ai_mark), "Думает…"
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

        for w in (self.sc, self.sci, self.status_head, self.kicker, self.status,
                  self.moves_line, self.meta, self.dot):
            w.configure(bg=bg)
        self.kicker.configure(text=kick.upper())
        self.status.configure(text=text)
        self.dot.delete("all")
        self.dot.create_oval(1, 1, 9, 9, fill=dot, outline="")

    # ------------------------------------------------------- окна

    def _modal(self, title, w, h):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=PANEL)
        win.transient(self.root)
        win.geometry("%dx%d" % (w, h))
        win.minsize(min(w, 520), min(h, 400))
        x = self.root.winfo_rootx() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - h) // 2
        win.geometry("+%d+%d" % (max(0, x), max(0, y)))
        win.grab_set()
        return win

    @staticmethod
    def _sb(parent, orient="vertical"):
        return tk.Scrollbar(parent, orient=orient, bg=SURF_HI, troughcolor=PANEL_HI,
                            activebackground=ACCENT, highlightthickness=0, bd=0,
                            relief="flat", elementborderwidth=0,
                            width=12 if orient == "vertical" else 11)

    def open_help(self):
        if self._help_win:
            self._help_win.lift()
            return
        win = self._modal("Правила игры", 720, 660)
        self._help_win = win

        def close():
            self._help_win = None
            win.destroy()

        head = tk.Frame(win, bg=PANEL_HI)
        head.pack(fill=tk.X)
        tk.Label(head, text="Правила и управление", bg=PANEL_HI, fg=TEXT,
                 font=self.F_TITLE).pack(side=tk.LEFT, padx=18, pady=14)
        Chip(head, "✕", close, "ghost", height=30, radius=15,
             font=self.F_UI, parent_bg=PANEL_HI, width=34).pack(side=tk.RIGHT,
                                                                padx=14)

        frame = tk.Frame(win, bg=PANEL)
        frame.pack(fill=tk.BOTH, expand=True)
        sb = self._sb(frame)
        txt = tk.Text(frame, wrap="word", bg=PANEL, fg=TEXT, font=self.F_BODY,
                      bd=0, highlightthickness=0, padx=18, pady=16,
                      spacing1=2, spacing3=5, yscrollcommand=sb.set, cursor="arrow")
        sb.configure(command=txt.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        txt.tag_configure("h2", font=self.F_H3, foreground=ACCENT,
                          spacing1=12, spacing3=4)
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
          "Состав и режим доступны только до начала партии.")
        h2("Ход и поле")
        p("Коснитесь свободной клетки левой кнопкой мыши. Зажав левую кнопку, "
          "тяните поле. Колесо меняет масштаб относительно точки под курсором. "
          "Кнопки − / % / + / ⌖ внизу поля дублируют масштаб и центрирование.")
        h2("Счёт ходов")
        p("Строка «Ходов: N» считает ходы крестиков, а не полуходы. Общее число "
          "полуходов показано ниже мелким шрифтом вместе с последним ходом.")
        h2("Кнопки: основная панель")
        kv("Начать игру", "запускает партию с выбранным составом. Во время партии "
                          "кнопка называется «Новая игра» и возвращает к настройке "
                          "состава, очищая поле.")
        kv("↶ Отменить", "снимает один последний полуход. Нажимайте подряд, чтобы "
                         "дойти до самого начала партии. Работает и после победы: "
                         "результат и статистика откатываются.")
        kv("↷ Повторить", "возвращает снятые полуходы по одному. Список возврата "
                          "очищается, как только сделан новый ход.")
        kv("Ход ИИ — продолжить", "активна, если после отмены или возврата очередь "
                                  "за компьютером. Нажмите, чтобы партия пошла "
                                  "дальше с текущей позиции.")
        kv("Правила игры", "это окно.")
        kv("Статистика", "победы, поражения и лучшее число ходов X. Записи хранятся "
                         "на этом устройстве.")
        kv("⇄", "меняет игроков местами, то же, что щелчок по овалу.")
        h2("Кнопки: отладка")
        txt.insert("end", "Нужны для проверки движка, в итоговой версии будут скрыты.\n",
                   "warn")
        kv("Анализ 1", "копирует разбор последнего хода ИИ: шаги поиска, угрозы, "
                       "точки достройки, оценки. Нажимать сразу после хода компьютера.")
        kv("Партия 2", "копирует список всех ходов текстом.")
        kv("Всё 3", "копирует разборы всех ходов ИИ подряд, с номерами и временем.")
        kv("Просмотр A", "окно со списком ходов ИИ и полным анализом выбранного хода. "
                         "Основной инструмент: найти ход, где оценка впервые испортилась.")
        kv("Сохранить S", "пишет JSON со всеми ходами, анализами и временем. "
                          "Файл можно загрузить как тестовую позицию.")
        kv("Центр C", "наводит камеру на последний ход.")
        h2("Клавиши")
        kv("стрелки", "сдвиг поля")
        kv("+ / −", "масштаб")
        kv("0 или Home", "вписать все камни в окно")
        kv("C", "центрировать на последнем ходе")
        kv("U или Ctrl+Z", "отменить ход")
        kv("Y", "повторить ход")
        kv("N", "начать / новая игра")
        kv("? или F1", "это окно")
        kv("1 / 2 / 3 / A / S", "отладочные действия")
        txt.configure(state="disabled")
        Chip(win, "Понятно", close, "primary", height=40,
             font=self.F_UI).pack(fill=tk.X, padx=18, pady=14)
        win.protocol("WM_DELETE_WINDOW", close)
        win.bind("<Escape>", lambda e: close())

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

        def close():
            self._an_win = None
            win.destroy()

        head = tk.Frame(win, bg=PANEL_HI)
        head.pack(fill=tk.X)
        tk.Label(head, text="Разбор ходов компьютера", bg=PANEL_HI, fg=TEXT,
                 font=self.F_TITLE).pack(side=tk.LEFT, padx=18, pady=12)
        Chip(head, "✕", close, "ghost", height=30, radius=15, font=self.F_UI,
             parent_bg=PANEL_HI, width=34).pack(side=tk.RIGHT, padx=14)

        body = tk.Frame(win, bg=PANEL)
        body.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)
        left = tk.Frame(body, bg=PANEL)
        left.pack(side=tk.LEFT, fill=tk.Y)
        lsb = self._sb(left)
        lb = tk.Listbox(left, width=30, bg=PANEL_HI, fg=TEXT, font=self.F_MONO,
                        bd=0, highlightthickness=1, highlightbackground=LINE,
                        selectbackground=ACCENT, selectforeground="#ffffff",
                        activestyle="none", yscrollcommand=lsb.set)
        lsb.configure(command=lb.yview)
        lb.pack(side=tk.LEFT, fill=tk.Y)
        lsb.pack(side=tk.LEFT, fill=tk.Y)

        right = tk.Frame(body, bg=PANEL)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))
        rsb = self._sb(right)
        hsb = self._sb(right, "horizontal")
        txt = tk.Text(right, wrap="none", bg=PANEL_HI, fg=TEXT, font=self.F_MONO,
                      bd=0, highlightthickness=1, highlightbackground=LINE,
                      padx=12, pady=10, yscrollcommand=rsb.set,
                      xscrollcommand=hsb.set, cursor="arrow")
        rsb.configure(command=txt.yview)
        hsb.configure(command=txt.xview)
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
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            txt.insert("end", recs[sel[0]]["analysis"])
            txt.configure(state="disabled")

        lb.bind("<<ListboxSelect>>", select)
        lb.selection_set(0)
        select()
        Chip(win, "Закрыть", close, "secondary", height=36,
             font=self.F_SMALL).pack(fill=tk.X, padx=14, pady=(0, 12))
        win.protocol("WM_DELETE_WINDOW", close)
        win.bind("<Escape>", lambda e: close())

    def open_records(self):
        if self._rec_win:
            self._rec_win.lift()
            return
        win = self._modal("Статистика", 620, 520)
        self._rec_win = win

        def close():
            self._rec_win = None
            self._reset_armed = False
            win.destroy()

        head = tk.Frame(win, bg=PANEL_HI)
        head.pack(fill=tk.X)
        tk.Label(head, text="Рекорды игроков", bg=PANEL_HI, fg=TEXT,
                 font=self.F_TITLE).pack(side=tk.LEFT, padx=18, pady=12)
        Chip(head, "✕", close, "ghost", height=30, radius=15, font=self.F_UI,
             parent_bg=PANEL_HI, width=34).pack(side=tk.RIGHT, padx=14)

        body = tk.Frame(win, bg=PANEL)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)
        tk.Label(body, text="Победы, поражения и лучшее число ходов X, за которое "
                            "собрано пять в ряд.", bg=PANEL, fg=MUTED,
                 font=self.F_BODY, justify="left", wraplength=560).pack(anchor="w")
        box = tk.Frame(body, bg=PANEL_HI, highlightthickness=1,
                       highlightbackground=LINE)
        box.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        sb = self._sb(box)
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
                                      kv[1]["best"] or 10 ** 9, kv[0]))
        txt.insert("end", "%-3s %-22s %7s %9s %8s\n" %
                   ("#", "Игрок", "Победы", "Пораж.", "Мин."), "hd")
        txt.insert("end", "─" * 54 + "\n", "hd")
        if not rows:
            txt.insert("end", "\nПока нет сыгранных партий.\n", "l")
        for i, (name, r) in enumerate(rows, 1):
            nm = name if len(name) <= 22 else name[:21] + "…"
            txt.insert("end", "%-3d %-22s " % (i, nm))
            txt.insert("end", "%7d " % r["wins"], "w")
            txt.insert("end", "%9d " % r["losses"], "l")
            txt.insert("end", "%8s\n" % (r["best"] or "—"), "bst")
        txt.configure(state="disabled")

        btns = tk.Frame(win, bg=PANEL)
        btns.pack(fill=tk.X, padx=16, pady=12)

        def disarm():
            self._reset_armed = False
            rb.set_text("Сбросить таблицу")
            rb.set_kind("secondary")

        def reset():
            if not self._reset_armed:
                self._reset_armed = True
                rb.set_text("Точно сбросить?")
                rb.set_kind("danger")
                win.after(6000, disarm)
                return
            self.records = {}
            self._save_state()
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