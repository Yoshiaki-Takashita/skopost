# Skopost 報告：例：AI のブラウザ操作（合成。実物の製品ではない）

**結論**：危ない道 10 本。関所 4 か所で全部断てます。

- 道具 7（確認なし 7）／宣言だけの地図では道 0 本（見落とし 10 本）／宣言と観察の食い違い 10／不明として危ない側に倒した項目 1

## 関所（ここに人の確認を置く）

- **read_page**（ページの文字を読む）→ `mode: ask`
  - 断つ道：exfil: read_page>navigate
  - 断つ道：exfil: read_page>type_text
  - 断つ道：exfil: read_page>copy_to_clipboard
  - 断つ道：exfil: read_page>download
- **click**（クリック）→ `mode: ask`
  - 断つ道：act: click
- **download**（ファイルをダウンロード）→ `mode: ask`
  - 断つ道：exec: download
  - 断つ道：exfil: read_page>download
  - 断つ道：exfil: screenshot>download
- **screenshot**（画面を撮る）→ `mode: ask`
  - 断つ道：exfil: screenshot>navigate
  - 断つ道：exfil: screenshot>type_text
  - 断つ道：exfil: screenshot>copy_to_clipboard
  - 断つ道：exfil: screenshot>download

## 宣言だけで決めたらどうなるか

宣言だけの関所 （なし） では、観察の層で **10 本**の道が残ります：`click`、`download`、`read_page>navigate`、`read_page>type_text`、`read_page>copy_to_clipboard`、`read_page>download`、`screenshot>navigate`、`screenshot>type_text`、`screenshot>copy_to_clipboard`、`screenshot>download`

これが「一覧で管理すると安全の錯覚になる」の具体です。

## 危ない道

| 種類 | 道 | 確度 | 経路 |
|---|---|---|---|
| 取り返しのつかない操作 | click | 論 | acts:delete,publish,purchase,send |
| 実行 | download | 不明 | exec |
| 持ち出し | read_page>navigate | 論 | reads_secret → args_leave |
| 持ち出し | read_page>type_text | 論 | reads_secret → net_out |
| 持ち出し | read_page>copy_to_clipboard | 論 | reads_secret → writes_stores→clipboard（外部の置き場） |
| 持ち出し | read_page>download | 論 | reads_secret → args_leave |
| 持ち出し | screenshot>navigate | 論 | reads_secret → args_leave |
| 持ち出し | screenshot>type_text | 論 | reads_secret → net_out |
| 持ち出し | screenshot>copy_to_clipboard | 論 | reads_secret → writes_stores→clipboard（外部の置き場） |
| 持ち出し | screenshot>download | 論 | reads_secret → args_leave |

## 宣言と観察の食い違い

| 道具 | 項目 | 宣言 | 観察 | 確度 | 向き | 根拠 |
|---|---|---|---|---|---|---|
| navigate | args_leave | false | true | 確 | **申告より危ない** | 合成：URL（と中の文字列）が宛先へ届く |
| read_page | reads_secret | false | true | 論 | **申告より危ない** | 合成：ログイン済みのページには個人情報が表示される |
| click | reads_untrusted | false | true | 確 | **申告より危ない** | 合成 |
| click | acts | [] | ["delete", "publish", "purchase", "send"] | 論 | **申告より危ない** | 合成：ボタンが何をするかは画面次第。送信・購入・削除・投稿のどれにもなりうる |
| type_text | net_out | false | true | 論 | **申告より危ない** | 合成：入力欄に書いた文は送信ボタンで外へ出る |
| copy_to_clipboard | writes_stores | [] | ["clipboard"] | 確 | **申告より危ない** | 合成 |
| download | reads_untrusted | false | true | 確 | **申告より危ない** | 合成 |
| download | args_leave | false | true | 確 | **申告より危ない** | 合成：URL が宛先へ届く |
| screenshot | reads_untrusted | false | true | 確 | **申告より危ない** | 合成 |
| screenshot | reads_secret | false | true | 論 | **申告より危ない** | 合成：画面に出ている個人情報が画像に入る |

## 不明として危ない側に倒した項目

観察の札を書けば、関所が減る可能性があります。
- download.exec

## 走らせなかった検査・限界

- 人の確認の素通し（ask にした道具を人が実際に止めるか）は測っていない
- 文脈の中の値の流れは追っていない（文脈は 1 つの汚れうる場所として丸めた）
- 札の正しさは確かめていない（札は入力。確度と根拠を見て判断すること）

_Skopost v1・計算 X 秒・外部通信なし・入力は変更していません_
