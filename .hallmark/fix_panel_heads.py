"""Strip the literal quotes the panel rewrite left in panel heads.

The rewrite copied the include attributes straight into the markup, so a
literal string arrived as "Dishes" rather than Dishes. This removes the
quotes around literal values and wraps bare names back into variables.
"""

import re
from pathlib import Path

ROOT = Path(r"D:\Haswanth\college\assignments\MessForecast\templates\console")

HEAD = re.compile(r'(<h2>)(?:"([^"]*)"|([a-z_][a-z0-9_]*))(</h2>)')
HINT = re.compile(r'(<span class="hint">)(?:"([^"]*)"|([a-z_][a-z0-9_]*))(</span>)')


def fix_head(match: re.Match) -> str:
    literal, variable = match.group(2), match.group(3)
    value = literal if literal is not None else "{{ %s }}" % variable
    return f"{match.group(1)}{value}{match.group(4)}"


def main() -> int:
    changed = 0
    for path in sorted(ROOT.glob("*.html")):
        source = path.read_text(encoding="utf-8")
        fixed = HEAD.sub(fix_head, source)
        fixed = HINT.sub(fix_head, fixed)
        if fixed != source:
            path.write_text(fixed, encoding="utf-8")
            print("fixed", path.name)
            changed += 1
    print(f"{changed} file(s) fixed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
