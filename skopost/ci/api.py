"""ci の公開面。担当 E（段 2）。基準線との差分（新しく増えた道だけで失敗させる）。

契約（tests/test_contract_ci.py）：
- 道は (kind, key) で同一視。道の順序・並べ替えに結果は依らない（C1）
- write_baseline は文字列を返すだけ（書くのは cli）。load_baseline(書いた内容) で同じ Baseline に戻る
- この木の CI を有効化・push で起動することはしない（雛形を置くだけ）。雛形の外部 action は SHA 固定（C2）
"""
from __future__ import annotations

import json

from ..model.constants import MAX_FILE_BYTES, PATH_KINDS
from ..model.errors import SkopostError
from ..model.types import AnalysisResult, Baseline, BaselineDiff

OWNER = "E：出力・CI"
BASELINE_KEY = "skopost_baseline"
BASELINE_VERSION = 1


def baseline_from_result(res: AnalysisResult) -> Baseline:
    return Baseline(frozenset((p.kind, p.key) for p in res.paths))


def parse_baseline(text: str) -> Baseline:
    """基準線の文字列 → Baseline。形が違えば SkopostError（入力の誤り）。"""
    try:
        d = json.loads(text)
    except ValueError as e:
        raise SkopostError(f"基準線が JSON として読めません：{e.msg}") from None
    if not isinstance(d, dict) or d.get(BASELINE_KEY) != BASELINE_VERSION or type(d.get(BASELINE_KEY)) is not int:
        raise SkopostError(f"基準線の版が違います（\"{BASELINE_KEY}\": {BASELINE_VERSION} が必要）", where="/" + BASELINE_KEY)
    paths = d.get("paths")
    if not isinstance(paths, list):
        raise SkopostError("基準線の paths は配列", where="/paths")
    entries = set()
    for i, e in enumerate(paths):
        if not (isinstance(e, list) and len(e) == 2 and e[0] in PATH_KINDS and isinstance(e[1], str) and e[1]):
            raise SkopostError("基準線の paths の要素は [kind, key]", where=f"/paths/{i}")
        entries.add((e[0], e[1]))
    return Baseline(frozenset(entries))


def load_baseline(path: str) -> Baseline:
    try:
        with open(path, "rb") as f:
            raw = f.read(MAX_FILE_BYTES + 1)
    except OSError as e:
        raise SkopostError(f"基準線を開けません：{e.strerror}") from None
    if len(raw) > MAX_FILE_BYTES:
        raise SkopostError("基準線が大きすぎます")
    try:
        return parse_baseline(raw.decode("utf-8-sig"))
    except UnicodeDecodeError:
        raise SkopostError("基準線が UTF-8 ではありません") from None


def diff(prev: Baseline, cur: AnalysisResult) -> BaselineDiff:
    c = baseline_from_result(cur).entries
    p = prev.entries
    return BaselineDiff(tuple(sorted(c - p)), tuple(sorted(p - c)), tuple(sorted(c & p)))


def write_baseline(res: AnalysisResult) -> str:
    entries = sorted(baseline_from_result(res).entries)
    return json.dumps({BASELINE_KEY: BASELINE_VERSION, "paths": [list(e) for e in entries]},
                      ensure_ascii=False, indent=2) + "\n"
