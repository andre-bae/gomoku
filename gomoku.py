# GUI-библиотека нужна только старому отладочному интерфейсу.
# Движок должен импортироваться и без неё: автотесты, самоигра, Android.
try:
    import tkinter as tk
    from tkinter import messagebox, filedialog
except ImportError:
    tk = None
    messagebox = None
    filedialog = None
from typing import Optional, List, Tuple, Dict
import threading
import json
import time

from gomoku_analysis import (
    analyze_threats, is_double_threat_new, is_winning_threat_set,
    completion_points, four_move_candidates, threat_move_candidates, describe,
    FIVE, LIVE_FOUR, FOUR, LIVE_THREE, SLEEPING_THREE, window_potential,
)


MASK64 = (1 << 64) - 1
POSITIONAL_TIME_LIMIT = 2.0   # секунд на позиционную фазу хода
TT_MAX_ENTRIES = 200_000

TT_EXACT, TT_LOWER, TT_UPPER = 0, 1, 2


# --- Временные переключатели дорогих эвристик (сессия 1) ---
ENABLE_POTENTIAL_FORK_SCAN = False        # шаг 6.5: перебор всех клеток
ENABLE_THREAT_SCAN_AFTER_BLOCK = False    # скан угроз после каждого блока
MOVE_TIME_LIMIT = 3.0                     # жёсткий лимит секунд на ход ИИ
_MOVE_DEADLINE = 0.0                      # служебное: когда время истекает
_TRUNCATED = [0]                          # счётчик обрывов поиска: >0 = бюджет исчерпан


class SearchTimeout(Exception):
    """Служебное исключение: время на ход закончилось."""


def _time_up() -> bool:
    return _MOVE_DEADLINE > 0.0 and time.perf_counter() > _MOVE_DEADLINE


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
VCF_LOG_MAX_INDENT = 2


# Отладочный лог
DEBUG_LOG: List[str] = []
DEBUG_ENABLED = True


def log(msg: str):
    if DEBUG_ENABLED:
        DEBUG_LOG.append(msg)


def player_name(p: int) -> str:
    return "X" if p == PLAYER_X else "O"


def assign_roles(ai_starts: bool) -> Tuple[int, int]:
    """Первым всегда играет X. Возвращает (human_player, ai_player)."""
    return (PLAYER_O, PLAYER_X) if ai_starts else (PLAYER_X, PLAYER_O)


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

    def copy(self) -> "Board":
        """Снапшот для фонового поиска — не разделяется с GUI."""
        b = Board()
        b.grid = dict(self.grid)
        b.move_history = list(self.move_history)
        b.zhash = self.zhash
        return b


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
    if budget is not None:
        if budget[0] <= 0:
            _TRUNCATED[0] += 1
            return None
        budget[0] -= 1

    if path is None:
        path = []

    if _time_up():
        raise SearchTimeout

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
    if indent <= VCF_LOG_MAX_INDENT:
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
            _TRUNCATED[0] += 1
            return None
        budget[0] -= 1

    if _time_up():
        raise SearchTimeout

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
    if indent <= VCF_LOG_MAX_INDENT:
        log(f"{ind}VCT d={depth} {player_name(attacker)}: {len(moves)} ходов-угроз")

    result = None
    for move in moves:
        if budget is not None and budget[0] <= 0:
            _TRUNCATED[0] += 1
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
            # C4: вилка не победа, если защитник выигрывает четвёрками раньше
            ref = search_vcf(board, depth=8, player=defender,
                             is_attacking=True, budget=[400])
            if ref is not None:
                log(f"{ind}VCT: вилка после {move} отклонена — у защитника VCF {ref}")
                board.undo_move()
                continue
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
                _TRUNCATED[0] += 1
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
        # C5: «победы нет» при оборванном поиске — не доказательство, в кэш не пишем
        if result is not None or _TRUNCATED[0] == 0:
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

        still_vcf = search_vcf(board, depth=depth, player=opponent,
                               is_attacking=True, budget=[2000])
        if still_vcf is not None:
            log(f"    защита {move} не помогает: VCF {still_vcf}")
            board.undo_move()
            continue

        # VCF отбит — проверяем, не выигрывает ли противник через тройки
        still_vct = search_vct(board, depth=4, player=opponent,
                               is_attacking=True, budget=[800], tt={})

        # тай-брейк с просмотром лучшего ответа противника, а не статикой
        score = minimax(board, depth=2, alpha=-float('inf'), beta=float('inf'),
                        is_maximizing=False, player=player, budget=[3000], tt={})

        verified.append((0 if still_vct is None else 1, score, move))
        log(f"    защита {move}: VCF нет, VCT "
            f"{'нет' if still_vct is None else still_vct}, просмотр {score}")
        board.undo_move()

    if not verified:
        return None
    # сначала те, что гасят и VCF, и VCT; внутри группы — по просмотру
    verified.sort(key=lambda t: (t[0], -t[1], t[2]))
    return verified[0][2]


def evaluate_threats_after_move(board: Board, player: int) -> Tuple[int, str]:
    """Быстрая версия: несколько проходов анализатора вместо перебора всех клеток."""
    if not ENABLE_THREAT_SCAN_AFTER_BLOCK:
        return 0, "скан угроз отключён (быстрый режим)"
    if completion_points(board, player):
        return 4, "есть ход, собирающий пятёрку"
    th = analyze_threats(board, player)
    if any(t.kind == LIVE_FOUR for t in th) or is_double_threat_new(board, player):
        return 3, "живая четвёрка или вилка"
    if four_move_candidates(board, player):
        return 2, "есть ход, создающий четвёрку"
    if any(t.kind == LIVE_THREE for t in th) or threat_move_candidates(board, player):
        return 1, "есть ход, создающий тройку"
    return 0, "нет угроз"


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
    """Этап 6 + C4: вилка проверяется анализатором, с учётом темпа противника.
    Вилка не годится, если противник успевает выиграть серией четвёрок (VCF)."""
    opponent = PLAYER_O if player == PLAYER_X else PLAYER_X
    if completion_points(board, opponent):
        return None                      # противник собирает пятёрку первым
    for (x, y) in generate_threat_moves(board, player):
        board.make_move(x, y, player)
        ok = (is_double_threat_new(board, player)
              and not completion_points(board, opponent))
        if ok:
            # C4: у противника может быть более быстрый форсированный выигрыш
            ref = search_vcf(board, depth=8, player=opponent,
                             is_attacking=True, budget=[400])
            if ref is not None:
                log(f"  вилка ({x},{y}) отклонена: у противника VCF {ref}")
                ok = False
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
        n = count_all_open_threes(board, opponent, debug=False)
        board.undo_move()
        if n >= 2:
            log(f"  потенциальная вилка противника в ({x},{y}): {n} живых троек")
            return (x, y)
    return None


def find_vct_defense(board: Board, player: int, depth: int = 4,
                     known_threat: Optional[Tuple[int, int]] = None,
                     max_candidates: int = 10) -> Optional[Tuple[int, int]]:
    """
    Этап 6. Ход, после которого у противника НЕ остаётся VCT.
    Кандидаты prioritized, каждый проверяется повторным поиском.
    Бюджет консервативный: при исчерпании считаем, что выигрыш не найден.
    """
    opponent = PLAYER_O if player == PLAYER_X else PLAYER_X

    threat = known_threat
    if threat is None:
        threat = search_vct(board, depth=depth, player=opponent,
                            is_attacking=True, budget=[1500], tt={})
    if threat is None:
        log("    VCT противника нет")
        return None
    log(f"    VCT противника начинается с {threat}")

    ordered = [threat]
    ordered += sorted(completion_points(board, opponent))
    live_pts = set()
    for t in analyze_threats(board, opponent):
        if t.kind == LIVE_THREE:
            live_pts.update(t.points)
    ordered += sorted(live_pts)
    ordered += generate_four_moves(board, player)          # наши контр-четвёрки
    ordered += sorted(threat_move_candidates(board, opponent))

    seen = set()
    candidates = []
    for m in ordered:
        if m in seen:
            continue
        seen.add(m)
        if board.is_empty(m[0], m[1]):
            candidates.append(m)
        if len(candidates) >= max_candidates:
            break

    verified = []
    for move in candidates:
        board.make_move(move[0], move[1], player)
        still = search_vct(board, depth=depth, player=opponent,
                           is_attacking=True, budget=[1500], tt={})
        if still is None:
            score = evaluate_position(board, player, to_move=opponent)
            verified.append((score, move))
            log(f"    защита {move} опровергает VCT (оценка {score})")
        else:
            log(f"    защита {move} не помогает: VCT {still}")
        board.undo_move()

    if not verified:
        log("    ни одна защита не опровергает VCT")
        return None
    verified.sort(key=lambda t: (-t[0], t[1]))
    return verified[0][1]


def block_potential_fork(board: Board, player: int) -> Optional[Tuple[int, int]]:
    if not ENABLE_POTENTIAL_FORK_SCAN:
        log("  (шаг 6.5 отключён: слишком дорогой перебор клеток)")
        return None
    return find_potential_fork(board, player)


def choose_resistance_move(board: Board, player: int) -> Tuple[int, int]:
    """
    Позиция тактически проиграна. Выбираем ход с максимумом контригры:
    свои четвёрки (форсируют ответ) > свои живые тройки > позиционная оценка.
    """
    opponent = PLAYER_O if player == PLAYER_X else PLAYER_X
    candidates = set(generate_four_moves(board, player))
    for m in generate_threat_moves(board, player):
        board.make_move(m[0], m[1], player)
        if any(t.kind == LIVE_THREE for t in analyze_threats(board, player)):
            candidates.add(m)
        board.undo_move()
    if not candidates:
        candidates = set(board.get_candidate_moves(radius=2))

    best, best_score = None, -float('inf')
    for m in sorted(candidates):
        board.make_move(m[0], m[1], player)
        my = analyze_threats(board, player)
        bonus = (1000 * sum(1 for t in my if t.kind in (FOUR, LIVE_FOUR))
                 + 100 * sum(1 for t in my if t.kind == LIVE_THREE))
        score = evaluate_position(board, player, to_move=opponent) + bonus
        board.undo_move()
        if score > best_score:
            best_score, best = score, m
    log(f"  сопротивление: лучший {best}, оценка {best_score}")
    return best if best else board.get_candidate_moves(radius=2)[0]


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


def _unique_threats(threats):
    """Одна угроза — один объект: тип + направление + точки достройки.
    Пример дубля: OXXXX.X даёт два FOUR с одной и той же точкой (4,0)."""
    seen = set()
    out = []
    for t in threats:
        key = (t.kind, t.direction, t.points)
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def evaluate_position(board: Board, player: int, to_move: Optional[int] = None) -> int:
    """
    Этап 5. Оценка по уникальным угрозам анализатора, без двойного учёта.
    to_move — чей ход в оцениваемой позиции (влияет на темп).
    """
    if to_move is None:
        to_move = player
    opponent = PLAYER_O if player == PLAYER_X else PLAYER_X
    WIN = 10_000_000

    my_th = _unique_threats(analyze_threats(board, player))
    op_th = _unique_threats(analyze_threats(board, opponent))

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
    # Вес потенциала зависит от темпа, а не от роли "я/противник" —
    # правило одинаково для обеих сторон, поэтому антисимметрия сохраняется.
    # Сторона НЕ в ходу опаснее: её потенциал ещё не реализован, значит
    # мешать её построению важнее, чем достраивать своё.
    pot_me = window_potential(board, player)
    pot_op = window_potential(board, opponent)
    w_move, w_wait = 1.0, 1.25
    w_me = w_move if to_move == player else w_wait
    w_op = w_move if to_move == opponent else w_wait
    score += int(pot_me * w_me) - int(pot_op * w_op)
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

    if _time_up():
        raise SearchTimeout

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


def _get_best_move_impl(board: Board, player: int) -> Tuple[int, int]:
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

    tactically_lost = False

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
            trunc0 = _TRUNCATED[0]
            defense = find_vcf_defense(board, player, depth=vcf_depth,
                                       known_threat=opp_vcf)
            if defense:
                log(f"  -> защита найдена: {defense}")
                return defense
            if _TRUNCATED[0] > trunc0:
                log("  защита не доказана: поиск оборван — НЕ считаем позицию проигранной")
            else:
                tactically_lost = True
                log("  ни одна защита не опровергает VCF — позиция тактически проиграна")
        else:
            log("  VCF противника нет")
    else:
        log("  (пропущено: камней противника < 3)")

    if not tactically_lost:
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

    if not tactically_lost and opp_stones >= 3:
        log("\n[ШАГ 4.6] Защита от VCT противника")
        opp_vct = search_vct(board, depth=4, player=opponent,
                             is_attacking=True, budget=[1200], tt={})
        if opp_vct:
            log(f"  VCT противника начинается с {opp_vct}")
            trunc0 = _TRUNCATED[0]
            d = find_vct_defense(board, player, depth=4, known_threat=opp_vct)
            if d:
                log(f"  -> защита найдена: {d}")
                return d
            if _TRUNCATED[0] > trunc0:
                log("  защита не доказана: поиск оборван — НЕ считаем позицию проигранной")
            else:
                tactically_lost = True
                log("  VCT не опровергается — позиция тактически проиграна")
        else:
            log("  VCT противника нет")

    if tactically_lost:
        log("\n[РЕЖИМ СОПРОТИВЛЕНИЯ] эвристические блокировки отключены")
        move = choose_resistance_move(board, player)
        log(f"\n=== Финальный ход: {move} ===")
        return move

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

    log("\n[ШАГ 7-8] (VCT уже проверен на шаге 4.5)")

    log("\n[ШАГ 9] Позиционный поиск (iterative deepening)")
    candidates = board.get_candidate_moves(radius=2)
    mm_budget = [8000]
    tt = {}
    deadline = time.perf_counter() + POSITIONAL_TIME_LIMIT
    ordered = _order_moves(board, player, candidates)
    shortlist = [m for m, _ in ordered[:24]]
    scored = []
    for x, y in shortlist:
        if _time_up():
            break
        board.make_move(x, y, player)
        score = evaluate_position(board, player, to_move=opponent)
        board.undo_move()
        scored.append(((x, y), score))
    scored.sort(key=lambda t: (-t[1], t[0]))
    if not scored:
        move = ordered[0][0]
        log(f"  время вышло до оценки — берём {move}")
        return move

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


def get_best_move(board: Board, player: int) -> Tuple[int, int]:
    """Обёртка: жёсткий лимит времени на ход и гарантия восстановления доски."""
    global _MOVE_DEADLINE
    _TRUNCATED[0] = 0
    base_len = len(board.move_history)
    t0 = time.perf_counter()
    _MOVE_DEADLINE = t0 + MOVE_TIME_LIMIT
    try:
        return _get_best_move_impl(board, player)
    except SearchTimeout:
        while len(board.move_history) > base_len:
            board.undo_move()
        log("  !! время хода исчерпано — быстрый выбор по сортировке")
        cands = board.get_candidate_moves(radius=1) or [(0, 0)]
        return _order_moves(board, player, cands)[0][0]
    finally:
        _MOVE_DEADLINE = 0.0
        while len(board.move_history) > base_len:
            board.undo_move()
        log(f"Время хода ИИ: {time.perf_counter() - t0:.2f} с")


class GomokuGUI:
    CANVAS = 660
    MIN_CELL, MAX_CELL = 8, 48
    MAX_MOVES = 400

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Гомоку — бесконечное поле")
        self.root.focus_set()

        self.board = Board()
        self.ai_starts = tk.BooleanVar(value=False)
        self.human_player, self.ai_player = assign_roles(False)
        self.current = PLAYER_X
        self.game_over = False
        self.thinking = False
        self.gen = 0
        self.cell = 20
        self.cam_x = 0.0
        self.cam_y = 0.0
        self.last_move = None
        self.win_line = []
        self.hover = None
        self.game_log = []
        self.move_records = []          # анализ по КАЖДОМУ ходу
        self.last_analysis = ""
        self._pan_from = None

        top = tk.Frame(self.root)
        top.pack(side=tk.TOP, fill=tk.X, padx=8, pady=3)

        fp = tk.Frame(top)
        fp.pack(side=tk.LEFT)
        tk.Label(fp, text="Первым ходит:", font=('Arial', 10)).pack(side=tk.LEFT)
        tk.Radiobutton(fp, text="Игрок", variable=self.ai_starts,
                       value=False, command=self.on_first_change,
                       font=('Arial', 10)).pack(side=tk.LEFT)
        tk.Radiobutton(fp, text="ИИ", variable=self.ai_starts,
                       value=True, command=self.on_first_change,
                       font=('Arial', 10)).pack(side=tk.LEFT)

        b1 = tk.Frame(top)
        b1.pack(side=tk.LEFT, padx=12)
        tk.Button(b1, text="Новая игра", command=self.new_game,
                  font=('Arial', 10)).pack(side=tk.LEFT, padx=3)
        tk.Button(b1, text="Центр (C)", command=self.center_last,
                  font=('Arial', 10)).pack(side=tk.LEFT, padx=3)

        b2 = tk.Frame(self.root)
        b2.pack(side=tk.TOP, fill=tk.X, padx=8)
        tk.Button(b2, text="Анализ хода (1)", command=self.copy_analysis,
                  font=('Arial', 9)).pack(side=tk.LEFT, padx=2)
        tk.Button(b2, text="Партия (2)", command=self.copy_game,
                  font=('Arial', 9)).pack(side=tk.LEFT, padx=2)
        tk.Button(b2, text="Все анализы (3)", command=self.copy_all_analyses,
                  font=('Arial', 9)).pack(side=tk.LEFT, padx=2)
        tk.Button(b2, text="Просмотр (A)", command=self.show_analyses,
                  font=('Arial', 9)).pack(side=tk.LEFT, padx=2)
        tk.Button(b2, text="Сохранить (S)", command=self.save_game,
                  font=('Arial', 9)).pack(side=tk.LEFT, padx=2)

        self.status = tk.Label(self.root, text="Ваш ход (X)", font=('Arial', 12))
        self.status.pack(side=tk.TOP, pady=2)

        self.canvas = tk.Canvas(self.root, width=self.CANVAS, height=self.CANVAS,
                                bg='#F5DEB3', highlightthickness=0)
        self.canvas.pack(side=tk.TOP, padx=8, pady=4)

        tk.Label(self.root,
                 text="ЛКМ — ход · ПКМ/СКМ-тяга — панорама · колесо или +/- — зум · "
                      "стрелки — сдвиг · C — центр · 1/2/3 — копировать · A — просмотр · S — сохранить",
                 font=('Arial', 8), fg='#555').pack(side=tk.TOP)

        self.canvas.bind('<Button-1>', self.on_click)
        self.canvas.bind('<Motion>', self.on_hover)
        self.canvas.bind('<Leave>', self.on_leave)
        for btn in (2, 3):
            self.canvas.bind(f'<ButtonPress-{btn}>', self.pan_start)
            self.canvas.bind(f'<B{btn}-Motion>', self.pan_move)
            self.canvas.bind(f'<ButtonRelease-{btn}>', self.pan_end)
        self.canvas.bind('<MouseWheel>', self.on_wheel)
        self.root.bind('<Key>', self.on_key)

        self.new_game()

    # ---------- геометрия ----------

    def b2p(self, bx, by):
        return (self.CANVAS / 2 + (bx - self.cam_x) * self.cell,
                self.CANVAS / 2 + (by - self.cam_y) * self.cell)

    def p2b(self, px, py):
        return (int(round(self.cam_x + (px - self.CANVAS / 2) / self.cell)),
                int(round(self.cam_y + (py - self.CANVAS / 2) / self.cell)))

    def visible(self):
        half = self.CANVAS / (2 * self.cell)
        return (int(self.cam_x - half) - 1, int(self.cam_x + half) + 2,
                int(self.cam_y - half) - 1, int(self.cam_y + half) + 2)

    def ensure_visible(self, bx, by):
        half = self.CANVAS / (2 * self.cell) * 0.8
        if abs(bx - self.cam_x) > half or abs(by - self.cam_y) > half:
            self.cam_x, self.cam_y = float(bx), float(by)

    def center_last(self):
        if self.last_move:
            self.cam_x, self.cam_y = map(float, self.last_move)
        else:
            self.cam_x = self.cam_y = 0.0
        self.draw()

    # ---------- отрисовка ----------

    def draw(self):
        c = self.canvas
        c.delete('all')
        x0, x1, y0, y1 = self.visible()

        # линии по границам клеток -> камни в центрах
        for bx in range(x0, x1 + 2):
            px, _ = self.b2p(bx - 0.5, 0)
            c.create_line(px, 0, px, self.CANVAS, fill='#C8B08A')
        for by in range(y0, y1 + 2):
            _, py = self.b2p(0, by - 0.5)
            c.create_line(0, py, self.CANVAS, py, fill='#C8B08A')

        for bx in range(x0, x1 + 1):
            if bx % 5 == 0:
                px, _ = self.b2p(bx, 0)
                c.create_text(px, 10, text=str(bx), fill='#666', font=('Arial', 8))
        for by in range(y0, y1 + 1):
            if by % 5 == 0:
                _, py = self.b2p(0, by)
                c.create_text(14, py, text=str(by), fill='#666', font=('Arial', 8))

        ox, oy = self.b2p(0, 0)
        c.create_oval(ox - 2, oy - 2, ox + 2, oy + 2, fill='#B0A080', outline='')

        if self.hover and not self.thinking and not self.game_over \
                and self.current == self.human_player \
                and self.board.is_empty(*self.hover):
            px, py = self.b2p(*self.hover)
            h = self.cell / 2 - 1
            c.create_rectangle(px - h, py - h, px + h, py + h,
                               fill='#FFEB99', outline='#FFA500')

        r = max(3, self.cell * 0.32)
        for (x, y), p in self.board.grid.items():
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                continue
            px, py = self.b2p(x, y)
            if p == PLAYER_X:
                c.create_line(px - r, py - r, px + r, py + r, fill='red', width=2)
                c.create_line(px + r, py - r, px - r, py + r, fill='red', width=2)
            else:
                c.create_oval(px - r, py - r, px + r, py + r, outline='blue', width=2)

        if self.last_move:
            px, py = self.b2p(*self.last_move)
            h = self.cell / 2 - 1
            c.create_rectangle(px - h, py - h, px + h, py + h,
                               outline='#2E8B57', width=2)

        if self.win_line:
            for x, y in self.win_line:
                px, py = self.b2p(x, y)
                c.create_oval(px - r - 3, py - r - 3, px + r + 3, py + r + 3,
                              outline='#00AA00', width=3)

    # ---------- ввод ----------

    def on_click(self, event):
        if self.thinking or self.game_over or self.current != self.human_player:
            return
        cell = self.p2b(event.x, event.y)
        if not self.board.is_empty(*cell):
            return
        self.place(cell, self.human_player)
        if self.finish_if_over(self.human_player):
            return
        self.current = self.ai_player
        self.start_ai()

    def on_hover(self, event):
        if self.thinking or self.game_over:
            return
        cell = self.p2b(event.x, event.y)
        if cell != self.hover:
            self.hover = cell
            self.draw()

    def on_leave(self, event):
        if self.hover is not None:
            self.hover = None
            self.draw()

    def pan_start(self, event):
        self._pan_from = (event.x, event.y, self.cam_x, self.cam_y)

    def pan_move(self, event):
        if not self._pan_from:
            return
        x0, y0, cx, cy = self._pan_from
        self.cam_x = cx - (event.x - x0) / self.cell
        self.cam_y = cy - (event.y - y0) / self.cell
        self.draw()

    def pan_end(self, event):
        self._pan_from = None

    def on_wheel(self, event):
        step = 2 if event.delta > 0 else -2
        self.cell = max(self.MIN_CELL, min(self.MAX_CELL, self.cell + step))
        self.draw()

    def on_key(self, event):
        k = event.keysym
        step = 3
        if k == 'Left':
            self.cam_x -= step
        elif k == 'Right':
            self.cam_x += step
        elif k == 'Up':
            self.cam_y -= step
        elif k == 'Down':
            self.cam_y += step
        elif k in ('plus', 'KP_Add', 'equal'):
            self.cell = min(self.MAX_CELL, self.cell + 2)
        elif k in ('minus', 'KP_Subtract'):
            self.cell = max(self.MIN_CELL, self.cell - 2)
        elif k in ('c', 'C', 'с', 'С'):
            self.center_last(); return
        elif k == '1':
            self.copy_analysis(); return
        elif k == '2':
            self.copy_game(); return
        elif k == '3':
            self.copy_all_analyses(); return
        elif k in ('a', 'A', 'ф', 'Ф'):
            self.show_analyses(); return
        elif k in ('s', 'S', 'ы', 'Ы'):
            self.save_game(); return
        else:
            return
        self.draw()

    # ---------- ходы ----------

    def place(self, cell, player, analysis="", elapsed=None):
        self.board.make_move(cell[0], cell[1], player)
        self.last_move = cell
        n = len(self.move_records) + 1
        self.move_records.append({
            "n": n, "player": player, "move": cell,
            "analysis": analysis, "elapsed": elapsed,
        })
        self.game_log.append(f"{n}. {player_name(player)} {cell}")
        self.ensure_visible(*cell)
        self.draw()

    @staticmethod
    def find_win_line(board, player):
        for (x, y), p in board.grid.items():
            if p != player:
                continue
            for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
                cells = [(x, y)]
                nx, ny = x + dx, y + dy
                while board.get_cell(nx, ny) == player:
                    cells.append((nx, ny)); nx += dx; ny += dy
                nx, ny = x - dx, y - dy
                while board.get_cell(nx, ny) == player:
                    cells.insert(0, (nx, ny)); nx -= dx; ny -= dy
                if len(cells) >= WIN_LENGTH:
                    return cells
        return []

    def finish_if_over(self, player):
        if check_five(self.board, player):
            self.game_over = True
            self.win_line = self.find_win_line(self.board, player)
            self.draw()
            who = "Вы выиграли!" if player == self.human_player else "Компьютер выиграл!"
            self.status.config(text=who)
            messagebox.showinfo("Игра окончена", who)
            return True
        if len(self.board.move_history) >= self.MAX_MOVES:
            self.game_over = True
            self.status.config(text="Ничья (лимит ходов)")
            messagebox.showinfo("Игра окончена", "Ничья по лимиту ходов")
            return True
        return False

    # ---------- фоновый поиск ----------

    def start_ai(self):
        if self.game_over or self.thinking:
            return
        self.thinking = True
        self.gen += 1
        gen = self.gen
        snapshot = self.board.copy()
        ai = self.ai_player
        self.hover = None
        self.status.config(text=f"Компьютер ({player_name(ai)}) думает...")
        self.draw()
        t0 = time.perf_counter()

        def work():
            try:
                move = get_best_move(snapshot, ai)
                analysis = "\n".join(DEBUG_LOG)
                err = None
            except Exception as e:
                move, analysis, err = None, "", f"{type(e).__name__}: {e}"
            elapsed = time.perf_counter() - t0
            self.root.after(0, lambda: self.ai_done(gen, move, analysis, err, elapsed))

        threading.Thread(target=work, daemon=True).start()

    def ai_done(self, gen, move, analysis, err, elapsed):
        if gen != self.gen:
            return
        self.thinking = False
        self.last_analysis = analysis
        if err or move is None:
            self.status.config(text=f"Ошибка поиска: {err}")
            self.current = self.human_player
            return
        self.place(move, self.ai_player, analysis=analysis, elapsed=elapsed)
        if self.finish_if_over(self.ai_player):
            return
        self.current = self.human_player
        self.status.config(
            text=f"Ваш ход ({player_name(self.human_player)}) · ИИ думал {elapsed:.2f} с")
        self.draw()

    # ---------- партия ----------

    def new_game(self):
        self.gen += 1
        self.thinking = False
        self.board = Board()
        self.human_player, self.ai_player = assign_roles(self.ai_starts.get())
        self.current = PLAYER_X
        self.game_over = False
        self.win_line = []
        self.last_move = None
        self.hover = None
        self.game_log = []
        self.move_records = []
        self.last_analysis = ""
        self.cam_x = self.cam_y = 0.0
        self.status.config(text=f"Ваш ход ({player_name(self.human_player)})")
        self.draw()
        if self.ai_player == PLAYER_X:
            self.start_ai()

    def on_first_change(self):
        self.new_game()

    # ---------- анализы ----------

    def _clip(self, text, msg):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.config(text=msg)

    def copy_analysis(self):
        self._clip(self.last_analysis or "(анализа ещё нет)",
                   f"Анализ скопирован ({len(self.last_analysis)} симв.)")

    def copy_game(self):
        text = "\n".join(self.game_log) or "(партия пуста)"
        self._clip(text, f"Партия скопирована ({len(self.game_log)} ходов)")

    def copy_all_analyses(self):
        parts = []
        for r in self.move_records:
            head = f"=== Ход {r['n']}: {player_name(r['player'])} {r['move']}"
            if r["elapsed"] is not None:
                head += f" ({r['elapsed']:.2f} с)"
            parts.append(head + " ===")
            parts.append(r["analysis"] or "(ход игрока — без анализа)")
            parts.append("")
        text = "\n".join(parts) or "(партия пуста)"
        self._clip(text, f"Скопировано анализов: {len(self.move_records)} ходов")

    def show_analyses(self):
        records = [r for r in self.move_records if r["analysis"]]
        if not records:
            self.status.config(text="Анализов пока нет")
            return
        win = tk.Toplevel(self.root)
        win.title("Анализы ходов ИИ")
        win.geometry("980x620")

        left = tk.Frame(win)
        left.pack(side=tk.LEFT, fill=tk.Y)
        lb = tk.Listbox(left, width=34, font=('Consolas', 10), exportselection=False)
        sb = tk.Scrollbar(left, command=lb.yview)
        lb.config(yscrollcommand=sb.set)
        lb.pack(side=tk.LEFT, fill=tk.Y)
        sb.pack(side=tk.LEFT, fill=tk.Y)

        right = tk.Frame(win)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        txt = tk.Text(right, wrap=tk.NONE, font=('Consolas', 9))
        tsb = tk.Scrollbar(right, command=txt.yview)
        txt.config(yscrollcommand=tsb.set)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tsb.pack(side=tk.LEFT, fill=tk.Y)

        for r in records:
            lb.insert(tk.END, f"{r['n']:>3}. {player_name(r['player'])} "
                              f"{str(r['move']):<12} {r['elapsed']:.2f}s")

        def on_select(_evt=None):
            sel = lb.curselection()
            if not sel:
                return
            r = records[sel[0]]
            txt.delete('1.0', tk.END)
            txt.insert(tk.END, r["analysis"])

        lb.bind('<<ListboxSelect>>', on_select)
        lb.selection_set(0)
        on_select()

    def save_game(self):
        if not self.move_records:
            self.status.config(text="Партия пуста")
            return
        path = filedialog.asksaveasfilename(
            title="Сохранить партию и анализы",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Все файлы", "*.*")],
            initialfile=f"gomoku_{time.strftime('%Y%m%d_%H%M%S')}.json")
        if not path:
            return
        data = {
            "saved": time.strftime("%Y-%m-%d %H:%M:%S"),
            "human": player_name(self.human_player),
            "ai": player_name(self.ai_player),
            "ai_starts": bool(self.ai_starts.get()),
            "moves": [
                {"n": r["n"], "player": player_name(r["player"]),
                 "x": r["move"][0], "y": r["move"][1],
                 "elapsed": r["elapsed"], "analysis": r["analysis"]}
                for r in self.move_records
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.status.config(text=f"Сохранено: {path}")


    def run(self):
        self.root.mainloop()

'''
if __name__ == "__main__":
    app = GomokuGUI()
    app.run()
'''
if __name__ == "__main__":
    from gomoku_ui import main
    main()