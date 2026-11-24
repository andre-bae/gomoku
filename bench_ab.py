"""
Честный A/B кэша по позиции.
Отличия от bench2:
  - варианты чередуются ВНУТРИ одного процесса (дрейф машины действует на оба);
  - фиксированный объём работы: 6000 узлов глубокого поиска с таблицей транспозиций;
  - кэши сбрасываются перед каждым замером — одинаковые условия;
  - проверка корректности: оценка не должна зависеть от кэша.

Запуск:  python bench_ab.py   ->  bench_ab.txt
"""
import statistics
import time

import gomoku_analysis as ga
from gomoku import PLAYER_X, PLAYER_O, minimax
from bench2 import quiet_position

REPEATS = 3
NODES = 6000


def probe(b, side):
    ga.clear_threat_cache()
    ga.clear_line_cache()
    ga.clear_window_cache()
    budget = [NODES]
    t0 = time.perf_counter()
    val = minimax(b, depth=8, alpha=-10**9, beta=10**9, is_maximizing=True,
                  player=side, budget=budget, tt={})
    dt = time.perf_counter() - t0
    used = NODES - budget[0]
    return (used / dt if dt > 0 else 0.0), val


def main():
    print("A/B position cache (fixed work, interleaved), please wait...", flush=True)
    lines = []
    for n in (12, 24, 36):
        b = quiet_position(n)
        side = PLAYER_X if n % 2 == 0 else PLAYER_O
        on, off, vals_on, vals_off = [], [], set(), set()
        for i in range(REPEATS):
            order = (True, False) if i % 2 == 0 else (False, True)
            for flag in order:
                ga.USE_POSITION_CACHE = flag
                nps, val = probe(b, side)
                if flag:
                    on.append(nps); vals_on.add(val)
                else:
                    off.append(nps); vals_off.add(val)
        ga.USE_POSITION_CACHE = True
        mo, mf = statistics.median(on), statistics.median(off)
        spread_on = 100.0 * (max(on) - min(on)) / mo
        spread_off = 100.0 * (max(off) - min(off)) / mf
        same = "ДА" if vals_on == vals_off else "НЕТ !!!"
        line = ("stones=%2d ON=%6.0f OFF=%6.0f nodes/s  выигрыш ON=%+6.1f%%  "
                "разброс ON=%.0f%% OFF=%.0f%%  оценка совпала: %s"
                % (n, mo, mf, 100.0 * (mo / mf - 1), spread_on, spread_off, same))
        lines.append(line)
        print(line, flush=True)
    with open("bench_ab.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Saved: bench_ab.txt")


if __name__ == "__main__":
    main()