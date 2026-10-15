"""型（model.types）と旧 API の辞書・JSON の相互変換。計算はしない。

- `from_legacy(d)`：`model.validate.validate()` の返す辞書 → Config
- `to_legacy(cfg)`：Config → `validate()` と同じ形の辞書（compat.v1 の関数に渡せる）
- `to_dict(cfg, spec=2)`：Config → 入力ファイルの JSON（`model.parse.parse` で読み戻すと同値：M2）
- `result_from_legacy(r)` / `result_to_dict(res)`：解析結果（SPEC §10 の JSON）との往復
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional

from .constants import BOOL_CAPS, RESULT_VERSION, SPEC_VERSION
from .frozen import FrozenMap
from .types import (AnalysisResult, Assumed, Cap, Checkpoints, Config, DeclaredOnly, HarmPath, ImportRecord,
                    Mismatch, Origin, Store, Summary, Tool)


# ---------------------------------------------------------------- 値
def _cap_value_in(cap: str, v: Any) -> Any:
    if v is None:
        return None
    if cap in BOOL_CAPS:
        return bool(v)
    return frozenset(v)


def _cap_value_out(v: Any) -> Any:
    if isinstance(v, frozenset):
        return sorted(v)
    return v


# ---------------------------------------------------------------- 入力（Config）
def from_legacy(d: Mapping[str, Any], *, origins: Optional[Mapping[str, Origin]] = None,
                sources: Optional[Mapping[tuple[str, str], str]] = None,
                imports: tuple[ImportRecord, ...] = ()) -> Config:
    origins = origins or {}
    sources = sources or {}
    stores = tuple(Store(id=s["id"], label=s["label"], external=s["external"], executes=s["executes"], secret=s["secret"])
                   for s in d["stores"].values())
    tools = []
    for t in d["tools"]:
        declared = {cap: Cap(_cap_value_in(cap, v), None) for cap, v in t["declared"].items()}
        observed = {cap: Cap(_cap_value_in(cap, o["value"]), o["confidence"], o["evidence"],
                             sources.get((t["id"], cap), "manual"))
                    for cap, o in t["observed"].items()}
        tools.append(Tool(id=t["id"], label=t["label"], mode=t["mode"], frequency=t["frequency"],
                          declared=FrozenMap(declared), observed=FrozenMap(observed), origin=origins.get(t["id"])))
    return Config(name=d["name"], untrusted_in_context=d["untrusted_in_context"], tools=tuple(tools),
                  stores=stores, imports=tuple(imports))


def to_legacy(cfg: Config) -> dict:
    """compat.v1 の関数が読む辞書。v2 の追加情報（origin・source・imports）は落ちる。"""
    stores = {s.id: {"id": s.id, "label": s.label, "external": s.external, "executes": s.executes, "secret": s.secret}
              for s in cfg.stores}
    tools = []
    for t in cfg.tools:
        declared = {cap: _cap_value_out(c.value) for cap, c in t.declared.items()}
        observed = {cap: {"value": _cap_value_out(c.value), "confidence": c.confidence, "evidence": c.evidence}
                    for cap, c in t.observed.items()}
        tools.append({"id": t.id, "label": t.label, "mode": t.mode, "frequency": t.frequency,
                      "declared": declared, "observed": observed})
    return {"skopost": SPEC_VERSION, "name": cfg.name, "untrusted_in_context": cfg.untrusted_in_context,
            "stores": stores, "tools": tools}


def _origin_out(o: Origin) -> dict:
    d: dict[str, Any] = {"file": o.file}
    if o.pointer:
        d["pointer"] = o.pointer
    if o.line is not None:
        d["line"] = o.line
    return d


def to_dict(cfg: Config, *, spec: int = 2) -> dict:
    """入力ファイルの形の JSON（辞書）。spec=1 は v2 の追加情報が無いときだけ（あれば ValueError：黙って落とさない）。"""
    if spec not in (1, 2):
        raise ValueError(f"spec は 1 か 2：{spec!r}")
    if spec == 1:
        lossy = bool(cfg.imports) or any(t.origin for t in cfg.tools) or any(
            c.source != "manual" for t in cfg.tools for c in t.observed.values())
        if lossy:
            raise ValueError("v2 の情報（imports・origin・source）があるため v1 では書けません")
    out: dict[str, Any] = {"skopost": spec, "name": cfg.name, "untrusted_in_context": cfg.untrusted_in_context}
    out["stores"] = [{"id": s.id, "label": s.label, "external": s.external, "executes": s.executes, "secret": s.secret}
                     for s in cfg.stores]
    tools = []
    for t in cfg.tools:
        td: dict[str, Any] = {"id": t.id, "label": t.label, "mode": t.mode, "frequency": t.frequency,
                              "declared": {cap: _cap_value_out(c.value) for cap, c in t.declared.items()}}
        obs: dict[str, Any] = {}
        for cap, c in t.observed.items():
            od: dict[str, Any] = {"confidence": c.confidence, "evidence": c.evidence}
            if not c.unknown:
                od["value"] = _cap_value_out(c.value)
            if c.source != "manual":
                od["source"] = c.source
            obs[cap] = od
        td["observed"] = obs
        if t.origin is not None:
            td["origin"] = _origin_out(t.origin)
        tools.append(td)
    out["tools"] = tools
    if cfg.imports:
        out["imports"] = [{"file": i.file, "sha256": i.sha256, "adapter": i.adapter} for i in cfg.imports]
    return out


# ---------------------------------------------------------------- 結果（AnalysisResult）
def _method_of(cp: Mapping[str, Any]) -> str:
    if not cp["exact"]:
        return "greedy"
    return "trivial" if not cp["primary"] else "exhaustive"


def result_from_legacy(r: Mapping[str, Any]) -> AnalysisResult:
    """compat.v1.analyze() の辞書 → AnalysisResult。"""
    s = r["summary"]
    cp = r["checkpoints"]
    size = len(cp["primary"])
    checkpoints = Checkpoints(exact=cp["exact"], primary=tuple(cp["primary"]),
                              alternatives=tuple(tuple(a) for a in cp["alternatives"]),
                              method=_method_of(cp), lower_bound=size if cp["exact"] else 0)  # type: ignore[arg-type]
    return AnalysisResult(
        name=r["name"],
        summary=Summary(**s),
        paths=tuple(HarmPath(p["kind"], tuple(p["tools"]), tuple(p["via"]), p["confidence"]) for p in r["paths"]),
        mismatches=tuple(Mismatch(m["tool"], m["cap"], _mm_val(m["declared"]), _mm_val(m["observed"]), m["confidence"],
                                  m["evidence"], m["severity"]) for m in r["mismatches"]),
        assumed=tuple(Assumed(a["tool"], a["cap"]) for a in r["assumed"]),
        checkpoints=checkpoints,
        reasons=FrozenMap({k: tuple(v) for k, v in cp["reasons"].items()}),
        declared_only=DeclaredOnly(cut=tuple(r["declared_only"]["cut"]), surviving=tuple(r["declared_only"]["surviving"])),
        not_checked=tuple(r["not_checked"]),
        result_version=r["skopost"],
    )


def _mm_val(v: Any) -> Any:
    return frozenset(v) if isinstance(v, list) else v


def result_to_dict(res: AnalysisResult) -> dict:
    """AnalysisResult → SPEC §10 の JSON（compat.v1.analyze() と同じ鍵・同じ順序）。"""
    s = res.summary
    cp = res.checkpoints
    return {
        "skopost": res.result_version if res.result_version else RESULT_VERSION, "name": res.name,
        "exit_code": res.exit_code,
        "summary": {"tools": s.tools, "allowed": s.allowed, "paths": s.paths, "paths_declared_only": s.paths_declared_only,
                    "missed_by_declared": s.missed_by_declared, "mismatches": s.mismatches,
                    "assumed_unknown": s.assumed_unknown, "seconds": s.seconds},
        "paths": [{"kind": p.kind, "tools": list(p.tools), "confidence": p.confidence, "via": list(p.via)} for p in res.paths],
        "mismatches": [{"tool": m.tool, "cap": m.cap, "declared": _cap_value_out(m.declared),
                        "observed": _cap_value_out(m.observed), "confidence": m.confidence, "evidence": m.evidence,
                        "severity": m.severity} for m in res.mismatches],
        "assumed": [{"tool": a.tool, "cap": a.cap} for a in res.assumed],
        "checkpoints": {"exact": cp.exact, "primary": list(cp.primary), "alternatives": [list(a) for a in cp.alternatives],
                        "size": cp.size, "reasons": {k: list(v) for k, v in res.reasons.items()}},
        "declared_only": {"cut": list(res.declared_only.cut), "holds": res.declared_only.holds,
                          "surviving_paths": res.declared_only.surviving_paths,
                          "surviving": list(res.declared_only.surviving)},
        "not_checked": list(res.not_checked),
    }
