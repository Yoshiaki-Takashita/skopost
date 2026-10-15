"""ci：基準線の比較と CI 雛形（担当 E・段 2）。依存は model と report だけ。"""
from __future__ import annotations

from .api import baseline_from_result, diff, load_baseline, parse_baseline, write_baseline

__all__ = ["baseline_from_result", "diff", "load_baseline", "parse_baseline", "write_baseline"]
