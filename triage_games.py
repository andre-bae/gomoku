"""
Триаж реальных партий: компактная выжимка для разбора ошибок силы.
Движок не нужен. Читает positions/game_*.json и печатает по каждой партии:
исход, число ходов, первый ход с «тактически проиграна», самый большой провал оценки,
и критические позиции ДО хода списком камней — чтобы сразу запускать движок.

Запуск:
  python triage_games.py                  -> все партии, top=2  -> triage.txt
  python triage_games.py --top 1          -> короче
  python triage_games.py --game positions/game_2026_11_24.json --top 3
"""
import argparse
import glob
import json

from review_game import parse_analysis

DIRS = ((1, 0), (0, 1), (1, 1), (1, -1))


def has_five(cells):
    s = set(cells)
    for (x, y) in s:
        for dx, dy in DIRS:
            if all((x + k * dx, y + k * dy) in s for k in range(1, 5)):
                return True
    return False


def fmt_cells(cells):
    return ",".join("(%d,%d)" % c for c in cells) or "-"


def analyze(path, top):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    moves = data["moves"]
    xs = [(m["x"], m["y"]) for m in moves if m["player"] == "X"]
    os_ = [(m["x"], m["y"]) for m in moves if m["player"] == "O"]
    result = ("победа X" if has_five(xs) else
              "победа O" if has_five(os_) else "без пятёрки")
    ai = []
    for m in moves:
        text = m.get("analysis") or ""
        if not text.strip():
            continue
        a = parse_analysis(text)
        ai.append({"n": m["n"], "p": m["player"], "xy": (m["x"], m["y"]),
                   "step": a["step"], "lost": a["lost"],
                   "ev": a["depths"][-1][1] if a["depths"] else None})
    first_lost = next((r["n"] for r in ai if r["lost"]), None)
    drops = []
    for i in range(1, len(ai)):
        a, b = ai[i - 1], ai[i]
        if a["p"] != b["p"] or a["ev"] is None or b["ev"] is None:
            continue
        d = a["ev"] - b["ev"]
        if d > 0:
            drops.append((d, b["n"]))
    drops.sort(reverse=True)
    name = path.replace("\\", "/").split("/")[-1]
    lines = ["%s: %d ходов, %s, ИИ-ходов=%d, первый проигрыш=%s, макс провал=%s"
             % (name, len(moves), result, len(ai),
                first_lost if first_lost else "-",
                ("%d на ходу %d" % drops[0]) if drops else "-")]
    picks = []
    if drops:
        picks.append(drops[0][1])
    if first_lost:
        prev = [r["n"] for r in ai if r["n"] < first_lost]
        if prev:
            picks.append(prev[-1])
    picks.extend(n for _, n in drops[1:])
    chosen = []
    for n in picks:
        if n not in chosen:
            chosen.append(n)
        if len(chosen) >= top:
            break
    for n in chosen:
        rec = next(r for r in ai if r["n"] == n)
        before = [m for m in moves if m["n"] < n]
        bx = [(m["x"], m["y"]) for m in before if m["player"] == "X"]
        bo = [(m["x"], m["y"]) for m in before if m["player"] == "O"]
        lines.append("  ход %d %s сыграл %s шаг=%s оценка=%s%s"
                     % (n, rec["p"], rec["xy"], rec["step"], rec["ev"],
                        " ПРОИГРАНА" if rec["lost"] else ""))
        lines.append("    до хода: X=%s | O=%s | ходит %s"
                     % (fmt_cells(bx), fmt_cells(bo), rec["p"]))
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=None)
    ap.add_argument("--top", type=int, default=2)
    args = ap.parse_args()
    paths = [args.game] if args.game else sorted(glob.glob("positions/game_*.json"))
    out = []
    for p in paths:
        try:
            block = analyze(p, args.top)
        except Exception as e:
            block = ["%s: ОШИБКА %r" % (p, e)]
        out.extend(block)
        print("\n".join(block), flush=True)
    with open("triage.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("Saved: triage.txt (%d строк)" % len(out))


if __name__ == "__main__":
    main()