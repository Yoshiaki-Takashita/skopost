#!/usr/bin/env python3
"""Skopost の互換の入口（v1.0.0 と同じ使い方・終了コード・出力）。

本体は同じ階層の skopost/ パッケージ。`python3 skopost.py ...` はパッケージの cli.main を呼ぶだけ。
`python3 -m skopost ...` でも同じ。使い方は `python3 skopost.py --help`。
"""
from __future__ import annotations

import os
import sys

if __name__ == "__main__":
    # スクリプトとして走るとき sys.path[0] はこのファイルの階層。同名のパッケージ skopost/ が先に解決される
    # （tests/test_cli_compat.py の ImportPrecedence が確かめる）。念のため明示的に先頭へ置く。
    _here = os.path.dirname(os.path.abspath(__file__))
    if not sys.path or os.path.abspath(sys.path[0] or os.curdir) != _here:
        sys.path.insert(0, _here)
    from skopost.cli import main

    sys.exit(main())
else:  # pragma: no cover - パッケージが優先されるので通常ここには来ない
    raise ImportError("skopost.py が import されました。同じ階層の skopost/ パッケージが見えていません（sys.path を確認）")
