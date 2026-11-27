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
    find_vcf_defense, block_open_three_threats,
    evaluate_position, minimax, search_vct,
    find_vct_defense, choose_resistance_move, assign_roles, find_own_fork,
)

from gomoku_analysis import (
    analyze_threats, is_double_threat_new, LIVE_THREE, LIVE_FOUR,
    window_potential, FOUR,
)


def build(x_stones: List[Tuple[int, int]], o_stones: List[Tuple[int, int]]) -> Board:
    b = Board()
    for x, y in x_stones:
        b.make_move(x, y, PLAYER_X)
    for x, y in o_stones:
        b.make_move(x, y, PLAYER_O)
    return b


def from_moves(moves: List) -> Board:
    """C12: понимает два формата ходов.
    компактный:  ["X", x, y]
    сохранённый: {"player": "X", "x": x, "y": y, ...}  (кнопка «Сохранить S»)
    """
    b = Board()
    for m in moves:
        if isinstance(m, dict):
            p, x, y = m["player"], m["x"], m["y"]
        else:
            p, x, y = m[0], m[1], m[2]
        mark = PLAYER_X if str(p).strip().upper() == "X" else PLAYER_O
        b.make_move(int(x), int(y), mark)
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


@case("защита от VCF: блок живой тройки опровергает")
def test_vcf_defense_blocks_live_three():
    b = build([(0, 0), (1, 0), (2, 0)], [(10, 10)])
    assert search_vcf(b, depth=6, player=PLAYER_X, is_attacking=True) is not None
    d = find_vcf_defense(b, PLAYER_O, depth=6)
    assert d in {(-1, 0), (3, 0)}, f"получено {d}"
    b.make_move(d[0], d[1], PLAYER_O)
    assert search_vcf(b, depth=6, player=PLAYER_X, is_attacking=True) is None


@case("защита от VCF: контр-четвёрка выигрывает темп")
def test_counter_four_defense():
    b = build([(0, 0), (1, 0), (2, 0), (4, 5)],
              [(5, 5), (6, 5), (7, 5)])
    assert search_vcf(b, depth=6, player=PLAYER_X, is_attacking=True) is not None
    d = find_vcf_defense(b, PLAYER_O, depth=6)
    assert d is not None, "контр-четвёрка должна опровергать VCF"
    b.make_move(d[0], d[1], PLAYER_O)
    assert search_vcf(b, depth=6, player=PLAYER_X, is_attacking=True) is None


@case("блок тройки не возвращается, если все блоки проигрывают VCF")
def test_no_safe_block_when_fork():
    b = build([(0, 0), (1, 0), (2, 0), (0, 1), (0, 2)], [(10, 10)])
    assert check_double_threat(b, PLAYER_X) is True
    assert block_open_three_threats(b, PLAYER_O) is None


@case("оценка: одна четвёрка не терминал, две — терминал")
def test_eval_no_double_counting():
    single = build([(0, 0), (1, 0), (2, 0), (3, 0)], [(-1, 0)])
    double = build([(0, 0), (1, 0), (2, 0), (3, 0),
                    (5, 1), (5, 2), (5, 3), (5, 4)], [(-1, 0), (5, 0)])
    s1 = evaluate_position(single, PLAYER_X, to_move=PLAYER_O)
    s2 = evaluate_position(double, PLAYER_X, to_move=PLAYER_O)
    assert s1 < 9_000_000, f"одна закрытая четвёрка не должна быть терминалом: {s1}"
    assert s2 >= 9_000_000, f"две четвёрки не блокируются одним ходом: {s2}"


@case("оценка учитывает темп")
def test_eval_tempo():
    b = build([(0, 0), (1, 0), (2, 0), (3, 0)], [(-1, 0)])
    assert evaluate_position(b, PLAYER_X, to_move=PLAYER_X) >= 9_000_000
    assert evaluate_position(b, PLAYER_X, to_move=PLAYER_O) < 9_000_000


@case("оценка: живая тройка дороже спящей")
def test_eval_live_vs_sleeping():
    live = build([(0, 0), (1, 0), (2, 0)], [])
    sleep = build([(0, 0), (1, 0), (2, 0)], [(-2, 0), (4, 0)])
    assert evaluate_position(live, PLAYER_X, to_move=PLAYER_O) > \
           evaluate_position(sleep, PLAYER_X, to_move=PLAYER_O)


@case("оценка: мёртвая тройка в коридоре почти ничего не стоит")
def test_eval_dead_three():
    b = build([(0, 0), (0, 1), (0, 2)], [(0, -1), (0, 3)])
    assert abs(evaluate_position(b, PLAYER_X, to_move=PLAYER_O)) < 1000


@case("оценка симметрична относительно смены стороны")
def test_eval_symmetry():
    b = build([(0, 0), (1, 0), (2, 0)], [(-2, 0), (4, 0)])
    for t in (PLAYER_X, PLAYER_O):
        assert evaluate_position(b, PLAYER_X, to_move=t) == \
               -evaluate_position(b, PLAYER_O, to_move=t)


@case("Zobrist: make/undo восстанавливает хеш")
def test_zobrist_make_undo():
    b = build([(0, 0), (1, 0)], [(0, 1)])
    h0 = b.zhash
    b.make_move(5, 5, PLAYER_X)
    assert b.zhash != h0
    b.undo_move()
    assert b.zhash == h0


@case("Zobrist: разные позиции — разные хеши")
def test_zobrist_distinct():
    assert build([(0, 0)], []).zhash != build([(1, 0)], []).zhash


@case("TT не меняет результат minimax")
def test_tt_same_result():
    b = build([(0, 0), (1, 0)], [(0, 1)])
    v1 = minimax(b, depth=2, alpha=-10**9, beta=10**9, is_maximizing=True,
                 player=PLAYER_X, budget=[100000], tt=None)
    v2 = minimax(b, depth=2, alpha=-10**9, beta=10**9, is_maximizing=True,
                 player=PLAYER_X, budget=[100000], tt={})
    assert v1 == v2, f"без TT {v1}, с TT {v2}"


@case("VCT находит выигрыш, которого не видит VCF")
def test_vct_finds_win_vcf_misses():
    b = build([(1, 0), (2, 0), (0, 1), (0, 2)], [(10, 10)])
    assert search_vcf(b, depth=6, player=PLAYER_X, is_attacking=True) is None
    m = search_vct(b, depth=4, player=PLAYER_X, is_attacking=True,
                   budget=[2000], tt={})
    # выигрывающих первых ходов несколько — конкретную клетку не фиксируем
    assert m is not None, "VCT должен найти форсированный выигрыш"


@case("вилка 3-3 в (0,0) распознаётся анализатором")
def test_fork_at_origin():
    b = build([(1, 0), (2, 0), (0, 1), (0, 2)], [(10, 10)])
    b.make_move(0, 0, PLAYER_X)
    assert is_double_threat_new(b, PLAYER_X) is True


@case("линия VCT: (-2,3) -> O(-1,2) -> X(0,0) — вилка")
def test_vct_concrete_line():
    b = build([(1, 0), (2, 0), (0, 1), (0, 2)], [(10, 10)])

    b.make_move(-2, 3, PLAYER_X)
    live = [t for t in analyze_threats(b, PLAYER_X) if t.kind == LIVE_THREE]
    assert len(live) == 1, "должна быть ровно одна живая тройка"
    assert live[0].points == ((-1, 2),), f"ключевая точка одна: {live[0].points}"

    # если O не парирует — X делает живую четвёрку
    b.make_move(-1, 2, PLAYER_X)
    assert any(t.kind == LIVE_FOUR for t in analyze_threats(b, PLAYER_X))
    b.undo_move()

    # O парирует, но вилка всё равно возникает
    b.make_move(-1, 2, PLAYER_O)
    b.make_move(0, 0, PLAYER_X)
    assert is_double_threat_new(b, PLAYER_X) is True


@case("VCT не выдумывает победу, если тройку можно парировать")
def test_vct_no_false_win():
    b = build([(1, 0), (2, 0)], [(10, 10)])
    m = search_vct(b, depth=4, player=PLAYER_X, is_attacking=True,
                   budget=[2000], tt={})
    assert m is None, f"ложная победа: {m}"


@case("VCT проваливается, если противник собирает пятёрку первым")
def test_vct_fails_when_defender_wins():
    b = build([(1, 0), (2, 0), (0, 1), (0, 2)],
              [(5, 5), (6, 5), (7, 5), (8, 5)])
    m = search_vct(b, depth=4, player=PLAYER_X, is_attacking=True,
                   budget=[2000], tt={})
    assert m is None, f"противник выигрывает первым, VCT быть не должно: {m}"


@case("защита от VCT находится (контр-четвёрка или блок вилки)")
def test_vct_defense_found():
    # у X вилка 3-3 в (0,0); у O есть спящая тройка для контр-четвёрки
    b = build([(1, 0), (2, 0), (0, 1), (0, 2), (4, 5)],
              [(5, 5), (6, 5), (7, 5)])
    assert search_vct(b, depth=4, player=PLAYER_X, is_attacking=True,
                      budget=[2000], tt={}) is not None
    d = find_vct_defense(b, PLAYER_O, depth=4)
    assert d is not None, "защита должна существовать"
    b.make_move(d[0], d[1], PLAYER_O)
    assert search_vct(b, depth=4, player=PLAYER_X, is_attacking=True,
                      budget=[2000], tt={}) is None, "защита должна опровергать VCT"


@case("защита от VCT не нужна, когда VCT нет")
def test_vct_defense_not_needed():
    b = build([(1, 0), (2, 0)], [(10, 10)])
    assert search_vct(b, depth=4, player=PLAYER_X, is_attacking=True,
                      budget=[2000], tt={}) is None
    assert find_vct_defense(b, PLAYER_O, depth=4) is None


@case("Board.copy: снапшот независим")
def test_board_copy():
    b = build([(0, 0), (1, 0)], [(0, 1)])
    c = b.copy()
    assert c.grid == b.grid and c.zhash == b.zhash
    c.make_move(5, 5, PLAYER_X)
    assert (5, 5) not in b.grid
    assert b.zhash != c.zhash


@case("поиск на снапшоте не меняет исходную доску")
def test_search_on_snapshot():
    b = build([(0, 0), (1, 0), (2, 0)], [(10, 10)])
    before, h = dict(b.grid), b.zhash
    c = b.copy()
    get_best_move(c, PLAYER_X)
    assert b.grid == before and b.zhash == h, "исходная доска изменилась"
    assert c.grid == before and c.zhash == h, "снапшот не восстановлен"


@case("позиция после 17 ходов: VCF у X есть, защиты нет")
def test_lost_position_detected():
    moves = [
        ["X", -1, -2], ["O", -3, -2], ["X", -1, -3], ["O", -4, -2],
        ["X", -1, -4], ["O", -1, -5], ["X", -1, -1], ["O", -1, 0],
        ["X", 0, -3], ["O", -2, -1], ["X", -4, -3], ["O", 1, -3],
        ["X", 0, -2], ["O", 0, 1], ["X", 1, 2], ["O", 1, -2],
        ["X", 0, -1],
    ]
    b = from_moves(moves)
    assert search_vcf(b, depth=12, player=PLAYER_X, is_attacking=True) is not None
    assert find_vcf_defense(b, PLAYER_O, depth=12) is None


@case("режим сопротивления возвращает допустимый ход")
def test_resistance_move_valid():
    b = build([(0, 0), (1, 0), (2, 0), (0, 1), (0, 2)], [(10, 10)])
    m = choose_resistance_move(b, PLAYER_O)
    assert m is not None and b.is_empty(m[0], m[1])


@case("роли: первым всегда X")
def test_assign_roles():
    assert assign_roles(False) == (PLAYER_X, PLAYER_O)
    assert assign_roles(True) == (PLAYER_O, PLAYER_X)


@case("потенциал: зажатая линия теряет вклад")
def test_potential_capped_line():
    opened = build([(0, 0), (1, 0), (2, 0)], [])
    capped = build([(0, 0), (1, 0), (2, 0)], [(-1, 0), (3, 0)])
    assert window_potential(opened, PLAYER_X) > window_potential(capped, PLAYER_X)


@case("оценка штрафует потенциал противника")
def test_eval_penalizes_opponent_potential():
    b1 = build([(0, 0), (1, 0)], [])
    b2 = build([(0, 0), (1, 0)], [(5, 5), (6, 5)])
    assert evaluate_position(b1, PLAYER_X, to_move=PLAYER_X) > \
           evaluate_position(b2, PLAYER_X, to_move=PLAYER_X)


# ---------- раннер и утилиты ----------

@case("C1: мёртвая тройка рядом с живой четвёркой остаётся мёртвой")
def test_c1_dead_three_near_live_four():
    b = build([(0, 0), (1, 0), (2, 0), (3, 0), (8, 0), (9, 0), (10, 0)], [(11, 0)])
    th = analyze_threats(b, PLAYER_X)
    assert any(t.kind == LIVE_FOUR for t in th), "живая четвёрка должна быть найдена"
    bad = [t for t in th if t.kind == LIVE_THREE and t.stones == ((8, 0), (9, 0), (10, 0))]
    assert not bad, f"тройка (8,9,10) мёртвая, но объявлена живой: {bad}"


@case("C1: та же тройка без соседней четвёрки — живая")
def test_c1_live_three_control():
    b = build([(8, 0), (9, 0), (10, 0)], [])
    th = analyze_threats(b, PLAYER_X)
    live = [t for t in th if t.kind == LIVE_THREE and t.stones == ((8, 0), (9, 0), (10, 0))]
    assert len(live) == 1, f"ожидалась одна живая тройка, получено: {th}"


@case("C2: четвёрка с хвостом не должна считаться дважды")
def test_c2_four_with_tail_not_double_counted():
    plain = build([(0, 0), (1, 0), (2, 0), (3, 0)], [(-1, 0)])
    tail = build([(0, 0), (1, 0), (2, 0), (3, 0), (5, 0)], [(-1, 0)])
    s_plain = evaluate_position(plain, PLAYER_X, to_move=PLAYER_O)
    s_tail = evaluate_position(tail, PLAYER_X, to_move=PLAYER_O)
    assert s_tail - s_plain < 20_000, \
        f"хвост добавил {s_tail - s_plain} очков — четвёрка посчитана дважды"


@case("C4: вилка не предлагается, если у противника есть более быстрый VCF")
def test_c4_fork_rejected_when_defender_has_vcf():
    b = build([(1, 0), (2, 0), (0, 1), (0, 2)], [(5, 5), (6, 5), (7, 5)])
    # у X вилка 3-3 в (0,0), но O живой тройкой делает живую четвёрку и выигрывает раньше
    assert search_vcf(b, depth=8, player=PLAYER_O, is_attacking=True,
                      budget=[600]) is not None, "у O должен быть VCF"
    assert find_own_fork(b, PLAYER_X) is None, "вилка не должна предлагаться"


@case("C4: та же вилка годится, когда у противника нет VCF")
def test_c4_fork_allowed_without_defender_vcf():
    b = build([(1, 0), (2, 0), (0, 1), (0, 2)], [(10, 10)])
    assert find_own_fork(b, PLAYER_X) == (0, 0)


@case("C3/C5: обрыв поиска отмечается и не отравляет кэш VCT")
def test_truncation_marked_and_tt_clean():
    import gomoku
    b = build([(1, 0), (2, 0), (0, 1), (0, 2)], [(10, 10)])
    gomoku._TRUNCATED[0] = 0
    tt = {}
    search_vct(b, depth=4, player=PLAYER_X, is_attacking=True, budget=[1], tt=tt)
    assert gomoku._TRUNCATED[0] > 0, "обрыв по бюджету должен быть отмечен"
    assert None not in tt.values(), f"в кэш попал недоказанный «победы нет»: {tt}"


@case("C3: счётчик обрывов сбрасывается в начале хода ИИ")
def test_truncation_counter_reset():
    import gomoku
    gomoku._TRUNCATED[0] = 99
    b = build([(0, 0), (1, 0), (2, 0)], [(10, 10)])
    get_best_move(b, PLAYER_X)
    assert gomoku._TRUNCATED[0] < 99, "счётчик должен обнуляться в обёртке get_best_move"


@case("C8: проверка вилки делает пробные ходы через make_move")
def test_fork_uses_make_move():
    class Tracked(Board):
        def __init__(self):
            super().__init__()
            self.calls = 0
        def make_move(self, x, y, p):
            self.calls += 1
            return super().make_move(x, y, p)
    b = Tracked()
    for x, y in [(1, 0), (2, 0), (0, 1), (0, 2)]:
        b.make_move(x, y, PLAYER_X)
    b.make_move(10, 10, PLAYER_O)
    b.make_move(0, 0, PLAYER_X)
    before = b.calls
    assert is_double_threat_new(b, PLAYER_X) is True
    assert b.calls > before, "пробные ходы защитника шли в обход make_move"


@case("C12: from_moves понимает формат сохранённой партии")
def test_from_moves_dict_format():
    moves = [{"n": 1, "player": "X", "x": 0, "y": 0, "elapsed": None, "analysis": ""},
             {"n": 2, "player": "O", "x": 1, "y": 0, "elapsed": 0.5, "analysis": "лог"}]
    b = from_moves(moves)
    assert b.get_cell(0, 0) == PLAYER_X
    assert b.get_cell(1, 0) == PLAYER_O
    assert len(b.move_history) == 2


@case("C12: from_moves по-прежнему понимает компактный формат")
def test_from_moves_list_format():
    b = from_moves([["X", 0, 0], ["O", 1, 0]])
    assert b.get_cell(0, 0) == PLAYER_X
    assert b.get_cell(1, 0) == PLAYER_O


@case("C7: в кандидаты защиты входят клетки будущих четвёрок противника")
def test_vcf_defense_candidates_widened():
    from gomoku import vcf_defense_candidates
    # спящая тройка OXXX: живых троек нет, но (3,0) и (4,0) — его будущие четвёрки
    b = build([(0, 0), (1, 0), (2, 0)], [(-1, 0)])
    cands = vcf_defense_candidates(b, PLAYER_O, (3, 0))
    assert (4, 0) in cands, f"клетка будущей четвёрки не попала в список: {cands}"


@case("S2: five_through видит пятёрку через клетку и не путает с четвёркой")
def test_five_through_basic():
    from gomoku import five_through
    b = build([(0, 0), (1, 0), (2, 0), (3, 0)], [])
    assert five_through(b, 0, 0, PLAYER_X) is False
    b.make_move(4, 0, PLAYER_X)
    assert five_through(b, 4, 0, PLAYER_X) is True
    assert five_through(b, 2, 0, PLAYER_X) is True
    assert five_through(b, 4, 0, PLAYER_O) is False


@case("S2: быстрая проверка пятёрки совпадает с полной на серии ходов")
def test_five_through_matches_full():
    from gomoku import five_through, check_five
    b = Board()
    seq = [(0, 0), (1, 0), (0, 1), (2, 0), (0, 2), (3, 0), (0, 3), (4, 0), (0, 4)]
    for i, (x, y) in enumerate(seq):
        p = PLAYER_X if i % 2 == 0 else PLAYER_O
        b.make_move(x, y, p)
        assert five_through(b, x, y, p) == check_five(b, p), f"расхождение на ходу {i}"


@case("S1a: кэш окон не меняет результат анализатора")
def test_window_cache_same_result():
    from gomoku_analysis import clear_window_cache
    b = build([(0, 0), (1, 0), (2, 0), (0, 1), (0, 2)], [(10, 10), (-3, 2)])
    clear_window_cache()
    cold = sorted((t.kind, t.stones, t.points) for t in analyze_threats(b, PLAYER_X))
    warm = sorted((t.kind, t.stones, t.points) for t in analyze_threats(b, PLAYER_X))
    assert cold == warm, "кэш изменил результат"
    clear_window_cache()
    again = sorted((t.kind, t.stones, t.points) for t in analyze_threats(b, PLAYER_X))
    assert cold == again, "после очистки результат другой"


@case("S1a: кэш окон наполняется и очищается")
def test_window_cache_populates():
    import gomoku_analysis as ga
    ga.clear_window_cache()
    ga.clear_threat_cache()      # верхний кэш иначе скроет нижний
    b = build([(0, 0), (1, 0), (2, 0)], [])
    ga.analyze_threats(b, PLAYER_X)
    assert len(ga._WINDOW_CACHE) > 0, "кэш пуст — значит не работает"
    ga.clear_window_cache()
    assert len(ga._WINDOW_CACHE) == 0


@case("S7a: после углубления ИИ по-прежнему находит форсированную вилку")
def test_root_still_finds_fork():
    b = build([(1, 0), (2, 0), (0, 1), (0, 2)], [(10, 10)])
    m = get_best_move(b, PLAYER_X)
    assert m is not None and b.is_empty(m[0], m[1])
    b.make_move(m[0], m[1], PLAYER_X)
    assert is_double_threat_new(b, PLAYER_X), f"ход {m} не создаёт вилку"


@case("S5a: кэш линий не меняет потенциал и наборы кандидатов")
def test_line_cache_same_result():
    from gomoku_analysis import (clear_line_cache, four_move_candidates,
                                 threat_move_candidates)
    b = build([(0, 0), (1, 0), (2, 0), (0, 1), (0, 2)], [(10, 10), (-3, 2)])

    def snap():
        return (window_potential(b, PLAYER_X),
                sorted(four_move_candidates(b, PLAYER_X)),
                sorted(threat_move_candidates(b, PLAYER_X)))

    clear_line_cache()
    cold = snap()
    warm = snap()
    assert cold == warm, "кэш изменил результат"
    clear_line_cache()
    assert cold == snap(), "после очистки результат другой"


@case("S5a: кэш линий наполняется и очищается")
def test_line_cache_populates():
    import gomoku_analysis as ga
    ga.clear_line_cache()
    b = build([(0, 0), (1, 0), (2, 0)], [])
    ga.window_potential(b, PLAYER_X)
    ga.four_move_candidates(b, PLAYER_X)
    ga.threat_move_candidates(b, PLAYER_X)
    assert len(ga._LINE_CACHE) > 0, "кэш пуст — значит не работает"
    ga.clear_line_cache()
    assert len(ga._LINE_CACHE) == 0


@case("S6a: лучший найденный ход запоминается для аварийного возврата")
def test_best_so_far_recorded():
    import gomoku
    b = build([(0, 0), (1, 0)], [(5, 5), (6, 5)])
    m = get_best_move(b, PLAYER_X)
    assert gomoku._BEST_SO_FAR[0] == m, "лучший ход поиска не запомнен"


@case("S6a: при жёстком лимите времени возвращается допустимый ход")
def test_tiny_time_limit_returns_valid_move():
    import gomoku
    old = gomoku.MOVE_TIME_LIMIT
    gomoku.MOVE_TIME_LIMIT = 0.001
    try:
        b = build([(0, 0), (1, 0), (2, 0), (0, 1), (0, 2)], [(10, 10), (-3, 2)])
        m = get_best_move(b, PLAYER_X)
        assert m is not None and b.is_empty(m[0], m[1])
        assert len(b.move_history) == 7, "доска не восстановлена после обрыва"
    finally:
        gomoku.MOVE_TIME_LIMIT = old


@case("S6b: в логе есть время каждой итерации углубления")
def test_depth_timing_logged():
    b = build([(0, 0), (1, 0)], [(5, 5), (6, 5)])
    get_best_move(b, PLAYER_X)
    lines = [ln for ln in DEBUG_LOG if ln.strip().startswith("глубина ")]
    assert lines, "нет строк об итерациях углубления"
    assert any("заняло" in ln for ln in lines), f"нет времени итераций: {lines}"


@case("S6c: прогноз не даёт начать итерацию, которая не влезет")
def test_depth_prediction():
    from gomoku import _should_start_depth
    assert _should_start_depth(0.0, 10.0, 12.0) is True    # первая итерация всегда
    assert _should_start_depth(0.5, 10.0, 12.0) is True    # 0.5*3=1.5 <= 2.0
    assert _should_start_depth(0.8, 10.0, 12.0) is False   # 2.4 > 2.0
    assert _should_start_depth(0.5, 10.0, 0.0) is True     # без дедлайна — можно


@case("S6c: в логе есть метки времени у строк")
def test_log_has_time_marks():
    b = build([(0, 0), (1, 0)], [(5, 5), (6, 5)])
    get_best_move(b, PLAYER_X)
    assert DEBUG_LOG, "лог пуст"
    assert any("(t=" in ln for ln in DEBUG_LOG), "нет меток времени"


@case("S1c: кэш по позиции не меняет угрозы и потенциал")
def test_threat_cache_same_result():
    from gomoku_analysis import clear_threat_cache
    b = build([(0, 0), (1, 0), (2, 0), (0, 1), (0, 2)], [(10, 10), (-3, 2)])

    def snap():
        return (sorted((t.kind, t.stones, t.points)
                       for t in analyze_threats(b, PLAYER_X)),
                window_potential(b, PLAYER_X))

    clear_threat_cache()
    cold = snap()
    warm = snap()
    assert cold == warm, "кэш изменил результат"
    clear_threat_cache()
    assert cold == snap(), "после очистки результат другой"


@case("S1c: кэш по позиции замечает новый камень и его отмену")
def test_threat_cache_position_sensitive():
    from gomoku_analysis import clear_threat_cache
    clear_threat_cache()
    b = build([(0, 0), (1, 0), (2, 0)], [])
    before = sorted(t.kind for t in analyze_threats(b, PLAYER_X))
    b.make_move(3, 0, PLAYER_X)
    after = sorted(t.kind for t in analyze_threats(b, PLAYER_X))
    assert before != after, "кэш не заметил новый камень"
    b.undo_move()
    assert sorted(t.kind for t in analyze_threats(b, PLAYER_X)) == before


def _clear_all_caches() -> None:
    """Каждый тест начинается с чистых кэшей.
    Иначе результат зависит от порядка запуска: верхний кэш скрывает нижний."""
    import gomoku_analysis as ga
    for name in ("clear_window_cache", "clear_line_cache", "clear_threat_cache",
                 "reset_stats"):
        fn = getattr(ga, name, None)
        if fn is not None:
            fn()


@case("S1b: линии доски совпадают с пересчётом из grid после ходов и отмен")
def test_board_lines_invariant():
    from gomoku_analysis import _line_inv, _param

    def rebuilt(b):
        out = [{}, {}, {}, {}]
        for (gx, gy), p in b.grid.items():
            for d in range(4):
                out[d].setdefault(_line_inv(d, gx, gy), {})[_param(d, gx, gy)] = p
        return out

    b = Board()
    seq = [(0, 0), (1, 0), (0, 1), (2, 0), (0, 2), (-1, -1), (3, 3), (5, -2)]
    for i, (x, y) in enumerate(seq):
        b.make_move(x, y, PLAYER_X if i % 2 == 0 else PLAYER_O)
        assert b.lines == rebuilt(b), f"расхождение после хода {i}"
    for i in range(len(seq)):
        b.undo_move()
        assert b.lines == rebuilt(b), f"расхождение после отмены {i}"


@case("S1b: кэш геометрии линий не меняет результаты")
def test_line_view_cache_same_result():
    import gomoku_analysis as ga
    b = build([(0, 0), (1, 0), (2, 0), (0, 1), (0, 2)], [(10, 10), (-3, 2)])

    def snap():
        return (sorted((t.kind, t.stones, t.points)
                       for t in analyze_threats(b, PLAYER_X)),
                window_potential(b, PLAYER_X),
                sorted(ga.four_move_candidates(b, PLAYER_X)),
                sorted(ga.threat_move_candidates(b, PLAYER_X)))

    ga.clear_line_cache(); ga.clear_threat_cache()
    cold = snap()
    warm = snap()
    assert cold == warm, "кэш геометрии изменил результат"
    ga.clear_line_cache(); ga.clear_threat_cache()
    assert cold == snap(), "после очистки результат другой"


@case("S1b: копия доски не делит линии с оригиналом")
def test_board_copy_lines_independent():
    b = build([(0, 0), (1, 0)], [(0, 1)])
    c = b.copy()
    c.make_move(5, 5, PLAYER_X)
    assert (5, 5) not in b.grid
    assert b.lines != c.lines, "линии копии связаны с оригиналом"


@case("S1c: выключенный кэш по позиции даёт те же результаты")
def test_position_cache_flag_equivalence():
    import gomoku_analysis as ga
    b = build([(0, 0), (1, 0), (2, 0), (0, 1), (0, 2)], [(10, 10), (-3, 2)])

    def snap():
        return (sorted((t.kind, t.stones, t.points)
                       for t in analyze_threats(b, PLAYER_X)),
                window_potential(b, PLAYER_X))

    try:
        ga.USE_POSITION_CACHE = True
        ga.clear_threat_cache()
        on = snap()
        ga.USE_POSITION_CACHE = False
        ga.clear_threat_cache()
        off = snap()
        assert on == off, "кэш по позиции меняет результат"
    finally:
        ga.USE_POSITION_CACHE = True


@case("S1c: счётчики работы — попадания и полные расчёты")
def test_position_cache_stats():
    import gomoku_analysis as ga
    b = build([(0, 0), (1, 0), (2, 0), (0, 1), (0, 2)], [(10, 10), (-3, 2)])
    try:
        ga.USE_POSITION_CACHE = True
        ga.clear_threat_cache()
        ga.reset_stats()
        for _ in range(5):
            analyze_threats(b, PLAYER_X)
        assert ga.STATS["analyze_full"] == 1, f"analyze_full={ga.STATS['analyze_full']}, ожидали 1"
        assert ga.STATS["analyze_hit"] == 4, f"analyze_hit={ga.STATS['analyze_hit']}, ожидали 4"
        for _ in range(5):
            window_potential(b, PLAYER_X)
        assert ga.STATS["pot_full"] == 1, f"pot_full={ga.STATS['pot_full']}, ожидали 1"
        assert ga.STATS["pot_hit"] == 4, f"pot_hit={ga.STATS['pot_hit']}, ожидали 4"

        ga.USE_POSITION_CACHE = False
        ga.clear_threat_cache()
        ga.reset_stats()
        for _ in range(5):
            analyze_threats(b, PLAYER_X)
        assert ga.STATS["analyze_full"] == 5, f"analyze_full={ga.STATS['analyze_full']}, ожидали 5"
        assert ga.STATS["analyze_hit"] == 0, f"analyze_hit={ga.STATS['analyze_hit']}, ожидали 0"
    finally:
        ga.USE_POSITION_CACHE = True


@case("C15: VCT находит темповый блок при четвёрке защитника (партия 2026-11-24)")
def test_vct_forced_block_game_regression():
    from gomoku import PLAYER_X, PLAYER_O, search_vct
    from gomoku_analysis import completion_points
    # позиция после 15 ходов партии game_2026_11_24 + контр-четвёрка O(-3,1)
    b = build([(-1, 0), (0, -1), (1, -2), (0, -3), (-2, -1),
               (0, 2), (-5, -3), (-5, 1)],
              [(-3, -1), (-2, -2), (-2, 1), (-2, 0), (-1, 1),
               (-4, -2), (-4, 1), (-3, 1)])
    assert completion_points(b, PLAYER_O) == {(0, 1)}, "ожидалась закрытая четвёрка O"
    m = search_vct(b, depth=4, player=PLAYER_X, is_attacking=True,
                   budget=[1500], tt={})
    assert m == (0, 1), f"VCT X обязан найти блокирующую вилку (0,1), получено {m}"


@case("C15: защита контр-четвёркой не опровергает VCT автоматически")
def test_vct_defense_rejects_counter_four():
    from gomoku import PLAYER_X, PLAYER_O, find_vct_defense, search_vct
    # позиция после 15 ходов (O ещё не сыграл 16-й)
    b = build([(-1, 0), (0, -1), (1, -2), (0, -3), (-2, -1),
               (0, 2), (-5, -3), (-5, 1)],
              [(-3, -1), (-2, -2), (-2, 1), (-2, 0), (-1, 1),
               (-4, -2), (-4, 1)])
    d = find_vct_defense(b, PLAYER_O, depth=4, known_threat=(0, 1))
    assert d is not None, "защита должна быть найдена"
    assert d != (-3, 1), "(-3,1) отдаёт вилку — не опровержение"
    b.make_move(d[0], d[1], PLAYER_O)
    still = search_vct(b, depth=4, player=PLAYER_X, is_attacking=True,
                       budget=[1500], tt={})
    assert still is None, "выбранная защита должна действительно опровергать VCT"


@case("C15: своя пятёрка раньше чужой четвёрки (VCF и VCT)")
def test_own_five_beats_defender_four():
    # X: четвёрка (0,0)..(3,0), достройка (-1,0)/(4,0); O: четвёрка на y=5
    b = build([(0, 0), (1, 0), (2, 0), (3, 0)],
              [(0, 5), (1, 5), (2, 5), (3, 5)])
    vcf = search_vcf(b, depth=6, player=PLAYER_X, is_attacking=True, budget=[400])
    assert vcf in {(-1, 0), (4, 0)}, f"X обязан достроить пятёрку, получено {vcf}"
    vct = search_vct(b, depth=4, player=PLAYER_X, is_attacking=True,
                     budget=[400], tt={})
    assert vct in {(-1, 0), (4, 0)}, f"VCT тоже обязан, получено {vct}"


@case("C15: VCF находит четвёрку-блок при четвёрке защитника")
def test_vcf_forced_block():
    from gomoku_analysis import completion_points
    # O: закрытая четвёрка (0,0)..(3,0), достройка (4,0); (-1,0) занят X.
    # X(4,0) блокирует и создаёт живую четвёрку по вертикали x=4.
    b = build([(-1, 0), (4, 1), (4, 2), (4, 3)],
              [(0, 0), (1, 0), (2, 0), (3, 0)])
    assert completion_points(b, PLAYER_O) == {(4, 0)}, "ожидалась закрытая четвёрка O"
    m = search_vcf(b, depth=8, player=PLAYER_X, is_attacking=True, budget=[400])
    assert m == (4, 0), f"VCF X обязан найти четвёрку-блок (4,0), получено {m}"


@case("Ш34: PVS+TT-best не меняют оценку при полном поиске")
def test_pvs_tt_value_matches():
    import gomoku as G
    b = build([(0, 0), (1, 0), (2, 0)], [(0, 3), (1, 3)])
    kw = dict(depth=3, alpha=-10**9, beta=10**9, is_maximizing=True, player=PLAYER_X)
    base = G.minimax(b, budget=[20000], tt={}, **kw)
    try:
        G.USE_PVS = True
        G.USE_TT_BEST = True
        got = G.minimax(b, budget=[20000], tt={}, **kw)
    finally:
        G.USE_PVS = False
        G.USE_TT_BEST = False
    assert base == got, f"оценка изменилась: {base} -> {got}"


@case("Ш34: TT хранит лучший ход (задел под главную линию)")
def test_tt_stores_move():
    b = build([(0, 0), (1, 0), (2, 0)], [(0, 3), (1, 3)])
    tt = {}
    minimax(b, depth=2, alpha=-10**9, beta=10**9, is_maximizing=True,
            player=PLAYER_X, budget=[5000], tt=tt)
    assert tt, "TT пустая"
    assert all(len(v) == 3 for v in tt.values()), "запись TT без хода"


@case("Ш34: доска после get_best_move идентична исходной")
def test_board_integrity_after_search():
    b = build([(0, 0), (1, 0), (2, 0), (-1, 2)], [(0, 3), (1, 3), (2, 2)])
    before = (dict(b.grid), list(b.move_history), b.zhash,
              [{inv: dict(cells) for inv, cells in d.items()} for d in b.lines])
    get_best_move(b, PLAYER_X)
    after = (dict(b.grid), list(b.move_history), b.zhash,
             [{inv: dict(cells) for inv, cells in d.items()} for d in b.lines])
    assert before == after, "поиск изменил доску (лишний make/undo)"


@case("Ш36: оценка антисимметрична при обоих весах темпа")
def test_eval_antisymmetry_contest():
    import gomoku as G
    b = build([(0, 0), (1, 1), (2, 0)], [(-2, 1), (-3, 0)])
    try:
        for flag in (False, True):
            G.USE_CONTEST_EVAL = flag
            for tm in (PLAYER_X, PLAYER_O):
                a = G.evaluate_position(b, PLAYER_X, to_move=tm)
                c = G.evaluate_position(b, PLAYER_O, to_move=tm)
                assert a == -c, f"антисимметрия нарушена: {a} vs {c} (flag={flag})"
    finally:
        G.USE_CONTEST_EVAL = False


def run_tests(only: Optional[str] = None) -> int:
    passed = failed = known = 0
    print("=" * 70)
    print("ЭТАП 2 — анализатор подключён")
    print("=" * 70)
    for name, fn, known_bug in TESTS:
        if only and only.lower() not in name.lower():
            continue
        DEBUG_LOG.clear()
        _clear_all_caches()
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