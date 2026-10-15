# 例（すべて合成。実在の製品の設定ではありません）

| ファイル | 何を模したか | 見どころ |
|---|---|---|
| `notes-agent.json` | ノートアプリのエージェントの道具 8 個 | 「設定を読む」＋「ウェブ取り込み（URL が外へ出る）」の持ち出しの道。「追加ぶんを入れる」＝実行される置き場への書き込み。音声合成の `不明` が関所を増やす |
| `browser-agent.json` | AI のブラウザ操作 7 個 | 「クリック」は画面次第で送信にも購入にもなる。「ページを読む」＋「ページを開く（URL に文字列を載せられる）」の道。クリップボードは外部の置き場 |

試す：

```sh
python3 skopost.py check examples/notes-agent.json --explain
python3 skopost.py check examples/browser-agent.json --format json
```
