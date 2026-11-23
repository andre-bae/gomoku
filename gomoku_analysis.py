# gomoku_analysis.py
"""
Этап 1: анализатор линий на окнах из 5 клеток.
Чистый модуль: без GUI, без глобального состояния, без логирования.
Требует от доски .grid, .get_cell, .make_move, .undo_move.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Set, Iterable

EMPTY = 0
PLAYER_X = 1
PLAYER_O = 2
WIN_LEN = 5

DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))

FIVE = "five"
LIVE_FOUR = "live_four"          # >= 2 точек достройки пятёрки
FOUR = "four"                    # ровно 1 точка достройки (закрытая/разрывная)
LIVE_THREE = "live_three"        # ходом превращается в живую четвёрку
SLEEPING_THREE = "sleeping_three"  # ходом превращается только в закрытую четвёрку

MARGIN = 5


@dataclass(frozen=True)
class Threat:
    kind: str
    player: int
    direction: Tuple[int, int]
    stones: Tuple[Tuple[int, int], ...]   # камни, образующие угрозу
    points: Tuple[Tuple[int, int], ...]   # точки достройки / ключевые точки


# ---------- геометрия линий ----------

def _line_inv(didx: int, x: int, y: int) -> int:
    dx, dy = DIRECTIONS[didx]
    if dx == 0:
        return x
    if dy == 0:
        return y
    if dy == 1:
        return x - y
    return x + y


def _coord(didx: int, t: int, inv: int) -> Tuple[int, int]:
    dx, dy = DIRECTIONS[didx]
    if dx == 0:
        return (inv, t)
    if dy == 0:
        return (t, inv)
    if dy == 1:
        return (t, t - inv)
    return (t, inv - t)


def _param(didx: int, x: int, y: int) -> int:
    return x if DIRECTIONS[didx][0] == 1 else y


def _collect_lines(board, player) -> Dict[Tuple[int, int], List[int]]:
    lines: Dict[Tuple[int, int], List[int]] = {}
    for (x, y), p in board.grid.items():
        if p != player:
            continue
        for didx in range(4):
            key = (didx, _line_inv(didx, x, y))
            lines.setdefault(key, []).append(_param(didx, x, y))
    return lines


def _split_opponent(vals: List[int], opponent: int) -> List[Tuple[int, int]]:
    segs = []
    start = 0
    for i, v in enumerate(vals):
        if v == opponent:
            if i > start:
                segs.append((start, i))
            start = i + 1
    if len(vals) > start:
        segs.append((start, len(vals)))
    return segs


# ---------- ядро: окна из 5 ----------

def _scan_windows(vals: List[int], player: int, opponent: int):
    """Возвращает fives, fours, threes по индексам внутри vals."""
    n = len(vals)
    fives: List[Tuple[int, ...]] = []
    fours: Dict[Tuple[int, ...], Set[int]] = {}
    threes: Dict[Tuple[int, ...], Set[int]] = {}
    for s in range(n - WIN_LEN + 1):
        stones = []
        empties = []
        bad = False
        for i in range(s, s + WIN_LEN):
            v = vals[i]
            if v == opponent:
                bad = True
                break
            if v == player:
                stones.append(i)
            else:
                empties.append(i)
        if bad:
            continue
        k = len(stones)
        key = tuple(stones)
        if k == 5:
            fives.append(key)
        elif k == 4:
            fours.setdefault(key, set()).update(empties)
        elif k == 3:
            threes.setdefault(key, set()).update(empties)
    return fives, fours, threes


def _classify_three(vals: List[int], player: int, opponent: int,
                    points: Set[int], three_stones: Tuple[int, ...]) -> Tuple[str, Set[int]]:
    """Достраиваем камень в каждую пустую клетку тройки.
    Учитываем ТОЛЬКО четвёрки, содержащие все камни нашей тройки и новый камень,
    иначе соседняя четвёрка на той же линии делает мёртвую тройку 'живой'."""
    live: Set[int] = set()
    sleeping: Set[int] = set()
    base = set(three_stones)
    for i in sorted(points):
        vals[i] = player
        _, fours_after, _ = _scan_windows(vals, player, opponent)
        vals[i] = EMPTY
        best = 0
        for st, pts in fours_after.items():
            s = set(st)
            if i in s and base <= s:
                best = max(best, len(pts))
        if best >= 2:
            live.add(i)
        elif best == 1:
            sleeping.add(i)
    if live:
        return LIVE_THREE, live
    if sleeping:
        return SLEEPING_THREE, sleeping
    return "", set()


# ---------- публичный API ----------

def analyze_threats(board, player: int) -> List[Threat]:
    opponent = PLAYER_O if player == PLAYER_X else PLAYER_X
    found: Dict[Tuple, Threat] = {}

    for (didx, inv), ts in _collect_lines(board, player).items():
        lo, hi = min(ts) - MARGIN, max(ts) + MARGIN
        coords = [_coord(didx, t, inv) for t in range(lo, hi + 1)]
        vals = [board.get_cell(x, y) for (x, y) in coords]
        direction = DIRECTIONS[didx]

        for a, b in _split_opponent(vals, opponent):
            sv = vals[a:b]
            sc = coords[a:b]
            fives, fours, threes = _scan_windows(sv, player, opponent)

            five_stones = set()
            for st in fives:
                five_stones.update(st)
                t = Threat(FIVE, player, direction,
                           tuple(sc[i] for i in st), ())
                found[(t.kind, direction, t.stones, t.points)] = t

            four_stones = set()
            for st, pts in fours.items():
                if set(st) <= five_stones:
                    continue
                four_stones.update(st)
                kind = LIVE_FOUR if len(pts) >= 2 else FOUR
                t = Threat(kind, player, direction,
                           tuple(sc[i] for i in st),
                           tuple(sorted(sc[i] for i in pts)))
                found[(t.kind, direction, t.stones, t.points)] = t

            for st, pts in threes.items():
                # тройка, целиком лежащая внутри четвёрки/пятёрки, — не отдельная угроза
                if set(st) <= four_stones or set(st) <= five_stones:
                    continue
                kind, key_points = _classify_three(sv, player, opponent, pts, st)
                if not kind:
                    continue
                t = Threat(kind, player, direction,
                           tuple(sc[i] for i in st),
                           tuple(sorted(sc[i] for i in key_points)))
                found[(t.kind, direction, t.stones, t.points)] = t

    return list(found.values())


def completion_points(board, player: int) -> Set[Tuple[int, int]]:
    """Клетки, ход в которые даёт игроку пятёрку. Это же точки блокировки для защитника."""
    pts: Set[Tuple[int, int]] = set()
    for t in analyze_threats(board, player):
        if t.kind in (FOUR, LIVE_FOUR):
            pts.update(t.points)
    return pts


def is_winning_threat_set(threats: Iterable[Threat]) -> bool:
    """
    Есть ли уже неустранимая за один ход угроза.
    Оговорка: случай двух живых троек с общей ключевой точкой будет
    уточнён на этапе 2 (проверка одним ходом защитника).
    """
    threats = list(threats)
    if any(t.kind in (FIVE, LIVE_FOUR) for t in threats):
        return True
    four_points: Set[Tuple[int, int]] = set()
    for t in threats:
        if t.kind == FOUR:
            four_points.update(t.points)
    if len(four_points) >= 2:
        return True
    live_threes = [t for t in threats if t.kind == LIVE_THREE]
    if four_points and live_threes:
        return True
    if len(live_threes) >= 2:
        return True
    return False


def _other(player: int) -> int:
    return PLAYER_O if player == PLAYER_X else PLAYER_X


def _fork_survives(board, player: int, cells) -> bool:
    """
    Уточнение: может ли ОДИН ход защитника погасить сразу все угрозы.
    Пробуем клетки-кандидаты (точки достройки четвёрок и ключевые точки троек).
    Если после какой-то из них не остаётся ни четвёрок, ни живых троек —
    это не вилка.
    C8: пробный ход делается через make_move/undo_move, чтобы хеш доски
    и будущие кэши оставались согласованными.
    """
    defender = _other(player)
    for (x, y) in sorted(cells):
        if board.get_cell(x, y) != EMPTY:
            continue
        board.make_move(x, y, defender)
        try:
            th = analyze_threats(board, player)
            has_four = any(t.kind in (FIVE, LIVE_FOUR, FOUR) for t in th)
            live = sum(1 for t in th if t.kind == LIVE_THREE)
        finally:
            board.undo_move()
        if not has_four and live == 0:
            return False
    return True


def is_double_threat_new(board, player: int) -> bool:
    threats = analyze_threats(board, player)
    if not is_winning_threat_set(threats):
        return False
    if any(t.kind in (FIVE, LIVE_FOUR) for t in threats):
        return True
    cells = set()
    for t in threats:
        if t.kind in (FOUR, LIVE_THREE):
            cells.update(t.points)
    return _fork_survives(board, player, cells)


def describe(threats: Iterable[Threat]) -> str:
    """Человекочитаемый инвентарь угроз — то, чего не хватало в старом логе."""
    lines = []
    for t in sorted(threats, key=lambda z: (z.kind, z.direction, z.stones)):
        lines.append(f"{t.kind:15s} dir={t.direction} камни={t.stones} точки={t.points}")
    return "\n".join(lines) if lines else "(угроз нет)"


def four_move_candidates(board, player: int):
    """
    Клетки, ход в которые создаёт четвёрку или пятёрку.
    Точный критерий: пустая клетка окна из 5, где уже >=3 наших камней
    и нет камней противника. Один проход по линиям, без симуляций.
    """
    opponent = PLAYER_O if player == PLAYER_X else PLAYER_X
    res = set()
    for (didx, inv), ts in _collect_lines(board, player).items():
        lo, hi = min(ts) - MARGIN, max(ts) + MARGIN
        coords = [_coord(didx, t, inv) for t in range(lo, hi + 1)]
        vals = [board.get_cell(x, y) for (x, y) in coords]
        for a, b in _split_opponent(vals, opponent):
            sv, sc = vals[a:b], coords[a:b]
            n = len(sv)
            for s in range(n - WIN_LEN + 1):
                stones = 0
                empties = []
                bad = False
                for i in range(s, s + WIN_LEN):
                    v = sv[i]
                    if v == opponent:
                        bad = True
                        break
                    if v == player:
                        stones += 1
                    else:
                        empties.append(i)
                if bad or stones < 3:
                    continue
                for i in empties:
                    res.add(sc[i])
    return res


def threat_move_candidates(board, player: int):
    """
    Клетки, ход в которые создаёт четвёрку или тройку.
    Надмножество four_move_candidates: окна с >=2 своими камнями.
    Живая тройка или нет — проверяется уже после хода в search_vct.
    """
    opponent = PLAYER_O if player == PLAYER_X else PLAYER_X
    res = set()
    for (didx, inv), ts in _collect_lines(board, player).items():
        lo, hi = min(ts) - MARGIN, max(ts) + MARGIN
        coords = [_coord(didx, t, inv) for t in range(lo, hi + 1)]
        vals = [board.get_cell(x, y) for (x, y) in coords]
        for a, b in _split_opponent(vals, opponent):
            sv, sc = vals[a:b], coords[a:b]
            n = len(sv)
            for s in range(n - WIN_LEN + 1):
                stones = 0
                empties = []
                bad = False
                for i in range(s, s + WIN_LEN):
                    v = sv[i]
                    if v == opponent:
                        bad = True
                        break
                    if v == player:
                        stones += 1
                    else:
                        empties.append(i)
                if bad or stones < 2:
                    continue
                for i in empties:
                    res.add(sc[i])
    return res


def window_potential(board, player: int) -> int:
    """
    Взвешенный потенциал: окна из 5 клеток без камней противника.
    Зажатая с обоих концов линия не даёт вклада — все её окна невалидны.
    """
    opponent = PLAYER_O if player == PLAYER_X else PLAYER_X
    W = {1: 1, 2: 12, 3: 60}
    total = 0
    for (didx, inv), ts in _collect_lines(board, player).items():
        lo, hi = min(ts) - MARGIN, max(ts) + MARGIN
        coords = [_coord(didx, t, inv) for t in range(lo, hi + 1)]
        vals = [board.get_cell(x, y) for (x, y) in coords]
        for a, b in _split_opponent(vals, opponent):
            sv = vals[a:b]
            n = len(sv)
            for s in range(n - WIN_LEN + 1):
                k = 0
                for i in range(s, s + WIN_LEN):
                    if sv[i] == player:
                        k += 1
                total += W.get(k, 0)
    return total