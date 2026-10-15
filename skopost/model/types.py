"""共有する型（全担当が依存する唯一の土台。変更できるのは担当 A だけ：ARCHITECTURE §4）。

すべて不変（frozen dataclass・FrozenMap・tuple・frozenset）。生成時に不変条件を確かめ、破れていれば
`ValueError`（プログラムの誤り）を投げる。利用者の入力の誤りは `model.parse` が `SkopostError` にする。

旧 API（辞書）との変換は `model.convert`。
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, Optional, Union, get_args

from .constants import (ACT_KINDS, ALL_CAPS, BOOL_CAPS, CONF_ORDER, ID_RE, RESULT_VERSION, SHA256_RE,
                        SOURCE_RE)
from .frozen import EMPTY, FrozenMap

# ---------------------------------------------------------------- 字句の型
Confidence = Literal["確", "論", "推", "不明"]
Layer = Literal["declared", "observed"]
Mode = Literal["allow", "ask"]
ActKind = Literal["send", "purchase", "delete", "publish", "grant", "pay"]
PathKind = Literal["exec", "act", "exfil"]
Severity = Literal["under", "over"]
CheckpointMethod = Literal["trivial", "bipartite-konig", "branch-and-bound", "exhaustive", "greedy", "unspecified"]
CapName = Literal["reads_untrusted", "reads_secret", "net_out", "args_leave", "exec",
                  "acts", "writes_stores", "reads_stores"]
#: 実効の札の項目（SPEC §6：置き場を畳み込んだ後の名前）
EffName = Literal["reads_untrusted", "args_leave", "exec", "net", "secret", "acts"]
CapValue = Union[bool, frozenset, None]

CONFIDENCE_VALUES: tuple[str, ...] = get_args(Confidence)
EFF_NAMES: tuple[str, ...] = get_args(EffName)
assert set(get_args(ActKind)) == set(ACT_KINDS)
assert set(get_args(CapName)) == set(ALL_CAPS)


def _req(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def _is_id(s: object) -> bool:
    return isinstance(s, str) and bool(ID_RE.match(s))


def weakest(*cs: Confidence) -> Confidence:
    """確度の合成は弱い方（不明 < 推 < 論 < 確）。空なら「不明」。"""
    if not cs:
        return "不明"
    return min(cs, key=lambda c: CONF_ORDER[c])  # type: ignore[return-value]


# ---------------------------------------------------------------- 入力の型
@dataclass(frozen=True, slots=True)
class Origin:
    """札や道具がどのファイルのどこから来たか（ingest が付ける。SARIF の位置になる）。"""
    file: str
    pointer: str = ""             # JSON Pointer（RFC 6901）。"" は文書全体
    line: Optional[int] = None    # 1 始まり。分からなければ None（不明）

    def __post_init__(self) -> None:
        _req(isinstance(self.file, str) and 0 < len(self.file) <= 4096, "Origin.file は 1〜4096 字")
        _req(isinstance(self.pointer, str) and (self.pointer == "" or self.pointer.startswith("/")),
             "Origin.pointer は '' か '/' で始まる JSON Pointer")
        _req(self.line is None or (isinstance(self.line, int) and not isinstance(self.line, bool) and self.line >= 1),
             "Origin.line は 1 以上の整数か None")


@dataclass(frozen=True, slots=True)
class Cap:
    """1 項目の札。

    - 観察の札（observed）：`confidence` は 確/論/推/不明。不明のとき `value` は None。
    - 宣言の札（declared）：`confidence` は None（宣言は主張であって確度を持たない）。`value` は None にならない。
    - 真偽の項目の値は bool、配列の項目は frozenset[str]。
    """
    value: CapValue
    confidence: Optional[Confidence]
    evidence: str = ""
    source: str = "manual"        # "manual" | "ingest:<adapter>" | "infer:<RULE-ID>"

    def __post_init__(self) -> None:
        _req(self.confidence is None or self.confidence in CONFIDENCE_VALUES, f"Cap.confidence が不正：{self.confidence!r}")
        _req(isinstance(self.evidence, str), "Cap.evidence は文字列")
        _req(isinstance(self.source, str) and bool(SOURCE_RE.match(self.source)), f"Cap.source が不正：{self.source!r}")
        if self.confidence == "不明":
            _req(self.value is None, "確度が不明の札の value は None")
        else:
            _req(self.value is not None, "確度が不明でない札（宣言を含む）の value は None にできない")
        _req(self.value is None or isinstance(self.value, (bool, frozenset)), "Cap.value は bool・frozenset・None")
        if self.source.startswith(("infer:", "ingest:")):
            # 不変条件（ARCHITECTURE §1.3・I1・F2）：規則・取り込みは札に「確」を作らない。
            # 設定ファイルの構文上の事実（mode など）は Cap ではなく Tool の欄に入るので、この制約と両立する。
            _req(self.confidence != "確", "規則（infer:）・取り込み（ingest:）由来の札に「確」は付けられない")

    @property
    def unknown(self) -> bool:
        return self.confidence == "不明"

    @property
    def is_declared(self) -> bool:
        return self.confidence is None


def _check_caps(caps: Mapping[str, Cap], *, declared: bool, who: str) -> None:
    for name, cap in caps.items():
        _req(name in ALL_CAPS, f"{who}: 未知の項目 {name!r}")
        _req(isinstance(cap, Cap), f"{who}.{name}: Cap が要る")
        _req(cap.is_declared == declared,
             f"{who}.{name}: {'宣言' if declared else '観察'}の札の確度の付け方が逆")
        v = cap.value
        if v is None:
            continue
        if name in BOOL_CAPS:
            _req(isinstance(v, bool), f"{who}.{name}: 真偽値が要る")
        else:
            _req(isinstance(v, frozenset) and all(isinstance(x, str) for x in v), f"{who}.{name}: frozenset[str] が要る")
            if name == "acts":
                _req(v <= frozenset(ACT_KINDS), f"{who}.acts: 未知の操作 {sorted(v - frozenset(ACT_KINDS))}")


@dataclass(frozen=True, slots=True)
class Tool:
    id: str
    label: str = ""
    mode: Mode = "allow"
    frequency: int = 1
    declared: FrozenMap = field(default=EMPTY)   # FrozenMap[CapName, Cap]（確度 None）
    observed: FrozenMap = field(default=EMPTY)   # FrozenMap[CapName, Cap]（確度あり）
    origin: Optional[Origin] = None

    def __post_init__(self) -> None:
        _req(_is_id(self.id), f"Tool.id が不正：{self.id!r}")
        _req(isinstance(self.label, str), "Tool.label は文字列")
        _req(self.mode in ("allow", "ask"), f"Tool.mode は allow か ask：{self.mode!r}")
        _req(isinstance(self.frequency, int) and not isinstance(self.frequency, bool) and 1 <= self.frequency <= 1_000_000,
             "Tool.frequency は 1〜1000000 の整数")
        for attr in ("declared", "observed"):
            m = getattr(self, attr)
            if not isinstance(m, FrozenMap):
                _req(isinstance(m, Mapping), f"Tool.{attr} は対応表")
                object.__setattr__(self, attr, FrozenMap(m))
        _check_caps(self.declared, declared=True, who=f"{self.id}.declared")
        _check_caps(self.observed, declared=False, who=f"{self.id}.observed")
        _req(self.origin is None or isinstance(self.origin, Origin), "Tool.origin は Origin か None")

    def stores_referenced(self) -> frozenset[str]:
        out: set[str] = set()
        for layer in (self.declared, self.observed):
            for cap in ("writes_stores", "reads_stores"):
                c = layer.get(cap)
                if c is not None and c.value:
                    out |= c.value
        return frozenset(out)


@dataclass(frozen=True, slots=True)
class Store:
    id: str
    label: str = ""
    external: bool = False
    executes: bool = False
    secret: bool = False

    def __post_init__(self) -> None:
        _req(_is_id(self.id), f"Store.id が不正：{self.id!r}")
        _req(isinstance(self.label, str), "Store.label は文字列")
        for k in ("external", "executes", "secret"):
            _req(isinstance(getattr(self, k), bool), f"Store.{k} は真偽値")


@dataclass(frozen=True, slots=True)
class ImportRecord:
    """取り込んだ元ファイル（v2・再現性のため）。中身は持たない。"""
    file: str
    sha256: str
    adapter: str = "native"

    def __post_init__(self) -> None:
        _req(isinstance(self.file, str) and 0 < len(self.file) <= 4096, "ImportRecord.file は 1〜4096 字")
        _req(isinstance(self.sha256, str) and bool(SHA256_RE.match(self.sha256)), "ImportRecord.sha256 は小文字 16 進 64 字")
        _req(isinstance(self.adapter, str) and bool(SOURCE_RE.match(f"ingest:{self.adapter}")),
             "ImportRecord.adapter は英小文字・数字・- の 1〜32 字")


@dataclass(frozen=True, slots=True)
class Config:
    name: str = ""
    untrusted_in_context: bool = True
    tools: tuple[Tool, ...] = ()
    stores: tuple[Store, ...] = ()
    imports: tuple[ImportRecord, ...] = ()
    spec: int = 2                 # 正規化後の版（model.parse は常に最新版にする）

    def __post_init__(self) -> None:
        _req(isinstance(self.name, str), "Config.name は文字列")
        _req(isinstance(self.untrusted_in_context, bool), "Config.untrusted_in_context は真偽値")
        for attr in ("tools", "stores", "imports"):
            v = getattr(self, attr)
            if not isinstance(v, tuple):
                object.__setattr__(self, attr, tuple(v))
        _req(all(isinstance(t, Tool) for t in self.tools), "Config.tools は Tool の並び")
        _req(all(isinstance(s, Store) for s in self.stores), "Config.stores は Store の並び")
        _req(all(isinstance(i, ImportRecord) for i in self.imports), "Config.imports は ImportRecord の並び")
        tids = [t.id for t in self.tools]
        _req(len(tids) == len(set(tids)), "Config.tools の id が重複")
        sids = [s.id for s in self.stores]
        _req(len(sids) == len(set(sids)), "Config.stores の id が重複")
        known = set(sids)
        for t in self.tools:
            missing = t.stores_referenced() - known
            _req(not missing, f"{t.id}: 置き場 {sorted(missing)} が stores にない")

    # 便利関数（計算はしない。引くだけ）
    def tool(self, tid: str) -> Tool:
        for t in self.tools:
            if t.id == tid:
                return t
        raise KeyError(tid)

    def store_map(self) -> FrozenMap:
        return FrozenMap({s.id: s for s in self.stores})

    def allowed(self) -> tuple[Tool, ...]:
        return tuple(t for t in self.tools if t.mode == "allow")


# ---------------------------------------------------------------- 取り込み（ingest）と推定（infer）の受け渡し
@dataclass(frozen=True, slots=True)
class Fact:
    """取り込みが設定ファイルから読んだ 1 つの事実。infer の規則の入力（ARCHITECTURE §1.2–1.3）。

    `value` は JSON で表せる不変の値（str・int・bool・None・tuple）。説明文（description）は事実にしない。
    """
    tool_id: str
    key: str                      # 例 "openapi.method"・"mcp.annotation.readOnlyHint"・"claude.permission"
    value: object
    origin: Optional[Origin] = None
    adapter: str = "native"

    def __post_init__(self) -> None:
        _req(_is_id(self.tool_id), f"Fact.tool_id が不正：{self.tool_id!r}")
        _req(isinstance(self.key, str) and 0 < len(self.key) <= 128, "Fact.key は 1〜128 字")
        _req(_is_frozen_json(self.value), "Fact.value は不変の JSON 値（str/int/float/bool/None/tuple）")


def _is_frozen_json(v: object, depth: int = 0) -> bool:
    if depth > 16:
        return False
    if v is None or isinstance(v, (str, bool, int, float)):
        return True
    if isinstance(v, tuple):
        return all(_is_frozen_json(x, depth + 1) for x in v)
    return False


IngestNoteKind = Literal["unread_key", "dropped", "assumption", "secret_discarded", "unsupported"]


@dataclass(frozen=True, slots=True)
class IngestNote:
    """取り込みで読めなかった鍵・捨てた項目・置いた仮定（原則 7：報告に出す）。秘密の値そのものは入れない。"""
    kind: IngestNoteKind
    pointer: str
    message: str

    def __post_init__(self) -> None:
        _req(self.kind in get_args(IngestNoteKind), f"IngestNote.kind が不正：{self.kind!r}")
        _req(isinstance(self.pointer, str) and (self.pointer == "" or self.pointer.startswith("/")), "IngestNote.pointer は JSON Pointer")
        _req(isinstance(self.message, str) and len(self.message) <= 500, "IngestNote.message は 500 字まで")


@dataclass(frozen=True, slots=True)
class IngestResult:
    config: Config
    notes: tuple[IngestNote, ...] = ()
    dropped: tuple[str, ...] = ()           # JSON Pointer の一覧
    facts: tuple[Fact, ...] = ()            # infer に渡す事実

    def __post_init__(self) -> None:
        _req(isinstance(self.config, Config), "IngestResult.config は Config")
        for attr in ("notes", "dropped", "facts"):
            v = getattr(self, attr)
            if not isinstance(v, tuple):
                object.__setattr__(self, attr, tuple(v))
        _req(all(isinstance(n, IngestNote) for n in self.notes), "IngestResult.notes は IngestNote の並び")
        _req(all(isinstance(p, str) and (p == "" or p.startswith("/")) for p in self.dropped), "IngestResult.dropped は JSON Pointer の並び")
        _req(all(isinstance(f, Fact) for f in self.facts), "IngestResult.facts は Fact の並び")


@dataclass(frozen=True, slots=True)
class EffCap:
    """実効の札の 1 項目（置き場を畳み込んだ後）。"""
    value: Union[bool, frozenset]
    confidence: Union[Confidence, Literal["宣言"]]   # declared 層では v1 互換で「宣言」
    why: str = ""

    def __post_init__(self) -> None:
        _req(isinstance(self.value, (bool, frozenset)), "EffCap.value は bool か frozenset")
        _req(self.confidence in CONFIDENCE_VALUES or self.confidence == "宣言", f"EffCap.confidence が不正：{self.confidence!r}")
        _req(isinstance(self.why, str), "EffCap.why は文字列")


@dataclass(frozen=True, slots=True)
class EffectiveCaps:
    """1 つの道具の実効の札（SPEC §6）。infer.effective が返し、graph が読む。"""
    tool_id: str
    layer: Layer
    caps: FrozenMap                    # FrozenMap[EffName, EffCap]。EFF_NAMES の 6 項目すべてを持つ
    assumed: frozenset = frozenset()   # 不明 → 危ない側と仮定した元の項目名（CapName）

    def __post_init__(self) -> None:
        _req(_is_id(self.tool_id), "EffectiveCaps.tool_id が不正")
        _req(self.layer in ("declared", "observed"), "EffectiveCaps.layer は declared か observed")
        if not isinstance(self.caps, FrozenMap):
            object.__setattr__(self, "caps", FrozenMap(self.caps))
        _req(set(self.caps) == set(EFF_NAMES), f"EffectiveCaps.caps は {EFF_NAMES} を全部持つ")
        _req(all(isinstance(c, EffCap) for c in self.caps.values()), "EffectiveCaps.caps の値は EffCap")
        _req(isinstance(self.caps["acts"].value, frozenset), "acts は frozenset")
        _req(all(isinstance(self.caps[k].value, bool) for k in EFF_NAMES if k != "acts"), "acts 以外は真偽値")
        _req(isinstance(self.assumed, frozenset) and self.assumed <= frozenset(ALL_CAPS), "assumed は CapName の frozenset")
        if self.layer == "declared":
            _req(not self.assumed, "declared 層は不明を仮定しない")

    def __getitem__(self, name: str) -> EffCap:
        return self.caps[name]


@dataclass(frozen=True, slots=True)
class Mismatch:
    tool: str
    cap: CapName
    declared: Union[bool, frozenset]
    observed: Union[bool, frozenset]
    confidence: Confidence
    evidence: str
    severity: Severity

    def __post_init__(self) -> None:
        _req(_is_id(self.tool), "Mismatch.tool が不正")
        _req(self.cap in ALL_CAPS, "Mismatch.cap が不正")
        _req(self.confidence in CONFIDENCE_VALUES and self.confidence != "不明", "Mismatch.confidence は 確/論/推（不明は食い違いにしない）")
        _req(self.severity in ("under", "over"), "Mismatch.severity は under か over")
        _req(self.declared != self.observed, "Mismatch は宣言と観察が違うときだけ")


@dataclass(frozen=True, slots=True)
class Assumed:
    tool: str
    cap: CapName

    def __post_init__(self) -> None:
        _req(_is_id(self.tool), "Assumed.tool が不正")
        _req(self.cap in ALL_CAPS, "Assumed.cap が不正")


# ---------------------------------------------------------------- 危険経路と関所（graph）
@dataclass(frozen=True, slots=True)
class HarmPath:
    """危ない道 1 本。定義（どの組み合わせを道とするか）は graph の担当・根幹で、段 1 では型だけを決める。

    形の不変条件（v1 の SPEC §7 と互換。種類を増やすときは版を上げて ARCHITECTURE を更新）：
    - exec・act：道具 1 個・via 1 個
    - exfil    ：道具 2 個（読む側, 送る側。同じ道具でもよい）・via 2 個
    """
    kind: PathKind
    tools: tuple[str, ...]
    via: tuple[str, ...]
    confidence: Union[Confidence, Literal["宣言"]]

    def __post_init__(self) -> None:
        _req(self.kind in ("exec", "act", "exfil"), f"HarmPath.kind が不正：{self.kind!r}")
        if not isinstance(self.tools, tuple):
            object.__setattr__(self, "tools", tuple(self.tools))
        if not isinstance(self.via, tuple):
            object.__setattr__(self, "via", tuple(self.via))
        n = 2 if self.kind == "exfil" else 1
        _req(len(self.tools) == n, f"HarmPath({self.kind}) の道具は {n} 個")
        _req(len(self.via) == n, f"HarmPath({self.kind}) の via は {n} 個")
        _req(all(_is_id(t) for t in self.tools), "HarmPath.tools の id が不正")
        _req(all(isinstance(v, str) for v in self.via), "HarmPath.via は文字列")
        # 「宣言」は declared 層の道（宣言だけの地図）で v1 互換の印。観察の層では 確/論/推/不明
        _req(self.confidence in CONFIDENCE_VALUES or self.confidence == "宣言", f"HarmPath.confidence が不正：{self.confidence!r}")

    @property
    def key(self) -> str:
        """v1 の path_key と同じ（道具 id を '>' でつなぐ）。基準線の照合に使う。"""
        return ">".join(self.tools)

    @property
    def tool_set(self) -> frozenset:
        return frozenset(self.tools)


@dataclass(frozen=True, slots=True)
class Checkpoints:
    """道を全部断つ allow→ask の集合。厳密解の求め方は graph の担当・根幹（段 1 は型と契約だけ）。

    不変条件：
    - `lower_bound <= len(primary)`。`exact` なら `lower_bound == len(primary)`（最小と証明できた）
    - `alternatives` の各案は `primary` と同じ大きさで、互いに・`primary` と重複しない
    - 各案の中に同じ道具は 2 度現れない
    """
    exact: bool
    primary: tuple[str, ...]
    alternatives: tuple[tuple[str, ...], ...] = ()
    method: CheckpointMethod = "unspecified"
    lower_bound: int = 0

    def __post_init__(self) -> None:
        _req(isinstance(self.exact, bool), "Checkpoints.exact は真偽値")
        if not isinstance(self.primary, tuple):
            object.__setattr__(self, "primary", tuple(self.primary))
        object.__setattr__(self, "alternatives", tuple(tuple(a) for a in self.alternatives))
        _req(all(_is_id(t) for t in self.primary), "Checkpoints.primary の id が不正")
        _req(len(set(self.primary)) == len(self.primary), "Checkpoints.primary に重複")
        _req(self.method in get_args(CheckpointMethod), f"Checkpoints.method が不正：{self.method!r}")
        _req(isinstance(self.lower_bound, int) and not isinstance(self.lower_bound, bool) and 0 <= self.lower_bound <= len(self.primary),
             "Checkpoints.lower_bound は 0 以上 len(primary) 以下")
        if self.exact:
            _req(self.lower_bound == len(self.primary), "exact なら lower_bound == len(primary)")
        seen = {frozenset(self.primary)}
        for alt in self.alternatives:
            _req(len(alt) == len(self.primary), "代替案は primary と同じ大きさ")
            _req(len(set(alt)) == len(alt) and all(_is_id(t) for t in alt), "代替案の id が不正か重複")
            _req(frozenset(alt) not in seen, "代替案が重複")
            seen.add(frozenset(alt))

    @property
    def size(self) -> int:
        return len(self.primary)

    def cuts(self, paths: tuple[HarmPath, ...] | list[HarmPath], cut: tuple[str, ...] | None = None) -> bool:
        """`cut`（既定 primary）が全部の道に少なくとも 1 つ当たるか。契約試験の判定に使う（計算は自明な集合演算だけ）。"""
        s = frozenset(self.primary if cut is None else cut)
        return all(p.tool_set & s for p in paths)


@dataclass(frozen=True, slots=True)
class DeclaredOnly:
    """宣言だけで関所を決めたとき、観察の層で道が残るか。"""
    cut: tuple[str, ...]
    surviving: tuple[str, ...]              # 残る道の key

    @property
    def holds(self) -> bool:
        return not self.surviving

    @property
    def surviving_paths(self) -> int:
        return len(self.surviving)


@dataclass(frozen=True, slots=True)
class Summary:
    tools: int
    allowed: int
    paths: int
    paths_declared_only: int
    missed_by_declared: int
    mismatches: int
    assumed_unknown: int
    seconds: float

    def __post_init__(self) -> None:
        for k in ("tools", "allowed", "paths", "paths_declared_only", "missed_by_declared", "mismatches", "assumed_unknown"):
            v = getattr(self, k)
            _req(isinstance(v, int) and not isinstance(v, bool) and v >= 0, f"Summary.{k} は 0 以上の整数")
        _req(self.allowed <= self.tools, "Summary.allowed <= tools")
        _req(self.missed_by_declared <= self.paths, "Summary.missed_by_declared <= paths")


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """解析の結果（report が整形し、ci が基準線と比べる）。JSON の形は SPEC §10・`model.convert.result_to_dict`。"""
    name: str
    summary: Summary
    paths: tuple[HarmPath, ...]
    mismatches: tuple[Mismatch, ...]
    assumed: tuple[Assumed, ...]
    checkpoints: Checkpoints
    reasons: FrozenMap                       # FrozenMap[tool_id, tuple[str, ...]]
    declared_only: DeclaredOnly
    not_checked: tuple[str, ...]
    result_version: int = RESULT_VERSION

    def __post_init__(self) -> None:
        for attr in ("paths", "mismatches", "assumed", "not_checked"):
            v = getattr(self, attr)
            if not isinstance(v, tuple):
                object.__setattr__(self, attr, tuple(v))
        if not isinstance(self.reasons, FrozenMap):
            object.__setattr__(self, "reasons", FrozenMap({k: tuple(v) for k, v in self.reasons.items()}))
        _req(self.summary.paths == len(self.paths), "Summary.paths と paths の本数が違う")
        _req(self.summary.mismatches == len(self.mismatches), "Summary.mismatches と mismatches の数が違う")
        _req(self.summary.assumed_unknown == len(self.assumed), "Summary.assumed_unknown と assumed の数が違う")
        _req(bool(self.not_checked), "not_checked（走らせなかった検査）は空にできない（原則 7）")
        _req(set(self.reasons) <= set(self.checkpoints.primary), "reasons の鍵は primary の道具だけ")

    @property
    def exit_code(self) -> int:
        """0＝道なし／2＝道あり（1＝入力の誤りは結果を作らない）。"""
        return 2 if self.paths else 0


# ---------------------------------------------------------------- 基準線（ci）
@dataclass(frozen=True, slots=True)
class Baseline:
    """前回の結果の道の集合（道は kind と key で同一視。順序には依らない：ARCHITECTURE C1）。"""
    entries: frozenset                       # frozenset[tuple[PathKind, str]]
    version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.entries, frozenset):
            object.__setattr__(self, "entries", frozenset(self.entries))
        for e in self.entries:
            _req(isinstance(e, tuple) and len(e) == 2 and e[0] in ("exec", "act", "exfil") and isinstance(e[1], str),
                 f"Baseline.entries の要素は (kind, key)：{e!r}")


@dataclass(frozen=True, slots=True)
class BaselineDiff:
    added: tuple[tuple[str, str], ...]
    removed: tuple[tuple[str, str], ...]
    unchanged: tuple[tuple[str, str], ...]

    @property
    def regressed(self) -> bool:
        """新しく増えた道があるか（CI はこれだけで失敗させる）。"""
        return bool(self.added)


__all__ = [
    "Confidence", "Layer", "Mode", "ActKind", "PathKind", "Severity", "CheckpointMethod", "CapName", "EffName",
    "CONFIDENCE_VALUES", "EFF_NAMES", "weakest",
    "Origin", "Cap", "Tool", "Store", "ImportRecord", "Config",
    "Fact", "IngestNote", "IngestResult", "EffCap", "EffectiveCaps", "Mismatch", "Assumed",
    "HarmPath", "Checkpoints", "DeclaredOnly", "Summary", "AnalysisResult", "Baseline", "BaselineDiff",
]
