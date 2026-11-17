import tkinter as tk
from tkinter import messagebox
from typing import Optional, List, Tuple, Dict
import threading

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

    def make_move(self, x: int, y: int, player: int) -> bool:
        if (x, y) in self.grid:
            return False
        self.grid[(x, y)] = player
        self.move_history.append((x, y, player))
        return True

    def undo_move(self) -> Optional[Tuple[int, int, int]]:
        if not self.move_history:
            return None
        x, y, player = self.move_history.pop()
        del self.grid[(x, y)]
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
    board.make_move(x, y, player)
    threats = []
    directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
    for dx, dy in directions:
        length, open_ends = count_line(board, x, y, dx, dy, player)
        if length >= 5:
            threats.append('five')
        elif length == 4 and open_ends == 2:
            threats.append('open_four')
        elif length == 4 and open_ends == 1:
            threats.append('closed_four')
        elif length == 3 and open_ends == 2:
            threats.append('open_three')
        else:
            length_gap, gaps, open_ends_gap = count_line_with_gap(board, x, y, dx, dy, player)
            if length_gap >= 5:
                threats.append('five')
            elif length_gap == 4 and gaps == 1 and open_ends_gap == 2:
                threats.append('open_four')
            elif length_gap == 4 and gaps == 1 and open_ends_gap == 1:
                threats.append('closed_four')
            elif length_gap == 3 and gaps == 1 and open_ends_gap == 2:
                threats.append('open_three')
    board.undo_move()
    return threats


def generate_four_moves(board: Board, player: int) -> List[Tuple[int, int]]:
    moves = []
    for x, y in board.get_candidate_moves(radius=2):
        threats = get_potential_threats(board, x, y, player)
        if 'open_four' in threats or 'closed_four' in threats or 'five' in threats:
            moves.append((x, y))
    return moves


def generate_threat_moves(board: Board, player: int) -> List[Tuple[int, int]]:
    moves = []
    for x, y in board.get_candidate_moves(radius=2):
        threats = get_potential_threats(board, x, y, player)
        if ('open_four' in threats or 'closed_four' in threats or
                'open_three' in threats or 'five' in threats):
            moves.append((x, y))
    return moves


def count_all_open_threes(board: Board, player: int, debug: bool = False) -> int:
    count = 0
    directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
    seen = set()

    for x, y, p in board.move_history:
        if p != player:
            continue
        for dx, dy in directions:
            if (board.get_cell(x, y) == player and
                    board.get_cell(x + dx, y + dy) == player and
                    board.get_cell(x + 2 * dx, y + 2 * dy) == player):

                if board.get_cell(x - dx, y - dy) == player:
                    continue
                if board.get_cell(x + 3 * dx, y + 3 * dy) == player:
                    continue

                if (board.get_cell(x - dx, y - dy) == EMPTY and
                        board.get_cell(x + 3 * dx, y + 3 * dy) == EMPTY):
                    end1 = (x, y)
                    end2 = (x + 2 * dx, y + 2 * dy)
                    key = (min(end1, end2), max(end1, end2), dx, dy, 'cont')
                    if key not in seen:
                        seen.add(key)
                        count += 1
                        if debug:
                            log(f"    Непрерывная: ({x},{y})-({x + dx},{y + dy})-({x + 2 * dx},{y + 2 * dy})")

            elif (board.get_cell(x, y) == player and
                  board.get_cell(x + dx, y + dy) == EMPTY and
                  board.get_cell(x + 2 * dx, y + 2 * dy) == player and
                  board.get_cell(x + 3 * dx, y + 3 * dy) == player):

                if (board.get_cell(x - dx, y - dy) == EMPTY and
                        board.get_cell(x + 4 * dx, y + 4 * dy) == EMPTY):
                    cells = tuple(sorted([(x, y), (x + 2 * dx, y + 2 * dy), (x + 3 * dx, y + 3 * dy)]))
                    gap = (x + dx, y + dy)
                    key = (cells, gap, dx, dy, 'gap1')
                    if key not in seen:
                        seen.add(key)
                        count += 1
                        if debug:
                            log(f"    С разрывом X_XX: ({x},{y})_({x + 2 * dx},{y + 2 * dy})-({x + 3 * dx},{y + 3 * dy})")

            elif (board.get_cell(x, y) == player and
                  board.get_cell(x + dx, y + dy) == player and
                  board.get_cell(x + 2 * dx, y + 2 * dy) == EMPTY and
                  board.get_cell(x + 3 * dx, y + 3 * dy) == player):

                if (board.get_cell(x - dx, y - dy) == EMPTY and
                        board.get_cell(x + 4 * dx, y + 4 * dy) == EMPTY):
                    cells = tuple(sorted([(x, y), (x + dx, y + dy), (x + 3 * dx, y + 3 * dy)]))
                    gap = (x + 2 * dx, y + 2 * dy)
                    key = (cells, gap, dx, dy, 'gap2')
                    if key not in seen:
                        seen.add(key)
                        count += 1
                        if debug:
                            log(f"    С разрывом XX_X: ({x},{y})-({x + dx},{y + dy})_({x + 3 * dx},{y + 3 * dy})")

    return count


def check_double_threat(board: Board, player: int) -> bool:
    open_threes = count_all_open_threes(board, player)
    if open_threes >= 2:
        return True
    open_fours = 0
    closed_fours = 0
    directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
    for x, y, p in board.move_history:
        if p != player:
            continue
        for dx, dy in directions:
            length, open_ends = count_line(board, x, y, dx, dy, player)
            if length == 4:
                if open_ends == 2:
                    open_fours += 1
                elif open_ends == 1:
                    closed_fours += 1
    if open_fours >= 1:
        return True
    if closed_fours >= 2:
        return True
    if open_threes >= 1 and closed_fours >= 1:
        return True
    return False


def search_vcf(board: Board, depth: int, player: int, is_attacking: bool,
               debug_path: List[str] = None, indent: int = 0) -> Optional[Tuple[int, int]]:
    if debug_path is None:
        debug_path = []

    if depth == 0:
        return None

    attacking_player = player if is_attacking else (PLAYER_O if player == PLAYER_X else PLAYER_X)
    defending_player = PLAYER_O if attacking_player == PLAYER_X else PLAYER_X

    candidate_moves = generate_four_moves(board, attacking_player)

    if not candidate_moves:
        return None

    indent_str = "  " * indent
    log(f"{indent_str}VCF поиск (глубина {depth}, {player_name(attacking_player)} атакует): "
        f"{len(candidate_moves)} четвёрок -> {candidate_moves[:10]}")

    for move in candidate_moves:
        board.make_move(move[0], move[1], attacking_player)

        is_five = check_five(board, attacking_player)
        is_double = check_double_threat(board, attacking_player)

        if is_five:
            log(f"{indent_str}VCF: пятёрка в {move}! Путь: "
                f"{' -> '.join(debug_path + [f'{player_name(attacking_player)}{move}'])}")
            board.undo_move()
            return move

        if is_double:
            log(f"{indent_str}VCF: вилка в {move}! Путь: "
                f"{' -> '.join(debug_path + [f'{player_name(attacking_player)}{move}'])}")
            board.undo_move()
            return move

        defense_moves = generate_four_moves(board, defending_player)

        if len(defense_moves) == 0:
            log(f"{indent_str}VCF: нет защиты после {move}! Путь: "
                f"{' -> '.join(debug_path + [f'{player_name(attacking_player)}{move}'])}")
            board.undo_move()
            return move

        if is_attacking:
            found_win = False
            for defense in defense_moves[:2]:
                board.make_move(defense[0], defense[1], defending_player)
                log(f"{indent_str}  {player_name(attacking_player)}{move} -> "
                    f"{player_name(defending_player)}{defense}")
                result = search_vcf(board, depth - 2, player, is_attacking,
                                    debug_path + [f'{player_name(attacking_player)}{move}',
                                                  f'{player_name(defending_player)}{defense}'],
                                    indent + 1)
                board.undo_move()
                if result:
                    found_win = True
                    break
            board.undo_move()
            if found_win:
                return move
        else:
            all_defenses_fail = True
            for defense in defense_moves[:2]:
                board.make_move(defense[0], defense[1], defending_player)
                log(f"{indent_str}  {player_name(attacking_player)}{move} -> "
                    f"{player_name(defending_player)}{defense}")
                result = search_vcf(board, depth - 2, player, is_attacking,
                                    debug_path + [f'{player_name(attacking_player)}{move}',
                                                  f'{player_name(defending_player)}{defense}'],
                                    indent + 1)
                board.undo_move()
                if not result:
                    all_defenses_fail = False
                    break
            board.undo_move()
            if all_defenses_fail:
                return move

    return None


def search_vct(board: Board, depth: int, player: int, is_attacking: bool) -> Optional[Tuple[int, int]]:
    if depth == 0:
        return None
    attacking_player = player if is_attacking else (PLAYER_O if player == PLAYER_X else PLAYER_X)
    defending_player = PLAYER_O if attacking_player == PLAYER_X else PLAYER_X
    vcf_move = search_vcf(board, depth, player, is_attacking)
    if vcf_move:
        return vcf_move
    candidate_moves = generate_threat_moves(board, attacking_player)
    for move in candidate_moves:
        board.make_move(move[0], move[1], attacking_player)
        if check_double_threat(board, attacking_player):
            board.undo_move()
            return move
        defense_moves = generate_four_moves(board, defending_player)
        if len(defense_moves) == 0:
            board.undo_move()
            return move
        if is_attacking:
            found_win = False
            for defense in defense_moves[:2]:
                board.make_move(defense[0], defense[1], defending_player)
                if search_vct(board, depth - 2, player, is_attacking):
                    found_win = True
                board.undo_move()
                if found_win:
                    break
            board.undo_move()
            if found_win:
                return move
        else:
            all_defenses_fail = True
            for defense in defense_moves[:2]:
                board.make_move(defense[0], defense[1], defending_player)
                if not search_vct(board, depth - 2, player, is_attacking):
                    all_defenses_fail = False
                board.undo_move()
                if not all_defenses_fail:
                    break
            board.undo_move()
            if all_defenses_fail:
                return move
    return None


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
    directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
    threats = []
    seen = set()

    for x, y, p in board.move_history:
        if p != player:
            continue
        for dx, dy in directions:
            if (board.get_cell(x, y) == player and
                    board.get_cell(x + dx, y + dy) == player and
                    board.get_cell(x + 2 * dx, y + 2 * dy) == player):

                if board.get_cell(x - dx, y - dy) == player:
                    continue
                if board.get_cell(x + 3 * dx, y + 3 * dy) == player:
                    continue

                if (board.get_cell(x - dx, y - dy) == EMPTY and
                        board.get_cell(x + 3 * dx, y + 3 * dy) == EMPTY):
                    end1 = (x, y)
                    end2 = (x + 2 * dx, y + 2 * dy)
                    key = (min(end1, end2), max(end1, end2), dx, dy, 'cont')
                    if key not in seen:
                        seen.add(key)
                        threats.append((x - dx, y - dy))
                        threats.append((x + 3 * dx, y + 3 * dy))

            elif (board.get_cell(x, y) == player and
                  board.get_cell(x + dx, y + dy) == EMPTY and
                  board.get_cell(x + 2 * dx, y + 2 * dy) == player and
                  board.get_cell(x + 3 * dx, y + 3 * dy) == player):

                if (board.get_cell(x - dx, y - dy) == EMPTY and
                        board.get_cell(x + 4 * dx, y + 4 * dy) == EMPTY):
                    cells = tuple(sorted([(x, y), (x + 2 * dx, y + 2 * dy), (x + 3 * dx, y + 3 * dy)]))
                    gap = (x + dx, y + dy)
                    key = (cells, gap, dx, dy, 'gap1')
                    if key not in seen:
                        seen.add(key)
                        threats.append((x + dx, y + dy))

            elif (board.get_cell(x, y) == player and
                  board.get_cell(x + dx, y + dy) == player and
                  board.get_cell(x + 2 * dx, y + 2 * dy) == EMPTY and
                  board.get_cell(x + 3 * dx, y + 3 * dy) == player):

                if (board.get_cell(x - dx, y - dy) == EMPTY and
                        board.get_cell(x + 4 * dx, y + 4 * dy) == EMPTY):
                    cells = tuple(sorted([(x, y), (x + dx, y + dy), (x + 3 * dx, y + 3 * dy)]))
                    gap = (x + 2 * dx, y + 2 * dy)
                    key = (cells, gap, dx, dy, 'gap2')
                    if key not in seen:
                        seen.add(key)
                        threats.append((x + 2 * dx, y + 2 * dy))

    return threats


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
    if len(board.move_history) < 4:
        log("  (пропущено: ходов < 4)")
        return None
    opponent = PLAYER_O if player == PLAYER_X else PLAYER_X
    debug_dump_all_threes(board, opponent)

    threats = find_all_open_three_blocks(board, opponent)
    log(f"  find_all_open_three_blocks вернул: {threats}")

    if not threats:
        return None

    free_blocks = []
    for t in threats:
        if board.is_empty(t[0], t[1]):
            free_blocks.append(t)
            log(f"    {t} — ПУСТА")
        else:
            log(f"    {t} — ЗАНЯТА ({player_name(board.get_cell(t[0], t[1]))})")

    if not free_blocks:
        return None

    best_block = None
    best_score = -float('inf')

    for block_move in free_blocks:
        log(f"    Проверяем блокировку {block_move}, ходов на доске: {len(board.move_history)}")
        board.make_move(block_move[0], block_move[1], player)
        log(f"    После make_move, ходов на доске: {len(board.move_history)}")

        max_threat_level, threat_desc = evaluate_threats_after_move(board, opponent)
        log(f"    После evaluate_threats, ходов на доске: {len(board.move_history)}")

        penalty = 0
        if max_threat_level >= 4:
            penalty = 1000000
        elif max_threat_level == 3:
            penalty = 100000
        elif max_threat_level == 2:
            penalty = 20000
        elif max_threat_level == 1:
            penalty = 5000

        score = evaluate_position(board, player) - penalty

        # Увеличили глубину VCF с 4 до 6
        if max_threat_level >= 2:
            log(f"      Запуск поиска VCF противника (глубина 6)...")
            log(f"      Перед search_vcf, ходов на доске: {len(board.move_history)}")
            vcf_found = search_vcf(board, depth=6, player=opponent, is_attacking=True)
            log(f"      После search_vcf, ходов на доске: {len(board.move_history)}")
            if vcf_found:
                log(f"      ВНИМАНИЕ: после блокировки {block_move} противник может создать VCF!")
                penalty += 50000
                score -= 50000
            else:
                log(f"      VCF противника не найден")

        board.undo_move()
        log(f"    После undo_move, ходов на доске: {len(board.move_history)}")

        log(f"    Оценка после блокировки {block_move}: {score}")
        log(f"      Макс. угроза противника: уровень {max_threat_level} ({threat_desc})")

        if score > best_score:
            best_score = score
            best_block = block_move

    return best_block


def find_own_fork(board: Board, player: int) -> Optional[Tuple[int, int]]:
    for x, y in board.get_candidate_moves(radius=2):
        if not board.is_empty(x, y):
            continue
        board.make_move(x, y, player)
        open_threes = count_all_open_threes(board, player)
        board.undo_move()
        if open_threes >= 2:
            log(f"  Вилка найдена в ({x},{y}): {open_threes} открытых троек")
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


def evaluate_position(board: Board, player: int) -> int:
    score = 0
    directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
    SCORE_FIVE = 1000000
    SCORE_OPEN_FOUR = 100000
    SCORE_CLOSED_FOUR = 10000
    SCORE_OPEN_THREE = 5000
    SCORE_GAP_FOUR_OPEN = 8000
    SCORE_GAP_FOUR_CLOSED = 5000
    SCORE_GAP_THREE_OPEN = 3000

    for p_id in [player, PLAYER_O if player == PLAYER_X else PLAYER_X]:
        sign = 1 if p_id == player else -1
        for x, y, p in board.move_history:
            if p != p_id:
                continue
            for dx, dy in directions:
                length, open_ends = count_line(board, x, y, dx, dy, p_id)
                if length >= 5:
                    score += sign * SCORE_FIVE
                elif length == 4:
                    if open_ends == 2:
                        score += sign * SCORE_OPEN_FOUR
                    elif open_ends == 1:
                        score += sign * SCORE_CLOSED_FOUR
                elif length == 3 and open_ends == 2:
                    score += sign * SCORE_OPEN_THREE
                length_gap, gaps, open_ends_gap = count_line_with_gap(board, x, y, dx, dy, p_id)
                if length_gap == 4 and gaps == 1:
                    if open_ends_gap == 2:
                        score += sign * SCORE_GAP_FOUR_OPEN
                    elif open_ends_gap == 1:
                        score += sign * SCORE_GAP_FOUR_CLOSED
                elif length_gap == 3 and gaps == 1 and open_ends_gap == 2:
                    score += sign * SCORE_GAP_THREE_OPEN
    return score


def minimax(board: Board, depth: int, alpha: int, beta: int,
            is_maximizing: bool, player: int) -> int:
    if depth == 0:
        return evaluate_position(board, player)
    if check_five(board, PLAYER_X):
        return 1000000 if player == PLAYER_X else -1000000
    if check_five(board, PLAYER_O):
        return 1000000 if player == PLAYER_O else -1000000
    current_player = player if is_maximizing else (PLAYER_O if player == PLAYER_X else PLAYER_X)
    candidates = board.get_candidate_moves(radius=2)
    candidates_with_scores = []
    for x, y in candidates:
        board.make_move(x, y, current_player)
        score = evaluate_position(board, player)
        board.undo_move()
        candidates_with_scores.append(((x, y), score))
    candidates_with_scores.sort(key=lambda x: x[1], reverse=is_maximizing)
    if is_maximizing:
        max_eval = -float('inf')
        for (x, y), _ in candidates_with_scores[:10]:
            board.make_move(x, y, current_player)
            eval_score = minimax(board, depth - 1, alpha, beta, False, player)
            board.undo_move()
            max_eval = max(max_eval, eval_score)
            alpha = max(alpha, eval_score)
            if beta <= alpha:
                break
        return max_eval
    else:
        min_eval = float('inf')
        for (x, y), _ in candidates_with_scores[:10]:
            board.make_move(x, y, current_player)
            eval_score = minimax(board, depth - 1, alpha, beta, True, player)
            board.undo_move()
            min_eval = min(min_eval, eval_score)
            beta = min(beta, eval_score)
            if beta <= alpha:
                break
        return min_eval


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
    vct_depth = 15 if my_stones >= 3 and opp_stones >= 2 else 6

    log("\n[ШАГ 1] Мгновенный выигрыш ИИ")
    immediate_win = check_immediate_win(board, player)
    if immediate_win:
        log(f"  -> НАЙДЕН: {immediate_win}")
        log(f"\n=== Финальный ход: {immediate_win} ===")
        return immediate_win
    log("  -> не найден")

    log(f"\n[ШАГ 2] Мгновенная защита от выигрыша {player_name(opponent)}")
    opponent_immediate_win = check_immediate_win(board, opponent)
    if opponent_immediate_win:
        log(f"  -> НАЙДЕНА угроза: {opponent_immediate_win}")
        log(f"\n=== Финальный ход: {opponent_immediate_win} ===")
        return opponent_immediate_win
    log("  -> не найдена")

    log(f"\n[ШАГ 3] Свой VCF (глубина {vcf_depth})")
    if my_stones >= 3:
        four_moves = generate_four_moves(board, player)
        log(f"  Четверочных ходов: {len(four_moves)} -> {four_moves[:5]}")
        vcf_move = search_vcf(board, depth=vcf_depth, player=player, is_attacking=True)
        if vcf_move:
            log(f"  -> НАЙДЕН: {vcf_move}")
            log(f"\n=== Финальный ход: {vcf_move} ===")
            return vcf_move
        log("  -> не найден")
    else:
        log("  (пропущено: своих камней < 3)")

    log(f"\n[ШАГ 4] Блокировка открытой тройки {player_name(opponent)} (включая с разрывом)")
    open_three_block = block_open_three_threats(board, player)
    if open_three_block:
        log(f"  -> ВЫБРАНА блокировка: {open_three_block}")
        log(f"\n=== Финальный ход: {open_three_block} ===")
        return open_three_block
    log("  -> не выбрана")

    log("\n[ШАГ 5] Своя вилка из открытых троек")
    own_fork = find_own_fork(board, player)
    if own_fork:
        log(f"  -> НАЙДЕНА: {own_fork}")
        log(f"\n=== Финальный ход: {own_fork} ===")
        return own_fork
    log("  -> не найдена")

    log(f"\n[ШАГ 5.5] Блокировка потенциальной вилки {player_name(opponent)}")
    fork_block = block_potential_fork(board, player)
    if fork_block:
        log(f"  -> ВЫБРАНА блокировка: {fork_block}")
        log(f"\n=== Финальный ход: {fork_block} ===")
        return fork_block
    log("  -> не найдена")

    log(f"\n[ШАГ 6] Защита от VCF {player_name(opponent)} (глубина {vcf_depth})")
    if opp_stones >= 3:
        opp_four = generate_four_moves(board, opponent)
        log(f"  Четверочных ходов противника: {len(opp_four)} -> {opp_four[:5]}")
        opponent_vcf = search_vcf(board, depth=vcf_depth, player=player, is_attacking=False)
        if opponent_vcf:
            log(f"  -> НАЙДЕНА угроза: {opponent_vcf}")
            final_move = find_blocking_move(board, opponent_vcf, player)
            log(f"\n=== Финальный ход: {final_move} ===")
            return final_move
        log("  -> не найдена")
    else:
        log("  (пропущено: камней противника < 3)")

    log(f"\n[ШАГ 7] Свой VCT (глубина {vct_depth})")
    if my_stones >= 2:
        threat_moves = generate_threat_moves(board, player)
        log(f"  Угрозных ходов: {len(threat_moves)} -> {threat_moves[:5]}")
        vct_move = search_vct(board, depth=vct_depth, player=player, is_attacking=True)
        if vct_move:
            log(f"  -> НАЙДЕН: {vct_move}")
            log(f"\n=== Финальный ход: {vct_move} ===")
            return vct_move
        log("  -> не найден")
    else:
        log("  (пропущено: своих камней < 2)")

    log(f"\n[ШАГ 8] Защита от VCT {player_name(opponent)} (глубина {vct_depth})")
    if opp_stones >= 2:
        opponent_vct = search_vct(board, depth=vct_depth, player=player, is_attacking=False)
        if opponent_vct:
            log(f"  -> НАЙДЕНА угроза: {opponent_vct}")
            final_move = find_blocking_move(board, opponent_vct, player)
            log(f"\n=== Финальный ход: {final_move} ===")
            return final_move
        log("  -> не найдена")
    else:
        log("  (пропущено: камней противника < 2)")

    log("\n[ШАГ 9] Позиционный Minimax")
    candidates = board.get_candidate_moves(radius=2)
    candidates_with_scores = []
    for x, y in candidates:
        board.make_move(x, y, player)
        score = evaluate_position(board, player)
        board.undo_move()
        candidates_with_scores.append(((x, y), score))
    candidates_with_scores.sort(key=lambda x: x[1], reverse=True)
    log(f"  Топ-10 кандидатов:")
    for (x, y), s in candidates_with_scores[:10]:
        log(f"    ({x},{y}) = {s}")

    best_score = -float('inf')
    best_move = candidates_with_scores[0][0]
    max_candidates = 7 if len(board.move_history) < 6 else 15
    for (x, y), _ in candidates_with_scores[:max_candidates]:
        board.make_move(x, y, player)
        score = minimax(board, depth=4, alpha=-float('inf'), beta=float('inf'),
                        is_maximizing=False, player=player)
        board.undo_move()
        log(f"  Minimax({x},{y}) = {score}")
        if score > best_score:
            best_score = score
            best_move = (x, y)
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