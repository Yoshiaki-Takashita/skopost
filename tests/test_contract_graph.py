"""graph の契約試験（担当 A 所有・担当 D／Mythos の受け入れ条件）。

根幹（危険経路の定義・最小関所の厳密解）は後で Mythos に任せる方針。ここに置くのは「どんな実装でも守ること」：
- harm_paths：v1 の参照実装（SPEC §7）と同じ道を同じ順序で返す。定義を変えるときは SPEC と本ファイルを先に更新（A）
- min_checkpoints：全部の道を断つ／exact なら最小（総当たりと同じ大きさ）／近似なら下界 ≤ 真の最小 ≤ 案の大きさ（G1・G4）
  同じ大きさの案の第一案は frequency 合計が最小、同点は道具の並び順で辞書順最小（v1 と同じ。報告のバイト一致のため）
- apply_checkpoints：締める方向だけ（cut の道具を ask に。他は不変。入力は不変。存在しない id は無視＝v1 と同じ）
- 単調性（F1）：observed の札を「不明」に変えても道は減らない
- analyze：v1 の analyze と、秒数と代替案の中身を除いて同値
"""
from __future__ import annotations

import itertools
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import SEEDS, call_or_skip, example_raws, gen_raw_config  # noqa: E402

from skopost import graph as G  # noqa: E402
from skopost import model as M  # noqa: E402
from skopost.compat import v1 as V1  # noqa: E402
from skopost.model import Checkpoints, Config, HarmPath  # noqa: E402


def corpus(n_tools=None):
    for name, raw in example_raws().items():
        yield name, raw
    for s in SEEDS:
        yield f"seed{s}", gen_raw_config(random.Random(s), n_tools=n_tools)


def typed_paths(paths: list[dict]) -> list[HarmPath]:
    return [HarmPath(p["kind"], tuple(p["tools"]), tuple(p["via"]), p["confidence"]) for p in paths]


def brute_min(cfg: Config, paths: list[HarmPath]) -> int:
    ids = [t.id for t in cfg.allowed()]
    if not paths:
        return 0
    sets = [p.tool_set for p in paths]
    for k in range(1, len(ids) + 1):
        for comb in itertools.combinations(ids, k):
            cs = set(comb)
            if all(s & cs for s in sets):
                return k
    return len(ids)


class HarmPathsMatchV1(unittest.TestCase):
    impl = G

    def test_same_paths_same_order(self):
        for name, raw in corpus():
            legacy = M.validate(raw)
            cfg = M.from_legacy(legacy)
            for layer in ("declared", "observed"):
                got = call_or_skip(self, self.impl.harm_paths, cfg, layer)
                self.assertEqual(got, typed_paths(V1.harm_paths(legacy, layer)), (name, layer))

    def test_untrusted_false_means_no_paths(self):
        for _, raw in corpus():
            cfg = M.parse({**raw, "untrusted_in_context": False})
            for layer in ("declared", "observed"):
                self.assertEqual(call_or_skip(self, self.impl.harm_paths, cfg, layer), [])

    def test_ask_tools_never_on_a_path(self):
        for _, raw in corpus():
            cfg = M.parse(raw)
            asks = {t.id for t in cfg.tools if t.mode == "ask"}
            for p in call_or_skip(self, self.impl.harm_paths, cfg, "observed"):
                self.assertFalse(p.tool_set & asks)

    def test_monotone_in_unknown(self):
        """F1：observed の真偽の札・acts を 1 つ不明にしても、道の集合は減らない。

        例外（記録・ARCHITECTURE「不明」欄）：v1 は writes_stores・reads_stores が不明のとき「置き場なし」と読む
        （過大警報を避ける設計）ため、置き場の札を不明にすると道が減ることがある。この扱いを変えるかは根幹の判断
        （Mythos）に残し、ここでは置き場の札を単調性の対象から外す。
        """
        rng = random.Random(99)
        for name, raw in corpus():
            cfg = M.parse(raw)
            before = {(p.kind, p.key) for p in call_or_skip(self, self.impl.harm_paths, cfg, "observed")}
            t = rng.choice(cfg.tools)
            candidates = [c for c in t.observed if c not in M.STORE_LIST_CAPS]
            if not candidates:
                continue
            cap = rng.choice(candidates)
            obs = dict(t.observed)
            obs[cap] = M.Cap(None, "不明", "試験で不明にした")
            t2 = M.Tool(t.id, t.label, t.mode, t.frequency, t.declared, M.FrozenMap(obs), t.origin)
            cfg2 = Config(cfg.name, cfg.untrusted_in_context, tuple(t2 if x.id == t.id else x for x in cfg.tools),
                          cfg.stores, cfg.imports)
            after = {(p.kind, p.key) for p in call_or_skip(self, self.impl.harm_paths, cfg2, "observed")}
            self.assertLessEqual(before, after, (name, t.id, cap))


class V1StoreUnknownQuirk(unittest.TestCase):
    """記録：v1 の参照実装では、置き場の札を不明にすると道が減る例がある（上の F1 の例外の具体）。"""

    def test_quirk_exists_in_reference(self):
        raw = {"skopost": 1, "stores": [{"id": "ext", "external": True}], "tools": [
            {"id": "r", "observed": {c: {"value": c == "reads_secret", "confidence": "確"}
                                     for c in ("reads_untrusted", "reads_secret", "net_out", "args_leave", "exec")}
             | {"acts": {"value": [], "confidence": "確"}, "writes_stores": {"value": [], "confidence": "確"},
                "reads_stores": {"value": [], "confidence": "確"}}},
            {"id": "w", "observed": {c: {"value": False, "confidence": "確"}
                                     for c in ("reads_untrusted", "reads_secret", "net_out", "args_leave", "exec")}
             | {"acts": {"value": [], "confidence": "確"}, "writes_stores": {"value": ["ext"], "confidence": "確"},
                "reads_stores": {"value": [], "confidence": "確"}}}]}
        before = V1.harm_paths(M.validate(raw), "observed")
        raw["tools"][1]["observed"]["writes_stores"] = {"confidence": "不明"}
        after = V1.harm_paths(M.validate(raw), "observed")
        self.assertEqual([p["tools"] for p in before], [["r", "w"]])
        self.assertEqual(after, [])


class MinCheckpoints(unittest.TestCase):
    impl = G

    def _check(self, name, cfg, paths, cp, *, exact_expected):
        self.assertIsInstance(cp, Checkpoints)
        self.assertTrue(cp.cuts(paths), (name, "全部の道を断つ"))
        allowed = {t.id for t in cfg.allowed()}
        self.assertLessEqual(set(cp.primary), allowed, "関所は allow の道具だけ")
        true_min = brute_min(cfg, paths)
        self.assertLessEqual(cp.lower_bound, true_min, name)
        self.assertLessEqual(true_min, cp.size, name)
        if cp.exact:
            self.assertEqual(cp.size, true_min, name)
        if exact_expected:
            self.assertTrue(cp.exact, f"{name}: 道具 {len(allowed)} 個（exact_limit 以下）なら厳密")
        for alt in cp.alternatives:
            self.assertTrue(cp.cuts(paths, alt), (name, alt))
        freq = {t.id: t.frequency for t in cfg.tools}
        costs = [sum(freq[x] for x in c) for c in (cp.primary,) + cp.alternatives]
        self.assertEqual(costs, sorted(costs), f"{name}: 案は frequency 合計の小さい順")

    def test_exact_small(self):
        for name, raw in corpus():
            cfg = M.parse(raw)
            paths = typed_paths(V1.harm_paths(M.to_legacy(cfg), "observed"))
            cp = call_or_skip(self, self.impl.min_checkpoints, cfg, paths)
            self._check(name, cfg, paths, cp, exact_expected=len(cfg.allowed()) <= 20)
            self.assertLessEqual(len(cp.alternatives), 5)

    def test_primary_tiebreak_matches_v1(self):
        for name, raw in corpus():
            legacy = M.validate(raw)
            cfg = M.from_legacy(legacy)
            paths = typed_paths(V1.harm_paths(legacy, "observed"))
            cp = call_or_skip(self, self.impl.min_checkpoints, cfg, paths)
            want = V1.min_checkpoints(legacy, V1.harm_paths(legacy, "observed"))
            self.assertEqual(list(cp.primary), want["primary"], name)

    def test_empty_paths(self):
        cfg = M.parse(example_raws()["example"])
        cp = call_or_skip(self, self.impl.min_checkpoints, cfg, [])
        self.assertEqual((cp.exact, cp.primary, cp.alternatives), (True, (), ()))

    def test_budget_or_limit_never_lies(self):
        """exact_limit を 0 にしても、exact=True と言うなら本当に最小（G4）。"""
        for name, raw in corpus(n_tools=10):
            cfg = M.parse(raw)
            paths = typed_paths(V1.harm_paths(M.to_legacy(cfg), "observed"))
            cp = call_or_skip(self, self.impl.min_checkpoints, cfg, paths, exact_limit=0, time_budget_s=0.0)
            self._check(name, cfg, paths, cp, exact_expected=False)

    def test_max_alternatives_respected(self):
        for name, raw in corpus():
            cfg = M.parse(raw)
            paths = typed_paths(V1.harm_paths(M.to_legacy(cfg), "observed"))
            cp = call_or_skip(self, self.impl.min_checkpoints, cfg, paths, max_alternatives=1)
            self.assertLessEqual(len(cp.alternatives), 1, name)


class ApplyAndExplain(unittest.TestCase):
    impl = G

    def test_apply_only_tightens(self):
        for name, raw in corpus():
            cfg = M.parse(raw)
            cut = [t.id for t in cfg.tools][::2] + ["no_such_tool"]
            out = call_or_skip(self, self.impl.apply_checkpoints, cfg, cut)
            self.assertEqual(M.parse(raw), cfg, "入力は変えない")
            for a, b in zip(cfg.tools, out.tools):
                if a.id in cut:
                    self.assertEqual(b.mode, "ask")
                    self.assertEqual((a.declared, a.observed, a.frequency, a.label), (b.declared, b.observed, b.frequency, b.label))
                else:
                    self.assertEqual(a, b)
            self.assertEqual((out.name, out.stores, out.untrusted_in_context), (cfg.name, cfg.stores, cfg.untrusted_in_context))

    def test_explain_matches_v1_reasons(self):
        for name, raw in corpus():
            legacy = M.validate(raw)
            cfg = M.from_legacy(legacy)
            want = V1.analyze(legacy)
            paths = typed_paths(want["paths"])
            cp = M.result_from_legacy(want).checkpoints
            got = call_or_skip(self, self.impl.explain, cfg, paths, cp)
            self.assertEqual(got, want["checkpoints"]["reasons"], name)


class AnalyzeMatchesV1(unittest.TestCase):
    impl = G

    @staticmethod
    def _norm(d: dict) -> dict:
        d = dict(d)
        d["summary"] = {**d["summary"], "seconds": 0}
        d["checkpoints"] = {**d["checkpoints"], "alternatives": None}
        return d

    def test_analyze(self):
        for name, raw in corpus():
            legacy = M.validate(raw)
            got = call_or_skip(self, self.impl.analyze, M.from_legacy(legacy))
            self.assertIsInstance(got, M.AnalysisResult)
            self.assertEqual(self._norm(M.result_to_dict(got)), self._norm(V1.analyze(legacy)), name)


if __name__ == "__main__":
    unittest.main()
