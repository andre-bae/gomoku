"""
T6: очная арена двух конфигураций движка + Elo.
Перед ходом стороны выставляем её выключатели; каждый дебют играем дважды (A=X и A=O).
Прогресс по ходам + предохранители: лимит на ход, лимит на партию, потолок ходов.

Запуск:
  python arena.py base base --pairs 3
  python arena.py base pvstt --pairs 10 --limit 3 --game-limit 180
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
    "pvstt": {"USE_PVS": True, "USE_TT_BEST": True},
}


def apply_config(cfg):
    G.USE_PVS = cfg.get("USE_PVS", False)
    G.USE_TT_BEST = cfg.get("USE_TT_BEST", False)
    G.USE_POSITION_CACHE = True


def opening(seed, stones):
    for s in range(seed, seed + 60):
        b = make_position(stones, s)
        if check_five(b, PLAYER_X) or check_five(b, PLAYER_O):
            continue
        if ga.completion_points(b, PLAYER_X) or ga.completion_points(b, PLAYER_O):
            continue
        return list(b.move_history)
    return list(make_position(stones, seed).move_history)


def play(cfg_x, cfg_o, opens, max_moves, game_limit, tag):
    b = Board()
    for (x, y, p) in opens:
        b.make_move(x, y, p)
    t0 = time.perf_counter()
    while len(b.move_history) < max_moves:
        n = len(b.move_history)
        if time.perf_counter() - t0 > game_limit:
            print("   %s: лимит партии %.0fс на ходу %d — прерываем" % (tag, game_limit, n), flush=True)
            return "abort"
        side = PLAYER_X if n % 2 == 0 else PLAYER_O
        apply_config(cfg_x if side == PLAYER_X else cfg_o)
        mv = get_best_move(b, side)
        if mv is None:
            return "draw"
        x, y = mv
        if not b.make_move(x, y, side):
            print("   %s: ход на занятую клетку %s — порча доски" % (tag, mv), flush=True)
            return "O" if side == PLAYER_X else "X"
        if check_five(b, side):
            return "X" if side == PLAYER_X else "O"
        n = len(b.move_history)
        if n % 10 == 0:
            print("   %s: ход %d, %.0fс" % (tag, n, time.perf_counter() - t0), flush=True)
    return "draw"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a", choices=sorted(CONFIGS))
    ap.add_argument("b", choices=sorted(CONFIGS))
    ap.add_argument("--pairs", type=int, default=3)
    ap.add_argument("--seed0", type=int, default=0)
    ap.add_argument("--limit", type=float, default=3.0, help="секунд на ход")
    ap.add_argument("--game-limit", type=float, default=180.0, help="секунд на партию")
    ap.add_argument("--max-moves", type=int, default=80)
    ap.add_argument("--stones", type=int, default=6, help="камней в дебюте (2 = длиннее партии)")
    args = ap.parse_args()
    G.MOVE_TIME_LIMIT = args.limit
    if hasattr(G, "POSITIONAL_TIME_LIMIT"):
        G.POSITIONAL_TIME_LIMIT = args.limit
    cfg_a, cfg_b = CONFIGS[args.a], CONFIGS[args.b]
    print("Арена %s против %s: пар=%d, лимит хода %.1fс, лимит партии %.0fс, дебют %d камней"
          % (args.a, args.b, args.pairs, args.limit, args.game_limit, args.stones), flush=True)
    lines = ["Арена %s против %s: пар=%d, лимит хода %.1fс" % (args.a, args.b, args.pairs, args.limit)]
    score_a = 0.0
    total = 0
    aborts = 0
    t0 = time.perf_counter()
    for i in range(args.pairs):
        opens = opening(args.seed0 + i * 10, args.stones)
        for a_is_x in (True, False):
            cfg_x, cfg_o = (cfg_a, cfg_b) if a_is_x else (cfg_b, cfg_a)
            tag = "дебют %d A=%s" % (i, "X" if a_is_x else "O")
            print(tag + ": играем...", flush=True)
            winner = play(cfg_x, cfg_o, opens, args.max_moves, args.game_limit, tag)
            if winner == "abort":
                aborts += 1
                s = 0.5
            elif winner == "draw":
                s = 0.5
            elif (winner == "X") == a_is_x:
                s = 1.0
            else:
                s = 0.0
            score_a += s
            total += 1
            line = "%s: победитель=%s, очко A=%.1f" % (tag, winner, s)
            lines.append(line)
            print(line, flush=True)
    p = score_a / total if total else 0.0
    elo_s = "%+.0f" % (-400.0 * math.log10(1.0 / p - 1.0)) if 0.0 < p < 1.0 else "—"
    summary = ("ИТОГ %s против %s: очки A=%.1f/%d (%.0f%%), Elo A=%s, прервано=%d, время %.0fс"
               % (args.a, args.b, score_a, total, 100 * p, elo_s, aborts, time.perf_counter() - t0))
    lines.append(summary)
    print(summary, flush=True)
    with open("arena.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Saved: arena.txt")


if __name__ == "__main__":
    main()