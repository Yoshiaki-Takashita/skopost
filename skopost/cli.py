"""cli：引数解析とサブコマンドの配線だけ（ロジックを持たない）。

挙動・文言・終了コードは単一ファイル時代（v1.0.0）と同一。

統合（段 2 の後）：
- 既存の使い方（check の md・json、validate、example）は compat.v1 のまま（バイト互換。切り替えていない）。
- 新しい引数は通しの流れ（pipeline：ingest → infer → graph → report）を使う：
  ``--format text|sarif``、``--baseline FILE``（新しく増えた道だけで終了 2）、``--adapter auto|native|mcp|openapi|claude-settings``
  （取り込み。指定しなければ v1 の検証器で読む）。md・json でもこれらを付けたときは新しい流れ。
- ``baseline 宣言.json [--adapter A] [--out FILE]``：基準線（ci.write_baseline）を出す。
- --help の文は v1.0.0 と同じ（互換試験が守る）。新しい引数は docs/ARCHITECTURE.md「統合の結果」に書いた。
"""
from __future__ import annotations

import json
import os
import sys

from .compat.v1 import analyze, report_md
from .model.errors import SkopostError
from .model.examples import EXAMPLE
from .model.safe import safe
from .model.validate import load_file
from .ci.api import write_baseline
from .pipeline import ADAPTER_CHOICES, render_outcome, run

#: --help の文（v1.0.0 の skopost.py の docstring と一字一句同じ。互換試験が守る）
USAGE = """Skopost — 見張りの持ち場：AI エージェントの道具の札から「危ない道」を数え、最小の確認点を出す。

標準ライブラリのみ。外へ通信しない。既定では何も書かない（--out を付けたときだけ 1 ファイル書く）。
仕様は SPEC.md。設計は DESIGN.md。限界は LIMITATIONS.md。

使い方:
  python3 skopost.py check 宣言.json [--format md|json] [--explain] [--out FILE]
  python3 skopost.py validate 宣言.json
  python3 skopost.py example > my.json
"""


def _usage() -> str:
    return USAGE


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(_usage())
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "example":
        print(json.dumps(EXAMPLE, ensure_ascii=False, indent=2))
        return 0
    if cmd not in ("check", "validate", "baseline"):
        print(f"未知のコマンド {safe(cmd, 30)!r}。check / validate / example", file=sys.stderr)
        return 1
    fmt, explain, out, path, baseline, adapter = "md", False, None, None, None, None
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--format":
            i += 1
            fmt = rest[i] if i < len(rest) else ""
            if fmt not in ("md", "json", "text", "sarif"):
                print("--format は md か json（新しい流れでは text・sarif も）", file=sys.stderr)
                return 1
        elif a == "--explain":
            explain = True
        elif a == "--out":
            i += 1
            out = rest[i] if i < len(rest) else None
        elif a == "--baseline":
            i += 1
            baseline = rest[i] if i < len(rest) else ""
            if not baseline:
                print("--baseline には基準線のファイルが要ります", file=sys.stderr)
                return 1
        elif a == "--adapter":
            i += 1
            adapter = rest[i] if i < len(rest) else ""
            if adapter not in ADAPTER_CHOICES:
                print(f"--adapter は {' / '.join(ADAPTER_CHOICES)} のどれか", file=sys.stderr)
                return 1
        elif a.startswith("-"):
            print(f"未知の引数 {safe(a, 30)!r}", file=sys.stderr)
            return 1
        else:
            path = a
        i += 1
    if not path:
        print("宣言ファイルのパスが要ります", file=sys.stderr)
        return 1
    legacy = cmd != "baseline" and fmt in ("md", "json") and baseline is None and adapter is None
    if legacy:
        try:
            cfg = load_file(path)
        except (SkopostError, OSError, UnicodeDecodeError) as e:
            print(f"入力の誤り：{safe(str(e), 300)}", file=sys.stderr)
            return 1
        if cmd == "validate":
            print(f"OK：道具 {len(cfg['tools'])}・置き場 {len(cfg['stores'])}")
            return 0
        res = analyze(cfg)
        text = json.dumps(res, ensure_ascii=False, indent=2) + "\n" if fmt == "json" else report_md(res, cfg, explain)
        code = res["exit_code"]
    else:
        try:
            o = run(path, adapter=adapter, baseline=baseline)
        except (SkopostError, OSError, UnicodeDecodeError) as e:
            print(f"入力の誤り：{safe(str(e), 300)}", file=sys.stderr)
            return 1
        for n in o.notes:
            print(f"取り込み：{n.kind} {safe(n.pointer, 120)} {safe(n.message, 200)}", file=sys.stderr)
        if cmd == "validate":
            print(f"OK：道具 {len(o.cfg.tools)}・置き場 {len(o.cfg.stores)}")
            return 0
        if cmd == "baseline":
            text, code = write_baseline(o.result), 0
        else:
            text, code = render_outcome(o, fmt, explain=explain), o.exit_code
        if o.baseline_diff is not None:
            d = o.baseline_diff
            print(f"基準線との差：増えた道 {len(d.added)}・消えた道 {len(d.removed)}・変わらない道 {len(d.unchanged)}",
                  file=sys.stderr)
            for kind, key in d.added:
                print(f"  増えた道：{kind}: {safe(key, 200)}", file=sys.stderr)
    if out:
        if os.path.exists(out):
            print(f"{safe(out, 100)} は既にあります。上書きはしません", file=sys.stderr)
            return 1
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"書きました：{safe(out, 100)}")
    else:
        sys.stdout.write(text)
    return code
