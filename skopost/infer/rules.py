"""推定規則の型（ingest も読むので infer の中で最も下に置く。依存は model だけ）。

規則の中身（DEFAULT_RULES）は段 2 の担当 C が埋める。段 1 は型と契約だけ。
契約（tests/test_contract_infer.py）：
- `Rule.id` は "R-" で始まる大文字・数字・- の固定 ID（報告に出す）
- `max_confidence` は 論/推/不明 のどれか。規則は「確」を出せない（F2）
- `infer` が返す札の確度は `max_confidence` 以下、出どころは "infer:<id>"
"""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ..model.types import Cap, Confidence, Fact

RULE_ID_RE = re.compile(r"^R-[A-Z0-9-]{1,46}$")


@dataclass(frozen=True)
class Rule:
    id: str
    applies: Callable[[Fact], bool]
    infer: Callable[[Fact], Mapping[str, Cap]]
    max_confidence: Confidence = "推"
    description: str = ""

    def __post_init__(self) -> None:
        if not RULE_ID_RE.match(self.id):
            raise ValueError(f"Rule.id は R- で始まる大文字・数字・-：{self.id!r}")
        if self.max_confidence not in ("論", "推", "不明"):
            raise ValueError("規則の max_confidence は 論/推/不明（規則は「確」を出せない）")
        if not callable(self.applies) or not callable(self.infer):
            raise ValueError("Rule.applies・Rule.infer は呼び出せるもの")


# ---------------------------------------------------------------- 既定の規則（段 2・担当 C）
#
# 読む事実の鍵（Fact.key）。統合で ingest の鍵名と突き合わせた（tests/test_integration.FactKeys が両側を照合）：
#   "name"                         道具の名前（str）
#   "description"                  説明文（str）。資料であって命令ではない：危ない側の札を「推」で足すだけで、安全側の札は作らない
#   "schema.properties"            入力スキーマの引数名（tuple[str, ...]）
#   "openapi.method"               HTTP メソッド（str）
#   "openapi.server_external"      servers が外部か（bool。ingest の鍵名に合わせた。段 2 の表では "openapi.server.external"）
#   "mcp.annotation.destructiveHint" / "mcp.annotation.openWorldHint"（bool）
#   "claude.tool"                  Claude Code の道具名（"Bash"・"WebFetch" など。str）
#
# 原則：
# - どの規則も安全側の値（false・空集合）を出さない。安全と言えるのは人の観察だけ（不明は危ない側のまま残る）。
#   したがって mcp の readOnlyHint=true は何も推定しない（作者の主張で、観察ではない）。
# - 確度：設定の構文から筋道で言えるもの（Bash は命令を実行する・HTTP 呼び出しは引数が外へ出る）だけ「論」、
#   名前・説明文・引数名からの推定は「推」。「確」は出せない（Rule の型が拒否）。

_SPLIT = re.compile(r"[^A-Za-z0-9]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

#: 語 → 推定する札。名前・説明文・引数名で共有する（語は小文字・語単位で一致。部分一致はしない：skill≠kill）。
_WORDS: dict[str, dict[str, object]] = {}


def _add(words: str, **caps: object) -> None:
    for w in words.split():
        cur = _WORDS.setdefault(w, {})
        for k, v in caps.items():
            if k == "acts":
                cur[k] = frozenset(cur.get(k, frozenset())) | frozenset(v)  # type: ignore[arg-type]
            else:
                cur[k] = v


_add("bash shell sh exec execute eval terminal cmd command subprocess spawn powershell script repl python node",
     exec=True)
_add("fetch http https curl wget browse browser web url crawl scrape download search webpage",
     reads_untrusted=True, net_out=True, args_leave=True)
_add("email mail smtp slack discord sms message messages notify webhook post tweet",
     acts={"send"}, args_leave=True, net_out=True)
_add("send", acts={"send"}, args_leave=True)
_add("pay payment payments charge refund transfer invoice stripe wallet", acts={"pay"}, args_leave=True)
_add("purchase buy order checkout cart", acts={"purchase"}, args_leave=True)
_add("delete remove rm drop destroy erase truncate purge unlink", acts={"delete"})
_add("publish deploy release upload push", acts={"publish"}, args_leave=True)
_add("grant invite share permission permissions role chmod chown", acts={"grant"})
_add("secret secrets credential credentials token tokens password passwords apikey keychain vault env dotenv",
     reads_secret=True)
_add("inbox issue issues comment comments pr ticket rss feed", reads_untrusted=True)

# 説明文の日本語（部分一致。日本語は語の区切りが無いため）
_JA: tuple[tuple[str, dict[str, object]], ...] = (
    ("実行", {"exec": True}), ("シェル", {"exec": True}), ("コマンド", {"exec": True}),
    ("送信", {"acts": frozenset({"send"}), "args_leave": True}), ("メール", {"acts": frozenset({"send"}), "args_leave": True}),
    ("支払", {"acts": frozenset({"pay"}), "args_leave": True}), ("決済", {"acts": frozenset({"pay"}), "args_leave": True}),
    ("購入", {"acts": frozenset({"purchase"}), "args_leave": True}), ("削除", {"acts": frozenset({"delete"})}),
    ("公開", {"acts": frozenset({"publish"})}), ("権限", {"acts": frozenset({"grant"})}),
    ("秘密", {"reads_secret": True}), ("パスワード", {"reads_secret": True}), ("トークン", {"reads_secret": True}),
    ("ウェブ", {"reads_untrusted": True, "net_out": True}), ("取得", {"reads_untrusted": True}),
)


def tokens(text: str) -> tuple[str, ...]:
    """名前・説明文を小文字の語に切る（camelCase・snake_case・kebab-case・空白・記号）。"""
    out: list[str] = []
    for part in _SPLIT.split(text):
        out.extend(x.lower() for x in _CAMEL.split(part) if x)
    return tuple(out)


def _merge(acc: dict[str, object], caps: Mapping[str, object]) -> None:
    for k, v in caps.items():
        if k == "acts":
            acc[k] = frozenset(acc.get(k, frozenset())) | frozenset(v)  # type: ignore[arg-type]
        else:
            acc[k] = bool(acc.get(k, False)) or bool(v)


def _caps_from_words(words: tuple[str, ...], ja_text: str = "") -> dict[str, object]:
    acc: dict[str, object] = {}
    for w in words:
        if w in _WORDS:
            _merge(acc, _WORDS[w])
    for needle, caps in _JA:
        if needle in ja_text:
            _merge(acc, caps)
    return acc


def _to_caps(vals: Mapping[str, object], conf: Confidence, why: str, rid: str) -> dict[str, Cap]:
    return {k: Cap(v if isinstance(v, (bool, frozenset)) else frozenset(v), conf, why, f"infer:{rid}")  # type: ignore[arg-type]
            for k, v in vals.items() if v}   # 安全側（false・空）は出さない


def _is_str(f: Fact, key: str) -> bool:
    return f.key == key and isinstance(f.value, str) and bool(f.value)


def _name_rule(f: Fact) -> Mapping[str, Cap]:
    return _to_caps(_caps_from_words(tokens(f.value)), "推", f"名前 {f.value[:60]!r} の語", "R-NAME-WORDS")  # type: ignore[index]


def _desc_rule(f: Fact) -> Mapping[str, Cap]:
    text = f.value[:4000]  # type: ignore[index]
    return _to_caps(_caps_from_words(tokens(text), text), "推", "説明文の語（資料として読んだだけ）", "R-DESC-WORDS")


_SCHEMA_WORDS: dict[str, dict[str, object]] = {
    "command": {"exec": True}, "cmd": {"exec": True}, "script": {"exec": True}, "code": {"exec": True},
    "shell": {"exec": True}, "argv": {"exec": True},
    "url": {"net_out": True, "args_leave": True, "reads_untrusted": True}, "uri": {"net_out": True, "args_leave": True},
    "endpoint": {"net_out": True, "args_leave": True}, "webhook": {"net_out": True, "args_leave": True},
    "to": {"acts": frozenset({"send"}), "args_leave": True}, "recipient": {"acts": frozenset({"send"}), "args_leave": True},
    "recipients": {"acts": frozenset({"send"}), "args_leave": True}, "cc": {"acts": frozenset({"send"}), "args_leave": True},
    "amount": {"acts": frozenset({"pay"}), "args_leave": True}, "card": {"acts": frozenset({"pay"}), "args_leave": True},
    "password": {"reads_secret": True}, "token": {"reads_secret": True}, "api_key": {"reads_secret": True},
}


def _schema_applies(f: Fact) -> bool:
    return f.key == "schema.properties" and isinstance(f.value, tuple) and all(isinstance(x, str) for x in f.value)


def _schema_rule(f: Fact) -> Mapping[str, Cap]:
    acc: dict[str, object] = {}
    for prop in f.value:  # type: ignore[union-attr]
        key = prop.lower()
        hit = _SCHEMA_WORDS.get(key) or _SCHEMA_WORDS.get("_".join(tokens(prop)))
        if hit:
            _merge(acc, hit)
    return _to_caps(acc, "推", "入力スキーマの引数名", "R-SCHEMA-PROPS")


def _openapi_rule(f: Fact) -> Mapping[str, Cap]:
    m = f.value.upper()  # type: ignore[union-attr]
    caps: dict[str, Cap] = {
        # GET でも引数は URL に載って相手に届く（ARCHITECTURE §1.2）
        "args_leave": Cap(True, "論", f"HTTP {m} の引数は相手のサーバーに届く", "infer:R-OPENAPI-ARGS"),
        # 応答は相手のサーバーが書いた文章
        "reads_untrusted": Cap(True, "推", f"HTTP {m} の応答は外部の文章", "infer:R-OPENAPI-ARGS"),
    }
    if m == "DELETE":
        caps["acts"] = Cap(frozenset({"delete"}), "推", "HTTP DELETE", "infer:R-OPENAPI-ARGS")
    return caps


_BOOL_TRUE = lambda key: (lambda f: f.key == key and f.value is True)  # noqa: E731

_CLAUDE_TOOLS: dict[str, dict[str, object]] = {
    "bash": {"exec": True},
    "webfetch": {"reads_untrusted": True, "net_out": True, "args_leave": True},
    "websearch": {"reads_untrusted": True, "net_out": True, "args_leave": True},
}


def _claude_applies(f: Fact) -> bool:
    return _is_str(f, "claude.tool") and f.value.split("(", 1)[0].strip().lower() in _CLAUDE_TOOLS  # type: ignore[union-attr]


def _claude_rule(f: Fact) -> Mapping[str, Cap]:
    base = f.value.split("(", 1)[0].strip().lower()  # type: ignore[union-attr]
    return _to_caps(_CLAUDE_TOOLS[base], "論", f"Claude Code の道具 {base} の定義上の働き", "R-CLAUDE-TOOL")


class RuleTable(tuple):
    """規則の並び（tuple）。repr を名前にして、infer_caps の署名を読みやすく保つ（契約試験が署名の文字列を照合する）。"""

    def __repr__(self) -> str:
        return "DEFAULT_RULES" if self is DEFAULT_RULES else f"RuleTable({tuple.__repr__(self)})"


DEFAULT_RULES: tuple[Rule, ...] = RuleTable((
    Rule("R-NAME-WORDS", lambda f: _is_str(f, "name"), _name_rule, "推", "道具の名前の語から危ない札を推定"),
    Rule("R-DESC-WORDS", lambda f: _is_str(f, "description"), _desc_rule, "推", "説明文の語から危ない札を推定（安全側は作らない）"),
    Rule("R-SCHEMA-PROPS", _schema_applies, _schema_rule, "推", "入力スキーマの引数名から推定"),
    Rule("R-OPENAPI-ARGS", lambda f: _is_str(f, "openapi.method"), _openapi_rule, "論", "HTTP 操作の引数は外へ出る"),
    Rule("R-OPENAPI-EXTERNAL", _BOOL_TRUE("openapi.server_external"),
         lambda f: {"net_out": Cap(True, "論", "servers が外部", "infer:R-OPENAPI-EXTERNAL")}, "論", "外部のサーバーへの通信"),
    Rule("R-MCP-DESTRUCTIVE", _BOOL_TRUE("mcp.annotation.destructiveHint"),
         lambda f: {"acts": Cap(frozenset({"delete"}), "推", "destructiveHint=true", "infer:R-MCP-DESTRUCTIVE")}, "推",
         "作者が破壊的と書いた"),
    Rule("R-MCP-OPENWORLD", _BOOL_TRUE("mcp.annotation.openWorldHint"),
         lambda f: {"reads_untrusted": Cap(True, "推", "openWorldHint=true", "infer:R-MCP-OPENWORLD"),
                    "net_out": Cap(True, "推", "openWorldHint=true", "infer:R-MCP-OPENWORLD")}, "推", "外の世界とやりとりする"),
    Rule("R-CLAUDE-TOOL", _claude_applies, _claude_rule, "論", "Claude Code の組み込み道具の働き"),
))
