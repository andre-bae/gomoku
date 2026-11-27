"""Диагностика хода 4 без обреза бюджета: порядок, статика, поиск, обрывы."""
import gomoku as G
from gomoku import Board, PLAYER_X, PLAYER_O, minimax, evaluate_position

X, O = PLAYER_X, PLAYER_O


def build(xs, os_):
    b = Board()
    for i in range(max(len(xs), len(os_))):
        if i < len(xs):
            b.make_move(xs[i][0], xs[i][1], X)
        if i < len(os_):
            b.make_move(os_[i][0], os_[i][1], O)
    return b


def probe(xs, os_, side, depth, budget_nodes, top):
    b = build(xs, os_)
    cands = b.get_candidate_moves(radius=2)
    ordered = G._order_moves(b, side, cands)
    print("кандидатов=%d, глубина=%d, бюджет=%d, показываем top=%d"
          % (len(cands), depth, budget_nodes, top), flush=True)
    rows = []
    for (x, y), s in ordered[:top]:
        near_x = any(abs(x - a) <= 1 and abs(y - c) <= 1 for a, c in xs)
        near_o = any(abs(x - a) <= 1 and abs(y - c) <= 1 for a, c in os_)
        kind = "мешает+своё" if (near_x and near_o) else ("мешает X" if near_x else "своё")
        G._TRUNCATED[0] = 0
        b.make_move(x, y, side)
        stat = evaluate_position(b, side, to_move=(O if side == X else X))
        v = minimax(b, depth=depth, alpha=-10**9, beta=10**9,
                    is_maximizing=(side == X), player=side,
                    budget=[budget_nodes], tt={})
        b.undo_move()
        rows.append((v, x, y, s, stat, kind, G._TRUNCATED[0]))
    for v, x, y, s, stat, kind, tr in rows:
        print("  (%2d,%2d) порядок=%5d статика=%7d поиск=%8d обрывов=%d  %s"
              % (x, y, s, stat, v, tr, kind), flush=True)
    best = max(rows, key=lambda r: r[0])
    print("лучший по поиску: (%d,%d) = %d" % (best[1], best[2], best[0]), flush=True)
    print("всего обрывов: %d" % sum(r[6] for r in rows), flush=True)


if __name__ == "__main__":
    for flag in (False, True):
        G.USE_CONTEST_EVAL = flag
        print("=== ход 4, USE_CONTEST_EVAL=%s ===" % flag, flush=True)
        probe([(0, 0), (1, 1)], [(-2, 1)], O, depth=4, budget_nodes=40000, top=16)
    G.USE_CONTEST_EVAL = False