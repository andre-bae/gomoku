import tkinter as tk
from tkinter import messagebox
from typing import Optional, List, Tuple, Dict
import threading

from gomoku_analysis import (
    analyze_threats, is_double_threat_new, is_winning_threat_set,
    completion_points, four_move_candidates, threat_move_candidates, describe,
    FIVE, LIVE_FOUR, FOUR, LIVE_THREE, SLEEPING_THREE,
)

import time

MASK64 = (1 << 64) - 1
POSITIONAL_TIME_LIMIT = 2.0   # секунд на позиционную фазу хода
TT_MAX_ENTRIES = 200_000

TT_EXACT, TT_LOWER, TT_UPPER = 0, 1, 2


def _zobrist_key(x: int, y: int, player: int) -> int:
    """Детерминированный 64-битный ключ клетки без состояния RNG."""
    h = ((x * 0x9E3779B97F4A7C15) ^ (y * 0xBF58476D1CE4E5B9) ^
         (player * 0x94D049BB133111EB)) & MASK64
    h = ((h ^ (h >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    h = ((h ^ (h >> 27)) * 0x94D049BB133111EB) & MASK64
    return (h ^ (h >> 31)) & MASK64


# Константы
EMPTY = 0
PLAYER_X = 1
PLAYER_O = 2
WIN_LENGTH = 5

# Отладочный лог
DEBUG_LOG: List[str] = []
DEBUG_ENABLED = True


def log(msg: str):
    if DEBUG_ENABLED:
        DEBUG_LOG.append(msg)


def player_name(p: int) -> str:
    return "X" if p == PLAYER_X else "O"


class Board:
    def __init__(self):
        self.grid: Dict[Tuple[int, int], int] = {}
        self.move_history: List[Tuple[int, int, int]] = []
        self.zhash: int = 0

    def make_move(self, x: int, y: int, player: int) -> bool:
        if (x, y) in self.grid:
            return False
        self.grid[(x, y)] = player
        self.move_history.append((x, y, player))
        self.zhash ^= _zobrist_key(x, y, player)
        return True

    def undo_move(self) -> Optional[Tuple[int, int, int]]:
        if not self.move_history:
            return None
        x, y, player = self.move_history.pop()
        del self.grid[(x, y)]
        self.zhash ^= _zobrist_key(x, y, player)
        return (x, y, player)

    def get_cell(self, x: int, y: int) -> int:
        return self.grid.get((x, y), EMPTY)

    def is_empty(self, x: int, y: int) -> bool:
        return (x, y) not in self.grid

    def get_candidate_moves(self, radius: int = 2) -> List[Tuple[int, int]]:
        if not self.grid:
            return [(0, 0)]
        candidates = set()
        for x, y in self.grid.keys():
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    nx, ny = x + dx, y + dy
                    if self.is_empty(nx, ny):
                        candidates.add((nx, ny))
        return list(candidates)

    def count_stones(self, player: int) -> int:
        return sum(1 for _, _, p in self.move_history if p == player)


def check_five(board: Board, player: int) -> bool:
    directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
    for x, y, p in board.move_history:
        if p != player:
            continue
        for dx, dy in directions:
            count = 1
            nx, ny = x + dx, y + dy
            while board.get_cell(nx, ny) == player:
                count += 1
                nx += dx
                ny += dy
            nx, ny = x - dx, y - dy
            while board.get_cell(nx, ny) == player:
                count += 1
                nx -= dx
                ny -= dy
            if count >= WIN_LENGTH:
                return True
    return False


def check_immediate_win(board: Board, player: int) -> Optional[Tuple[int, int]]:
    for x, y in board.get_candidate_moves(radius=1):
        board.make_move(x, y, player)
        if check_five(board, player):
            board.undo_move()
            return (x, y)
        board.undo_move()
    return None


def count_line(board: Board, x: int, y: int, dx: int, dy: int, player: int) -> Tuple[int, int]:
    length = 1
    open_ends = 0
    nx, ny = x + dx, y + dy
    while board.get_cell(nx, ny) == player:
        length += 1
        nx += dx
        ny += dy
    if board.get_cell(nx, ny) == EMPTY:
        open_ends += 1
    nx, ny = x - dx, y - dy
    while board.get_cell(nx, ny) == player:
        length += 1
        nx -= dx
        ny -= dy
    if board.get_cell(nx, ny) == EMPTY:
        open_ends += 1
    return length, open_ends


def count_line_with_gap(board: Board, x: int, y: int, dx: int, dy: int, player: int) -> Tuple[int, int, int]:
    pos_length = 0
    pos_gaps = 0
    pos_open = False
    nx, ny = x + dx, y + dy
    while True:
        cell = board.get_cell(nx, ny)
        if cell == player:
            pos_length += 1
            nx += dx
            ny += dy
        elif cell == EMPTY:
            if pos_gaps == 0:
                next_nx, next_ny = nx + dx, ny + dy
                if board.get_cell(next_nx, next_ny) == player:
                    pos_gaps += 1
                    nx, ny = next_nx, next_ny
                    continue
            pos_open = True
            break
        else:
            pos_open = False
            break

    neg_length = 0
    neg_gaps = 0
    neg_open = False
    nx, ny = x - dx, y - dy
    while True:
        cell = board.get_cell(nx, ny)
        if cell == player:
            neg_length += 1
            nx -= dx
            ny -= dy
        elif cell == EMPTY:
            if neg_gaps == 0:
                next_nx, next_ny = nx - dx, ny - dy
                if board.get_cell(next_nx, next_ny) == player:
                    neg_gaps += 1
                    nx, ny = next_nx, next_ny
                    continue
            neg_open = True
            break
        else:
            neg_open = False
            break

    total_length = pos_length + neg_length + 1
    total_gaps = pos_gaps + neg_gaps
    open_ends = (1 if pos_open else 0) + (1 if neg_open else 0)
    return total_length, total_gaps, open_ends


def get_potential_threats(board: Board, x: int, y: int, player: int) -> List[str]:
    """Этап 3: метки угроз берутся из анализатора, только по угрозам с новым камнем."""
    if not board.is_empty(x, y):
        return []
    board.make_move(x, y, player)
    try:
        threats = analyze_threats(board, player)
    finally:
        board.undo_move()
    out = []
    for t in threats:
        if (x, y) not in t.stones:
            continue
        if t.kind == FIVE:
            out.append('five')
        elif t.kind == LIVE_FOUR:
            out.append('open_four')
        elif t.kind == FOUR:
            out.append('closed_four')
        elif t.kind == LIVE_THREE:
            out.append('open_three')
        elif t.kind == SLEEPING_THREE:
            out.append('closed_three')
    return list(dict.fromkeys(out))

def generate_four_moves(board: Board, player: int) -> List[Tuple[int, int]]:
    """Этап 3: точный и быстрый критерий через окна анализатора."""
    return sorted(four_move_candidates(board, player))


def generate_threat_moves(board: Board, player: int) -> List[Tuple[int, int]]:
    """Этап 6: точный набор ходов-угроз через окна анализатора."""
    return sorted(threat_move_candidates(board, player))

def count_all_open_threes(board: Board, player: int, debug: bool = False) -> int:
    """Этап 2: считаем только ЖИВЫЕ тройки (способные стать живой четвёркой)."""
    threats = analyze_threats(board, player)
    live = [t for t in threats if t.kind == LIVE_THREE]
    if debug:
        for t in live:
            log(f"    живая тройка: камни={t.stones} ключевые={t.points}")
    return len(live)

def check_double_threat(board: Board, player: int) -> bool:
    """Этап 2: вилки считаются по уникальным угрозам нового анализатора."""
    return is_double_threat_new(board, player)


def search_vcf(board: Board, depth: int, player: int, is_attacking: bool,
               path=None, indent: int = 0, budget=None) -> Optional[Tuple[int, int]]:
    """
    Этап 3. Форсированный выигрыш серией четвёрок.
    Защита = точки достройки пятёрки атакующего (а не свои четвёрки защитника).
    Выигрыш засчитывается только если ПРОИГРЫВАЮТ ВСЕ защиты.
    Терминальные позиции проверяются до отсечения по глубине.
    """
    if path is None:
        path = []
    if budget is not None:
        if budget[0] <= 0:
            return None
        budget[0] -= 1

    attacker = player if is_attacking else (PLAYER_O if player == PLAYER_X else PLAYER_X)
    defender = PLAYER_O if attacker == PLAYER_X else PLAYER_X
    ind = "  " * indent

    # защитник собирает пятёрку первым — VCF атакующего не работает
    if completion_points(board, defender):
        return None

    win_now = completion_points(board, attacker)
    if win_now:
        m = sorted(win_now)[0]
        log(f"{ind}VCF: пятёрка {m} | путь: {' -> '.join(path + [f'{player_name(attacker)}{m}'])}")
        return m

    if depth <= 0:
        return None

    moves = generate_four_moves(board, attacker)
    if not moves:
        return None
    log(f"{ind}VCF d={depth} {player_name(attacker)}: {len(moves)} четвёрок -> {moves}")

    for move in moves:
        board.make_move(move[0], move[1], attacker)
        tag = f"{player_name(attacker)}{move}"

        if check_five(board, attacker):
            log(f"{ind}VCF: пятёрка {move} | путь: {' -> '.join(path + [tag])}")
            board.undo_move()
            return move

        # защитник может выиграть сразу — эта атака не годится
        if completion_points(board, defender):
            board.undo_move()
            continue

        threats = analyze_threats(board, attacker)
        if is_winning_threat_set(threats) and is_double_threat_new(board, attacker):
            log(f"{ind}VCF: неустранимая угроза после {move}")
            log(f"{ind}  путь: {' -> '.join(path + [tag])}")
            log(f"{ind}  угрозы: {describe(threats)}")
            board.undo_move()
            return move

        defenses = sorted({p for t in threats if t.kind in (FOUR, LIVE_FOUR) for p in t.points})
        if not defenses:
            board.undo_move()
            continue

        all_defenses_lose = True
        for d in defenses:
            board.make_move(d[0], d[1], defender)
            res = search_vcf(board, depth - 2, player, is_attacking,
                             path + [tag, f"{player_name(defender)}{d}"],
                             indent + 1, budget)
            board.undo_move()
            if res is None:
                all_defenses_lose = False
                break

        board.undo_move()
        if all_defenses_lose:
            return move

    return None

def search_vct(board: Board, depth: int, player: int, is_attacking: bool,
               path=None, indent: int = 0, budget=None, tt=None) -> Optional[Tuple[int, int]]:
    """
    Этап 6. Форсированный выигрыш непрерывными угрозами (четвёрки + живые тройки).
    Парирования защитника: точки достройки четвёрок, ключевые точки живых троек,
    контр-четвёрки (только когда у атакующего нет четвёрки).
    Выигрыш — только если проигрывают ВСЕ парирования. Бюджет — консервативный.
    """
    if path is None:
        path = []
    if budget is not None:
        if budget[0] <= 0:
            return None
        budget[0] -= 1

    attacker = player if is_attacking else (PLAYER_O if player == PLAYER_X else PLAYER_X)
    defender = PLAYER_O if attacker == PLAYER_X else PLAYER_X
    ind = "  " * indent

    if completion_points(board, defender):
        return None
    win_now = completion_points(board, attacker)
    if win_now:
        m = sorted(win_now)[0]
        log(f"{ind}VCT: пятёрка {m} | путь: {' -> '.join(path + [f'{player_name(attacker)}{m}'])}")
        return m
    if depth <= 0:
        return None

    key = None
    if tt is not None:
        key = (board.zhash, depth, attacker, 'vct')
        if key in tt:
            return tt[key]

    moves = generate_threat_moves(board, attacker)
    if not moves:
        return None
    log(f"{ind}VCT d={depth} {player_name(attacker)}: {len(moves)} ходов-угроз")

    result = None
    for move in moves:
        if budget is not None and budget[0] <= 0:
            break
        board.make_move(move[0], move[1], attacker)
        tag = f"{player_name(attacker)}{move}"

        if check_five(board, attacker):
            log(f"{ind}VCT: пятёрка {move} | путь: {' -> '.join(path + [tag])}")
            result = move
            board.undo_move()
            break

        if completion_points(board, defender):
            board.undo_move()
            continue

        threats = analyze_threats(board, attacker)
        has_four = any(t.kind in (FOUR, LIVE_FOUR) for t in threats)
        live3 = [t for t in threats if t.kind == LIVE_THREE]
        if not has_four and not live3:
            board.undo_move()
            continue                      # не форсирующая угроза

        if is_double_threat_new(board, attacker):
            log(f"{ind}VCT: неустранимая угроза после {move}")
            log(f"{ind}  путь: {' -> '.join(path + [tag])}")
            log(f"{ind}  угрозы: {describe(threats)}")
            result = move
            board.undo_move()
            break

        if has_four:
            parries = {p for t in threats if t.kind in (FOUR, LIVE_FOUR) for p in t.points}
        else:
            parries = {p for t in live3 for p in t.points}
            parries |= four_move_candidates(board, defender)   # контр-четвёрки

        if not parries:
            board.undo_move()
            continue

        all_parries_lose = True
        for d in sorted(parries):
            if budget is not None and budget[0] <= 0:
                all_parries_lose = False
                break
            board.make_move(d[0], d[1], defender)
            res = search_vct(board, depth - 2, player, is_attacking,
                             path + [tag, f"{player_name(defender)}{d}"],
                             indent + 1, budget, tt)
            board.undo_move()
            if res is None:
                all_parries_lose = False
                break

        board.undo_move()
        if all_parries_lose:
            result = move
            break

    if tt is not None and key is not None:
        tt[key] = result
    return result


def debug_dump_all_threes(board: Board, player: int):
    log(f"  --- Все тройки {player_name(player)} ---")
    directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
    dir_names = {(1, 0): "гориз", (0, 1): "верт", (1, 1): "диаг\\", (1, -1): "диаг/"}
    found_any = False
    seen = set()
    for x, y, p in board.move_history:
        if p != player:
            continue
        for dx, dy in directions:
            if (board.get_cell(x, y) == player and
                    board.get_cell(x + dx, y + dy) == player and
                    board.get_cell(x + 2 * dx, y + 2 * dy) == player):
                key = (x, y, dx, dy)
                if key in seen:
                    continue
                seen.add(key)
                before = board.get_cell(x - dx, y - dy)
                after = board.get_cell(x + 3 * dx, y + 3 * dy)
                before_s = {EMPTY: "ПУСТО", PLAYER_X: "X", PLAYER_O: "O"}.get(before, "?")
                after_s = {EMPTY: "ПУСТО", PLAYER_X: "X", PLAYER_O: "O"}.get(after, "?")
                if before == player:
                    status = "не начало (есть камень перед)"
                elif after == player:
                    status = "это часть четверки+"
                elif before == EMPTY and after == EMPTY:
                    status = "ОТКРЫТАЯ"
                elif before == EMPTY or after == EMPTY:
                    status = "ПОЛУОТКРЫТАЯ"
                else:
                    status = "ЗАКРЫТАЯ"
                log(f"    Тройка ({x},{y})+({x + dx},{y + dy})+({x + 2 * dx},{y + 2 * dy}) [{dir_names[(dx, dy)]}] "
                    f"до={before_s}({x - dx},{y - dy}) после={after_s}({x + 3 * dx},{y + 3 * dy}) => {status}")
                found_any = True
    if not found_any:
        log(f"    (ни одной тройки не найдено)")


def find_all_open_three_blocks(board: Board, player: int) -> List[Tuple[int, int]]:
    """Этап 4: ключевые точки живых троек из анализатора (а не старые паттерны)."""
    points = set()
    for t in analyze_threats(board, player):
        if t.kind == LIVE_THREE:
            points.update(t.points)
    return sorted(points)

def find_vcf_defense(board: Board, player: int, depth: int = 12,
                     known_threat: Optional[Tuple[int, int]] = None) -> Optional[Tuple[int, int]]:
    """
    Этап 4. Ищем ход, после которого у противника НЕ остаётся VCF.
    Кандидаты: клетка первого хода VCF, точки достройки его четвёрок,
    ключевые точки живых троек, наши контр-четвёрки.
    Каждый кандидат проверяется повторным поиском.
    """
    opponent = PLAYER_O if player == PLAYER_X else PLAYER_X

    threat = known_threat
    if threat is None:
        threat = search_vcf(board, depth=depth, player=opponent,
                            is_attacking=True, budget=[2000])
    if threat is None:
        return None

    candidates = {threat}
    candidates.update(completion_points(board, opponent))
    for t in analyze_threats(board, opponent):
        if t.kind == LIVE_THREE:
            candidates.update(t.points)
    candidates.update(generate_four_moves(board, player))   # контр-четвёрки

    verified = []
    for move in sorted(candidates):
        if not board.is_empty(move[0], move[1]):
            continue
        board.make_move(move[0], move[1], player)
        still = search_vcf(board, depth=depth, player=opponent,
                           is_attacking=True, budget=[2000])
        if still is None:
            score = evaluate_position(board, player, to_move=opponent)
            verified.append((score, move))
            log(f"    защита {move} опровергает VCF (оценка {score})")
        else:
            log(f"    защита {move} не помогает: VCF {still}")
        board.undo_move()

    if not verified:
        return None
    verified.sort(key=lambda x: (-x[0], x[1]))
    return verified[0][1]

def evaluate_threats_after_move(board: Board, player: int) -> Tuple[int, str]:
    max_level = 0
    threat_desc = "нет угроз"

    for x, y in board.get_candidate_moves(radius=2):
        if not board.is_empty(x, y):
            continue

        threats = get_potential_threats(board, x, y, player)

        if 'five' in threats:
            if max_level < 4:
                max_level = 4
                threat_desc = f"пятёрка в ({x},{y})"
        if 'open_four' in threats:
            if max_level < 3:
                max_level = 3
                threat_desc = f"открытая четвёрка в ({x},{y})"
        if 'closed_four' in threats:
            if max_level < 2:
                max_level = 2
                threat_desc = f"четвёрка (закрытая/с разрывом) в ({x},{y})"
        if 'open_three' in threats:
            if max_level < 1:
                max_level = 1
                threat_desc = f"открытая тройка в ({x},{y})"

        board.make_move(x, y, player)
        open_threes = count_all_open_threes(board, player)
        board.undo_move()

        if open_threes >= 2:
            if max_level < 3:
                max_level = 3
                threat_desc = f"вилка в ({x},{y})"

        if max_level >= 3:
            break

    return max_level, threat_desc


def block_open_three_threats(board: Board, player: int) -> Optional[Tuple[int, int]]:
    """
    Этап 4. Блокируем живую тройку, но НЕ возвращаем блок,
    после которого противник всё равно выигрывает VCF.
    """
    if len(board.move_history) < 4:
        log("  (пропущено: ходов < 4)")
        return None
    opponent = PLAYER_O if player == PLAYER_X else PLAYER_X
    debug_dump_all_threes(board, opponent)

    threats = find_all_open_three_blocks(board, opponent)
    log(f"  ключевые точки живых троек: {threats}")
    if not threats:
        return None

    safe = []
    for block_move in threats:
        if not board.is_empty(block_move[0], block_move[1]):
            continue
        board.make_move(block_move[0], block_move[1], player)
        vcf = search_vcf(board, depth=12, player=opponent,
                         is_attacking=True, budget=[1500])
        if vcf is None:
            level, desc = evaluate_threats_after_move(board, opponent)
            penalty = {4: 1000000, 3: 100000, 2: 20000, 1: 5000}.get(level, 0)
            score = evaluate_position(board, player, to_move=opponent)
            safe.append((score, block_move))
            log(f"    блок {block_move} безопасен, оценка {score} (угроза {level}: {desc})")
        else:
            log(f"    блок {block_move} ПРОИГРЫВАЕТ: VCF {vcf}")
        board.undo_move()

    if not safe:
        log("  все блокировки живых троек проигрывают VCF — блок не возвращаем")
        return None
    safe.sort(key=lambda x: (-x[0], x[1]))
    return safe[0][1]


def find_own_fork(board: Board, player: int) -> Optional[Tuple[int, int]]:
    """Этап 6: вилка проверяется анализатором, с учётом темпа противника."""
    opponent = PLAYER_O if player == PLAYER_X else PLAYER_X
    if completion_points(board, opponent):
        return None                      # противник собирает пятёрку первым
    for (x, y) in generate_threat_moves(board, player):
        board.make_move(x, y, player)
        ok = (is_double_threat_new(board, player)
              and not completion_points(board, opponent))
        board.undo_move()
        if ok:
            log(f"  вилка найдена в ({x},{y})")
            return (x, y)
    return None


def find_potential_fork(board: Board, player: int) -> Optional[Tuple[int, int]]:
    opponent = PLAYER_O if player == PLAYER_X else PLAYER_X

    for x, y in board.get_candidate_moves(radius=2):
        if not board.is_empty(x, y):
            continue

        board.make_move(x, y, opponent)
        open_threes = count_all_open_threes(board, opponent, debug=True)
        board.undo_move()

        if open_threes >= 2:
            log(f"  Потенциальная вилка противника в ({x},{y}): {open_threes} открытых троек")
            return (x, y)

    return None


def block_potential_fork(board: Board, player: int) -> Optional[Tuple[int, int]]:
    fork_threat = find_potential_fork(board, player)
    return fork_threat


def find_blocking_move(board: Board, threat_move: Tuple[int, int], player: int) -> Tuple[int, int]:
    log(f"  find_blocking_move: блокируем угрозу в {threat_move}")
    if not board.is_empty(threat_move[0], threat_move[1]):
        log(f"    ВНИМАНИЕ: клетка занята! Это баг в поиске VCF/VCT.")
    return threat_move


def _connectivity(board: Board, player: int) -> int:
    """Число смежных пар своих камней — дешёвый позиционный член."""
    total = 0
    for (x, y), p in board.grid.items():
        if p != player:
            continue
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                if board.get_cell(x + dx, y + dy) == player:
                    total += 1
    return total // 2


def evaluate_position(board: Board, player: int, to_move: Optional[int] = None) -> int:
    """
    Этап 5. Оценка по уникальным угрозам анализатора, без двойного учёта.
    to_move — чей ход в оцениваемой позиции (влияет на темп).
    """
    if to_move is None:
        to_move = player
    opponent = PLAYER_O if player == PLAYER_X else PLAYER_X
    WIN = 10_000_000

    my_th = analyze_threats(board, player)
    op_th = analyze_threats(board, opponent)

    if any(t.kind == FIVE for t in my_th):
        return WIN
    if any(t.kind == FIVE for t in op_th):
        return -WIN

    my_pts = {p for t in my_th if t.kind in (FOUR, LIVE_FOUR) for p in t.points}
    op_pts = {p for t in op_th if t.kind in (FOUR, LIVE_FOUR) for p in t.points}

    # ходящий собирает пятёрку сейчас
    if to_move == player and my_pts:
        return WIN - 1
    if to_move == opponent and op_pts:
        return -(WIN - 1)
    # две точки достройки — не блокируется одним ходом
    if len(my_pts) >= 2:
        return WIN - 1
    if len(op_pts) >= 2:
        return -(WIN - 1)

    BASE = {LIVE_FOUR: 400_000, FOUR: 50_000, LIVE_THREE: 20_000, SLEEPING_THREE: 2_000}
    TEMPO = {LIVE_FOUR: 400_000, FOUR: 500_000, LIVE_THREE: 200_000, SLEEPING_THREE: 1_000}

    score = 0
    for t in my_th:
        score += BASE.get(t.kind, 0)
        if to_move == player:
            score += TEMPO.get(t.kind, 0)
    for t in op_th:
        score -= BASE.get(t.kind, 0)
        if to_move == opponent:
            score -= TEMPO.get(t.kind, 0)

    score += 25 * (_connectivity(board, player) - _connectivity(board, opponent))
    return score


def _order_moves(board: Board, side: int, candidates) -> List[Tuple[Tuple[int, int], int]]:
    """
    Этап 5. Быстрая сортировка для alpha-beta: 3 прохода анализатора на узел
    вместо полной оценки каждого кандидата.
    """
    opp = PLAYER_O if side == PLAYER_X else PLAYER_X
    my_th = analyze_threats(board, side)
    op_th = analyze_threats(board, opp)
    my_pts = {p for t in my_th if t.kind in (FOUR, LIVE_FOUR) for p in t.points}
    op_pts = {p for t in op_th if t.kind in (FOUR, LIVE_FOUR) for p in t.points}
    my_live3 = {p for t in my_th if t.kind == LIVE_THREE for p in t.points}
    op_live3 = {p for t in op_th if t.kind == LIVE_THREE for p in t.points}
    my_four_moves = four_move_candidates(board, side)

    scored = []
    for (x, y) in candidates:
        s = 0
        if (x, y) in my_pts:
            s += 1_000_000
        if (x, y) in op_pts:
            s += 900_000
        if (x, y) in my_four_moves:
            s += 50_000
        if (x, y) in my_live3:
            s += 20_000
        if (x, y) in op_live3:
            s += 15_000
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                v = board.get_cell(x + dx, y + dy)
                if v == side:
                    s += 12
                elif v == opp:
                    s += 6
        scored.append(((x, y), s))
    scored.sort(key=lambda t: (-t[1], t[0]))
    return scored


def minimax(board: Board, depth: int, alpha: int, beta: int,
            is_maximizing: bool, player: int, budget=None, tt=None) -> int:
    opponent = PLAYER_O if player == PLAYER_X else PLAYER_X
    current = player if is_maximizing else opponent

    if budget is not None:
        if budget[0] <= 0:
            return evaluate_position(board, player, to_move=current)
        budget[0] -= 1

    if check_five(board, PLAYER_X):
        return 10_000_000 if player == PLAYER_X else -10_000_000
    if check_five(board, PLAYER_O):
        return 10_000_000 if player == PLAYER_O else -10_000_000
    if completion_points(board, current):
        return 9_999_999 if current == player else -9_999_999

    if depth <= 0:
        return evaluate_position(board, player, to_move=current)

    orig_alpha, orig_beta = alpha, beta
    key = None
    if tt is not None:
        key = (board.zhash, depth, is_maximizing, player)
        entry = tt.get(key)
        if entry is not None:
            val, flag = entry
            if flag == TT_EXACT:
                return val
            if flag == TT_LOWER:
                alpha = max(alpha, val)
            elif flag == TT_UPPER:
                beta = min(beta, val)
            if alpha >= beta:
                return val

    candidates = board.get_candidate_moves(radius=2)
    ordered = _order_moves(board, current, candidates)
    cap = 10

    if is_maximizing:
        best = -float('inf')
        for (x, y), _ in ordered[:cap]:
            board.make_move(x, y, current)
            v = minimax(board, depth - 1, alpha, beta, False, player, budget, tt)
            board.undo_move()
            best = max(best, v)
            alpha = max(alpha, v)
            if beta <= alpha:
                break
    else:
        best = float('inf')
        for (x, y), _ in ordered[:cap]:
            board.make_move(x, y, current)
            v = minimax(board, depth - 1, alpha, beta, True, player, budget, tt)
            board.undo_move()
            best = min(best, v)
            beta = min(beta, v)
            if beta <= alpha:
                break

    if tt is not None and key is not None and len(tt) < TT_MAX_ENTRIES:
        if best <= orig_alpha:
            flag = TT_UPPER
        elif best >= orig_beta:
            flag = TT_LOWER
        else:
            flag = TT_EXACT
        tt[key] = (best, flag)

    return best

def get_best_move(board: Board, player: int) -> Tuple[int, int]:
    DEBUG_LOG.clear()
    log(f"=== Ход ИИ ({player_name(player)}) ===")
    log("Доска:")
    for x, y, p in board.move_history:
        log(f"  {player_name(p)} в ({x},{y})")
    log(f"Ходов на доске: {len(board.move_history)}")

    opponent = PLAYER_O if player == PLAYER_X else PLAYER_X
    my_stones = board.count_stones(player)
    opp_stones = board.count_stones(opponent)
    log(f"Камней: {player_name(player)}={my_stones}, {player_name(opponent)}={opp_stones}")

    vcf_depth = 20 if my_stones >= 4 and opp_stones >= 3 else 8
    vcf_budget = [2000]

    log("\n[ШАГ 1] Мгновенный выигрыш ИИ")
    immediate_win = check_immediate_win(board, player)
    if immediate_win:
        log(f"  -> НАЙДЕН: {immediate_win}")
        return immediate_win
    log("  -> не найден")

    log(f"\n[ШАГ 2] Мгновенная защита от пятёрки {player_name(opponent)}")
    opp_win = check_immediate_win(board, opponent)
    if opp_win:
        log(f"  -> блокируем: {opp_win}")
        return opp_win
    log("  -> не найдена")

    log(f"\n[ШАГ 3] Свой VCF (глубина {vcf_depth})")
    if my_stones >= 3:
        vcf_move = search_vcf(board, depth=vcf_depth, player=player,
                              is_attacking=True, budget=vcf_budget)
        if vcf_move:
            log(f"  -> НАЙДЕН: {vcf_move}")
            return vcf_move
        log("  -> не найден")
    else:
        log("  (пропущено: своих камней < 3)")

    log(f"\n[ШАГ 4] Защита от VCF противника (с перепроверкой)")
    if opp_stones >= 3:
        opp_vcf = search_vcf(board, depth=vcf_depth, player=opponent,
                             is_attacking=True, budget=[2000])
        if opp_vcf:
            log(f"  VCF противника начинается с {opp_vcf}")
            defense = find_vcf_defense(board, player, depth=vcf_depth,
                                       known_threat=opp_vcf)
            if defense:
                log(f"  -> защита найдена: {defense}")
                return defense
            log("  ни одна защита не опровергает VCF — позиция тактически проиграна")
            log("  проигрышный блок НЕ возвращаем, переходим к позиционной игре")
        else:
            log("  VCF противника нет")
    else:
        log("  (пропущено: камней противника < 3)")

    log("\n[ШАГ 4.4] Своя вилка из живых троек")
    fork = find_own_fork(board, player)
    if fork:
        log(f"  -> НАЙДЕНА: {fork}")
        return fork
    log("  -> не найдена")

    log("\n[ШАГ 4.5] Свой VCT (ограниченный)")
    if my_stones >= 3:
        vct_move = search_vct(board, depth=4, player=player,
                              is_attacking=True, budget=[800], tt={})
        if vct_move:
            log(f"  -> НАЙДЕН: {vct_move}")
            return vct_move
        log("  -> не найден")
    else:
        log("  (пропущено: своих камней < 3)")

    log(f"\n[ШАГ 5] Безопасная блокировка живой тройки {player_name(opponent)}")
    block = block_open_three_threats(board, player)
    if block:
        log(f"  -> ВЫБРАНА: {block}")
        return block
    log("  -> не выбрана")

    log(f"\n[ШАГ 6.5] Блокировка потенциальной вилки {player_name(opponent)}")
    fork_block = block_potential_fork(board, player)
    if fork_block:
        log(f"  -> ВЫБРАНА: {fork_block}")
        return fork_block
    log("  -> не найдена")

    log("\n[ШАГ 7-8] VCT временно отключён (этап 6)")

    log("\n[ШАГ 9] Позиционный поиск (iterative deepening)")
    candidates = board.get_candidate_moves(radius=2)
    mm_budget = [8000]
    tt = {}
    deadline = time.perf_counter() + POSITIONAL_TIME_LIMIT

    scored = []
    for x, y in candidates:
        board.make_move(x, y, player)
        score = evaluate_position(board, player, to_move=opponent)
        board.undo_move()
        scored.append(((x, y), score))
    scored.sort(key=lambda t: (-t[1], t[0]))
    log("  Топ-10 кандидатов:")
    for (x, y), s in scored[:10]:
        log(f"    ({x},{y}) = {s}")

    max_candidates = 7 if len(board.move_history) < 6 else 15
    root_moves = [m for m, _ in scored[:max_candidates]]
    best_move = root_moves[0]

    for depth in range(1, 5):
        best_score = -float('inf')
        local_best = None
        for (x, y) in root_moves:
            if time.perf_counter() > deadline or mm_budget[0] <= 0:
                break
            board.make_move(x, y, player)
            score = minimax(board, depth - 1, -float('inf'), float('inf'),
                            False, player, mm_budget, tt)
            board.undo_move()
            log(f"  d={depth} ({x},{y}) = {score}")
            if score > best_score:
                best_score = score
                local_best = (x, y)
        if local_best is not None:
            best_move = local_best
            root_moves.remove(local_best)
            root_moves.insert(0, local_best)
            log(f"  глубина {depth}: лучший {local_best}, оценка {best_score}")
        if time.perf_counter() > deadline or mm_budget[0] <= 0:
            log("  бюджет исчерпан — углубление остановлено")
            break

    log(f"  -> ВЫБРАН: {best_move}")
    log(f"\n=== Финальный ход: {best_move} ===")
    return best_move

class GomokuGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Гомоку - 5 в ряд (30x30) [DEBUG: клавиша 1]")
        self.root.focus_set()

        self.board = Board()
        self.current_player = PLAYER_X
        self.cell_size = 20
        self.board_size = 30
        self.offset = 30
        self.is_computer_thinking = False
        self.hover_cell: Optional[Tuple[int, int]] = None
        self.first_player = tk.IntVar(value=PLAYER_X)

        ctrl_frame = tk.Frame(self.root)
        ctrl_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=3)

        first_frame = tk.Frame(ctrl_frame)
        first_frame.pack(side=tk.LEFT, padx=10)
        tk.Label(first_frame, text="Первым ходит:", font=('Arial', 10)).pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(first_frame, text="Игрок (X)", variable=self.first_player,
                       value=PLAYER_X, command=self.on_first_player_change, font=('Arial', 10)).pack(side=tk.LEFT)
        tk.Radiobutton(first_frame, text="Компьютер (O)", variable=self.first_player,
                       value=PLAYER_O, command=self.on_first_player_change, font=('Arial', 10)).pack(side=tk.LEFT)

        btn_frame = tk.Frame(ctrl_frame)
        btn_frame.pack(side=tk.LEFT, padx=20)
        tk.Button(btn_frame, text='Начать новую игру', command=self.restart_game,
                  font=('Arial', 10)).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text='Скопировать отладку (1)',
                  command=self.copy_debug_to_clipboard, font=('Arial', 10)).pack(side=tk.LEFT, padx=5)

        self.status_label = tk.Label(self.root, text='Ваш ход (X) — [1] скопировать отладку',
                                     font=('Arial', 12))
        self.status_label.pack(side=tk.TOP, pady=3)

        canvas_size = self.board_size * self.cell_size + 2 * self.offset
        self.canvas = tk.Canvas(self.root, width=canvas_size, height=canvas_size, bg='#F5DEB3')
        self.canvas.pack(side=tk.TOP, padx=10, pady=5)
        self.canvas.bind('<Button-1>', self.on_click)
        self.canvas.bind('<Motion>', self.on_motion)
        self.canvas.bind('<Leave>', self.on_leave)

        self.root.bind('<Key-1>', self.on_debug_key)

        self.draw_board()

    def on_first_player_change(self):
        if self.board.move_history:
            self.restart_game()
        else:
            self.update_status()
            if self.first_player.get() == PLAYER_O:
                self.start_computer_first_move()

    def start_computer_first_move(self):
        if self.first_player.get() == PLAYER_O and not self.board.move_history:
            self.current_player = PLAYER_O
            self.is_computer_thinking = True
            self.status_label.config(text='Компьютер думает...')
            threading.Thread(target=self.computer_move, daemon=True).start()

    def update_status(self):
        if self.current_player == PLAYER_X:
            self.status_label.config(text='Ваш ход (X) — [1] скопировать отладку')
        else:
            self.status_label.config(text='Компьютер думает...')

    def on_debug_key(self, event):
        self.copy_debug_to_clipboard()

    def copy_debug_to_clipboard(self):
        if not DEBUG_LOG:
            self.status_label.config(text='Лога нет — ИИ ещё не ходил')
            return
        text = '\n'.join(DEBUG_LOG)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_label.config(text=f'Отладка скопирована ({len(DEBUG_LOG)} строк)')

    def board_coord_to_pixel(self, board_x: int, board_y: int) -> Tuple[int, int]:
        grid_x = board_x + self.board_size // 2
        grid_y = board_y + self.board_size // 2
        pixel_x = self.offset + grid_x * self.cell_size + self.cell_size // 2
        pixel_y = self.offset + grid_y * self.cell_size + self.cell_size // 2
        return (pixel_x, pixel_y)

    def pixel_to_board(self, pixel_x: int, pixel_y: int) -> Optional[Tuple[int, int]]:
        rel_x = pixel_x - self.offset
        rel_y = pixel_y - self.offset
        field_size = self.board_size * self.cell_size
        if not (0 <= rel_x < field_size and 0 <= rel_y < field_size):
            return None
        board_x = rel_x // self.cell_size - self.board_size // 2
        board_y = rel_y // self.cell_size - self.board_size // 2
        return (board_x, board_y)

    def draw_board(self):
        self.canvas.delete('all')
        field_size = self.board_size * self.cell_size

        for i in range(self.board_size + 1):
            x = self.offset + i * self.cell_size
            self.canvas.create_line(x, self.offset, x, self.offset + field_size, fill='#8B7355')
            self.canvas.create_line(self.offset, x, self.offset + field_size, x, fill='#8B7355')

        half = self.board_size // 2
        for i in range(self.board_size + 1):
            coord_x = i - half
            coord_y = i - half

            if i % 5 == 0 or i == self.board_size:
                px = self.offset + i * self.cell_size
                self.canvas.create_text(px, self.offset - 15, text=str(coord_x),
                                        fill='#333', font=('Arial', 9))
                py = self.offset + i * self.cell_size
                self.canvas.create_text(self.offset - 20, py, text=str(coord_y),
                                        fill='#333', font=('Arial', 9))

        if (self.hover_cell is not None and self.current_player == PLAYER_X
                and not self.is_computer_thinking):
            hx, hy = self.hover_cell
            if self.board.is_empty(hx, hy):
                px, py = self.board_coord_to_pixel(hx, hy)
                m = 2
                self.canvas.create_rectangle(
                    px - self.cell_size // 2 + m, py - self.cell_size // 2 + m,
                    px + self.cell_size // 2 - m, py + self.cell_size // 2 - m,
                    fill='#FFEB99', outline='#FFA500', width=2)

        for (x, y), player in self.board.grid.items():
            px, py = self.board_coord_to_pixel(x, y)
            if (self.offset <= px <= self.offset + field_size and
                    self.offset <= py <= self.offset + field_size):
                if player == PLAYER_X:
                    m = self.cell_size // 4
                    self.canvas.create_line(px - m, py - m, px + m, py + m, fill='red', width=2)
                    self.canvas.create_line(px + m, py - m, px - m, py + m, fill='red', width=2)
                else:
                    m = self.cell_size // 4
                    self.canvas.create_oval(px - m, py - m, px + m, py + m, outline='blue', width=2)

    def on_motion(self, event):
        if self.is_computer_thinking:
            return
        new_cell = self.pixel_to_board(event.x, event.y)
        if new_cell is not None:
            hx, hy = new_cell
            fh = self.board_size // 2
            if not (-fh <= hx <= fh and -fh <= hy <= fh):
                new_cell = None
        if new_cell != self.hover_cell:
            self.hover_cell = new_cell
            self.draw_board()

    def on_leave(self, event):
        if self.is_computer_thinking:
            return
        if self.hover_cell is not None:
            self.hover_cell = None
            self.draw_board()

    def on_click(self, event):
        if self.is_computer_thinking:
            return
        if self.current_player != PLAYER_X:
            return
        cell = self.pixel_to_board(event.x, event.y)
        if cell is None:
            return
        bx, by = cell
        if self.board.make_move(bx, by, PLAYER_X):
            self.draw_board()
            if check_five(self.board, PLAYER_X):
                messagebox.showinfo('Победа!', 'Вы выиграли!')
                return
            self.current_player = PLAYER_O
            self.hover_cell = None
            self.status_label.config(text='Компьютер думает...')
            self.is_computer_thinking = True
            threading.Thread(target=self.computer_move, daemon=True).start()

    def computer_move(self):
        move = get_best_move(self.board, PLAYER_O)
        self.board.make_move(move[0], move[1], PLAYER_O)
        self.root.after(0, self._after_computer_move)

    def _after_computer_move(self):
        self.is_computer_thinking = False
        self.draw_board()
        if check_five(self.board, PLAYER_O):
            messagebox.showinfo('Поражение', 'Компьютер выиграл!')
            return
        self.current_player = PLAYER_X
        self.status_label.config(text='Ваш ход (X) — [1] скопировать отладку')

    def restart_game(self):
        if self.is_computer_thinking:
            return
        self.board = Board()
        self.current_player = PLAYER_X
        self.hover_cell = None
        DEBUG_LOG.clear()

        if self.first_player.get() == PLAYER_O:
            self.start_computer_first_move()
        else:
            self.status_label.config(text='Ваш ход (X) — [1] скопировать отладку')

        self.draw_board()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = GomokuGUI()
    app.run()