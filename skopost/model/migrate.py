"""入力仕様の版の移行（ARCHITECTURE §2.3）。

- 読めるのは現行（v2）と 1 つ前（v1）。古い版は現行に上げてから検証する。
- 未来の版・未知の版は拒否（SkopostError → CLI では終了 1）。
- 入力は変更しない（新しい辞書を返す）。
"""
from __future__ import annotations

from typing import Any

from .constants import LATEST_SPEC_VERSION, SUPPORTED_SPEC_VERSIONS
from .errors import SkopostError


def spec_version_of(data: Any) -> int:
    """`skopost` 鍵の版を返す。無い・整数でない・範囲外は SkopostError。"""
    if not isinstance(data, dict):
        raise SkopostError("最上位は JSON オブジェクトが要ります", where="")
    v = data.get("skopost")
    if isinstance(v, bool) or not isinstance(v, int):
        raise SkopostError(f'"skopost" は版の整数（{", ".join(map(str, SUPPORTED_SPEC_VERSIONS))}）が要ります', where="/skopost")
    if v > LATEST_SPEC_VERSION:
        raise SkopostError(f'"skopost": {v} はこの版（最新 {LATEST_SPEC_VERSION}）より新しく読めません', where="/skopost")
    if v not in SUPPORTED_SPEC_VERSIONS:
        raise SkopostError(f'"skopost": {v} は古すぎて読めません（読めるのは {", ".join(map(str, SUPPORTED_SPEC_VERSIONS))}）', where="/skopost")
    return v


def _v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    # v2 は v1 に任意の鍵（tool.origin・observed.*.source・imports）を足しただけ。v1 の意味は変えない。
    out = dict(data)
    out["skopost"] = 2
    return out


_STEPS = {1: _v1_to_v2}


def migrate(data: Any) -> dict[str, Any]:
    """古い版の入力を現行版の形にした新しい辞書を返す。現行版ならそのまま（浅い複製）。"""
    v = spec_version_of(data)
    out: dict[str, Any] = dict(data)
    while v < LATEST_SPEC_VERSION:
        out = _STEPS[v](out)
        v += 1
    return out
