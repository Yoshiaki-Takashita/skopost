"""graph の公開面（担当 D・段 2）。署名は契約（tests/test_contract_signatures.py）で固定。中身は

- caps.py     ：実効の札と「不明」の倒し方（方針 v1／monotone）
- paths.py    ：危ない道の列挙
- hitting.py  ：最小ヒッティングセット（強制 → 二部なら最大流 → 分枝限定 → 列挙／貪欲）
- analysis.py ：解析の全体

既定の方針は "v1"（compat.v1 と同じ道・同じ順序・同じ第一案）。単調性を守る方針 "monotone" は
``harm_paths_policy``／``analyze_policy``（graph パッケージの公開）から使う。説明は docs/GRAPH.md。
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from ..model.constants import MAX_ALTERNATIVES
from ..model.types import AnalysisResult, Checkpoints, Config, HarmPath, Layer
from . import analysis as _A
from .caps import DEFAULT_POLICY
from .paths import harm_paths_policy

OWNER = "D：グラフ"


def harm_paths(cfg: Config, layer: Layer) -> list[HarmPath]:
    """危ない道の列挙（SPEC §7）。untrusted_in_context=false なら空。allow の道具だけを見る。"""
    return harm_paths_policy(cfg, layer, DEFAULT_POLICY)


def min_checkpoints(cfg: Config, paths: Sequence[HarmPath], *, exact_limit: int = 20,
                    max_alternatives: int = MAX_ALTERNATIVES, time_budget_s: float = 5.0) -> Checkpoints:
    """道を全部断つ allow→ask の最小集合。厳密に最小と示せないときは exact=False と下界を返す（原則 4）。
    同じ大きさの案は frequency 合計の小さい順（同点は id の並び順）。"""
    cp, _notes = _A.checkpoints_for(cfg, list(paths), exact_limit=exact_limit, max_alternatives=max_alternatives,
                                    time_budget_s=time_budget_s)
    return cp


def apply_checkpoints(cfg: Config, cut: Iterable[str]) -> Config:
    """cut の道具を mode=ask にした新しい Config（締める方向だけ。入力は変えない）。"""
    return _A.apply_cut(cfg, frozenset(cut))


def explain(cfg: Config, paths: Sequence[HarmPath], cp: Checkpoints) -> dict[str, list[str]]:
    """関所ごとに断つ道（"<kind>: <key>"）。v1 の checkpoints.reasons と同じ。"""
    return _A.reasons_for(list(paths), cp)


def analyze(cfg: Config) -> AnalysisResult:
    """解析の全体（v1 の analyze と同じ意味）。infer と graph の部品を組むだけ。"""
    return _A.analyze(cfg, DEFAULT_POLICY)
