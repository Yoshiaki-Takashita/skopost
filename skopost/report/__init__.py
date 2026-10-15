"""report：AnalysisResult → text / JSON / SARIF / Markdown（担当 E・段 2）。依存は model と graph だけ。"""
from __future__ import annotations

from .api import FORMATS, RULE_IDS, render, to_json, to_sarif

__all__ = ["FORMATS", "RULE_IDS", "render", "to_json", "to_sarif"]
