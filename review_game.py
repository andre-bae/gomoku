"""
Компактный разбор сохранённой партии — вместо загрузки большого JSON в чат.
Читает анализы, УЖЕ записанные кнопкой «Сохранить S», ничего не пересчитывает.

Запуск:
    python review_game.py positions/my_game.json            -> review.txt (выжимка)
    python review_game.py positions/my_game.json --move 14  -> move14.txt (полный анализ хода)
"""
import json
import re
import sys


def parse_analysis(text):
    lines = text.splitlines()
    step, depths, panic, lost = "?", [], False, False
    prev_t, gap, gap_line = 0.0, 0.0, ""
    for ln in lines:
        s = ln.strip()
        m = re.search(r"\(t=([0-9.]+)\)", s)
        if m:
            t = float(m.group(1))
            if t - prev_t > gap:
                gap, gap_line = t - prev_t, s
            prev_t = t
        if s.startswith("[ШАГ") or s.startswith("[РЕЖИМ"):
            step = s.split("]")[0].lstrip("[")
        if s.startswith("глубина "):
            d = re.match(r"глубина (\d+)", s)
            v = re.search(r"оценка (-?\d+)", s)
            if d and v:
                depths.append((int(d.group(1)), int(v.group(1))))
        if "время хода исчерпано" in s:
            panic = True
        if "тактически проиграна" in s:
            lost = True
    return {"step": step, "depths": depths, "panic": panic, "lost": lost,
            "gap": gap, "gap_line": gap_line}


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "positions/bench_game_1.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    moves = data["moves"]

    if "--move" in sys.argv:
        n = int(sys.argv[sys.argv.index("--move") + 1])
        rec = next((m for m in moves if m["n"] == n), None)
        if rec is None:
            print("No move %d" % n)
            return
        out = "move%d.txt" % n
        with open(out, "w", encoding="utf-8") as f:
            f.write("ход %d: %s (%s,%s)\n\n" % (n, rec["player"], rec["x"], rec["y"]))
            f.write(rec.get("analysis") or "(анализа в файле нет)")
        print("Saved: %s" % out)
        return

    out = ["партия: %s" % path, "ходов: %d" % len(moves), ""]
    times, panics, losts, steps = [], 0, 0, {}
    for m in moves:
        head = "%2d %s (%s,%s)" % (m["n"], m["player"], m["x"], m["y"])
        el = m.get("elapsed")
        if el is not None:
            head += "  %.2f с" % el
            times.append(el)
        text = m.get("analysis") or ""
        if not text.strip():
            out.append(head + "  — анализа в файле нет (ход человека)")
            continue
        a = parse_analysis(text)
        flags = []
        if a["panic"]:
            flags.append("АВАРИЯ"); panics += 1
        if a["lost"]:
            flags.append("проиграна тактически"); losts += 1
        steps[a["step"]] = steps.get(a["step"], 0) + 1
        out.append(head + "  решил=" + a["step"]
                   + ("  [" + ", ".join(flags) + "]" if flags else ""))
        if a["depths"]:
            out.append("     оценки: " + ", ".join("d%d=%d" % ds for ds in a["depths"]))
        if a["gap"] >= 0.2:
            out.append("     %.2f с ушло на: %s" % (a["gap"], a["gap_line"][:110]))
    out.append("")
    out.append("ИТОГО: ходов ИИ с анализом=%d, аварий=%d, тактически проиграно=%d"
               % (sum(steps.values()), panics, losts))
    if times:
        out.append("время: среднее %.2f с, максимум %.2f с" %
                   (sum(times) / len(times), max(times)))
    out.append("чем решались ходы: "
               + ", ".join("%s=%d" % kv for kv in sorted(steps.items())))
    with open("review.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("Saved: review.txt")


if __name__ == "__main__":
    main()