"""ШАГ 30: продления поиска — A/B стоимости и ходов (USE_EXTENSIONS)."""
import time

import gomoku
import gomoku_analysis as ga
from gomoku import PLAYER_X, PLAYER_O, get_best_move, DEBUG_LOG
from bench2 import quiet_position, deciding_step, max_depth


def game16_board():
    b = gomoku.Board()
    for x, y in [(-1, 0), (0, -1), (1, -2), (0, -3), (-2, -1), (0, 2), (-5, -3), (-5, 1)]:
        b.make_move(x, y, PLAYER_X)
    for x, y in [(-3, -1), (-2, -2), (-2, 1), (-2, 0), (-1, 1), (-4, -2), (-4, 1)]:
        b.make_move(x, y, PLAYER_O)
    return b


def run(make_b, side, flag):
    gomoku.USE_EXTENSIONS = flag
    ga.clear_threat_cache(); ga.clear_line_cache(); ga.clear_window_cache(); ga.reset_stats()
    DEBUG_LOG.clear(); gomoku._TRUNCATED[0] = 0
    b = make_b()
    t0 = time.perf_counter()
    mv = get_best_move(b, side)
    dt = time.perf_counter() - t0
    log = list(DEBUG_LOG)
    panic = any("время хода исчерпано" in s for s in log)
    return mv, dt, max_depth(), deciding_step(), panic


def main():
    cases = [("12к", lambda: quiet_position(12), PLAYER_X),
             ("24к", lambda: quiet_position(24), PLAYER_X),
             ("36к", lambda: quiet_position(36), PLAYER_X),
             ("game16", game16_board, PLAYER_O)]
    print("Продления A/B (USE_EXTENSIONS off/on)...", flush=True)
    lines = ["ШАГ 30: продления off/on"]
    for name, mk, side in cases:
        off = run(mk, side, False)
        on = run(mk, side, True)
        gomoku.USE_EXTENSIONS = False
        line = ("%s  OFF ход=%s %.2fс d%d %s%s | ON ход=%s %.2fс d%d %s%s"
                % (name, off[0], off[1], off[2], off[3], " АВАРИЯ" if off[4] else "",
                   on[0], on[1], on[2], on[3], " АВАРИЯ" if on[4] else ""))
        lines.append(line)
        print(line, flush=True)
    with open("bench_ext.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Saved: bench_ext.txt")


if __name__ == "__main__":
    main()