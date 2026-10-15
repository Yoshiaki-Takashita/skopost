# Skopost 0.1.0-preview

## 日本語

研究段階の試作の公開です。**保証はありません**。セキュリティ製品でも監査でもなく、「危ない道なし」の報告は安全の証明ではありません。出力の形式や使い方は今後変わることがあります。

**できること**
- AI エージェントに繋いだ道具の札（MCP の設定・Claude の設定・OpenAPI・独自の JSON）を読み、道具の**組み合わせ**で生まれる危ない道（外の文章 → コマンド実行・取り返しのつかない操作・秘密の持ち出し）を数える。
- その道を全部断つ**最小の「人の確認」の場所**を、理由と代替案つきで出す（厳密解）。
- 読むだけ・通信なし・テレメトリなし。Python 3.10〜3.13 の標準ライブラリだけで動く。

**限界と不明**
- 札が正しいかは確かめない。札が間違えば結果も間違う。
- 人が確認を素通しする率、文脈の中の値の流れは扱わない。
- 数字はすべて**合成**の評価。事前登録した予言 9 件のうち 4 件は外れた（本番の評価）。現実の構成での精度は**不明**。
- 自作の合成コーパス 72 件で、読めない鍵の記録漏れを 1 種見つけて直した。ほかの形式の版の違いへの追従は不明。
- PyPI には出していない。名前の商標の確認は済んでいない。

## English

A research preview. **No guarantees**: this is not a security product or an audit, and a clean report does not mean a setup is safe. Interfaces and output formats may change.

**What it does**
- Reads tool sheets for an AI agent (MCP configs, Claude settings, OpenAPI, or a native JSON sheet) and enumerates dangerous paths that arise from *combinations* of tools (untrusted text → command execution, irreversible actions, or secret exfiltration).
- Computes the smallest set of human-confirmation checkpoints that cuts all of them (exact solver), with reasons and alternatives.
- Read-only, no network, no telemetry. Python 3.10–3.13, standard library only.

**Limits and unknowns**
- It does not verify that the sheets are true; wrong sheets give wrong maps.
- It does not model how often humans click through confirmations, nor value flow inside the agent context.
- All numbers come from **synthetic** evaluation; 4 of 9 preregistered predictions missed in the full run. Real-world accuracy is **unknown**.
- A self-made synthetic corpus of 72 files found and fixed one class of unrecorded keys; coverage of other format versions is unknown.
- Not published on PyPI. Trademark clearance for the name has not been done.
