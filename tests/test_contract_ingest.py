"""ingest の契約試験（担当 A 所有・担当 B の受け入れ条件）。I1・I2 と Protocol への適合。

アダプタ固有の入力は担当 B が tests/fixtures/ingest/<アダプタ名>/ に置く。ここはどのアダプタにも共通の約束だけ。
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import FIXTURES, PKG, call_or_skip  # noqa: E402

from skopost import ingest as IN  # noqa: E402
from skopost import model as M  # noqa: E402

SECRET_RE = re.compile(r"sk-[A-Za-z0-9]{8,}|AKIA[0-9A-Z]{12,}|-----BEGIN [A-Z ]+-----")
JUNK = (None, 0, "", "x", [], {}, [1, 2], {"a": {"b": []}}, {"mcpServers": 3}, {"openapi": None}, {"permissions": "x"})


def ingest_fixture_files():
    root = os.path.join(FIXTURES, "ingest")
    if not os.path.isdir(root):
        return []
    out = []
    for d, _, files in os.walk(root):
        out += [os.path.join(d, f) for f in sorted(files) if f.endswith(".json")]
    return out


class Registry(unittest.TestCase):
    def test_adapters_follow_protocol(self):
        for name, ad in IN.ADAPTERS.items():
            with self.subTest(name=name):
                self.assertIsInstance(ad, IN.Adapter)
                self.assertEqual(ad.name, name)
                self.assertRegex(name, r"^[a-z0-9-]{1,32}$")

    def test_sniff_never_raises_and_is_bounded(self):
        for name, ad in IN.ADAPTERS.items():
            for j in JUNK:
                v = ad.sniff(j, "x.json")
                self.assertIsInstance(v, float, name)
                self.assertTrue(0.0 <= v <= 1.0, name)

    def test_detect_refuses_when_unsure(self):
        for j in JUNK:
            try:
                IN.detect(j, "x.json")
            except M.NotImplementedYet as e:
                self.skipTest(f"未実装：{e.what}")
            except M.SkopostError:
                continue
            # 判定できたなら自信は下限以上
            best = max((ad.sniff(j, "x.json") for ad in IN.ADAPTERS.values()), default=0.0)
            self.assertGreaterEqual(best, IN.MIN_CONFIDENCE)

    def test_adapter_sources_cite_primary_docs(self):
        """各アダプタの冒頭に出典と確認日（鍵名は記憶に頼らない：ARCHITECTURE §1.2）。"""
        d = os.path.join(PKG, "ingest")
        for f in sorted(os.listdir(d)):
            if f.endswith(".py") and f not in ("__init__.py", "api.py", "base.py"):
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    head = fh.read(3000)
                self.assertRegex(head, r"出典", f)
                self.assertRegex(head, r"確認日[:：]?\s*20\d\d-\d\d-\d\d", f)


class Fixtures(unittest.TestCase):
    def test_each_fixture(self):
        files = ingest_fixture_files()
        if not files:
            self.skipTest("未実装：tests/fixtures/ingest/（担当 B）")
        for p in files:
            with self.subTest(p=os.path.relpath(p, FIXTURES)):
                res = call_or_skip(self, IN.ingest, p)
                self.assertIsInstance(res, M.IngestResult)
                for t in res.config.tools:
                    for c in t.observed.values():
                        self.assertNotEqual(c.confidence, "確", "取り込みは札に「確」を付けない（I1）")
                blob = repr(res)
                self.assertIsNone(SECRET_RE.search(blob), "秘密らしき値が結果に残っている（I2）")

    def test_secrets_are_discarded(self):
        """I2：どのアダプタでも、入力に埋めた秘密らしき文字列が結果に現れない。"""
        planted = {"env": {"OPENAI_API_KEY": "sk-" + "A" * 40, "AWS": "AKIA" + "B" * 16},
                   "key": "-----BEGIN PRIVATE KEY-----\nMII\n-----END PRIVATE KEY-----"}
        if not IN.ADAPTERS:
            self.skipTest("未実装：アダプタが無い（担当 B）")
        for name in IN.ADAPTERS:
            for p in ingest_fixture_files():
                if f"{os.sep}{name}{os.sep}" not in p:
                    continue
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                data = {**data, "x-planted": planted}
                with tempfile.TemporaryDirectory() as d:
                    q = os.path.join(d, os.path.basename(p))
                    with open(q, "w", encoding="utf-8") as f:
                        json.dump(data, f)
                    try:
                        res = IN.ingest(q, adapter=name)
                    except M.SkopostError:
                        continue
                    self.assertIsNone(SECRET_RE.search(repr(res)), (name, p))


class Merge(unittest.TestCase):
    impl = IN

    def test_manual_overlay_wins(self):
        base = M.parse({"skopost": 2, "tools": [
            {"id": "a", "observed": {"exec": {"value": True, "confidence": "推", "source": "ingest:mcp"}}},
            {"id": "b"}]})
        overlay = M.parse({"skopost": 1, "tools": [
            {"id": "a", "observed": {"exec": {"value": False, "confidence": "確", "evidence": "人が読んだ"}}},
            {"id": "c"}]})
        out = call_or_skip(self, self.impl.merge, base, overlay)
        self.assertEqual([t.id for t in out.tools], ["a", "b", "c"])
        self.assertEqual(out.tool("a").observed["exec"], M.Cap(False, "確", "人が読んだ"))


if __name__ == "__main__":
    unittest.main()
