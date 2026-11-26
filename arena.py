"""
T6: очная арена двух конфигураций движка + Elo.
Перед ходом стороны выставляем её выключатели; каждый дебют играем дважды (A=X и A=O).
Детерминированный режим (бюджет узлов, большие лимиты).

Запуск:
  python arena.py base base --pairs 3     # санитарная проверка (~50%)
  python arena.py base pvstt --pairs 3    # base против PVS+TT
Пресеты: base, pvs, tt, kh, pvstt, narrow.  -> arena.txt
"""
import argparse
import math
import time

import gomoku as G
import gomoku_analysis as ga
from gomoku import Board, PLAYER_X, PLAYER_O, get_best_move, check_five
from bench2 import make_position

CONFIGS = {
    "base": {},
    "pvs": {"USE_PVS": True},
    "tt": {"USE_TT_BEST": True},
    "kh": {"USE_KILLER_HISTORY": True},
    "pvstt": {"USE_PVS": True, "USE_TT_BEST": True},
    "narrow": {"USE_NARROW_CANDIDATES": True},
}


def apply_config(cfg):
    G.USE_PVS = cfg.get("USE_PVS", False)
    G.USE_KILLER_HISTORY = cfg.get("USE_KILLER_HISTORY", False)
    G.USE_TT_BEST = cfg.get("USE_TT_BEST", False)
    G.USE_EXTENSIONS = cfg.get("USE_EXTENSIONS", False)
    G.USE_NARROW_CANDIDATES = cfg.get("USE_NARROW_CANDIDATES", False)
    G.USE_POSITION_CACHE = True


def opening(seed):
    for s in range(seed, seed + 60):
        b = make_position(6, s)
        if check_five(b, PLAYER_X) or check_five(b, PLAYER_O):
            continue
        if ga.completion_points(b, PLAYER_X) or ga.completion_points(b, PLAYER_O):
            continue
        return list(b.move_history)
    return list(make_position(6, seed).move_history)


def play(cfg_x, cfg_o, opens, max_moves=120):
    b = Board()
    for (x, y, p) in opens:
        b.make_move(x, y, p)
    while len(b.move_history) < max_moves:
        side = PLAYER_X if len(b.move_history) % 2 == 0 else PLAYER_O
        apply_config(cfg_x if side == PLAYER_X else cfg_o)
        mv = get_best_move(b, side)
        if mv is None:
            return "draw"
        x, y = mv
        if not b.make_move(x, y, side):
            # ход на занятую клетку = порча доски; сторона проигрывает
            return "O" if side == PLAYER_X else "X"
        if check_five(b, side):
            return "X" if side == PLAYER_X else "O"
    return "draw"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a", choices=sorted(CONFIGS))
    ap.add_argument("b", choices=sorted(CONFIGS))
    ap.add_argument("--pairs", type=int, default=3)
    ap.add_argument("--seed0", type=int, default=0)
    args = ap.parse_args()
    G.MOVE_TIME_LIMIT = 1000.0
    if hasattr(G, "POSITIONAL_TIME_LIMIT"):
        G.POSITIONAL_TIME_LIMIT = 1000.0
    cfg_a, cfg_b = CONFIGS[args.a], CONFIGS[args.b]
    print("Арена %s против %s, пар=%d (игр=%d)..." % (args.a, args.b, args.pairs, args.pairs * 2), flush=True)
    lines = ["Арена %s против %s, пар=%d" % (args.a, args.b, args.pairs)]
    score_a = 0.0
    total = 0
    t0 = time.perf_counter()
    for i in range(args.pairs):
        opens = opening(args.seed0 + i * 10)
        for a_is_x in (True, False):
            cfg_x, cfg_o = (cfg_a, cfg_b) if a_is_x else (cfg_b, cfg_a)
            winner = play(cfg_x, cfg_o, opens)
            if winner == "draw":
                s = 0.5
            elif (winner == "X") == a_is_x:
                s = 1.0
            else:
                s = 0.0
            score_a += s
            total += 1
            tag = "A=%s" % ("X" if a_is_x else "O")
            line = "дебют %d %s: победитель=%s, очко A=%.1f" % (i, tag, winner, s)
            lines.append(line)
            print(line, flush=True)
    p = score_a / total if total else 0.0
    if 0.0 < p < 1.0:
        elo = -400.0 * math.log10(1.0 / p - 1.0)
        elo_s = "%+.0f" % elo
    else:
        elo_s = "—"
    summary = ("ИТОГ %s против %s: очки A=%.1f/%d (%.0f%%), Elo A=%s, время %.0fс"
               % (args.a, args.b, score_a, total, 100 * p, elo_s, time.perf_counter() - t0))
    lines.append(summary)
    print(summary, flush=True)
    with open("arena.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Saved: arena.txt")


if __name__ == "__main__":
    main()