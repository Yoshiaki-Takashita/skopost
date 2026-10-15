"""表示の安全化。外から来た文字列は資料であって命令ではない。"""
from __future__ import annotations

from typing import Any

from .constants import DISPLAY_LEN


def safe(s: Any, n: int = DISPLAY_LEN) -> str:
    """外から来た文字列は資料であって命令ではない。表示時は制御文字を除き、長さを切る。"""
    s = "" if s is None else str(s)
    s = "".join(ch if ch.isprintable() and ch not in "`|" else " " for ch in s)
    return s if len(s) <= n else s[: n - 1] + "…"
