# Skopost

Static analyzer for AI agent tool setups: it reads a description of the tools wired into an agent (MCP servers, Claude settings, OpenAPI specs or a native JSON sheet), enumerates the dangerous paths that arise from *combinations* of tools, and proposes the smallest set of human-confirmation checkpoints that cuts them all, with reasons and alternatives.

> **Research preview.** No guarantees of any kind: not a security product, not an audit, and a clean report does not mean a setup is safe. Interfaces and output formats may change. License: Apache-2.0 (see [LICENSE](LICENSE), [NOTICE](NOTICE)); Copyright 2026 Yoshiaki Takashita. Version note: the distribution version is 0.1.0; the `1.1.0.dev0` that appears in the code and in SARIF output is the schema/format version, a separate thing (see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) section 2.3). Security reports: GitHub private vulnerability reporting ([SECURITY.md](SECURITY.md)).

Japanese documentation: [GUIDE-JA.md](GUIDE-JA.md) (non-engineer guide) and the [Japanese section below](#skopost日本語).

## Install and use

No dependencies: Python >= 3.10 (tested on 3.10–3.13), standard library only. Clone the repository and run the commands below with `python3 skopost.py`, or install it locally with `pip install .` and use the `skopost` command (not published on PyPI yet):

```sh
python3 skopost.py example > my.json          # a template to edit
python3 skopost.py validate my.json
python3 skopost.py check my.json --explain
python3 skopost.py check examples/notes-agent.json --format json
python3 skopost.py check my.json --format sarif --out skopost.sarif     # for code-scanning UIs
python3 skopost.py baseline my.json --out baseline.json                 # record today's paths
python3 skopost.py check my.json --baseline baseline.json               # exit 2 only for NEW paths
python3 verify.py --quick                                               # tests + synthetic evaluation
```

`--adapter auto|native|mcp|openapi|claude-settings` selects the input format (default: auto-detect). It is read-only: no network access, no telemetry, nothing written unless you pass `--out` (never overwrites).

## What it detects, and what it does not

Detects (from the tool sheets you give it): paths from untrusted text to command execution, irreversible actions, or secret exfiltration through outbound channels, including paths via shared stores; then a minimum checkpoint set (exact solver, with the number of "ask" points).

Does not: verify that a sheet is true, model how often humans click through confirmations, track values flowing inside the agent context, or run any live test. Unreadable input keys are listed in the report rather than silently skipped. Full list: [LIMITATIONS.md](LIMITATIONS.md). Defensive use only.

## Confidence marks

Each capability on a tool carries a mark (written in Japanese in the output): **確** = confirmed (a human observed it), **論** = reasoned from syntax or structure, **推** = guessed, e.g. from a description text, **不明** = unknown. Unknown is treated as the dangerous side. Rules that infer capabilities automatically never produce 確; inference may add information but never removes a path.

## Numbers

All numbers are from a **synthetic benchmark**, not from real-world setups; 4 of 9 preregistered predictions missed ([RESULTS.md](RESULTS.md), [docs/RESULTS-CORPUS.md](docs/RESULTS-CORPUS.md)). With 10 tools and a 10% declaration error rate, checkpoints chosen from declarations alone leave a path in 32% of configurations and a denylist in 42%; Skopost leaves 0% by construction (given the sheets) with 2.5 checkpoints on average, versus 6.9 for ask-everything. Real-world failure rates are unknown.

## Name collision

On PyPI, `skopos` (an unrelated reinforcement-learning library) and `skopos-audit` (a Python supply-chain tool) already exist and are unrelated to this project. The package name `skopost` was unregistered on PyPI and npm as of 2026-10-15 (not reserved; it could be taken before release). Trademark databases have not been checked.

---

# Skopost（日本語）

> 名前の由来：古代ギリシャ語 *skopos*（見張り）＋ *post*（持ち場。check post＝関所）。旧仮名は Sekisho。Skopost は街道の関所のように、通らねばならない所にだけ見張りを置く。

**AI エージェントが取り返しのつかない操作をする前の「人の確認」を、止めれば危ない道が消える最小の場所にだけ置く。**

道具の一覧で管理しても、事故は組み合わせで起きる——「設定を読む」＋「検索語を URL に載せて送る」は、どちらも「読むだけ」なのに秘密の持ち出しになる。Skopost は道具の札（宣言と、人が確かめた実能力）から**危ない道を全部数え、それを断つ最小の関所**を、理由と代替案つきで出す。

- 対象：AI の担当・MCP・ブラウザ操作に道具を 5〜20 個繋いでいる個人・小さな組織。
- 既定で安全：**読むだけ・通信ゼロ・テレメトリなし・何も書き換えない**（`--out` を付けたときだけ 1 ファイル書く。上書きしない）。
- 依存ゼロ：Python 3.10 以上（3.10〜3.13 で試験）の標準ライブラリだけ。クローンしてそのまま動く（`pip install .` で `skopost` コマンドにもなる。PyPI には未公開）。

## 30 秒で試す

```sh
python3 skopost.py check examples/notes-agent.json --explain
```

出力の要点：「危ない道 4 本。関所 2 か所で全部断てます」「宣言だけの関所では 2 本の道が残ります」。

自分の構成で試す：`python3 skopost.py example > my.json` を手直しして `check`。書き方は [SPEC.md](SPEC.md)。

検証を再現する：`python3 verify.py --quick`（約 40 秒・試験 304 本＋合成の評価＋事前登録との照合。速い版なので予言の当たり外れは本番の RESULTS.md と少し違う）。

## 限界（最初に）

- **札は人が書く**。札が間違えば地図も間違う。Skopost は札の正しさを確かめない（確度と根拠の欄を見ること）。
- **人の確認が素通しされる率は模型に入れていない**。関所は「人が止める」前提。
- **文脈の中の値の流れは追わない**（粗く・保守的）。細かい情報流の制御が使えるなら（CaMeL など）そちらが上。
- **全部合成で測った**。現実の構成の数字ではない。事前登録 9 件中 4 件は外れた（[RESULTS.md](RESULTS.md)）。
- 防御専用。攻撃の手順・検知回避・辺の実証（注入文を流す）は含まない。

詳しくは [LIMITATIONS.md](LIMITATIONS.md)。

## 測った数字（合成・[RESULTS.md](RESULTS.md)）

| | 失敗率（道が残る） | 確認の手間（ask の個数） |
|---|---|---|
| 宣言だけで決めた関所（誤り率 10%・道具 10） | 32% | 2.2 |
| 拒否リスト（宣言で危ない道具を全部止める） | 42%（誤り率 0 でも 19%） | 2.4 |
| 全部聞く | 0% | 6.9 |
| **Skopost**（観察の札・不明は危ない側） | **0%**（構成上） | **2.5** |

## 文書

[GUIDE-JA.md](GUIDE-JA.md)（非エンジニア向け・図とたとえ）／[SPEC.md](SPEC.md)／[DESIGN.md](DESIGN.md)／[PREREG.md](PREREG.md)／[RESULTS.md](RESULTS.md)／[LIMITATIONS.md](LIMITATIONS.md)／[SECURITY.md](SECURITY.md)／[CONTRIBUTING.md](CONTRIBUTING.md)／[CHOICES.md](CHOICES.md)

## 名前の衝突の注意（日本語）

PyPI にはすでに `skopos`（別の、放置された強化学習ライブラリ）と `skopos-audit`（Python の供給網の道具）があり、この計画とは無関係。`skopost` は 2026-10-15 時点で PyPI・npm とも未登録（予約ではないので公開前に再確認）。商標（J-PlatPat・USPTO・EUIPO）は未確認。

## ライセンス

Apache-2.0（[LICENSE](LICENSE)・[NOTICE](NOTICE)）。著作権者：Yoshiaki Takashita。配布の版は 0.1.0。コードや SARIF 出力の `1.1.0.dev0` は出力形式の「スキーマの版」で、配布の版とは別（[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §2.3）。
