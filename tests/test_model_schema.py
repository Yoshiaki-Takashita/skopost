"""JSON スキーマと検証器の一致（担当 A）。

スキーマは「必要条件」：検証器（model.parse / validate）が通す入力はスキーマも必ず通す（健全性）。
スキーマで表せる誤り（型・未知の鍵・列挙）は、スキーマも拒否する（負例の一部で確かめる）。
"""
from __future__ import annotations

import json
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import FIXTURES, SEEDS, example_raws, gen_raw_config  # noqa: E402

from skopost import model as M  # noqa: E402
from skopost.compat import v1 as V1  # noqa: E402


def load_json(p: str):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


class Validator(unittest.TestCase):
    def test_keywords(self):
        sch = {"type": "object", "required": ["a"], "additionalProperties": False,
               "properties": {"a": {"type": "integer", "minimum": 1, "maximum": 3},
                              "b": {"type": "array", "items": {"enum": ["x"]}, "uniqueItems": True, "maxItems": 2},
                              "c": {"anyOf": [{"type": "string", "pattern": "^z"}, {"const": 5}]},
                              "d": {"oneOf": [{"type": "number"}, {"type": "integer"}]},
                              "e": {"not": {"type": "null"}},
                              "f": {"type": "string", "minLength": 2, "maxLength": 3}}}
        self.assertEqual(M.schema_errors({"a": 2, "b": ["x"], "c": "zz", "d": 1.5, "e": 0, "f": "ab"}, sch), [])
        self.assertTrue(M.schema_errors({}, sch))
        self.assertTrue(M.schema_errors({"a": True}, sch))            # bool は integer ではない
        self.assertTrue(M.schema_errors({"a": 4}, sch))
        self.assertTrue(M.schema_errors({"a": 1, "zz": 0}, sch))
        self.assertTrue(M.schema_errors({"a": 1, "b": ["x", "x"]}, sch))
        self.assertTrue(M.schema_errors({"a": 1, "c": 6}, sch))
        self.assertTrue(M.schema_errors({"a": 1, "d": 1}, sch))       # 1 は number にも integer にも合う
        self.assertTrue(M.schema_errors({"a": 1, "e": None}, sch))
        self.assertTrue(M.schema_errors({"a": 1, "f": "a"}, sch))
        self.assertTrue(M.schema_errors({"a": 1, "f": "abcd"}, sch))
        self.assertEqual(M.schema_errors({"x": 1}, {"enum": [{"x": 1}]}), [])
        self.assertTrue(M.schema_errors(True, {"const": 1}))

    def test_unknown_keyword_is_an_error_not_ignored(self):
        with self.assertRaises(ValueError):
            M.schema_errors(1, {"format": "email"})
        with self.assertRaises(ValueError):
            M.schema_errors(1, {"$ref": "http://x"})

    def test_names(self):
        self.assertEqual(set(M.SCHEMA_NAMES), {"config.v1", "config.v2", "result.v1"})
        with self.assertRaises(KeyError):
            M.get_schema("nope")
        a = M.get_schema("config.v1")
        a["title"] = "changed"
        self.assertNotEqual(M.get_schema("config.v1")["title"], "changed")


class Agreement(unittest.TestCase):
    def test_valid_inputs_pass_schema(self):
        raws = list(example_raws().values()) + [gen_raw_config(random.Random(s)) for s in SEEDS]
        for raw in raws:
            M.validate(raw)
            self.assertEqual(M.schema_errors(raw, M.get_schema("config.v1")), [])
            self.assertEqual(M.schema_errors({**raw, "skopost": 2}, M.get_schema("config.v2")), [])
        for name in sorted(os.listdir(os.path.join(FIXTURES, "spec-v2"))):
            if name.startswith("ok-"):
                raw = load_json(os.path.join(FIXTURES, "spec-v2", name))
                self.assertEqual(M.schema_errors(raw, M.get_schema("config.v2")), [], name)

    def test_to_dict_output_passes_schema(self):
        for s in SEEDS[:20]:
            cfg = M.parse(gen_raw_config(random.Random(s)))
            self.assertEqual(M.schema_errors(M.to_dict(cfg), M.get_schema("config.v2")), [])
            self.assertEqual(M.schema_errors(M.to_dict(cfg, spec=1), M.get_schema("config.v1")), [])

    def test_structural_negatives_rejected_by_both(self):
        # スキーマで表せる誤りだけ（重複 id・存在しない置き場は意味の制約で、スキーマの外）
        structural = ["bad-empty-tools.json", "bad-unknown-top.json", "bad-id.json", "bad-conf.json",
                      "bad-freq-zero.json", "bad-version2-in-v1-keys.json", "bad-not-object.json"]
        for name in structural:
            raw = load_json(os.path.join(FIXTURES, "spec-v1", name))
            with self.subTest(name=name):
                self.assertTrue(M.schema_errors(raw, M.get_schema("config.v1")))
        for name in ["bad-source-format.json", "bad-origin-pointer.json", "bad-origin-line.json",
                     "bad-origin-key.json", "bad-imports-sha.json", "bad-imports-adapter.json",
                     "bad-tool-key.json", "bad-top-key.json"]:
            raw = load_json(os.path.join(FIXTURES, "spec-v2", name))
            with self.subTest(name=name):
                self.assertTrue(M.schema_errors(raw, M.get_schema("config.v2")))

    def test_result_schema_matches_v1_output(self):
        raws = list(example_raws().values()) + [gen_raw_config(random.Random(s)) for s in SEEDS]
        for raw in raws:
            res = V1.analyze(M.validate(raw))
            self.assertEqual(M.schema_errors(res, M.get_schema("result.v1")), [])
            # JSON にして戻しても同じ（CLI の --format json と同じ経路）
            self.assertEqual(M.schema_errors(json.loads(json.dumps(res, ensure_ascii=False)), M.get_schema("result.v1")), [])


if __name__ == "__main__":
    unittest.main()
