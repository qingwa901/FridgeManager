"""发布新版本：按规则算出下一个版本号，写入 VERSION，并在 docs/RELEASE_NOTES.md 插入新版本标题。

版本号规则：1.{年份后两位}.{月份}.{当月序号}
  - 当月第一个版本序号为 0，之后每次 +1；进入新的月份后从 0 重新开始。
  - 例：1.26.11.0 → 1.26.11.1；到 2026 年 12 月 → 1.26.12.0

用法（在 src 目录下）：
  python -m function.version_bumper            # 发布下一个版本
  python -m function.version_bumper --dry-run  # 只显示下一个版本号，不改文件
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path


class VersionBumper:
    MAJOR = 1
    VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)\.(\d+)$")

    def __init__(self, root: Path):
        self.root = root
        self.version_file = root / "VERSION"
        self.notes_file = root / "docs" / "RELEASE_NOTES.md"

    @classmethod
    def next_version(cls, current: str | None, today: date) -> str:
        yy, mm = today.year % 100, today.month
        if current and (m := cls.VERSION_RE.match(current.strip())):
            major, y, mo, n = map(int, m.groups())
            if (major, y, mo) == (cls.MAJOR, yy, mm):
                return f"{cls.MAJOR}.{yy}.{mm}.{n + 1}"
        return f"{cls.MAJOR}.{yy}.{mm}.0"

    def bump(self, dry_run: bool = False) -> str:
        today = date.today()
        current = self.version_file.read_text(encoding="utf-8").strip() if self.version_file.exists() else None
        new = self.next_version(current, today)
        print(f"当前版本：{current or '（无）'}  →  新版本：{new}")
        if dry_run:
            return new

        self.version_file.write_text(new + "\n", encoding="utf-8")
        # 在第一个版本标题（"## 1."）之前插入新版本的标题和待填写的条目
        notes = (self.notes_file.read_text(encoding="utf-8") if self.notes_file.exists()
                 else "# 更新日志 Release Notes\n\n")
        entry = f"## {new} — {today.isoformat()}\n\n- （在这里填写本次更新内容）\n\n"
        m = re.search(r"^## \d+\.", notes, re.M)
        notes = notes[:m.start()] + entry + notes[m.start():] if m else notes.rstrip() + "\n\n" + entry
        self.notes_file.write_text(notes, encoding="utf-8")
        print(f"已更新 {self.version_file.name} 和 {self.notes_file.relative_to(self.root)}，请补充更新内容。")
        return new


if __name__ == "__main__":
    VersionBumper(Path(__file__).resolve().parents[2]).bump(dry_run="--dry-run" in sys.argv)
