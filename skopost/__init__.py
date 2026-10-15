"""Skopost — 見張りの持ち場：AI エージェントの道具の札から「危ない道」を数え、最小の確認点を出す。

標準ライブラリのみ。外へ通信しない。既定では何も書かない。構成は docs/ARCHITECTURE.md。

`import skopost as S` で単一ファイル時代（v1.0.0）の名前がすべて使える（再輸出。既存の bench.py・verify.py・
試験のため）。新しいコードは型付きの API（`skopost.model` など）を使うこと。

注意：`skopost.py`（互換の入口）とこのパッケージは同じ階層にあり、`import skopost` は**パッケージが優先**される
（tests/test_cli_compat.py の ImportPrecedence が確かめる。ARCHITECTURE「不明」欄 参照）。
"""
from __future__ import annotations

# ---- v1.0.0 の公開名（互換のため再輸出。名前・意味を変えない）
from .cli import _usage, main
from .compat.v1 import (KIND_JA, _layer_value, _min_conf, analyze, apply_checkpoints, effective, harm_paths,
                        mismatches, min_checkpoints, path_key, report_md)
from .model.constants import (ACT_KINDS, ALL_CAPS, BOOL_CAPS, CONF_ALIAS, CONF_ORDER, DISPLAY_LEN, EXACT_LIMIT, ID_RE,
                              LIST_CAPS, MAX_ALTERNATIVES, MAX_FILE_BYTES, MAX_ID_LEN, MAX_STORES, MAX_TOOLS,
                              SPEC_VERSION, STORE_KEYS, TOOL_KEYS, TOP_KEYS)
from .model.errors import SkopostError
from .model.examples import EXAMPLE
from .model.safe import safe
from .model.validate import _expect, _norm_cap_value, _norm_conf, load_file, validate
from .model.version import __version__

#: v1.0.0 の skopost.py が持っていた公開名（互換試験 test_cli_compat が、全部あることを確かめる）
V1_NAMES = (
    "SPEC_VERSION", "MAX_FILE_BYTES", "MAX_TOOLS", "MAX_STORES", "MAX_ID_LEN", "EXACT_LIMIT", "MAX_ALTERNATIVES",
    "DISPLAY_LEN", "ID_RE", "BOOL_CAPS", "LIST_CAPS", "ALL_CAPS", "ACT_KINDS", "CONF_ORDER", "CONF_ALIAS",
    "TOOL_KEYS", "STORE_KEYS", "TOP_KEYS", "SkopostError", "safe", "load_file", "validate", "effective",
    "harm_paths", "path_key", "min_checkpoints", "apply_checkpoints", "mismatches", "analyze", "KIND_JA",
    "report_md", "EXAMPLE", "main",
)

__all__ = list(V1_NAMES) + ["__version__", "V1_NAMES"]

# 旧 API の私的な名前も残す（外から使われていた場合の互換。__all__ には入れない）
_ = (_usage, _layer_value, _min_conf, _expect, _norm_cap_value, _norm_conf)
del _
