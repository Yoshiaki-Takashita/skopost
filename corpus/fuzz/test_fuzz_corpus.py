"""コーパスを壊して ingest に通すファズ：例外は SkopostError だけ（M3 の拡張・実例風の形を種に）。"""
from __future__ import annotations

import copy
import json
import os
import random
import unittest

from _common import TmpFiles, gen, load_real, manifest

from skopost.ingest import ingest
from skopost.model.errors import SkopostError

N_PER_FILE = int(os.environ.get("SKOPOST_CORPUS_FUZZ", "6"))
WEIRD = (None, True, 0, -1, 1.5e308, "", "‮\u0000퟿", "😀" * 50, [], {}, [[[]]], {"": {}}, "x" * 5000)


def _nodes(obj, path=()):
    yield path, obj
    if len(path) > 30:  # 深く入れ子にした節の中までは辿らない（試験側の再帰の上限）
        return
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            yield from _nodes(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _nodes(v, path + (i,))


def _set(obj, path, val):
    if not path:
        return val
    cur = obj
    for p in path[:-1]:
        cur = cur[p]
    cur[path[-1]] = val
    return obj


def mutate(rng: random.Random, data):
    d = copy.deepcopy(data)
    for _ in range(rng.randint(1, 4)):
        nodes = list(_nodes(d))
        path, node = rng.choice(nodes)
        op = rng.random()
        if op < 0.4:
            d = _set(d, path, copy.deepcopy(rng.choice(WEIRD)))
        elif op < 0.6 and path:
            parent = d
            for p in path[:-1]:
                parent = parent[p]
            del parent[path[-1]]
        elif op < 0.8 and isinstance(node, dict):
            node[rng.choice(("あ", "a/b~c", "", "x-" + "z" * 300))] = copy.deepcopy(rng.choice(WEIRD))
        else:
            deep = copy.deepcopy(rng.choice(WEIRD))
            for _ in range(rng.randint(10, 60)):
                deep = [deep] if rng.random() < 0.5 else {"k": deep}
            d = _set(d, path, deep)
    return d


class FuzzRealCorpus(unittest.TestCase):
    def setUp(self):
        self.tmp = TmpFiles()

    def tearDown(self):
        self.tmp.close()

    def _run(self, p, adapter):
        try:
            ingest(p, adapter=adapter)
        except SkopostError:
            pass

    def test_mutations_only_skoposterror(self):
        rng = random.Random(gen.SEED)
        for rel, ent in sorted(manifest()["files"].items()):
            base = load_real(rel)
            for k in range(N_PER_FILE):
                d = mutate(rng, base)
                p = self.tmp.write(f"m{k}/" + os.path.basename(rel), d)
                for ad in (ent["format"], None):
                    with self.subTest(rel=rel, k=k, adapter=ad):
                        self._run(p, ad)

    def test_bytes_level(self):
        rng = random.Random(1)
        for rel, ent in sorted(manifest()["files"].items())[::4]:
            raw = json.dumps(load_real(rel)).encode()
            cases = [raw[: rng.randint(0, len(raw))], raw.replace(b"{", b"[", 1), b"\xef\xbb\xbf" + raw,
                     raw[:10] + b"\xff\xfe" + raw[10:], b"[" * 5000 + b"]" * 5000]
            for i, c in enumerate(cases):
                p = self.tmp.write(f"b{i}/" + os.path.basename(rel), None, raw=c)
                with self.subTest(rel=rel, i=i):
                    self._run(p, ent["format"])
                    self._run(p, None)

    def test_huge_synth_rejected_or_read(self):
        # 道具 64 の合成を native として auto で読む（上限内）
        for i in range(3):
            p = self.tmp.write(f"s{i}.json", gen.synth(gen.SEED, 64, i))
            res = ingest(p)
            self.assertEqual(len(res.config.tools), 64)


if __name__ == "__main__":
    unittest.main()
