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