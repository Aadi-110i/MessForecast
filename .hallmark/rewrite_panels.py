"""One-off: rewrite {% include "components/panel.html" %}...{% endinclude %}
into the codebase's native panel markup.

Django has no {% endinclude %}, so a wrapping component cannot capture the
caller's body. The house pattern in this project is a plain <section
class="panel"> with a panelhead, so the console screens are rewritten to it
and the partial is kept for the cases where a body is a reusable template.
"""

import re
import sys
from pathlib import Path

PATTERN = re.compile(
    r'\{%\s*include\s+"components/panel\.html"\s+with\s+(?P<attrs>[^%]*?)%\}'
    r'(?P<body>.*?)'
    r'\{%\s*endinclude\s*%\}',
    re.DOTALL,
)


def split_attrs(attrs: str) -> tuple[str, str]:
    """Split 'title=X hint=Y' into the two values."""
    title = ""
    hint = ""
    if "hint=" in attrs:
        title_part, _, hint_part = attrs.partition("hint=")
        title = title_part.replace("title=", "").strip()
        hint = hint_part.strip()
    elif "title=" in attrs:
        title = attrs.replace("title=", "").strip()
    return title, hint


def rewrite(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")

    def replace(match: re.Match) -> str:
        title, hint = split_attrs(match.group("attrs"))
        body = match.group("body")
        # Strip the common leading indentation of the body so the rewritten
        # block keeps the shape of the original file.
        lines = [line for line in body.split("\n")]
        while lines and not lines[0].strip():
            lines.pop(0)
        indent = ""
        if lines:
            stripped = lines[0][: len(lines[0]) - len(lines[0].lstrip())]
            indent = stripped
        body = "\n".join(line[len(indent):] if line.startswith(indent) else line for line in lines)
        body = body.rstrip()

        head = [f'<section class="panel">']
        head.append('  <div class="panelhead">')
        if title:
            head.append(f"    <h2>{title}</h2>")
        if hint:
            head.append(f'    <span class="hint">{hint}</span>')
        head.append("  </div>")
        return "\n".join(head) + "\n" + body + "\n</section>"

    rewritten = PATTERN.sub(replace, source)
    if rewritten != source:
        path.write_text(rewritten, encoding="utf-8")
        return True
    return False


def main() -> int:
    changed = 0
    for arg in sys.argv[1:]:
        path = Path(arg)
        if rewrite(path):
            print(f"rewritten {path.name}")
            changed += 1
        else:
            print(f"unchanged {path.name}")
    print(f"{changed} file(s) changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
