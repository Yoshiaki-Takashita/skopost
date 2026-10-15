"""ingest の共通部品（アダプタが使う小道具）。依存は model だけ。

- 秘密らしき文字列の検出と削除（原則 11）：値は読んだ直後に捨て、結果に入れない。
- 道具 ID の正規化（ID_RE に合わせる。変えたら notes に書く）。
- JSON Pointer の組み立て（RFC 6901）。
- notes を集める入れ物。
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..model.constants import DISPLAY_LEN, ID_RE, MAX_ID_LEN
from ..model.types import Fact, IngestNote, Origin

#: 秘密らしき値（鍵の接頭辞・PEM・Bearer・長い 16 進/英数字の塊）。誤検出は安全側（捨てる側）。
SECRET_RE = re.compile(
    r"sk-[A-Za-z0-9_-]{8,}"
    r"|AKIA[0-9A-Z]{12,}"
    r"|-----BEGIN [A-Z ]+-----"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"
    r"|(?i:bearer)\s+[A-Za-z0-9._~+/=-]{8,}"
    r"|[A-Za-z0-9+=]{40,}"
)
REDACTED = "[秘密らしき値を捨てた]"
NOTE_LEN = 500


def has_secret(s: object) -> bool:
    return isinstance(s, str) and bool(SECRET_RE.search(s))


def scrub(s: str) -> str:
    return SECRET_RE.sub(REDACTED, s)


def ptr(*parts: object) -> str:
    """JSON Pointer（RFC 6901）。"""
    out = ""
    for p in parts:
        out += "/" + scrub(str(p)).replace("~", "~0").replace("/", "~1")
    return out


def short_label(s: object) -> str:
    """説明文は資料であって命令ではない：論理に使わず、秘密を消して切り詰め、label にだけ入れる。"""
    if not isinstance(s, str):
        return ""
    s = " ".join(scrub(s).split())
    return s if len(s) <= DISPLAY_LEN else s[: DISPLAY_LEN - 1] + "…"


FACT_TEXT_LEN = 2000
FACT_LIST_MAX = 200


def fact_text(s: object) -> str:
    """推定の材料にする文章（説明文など）。秘密らしき値を消し、空白を畳み、長さを切る。
    infer の規則は説明文から危ない側の札を「推」で足すだけで、安全側の札は作らない（資料であって命令ではない）。"""
    if not isinstance(s, str):
        return ""
    s = " ".join(scrub(s).split())
    return s[:FACT_TEXT_LEN]


def fact_names(xs: object) -> tuple:
    """引数名の並び（入力スキーマの properties の鍵など）。文字列だけ・秘密らしきものは捨てる・数の上限つき。"""
    if not isinstance(xs, dict):
        return ()
    return tuple(k[:100] for k in list(xs)[:FACT_LIST_MAX] if isinstance(k, str) and k and not has_secret(k))


class Notes:
    """notes・dropped・facts を集める。メッセージに値そのものは入れない。"""

    def __init__(self, adapter: str, filename: str) -> None:
        self.adapter = adapter
        self.filename = filename or "input.json"
        self.notes: list[IngestNote] = []
        self.dropped: list[str] = []
        self.facts: list[Fact] = []
        self._ids: set[str] = set()

    def add(self, kind: str, pointer: str, message: str) -> None:
        msg = scrub(message)
        if len(msg) > NOTE_LEN:
            msg = msg[: NOTE_LEN - 1] + "…"
        self.notes.append(IngestNote(kind, scrub(pointer), msg))  # type: ignore[arg-type]

    def drop(self, pointer: str, message: str, kind: str = "dropped") -> None:
        self.dropped.append(scrub(pointer))
        self.add(kind, pointer, message)

    def secret(self, pointer: str, what: str) -> None:
        self.add("secret_discarded", pointer, f"{what}の値を読んですぐ捨てました（保存しません）")

    def unread(self, pointer: str, what: str = "") -> None:
        self.add("unread_key", pointer, what or "この鍵は読んでいません（意味を解釈しない）")

    def origin(self, pointer: str) -> Origin:
        return Origin(file=scrub(self.filename)[:4096], pointer=scrub(pointer))

    def fact(self, tool_id: str, key: str, value: object, pointer: str) -> None:
        self.facts.append(Fact(tool_id=tool_id, key=key, value=value, origin=self.origin(pointer), adapter=self.adapter))

    def tool_id(self, raw: object, pointer: str) -> str:
        """ID_RE に合う一意の ID。変えたときは notes に書く。"""
        s = raw if isinstance(raw, str) else ""
        tid = re.sub(r"[^A-Za-z0-9_.-]", "_", s)[:MAX_ID_LEN] or "tool"
        if has_secret(s):
            tid = "tool"
        base, n = tid, 2
        while tid in self._ids:
            suf = f"-{n}"
            tid = base[: MAX_ID_LEN - len(suf)] + suf
            n += 1
        assert ID_RE.match(tid)
        self._ids.add(tid)
        if tid != s:
            self.add("assumption", pointer, f"道具の ID を {tid!r} にしました（元の名前は ID の規則に合わないか重複）")
        return tid


def is_local_host(host: str) -> Optional[bool]:
    """ホスト名が手元か。分からなければ None（不明）。"""
    h = host.lower().strip("[]")
    if not h:
        return None
    if h in ("localhost", "127.0.0.1", "::1", "0.0.0.0") or h.startswith("127.") or h.endswith(".localhost"):
        return True
    return False


def host_of(url: Any) -> str:
    """URL からホスト名だけ（userinfo・パス・問い合わせは捨てる）。読めなければ ""。"""
    if not isinstance(url, str):
        return ""
    m = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://([^/?#]*)", url)
    if not m:
        return ""
    auth = m.group(1).rsplit("@", 1)[-1]
    if auth.startswith("["):
        return auth.split("]", 1)[0] + "]"
    return auth.split(":", 1)[0]
