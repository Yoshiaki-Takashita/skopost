# Skopost 報告：例：ノート・エージェントの道具（合成。実物の設定ではない）

**結論**：危ない道 4 本。関所 2 か所で全部断てます。

- 道具 8（確認なし 7）／宣言だけの地図では道 2 本（見落とし 2 本）／宣言と観察の食い違い 3／不明として危ない側に倒した項目 2

## 関所（ここに人の確認を置く）

- **settings_read**（設定を読む）→ `mode: ask`
- **addon_install**（追加ぶんを入れる）→ `mode: ask`

## 宣言だけで決めたらどうなるか

宣言だけの関所 ['addon_install', 'share_export'] では、観察の層で **2 本**の道が残ります：`settings_read>web_import`、`settings_read>voice_synth`

これが「一覧で管理すると安全の錯覚になる」の具体です。

## 危ない道

| 種類 | 道 | 確度 | 経路 |
|---|---|---|---|
| 実行 | addon_install | 論 | writes_stores→addons（実行される置き場） |
| 持ち出し | settings_read>web_import | 論 | reads_stores→settings（秘密のある置き場） → args_leave |
| 持ち出し | settings_read>share_export | 論 | reads_stores→settings（秘密のある置き場） → writes_stores→share（外部の置き場） |
| 持ち出し | settings_read>voice_synth | 不明 | reads_stores→settings（秘密のある置き場） → net_out |

## 宣言と観察の食い違い

| 道具 | 項目 | 宣言 | 観察 | 確度 | 向き | 根拠 |
|---|---|---|---|---|---|---|
| note_read | reads_untrusted | false | true | 確 | **申告より危ない** | 合成：取り込んだウェブの文が入る |
| web_import | args_leave | false | true | 確 | **申告より危ない** | 合成：URL がそのまま外へ出る（R-2 の型） |
| web_import | writes_stores | [] | ["notes"] | 確 | **申告より危ない** | 合成 |

## 不明として危ない側に倒した項目

観察の札を書けば、関所が減る可能性があります。
- voice_synth.args_leave
- voice_synth.net_out

## 走らせなかった検査・限界

- 人の確認の素通し（ask にした道具を人が実際に止めるか）は測っていない
- 文脈の中の値の流れは追っていない（文脈は 1 つの汚れうる場所として丸めた）
- 札の正しさは確かめていない（札は入力。確度と根拠を見て判断すること）

_Skopost v1・計算 X 秒・外部通信なし・入力は変更していません_
