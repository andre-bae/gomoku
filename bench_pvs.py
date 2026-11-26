"""ШАГ 31: A/B PVS / killer-history / TT-best. Чередование, фиксированный бюджет."""
import statistics
import time

import gomoku as G
import gomoku_analysis as ga
from gomoku import PLAYER_X, PLAYER_O
from bench2 import quiet_position

NODES = 4000
REPEATS = 2
VARIANTS = [("base", (False, False, False)),
            ("PVS", (True, False, False)),
            ("KH", (False, True, False)),
            ("TT", (False, False, True)),
            ("ALL", (True, True, True))]


def probe(b, side, flags):
    G.USE_EXTENSIONS = False
    G.USE_PVS, G.USE_KILLER_HISTORY, G.USE_TT_BEST = flags
    G.reset_search_tables()
    ga.clear_threat_cache(); ga.clear_line_cache(); ga.clear_window_cache(); ga.reset_stats()
    budget = [NODES]
    t0 = time.perf_counter()
    val = G.minimax(b, depth=6, alpha=-10**9, beta=10**9, is_maximizing=True,
                    player=side, budget=budget, tt={})
    dt = time.perf_counter() - t0
    used = NODES - budget[0]
    return (used / dt if dt > 0 else 0.0), val


def main():
    print("A/B PVS/KH/TT: nodes=%d repeats=%d..." % (NODES, REPEATS), flush=True)
    lines = ["ШАГ 31 A/B: nodes=%d, медиана узлов/с" % NODES]
    for n in (12, 24, 36):
        b = quiet_position(n)
        side = PLAYER_X if n % 2 == 0 else PLAYER_O
        res = {name: [] for name, _ in VARIANTS}
        vals = {name: set() for name, _ in VARIANTS}
        for i in range(REPEATS):
            order = VARIANTS if i % 2 == 0 else list(reversed(VARIANTS))
            for name, flags in order:
                nps, val = probe(b, side, flags)
                res[name].append(nps)
                vals[name].add(val)
        for f in (False, False, False):
            pass
        G.USE_PVS = G.USE_KILLER_HISTORY = G.USE_TT_BEST = False
        base = statistics.median(res["base"])
        parts = []
        for name, _ in VARIANTS:
            m = statistics.median(res[name])
            parts.append("%s=%.0f(%+.1f%%)" % (name, m, 100.0 * (m / base - 1) if base else 0))
        line = "stones=%2d  %s" % (n, "  ".join(parts))
        lines.append(line)
        print(line, flush=True)
        print("   оценки: " + ", ".join("%s=%s" % (k, sorted(v)) for k, v in vals.items()), flush=True)
        lines.append("   оценки: " + ", ".join("%s=%s" % (k, sorted(v)) for k, v in vals.items()))
    with open("bench_pvs.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Saved: bench_pvs.txt")


if __name__ == "__main__":
    main()