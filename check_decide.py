"""
Шаг 28: почему на 24/36 камнях сменился решающий шаг.
  1) кэш по позиции ON/OFF не меняет ход и решающий шаг? (корректность)
  2) решающий шаг зависит от того, успевает ли тактика досчитаться? (скорость)
Метод: позиции bench2, три лимита времени (0.3 / 3 / 1000 с),
чередование ON/OFF в одном процессе, чистые кэши перед каждым замером.
Запуск:  python check_decide.py   ->  check_decide.txt
"""
import time

import gomoku
import gomoku_analysis as ga
from gomoku import PLAYER_X, PLAYER_O, get_best_move, DEBUG_LOG
from bench2 import quiet_position, deciding_step, max_depth

LIMITS = (0.3, 3.0, 1000.0)


def run_once(b, side, flag, limit):
    ga.USE_POSITION_CACHE = flag
    gomoku.MOVE_TIME_LIMIT = limit
    if hasattr(gomoku, "POSITIONAL_TIME_LIMIT"):
        gomoku.POSITIONAL_TIME_LIMIT = limit
    ga.clear_threat_cache()
    ga.clear_line_cache()
    ga.clear_window_cache()
    ga.reset_stats()
    DEBUG_LOG.clear()
    gomoku._TRUNCATED[0] = 0
    t0 = time.perf_counter()
    move = get_best_move(b, side)
    dt = time.perf_counter() - t0
    log = list(DEBUG_LOG)
    return {
        "move": move, "step": deciding_step(), "depth": max_depth(), "t": dt,
        "panic": any("время хода исчерпано" in s for s in log),
        "lost": any("тактически проиграна" in s for s in log),
        "undok": any("не доказана" in s for s in log),
        "log": log,
    }


def fmt(r):
    flags = []
    if r["panic"]:
        flags.append("АВАРИЯ")
    if r["lost"]:
        flags.append("проиграна")
    if r["undok"]:
        flags.append("не доказана")
    return "ход=%s шаг=%s глубина=%d %.2fс%s" % (
        r["move"], r["step"], r["depth"], r["t"],
        (" [" + ",".join(flags) + "]") if flags else "")


def main():
    print("check_decide: лимиты %s, чередование ON/OFF..." % (LIMITS,), flush=True)
    lines = ["check_decide: лимиты %s (детерминированные позиции bench2)" % (LIMITS,)]
    all_same = True
    evidence = []
    for n in (12, 24, 36):
        side = PLAYER_X if n % 2 == 0 else PLAYER_O
        lines.append("stones=%2d  сторона=%s" % (n, "X" if side == PLAYER_X else "O"))
        steps_by_limit = {}
        for li, limit in enumerate(LIMITS):
            order = (True, False) if li % 2 == 0 else (False, True)
            res = {}
            for flag in order:
                b = quiet_position(n)          # свежая доска на каждый замер
                res[flag] = run_once(b, side, flag, limit)
            on, off = res[True], res[False]
            same = (on["move"] == off["move"] and on["step"] == off["step"])
            all_same = all_same and same
            steps_by_limit[limit] = on["step"]
            line = "  лимит=%6.1fс  ON: %s | OFF: %s | совпало: %s" % (
                limit, fmt(on), fmt(off), "ДА" if same else "НЕТ !!!")
            lines.append(line)
            print(line, flush=True)
            evidence.append("=== stones=%d лимит=%.1fс ON ===\n%s"
                            % (n, limit, "\n".join(on["log"])))
        summary = "  решающий шаг по лимиту: " + ", ".join(
            "%.1fс->%s" % (l, steps_by_limit[l]) for l in LIMITS)
        lines.append(summary)
        print(summary, flush=True)
    verdict = "КЭШ ON/OFF: ход и решающий шаг совпали во всех 9 парах: %s" % (
        "ДА" if all_same else "НЕТ !!!")
    lines.append(verdict)
    print(verdict, flush=True)
    ga.USE_POSITION_CACHE = True
    gomoku.MOVE_TIME_LIMIT = 3.0
    with open("check_decide.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n\n")
        f.write("\n\n".join(evidence) + "\n")
    print("Saved: check_decide.txt (сводка + полные логи)")


if __name__ == "__main__":
    main()