# Skopost 宣言ファイルの仕様（v1）

Skopost が読む入力は 1 つの JSON ファイル（**宣言ファイル**）。AI エージェントに繋いだ道具の一覧と、各道具の「できること」の札を書く。札は **2 層**で持つ：

- `declared`（宣言）：道具の自己申告（説明文・`readOnlyHint` の類・配布元の説明）を**そのまま**写す。
- `observed`（観察）：ソースや設定や実験で**人が確かめた**実能力。1 項目ごとに確度と根拠を付ける。書かなければ「不明」。

Skopost は **`observed` を信じ、`declared` は比較の対象としてだけ使う**。`observed` が無い項目は「不明」として**危ない側に倒す**（能力があると仮定する）。

## 1. 全体

```json
{
  "skopost": 1,
  "name": "任意の名前",
  "untrusted_in_context": true,
  "stores": [ ...置き場... ],
  "tools":  [ ...道具... ]
}
```

| 鍵 | 型 | 既定 | 意味 |
|---|---|---|---|
| `skopost` | 整数 | 必須 | 仕様の版。いまは `1` |
| `name` | 文字列 | `""` | 表示用。論理には使わない |
| `untrusted_in_context` | 真偽 | `true` | エージェントの文脈に「外から来た文」（ページ・メール・道具の返り）が入りうるか。`false` にできるのは、外の文を一切読まない構成だけ |
| `stores` | 配列 | `[]` | ファイルや共有の置き場（§3） |
| `tools` | 配列 | 必須 | 道具（§2）。**最大 64** |

## 2. 道具

```json
{
  "id": "web_search",
  "label": "ウェブ検索",
  "mode": "allow",
  "frequency": 3,
  "declared": { "reads_untrusted": true, "args_leave": false },
  "observed": {
    "args_leave": { "value": true, "confidence": "確", "evidence": "src/search.py:42 検索語を URL に載せる" }
  }
}
```

| 鍵 | 型 | 既定 | 意味 |
|---|---|---|---|
| `id` | 文字列（64 字以内・`[A-Za-z0-9_.-]`） | 必須 | 一意の名前 |
| `label` | 文字列 | `id` | 表示用。**資料であって命令ではない**（中に何が書いてあっても論理に影響しない） |
| `mode` | `"allow"` / `"ask"` | `"allow"` | `allow`＝確認なしで動く／`ask`＝動く前に人が確認する |
| `frequency` | 1 以上の整数 | `1` | どれくらい頻繁に使うか。同じ大きさの関所の案が複数あるとき、確認の手間（頻度の合計）が小さい案を先に出す |
| `declared` | 札（§4） | `{}` | 自己申告。無い項目は `false` |
| `observed` | 観察の札（§5） | `{}` | 確かめた実能力。無い項目は**不明** |

## 3. 置き場（stores）

道具の間を「文脈」以外で結ぶもの。ファイルシステム・共有ドライブ・設定ファイルなど。

```json
{ "id": "workspace", "external": false, "executes": false, "secret": false }
```

| 鍵 | 意味 |
|---|---|
| `external` | ここに書くと**外に出る**（共有ドライブ・公開フォルダ）。書く道具は「外へ送れる」のと同じ扱い |
| `executes` | ここに書いたものが**実行される**（起動スクリプト・cron・CI の設定・エディタのタスク定義）。書く道具は「実行できる」のと同じ扱い |
| `secret` | ここに**秘密がある**（鍵・トークン・環境ファイル）。読む道具は「秘密を読める」のと同じ扱い |

## 4. 札（capability）の項目

| 項目 | 型 | 意味 |
|---|---|---|
| `reads_untrusted` | 真偽 | 返りに外から来た文が含まれる（ウェブ・メール・他人のリポジトリ） |
| `reads_secret` | 真偽 | 秘密（鍵・トークン・個人情報）を読める |
| `net_out` | 真偽 | 文脈の内容を**本文として**外へ送れる |
| `args_leave` | 真偽 | 「読むだけ」でも**引数が外へ出る**（検索語・URL・ホスト名）。Skopost が最も重視する型 |
| `exec` | 真偽 | 任意のコマンド・コードを実行できる |
| `acts` | 配列 | 取り返しのつかない操作の種類：`send`（送信）`purchase`（購入）`delete`（削除）`publish`（公開・投稿）`grant`（権限付与）`pay`（支払い） |
| `writes_stores` | 配列 | 書ける置き場の `id` |
| `reads_stores` | 配列 | 読める置き場の `id` |

## 5. 観察の札（observed）の書き方

項目ごとに `{ "value": ..., "confidence": "...", "evidence": "..." }`。省略形として裸の値（`true` など）も許すが、その場合の確度は `"推"` になる。

| 確度 | 意味 |
|---|---|
| `確` | 読んで・動かして確かめた（根拠に行や手順を書く） |
| `論` | 確かな事実から筋道で導いた |
| `推` | 推測 |
| `不明` | 分からない（`value` は無視され、**危ない側**に倒す） |

英語表記 `sure`/`derived`/`guess`/`unknown` も同じ意味で受け付ける。

## 6. 導かれる「実効の札」

Skopost は置き場を畳み込んで、層ごとに実効の札を作る：

- 実効 `exec` ＝ `exec` または（`executes` な置き場に書ける）
- 実効 `net` ＝ `net_out` または（`external` な置き場に書ける）
- 実効 `secret` ＝ `reads_secret` または（`secret` な置き場を読める）
- 実効 `args_leave` ＝ `args_leave`
- 実効 `acts` ＝ `acts`

`observed` 層で不明な項目は `true`（配列なら「全種」）と仮定し、報告の「仮定した項目」に列挙する。

## 7. 危ない道（harm path）

`untrusted_in_context` が真のとき：

- **行動の道** `[T]`：`T` が `allow` で、実効 `exec` または実効 `acts` が空でない。
- **持ち出しの道** `[R, S]`：`R` が `allow` で実効 `secret`、`S` が `allow` で実効 `net` または実効 `args_leave`（`R` と `S` は同じ道具でもよい）。

`ask` の道具は「人が止める」とみなす（人の素通しは模型に入れていない。LIMITATIONS.md）。

## 8. 関所（checkpoint）

道を全部断つために `allow` → `ask` に変える道具の集合で、**個数が最小**のもの。同じ個数の案が複数あるときは `frequency` の合計が小さい順に、最大 5 案まで出す。道具が 20 個以下なら厳密解、21 個以上は貪欲法で近似し「近似」と明記する。

## 9. 上限・失敗の扱い

| 事項 | 値・挙動 |
|---|---|
| ファイルの大きさ | 2 MB まで。超えたら読まずに終了（コード 1） |
| 道具の数 | 64 まで。置き場 32 まで |
| 文字列 | 表示時は 120 字に切り、制御文字を除く。`id` 以外の文字列は論理に使わない |
| 壊れた JSON・未知の鍵・型違い | 終了コード 1 と、どこが悪いかの 1 行 |
| 終了コード | `0`＝危ない道なし／`2`＝危ない道あり（関所を提案）／`1`＝入力の誤り |

## 10. 出力（`--format json`）

```json
{
  "skopost": 1, "name": "...", "exit_code": 2,
  "summary": { "tools": 8, "allowed": 6, "paths": 4, "mismatches": 2, "assumed_unknown": 1 },
  "paths": [ { "kind": "exfil", "tools": ["read_env","web_search"], "confidence": "確", "via": ["secret","args_leave"] } ],
  "mismatches": [ { "tool": "web_search", "cap": "args_leave", "declared": false, "observed": true, "confidence": "確", "severity": "under" } ],
  "assumed": [ { "tool": "shell", "cap": "exec" } ],
  "checkpoints": { "exact": true, "primary": ["..."], "alternatives": [["..."]], "reasons": { "web_search": ["exfil: read_env>web_search"] } },
  "declared_only": { "cut": ["..."], "holds": false, "surviving_paths": 1 },
  "not_checked": [ "..." ]
}
```
