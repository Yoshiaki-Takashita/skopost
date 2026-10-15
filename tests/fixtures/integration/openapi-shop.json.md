# Skopost 報告：Example shop API (synthetic)

**結論**：危ない道 15 本。関所 3 か所で全部断てます。

- 道具 3（確認なし 3）／宣言だけの地図では道 0 本（見落とし 15 本）／宣言と観察の食い違い 9／不明として危ない側に倒した項目 9

## 関所（ここに人の確認を置く）

- **searchProducts**（Search products）→ `mode: ask`
- **placeOrder**（Place an order and charge the saved card）→ `mode: ask`
- **cancelOrder**（Cancel an order）→ `mode: ask`

## 宣言だけで決めたらどうなるか

宣言だけの関所 （なし） では、観察の層で **15 本**の道が残ります：`searchProducts`、`searchProducts`、`placeOrder`、`placeOrder`、`cancelOrder`、`cancelOrder`、`searchProducts>searchProducts`、`searchProducts>placeOrder`、`searchProducts>cancelOrder`、`placeOrder>searchProducts`、`placeOrder>placeOrder`、`placeOrder>cancelOrder`、`cancelOrder>searchProducts`、`cancelOrder>placeOrder`、`cancelOrder>cancelOrder`

これが「一覧で管理すると安全の錯覚になる」の具体です。

## 危ない道

| 種類 | 道 | 確度 | 経路 |
|---|---|---|---|
| 実行 | searchProducts | 不明 | exec |
| 取り返しのつかない操作 | searchProducts | 不明 | acts:send,purchase,delete,publish,grant,pay |
| 実行 | placeOrder | 不明 | exec |
| 取り返しのつかない操作 | placeOrder | 不明 | acts:send,purchase,delete,publish,grant,pay |
| 実行 | cancelOrder | 不明 | exec |
| 取り返しのつかない操作 | cancelOrder | 不明 | acts:send,purchase,delete,publish,grant,pay |
| 持ち出し | searchProducts>searchProducts | 不明 | reads_secret → net_out |
| 持ち出し | searchProducts>placeOrder | 不明 | reads_secret → net_out |
| 持ち出し | searchProducts>cancelOrder | 不明 | reads_secret → net_out |
| 持ち出し | placeOrder>searchProducts | 不明 | reads_secret → net_out |
| 持ち出し | placeOrder>placeOrder | 不明 | reads_secret → net_out |
| 持ち出し | placeOrder>cancelOrder | 不明 | reads_secret → net_out |
| 持ち出し | cancelOrder>searchProducts | 不明 | reads_secret → net_out |
| 持ち出し | cancelOrder>placeOrder | 不明 | reads_secret → net_out |
| 持ち出し | cancelOrder>cancelOrder | 不明 | reads_secret → net_out |

## 宣言と観察の食い違い

| 道具 | 項目 | 宣言 | 観察 | 確度 | 向き | 根拠 |
|---|---|---|---|---|---|---|
| searchProducts | reads_untrusted | false | true | 推 | **申告より危ない** | HTTP GET の応答は外部の文章；名前 'searchProducts' の語；説明文の語（資料として読んだだけ）… |
| searchProducts | net_out | false | true | 推 | **申告より危ない** | servers が外部；名前 'searchProducts' の語；説明文の語（資料として読んだだけ）；説明文の語（… |
| searchProducts | args_leave | false | true | 推 | **申告より危ない** | HTTP GET の引数は相手のサーバーに届く；名前 'searchProducts' の語；説明文の語（資料として読… |
| placeOrder | reads_untrusted | false | true | 推 | **申告より危ない** | HTTP POST の応答は外部の文章 |
| placeOrder | net_out | false | true | 論 | **申告より危ない** | servers が外部 |
| placeOrder | args_leave | false | true | 推 | **申告より危ない** | HTTP POST の引数は相手のサーバーに届く；名前 'placeOrder' の語；説明文の語（資料として読んだだ… |
| cancelOrder | reads_untrusted | false | true | 推 | **申告より危ない** | HTTP DELETE の応答は外部の文章 |
| cancelOrder | net_out | false | true | 論 | **申告より危ない** | servers が外部 |
| cancelOrder | args_leave | false | true | 推 | **申告より危ない** | HTTP DELETE の引数は相手のサーバーに届く；名前 'cancelOrder' の語；説明文の語（資料として読… |

## 不明として危ない側に倒した項目

観察の札を書けば、関所が減る可能性があります。
- searchProducts.exec
- searchProducts.reads_secret
- searchProducts.acts
- placeOrder.exec
- placeOrder.reads_secret
- placeOrder.acts
- cancelOrder.exec
- cancelOrder.reads_secret
- cancelOrder.acts

## 走らせなかった検査・限界

- 人の確認の素通し（ask にした道具を人が実際に止めるか）は測っていない
- 文脈の中の値の流れは追っていない（文脈は 1 つの汚れうる場所として丸めた）
- 札の正しさは確かめていない（札は入力。確度と根拠を見て判断すること）

_Skopost v1・計算 X 秒・外部通信なし・入力は変更していません_
