"""infer の公開面（担当 C・段 2）。名前・引数・返り値の型は契約（変えるときは担当 A に依頼）。

参照実装：compat.v1 の `effective`・`mismatches`・`_min_conf`（意味はこれと同じにする。契約試験が照合する）。

方針：
- 「不明」は危ない側に倒す（observed 層の真偽は真・acts は全種）。置き場の札（writes_stores・reads_stores）だけは
  v1 互換で「置き場なし」と読む（ARCHITECTURE「段 1 で見つけたこと」1。どちらに寄せるかは未決・ここでは変えない）。
- 規則由来の札は「確」にならない（max_confidence で頭打ち・model.Cap の不変条件でも二重に守る）。
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..model.constants import ACT_KINDS, ALL_CAPS, BOOL_CAPS
from ..model.types import Assumed, Cap, Config, EffCap, EffectiveCaps, Fact, Layer, Mismatch, Store, Tool, weakest
from .rules import DEFAULT_RULES, Rule

OWNER = "C：推定"

_EMPTY_SET: frozenset = frozenset()


# ---------------------------------------------------------------- 推定
def _clamp(cap: Cap, max_conf: str, rule_id: str) -> Cap:
    """確度を規則の上限で頭打ちにし、出どころを "infer:<id>" に揃える。"""
    conf = cap.confidence
    if conf is None:
        raise ValueError(f"{rule_id}: 規則は宣言の札（確度 None）を出せない")
    conf = weakest(conf, max_conf)  # type: ignore[arg-type]
    value = None if conf == "不明" else cap.value
    return Cap(value, conf, cap.evidence, f"infer:{rule_id}")


def infer_caps(facts: Sequence[Fact], rules: Sequence[Rule] = DEFAULT_RULES) -> dict[str, dict[str, Cap]]:
    """事実から札を推定する。返り値は {tool_id: {cap_name: Cap}}。出どころは "infer:<規則ID>"、確度は「確」にならない。

    既定値は DEFAULT_RULES（統合で契約を変更）。規則を使わないときは `infer_caps(facts, ())`。

    同じ道具・同じ項目に複数の規則が当たったら `combine`（同じ層の出どころ同士なので危ない側・弱い確度）。
    """
    out: dict[str, dict[str, Cap]] = {}
    for f in facts:
        for r in rules:
            if not r.applies(f):
                continue
            for name, cap in r.infer(f).items():
                if name not in ALL_CAPS:
                    raise ValueError(f"{r.id}: 未知の項目 {name!r}")
                c = _clamp(cap, r.max_confidence, r.id)
                slot = out.setdefault(f.tool_id, {})
                slot[name] = combine(slot[name], c) if name in slot else c
    return out


def _rank(src: str) -> int:
    if src == "manual":
        return 2
    if src.startswith("ingest:"):
        return 1
    return 0  # infer:


def _join_evidence(a: str, b: str) -> str:
    parts = sorted({x for x in (a, b) if x})
    return "；".join(parts)


def combine(a: Cap, b: Cap) -> Cap:
    """2 つの札を合成。手書き（manual）> 取り込み（ingest）> 規則（infer）。同じ順位なら危ない側。確度は弱い方。

    - 同じ順位で片方が不明なら結果は不明（不明は危ない側）。
    - 値・確度は引数の順に依らない（可換）。出どころ・根拠も順に依らないよう決める。
    """
    if a.is_declared != b.is_declared:
        raise ValueError("宣言の札と観察の札は合成できない")
    ra, rb = _rank(a.source), _rank(b.source)
    if ra != rb:
        return a if ra > rb else b
    src = min(a.source, b.source)
    ev = _join_evidence(a.evidence, b.evidence)
    if a.is_declared:
        return Cap(_danger(a.value, b.value), None, ev, src)
    if a.unknown or b.unknown:
        return Cap(None, "不明", ev, src)
    if type(a.value) is not type(b.value):
        raise ValueError("真偽の札と集合の札は合成できない")
    return Cap(_danger(a.value, b.value), weakest(a.confidence, b.confidence), ev, src)  # type: ignore[arg-type]


def _danger(x, y):
    if isinstance(x, bool):
        return x or y
    return frozenset(x) | frozenset(y)


# ---------------------------------------------------------------- 実効の札
def _layer_value(tool: Tool, cap: str, layer: str) -> tuple[object, str, bool]:
    """(値, 確度, 不明を仮定したか)。compat.v1._layer_value と同じ意味。"""
    if layer == "declared":
        c = tool.declared.get(cap)
        if c is None:
            return (False if cap in BOOL_CAPS else _EMPTY_SET), "宣言", False
        return c.value, "宣言", False
    ob = tool.observed.get(cap)
    if ob is None or ob.unknown:
        if cap in BOOL_CAPS:
            return True, "不明", True
        if cap == "acts":
            return frozenset(ACT_KINDS), "不明", True
        return _EMPTY_SET, "不明", False  # 置き場：v1 互換（上の方針を参照）
    return ob.value, ob.confidence, False  # type: ignore[return-value]


def _ordered(ids: frozenset) -> list[str]:
    # v1 の検証器は配列を sorted(set()) にするので、v1 と同じ並びは昇順。
    return sorted(ids)


def effective(tool: Tool, stores: Mapping[str, Store], layer: Layer) -> EffectiveCaps:
    """置き場を畳み込んだ実効の札（SPEC §6）。observed 層では不明を危ない側に倒し、assumed に記録する。"""
    if layer not in ("declared", "observed"):
        raise ValueError(f"layer は declared か observed：{layer!r}")
    caps: dict[str, EffCap] = {}
    assumed: set[str] = set()

    def get(cap: str):
        v, c, a = _layer_value(tool, cap, layer)
        if a:
            assumed.add(cap)
        return v, c

    for cap in ("reads_untrusted", "args_leave"):
        v, c = get(cap)
        caps[cap] = EffCap(bool(v), c, cap)  # type: ignore[arg-type]
    ws, _ = get("writes_stores")
    rs, _ = get("reads_stores")

    def fold(eff: str, cap: str, src: frozenset, prop: str, verb: str, what: str) -> None:
        v, c = get(cap)
        hit = [s for s in _ordered(src) if getattr(stores[s], prop)]
        if v:
            caps[eff] = EffCap(True, c, cap)  # type: ignore[arg-type]
        elif hit:
            caps[eff] = EffCap(True, "論", f"{verb}→{','.join(hit)}（{what}）")
        else:
            caps[eff] = EffCap(False, c, "")  # type: ignore[arg-type]

    fold("exec", "exec", ws, "executes", "writes_stores", "実行される置き場")
    fold("net", "net_out", ws, "external", "writes_stores", "外部の置き場")
    fold("secret", "reads_secret", rs, "secret", "reads_stores", "秘密のある置き場")
    v, c = get("acts")
    caps["acts"] = EffCap(frozenset(v), c, "acts")  # type: ignore[arg-type]
    return EffectiveCaps(tool.id, layer, caps, frozenset(assumed))


# ---------------------------------------------------------------- 食い違い
def mismatches(cfg: Config) -> list[Mismatch]:
    """宣言と観察の食い違い（不明の札は食い違いにしない）。順序は道具の順・ALL_CAPS の順。"""
    out: list[Mismatch] = []
    for t in cfg.tools:
        for cap in ALL_CAPS:
            ob = t.observed.get(cap)
            if ob is None or ob.unknown:
                continue
            d = t.declared.get(cap)
            dv = d.value if d is not None else (False if cap in BOOL_CAPS else _EMPTY_SET)
            ov = ob.value
            if dv == ov:
                continue
            if cap in BOOL_CAPS:
                sev = "under" if ov and not dv else "over"
            else:
                sev = "under" if frozenset(ov) - frozenset(dv) else "over"  # type: ignore[arg-type]
            out.append(Mismatch(t.id, cap, dv, ov, ob.confidence, ob.evidence, sev))  # type: ignore[arg-type]
    return out


# v1 の analyze が assumed を並べる順（effective の中で get を呼ぶ順）
_ASSUMED_ORDER = ("reads_untrusted", "args_leave", "exec", "net_out", "reads_secret", "acts")


def assumed_unknown(cfg: Config) -> list[Assumed]:
    """allow の道具で、observed 層の実効の札を作るときに不明を危ない側と仮定した項目（v1 の analyze の assumed と同じ順）。"""
    stores = cfg.store_map()
    out: list[Assumed] = []
    for t in cfg.allowed():
        a = effective(t, stores, "observed").assumed
        out.extend(Assumed(t.id, cap) for cap in _ASSUMED_ORDER if cap in a)  # type: ignore[arg-type]
    return out

