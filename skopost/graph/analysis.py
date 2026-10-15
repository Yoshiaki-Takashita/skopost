"""解析の全体（v1 の analyze と同じ意味）と、その部品のうち graph が自前で持つもの。

- ``mismatches``：宣言と観察の食い違い。統合で infer.mismatches に寄せた。段 2 の自前の計算は
  ``_mismatches_local`` として残し、infer と一致することを試験で確かめる（tests/test_graph_paths.py）。
- ``analyze``：道・関所・宣言だけの地図・仮定・食い違い・走らせなかった検査を 1 つの AnalysisResult に。
"""
from __future__ import annotations

import time

from ..infer import api as _infer

from ..model.constants import ALL_CAPS, BOOL_CAPS, EXACT_LIMIT
from ..model.frozen import FrozenMap
from ..model.types import (AnalysisResult, Assumed, Checkpoints, Config, DeclaredOnly, HarmPath, Mismatch,
                           Summary, Tool)
from .caps import DEFAULT_POLICY, Policy, assumed_order
from .hitting import make_instance, solve
from .paths import harm_paths_policy

NOT_CHECKED_BASE: tuple[str, ...] = (
    "人の確認の素通し（ask にした道具を人が実際に止めるか）は測っていない",
    "文脈の中の値の流れは追っていない（文脈は 1 つの汚れうる場所として丸めた）",
    "札の正しさは確かめていない（札は入力。確度と根拠を見て判断すること）",
)


def mismatches(cfg: Config) -> list[Mismatch]:
    """infer.mismatches に寄せた（統合）。自前の計算は ``_mismatches_local`` として一致試験に残す。"""
    return _infer.mismatches(cfg)


def _mismatches_local(cfg: Config) -> list[Mismatch]:
    out: list[Mismatch] = []
    for t in cfg.tools:
        for cap in ALL_CAPS:
            ob = t.observed.get(cap)
            if ob is None or ob.unknown:
                continue
            dc = t.declared.get(cap)
            dv = dc.value if dc is not None else (False if cap in BOOL_CAPS else frozenset())
            ov = ob.value
            if dv == ov:
                continue
            if cap in BOOL_CAPS:
                sev = "under" if ov and not dv else "over"
            else:
                sev = "under" if (ov - dv) else "over"  # type: ignore[operator]
            out.append(Mismatch(t.id, cap, dv, ov, ob.confidence, ob.evidence, sev))  # type: ignore[arg-type]
    return out


def assumed_unknown(cfg: Config, policy: Policy = DEFAULT_POLICY) -> list[Assumed]:
    if policy == "v1":
        return _infer.assumed_unknown(cfg)
    return _assumed_unknown_local(cfg, policy)


def _assumed_unknown_local(cfg: Config, policy: Policy = DEFAULT_POLICY) -> list[Assumed]:
    stores = cfg.store_map()
    return [Assumed(t.id, cap) for t in cfg.allowed() for cap in assumed_order(t, stores, policy)]


def checkpoints_for(cfg: Config, paths: list[HarmPath], *, exact_limit: int = EXACT_LIMIT, max_alternatives: int = 5,
                    time_budget_s: float = 5.0) -> tuple[Checkpoints, dict[str, object]]:
    ids = [t.id for t in cfg.allowed()]
    freq = [t.frequency for t in cfg.allowed()]
    inst = make_instance(ids, freq, [p.tool_set for p in paths])
    return solve(inst, exact_limit=exact_limit, max_alternatives=max_alternatives, time_budget_s=time_budget_s)


def apply_cut(cfg: Config, cut: frozenset) -> Config:
    tools = tuple(Tool(t.id, t.label, "ask", t.frequency, t.declared, t.observed, t.origin) if t.id in cut else t
                  for t in cfg.tools)
    return Config(cfg.name, cfg.untrusted_in_context, tools, cfg.stores, cfg.imports, cfg.spec)


def reasons_for(paths: list[HarmPath], cp: Checkpoints) -> dict[str, list[str]]:
    return {tid: [f"{p.kind}: {p.key}" for p in paths if tid in p.tools] for tid in cp.primary}


def analyze(cfg: Config, policy: Policy = DEFAULT_POLICY, *, exact_limit: int = EXACT_LIMIT,
            time_budget_s: float = 5.0) -> AnalysisResult:
    t0 = time.perf_counter()
    actual = harm_paths_policy(cfg, "observed", policy)
    declared = harm_paths_policy(cfg, "declared", policy)
    cp, notes = checkpoints_for(cfg, actual, exact_limit=exact_limit, time_budget_s=time_budget_s)
    reasons = reasons_for(actual, cp)
    d_cp, _ = checkpoints_for(cfg, declared, exact_limit=exact_limit, time_budget_s=time_budget_s)
    surviving = harm_paths_policy(apply_cut(cfg, frozenset(d_cp.primary)), "observed", policy)
    assumed = assumed_unknown(cfg, policy)
    mm = mismatches(cfg)
    dkeys = {p.key for p in declared}
    missed = [p for p in actual if p.key not in dkeys]
    not_checked = list(NOT_CHECKED_BASE)
    if not cfg.untrusted_in_context:
        not_checked.append("untrusted_in_context=false のため道を数えていない（外の文を一切読まない構成だけが使える設定）")
    if not cp.exact:
        not_checked.append(f"道具が {exact_limit} 個を超えるため関所は近似（貪欲法）。最小でない可能性がある")
    if not notes.get("enum_complete", True):
        not_checked.append("同じ大きさの関所の案が多すぎて列挙を打ち切った（第一案は厳密。代替案は一部）")
    if policy != "v1":
        not_checked.append(f"危険経路の方針 {policy}（置き場の札が不明なら全置き場に倒す）。v1 の報告と道の数が違いうる")
    seconds = round(time.perf_counter() - t0, 4)
    summary = Summary(tools=len(cfg.tools), allowed=len(cfg.allowed()), paths=len(actual),
                      paths_declared_only=len(declared), missed_by_declared=len(missed), mismatches=len(mm),
                      assumed_unknown=len(assumed), seconds=seconds)
    return AnalysisResult(name=cfg.name, summary=summary, paths=tuple(actual), mismatches=tuple(mm),
                          assumed=tuple(assumed), checkpoints=cp,
                          reasons=FrozenMap({k: tuple(v) for k, v in reasons.items()}),
                          declared_only=DeclaredOnly(tuple(d_cp.primary), tuple(p.key for p in surviving)),
                          not_checked=tuple(not_checked))


__all__ = ["mismatches", "assumed_unknown", "checkpoints_for", "apply_cut", "reasons_for", "analyze", "NOT_CHECKED_BASE"]
