from __future__ import annotations

import re


class TextParser:
    """菜谱文本的通用解析：用时、"名称 用量"。"""

    AMOUNT_RE = re.compile(r"^[\d.\/½¼¾一二三四五六七八九十半几]+\s*\S{0,3}$|^(适量|少许|若干|少量|一点|按口味)$")

    @staticmethod
    def parse_minutes(text) -> int | None:
        """'70分钟' / '1小时30分钟' / 'PT1H10M' / 45 → 分钟数。"""
        if text is None:
            return None
        if isinstance(text, (int, float)):
            return int(text)
        s = str(text)
        m = re.fullmatch(r"P(?:T)?(?:(\d+)H)?(?:(\d+)M)?(?:\d+S)?", s.strip(), re.I)  # ISO 8601
        if m and (m.group(1) or m.group(2)):
            return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
        h = re.search(r"(\d+(?:\.\d+)?)\s*(?:小时|h|hour)", s, re.I)
        mi = re.search(r"(\d+)\s*(?:分钟|分|min)", s, re.I)
        if h or mi:
            return round(float(h.group(1)) * 60 if h else 0) + (int(mi.group(1)) if mi else 0)
        m = re.search(r"\d+", s)
        return int(m.group()) if m else None

    @classmethod
    def split_amount(cls, text: str) -> tuple[str, str]:
        """'老母鸡 1只' / '1只 老母鸡' / '盐 适量' → (名称, 用量)。分不开时用量为空。"""
        parts = text.strip().split()
        if len(parts) >= 2:
            if cls.AMOUNT_RE.match(parts[-1]):
                return " ".join(parts[:-1]), parts[-1]
            if cls.AMOUNT_RE.match(parts[0]):
                return " ".join(parts[1:]), parts[0]
        return text.strip(), ""
