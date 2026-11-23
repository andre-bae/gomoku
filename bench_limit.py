"""
Эксперимент: сколько времени реально нужно поиску.
Берёт сохранённую партию и для ОДНИХ И ТЕХ ЖЕ позиций считает ход ИИ
с разными жёсткими лимитами. Отвечает:
  - исчезают ли аварийные ходы при +1 секунде?
  - меняется ли выбранный ход (то есть растёт ли сила)?

Запуск:
    python bench_limit.py
    python bench_limit.py positions/bench_game_1.json
Результат: bench_limit.txt (UTF-8). Восклицательный знак = аварийный ход.
"""
import json
import sys
import time

import gomoku
from gomoku import (Board, PLAYER_X, PLAYER_O, get_best_move,
                    DEBUG_LOG, player_name)

LIMITS = (3.0, 4.0, 5.0)


def load_moves(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for m in data["moves"]:
        p = PLAYER_X if str(m["player"]).strip().upper() == "X" else PLAYER_O
        out.append((int(m["x"]), int(m["y"]), p))
    return out


def depth_reached():
    d = 0
    for ln in DEBUG_LOG:
        s = ln.strip()
        if s.startswith("глубина "):
            try:
                d = max(d, int(s.split(":")[0].split()[1]))
            except Exception:
                pass
    return d


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "positions/bench_game_1.json"
    moves = load_moves(path)
    print("Positions from %s, limits %s" % (path, LIMITS), flush=True)
    report = ["партия: %s" % path, "лимиты, с: %s" % (LIMITS,)]
    rows = []
    for k in range(6, min(len(moves), 21), 2):
        b = Board()
        for x, y, p in moves[:k]:
            b.make_move(x, y, p)
        side = PLAYER_X if k % 2 == 0 else PLAYER_O
        cells = []
        for lim in LIMITS:
            gomoku.MOVE_TIME_LIMIT = lim
            gomoku.POSITIONAL_TIME_LIMIT = lim * 2.0 / 3.0
            t0 = time.perf_counter()
            mv = get_best_move(b.copy(), side)
            dt = time.perf_counter() - t0
            panic = any("время хода исчерпано" in ln for ln in DEBUG_LOG)
            cells.append((lim, dt, depth_reached(), panic, mv))
        rows.append(cells)
        line = ("после %2d ходов (%s): " % (k, player_name(side))) + " | ".join(
            "%.0fs: %5.2fs d=%d%s %s" % (c[0], c[1], c[2], "!" if c[3] else " ", c[4])
            for c in cells)
        report.append(line)
        print(line, flush=True)

    report.append("")
    for i, lim in enumerate(LIMITS):
        sub = [r[i] for r in rows]
        if not sub:
            continue
        n = len(sub)
        report.append("лимит %.0f с: аварий %d из %d, среднее время %.2f с, средняя глубина %.1f"
                      % (lim, sum(1 for c in sub if c[3]), n,
                         sum(c[1] for c in sub) / n, sum(c[2] for c in sub) / n))
    changed = sum(1 for r in rows if r[0][4] != r[-1][4])
    report.append("ход изменился при росте лимита 3->5 с: %d из %d позиций"
                  % (changed, len(rows)))
    with open("bench_limit.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")
    print("Saved: bench_limit.txt")


if __name__ == "__main__":
    main()