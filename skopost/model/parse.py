"""型付きの読み込み：JSON（v1・v2）→ Config。

設計：v2 の追加鍵（tool.origin・observed.*.source・imports）を先に取り分けて検証し、残りを v1 の検証器
（`model.validate.validate`）に通す。こうすると v1 の意味・誤りの文言を一か所で守れ、v1 の入力は v2 で読んでも
同じ Config になる（ARCHITECTURE M1）。
"""
from __future__ import annotations

import os
from typing import Any

from .constants import (IMPORT_KEYS, MAX_FILE_BYTES, MAX_IMPORTS, ORIGIN_KEYS, SHA256_RE, SOURCE_RE, TOOL_KEYS_V2,
                        TOP_KEYS_V2)
from .convert import from_legacy
from .errors import SkopostError
from .migrate import migrate, spec_version_of
from .safe import safe
from .types import Config, ImportRecord, Origin
from .validate import read_json_file, validate


def _expect(cond: bool, msg: str, where: str = "") -> None:
    if not cond:
        raise SkopostError(msg, where=where)


def _parse_origin(v: Any, where: str) -> Origin:
    _expect(isinstance(v, dict), f"{where}: オブジェクトが要ります", where)
    unk = set(v) - ORIGIN_KEYS
    _expect(not unk, f"{where}: 未知の鍵 {', '.join(sorted(safe(k, 30) for k in unk))}", where)
    f = v.get("file")
    _expect(isinstance(f, str) and 0 < len(f) <= 4096, f"{where}.file: 1〜4096 字の文字列", where)
    p = v.get("pointer", "")
    _expect(isinstance(p, str) and (p == "" or p.startswith("/")) and len(p) <= 4096,
            f"{where}.pointer: '' か '/' で始まる JSON Pointer", where)
    line = v.get("line")
    _expect(line is None or (isinstance(line, int) and not isinstance(line, bool) and 1 <= line <= 10_000_000),
            f"{where}.line: 1 以上の整数", where)
    return Origin(file=f, pointer=p, line=line)


def _parse_imports(v: Any) -> tuple[ImportRecord, ...]:
    _expect(isinstance(v, list) and len(v) <= MAX_IMPORTS, f"imports は配列で {MAX_IMPORTS} 個まで", "/imports")
    out = []
    for i, x in enumerate(v):
        where = f"imports[{i}]"
        _expect(isinstance(x, dict), f"{where}: オブジェクトが要ります", f"/imports/{i}")
        unk = set(x) - IMPORT_KEYS
        _expect(not unk, f"{where}: 未知の鍵 {', '.join(sorted(safe(k, 30) for k in unk))}", f"/imports/{i}")
        f, h, a = x.get("file"), x.get("sha256"), x.get("adapter", "native")
        _expect(isinstance(f, str) and 0 < len(f) <= 4096, f"{where}.file: 1〜4096 字の文字列", f"/imports/{i}/file")
        _expect(isinstance(h, str) and bool(SHA256_RE.match(h)), f"{where}.sha256: 小文字 16 進 64 字", f"/imports/{i}/sha256")
        _expect(isinstance(a, str) and bool(SOURCE_RE.match(f"ingest:{a}")), f"{where}.adapter: 英小文字・数字・- の 1〜32 字",
                f"/imports/{i}/adapter")
        out.append(ImportRecord(file=f, sha256=h, adapter=a))
    return tuple(out)


def parse(data: Any) -> Config:
    """v1 か v2 の入力を検証し、型付きの Config（正規化後は v2）を返す。誤りは SkopostError だけ。"""
    if spec_version_of(data) == 1:
        # v1 の入力は v1 の検証器だけで読む（v2 の鍵が紛れていれば v1 の規則どおり「未知の鍵」で拒否）
        return from_legacy(validate(data))
    d = migrate(data)
    unknown = set(d) - TOP_KEYS_V2
    _expect(not unknown, f"未知の鍵：{', '.join(sorted(safe(k, 30) for k in unknown))}")
    imports = _parse_imports(d["imports"]) if "imports" in d else ()

    stripped: dict[str, Any] = {k: v for k, v in d.items() if k != "imports"}
    stripped["skopost"] = 1
    origins: dict[str, Origin] = {}
    sources: dict[tuple[str, str], str] = {}
    raw_tools = d.get("tools")
    if isinstance(raw_tools, list):
        new_tools = []
        for i, t in enumerate(raw_tools):
            if not isinstance(t, dict):
                new_tools.append(t)          # 誤りの報告は v1 の検証器に任せる
                continue
            unk = set(t) - TOOL_KEYS_V2
            _expect(not unk, f"tools[{i}]: 未知の鍵 {', '.join(sorted(safe(k, 30) for k in unk))}", f"/tools/{i}")
            t2 = dict(t)
            tid = t.get("id")
            if "origin" in t2:
                o = _parse_origin(t2.pop("origin"), f"tools[{i}].origin")
                if isinstance(tid, str):
                    origins[tid] = o
            obs = t2.get("observed")
            if isinstance(obs, dict):
                obs2 = {}
                for cap, v in obs.items():
                    if isinstance(v, dict) and "source" in v:
                        v2 = dict(v)
                        src = v2.pop("source")
                        _expect(isinstance(src, str) and bool(SOURCE_RE.match(src)),
                                f"tools[{i}].observed.{safe(cap, 30)}.source: manual・ingest:<名>・infer:<規則ID> のどれか",
                                f"/tools/{i}/observed/{cap}/source")
                        _expect(not (src != "manual" and v2.get("confidence") in ("確", "sure")),
                                f"tools[{i}].observed.{safe(cap, 30)}: 取り込み・規則由来（{safe(src, 40)}）の札に「確」は付けられません",
                                f"/tools/{i}/observed/{cap}")
                        if isinstance(tid, str):
                            sources[(tid, cap)] = src
                        obs2[cap] = v2
                    else:
                        obs2[cap] = v
                t2["observed"] = obs2
            new_tools.append(t2)
        stripped["tools"] = new_tools
    legacy = validate(stripped)
    return from_legacy(legacy, origins=origins, sources=sources, imports=imports)


def load(path: str | os.PathLike[str], *, max_bytes: int = MAX_FILE_BYTES) -> Config:
    """ファイルから型付きで読む（大きさを先に確かめる）。"""
    return parse(read_json_file(path, max_bytes=max_bytes))
