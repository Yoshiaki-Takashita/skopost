"""model の読み込み・版移行・往復（M1・M2・M3。担当 A）。"""
from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import FIXTURES, SEEDS, example_raws, gen_raw_config  # noqa: E402

from skopost import model as M  # noqa: E402
from skopost.model import SkopostError  # noqa: E402


def fixture_files(version: int, prefix: str) -> list[str]:
    d = os.path.join(FIXTURES, f"spec-v{version}")
    return sorted(os.path.join(d, f) for f in os.listdir(d) if f.startswith(prefix) and f.endswith(".json"))


class Fixtures(unittest.TestCase):
    """各版の正例・負例は、以降の全版で同じ判定になる（ARCHITECTURE §2.3・原則 12）。"""

    def test_fixture_sets_exist(self):
        for v in (1, 2):
            self.assertGreaterEqual(len(fixture_files(v, "ok-")), 2)
            self.assertGreaterEqual(len(fixture_files(v, "bad-")), 5)

    def test_ok_fixtures_load(self):
        for v in (1, 2):
            for p in fixture_files(v, "ok-"):
                with self.subTest(p=os.path.basename(p)):
                    cfg = M.load(p)
                    self.assertIsInstance(cfg, M.Config)
                    self.assertEqual(cfg.spec, 2)

    def test_bad_fixtures_rejected_with_skoposterror_only(self):
        for v in (1, 2):
            for p in fixture_files(v, "bad-"):
                with self.subTest(p=os.path.basename(p)):
                    with self.assertRaises(SkopostError):
                        M.load(p)

    def test_v1_ok_fixtures_also_pass_legacy_validate(self):
        for p in fixture_files(1, "ok-"):
            M.load_file(p)

    def test_v2_fixture_details(self):
        cfg = M.load(os.path.join(FIXTURES, "spec-v2", "ok-full.json"))
        t = cfg.tool("read")
        self.assertEqual(t.origin, M.Origin(".mcp.json", "/mcpServers/fs", 3))
        self.assertEqual(t.observed["exec"].source, "infer:R-OPENAPI-GET")
        self.assertEqual(t.observed["reads_untrusted"].source, "manual")
        self.assertTrue(t.observed["net_out"].unknown)
        self.assertEqual(t.observed["net_out"].source, "ingest:mcp")
        self.assertEqual(cfg.imports, (M.ImportRecord(".mcp.json", "a" * 64, "mcp"),))
        self.assertEqual(cfg.tool("send").origin, M.Origin("x.json"))


class LegacyQuirks(unittest.TestCase):
    """v1 の検証器の癖（記録。直さない：変えた行は依頼にたどれるようにする原則）。型付きの読み込みは厳しく拒否する。"""

    def test_bool_and_float_version_accepted_by_legacy_only(self):
        for v in (True, 1.0):
            raw = {"skopost": v, "tools": [{"id": "a"}]}
            M.validate(raw)  # 旧 API は True == 1・1.0 == 1 で通してしまう（互換のため据え置き）
            with self.assertRaises(SkopostError):
                M.parse(raw)


class V1EqualsV2(unittest.TestCase):
    """M1：v1 の入力は、v2 として（skopost を 2 に書き換えて）読んでも同じ Config になる。"""

    def test_examples(self):
        for name, raw in example_raws().items():
            with self.subTest(name=name):
                a = M.parse(raw)
                b = M.parse({**raw, "skopost": 2})
                self.assertEqual(a, b)

    def test_random(self):
        for seed in SEEDS:
            raw = gen_raw_config(random.Random(seed))
            self.assertEqual(M.parse(raw), M.parse({**raw, "skopost": 2}), seed)

    def test_migrate_does_not_mutate_input(self):
        raw = example_raws()["example"]
        before = json.dumps(raw, sort_keys=True)
        out = M.migrate(raw)
        self.assertEqual(out["skopost"], 2)
        self.assertEqual(json.dumps(raw, sort_keys=True), before)

    def test_migrate_rejects(self):
        for bad in ({"skopost": 3}, {"skopost": 0}, {"skopost": "1"}, {}, [], None, {"skopost": None}):
            with self.assertRaises(SkopostError):
                M.migrate(bad)

    def test_spec_version_of(self):
        self.assertEqual(M.spec_version_of({"skopost": 1}), 1)
        self.assertEqual(M.spec_version_of({"skopost": 2}), 2)


class RoundTrip(unittest.TestCase):
    """M2：parse ∘ to_dict が恒等。to_legacy は validate と同じ辞書を返す。"""

    def _roundtrip(self, cfg: M.Config) -> None:
        d = M.to_dict(cfg)
        self.assertEqual(json.loads(json.dumps(d, ensure_ascii=False)), d, "to_dict は JSON にそのまま書ける")
        self.assertEqual(M.parse(d), cfg)

    def test_examples(self):
        for raw in example_raws().values():
            self._roundtrip(M.parse(raw))

    def test_v2_fixture(self):
        self._roundtrip(M.load(os.path.join(FIXTURES, "spec-v2", "ok-full.json")))

    def test_random(self):
        for seed in SEEDS:
            raw = gen_raw_config(random.Random(seed))
            cfg = M.parse(raw)
            self._roundtrip(cfg)
            self.assertEqual(M.to_legacy(cfg), M.validate(raw), seed)
            self.assertEqual(M.from_legacy(M.validate(raw)), cfg, seed)

    def test_to_dict_v1_refuses_lossy(self):
        cfg = M.load(os.path.join(FIXTURES, "spec-v2", "ok-full.json"))
        with self.assertRaises(ValueError):
            M.to_dict(cfg, spec=1)
        plain = M.parse(example_raws()["example"])
        d1 = M.to_dict(plain, spec=1)
        self.assertEqual(d1["skopost"], 1)
        self.assertEqual(M.parse(d1), plain)
        with self.assertRaises(ValueError):
            M.to_dict(plain, spec=3)

    def test_load_file_size_limit(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(example_raws()["example"], f)
            with self.assertRaises(SkopostError):
                M.load(p, max_bytes=10)
            self.assertIsInstance(M.load(p), M.Config)


class Fuzz(unittest.TestCase):
    """M3（縮小版）：壊した入力で出る例外は SkopostError だけ。10 万例は段 3 の corpus/fuzz で回す。"""

    N = int(os.environ.get("SKOPOST_FUZZ", "3000"))
    JUNK = (None, True, False, 0, -1, 1.5, "", "x" * 200, "確", [], {}, [1], {"a": 1}, "\u0000", "../../etc", 10 ** 30)

    def _mutate(self, rng: random.Random, obj, depth: int = 0):
        if depth > 6 or rng.random() < 0.15:
            return rng.choice(self.JUNK)
        if isinstance(obj, dict):
            d = dict(obj)
            r = rng.random()
            if d and r < 0.3:
                k = rng.choice(list(d))
                d[k] = self._mutate(rng, d[k], depth + 1)
            elif d and r < 0.45:
                del d[rng.choice(list(d))]
            elif r < 0.55:
                d[rng.choice(["origin", "source", "imports", "typo", "value", "confidence", "id"])] = rng.choice(self.JUNK)
            else:
                for k in list(d)[:3]:
                    if rng.random() < 0.5:
                        d[k] = self._mutate(rng, d[k], depth + 1)
            return d
        if isinstance(obj, list):
            lst = list(obj)
            if lst and rng.random() < 0.5:
                i = rng.randrange(len(lst))
                lst[i] = self._mutate(rng, lst[i], depth + 1)
            elif rng.random() < 0.3:
                lst.append(rng.choice(self.JUNK))
            return lst
        return rng.choice(self.JUNK)

    def test_only_skoposterror(self):
        rng = random.Random(20261013)
        bases = list(example_raws().values()) + [gen_raw_config(random.Random(s)) for s in range(10)]
        accepted = rejected = 0
        for i in range(self.N):
            raw = self._mutate(rng, rng.choice(bases))
            if isinstance(raw, dict) and rng.random() < 0.5:
                raw = {**raw, "skopost": 2}
            for fn in (M.parse, M.validate):
                try:
                    out = fn(raw)
                    accepted += 1
                    if fn is M.parse:
                        self.assertEqual(M.parse(M.to_dict(out)), out)
                except SkopostError:
                    rejected += 1
                except Exception as e:  # noqa: BLE001
                    self.fail(f"#{i} {fn.__name__} が SkopostError 以外を投げた：{type(e).__name__}: {e}\n{raw!r:.400}")
        self.assertGreater(accepted, 0)
        self.assertGreater(rejected, 0)


if __name__ == "__main__":
    unittest.main()
