"""コーパスの性質試験：生成の決定性・往復・自動判別・単調性・厳密解と全探索の一致・秘密が出ない。"""
from __future__ import annotations

import itertools
import json
import os
import random
import unittest

from _common import TmpFiles, gen, load_real, manifest

from skopost import graph as G
from skopost import model as M
from skopost.ingest import detect, ingest
from skopost.pipeline import apply_inferred


class Determinism(unittest.TestCase):
    def test_synth_same_seed_same_output(self):
        for n in (10, 37, 64):
            self.assertEqual(json.dumps(gen.synth(7, n, 3)), json.dumps(gen.synth(7, n, 3)))
        self.assertNotEqual(json.dumps(gen.synth(7, 10, 0)), json.dumps(gen.synth(8, 10, 0)))

    def test_synth_range_and_valid(self):
        for n in range(gen.N_MIN, gen.N_MAX + 1):
            cfg = M.parse(gen.synth(gen.SEED, n, 0))
            self.assertEqual(len(cfg.tools), n)
        for bad in (gen.N_MIN - 1, gen.N_MAX + 1):
            with self.assertRaises(ValueError):
                gen.synth(1, bad)

    def test_real_corpus_regenerates_byte_identical(self):
        man = manifest()
        self.assertEqual(man["seed"], gen.SEED)
        seen = set()
        for rel, fmt, data, plants in gen.real_corpus(gen.SEED):
            seen.add(rel)
            self.assertEqual(load_real(rel), data, rel)
            self.assertEqual(man["files"][rel], {"format": fmt, "planted_unread": plants})
        self.assertEqual(seen, set(man["files"]))

    def test_at_least_20_per_format(self):
        from collections import Counter
        c = Counter(e["format"] for e in manifest()["files"].values())
        for fmt in ("mcp", "openapi", "claude-settings"):
            self.assertGreaterEqual(c[fmt], 20)

    def test_only_example_hosts(self):
        import re
        for rel in manifest()["files"]:
            text = json.dumps(load_real(rel))
            for host in re.findall(r"https?://([^/:\"]+)", text):
                self.assertTrue(host == "localhost" or host.endswith((".example.com", ".example.org"))
                                or host in ("example.com", "example.org"), f"{rel}: {host}")


class RealCorpus(unittest.TestCase):
    def test_detect_matches_format(self):
        for rel, ent in manifest()["files"].items():
            self.assertEqual(detect(load_real(rel), os.path.basename(rel)).name, ent["format"], rel)

    def test_non_x_planted_keys_recorded(self):
        for rel, ent in manifest()["files"].items():
            res = ingest(os.path.join(gen.REAL_DIR, rel), adapter=ent["format"])
            got = {n.pointer for n in res.notes}
            for p in ent["planted_unread"]:
                self.assertIn(p, got, f"{rel}: {p}")

    def test_x_keys_on_path_item_and_operation_recorded(self):
        doc = {"openapi": "3.0.0", "info": {"title": "t"},
               "paths": {"/a": {"x-p": 1, "get": {"operationId": "g", "x-o": {"k": 1}}}}}
        t = TmpFiles()
        self.addCleanup(t.close)
        got = {n.pointer for n in ingest(t.write("o.json", doc), adapter="openapi").notes}
        self.assertIn("/paths/~1a/x-p", got)
        self.assertIn("/paths/~1a/get/x-o", got)

    def test_infer_never_kaku(self):
        for rel, ent in manifest()["files"].items():
            res = ingest(os.path.join(gen.REAL_DIR, rel), adapter=ent["format"])
            cfg = apply_inferred(res.config, res.facts)
            for t in cfg.tools:
                for cap in t.observed.values():
                    if cap.source.startswith("infer:"):
                        self.assertNotEqual(cap.confidence, "確", f"{rel}:{t.id}")

    def test_infer_never_removes_paths(self):
        for rel, ent in manifest()["files"].items():
            res = ingest(os.path.join(gen.REAL_DIR, rel), adapter=ent["format"])
            a = {(p.kind, p.key) for p in G.harm_paths(res.config, "observed")}
            b = {(p.kind, p.key) for p in G.harm_paths(apply_inferred(res.config, res.facts), "observed")}
            self.assertLessEqual(a, b, rel)


def _brute(paths) -> int:
    sets = [frozenset(p.tools) for p in paths]
    cand = sorted(set().union(*sets)) if sets else []
    for k in range(len(cand) + 1):
        for c in itertools.combinations(cand, k):
            if all(s & set(c) for s in sets):
                return k
    raise AssertionError


class GraphOnSynth(unittest.TestCase):
    def test_exact_equals_brute_small(self):
        for i in range(30):
            cfg = M.parse(gen.synth(99, 10 + i % 3, i))
            res = G.analyze(cfg)
            self.assertTrue(res.checkpoints.exact)
            self.assertEqual(len(res.checkpoints.primary), _brute(res.paths), i)

    def test_monotone_superset(self):
        for n in (10, 24, 64):
            for i in range(10):
                d = G.policy_diff(M.parse(gen.synth(5, n, i)))
                self.assertEqual(d["only_v1"], [], (n, i))

    def test_making_store_caps_unknown_never_shrinks_monotone(self):
        rng = random.Random(3)
        for i in range(20):
            raw = gen.synth(11, 12, i, p_store_unknown=0.0)
            base = {(p.kind, p.key) for p in G.harm_paths_policy(M.parse(raw), "observed", "monotone")}
            t = rng.choice(raw["tools"])
            t["observed"][rng.choice(("writes_stores", "reads_stores"))] = {"confidence": "不明"}
            more = {(p.kind, p.key) for p in G.harm_paths_policy(M.parse(raw), "observed", "monotone")}
            self.assertLessEqual(base, more, i)


class SecretsNeverLeak(unittest.TestCase):
    """秘密らしき値を実行時に組み立てて埋め込み、ingest の出力（notes・facts・config）に現れないことを確かめる。
    リポジトリには鍵らしき文字列を置かない（連結で作る）。"""

    def setUp(self):
        self.tmp = TmpFiles()

    def tearDown(self):
        self.tmp.close()

    def _fake(self, rng) -> str:
        body = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(24))
        return rng.choice(("s" + "k-", "A" + "KIA", "gh" + "p_")) + body

    def test_embedded_secrets_absent(self):
        rng = random.Random(42)
        man = manifest()
        n = 0
        for rel, ent in sorted(man["files"].items()):
            if ent["format"] != "mcp":
                continue
            data = load_real(rel)
            secrets = []
            for srv in data["mcpServers"].values():
                s = self._fake(rng)
                secrets.append(s)
                srv.setdefault("env", {})["TOKEN"] = s
                s2 = self._fake(rng)
                secrets.append(s2)
                srv.setdefault("args", []).append("--key=" + s2)
            p = self.tmp.write(os.path.basename(rel), data)
            res = ingest(p, adapter="mcp")
            out = repr((res.notes, res.facts, res.config, res.dropped))
            for s in secrets:
                self.assertNotIn(s, out, rel)
                n += 1
        self.assertGreater(n, 40)


if __name__ == "__main__":
    unittest.main()
