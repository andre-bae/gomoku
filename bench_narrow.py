"""
S4 A/B: узкие кандидаты (радиус 1 + угрозы) против радиуса 2.
Чередование в одном процессе, фиксированный бюджет узлов, чистые кэши.
Запуск:  python bench_narrow.py [--quick]   ->  bench_narrow.txt
"""
import argparse
import statistics
import time

import gomoku
import gomoku_analysis as ga
from gomoku import PLAYER_X, PLAYER_O, minimax, get_best_move
from bench2 import quiet_position


def cand_counts(b):
    wide = set(b.get_candidate_moves(radius=2))
    narrow = set(gomoku.narrow_candidate_moves(b))
    return len(wide), len(narrow)


def probe(b, side, narrow, nodes):
    gomoku.USE_NARROW_CANDIDATES = narrow
    ga.clear_threat_cache()
    ga.clear_line_cache()
    ga.clear_window_cache()
    ga.reset_stats()
    budget = [nodes]
    t0 = time.perf_counter()
    val = minimax(b, depth=6, alpha=-10**9, beta=10**9, is_maximizing=True,
                  player=side, budget=budget, tt={})
    dt = time.perf_counter() - t0
    used = nodes - budget[0]
    return (used / dt if dt > 0 else 0.0), used


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()
    nodes = 2000 if args.quick else 8000
    reps = max(1, args.repeats)
    print("S4 A/B кандидатов: nodes=%d repeats=%d..." % (nodes, reps), flush=True)
    lines = ["S4 A/B: узкие (радиус1+угрозы) vs радиус2, nodes=%d" % nodes]
    for n in (12, 24, 36):
        b = quiet_position(n)
        side = PLAYER_X if n % 2 == 0 else PLAYER_O
        wide, narrow = cand_counts(b)
        res = {True: [], False: []}
        for i in range(reps):
            order = (True, False) if i % 2 == 0 else (False, True)
            for flag in order:
                nps, used = probe(b, side, flag, nodes)
                res[flag].append(nps)
        gomoku.USE_NARROW_CANDIDATES = False
        mn = statistics.median(res[True])
        mw = statistics.median(res[False])
        gain = 100.0 * (mn / mw - 1) if mw else 0.0
        moves = {}
        for flag in (False, True):
            gomoku.USE_NARROW_CANDIDATES = flag
            ga.clear_threat_cache(); ga.clear_line_cache(); ga.clear_window_cache()
            moves[flag] = get_best_move(quiet_position(n), side)
        gomoku.USE_NARROW_CANDIDATES = False
        line = ("stones=%2d  клеток wide=%d narrow=%d  узлов/с narrow=%.0f wide=%.0f  "
                "выигрыш=%+.1f%%  ход wide=%s narrow=%s"
                % (n, wide, narrow, mn, mw, gain, moves[False], moves[True]))
        lines.append(line)
        print(line, flush=True)
    with open("bench_narrow.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Saved: bench_narrow.txt")


if __name__ == "__main__":
    main()