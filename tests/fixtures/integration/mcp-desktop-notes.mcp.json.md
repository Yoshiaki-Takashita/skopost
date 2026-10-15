# Skopost 報告：mcp-desktop-notes.mcp.json

**結論**：危ない道 24 本。関所 4 か所で全部断てます。

- 道具 4（確認なし 4）／宣言だけの地図では道 0 本（見落とし 24 本）／宣言と観察の食い違い 7／不明として危ない側に倒した項目 15

## 関所（ここに人の確認を置く）

- **notes.search_notes**（Search the user's notes by keyword.）→ `mode: ask`
- **notes.delete_note**（Delete a note permanently.）→ `mode: ask`
- **web.fetch_url**（Fetch a web page and return its text.）→ `mode: ask`
- **mailer.send_email**（Send an email to a recipient.）→ `mode: ask`

## 宣言だけで決めたらどうなるか

宣言だけの関所 （なし） では、観察の層で **24 本**の道が残ります：`notes.search_notes`、`notes.search_notes`、`notes.delete_note`、`notes.delete_note`、`web.fetch_url`、`web.fetch_url`、`mailer.send_email`、`mailer.send_email`、`notes.search_notes>notes.search_notes`、`notes.search_notes>notes.delete_note`、`notes.search_notes>web.fetch_url`、`notes.search_notes>mailer.send_email`、`notes.delete_note>notes.search_notes`、`notes.delete_note>notes.delete_note`、`notes.delete_note>web.fetch_url`、`notes.delete_note>mailer.send_email`、`web.fetch_url>notes.search_notes`、`web.fetch_url>notes.delete_note`、`web.fetch_url>web.fetch_url`、`web.fetch_url>mailer.send_email`、`mailer.send_email>notes.search_notes`、`mailer.send_email>notes.delete_note`、`mailer.send_email>web.fetch_url`、`mailer.send_email>mailer.send_email`

これが「一覧で管理すると安全の錯覚になる」の具体です。

## 危ない道

| 種類 | 道 | 確度 | 経路 |
|---|---|---|---|
| 実行 | notes.search_notes | 不明 | exec |
| 取り返しのつかない操作 | notes.search_notes | 不明 | acts:send,purchase,delete,publish,grant,pay |
| 実行 | notes.delete_note | 不明 | exec |
| 取り返しのつかない操作 | notes.delete_note | 不明 | acts:send,purchase,delete,publish,grant,pay |
| 実行 | web.fetch_url | 不明 | exec |
| 取り返しのつかない操作 | web.fetch_url | 不明 | acts:send,purchase,delete,publish,grant,pay |
| 実行 | mailer.send_email | 不明 | exec |
| 取り返しのつかない操作 | mailer.send_email | 不明 | acts:send,purchase,delete,publish,grant,pay |
| 持ち出し | notes.search_notes>notes.search_notes | 不明 | reads_secret → net_out |
| 持ち出し | notes.search_notes>notes.delete_note | 不明 | reads_secret → net_out |
| 持ち出し | notes.search_notes>web.fetch_url | 不明 | reads_secret → net_out |
| 持ち出し | notes.search_notes>mailer.send_email | 不明 | reads_secret → net_out |
| 持ち出し | notes.delete_note>notes.search_notes | 不明 | reads_secret → net_out |
| 持ち出し | notes.delete_note>notes.delete_note | 不明 | reads_secret → net_out |
| 持ち出し | notes.delete_note>web.fetch_url | 不明 | reads_secret → net_out |
| 持ち出し | notes.delete_note>mailer.send_email | 不明 | reads_secret → net_out |
| 持ち出し | web.fetch_url>notes.search_notes | 不明 | reads_secret → net_out |
| 持ち出し | web.fetch_url>notes.delete_note | 不明 | reads_secret → net_out |
| 持ち出し | web.fetch_url>web.fetch_url | 不明 | reads_secret → net_out |
| 持ち出し | web.fetch_url>mailer.send_email | 不明 | reads_secret → net_out |
| 持ち出し | mailer.send_email>notes.search_notes | 不明 | reads_secret → net_out |
| 持ち出し | mailer.send_email>notes.delete_note | 不明 | reads_secret → net_out |
| 持ち出し | mailer.send_email>web.fetch_url | 不明 | reads_secret → net_out |
| 持ち出し | mailer.send_email>mailer.send_email | 不明 | reads_secret → net_out |

## 宣言と観察の食い違い

| 道具 | 項目 | 宣言 | 観察 | 確度 | 向き | 根拠 |
|---|---|---|---|---|---|---|
| notes.search_notes | reads_untrusted | false | true | 推 | **申告より危ない** | 名前 'search_notes' の語；説明文の語（資料として読んだだけ） |
| notes.search_notes | net_out | false | true | 推 | **申告より危ない** | 名前 'search_notes' の語；説明文の語（資料として読んだだけ） |
| notes.search_notes | args_leave | false | true | 推 | **申告より危ない** | 名前 'search_notes' の語；説明文の語（資料として読んだだけ） |
| web.fetch_url | reads_untrusted | false | true | 推 | **申告より危ない** | openWorldHint=true；入力スキーマの引数名；名前 'fetch_url' の語；説明文の語（資料として… |
| web.fetch_url | args_leave | false | true | 推 | **申告より危ない** | 入力スキーマの引数名；名前 'fetch_url' の語；説明文の語（資料として読んだだけ） |
| mailer.send_email | reads_untrusted | false | true | 推 | **申告より危ない** | openWorldHint=true |
| mailer.send_email | args_leave | false | true | 推 | **申告より危ない** | 入力スキーマの引数名；名前 'send_email' の語；説明文の語（資料として読んだだけ） |

## 不明として危ない側に倒した項目

観察の札を書けば、関所が減る可能性があります。
- notes.search_notes.exec
- notes.search_notes.reads_secret
- notes.search_notes.acts
- notes.delete_note.reads_untrusted
- notes.delete_note.args_leave
- notes.delete_note.exec
- notes.delete_note.net_out
- notes.delete_note.reads_secret
- notes.delete_note.acts
- web.fetch_url.exec
- web.fetch_url.reads_secret
- web.fetch_url.acts
- mailer.send_email.exec
- mailer.send_email.reads_secret
- mailer.send_email.acts

## 走らせなかった検査・限界

- 人の確認の素通し（ask にした道具を人が実際に止めるか）は測っていない
- 文脈の中の値の流れは追っていない（文脈は 1 つの汚れうる場所として丸めた）
- 札の正しさは確かめていない（札は入力。確度と根拠を見て判断すること）

_Skopost v1・計算 X 秒・外部通信なし・入力は変更していません_
