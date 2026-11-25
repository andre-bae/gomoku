"""
Честный A/B кэша по позиции (S1c), шаг 26.
Отличия от шага 25:
  - крупная фиксированная работа: 30000 узлов (--quick = 6000, --nodes N для отладки);
  - счётчики работы: сколько полных расчётов кэш реально убрал;
  - wall-clock и process_time, медиана и разброс по --repeats (по умолчанию 3);
  - проверки: оценка, число узлов и число вызовов не зависят от кэша.

Запуск:
  python bench_ab.py            ->  bench_ab.txt
  python bench_ab.py --quick    ->  быстрый прогон
"""
import argparse
import statistics
import time

import gomoku_analysis as ga
from gomoku import PLAYER_X, PLAYER_O, minimax
from bench2 import quiet_position


def probe(b, side, nodes):
    """Один замер: чистые кэши, свой бюджет узлов, своя таблица транспозиций."""
    ga.clear_threat_cache()
    ga.clear_line_cache()
    ga.clear_window_cache()
    ga.reset_stats()
    budget = [nodes]
    t0 = time.perf_counter()
    c0 = time.process_time()
    val = minimax(b, depth=8, alpha=-10**9, beta=10**9, is_maximizing=True,
                  player=side, budget=budget, tt={})
    wall = time.perf_counter() - t0
    cpu = time.process_time() - c0
    used = nodes - budget[0]
    return {"used": used, "val": val, "wall": wall, "cpu": cpu,
            "nps": used / wall if wall > 0 else 0.0,
            "nps_cpu": used / cpu if cpu > 0 else 0.0,
            "stats": dict(ga.STATS)}


def _median(rs, key):
    return statistics.median(r[key] for r in rs)


def _spread(rs):
    vals = [r["nps"] for r in rs]
    m = statistics.median(vals)
    return 100.0 * (max(vals) - min(vals)) / m if m > 0 else 0.0


def _saved(on, off, full_key):
    f_on, f_off = on[full_key], off[full_key]
    return 100.0 * (1.0 - f_on / f_off) if f_off else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="6000 узлов вместо 30000")
    ap.add_argument("--nodes", type=int, default=0, help="точный бюджет узлов (отладка)")
    ap.add_argument("--repeats", type=int, default=3, help="повторов на вариант")
    args = ap.parse_args()
    nodes = args.nodes if args.nodes > 0 else (6000 if args.quick else 30000)
    reps = max(1, args.repeats)
    print("A/B S1c: nodes=%d repeats=%d, чередование ON/OFF в одном процессе..."
          % (nodes, reps), flush=True)
    lines = ["A/B S1c: nodes=%d repeats=%d (фиксированная работа, чистые кэши перед замером)"
             % (nodes, reps)]
    for n in (12, 24, 36):
        b = quiet_position(n)
        side = PLAYER_X if n % 2 == 0 else PLAYER_O
        res = {True: [], False: []}
        for i in range(reps):
            order = (True, False) if i % 2 == 0 else (False, True)
            for flag in order:
                ga.USE_POSITION_CACHE = flag
                r = probe(b, side, nodes)
                res[flag].append(r)
                print("  stones=%2d %-3s повтор %d/%d: %6.0f узлов/с"
                      % (n, "ON" if flag else "OFF", i + 1, reps, r["nps"]), flush=True)
        ga.USE_POSITION_CACHE = True
        on, off = res[True], res[False]
        mo, mf = _median(on, "nps"), _median(off, "nps")
        co, cf = _median(on, "nps_cpu"), _median(off, "nps_cpu")
        son, soff = on[-1]["stats"], off[-1]["stats"]
        same_val = {r["val"] for r in on} == {r["val"] for r in off}
        same_used = len({r["used"] for r in on + off}) == 1
        same_calls = (son["analyze_full"] + son["analyze_hit"]
                      == soff["analyze_full"] + soff["analyze_hit"]
                      and son["pot_full"] + son["pot_hit"]
                      == soff["pot_full"] + soff["pot_hit"])
        stable = (all(r["stats"] == son for r in on)
                  and all(r["stats"] == soff for r in off))
        saved_an = _saved(son, soff, "analyze_full")
        saved_pot = _saved(son, soff, "pot_full")
        gain_wall = 100.0 * (mo / mf - 1) if mf > 0 else 0.0
        gain_cpu = 100.0 * (co / cf - 1) if cf > 0 else 0.0
        block = [
            "stones=%2d  оценка совпала: %s  узлов одинаково: %s  вызовов одинаково: %s  счётчики стабильны: %s"
            % (n, "ДА" if same_val else "НЕТ !!!", "ДА" if same_used else "НЕТ !!!",
               "ДА" if same_calls else "НЕТ !!!", "ДА" if stable else "НЕТ"),
            "  ON : %6.0f узлов/с (разброс %4.1f%%)  cpu %6.0f  analyze full/hit=%d/%d  pot full/hit=%d/%d"
            % (mo, _spread(on), co, son["analyze_full"], son["analyze_hit"],
               son["pot_full"], son["pot_hit"]),
            "  OFF: %6.0f узлов/с (разброс %4.1f%%)  cpu %6.0f  analyze full/hit=%d/%d  pot full/hit=%d/%d"
            % (mf, _spread(off), cf, soff["analyze_full"], soff["analyze_hit"],
               soff["pot_full"], soff["pot_hit"]),
            "  geom build/hit ON=%d/%d OFF=%d/%d   scan full/hit ON=%d/%d OFF=%d/%d"
            % (son["geom_build"], son["geom_hit"], soff["geom_build"], soff["geom_hit"],
               son["scan_full"], son["scan_hit"], soff["scan_full"], soff["scan_hit"]),
            "  выигрыш ON: wall %+.1f%%  cpu %+.1f%%   убрано полных: analyze %.1f%%  pot %.1f%%"
            % (gain_wall, gain_cpu, saved_an, saved_pot),
        ]
        lines.extend(block)
        print("\n".join(block), flush=True)
    with open("bench_ab.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Saved: bench_ab.txt")
    print("Критерий (HANDOFF): убрать >=20% полных расчётов и не ухудшить время -> оставить.")


if __name__ == "__main__":
    main()