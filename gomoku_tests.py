# gomoku_tests.py
# Этап 0: тестовая обвязка, загрузка позиций, replay и ASCII-отладка.
# Текущий движок НЕ меняется. Часть тестов специально красная — это_known bugs.

import json
import sys
import argparse
from typing import List, Tuple, Optional

from gomoku import (
    Board, PLAYER_X, PLAYER_O, EMPTY,
    check_double_threat, search_vcf, check_immediate_win,
    find_all_open_three_blocks, get_potential_threats,
    get_best_move, DEBUG_LOG,
)


# ---------- построение позиций ----------

def build(x_stones: List[Tuple[int, int]], o_stones: List[Tuple[int, int]]) -> Board:
    b = Board()
    for x, y in x_stones:
        b.make_move(x, y, PLAYER_X)
    for x, y in o_stones:
        b.make_move(x, y, PLAYER_O)
    return b


def from_moves(moves: List[list]) -> Board:
    """moves: [["X", 0, 0], ["O", 1, 0], ...]"""
    b = Board()
    for p, x, y in moves:
        b.make_move(x, y, PLAYER_X if p == "X" else PLAYER_O)
    return b


def ascii_board(b: Board) -> str:
    if not b.grid:
        return "(пустая доска)"
    xs = [p[0] for p in b.grid]
    ys = [p[1] for p in b.grid]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    lines = ["     " + " ".join(f"{x:>2}" for x in range(minx, maxx + 1))]
    for y in range(miny, maxy + 1):
        row = f"{y:>3}: "
        for x in range(minx, maxx + 1):
            c = b.get_cell(x, y)
            row += "  X" if c == PLAYER_X else "  O" if c == PLAYER_O else "  ."
        lines.append(row)
    return "\n".join(lines)


# ---------- тесты ----------

TESTS = []


def test(name: str, known_bug: Optional[str] = None):
    def deco(fn):
        TESTS.append((name, fn, known_bug))
        return fn
    return deco


@test("одна закрытая четвёрка — НЕ вилка",
      known_bug="check_double_threat считает четвёрку 4 раза (по камням)")
def t_closed_four_not_fork():
    b = build([(0, 0), (1, 0), (2, 0), (3, 0)], [(-1, 0)])
    assert check_double_threat(b, PLAYER_X) is False, \
        "одна закрытая четвёрка блокируется одним ходом, это не вилка"


@test("открытая четвёрка — победа")
def t_open_four_is_win():
    b = build([(0, 0), (1, 0), (2, 0), (3, 0)], [(10, 10)])
    assert check_double_threat(b, PLAYER_X) is True


@test("четвёрка с разрывом — одна точка достройки, не вилка")
def t_gap_four_not_fork():
    b = build([(0, 0), (1, 0), (3, 0), (4, 0)], [(-1, 0)])
    assert check_double_threat(b, PLAYER_X) is False
    threats = get_potential_threats(b, 2, 0, PLAYER_X)
    assert "five" in threats, "достройка разрыва должна давать пятёрку"


@test("разрывная четвёрка с двумя пустыми концами — всё равно ОДНА точка пятёрки",
      known_bug="get_potential_threats помечает .XX_XX. как open_four")
def t_gap_four_single_completion():
    b = build([(0, 0), (1, 0), (3, 0)], [])
    threats = get_potential_threats(b, 4, 0, PLAYER_X)
    assert "closed_four" in threats, "это четвёрка с одной точкой достройки"
    assert "open_four" not in threats, "у неё нет двух точек пятёрки"


@test("две спящие тройки O_XXX_O — НЕ вилка",
      known_bug="count_all_open_threes не отличает живую тройку от спящей")
def t_two_sleeping_threes_not_fork():
    b = build(
        [(0, 0), (1, 0), (2, 0), (0, 1), (0, 2)],
        [(-2, 0), (4, 0), (0, -2), (0, 4)],
    )
    assert check_double_threat(b, PLAYER_X) is False, \
        "обе тройки дают только закрытые четвёрки, форсированной победы нет"


@test("одна закрытая тройка — VCF нет",
      known_bug="любая четвёрка объявляется победой из-за бага ×4")
def t_single_closed_three_no_vcf():
    b = build([(0, 0), (1, 0), (2, 0)], [(-1, 0)])
    assert check_immediate_win(b, PLAYER_X) is None
    move = search_vcf(b, depth=6, player=PLAYER_X, is_attacking=True)
    assert move is None, \
        f"X(3,0) даёт закрытую четвёрку, O(4,0) блокирует; VCF нет, а найдено {move}"


@test("позиция из лога после O(2,-3) — VCF у X нет",
      known_bug="defense_moves ищет свои четвёрки O вместо блокировки; плюс баг ×4")
def t_log_position_no_vcf():
    moves = [
        ["O", 0, 0], ["X", 1, -1], ["O", 2, 2], ["X", 0, -2],
        ["O", -1, -1], ["X", -2, -2], ["O", 3, 3], ["X", 1, 1],
        ["O", 1, -2], ["X", -1, -3], ["O", -2, -4], ["X", 0, -4],
        ["O", -3, -1], ["X", 0, -3], ["O", 0, -5], ["X", 1, -3],
        ["O", 2, -3],
    ]
    b = from_moves(moves)
    move = search_vcf(b, depth=6, player=PLAYER_X, is_attacking=True)
    assert move is None, \
        f"после O(2,-3) у X нет форсированного выигрыша; найдено {move}"


@test("немедленная пятёрка находится")
def t_immediate_win():
    b = build([(0, 0), (1, 0), (2, 0), (3, 0)], [(10, 10)])
    move = check_immediate_win(b, PLAYER_X)
    assert move in {(4, 0), (-1, 0)}, f"ожидалась достройка пятёрки, получено {move}"


@test("блокировки открытой тройки найдены")
def t_open_three_blocks():
    b = build([(0, 0), (1, 0), (2, 0)], [(10, 10)])
    blocks = find_all_open_three_blocks(b, PLAYER_X)
    assert (-1, 0) in blocks and (3, 0) in blocks


# ---------- runner ----------

def run_tests(only: Optional[str] = None, show_board_on_fail: bool = True) -> int:
    passed = failed = known = 0
    print("=" * 70)
    print("ЭТАП 0 — тестовая обвязка (движок не изменён)")
    print("=" * 70)
    for name, fn, known_bug in TESTS:
        if only and only.lower() not in name.lower():
            continue
        DEBUG_LOG.clear()
        try:
            fn()
            passed += 1
            print(f"[PASS] {name}")
        except AssertionError as e:
            failed += 1
            tag = "KNOWN BUG" if known_bug else "FAIL"
            if known_bug:
                known += 1
            print(f"[{tag}] {name}")
            print(f"       {e}")
            if known_bug:
                print(f"       причина: {known_bug}")
            if show_board_on_fail:
                # восстановить доску из теста нельзя напрямую, поэтому выводим только сообщение
                pass
        except Exception as e:
            failed += 1
            print(f"[ERROR] {name}: {type(e).__name__}: {e}")
    print("-" * 70)
    print(f"Итого: PASS={passed}  FAIL={failed}  (из них известных багов={known})")
    print("Красные тесты с пометкой KNOWN BUG — ожидаемы на текущем движке.")
    print("После этапов 1–3 они должны стать зелёными.")
    return 0 if failed == 0 else 1


# ---------- replay / analyze ----------

def load_position_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def cmd_replay(path: str):
    data = load_position_file(path)
    b = from_moves(data["moves"])
    print(f"Позиция: {data.get('name', path)}")
    print(f"Ходов: {len(data['moves'])}")
    print(ascii_board(b))


def cmd_analyze(path: str, side: str):
    data = load_position_file(path)
    b = from_moves(data["moves"])
    player = PLAYER_X if side.upper() == "X" else PLAYER_O
    print(f"Анализ за {side.upper()} для позиции: {data.get('name', path)}")
    print(ascii_board(b))
    move = get_best_move(b, player)
    print(f"\nВыбран ход: {move}")
    print("\n--- лог анализа ---")
    print("\n".join(DEBUG_LOG))


def main():
    ap = argparse.ArgumentParser(description="Гомоку: этап 0 — тесты, replay, анализ")
    ap.add_argument("--test", action="store_true", help="прогнать тесты")
    ap.add_argument("--only", type=str, help="фильтр тестов по подстроке")
    ap.add_argument("--replay", type=str, help="JSON-файл позиции: показать доску")
    ap.add_argument("--analyze", type=str, help="JSON-файл позиции: запустить ИИ")
    ap.add_argument("--side", type=str, default="X", help="за кого анализировать (X/O)")
    args = ap.parse_args()

    if args.replay:
        cmd_replay(args.replay)
        return 0
    if args.analyze:
        cmd_analyze(args.analyze, args.side)
        return 0
    return run_tests(only=args.only)


if __name__ == "__main__":
    sys.exit(main())