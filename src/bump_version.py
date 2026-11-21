"""发布新版本：按规则算出下一个版本号，写入 VERSION，并在 docs/RELEASE_NOTES.md 插入新版本标题。

版本号规则：1.{年份后两位}.{月份}.{当月序号}
  - 当月第一个版本序号为 0，之后每次 +1；进入新的月份后从 0 重新开始。
  - 例：1.26.11.0 → 1.26.11.1；到 2026 年 12 月 → 1.26.12.0

用法：
  .venv\\Scripts\\python.exe src\\bump_version.py            # 发布下一个版本
  .venv\\Scripts\\python.exe src\\bump_version.py --dry-run  # 只显示下一个版本号，不改文件
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"
NOTES_FILE = ROOT / "docs" / "RELEASE_NOTES.md"
MAJOR = 1
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)\.(\d+)$")


def next_version(current: str | None, today: date) -> str:
    yy, mm = today.year % 100, today.month
    if current and (m := VERSION_RE.match(current.strip())):
        major, y, mo, n = map(int, m.groups())
        if (major, y, mo) == (MAJOR, yy, mm):
            return f"{MAJOR}.{yy}.{mm}.{n + 1}"
    return f"{MAJOR}.{yy}.{mm}.0"


def main() -> None:
    today = date.today()
    current = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.exists() else None
    new = next_version(current, today)
    print(f"当前版本：{current or '（无）'}  →  新版本：{new}")
    if "--dry-run" in sys.argv:
        return

    VERSION_FILE.write_text(new + "\n", encoding="utf-8")

    # 在第一个版本标题（"## 1."）之前插入新版本的标题和待填写的条目
    notes = NOTES_FILE.read_text(encoding="utf-8") if NOTES_FILE.exists() else "# 更新日志 Release Notes\n\n"
    entry = f"## {new} — {today.isoformat()}\n\n- （在这里填写本次更新内容）\n\n"
    m = re.search(r"^## \d+\.", notes, re.M)
    notes = notes[:m.start()] + entry + notes[m.start():] if m else notes.rstrip() + "\n\n" + entry
    NOTES_FILE.write_text(notes, encoding="utf-8")
    print(f"已更新 {VERSION_FILE.name} 和 {NOTES_FILE.relative_to(ROOT)}，请补充更新内容。")


if __name__ == "__main__":
    main()
