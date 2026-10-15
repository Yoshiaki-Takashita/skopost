"""ingest：外の設定形式 → Config の下書き（担当 B・段 2）。依存は model と infer.rules だけ。"""
from __future__ import annotations

from .api import ADAPTERS, MIN_CONFIDENCE, Adapter, detect, ingest, merge

__all__ = ["ADAPTERS", "MIN_CONFIDENCE", "Adapter", "detect", "ingest", "merge"]
