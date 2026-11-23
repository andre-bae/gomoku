"""
Бенчмарк живой партии: ИИ играет сам с собой, времена хода пишутся в файл.
Заменяет ручную партию и запись времён из «Просмотр A».

Запуск:
    python bench_game.py                  реальный режим (лимиты времени как в игре)
    python bench_game.py --fixed          фиксированный бюджет узлов (детерминированно)
    python bench_game.py --moves 16       короче партия
    python bench_game.py --games 2        две партии подряд

Результат: bench_game.txt (UTF-8) + партия в positions/bench_game_N.json
"""
import argparse
import json
import os
import statistics
import time

import gomoku
from gomoku import (Board, PLAYER_X, PLAYER_O, get_best_move,
                    DEBUG_LOG, player_name)


def deciding_step():
    step = "?"
    for ln in DEBUG_LOG:
        s = ln.strip()
        if s.startswith("[ШАГ") or s.startswith("[РЕЖИМ"):
            step = s.split("]")[0].lstrip("[")
    return step


def reached_depth():
    d = 0
    for ln in DEBUG_LOG:
        s = ln.strip()
        if s.startswith("глубина "):
            try:
                d = max(d, int(s.split(":")[0].split()[1]))
            except Exception:
                pass
    return d


def play_game(max_moves):
    b = Board()
    rows = []
    winner = None
    for n in range(1, max_moves + 1):
        side = PLAYER_X if n % 2 == 1 else PLAYER_O
        t0 = time.perf_counter()
        mv = get_best_move(b, side)
        dt = time.perf_counter() - t0
        step, dep = deciding_step(), reached_depth()
        panic = any("время хода исчерпано" in ln for ln in DEBUG_LOG)
        b.make_move(mv[0], mv[1], side)
        rows.append({"n": n, "side": player_name(side), "move": mv,
                     "t": dt, "step": step, "depth": dep, "panic": panic})
        print("  %2d %s %-10s %5.2fs depth=%d %s"
              % (n, player_name(side), str(mv), dt, dep, step), flush=True)
        if gomoku.check_five(b, side):
            winner = player_name(side)
            break
    return rows, winner, b


def summarize(rows):
    if not rows:
        return ["ходов нет"]
    ts = [r["t"] for r in rows]
    slow = sum(1 for t in ts if t > 1.5)
    out = ["ходов: %d" % len(rows),
           "время хода: среднее %.2f с, медиана %.2f с, максимум %.2f с"
           % (statistics.mean(ts), statistics.median(ts), max(ts)),
           "дороже 1.5 с: %d ходов (%.0f%%)" % (slow, 100.0 * slow / len(ts))]
    out.append("аварийных ходов (упёрлись в лимит 3 с): %d"
               % sum(1 for r in rows if r.get("panic")))
    pos = [r for r in rows if r["step"] == "ШАГ 9"]
    if pos:
        out.append("позиционных ходов (ШАГ 9): %d, средняя глубина %.1f, среднее время %.2f с"
                   % (len(pos), statistics.mean([r["depth"] for r in pos]),
                      statistics.mean([r["t"] for r in pos])))
    steps = {}
    for r in rows:
        steps[r["step"]] = steps.get(r["step"], 0) + 1
    out.append("чем решался ход: "
               + ", ".join("%s=%d" % kv for kv in sorted(steps.items())))
    return out


def save_game(b, path):
    data = {"saved": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "selfplay",
            "moves": [{"n": i + 1, "player": player_name(p), "x": x, "y": y,
                       "elapsed": None, "analysis": ""}
                      for i, (x, y, p) in enumerate(b.move_history)]}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--moves", type=int, default=24)
    ap.add_argument("--games", type=int, default=1)
    ap.add_argument("--fixed", action="store_true")
    ap.add_argument("--out", default="bench_game.txt")
    a = ap.parse_args()

    if a.fixed:
        # снимаем лимиты времени: останавливать поиск будет бюджет узлов (8000),
        # поэтому партия воспроизводима от запуска к запуску
        gomoku.POSITIONAL_TIME_LIMIT = 1000.0
        gomoku.MOVE_TIME_LIMIT = 1000.0

    mode = "фиксированный бюджет узлов" if a.fixed else "реальные лимиты времени"
    print("Self-play benchmark (%s), please wait..." % mode, flush=True)

    report = ["режим: %s" % mode,
              "лимиты: MOVE_TIME_LIMIT=%.1f с, POSITIONAL_TIME_LIMIT=%.1f с"
              % (gomoku.MOVE_TIME_LIMIT, gomoku.POSITIONAL_TIME_LIMIT)]
    all_rows = []
    for g in range(1, a.games + 1):
        print("game %d/%d" % (g, a.games), flush=True)
        rows, winner, b = play_game(a.moves)
        all_rows += rows
        report.append("")
        report.append("=== Партия %d: %s ==="
                      % (g, ("победа " + winner) if winner else "лимит ходов, без победителя"))
        report += summarize(rows)
        save_game(b, os.path.join("positions", "bench_game_%d.json" % g))
    if a.games > 1:
        report.append("")
        report.append("=== Всего по всем партиям ===")
        report += summarize(all_rows)

    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")
    print("Saved: %s" % a.out)


if __name__ == "__main__":
    main()