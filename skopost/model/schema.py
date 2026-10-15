"""JSON スキーマ（Draft 2020-12 の部分集合）と、標準ライブラリだけの小さな検証器。

スキーマは「文書と外部ツール向け」。正規の検証は `model.validate` / `model.parse`（意味の検査を含む）で、
両者の一致は試験（tests/test_model_schema.py）が守る。スキーマで表せない意味の制約（id の重複・存在しない
置き場の参照・確度「不明」のとき value を無視する等）は `x-skopost-semantic` に文章で書く。

検証器が扱うキーワード：type・enum・const・properties・required・additionalProperties（false か スキーマ）・
items・minItems・maxItems・uniqueItems・minLength・maxLength・pattern・minimum・maximum・$ref（#/$defs/ のみ）・
anyOf・oneOf・not・$defs。それ以外のキーワードは無視せず ValueError（黙って通さない）。
"""
from __future__ import annotations

import copy
import re
from typing import Any

from .constants import (ACT_KINDS, BOOL_CAPS, CONF_ALIAS, MAX_IMPORTS, MAX_STORES, MAX_TOOLS, RESULT_VERSION)

_ID = {"type": "string", "pattern": "^[A-Za-z0-9_.-]{1,64}$"}
_CONF = {"enum": sorted(CONF_ALIAS)}
_CONF_CANON = {"enum": ["確", "論", "推", "不明"]}
_ACTS = {"type": "array", "items": {"enum": list(ACT_KINDS)}}
_STR_ARR = {"type": "array", "items": {"type": "string"}}


def _cap_props(value_of: Any) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for c in BOOL_CAPS:
        props[c] = value_of({"type": "boolean"})
    props["acts"] = value_of(_ACTS)
    props["writes_stores"] = value_of(_STR_ARR)
    props["reads_stores"] = value_of(_STR_ARR)
    return props


def _observed_entry(v: dict[str, Any], *, v2: bool) -> dict[str, Any]:
    obj_props: dict[str, Any] = {"value": {}, "confidence": _CONF, "evidence": {}}
    if v2:
        obj_props["source"] = {"type": "string", "pattern": "^(manual|ingest:[a-z0-9-]{1,32}|infer:[A-Z0-9-]{1,48})$"}
    return {"anyOf": [
        v,
        {"type": "object", "additionalProperties": False, "properties": obj_props},
    ]}


def _config_schema(version: int) -> dict[str, Any]:
    v2 = version == 2
    tool_props: dict[str, Any] = {
        "id": {"$ref": "#/$defs/id"},
        "label": {},
        "mode": {"enum": ["allow", "ask"]},
        "frequency": {"type": "integer", "minimum": 1, "maximum": 1_000_000},
        "declared": {"type": "object", "additionalProperties": False, "properties": _cap_props(lambda s: s)},
        "observed": {"type": "object", "additionalProperties": False,
                     "properties": _cap_props(lambda s: _observed_entry(s, v2=v2))},
    }
    if v2:
        tool_props["origin"] = {"type": "object", "additionalProperties": False, "required": ["file"],
                                "properties": {"file": {"type": "string", "minLength": 1, "maxLength": 4096},
                                               "pointer": {"type": "string", "pattern": "^(|/.*)$", "maxLength": 4096},
                                               "line": {"type": "integer", "minimum": 1, "maximum": 10_000_000}}}
    top: dict[str, Any] = {
        "skopost": {"const": version},
        "name": {"type": "string"},
        "untrusted_in_context": {"type": "boolean"},
        "stores": {"type": "array", "maxItems": MAX_STORES, "items": {
            "type": "object", "additionalProperties": False, "required": ["id"],
            "properties": {"id": {"$ref": "#/$defs/id"}, "label": {}, "external": {"type": "boolean"},
                           "executes": {"type": "boolean"}, "secret": {"type": "boolean"}}}},
        "tools": {"type": "array", "minItems": 1, "maxItems": MAX_TOOLS, "items": {
            "type": "object", "additionalProperties": False, "required": ["id"], "properties": tool_props}},
    }
    if v2:
        top["imports"] = {"type": "array", "maxItems": MAX_IMPORTS, "items": {
            "type": "object", "additionalProperties": False, "required": ["file", "sha256"],
            "properties": {"file": {"type": "string", "minLength": 1, "maxLength": 4096},
                           "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                           "adapter": {"type": "string", "pattern": "^[a-z0-9-]{1,32}$"}}}}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://skopost.invalid/schema/config.v{version}.json",
        "title": f"Skopost 宣言ファイル v{version}",
        "type": "object", "additionalProperties": False, "required": ["skopost", "tools"],
        "properties": top,
        "$defs": {"id": _ID},
        "x-skopost-semantic": [
            "tools[].id と stores[].id はそれぞれ重複しない",
            "writes_stores・reads_stores の要素は stores[].id のどれか",
            "observed の確度が 不明（unknown）のとき value は読まない（検証もしない）。それ以外の確度では value は項目の型（真偽値／配列）",
            "observed の確度を省いたときは 推。observed を真偽値・配列だけで書いたときも 推",
        ] + (["source が manual 以外の札に 確（sure）は付けられない"] if v2 else []),
    }


def _result_schema() -> dict[str, Any]:
    nn = {"type": "integer", "minimum": 0}
    path = {"type": "object", "additionalProperties": False, "required": ["kind", "tools", "confidence", "via"],
            "properties": {"kind": {"enum": ["exec", "act", "exfil"]},
                           "tools": {"type": "array", "minItems": 1, "maxItems": 2, "items": {"$ref": "#/$defs/id"}},
                           "confidence": _CONF_CANON,
                           "via": {"type": "array", "minItems": 1, "maxItems": 2, "items": {"type": "string"}}}}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://skopost.invalid/schema/result.v{RESULT_VERSION}.json",
        "title": f"Skopost 解析結果 v{RESULT_VERSION}（check --format json）",
        "type": "object", "additionalProperties": False,
        "required": ["skopost", "name", "exit_code", "summary", "paths", "mismatches", "assumed", "checkpoints",
                     "declared_only", "not_checked"],
        "properties": {
            "skopost": {"const": RESULT_VERSION},
            "name": {"type": "string"},
            "exit_code": {"enum": [0, 2]},
            "summary": {"type": "object", "additionalProperties": False,
                        "required": ["tools", "allowed", "paths", "paths_declared_only", "missed_by_declared",
                                     "mismatches", "assumed_unknown", "seconds"],
                        "properties": {"tools": nn, "allowed": nn, "paths": nn, "paths_declared_only": nn,
                                       "missed_by_declared": nn, "mismatches": nn, "assumed_unknown": nn,
                                       "seconds": {"type": "number", "minimum": 0}}},
            "paths": {"type": "array", "items": path},
            "mismatches": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["tool", "cap", "declared", "observed", "confidence", "evidence", "severity"],
                "properties": {"tool": {"$ref": "#/$defs/id"},
                               "cap": {"enum": list(BOOL_CAPS) + ["acts", "writes_stores", "reads_stores"]},
                               "declared": {"type": ["boolean", "array"]}, "observed": {"type": ["boolean", "array"]},
                               "confidence": {"enum": ["確", "論", "推"]}, "evidence": {"type": "string"},
                               "severity": {"enum": ["under", "over"]}}}},
            "assumed": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                   "required": ["tool", "cap"],
                                                   "properties": {"tool": {"$ref": "#/$defs/id"}, "cap": {"type": "string"}}}},
            "checkpoints": {"type": "object", "additionalProperties": False,
                            "required": ["exact", "primary", "alternatives", "size", "reasons"],
                            "properties": {"exact": {"type": "boolean"},
                                           "primary": {"type": "array", "uniqueItems": True, "items": {"$ref": "#/$defs/id"}},
                                           "alternatives": {"type": "array", "items": {"type": "array", "items": {"$ref": "#/$defs/id"}}},
                                           "size": nn,
                                           "reasons": {"type": "object", "additionalProperties": {"type": "array", "items": {"type": "string"}}}}},
            "declared_only": {"type": "object", "additionalProperties": False,
                              "required": ["cut", "holds", "surviving_paths", "surviving"],
                              "properties": {"cut": {"type": "array", "items": {"$ref": "#/$defs/id"}},
                                             "holds": {"type": "boolean"}, "surviving_paths": nn,
                                             "surviving": {"type": "array", "items": {"type": "string"}}}},
            "not_checked": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        },
        "$defs": {"id": _ID},
    }


_SCHEMAS = {"config.v1": lambda: _config_schema(1), "config.v2": lambda: _config_schema(2),
            "result.v1": _result_schema}
SCHEMA_NAMES = tuple(_SCHEMAS)


def get_schema(name: str) -> dict[str, Any]:
    """名前（config.v1・config.v2・result.v1）のスキーマの複製を返す。"""
    if name not in _SCHEMAS:
        raise KeyError(f"未知のスキーマ {name!r}。{', '.join(SCHEMA_NAMES)}")
    return copy.deepcopy(_SCHEMAS[name]())


# ---------------------------------------------------------------- 小さな検証器
_KNOWN = {"$schema", "$id", "title", "description", "$defs", "x-skopost-semantic", "type", "enum", "const",
          "properties", "required", "additionalProperties", "items", "minItems", "maxItems", "uniqueItems",
          "minLength", "maxLength", "pattern", "minimum", "maximum", "$ref", "anyOf", "oneOf", "not"}
_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "null": lambda v: v is None,
}


def _json_eq(a: Any, b: Any) -> bool:
    # JSON の等価：true と 1 は別物
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_json_eq(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_json_eq(a[k], b[k]) for k in a)
    return a == b


def schema_errors(instance: Any, schema: dict[str, Any], *, _root: dict[str, Any] | None = None,
                  _path: str = "", _depth: int = 0) -> list[str]:
    """スキーマに反する箇所を「JSON Pointer: 理由」の並びで返す（空なら適合）。"""
    root = schema if _root is None else _root
    if _depth > 64:
        return [f"{_path or '/'}: 入れ子が深すぎます"]
    unknown = set(schema) - _KNOWN
    if unknown:
        raise ValueError(f"検証器が扱えないキーワード：{sorted(unknown)}")
    errs: list[str] = []
    here = _path or "/"

    def sub(inst: Any, sch: dict[str, Any], path: str) -> list[str]:
        return schema_errors(inst, sch, _root=root, _path=path, _depth=_depth + 1)

    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            raise ValueError(f"扱えない $ref：{ref}")
        errs += sub(instance, root["$defs"][ref[len("#/$defs/"):]], _path)
    if "type" in schema:
        ts = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_TYPES[t](instance) for t in ts):
            return errs + [f"{here}: 型は {'/'.join(ts)}"]
    if "const" in schema and not _json_eq(instance, schema["const"]):
        errs.append(f"{here}: 値は {schema['const']!r}")
    if "enum" in schema and not any(_json_eq(instance, e) for e in schema["enum"]):
        errs.append(f"{here}: 値は {schema['enum']!r} のどれか")
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errs.append(f"{here}: {schema['minLength']} 字以上")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errs.append(f"{here}: {schema['maxLength']} 字以下")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errs.append(f"{here}: 形式 {schema['pattern']} に合わない")
    if _TYPES["number"](instance):
        if "minimum" in schema and instance < schema["minimum"]:
            errs.append(f"{here}: {schema['minimum']} 以上")
        if "maximum" in schema and instance > schema["maximum"]:
            errs.append(f"{here}: {schema['maximum']} 以下")
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errs.append(f"{here}: {schema['minItems']} 個以上")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errs.append(f"{here}: {schema['maxItems']} 個以下")
        if schema.get("uniqueItems"):
            for i in range(len(instance)):
                if any(_json_eq(instance[i], instance[j]) for j in range(i)):
                    errs.append(f"{here}: 要素 {i} が重複")
                    break
        if "items" in schema:
            for i, x in enumerate(instance):
                errs += sub(x, schema["items"], f"{_path}/{i}")
    if isinstance(instance, dict):
        for k in schema.get("required", []):
            if k not in instance:
                errs.append(f"{here}: 必須の鍵 {k!r} が無い")
        props = schema.get("properties", {})
        for k, v in instance.items():
            p = f"{_path}/{_escape(k)}"
            if k in props:
                errs += sub(v, props[k], p)
            elif "additionalProperties" in schema:
                ap = schema["additionalProperties"]
                if ap is False:
                    errs.append(f"{p}: 未知の鍵")
                elif isinstance(ap, dict):
                    errs += sub(v, ap, p)
    if "anyOf" in schema:
        if not any(not sub(instance, s, _path) for s in schema["anyOf"]):
            errs.append(f"{here}: anyOf のどれにも合わない")
    if "oneOf" in schema:
        n = sum(1 for s in schema["oneOf"] if not sub(instance, s, _path))
        if n != 1:
            errs.append(f"{here}: oneOf にちょうど 1 つ合う必要がある（{n} 個）")
    if "not" in schema and not sub(instance, schema["not"], _path):
        errs.append(f"{here}: not に合ってしまう")
    return errs


def _escape(k: str) -> str:
    return str(k).replace("~", "~0").replace("/", "~1")
