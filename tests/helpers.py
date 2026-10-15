"""試験の共通補助（担当 A 所有）。標準ライブラリのみ。

- `gen_raw_config(rng, ...)`：SPEC v1 の正しい入力をランダムに作る（性質試験・契約試験用。種で再現できる）
- `example_raws()`：examples/ と skopost example の入力
- `call_or_skip(tc, fn, ...)`：段 2 の空実装（NotImplementedYet）なら「未実装」として飛ばす
- `signature_of(fn)`：契約の署名比較用の正規化文字列
"""
from __future__ import annotations

import inspect
import json
import os
import random
import sys
import unittest
from typing import Any, Callable

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from skopost.model.constants import ACT_KINDS, BOOL_CAPS  # noqa: E402
from skopost.model.errors import NotImplementedYet  # noqa: E402
from skopost.model.examples import EXAMPLE  # noqa: E402

PKG = os.path.join(ROOT, "skopost")
FIXTURES = os.path.join(HERE, "fixtures")
CONFS = ("確", "論", "推", "不明")
SEEDS = tuple(range(int(os.environ.get("SKOPOST_TEST_SEEDS", "60"))))


def example_raws() -> dict[str, dict]:
    out = {"example": json.loads(json.dumps(EXAMPLE))}
    for name in ("notes-agent.json", "browser-agent.json"):
        with open(os.path.join(ROOT, "examples", name), encoding="utf-8") as f:
            out[name] = json.load(f)
    return out


def _rand_cap_value(rng: random.Random, cap: str, store_ids: list[str]) -> Any:
    if cap in BOOL_CAPS:
        return rng.random() < 0.4
    if cap == "acts":
        return rng.sample(ACT_KINDS, rng.randint(0, 2)) if rng.random() < 0.3 else []
    return rng.sample(store_ids, rng.randint(0, min(2, len(store_ids)))) if store_ids else []


def gen_raw_config(rng: random.Random, *, n_tools: int | None = None, n_stores: int | None = None,
                   p_unknown: float = 0.15, p_observed: float = 0.7, shorthand: float = 0.1) -> dict:
    """SPEC v1 として正しい入力（辞書）を作る。道が出やすいように危ない札をそこそこ混ぜる。"""
    n_tools = rng.randint(1, 8) if n_tools is None else n_tools
    n_stores = rng.randint(0, 3) if n_stores is None else n_stores
    stores = [{"id": f"s{i}", "label": f"置き場{i}", "external": rng.random() < 0.3,
               "executes": rng.random() < 0.2, "secret": rng.random() < 0.3} for i in range(n_stores)]
    sids = [s["id"] for s in stores]
    tools = []
    caps = list(BOOL_CAPS) + ["acts", "writes_stores", "reads_stores"]
    for i in range(n_tools):
        declared = {c: _rand_cap_value(rng, c, sids) for c in caps if rng.random() < 0.35}
        observed: dict[str, Any] = {}
        for c in caps:
            if rng.random() >= p_observed:
                continue
            if rng.random() < shorthand:
                observed[c] = _rand_cap_value(rng, c, sids)
            elif rng.random() < p_unknown:
                observed[c] = {"confidence": rng.choice(["不明", "unknown"]), "evidence": "わからない"}
            else:
                observed[c] = {"value": _rand_cap_value(rng, c, sids), "confidence": rng.choice(CONFS[:3]),
                               "evidence": rng.choice(["", "読んだ", "動かした"])}
        t: dict[str, Any] = {"id": f"t{i}", "label": f"道具{i}", "mode": "allow" if rng.random() < 0.8 else "ask",
                             "frequency": rng.randint(1, 9), "declared": declared, "observed": observed}
        tools.append(t)
    return {"skopost": 1, "name": f"rand-{rng.random():.6f}", "untrusted_in_context": rng.random() < 0.9,
            "stores": stores, "tools": tools}


def call_or_skip(tc: unittest.TestCase, fn: Callable[..., Any], *args: Any, **kw: Any) -> Any:
    """空実装なら skipTest（契約は段 2 の実装が入った時点で自動的に効く）。"""
    try:
        return fn(*args, **kw)
    except NotImplementedYet as e:
        tc.skipTest(f"未実装：{e.what}（{e.owner}）")


def signature_of(fn: Callable[..., Any]) -> str:
    """注釈込みの署名（from __future__ import annotations なので注釈は文字列のまま比較できる）。"""
    return str(inspect.signature(fn))


def mask_seconds(text: str) -> str:
    import re
    return re.sub(r'(計算 |"seconds": )[0-9.e-]+', r"\1X", text)
