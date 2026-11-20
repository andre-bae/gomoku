"""
Прогоняет тесты и сохраняет вывод в UTF-8 файл.
Обходит проблемы кодировок Windows: файл пишет сам Python, а не оболочка.

Запуск:
    python run_tests_to_file.py                     -> baseline_tests.txt
    python run_tests_to_file.py after_step2.txt     -> after_step2.txt
    python run_tests_to_file.py out.txt Zobrist     -> только тесты с "Zobrist" в названии
"""
import contextlib
import io
import re
import sys


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "baseline_tests.txt"
    only = sys.argv[2] if len(sys.argv) > 2 else None

    print("Running tests, please wait (can take several minutes)...", flush=True)

    buf = io.StringIO()
    code = 2
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            import gomoku_tests
            code = gomoku_tests.run_tests(only=only)
        except SystemExit as exc:
            code = int(exc.code or 0)
        except BaseException:
            import traceback
            traceback.print_exc()
            code = 2

    text = buf.getvalue()
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    print("OK: saved %s (%d lines), exit=%d" % (out, len(text.splitlines()), code))
    m = re.search(r"PASS=(\d+)\s+FAIL=(\d+)", text)
    if m:
        print("PASS=%s  FAIL=%s" % (m.group(1), m.group(2)))
    else:
        print("No summary line found - open the file and look at the end.")
    return code


if __name__ == "__main__":
    sys.exit(main())