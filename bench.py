"""
Замер скорости движка на позициях середины партии.
Запуск:  python bench.py
Результат печатается на экран и сохраняется в bench.txt (UTF-8).
Позиции детерминированные — цифры можно сравнивать между сессиями.
"""
import random
import time

from gomoku import (Board, PLAYER_X, PLAYER_O, get_best_move,
                    evaluate_position, check_five)
from gomoku_analysis import analyze_threats, completion_points


def make_position(n_stones, seed):
    cells = [(x, y) for x in range(-6, 7) for y in range(-6, 7)]
    random.Random(seed).shuffle(cells)
    b = Board()
    for i in range(n_stones):
        x, y = cells[i]
        b.make_move(x, y, PLAYER_X if i % 2 == 0 else PLAYER_O)
    return b


def quiet_position(n_stones):
    """Позиция без готовых пятёрок и без ходов в пятёрку — чтобы мерить именно поиск."""
    for seed in range(200):
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


def main():
    print("Benchmark, please wait...", flush=True)
    lines = []
    for n in (12, 24, 36):
        b = quiet_position(n)
        side = PLAYER_X if n % 2 == 0 else PLAYER_O
        an = ms_per_call(lambda: (analyze_threats(b, PLAYER_X),
                                  analyze_threats(b, PLAYER_O)), 20)
        ev = ms_per_call(lambda: evaluate_position(b, PLAYER_X, to_move=PLAYER_O), 10)
        t0 = time.perf_counter()
        mv = get_best_move(b, side)
        dt = time.perf_counter() - t0
        line = ("stones=%2d  analyze_x2=%7.2f ms  eval=%7.2f ms  "
                "move=%s  move_time=%5.2f s" % (n, an, ev, mv, dt))
        lines.append(line)
        print(line, flush=True)
    with open("bench.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Saved: bench.txt")


if __name__ == "__main__":
    main()