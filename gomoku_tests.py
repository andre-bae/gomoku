# gomoku_tests.py
# Этап 2: часть багов закрыта, часть оставлена за этапом 3.

import json
import sys
import argparse
from typing import List, Tuple, Optional

try:
    import pytest
except ImportError:
    pytest = None

from gomoku import (
    Board, PLAYER_X, PLAYER_O, EMPTY,
    check_double_threat, search_vcf, check_immediate_win,
    find_all_open_three_blocks, get_potential_threats,
    count_all_open_threes, get_best_move, DEBUG_LOG,
)


def build(x_stones: List[Tuple[int, int]], o_stones: List[Tuple[int, int]]) -> Board:
    b = Board()
    for x, y in x_stones:
        b.make_move(x, y, PLAYER_X)
    for x, y in o_stones:
        b.make_move(x, y, PLAYER_O)
    return b


def from_moves(moves: List[list]) -> Board:
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


TESTS = []


def case(name: str, known_bug: Optional[str] = None):
    def deco(fn):
        TESTS.append((name, fn, known_bug))
        if pytest is not None and known_bug:
            fn = pytest.mark.xfail(reason=known_bug, strict=False)(fn)
        return fn
    return deco


# ---------- закрыто этапом 2 ----------

@case("одна закрытая четвёрка — НЕ вилка")
def test_closed_four_not_fork():
    b = build([(0, 0), (1, 0), (2, 0), (3, 0)], [(-1, 0)])
    assert check_double_threat(b, PLAYER_X) is False


@case("две спящие тройки O_XXX_O — НЕ вилка")
def test_two_sleeping_threes_not_fork():
    b = build([(0, 0), (1, 0), (2, 0), (0, 1), (0, 2)],
              [(-2, 0), (4, 0), (0, -2), (0, 4)])
    assert check_double_threat(b, PLAYER_X) is False


@case("count_all_open_threes считает только живые тройки")
def test_count_only_live_threes():
    sleeping = build([(0, 0), (1, 0), (2, 0), (0, 1), (0, 2)],
                     [(-2, 0), (4, 0), (0, -2), (0, 4)])
    assert count_all_open_threes(sleeping, PLAYER_X) == 0
    live = build([(0, 0), (1, 0), (2, 0), (0, 1), (0, 2)], [])
    assert count_all_open_threes(live, PLAYER_X) == 2


@case("позиция из лога: X(3,1) не даёт вилку")
def test_log_position_x31_not_fork():
    moves = [
        ["O", 0, 0], ["X", 1, -1], ["O", 2, 2], ["X", 0, -2],
        ["O", -1, -1], ["X", -2, -2], ["O", 3, 3], ["X", 1, 1],
        ["O", 1, -2], ["X", -1, -3], ["O", -2, -4], ["X", 0, -4],
        ["O", -3, -1], ["X", 0, -3], ["O", 0, -5], ["X", 1, -3],
        ["O", 2, -3], ["X", 3, 1],
    ]
    b = from_moves(moves)
    assert check_double_threat(b, PLAYER_X) is False


# ---------- остаётся на этап 3 ----------

@case("разрывная четвёрка — одна точка пятёрки в get_potential_threats")
def test_gap_four_single_completion():
    b = build([(0, 0), (1, 0), (3, 0)], [])
    threats = get_potential_threats(b, 4, 0, PLAYER_X)
    assert "closed_four" in threats
    assert "open_four" not in threats


@case("одна закрытая тройка — VCF нет")
def test_single_closed_three_no_vcf():
    b = build([(0, 0), (1, 0), (2, 0)], [(-1, 0)])
    assert check_immediate_win(b, PLAYER_X) is None
    move = search_vcf(b, depth=6, player=PLAYER_X, is_attacking=True)
    assert move is None, f"найдено {move}"


@case("позиция из лога после O(2,-3) — VCF у X нет")
def test_log_position_no_vcf():
    moves = [
        ["O", 0, 0], ["X", 1, -1], ["O", 2, 2], ["X", 0, -2],
        ["O", -1, -1], ["X", -2, -2], ["O", 3, 3], ["X", 1, 1],
        ["O", 1, -2], ["X", -1, -3], ["O", -2, -4], ["X", 0, -4],
        ["O", -3, -1], ["X", 0, -3], ["O", 0, -5], ["X", 1, -3],
        ["O", 2, -3],
    ]
    b = from_moves(moves)
    move = search_vcf(b, depth=6, player=PLAYER_X, is_attacking=True)
    assert move is None, f"найдено {move}"


# ---------- было зелёным и осталось ----------

@case("открытая четвёрка — победа")
def test_open_four_is_win():
    b = build([(0, 0), (1, 0), (2, 0), (3, 0)], [(10, 10)])
    assert check_double_threat(b, PLAYER_X) is True


@case("четвёрка с разрывом — не вилка")
def test_gap_four_not_fork():
    b = build([(0, 0), (1, 0), (3, 0), (4, 0)], [(-1, 0)])
    assert check_double_threat(b, PLAYER_X) is False
    assert "five" in get_potential_threats(b, 2, 0, PLAYER_X)


@case("немедленная пятёрка находится")
def test_immediate_win():
    b = build([(0, 0), (1, 0), (2, 0), (3, 0)], [(10, 10)])
    assert check_immediate_win(b, PLAYER_X) in {(4, 0), (-1, 0)}


@case("блокировки открытой тройки найдены")
def test_open_three_blocks():
    b = build([(0, 0), (1, 0), (2, 0)], [(10, 10)])
    blocks = find_all_open_three_blocks(b, PLAYER_X)
    assert (-1, 0) in blocks and (3, 0) in blocks


@case("VCF находит живую четвёрку")
def test_vcf_finds_live_four():
    b = build([(0, 0), (1, 0), (2, 0)], [(10, 10)])
    move = search_vcf(b, depth=6, player=PLAYER_X, is_attacking=True)
    assert move in {(-1, 0), (3, 0)}, f"ожидалась живая четвёрка, получено {move}"


# ---------- раннер и утилиты ----------

def run_tests(only: Optional[str] = None) -> int:
    passed = failed = known = 0
    print("=" * 70)
    print("ЭТАП 2 — анализатор подключён")
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
            if known_bug:
                known += 1
                print(f"[KNOWN BUG] {name}")
            else:
                print(f"[FAIL] {name}")
            print(f"       {e}")
            if known_bug:
                print(f"       причина: {known_bug}")
        except Exception as e:
            failed += 1
            print(f"[ERROR] {name}: {type(e).__name__}: {e}")
    print("-" * 70)
    print(f"Итого: PASS={passed}  FAIL={failed}  (известных багов={known})")
    return 0 if failed == 0 else 1


def load_position_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def cmd_replay(path: str):
    data = load_position_file(path)
    b = from_moves(data["moves"])
    print(f"Позиция: {data.get('name', path)}")
    print(ascii_board(b))


def cmd_analyze(path: str, side: str):
    data = load_position_file(path)
    b = from_moves(data["moves"])
    player = PLAYER_X if side.upper() == "X" else PLAYER_O
    print(ascii_board(b))
    move = get_best_move(b, player)
    print(f"\nВыбран ход: {move}")
    print("\n".join(DEBUG_LOG))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--only", type=str)
    ap.add_argument("--replay", type=str)
    ap.add_argument("--analyze", type=str)
    ap.add_argument("--side", type=str, default="X")
    args = ap.parse_args()
    if args.replay:
        cmd_replay(args.replay); return 0
    if args.analyze:
        cmd_analyze(args.analyze, args.side); return 0
    return run_tests(only=args.only)


if __name__ == "__main__":
    sys.exit(main())