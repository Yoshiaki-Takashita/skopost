"""v1 の読み込みと検証（旧 API・辞書を返す）。

`skopost.py` 単一ファイル時代の `load_file` / `validate` をそのまま移したもの。挙動・文言は一字も変えない
（既存の試験・CLI・JSON 出力の互換のため）。型付きの読み込みは `model.parse`。
"""
from __future__ import annotations

import json
import os
from typing import Any

from .constants import (ACT_KINDS, ALL_CAPS, BOOL_CAPS, CONF_ALIAS, ID_RE, MAX_FILE_BYTES, MAX_ID_LEN,
                        MAX_STORES, MAX_TOOLS, SPEC_VERSION, STORE_KEYS, TOOL_KEYS, TOP_KEYS)
from .errors import SkopostError
from .safe import safe


def read_json_file(path: str | os.PathLike[str], *, max_bytes: int = MAX_FILE_BYTES) -> Any:
    """大きさを先に確かめてから読む。壊れた JSON は SkopostError。"""
    size = os.path.getsize(path)
    if size > max_bytes:
        raise SkopostError(f"ファイルが大きすぎます（{size} バイト > {max_bytes}）。読まずに止めました")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read(max_bytes + 1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:  # noqa: PERF203
        raise SkopostError(f"JSON が壊れています：{e.msg}（{e.lineno} 行 {e.colno} 桁）") from None


def load_file(path: str) -> dict:
    return validate(read_json_file(path))


def _expect(cond: bool, msg: str) -> None:
    if not cond:
        raise SkopostError(msg)


def _norm_conf(v: Any, where: str) -> str:
    _expect(isinstance(v, str) and v in CONF_ALIAS, f"{where}: 確度は 確/論/推/不明（sure/derived/guess/unknown）のどれか")
    return CONF_ALIAS[v]


def _norm_cap_value(cap: str, v: Any, where: str) -> Any:
    if cap in BOOL_CAPS:
        _expect(isinstance(v, bool), f"{where}.{cap}: 真偽値（true/false）が要ります")
        return v
    _expect(isinstance(v, list) and all(isinstance(x, str) for x in v), f"{where}.{cap}: 文字列の配列が要ります")
    if cap == "acts":
        for x in v:
            _expect(x in ACT_KINDS, f"{where}.acts: 未知の操作 {safe(x, 30)!r}。使えるのは {', '.join(ACT_KINDS)}")
    return sorted(set(v))


def validate(data: Any) -> dict:
    """構造を検証し、正規化した辞書を返す。未知の鍵は誤りにする（打ち間違いで札が抜けるのを防ぐ）。"""
    _expect(isinstance(data, dict), "最上位は JSON オブジェクトが要ります")
    unknown = set(data) - TOP_KEYS
    _expect(not unknown, f"未知の鍵：{', '.join(sorted(safe(k, 30) for k in unknown))}")
    _expect(data.get("skopost") == SPEC_VERSION, f'"skopost": {SPEC_VERSION} が要ります')
    name = data.get("name", "")
    _expect(isinstance(name, str), "name は文字列")
    uic = data.get("untrusted_in_context", True)
    _expect(isinstance(uic, bool), "untrusted_in_context は真偽値")

    stores: dict[str, dict] = {}
    raw_stores = data.get("stores", [])
    _expect(isinstance(raw_stores, list) and len(raw_stores) <= MAX_STORES, f"stores は配列で {MAX_STORES} 個まで")
    for i, s in enumerate(raw_stores):
        where = f"stores[{i}]"
        _expect(isinstance(s, dict), f"{where}: オブジェクトが要ります")
        unk = set(s) - STORE_KEYS
        _expect(not unk, f"{where}: 未知の鍵 {', '.join(sorted(safe(k, 30) for k in unk))}")
        sid = s.get("id")
        _expect(isinstance(sid, str) and ID_RE.match(sid or ""), f"{where}: id は英数字・_ . - の 1〜{MAX_ID_LEN} 字")
        _expect(sid not in stores, f"{where}: id {sid!r} が重複")
        for k in ("external", "executes", "secret"):
            _expect(isinstance(s.get(k, False), bool), f"{where}.{k}: 真偽値")
        stores[sid] = {"id": sid, "label": str(s.get("label", sid)),
                       "external": s.get("external", False), "executes": s.get("executes", False),
                       "secret": s.get("secret", False)}

    raw_tools = data.get("tools")
    _expect(isinstance(raw_tools, list) and raw_tools, "tools は 1 個以上の配列が要ります")
    _expect(len(raw_tools) <= MAX_TOOLS, f"tools は {MAX_TOOLS} 個まで（{len(raw_tools)} 個）")
    tools: list[dict] = []
    seen: set[str] = set()
    for i, t in enumerate(raw_tools):
        where = f"tools[{i}]"
        _expect(isinstance(t, dict), f"{where}: オブジェクトが要ります")
        unk = set(t) - TOOL_KEYS
        _expect(not unk, f"{where}: 未知の鍵 {', '.join(sorted(safe(k, 30) for k in unk))}")
        tid = t.get("id")
        _expect(isinstance(tid, str) and ID_RE.match(tid or ""), f"{where}: id は英数字・_ . - の 1〜{MAX_ID_LEN} 字")
        _expect(tid not in seen, f"{where}: id {tid!r} が重複")
        seen.add(tid)
        mode = t.get("mode", "allow")
        _expect(mode in ("allow", "ask"), f"{where}.mode: allow か ask")
        freq = t.get("frequency", 1)
        _expect(isinstance(freq, int) and not isinstance(freq, bool) and 1 <= freq <= 1_000_000, f"{where}.frequency: 1 以上の整数")
        declared_raw = t.get("declared", {})
        _expect(isinstance(declared_raw, dict), f"{where}.declared: オブジェクト")
        declared: dict[str, Any] = {}
        for cap, v in declared_raw.items():
            _expect(cap in ALL_CAPS, f"{where}.declared: 未知の項目 {safe(cap, 30)!r}")
            declared[cap] = _norm_cap_value(cap, v, f"{where}.declared")
        observed_raw = t.get("observed", {})
        _expect(isinstance(observed_raw, dict), f"{where}.observed: オブジェクト")
        observed: dict[str, dict] = {}
        for cap, v in observed_raw.items():
            _expect(cap in ALL_CAPS, f"{where}.observed: 未知の項目 {safe(cap, 30)!r}")
            if isinstance(v, dict):
                unk2 = set(v) - {"value", "confidence", "evidence"}
                _expect(not unk2, f"{where}.observed.{cap}: 未知の鍵")
                conf = _norm_conf(v.get("confidence", "推"), f"{where}.observed.{cap}")
                val = None if conf == "不明" else _norm_cap_value(cap, v.get("value"), f"{where}.observed")
                observed[cap] = {"value": val, "confidence": conf, "evidence": str(v.get("evidence", ""))}
            else:
                observed[cap] = {"value": _norm_cap_value(cap, v, f"{where}.observed"), "confidence": "推", "evidence": ""}
        for cap in ("writes_stores", "reads_stores"):
            for src in (declared.get(cap, []), (observed.get(cap) or {}).get("value") or []):
                for sid in src:
                    _expect(sid in stores, f"{where}.{cap}: 置き場 {safe(sid, 30)!r} が stores にありません")
        tools.append({"id": tid, "label": str(t.get("label", tid)), "mode": mode, "frequency": freq,
                      "declared": declared, "observed": observed})
    return {"skopost": SPEC_VERSION, "name": name, "untrusted_in_context": uic, "stores": stores, "tools": tools}
