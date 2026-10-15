"""native アダプタ：skopost 自身の宣言ファイル（SPEC v1・v2）。

出典：projects/skopost/SPEC.md と ARCHITECTURE §2.2（本リポジトリ内の一次資料）。確認日：2026-10-13
読み込みは model.parse に任せる（検証の規則は 1 か所だけ）。札は手書き（manual）のまま。
"""
from __future__ import annotations

from typing import ClassVar

from ..model.parse import parse
from ..model.types import IngestResult


class NativeAdapter:
    name: ClassVar[str] = "native"

    def sniff(self, data: object, filename: str) -> float:
        try:
            if isinstance(data, dict):
                v = data.get("skopost")
                if isinstance(v, int) and not isinstance(v, bool) and v in (1, 2):
                    return 0.95
        except Exception:  # noqa: BLE001
            return 0.0
        return 0.0

    def read(self, data: object, *, filename: str) -> IngestResult:
        return IngestResult(config=parse(data))
