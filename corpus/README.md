# corpus — 評価用コーパス（段 3・パッケージ外・配布物に含めない）

- `gen.py`：生成器（種 `SEED = 20261013`・標準ライブラリのみ・外部通信なし）。
  - 合成 `synth(seed, n, i)`：native 構成、道具 10〜64 個。(種, n, i) だけで決まる。
  - 実例風 `real/`：MCP・OpenAPI・Claude settings 各 24 件。**すべて自作の合成**（実在の第三者の設定は写していない。
    ホストは example.com / example.org / localhost のみ）。`python3 corpus/gen.py real --write` で同じバイト列に作り直せる。
  - `real/MANIFEST.json`：各ファイルの形式と、植えた「読み手が解釈しない鍵」の JSON Pointer（記録率の正解表）。
- `eval.py`：評価（docs/PREREG-CORPUS.md の予言を判定し、結果を JSON に出す）。
- `fuzz/`・`props/`：ファズと性質試験。`python3 -m unittest discover -s corpus -t .`（tests/ の本数は変えない）。
