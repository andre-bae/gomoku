# gomoku_analysis_tests.py
# Тесты нового анализатора. Все должны быть ЗЕЛЁНЫМИ сразу.
# Старый движок не меняется, его 5 xfail остаются.

from typing import List, Tuple
from gomoku import Board, PLAYER_X, PLAYER_O
from gomoku_analysis import (
    analyze_threats, completion_points, is_double_threat_new,
    is_winning_threat_set, describe,
    FIVE, LIVE_FOUR, FOUR, LIVE_THREE, SLEEPING_THREE,
)


def build(x_stones: List[Tuple[int, int]], o_stones: List[Tuple[int, int]]) -> Board:
    b = Board()
    for x, y in x_stones:
        b.make_move(x, y, PLAYER_X)
    for x, y in o_stones:
        b.make_move(x, y, PLAYER_O)
    return b


def from_moves(moves) -> Board:
    b = Board()
    for p, x, y in moves:
        b.make_move(x, y, PLAYER_X if p == "X" else PLAYER_O)
    return b


def kinds(threats):
    return sorted(t.kind for t in threats)


def test_closed_four_single_point():
    b = build([(0, 0), (1, 0), (2, 0), (3, 0)], [(-1, 0)])
    th = analyze_threats(b, PLAYER_X)
    fours = [t for t in th if t.kind == FOUR]
    assert len(fours) == 1, describe(th)
    assert fours[0].points == ((4, 0),), describe(th)
    assert not any(t.kind == LIVE_FOUR for t in th)
    assert is_winning_threat_set(th) is False


def test_open_four_two_points():
    b = build([(0, 0), (1, 0), (2, 0), (3, 0)], [(10, 10)])
    th = analyze_threats(b, PLAYER_X)
    live = [t for t in th if t.kind == LIVE_FOUR]
    assert len(live) == 1, describe(th)
    assert set(live[0].points) == {(-1, 0), (4, 0)}, describe(th)
    assert is_winning_threat_set(th) is True


def test_broken_four_is_not_open_four():
    # . X X _ X X .  -> единственная точка пятёрки — разрыв
    b = build([(0, 0), (1, 0), (3, 0), (4, 0)], [])
    th = analyze_threats(b, PLAYER_X)
    assert not any(t.kind == LIVE_FOUR for t in th), describe(th)
    fours = [t for t in th if t.kind == FOUR]
    assert len(fours) == 1, describe(th)
    assert fours[0].points == ((2, 0),), describe(th)
    assert completion_points(b, PLAYER_X) == {(2, 0)}


def test_two_sleeping_threes_not_winning():
    b = build([(0, 0), (1, 0), (2, 0), (0, 1), (0, 2)],
              [(-2, 0), (4, 0), (0, -2), (0, 4)])
    th = analyze_threats(b, PLAYER_X)
    assert kinds(th) == [SLEEPING_THREE, SLEEPING_THREE], describe(th)
    assert is_winning_threat_set(th) is False


def test_live_three_detected():
    b = build([(0, 0), (1, 0), (2, 0)], [])
    th = analyze_threats(b, PLAYER_X)
    live = [t for t in th if t.kind == LIVE_THREE]
    assert len(live) == 1, describe(th)
    assert is_winning_threat_set(th) is False


def test_dead_three_in_corridor():
    # коридор всего из 4 клеток — пятёрка невозможна физически
    b = build([(0, 0), (0, 1), (0, 2)], [(0, -1), (0, 3)])
    th = analyze_threats(b, PLAYER_X)
    assert th == [], describe(th)


def test_two_live_threes_is_fork():
    b = build([(0, 0), (1, 0), (2, 0), (0, 1), (0, 2)], [])
    th = analyze_threats(b, PLAYER_X)
    assert kinds(th).count(LIVE_THREE) == 2, describe(th)
    assert is_winning_threat_set(th) is True


def test_four_plus_live_three_is_fork():
    b = build([(0, 0), (1, 0), (2, 0), (3, 0), (5, 1), (5, 2), (5, 3)],
              [(-1, 0)])
    th = analyze_threats(b, PLAYER_X)
    assert any(t.kind == FOUR for t in th), describe(th)
    assert any(t.kind == LIVE_THREE for t in th), describe(th)
    assert is_winning_threat_set(th) is True


def test_five_detected():
    b = build([(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)], [])
    th = analyze_threats(b, PLAYER_X)
    assert any(t.kind == FIVE for t in th), describe(th)


def test_log_position_after_x31():
    """Та самая позиция: X(3,1) даёт ОДНУ закрытую четвёрку с точкой (2,0)."""
    moves = [
        ["O", 0, 0], ["X", 1, -1], ["O", 2, 2], ["X", 0, -2],
        ["O", -1, -1], ["X", -2, -2], ["O", 3, 3], ["X", 1, 1],
        ["O", 1, -2], ["X", -1, -3], ["O", -2, -4], ["X", 0, -4],
        ["O", -3, -1], ["X", 0, -3], ["O", 0, -5], ["X", 1, -3],
        ["O", 2, -3], ["X", 3, 1],
    ]
    b = from_moves(moves)
    th = analyze_threats(b, PLAYER_X)
    fours = [t for t in th if t.kind == FOUR]
    assert len(fours) == 1, describe(th)
    assert fours[0].points == ((2, 0),), describe(th)
    assert not any(t.kind in (LIVE_FOUR, LIVE_THREE) for t in th), describe(th)
    assert is_winning_threat_set(th) is False
    assert completion_points(b, PLAYER_X) == {(2, 0)}