"""
Шаг 29 (S4): замер стоимости кандидатов — прежде чем сужать набор.
Мерим без правок движка:
  1) число клеток: radius=2 (текущий), radius=1, точки угроз, «узкий» набор
     (radius1 + угрозы) и сколько «дальних» клеток можно убрать;
  2) куда уходит время позиционного поиска (cProfile, фиксированный бюджет):
     собственное время ключевых функций и число вызовов на узел.
Запуск:  python bench_candidates.py   ->  bench_candidates.txt
"""
import cProfile
import io
import pstats

import gomoku_analysis as ga
from gomoku import PLAYER_X, PLAYER_O, minimax
from gomoku_analysis import four_move_candidates, threat_move_candidates
from bench2 import quiet_position

NODES = 8000
KEYS = ["get_candidate_moves", "_order_moves", "evaluate_position",
        "analyze_threats", "_scan_windows", "_line_view"]


def counts(b):
    r2 = set(b.get_candidate_moves(radius=2))
    r1 = set(b.get_candidate_moves(radius=1))
    th = set()
    for p in (PLAYER_X, PLAYER_O):
        th |= set(four_move_candidates(b, p))
        th |= set(threat_move_candidates(b, p))
    narrow = r1 | th
    far = r2 - narrow
    return len(r2), len(r1), len(th), len(narrow), len(far)


def profile(b, side):
    ga.clear_threat_cache()
    ga.clear_line_cache()
    ga.clear_window_cache()
    ga.reset_stats()
    budget = [NODES]
    pr = cProfile.Profile()
    pr.enable()
    minimax(b, depth=6, alpha=-10**9, beta=10**9, is_maximizing=True,
            player=side, budget=budget, tt={})
    pr.disable()
    used = NODES - budget[0]
    ps = pstats.Stats(pr)
    total = ps.total_tt or 1e-9

    def own(name):
        return sum(v[2] for k, v in ps.stats.items() if k[2] == name)

    def nc(name):
        return sum(v[1] for k, v in ps.stats.items() if k[2] == name)

    shares = "  своё время: " + "  ".join(
        "%s=%.0f%%" % (k, 100.0 * own(k) / total) for k in KEYS)
    per = "  вызовов/узел: " + "  ".join(
        "%s=%.1f" % (k, nc(k) / used if used else 0) for k in KEYS)
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(30)
    return used, total, shares, per, s.getvalue()


def main():
    print("S4 замер кандидатов (NODES=%d, depth=6, под профилем)..." % NODES, flush=True)
    lines = ["S4 замер кандидатов: NODES=%d depth=6 (время под профилем, доли ориентировочные)" % NODES]
    for n in (12, 24, 36):
        b = quiet_position(n)
        side = PLAYER_X if n % 2 == 0 else PLAYER_O
        r2, r1, th, narrow, far = counts(b)
        head = ("stones=%2d  radius2=%d  radius1=%d  угрозы=%d  узкий(r1+угрозы)=%d  "
                "дальних=%d (%.0f%%)" % (n, r2, r1, th, narrow, far,
                                         100.0 * far / r2 if r2 else 0))
        used, total, shares, per, full = profile(b, side)
        lines += [head, "  поиск: %d узлов, %.2fс" % (used, total), shares, per, ""]
        print(head, flush=True)
        print("  поиск: %d узлов, %.2fс" % (used, total), flush=True)
        print(shares, flush=True)
        print(per, flush=True)
        lines.append("=== полный профиль stones=%d ===\n%s" % (n, full))
    with open("bench_candidates.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Saved: bench_candidates.txt (сводка + полные профили)")


if __name__ == "__main__":
    main()