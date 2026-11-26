"""ШАГ 31: PVS/TT в реальном конвейере get_best_move (общая TT, углубление)."""
import statistics
import time

import gomoku as G
import gomoku_analysis as ga
from gomoku import PLAYER_X, PLAYER_O, get_best_move, DEBUG_LOG
from bench2 import quiet_position, deciding_step, max_depth

VARIANTS = [("base", (False, False, False)),
            ("PVS", (True, False, False)),
            ("TT", (False, False, True)),
            ("PVS+TT", (True, False, True))]
REPEATS = 2


def run(n, flags):
    G.USE_EXTENSIONS = False
    G.USE_PVS, G.USE_KILLER_HISTORY, G.USE_TT_BEST = flags
    ga.clear_threat_cache(); ga.clear_line_cache(); ga.clear_window_cache()
    G.reset_search_tables()
    DEBUG_LOG.clear(); G._TRUNCATED[0] = 0
    b = quiet_position(n)
    side = PLAYER_X if n % 2 == 0 else PLAYER_O
    t0 = time.perf_counter()
    mv = get_best_move(b, side)
    dt = time.perf_counter() - t0
    return mv, dt, max_depth(), deciding_step()


def main():
    print("PVS/TT в конвейере: repeats=%d..." % REPEATS, flush=True)
    lines = ["ШАГ 31: PVS/TT через get_best_move (медиана времени)"]
    for n in (12, 16, 20):
        res = {name: [] for name, _ in VARIANTS}
        info = {}
        for i in range(REPEATS):
            order = VARIANTS if i % 2 == 0 else list(reversed(VARIANTS))
            for name, flags in order:
                mv, dt, d, step = run(n, flags)
                res[name].append(dt)
                info[name] = (mv, d, step)
        G.USE_PVS = G.USE_KILLER_HISTORY = G.USE_TT_BEST = False
        parts = []
        for name, _ in VARIANTS:
            mt = statistics.median(res[name])
            mv, d, step = info[name]
            parts.append("%s %.2fс d%d ход=%s" % (name, mt, d, mv))
        line = "stones=%2d  %s" % (n, " | ".join(parts))
        lines.append(line)
        print(line, flush=True)
    with open("bench_pvs2.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Saved: bench_pvs2.txt")


if __name__ == "__main__":
    main()