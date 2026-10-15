# PREREG-CORPUS — 段 3 コーパス評価の事前登録

登録日：2026-10-13。**評価（corpus/eval.py）を書く・走らせる前に**この文書と `prereg-corpus.json` をコミットする。
結果は `docs/RESULTS-CORPUS.md` に外れも含めて書く。予言・外れ条件はあとから変えない（変えるなら別の版として足す）。

## 材料（コミット済み・種固定）

- 合成：`corpus/gen.py` の `synth(seed=20261013, n, i)`（native・道具 10〜64 個）。
- 実例風：`corpus/real/`（MCP・OpenAPI・Claude settings 各 24 件、すべて自作の合成）。植えた鍵の正解表は
  `corpus/real/MANIFEST.json`（植えた数：openapi 32・mcp 26・claude-settings 9＝計 67）。
- 走らせる人は生成器と ingest のコードを**読んだうえで**予言している（C1b はその読みに基づく）。盲検ではない。

## 予言と外れ条件

| ID | 測るもの | 予言 | 外れ条件 |
|---|---|---|---|
| C1 | ingest の「読めなかった鍵の記録率」（x- 以外の植えた鍵が notes の pointer に完全一致で現れる割合） | 100%（I3） | 1 件でも記録漏れ |
| C1b | OpenAPI の Path Item・Operation に植えた `x-` 拡張の記録率 | 0%（読み手が黙って飛ばす） | 1 件でも記録される |
| C2 | 自動判別（`ingest.detect`）の誤り率。誤判別と判別拒否（SkopostError）の両方を誤りに数える。混在＝実例風 72＋合成 native 120 | < 2%（I4） | ≥ 2% |
| C2b | 同じ、ファイル名を全部 `config.json` に変えて | < 2% | ≥ 2% |
| C3 | infer の規則が足した札（`pipeline.apply_inferred` 後、source が `infer:` の観察の札）の確度の分布 | 「確」0 件（F2） | 1 件でも「確」 |
| C3b | 同じ分布の「推」の割合 | ≥ 80% | < 80% |
| C4 | 厳密解（`graph.analyze` の `checkpoints`、exact=True のもの）の大きさ vs 全探索の最小。合成 n=10〜14 を各 200＝1,000 構成 | 不一致 0（G1） | 1 件でも不一致、または exact=False が出る |
| C5 | n=64 の 50 構成で `graph.analyze` の時間 | 95 パーセンタイル < 2 秒（G2） | ≥ 2 秒 |
| C6 | 方針 monotone と v1 の道の差（`graph.policy_diff` 相当。合成 n∈{10,16,24,32,48,64} の計 1,000 構成） | monotone が少ない構成 0 | 1 件でもある |
| C6b | monotone で道が増える構成の割合 | 10%〜50% | 範囲外 |
| C6c | 道の総数の増加率 | 2%〜25% | 範囲外 |

## 縮めたところ（理由）

- G1 は ARCHITECTURE では「n≤14 で 5 万例」。ここでは 1,000 構成（全探索が 2^14 の部分集合を舐めるため時間がかかる。
  5 万例は走らせない）。tests/test_graph_* に既存の総当たり照合がある。
- 実例風は合成なので、K1（実例での declared の失敗率 g）は**測れない**（実在の設定を集めていないため・不明のまま）。
