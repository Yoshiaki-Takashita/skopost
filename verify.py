#!/usr/bin/env python3
"""検証パック（1 コマンド）：試験 → 例 → 合成の評価 → 事前登録（prereg.json）との照合。
外部通信なし・何も書かない（--out で評価の JSON を 1 つ書ける）。

  python3 verify.py --quick     # 1 分ほど
  python3 verify.py --full      # 数分
終了コード：0＝試験が緑で予想も全部当たり／3＝試験は緑だが外れた予想あり（正直に表示）／1＝試験が赤
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bench  # noqa: E402
import skopost as S  # noqa: E402


def run_tests() -> bool:
    suite = unittest.defaultTestLoader.discover(os.path.join(HERE, "tests"))
    buf = io.StringIO()
    result = unittest.TextTestRunner(stream=buf, verbosity=0).run(suite)
    print(f"試験：{result.testsRun} 本・失敗 {len(result.failures)}・エラー {len(result.errors)}")
    if not result.wasSuccessful():
        print(buf.getvalue())
    return result.wasSuccessful()


def run_examples() -> bool:
    ok = True
    for name, expect_code in (("notes-agent.json", 2), ("browser-agent.json", 2)):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = S.main(["check", os.path.join(HERE, "examples", name)])
        print(f"例 {name}：終了コード {code}（期待 {expect_code}）")
        ok &= code == expect_code
    return ok


def check_prereg(res: dict) -> list[tuple[str, bool, str]]:
    pre = json.load(open(os.path.join(HERE, "prereg.json"), encoding="utf-8"))
    cells = {c["cell"]: c for c in res["cells"]}

    def metric(cell: str, method: str | None, m: str) -> float:
        c = cells[cell]
        return c[m] if method is None else c[m][method]

    out = []
    for pid, pr in pre["predictions"].items():
        m = pr["metric"]
        try:
            if pr.get("all_cells"):
                vals = [c[m][pr["method"]] for c in res["cells"]]
                v = max(vals)
                ok = pr["min"] <= v <= pr["max"]
                detail = f"max {v:.3f}"
            elif "ratio" in pr:
                a, b = pr["ratio"]
                v = metric(pr["cell"], a, m) / metric(pr["cell"], b, m)
                ok = v <= pr["max"]
                detail = f"{v:.3f}"
            elif "diff" in pr:
                a, b = pr["diff"]
                v = metric(a, pr["method"], m) - metric(b, pr["method"], m)
                ok = (v >= pr.get("min", -1e9)) and (v <= pr.get("max", 1e9))
                detail = f"{v:+.3f}"
            elif "less" in pr:
                a, b = pr["less"]
                va, vb = metric(pr["cell"], a, m), metric(pr["cell"], b, m)
                ok = va < vb
                detail = f"{va:.3f} < {vb:.3f}"
            elif "cell_prefix" in pr:
                vals = [c[m] for c in res["cells"] if c["cell"].startswith(pr["cell_prefix"])]
                v = sum(vals) / len(vals)
                ok = v <= pr["max"]
                detail = f"mean {v:.4f}"
            else:
                v = metric(pr["cell"], pr["method"], m)
                ok = pr["min"] <= v <= pr["max"]
                detail = f"{v:.3f}"
                if pr.get("also_f_zero"):
                    fv = cells[pr["cell"]]["f"]
                    ok = ok and fv == 0.0
                    detail += f", f={fv:.3f}"
        except (KeyError, ZeroDivisionError) as ex:
            ok, detail = False, f"計算できず：{ex!r}"
        out.append((pid, ok, f"{pr['desc']} → {detail}"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--out", default=None, help="評価の JSON を書く（既存は上書きしない）")
    a = ap.parse_args(argv)
    configs = 400 if a.full else 100
    print(f"Skopost 検証パック（{'full' if a.full else 'quick'}・{configs} 構成/格子点・種 {bench.DEFAULT_SEED}）")
    if not run_tests():
        return 1
    if not run_examples():
        return 1
    res = bench.run(bench.DEFAULT_SEED, configs)
    print(bench.table(res))
    print()
    checks = check_prereg(res)
    misses = 0
    for pid, ok, detail in checks:
        print(f"{'当たり' if ok else '外れ  '} {pid}: {detail}")
        misses += not ok
    print(f"\n予想 {len(checks)} 件中 当たり {len(checks) - misses}・外れ {misses}")
    if a.out:
        if os.path.exists(a.out):
            print(f"{a.out} は既にあります。上書きしません")
        else:
            with open(a.out, "w", encoding="utf-8") as f:
                json.dump({"bench": res, "prereg_checks": [{"id": p, "ok": o, "detail": d} for p, o, d in checks]},
                          f, ensure_ascii=False, indent=1)
            print(f"書きました：{a.out}")
    return 3 if misses else 0


if __name__ == "__main__":
    sys.exit(main())
