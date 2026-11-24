"""
Бенчмарк v2: скорость движка + какой шаг решил ход.
Запуск:  python bench2.py   ->  bench2.txt (UTF-8)
Позиции детерминированные, плотность камней примерно постоянная.
Главный показатель — nodes/s (узлов в секунду).
"""
import random
import time

from gomoku import (Board, PLAYER_X, PLAYER_O, get_best_move, minimax,
                    evaluate_position, check_five, DEBUG_LOG)
from gomoku_analysis import analyze_threats, completion_points, clear_threat_cache


def make_position(n_stones, seed):
    side = max(9, int((n_stones * 7) ** 0.5) + 1)
    half = side // 2
    cells = [(x, y) for x in range(-half, half + 1)
             for y in range(-half, half + 1)]
    random.Random(seed).shuffle(cells)
    b = Board()
    for i in range(n_stones):
        x, y = cells[i]
        b.make_move(x, y, PLAYER_X if i % 2 == 0 else PLAYER_O)
    return b


def quiet_position(n_stones):
    for seed in range(300):
        b = make_position(n_stones, seed)
        if check_five(b, PLAYER_X) or check_five(b, PLAYER_O):
            continue
        if completion_points(b, PLAYER_X) or completion_points(b, PLAYER_O):
            continue
        return b
    return make_position(n_stones, 0)


def ms_per_call(fn, repeats):
    t0 = time.perf_counter()
    for _ in range(repeats):
        fn()
    return (time.perf_counter() - t0) / repeats * 1000.0


def deciding_step():
    step = "?"
    for ln in DEBUG_LOG:
        s = ln.strip()
        if s.startswith("[ШАГ") or s.startswith("[РЕЖИМ"):
            step = s.split("]")[0].lstrip("[")
    return step


def max_depth():
    d = 0
    for ln in DEBUG_LOG:
        s = ln.strip()
        if s.startswith("глубина "):
            try:
                d = max(d, int(s.split(":")[0].split()[1]))
            except Exception:
                pass
    return d


def nodes_per_sec(b, side, n=400):
    budget = [n]
    t0 = time.perf_counter()
    minimax(b, depth=6, alpha=-10**9, beta=10**9, is_maximizing=True,
            player=side, budget=budget, tt={})
    dt = time.perf_counter() - t0
    used = n - budget[0]
    return (used / dt if dt > 0 else 0.0), used


def main():
    import sys
    import gomoku_analysis as ga
    if "--no-pos-cache" in sys.argv:
        ga.USE_POSITION_CACHE = False
    tag = "pos_cache=ON" if ga.USE_POSITION_CACHE else "pos_cache=OFF"
    out = "bench2.txt" if ga.USE_POSITION_CACHE else "bench2_nocache.txt"
    print("Benchmark v2 (%s), please wait..." % tag, flush=True)
    lines = ["режим: %s" % tag]
    for n in (12, 24, 36):
        b = quiet_position(n)
        side = PLAYER_X if n % 2 == 0 else PLAYER_O
        an = ms_per_call(lambda: (clear_threat_cache(),
                                  analyze_threats(b, PLAYER_X),
                                  analyze_threats(b, PLAYER_O)), 20)
        ev = ms_per_call(lambda: (clear_threat_cache(),
                                  evaluate_position(b, PLAYER_X, to_move=PLAYER_O)), 10)
        nps, used = nodes_per_sec(b, side)
        t0 = time.perf_counter()
        mv = get_best_move(b, side)
        mt = time.perf_counter() - t0
        line = ("stones=%2d analyze_x2=%6.2fms eval=%6.2fms nodes/s=%6.0f "
                "move=%s time=%5.2fs depth=%d decided=%s"
                % (n, an, ev, nps, mv, mt, max_depth(), deciding_step()))
        lines.append(line)
        print(line, flush=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Saved: %s" % out)


if __name__ == "__main__":
    main()