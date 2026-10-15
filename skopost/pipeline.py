"""通しの流れ（統合）：ingest → infer → graph → report。cli から呼ばれる配線の部品（計算は各層が持つ）。

- ``load_config``：宣言ファイルを読む。``adapter`` が None なら v1 と同じ検証器（model.validate.load_file）で読み、
  誤りの文言も v1 と同じ。``adapter`` を指定すると ingest（"auto" は自動判別）。
- ``apply_inferred``：取り込みの事実から infer の規則で札を推定し、観察の層に合成する（infer.combine：
  手書き > 取り込み > 規則）。宣言の層には足さない。設定に無い道具の事実は使わない。
  不明の集合の札（acts など）は推定で狭めない（道が減るため）。結果として、推定で道が減ることは無い
  （tests/test_integration.InferNeverRemovesPaths）。
- ``run``：読む → 推定 → 解析（graph.analyze＝方針 v1）→ （基準線があれば差分）。

既存の ``check``（md・json・基準線なし・取り込みなし）は cli が compat.v1 を使い続ける（バイト互換）。
新しい流れが同じ出力になることは tests/test_integration.py が確かめる（切り替えはしていない）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .ci.api import diff as _diff
from .ci.api import load_baseline
from .graph.api import analyze
from .infer.api import combine, infer_caps
from .infer.rules import DEFAULT_RULES
from .ingest.api import ADAPTERS, ingest
from .model.constants import ALL_CAPS
from .model.convert import from_legacy
from .model.types import AnalysisResult, BaselineDiff, Config, Fact, IngestNote, Tool
from .model.validate import load_file
from .report.api import render

ADAPTER_CHOICES: tuple[str, ...] = ("auto",) + tuple(sorted(ADAPTERS))


@dataclass(frozen=True)
class Outcome:
    cfg: Config
    result: AnalysisResult
    notes: tuple[IngestNote, ...] = ()
    baseline_diff: Optional[BaselineDiff] = None

    @property
    def exit_code(self) -> int:
        """既存と同じ：0＝道なし／2＝道あり。基準線があるときは「新しく増えた道」があれば 2。"""
        if self.baseline_diff is not None:
            return 2 if self.baseline_diff.regressed else 0
        return self.result.exit_code


def load_config(path: str, adapter: Optional[str] = None) -> tuple[Config, tuple[Fact, ...], tuple[IngestNote, ...]]:
    if adapter is None:
        return from_legacy(load_file(path)), (), ()
    res = ingest(path, adapter=None if adapter == "auto" else adapter)
    return res.config, tuple(res.facts), tuple(res.notes)


def apply_inferred(cfg: Config, facts, rules=DEFAULT_RULES) -> Config:
    ids = {t.id for t in cfg.tools}
    stores = {s.id for s in cfg.stores}
    inferred = infer_caps([f for f in facts if f.tool_id in ids], rules)
    if not inferred:
        return cfg
    tools: list[Tool] = []
    for t in cfg.tools:
        add = inferred.get(t.id)
        if not add:
            tools.append(t)
            continue
        obs = dict(t.observed.items())
        for name in ALL_CAPS:
            c = add.get(name)
            if c is None:
                continue
            if name not in obs and name in ("acts", "writes_stores", "reads_stores"):
                # 不明の集合の札（acts＝全種）を規則の推定で狭めると道が減る（不明を危ない側に倒す約束 F1 に反する）。
                # 不明のまま残す。真偽の札は推定が真なので値は変わらず、確度と根拠だけが付く。
                continue
            if name in ("writes_stores", "reads_stores") and not (c.value is None or set(c.value) <= stores):
                continue  # 設定に無い置き場を指す推定は使わない
            obs[name] = combine(obs[name], c) if name in obs else c
        tools.append(Tool(id=t.id, label=t.label, mode=t.mode, frequency=t.frequency, declared=t.declared,
                          observed=obs, origin=t.origin))
    return Config(name=cfg.name, untrusted_in_context=cfg.untrusted_in_context, tools=tuple(tools),
                  stores=cfg.stores, imports=cfg.imports, spec=cfg.spec)


def run(path: str, *, adapter: Optional[str] = None, baseline: Optional[str] = None) -> Outcome:
    cfg, facts, notes = load_config(path, adapter)
    cfg = apply_inferred(cfg, facts)
    res = analyze(cfg)
    bd = _diff(load_baseline(baseline), res) if baseline else None
    return Outcome(cfg, res, notes, bd)


def render_outcome(o: Outcome, fmt: str, *, explain: bool = False) -> str:
    return render(o.result, o.cfg, fmt, explain=explain)  # type: ignore[arg-type]


__all__ = ["ADAPTER_CHOICES", "Outcome", "apply_inferred", "load_config", "render_outcome", "run"]
