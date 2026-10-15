# Skopost 報告：claude-settings

**結論**：危ない道 24 本。関所 4 か所で全部断てます。

- 道具 4（確認なし 4）／宣言だけの地図では道 0 本（見落とし 24 本）／宣言と観察の食い違い 4／不明として危ない側に倒した項目 20

## 関所（ここに人の確認を置く）

- **Read**（）→ `mode: ask`
- **Bash**（）→ `mode: ask`
- **Edit**（）→ `mode: ask`
- **WebFetch**（）→ `mode: ask`

## 宣言だけで決めたらどうなるか

宣言だけの関所 （なし） では、観察の層で **24 本**の道が残ります：`Read`、`Read`、`Bash`、`Bash`、`Edit`、`Edit`、`WebFetch`、`WebFetch`、`Read>Read`、`Read>Bash`、`Read>Edit`、`Read>WebFetch`、`Bash>Read`、`Bash>Bash`、`Bash>Edit`、`Bash>WebFetch`、`Edit>Read`、`Edit>Bash`、`Edit>Edit`、`Edit>WebFetch`、`WebFetch>Read`、`WebFetch>Bash`、`WebFetch>Edit`、`WebFetch>WebFetch`

これが「一覧で管理すると安全の錯覚になる」の具体です。

## 危ない道

| 種類 | 道 | 確度 | 経路 |
|---|---|---|---|
| 実行 | Read | 不明 | exec |
| 取り返しのつかない操作 | Read | 不明 | acts:send,purchase,delete,publish,grant,pay |
| 実行 | Bash | 論 | exec |
| 取り返しのつかない操作 | Bash | 不明 | acts:send,purchase,delete,publish,grant,pay |
| 実行 | Edit | 不明 | exec |
| 取り返しのつかない操作 | Edit | 不明 | acts:send,purchase,delete,publish,grant,pay |
| 実行 | WebFetch | 不明 | exec |
| 取り返しのつかない操作 | WebFetch | 不明 | acts:send,purchase,delete,publish,grant,pay |
| 持ち出し | Read>Read | 不明 | reads_secret → net_out |
| 持ち出し | Read>Bash | 不明 | reads_secret → net_out |
| 持ち出し | Read>Edit | 不明 | reads_secret → net_out |
| 持ち出し | Read>WebFetch | 不明 | reads_secret → net_out |
| 持ち出し | Bash>Read | 不明 | reads_secret → net_out |
| 持ち出し | Bash>Bash | 不明 | reads_secret → net_out |
| 持ち出し | Bash>Edit | 不明 | reads_secret → net_out |
| 持ち出し | Bash>WebFetch | 不明 | reads_secret → net_out |
| 持ち出し | Edit>Read | 不明 | reads_secret → net_out |
| 持ち出し | Edit>Bash | 不明 | reads_secret → net_out |
| 持ち出し | Edit>Edit | 不明 | reads_secret → net_out |
| 持ち出し | Edit>WebFetch | 不明 | reads_secret → net_out |
| 持ち出し | WebFetch>Read | 不明 | reads_secret → net_out |
| 持ち出し | WebFetch>Bash | 不明 | reads_secret → net_out |
| 持ち出し | WebFetch>Edit | 不明 | reads_secret → net_out |
| 持ち出し | WebFetch>WebFetch | 不明 | reads_secret → net_out |

## 宣言と観察の食い違い

| 道具 | 項目 | 宣言 | 観察 | 確度 | 向き | 根拠 |
|---|---|---|---|---|---|---|
| Bash | exec | false | true | 論 | **申告より危ない** | Claude Code の道具 bash の定義上の働き |
| WebFetch | reads_untrusted | false | true | 論 | **申告より危ない** | Claude Code の道具 webfetch の定義上の働き |
| WebFetch | net_out | false | true | 論 | **申告より危ない** | Claude Code の道具 webfetch の定義上の働き |
| WebFetch | args_leave | false | true | 論 | **申告より危ない** | Claude Code の道具 webfetch の定義上の働き |

## 不明として危ない側に倒した項目

観察の札を書けば、関所が減る可能性があります。
- Read.reads_untrusted
- Read.args_leave
- Read.exec
- Read.net_out
- Read.reads_secret
- Read.acts
- Bash.reads_untrusted
- Bash.args_leave
- Bash.net_out
- Bash.reads_secret
- Bash.acts
- Edit.reads_untrusted
- Edit.args_leave
- Edit.exec
- Edit.net_out
- Edit.reads_secret
- Edit.acts
- WebFetch.exec
- WebFetch.reads_secret
- WebFetch.acts

## 走らせなかった検査・限界

- 人の確認の素通し（ask にした道具を人が実際に止めるか）は測っていない
- 文脈の中の値の流れは追っていない（文脈は 1 つの汚れうる場所として丸めた）
- 札の正しさは確かめていない（札は入力。確度と根拠を見て判断すること）

_Skopost v1・計算 X 秒・外部通信なし・入力は変更していません_
