"""
Полный анализ одного хода из сохранённой партии.
Запуск:
    python dump_log.py positions/bench_game_1.json 20
    python dump_log.py positions/bench_game_1.json 20 X
Смысл: строим позицию после первых 20 ходов партии и просим ИИ сходить.
Результат: log_move20.txt (UTF-8) — весь лог с метками времени (t=...).
"""
import json
import sys
import time

from gomoku import (Board, PLAYER_X, PLAYER_O, get_best_move,
                    DEBUG_LOG, player_name)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "positions/bench_game_1.json"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    b = Board()
    for m in data["moves"][:n]:
        p = PLAYER_X if str(m["player"]).strip().upper() == "X" else PLAYER_O
        b.make_move(int(m["x"]), int(m["y"]), p)
    side = PLAYER_X if n % 2 == 0 else PLAYER_O
    if len(sys.argv) > 3:
        side = PLAYER_X if sys.argv[3].strip().upper() == "X" else PLAYER_O

    t0 = time.perf_counter()
    mv = get_best_move(b, side)
    dt = time.perf_counter() - t0

    out = "log_move%d.txt" % n
    head = ["партия: %s" % path,
            "позиция после %d ходов, ходит %s" % (n, player_name(side)),
            "выбран ход: %s, время %.2f с" % (mv, dt),
            ""]
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(head) + "\n".join(DEBUG_LOG) + "\n")
    print("Saved: %s  (move=%s, %.2f s)" % (out, mv, dt))


if __name__ == "__main__":
    main()