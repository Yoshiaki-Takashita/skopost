"""定数（全層が読む唯一の置き場）。値は v1（SPEC.md）と同一。変えるときは版の規則（ARCHITECTURE §2.3）に従う。"""
from __future__ import annotations

import re

#: 入力仕様の現行版（`skopost` 鍵）。旧 CLI（compat.v1）はこの版だけを読む。
SPEC_VERSION = 1
#: 型付きの読み込み（model.parse）が読める入力の版。現行と 1 つ前まで（ARCHITECTURE §2.3）。
SUPPORTED_SPEC_VERSIONS = (1, 2)
#: 型付きの読み込みが正規化した後の版（v1 は migrate で v2 に上げる）。
LATEST_SPEC_VERSION = 2
#: 出力 JSON の `skopost` 鍵（結果の版）。入力の版とは独立に上げる。
RESULT_VERSION = 1

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOOLS = 64
MAX_STORES = 32
MAX_ID_LEN = 64
MAX_IMPORTS = 64
EXACT_LIMIT = 20          # これ以下の道具数なら厳密解（v1 の挙動）
MAX_ALTERNATIVES = 5
DISPLAY_LEN = 120
MAX_TEXT_LEN = 10_000     # label・evidence などの文字列の上限（v2 の型付き読み込みだけが使う）

ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
BOOL_CAPS = ("reads_untrusted", "reads_secret", "net_out", "args_leave", "exec")
STORE_LIST_CAPS = ("writes_stores", "reads_stores")
LIST_CAPS = ("acts", "writes_stores", "reads_stores")
ALL_CAPS = BOOL_CAPS + LIST_CAPS
ACT_KINDS = ("send", "purchase", "delete", "publish", "grant", "pay")
CONFIDENCES = ("確", "論", "推", "不明")
CONF_ORDER = {"確": 3, "論": 2, "推": 1, "不明": 0}
CONF_ALIAS = {"sure": "確", "derived": "論", "guess": "推", "unknown": "不明",
              "確": "確", "論": "論", "推": "推", "不明": "不明"}
TOOL_KEYS = {"id", "label", "mode", "frequency", "declared", "observed"}
STORE_KEYS = {"id", "label", "external", "executes", "secret"}
TOP_KEYS = {"skopost", "name", "untrusted_in_context", "stores", "tools"}
OBSERVED_KEYS = {"value", "confidence", "evidence"}

# v2 で増える鍵（すべて任意）
TOOL_KEYS_V2 = TOOL_KEYS | {"origin"}
TOP_KEYS_V2 = TOP_KEYS | {"imports"}
OBSERVED_KEYS_V2 = OBSERVED_KEYS | {"source"}
ORIGIN_KEYS = {"file", "pointer", "line"}
IMPORT_KEYS = {"file", "sha256", "adapter"}
SOURCE_RE = re.compile(r"^(manual|ingest:[a-z0-9-]{1,32}|infer:[A-Z0-9-]{1,48})$")

PATH_KINDS = ("exec", "act", "exfil")
LAYERS = ("declared", "observed")
MODES = ("allow", "ask")

__all__ = [
    "SPEC_VERSION",
    "SUPPORTED_SPEC_VERSIONS",
    "LATEST_SPEC_VERSION",
    "RESULT_VERSION",
    "MAX_FILE_BYTES",
    "MAX_TOOLS",
    "MAX_STORES",
    "MAX_ID_LEN",
    "MAX_IMPORTS",
    "EXACT_LIMIT",
    "MAX_ALTERNATIVES",
    "DISPLAY_LEN",
    "MAX_TEXT_LEN",
    "ID_RE",
    "SHA256_RE",
    "BOOL_CAPS",
    "STORE_LIST_CAPS",
    "LIST_CAPS",
    "ALL_CAPS",
    "ACT_KINDS",
    "CONFIDENCES",
    "CONF_ORDER",
    "CONF_ALIAS",
    "TOOL_KEYS",
    "STORE_KEYS",
    "TOP_KEYS",
    "OBSERVED_KEYS",
    "TOOL_KEYS_V2",
    "TOP_KEYS_V2",
    "OBSERVED_KEYS_V2",
    "ORIGIN_KEYS",
    "IMPORT_KEYS",
    "SOURCE_RE",
    "PATH_KINDS",
    "LAYERS",
    "MODES",
]
