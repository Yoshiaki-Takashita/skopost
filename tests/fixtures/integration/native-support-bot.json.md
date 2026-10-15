# Skopost 報告：例：問い合わせ対応ボット（合成。実物の設定ではない）

**結論**：危ない道 14 本。関所 3 か所で全部断てます。

- 道具 4（確認なし 3）／宣言だけの地図では道 1 本（見落とし 13 本）／宣言と観察の食い違い 0／不明として危ない側に倒した項目 15

## 関所（ここに人の確認を置く）

- **ticket_read**（問い合わせを読む）→ `mode: ask`
- **crm_lookup**（顧客台帳を引く）→ `mode: ask`
- **reply_draft**（返信を下書きに置く）→ `mode: ask`

## 宣言だけで決めたらどうなるか

宣言だけの関所 ['crm_lookup'] では、観察の層で **7 本**の道が残ります：`ticket_read`、`ticket_read`、`reply_draft`、`ticket_read>ticket_read`、`ticket_read>reply_draft`、`reply_draft>ticket_read`、`reply_draft>reply_draft`

これが「一覧で管理すると安全の錯覚になる」の具体です。

## 危ない道

| 種類 | 道 | 確度 | 経路 |
|---|---|---|---|
| 実行 | ticket_read | 不明 | exec |
| 取り返しのつかない操作 | ticket_read | 不明 | acts:send,purchase,delete,publish,grant,pay |
| 実行 | crm_lookup | 不明 | exec |
| 取り返しのつかない操作 | crm_lookup | 不明 | acts:send,purchase,delete,publish,grant,pay |
| 実行 | reply_draft | 不明 | exec |
| 持ち出し | ticket_read>ticket_read | 不明 | reads_secret → net_out |
| 持ち出し | ticket_read>crm_lookup | 不明 | reads_secret → net_out |
| 持ち出し | ticket_read>reply_draft | 不明 | reads_secret → net_out |
| 持ち出し | crm_lookup>ticket_read | 不明 | reads_secret → net_out |
| 持ち出し | crm_lookup>crm_lookup | 不明 | reads_secret → net_out |
| 持ち出し | crm_lookup>reply_draft | 不明 | reads_secret → net_out |
| 持ち出し | reply_draft>ticket_read | 不明 | reads_secret → net_out |
| 持ち出し | reply_draft>crm_lookup | 不明 | reads_secret → net_out |
| 持ち出し | reply_draft>reply_draft | 不明 | reads_secret → net_out |

## 宣言と観察の食い違い

なし。

## 不明として危ない側に倒した項目

観察の札を書けば、関所が減る可能性があります。
- ticket_read.args_leave
- ticket_read.exec
- ticket_read.net_out
- ticket_read.reads_secret
- ticket_read.acts
- crm_lookup.reads_untrusted
- crm_lookup.exec
- crm_lookup.net_out
- crm_lookup.reads_secret
- crm_lookup.acts
- reply_draft.reads_untrusted
- reply_draft.args_leave
- reply_draft.exec
- reply_draft.net_out
- reply_draft.reads_secret

## 走らせなかった検査・限界

- 人の確認の素通し（ask にした道具を人が実際に止めるか）は測っていない
- 文脈の中の値の流れは追っていない（文脈は 1 つの汚れうる場所として丸めた）
- 札の正しさは確かめていない（札は入力。確度と根拠を見て判断すること）

_Skopost v1・計算 X 秒・外部通信なし・入力は変更していません_
