# 公開の手順書（PUBLISHING）

この文書は、非公開のリポジトリ `Yoshiaki-Takashita/skopost` を公開するときの手順です。
**公開そのもの（可視性の変更・PyPI へのアップロード・タグやリリースの公開）は、作者が行います。** 履歴の 1 コミット化（非公開のまま）以外は、行っていません。

---

## 0. 決定済み（2026-10-15）

作者が「全て任せる」とし、推奨案を採った。反映は済んでいる。

| # | 決めること | 決定 | 反映 |
|---|---|---|---|
| 1 | ライセンス | **Apache-2.0** | `LICENSE`（正式な全文）・`NOTICE`・`pyproject.toml`・README。`LICENSE.draft` は削除 |
| 2 | 著作者の表記 | **Yoshiaki Takashita** | `NOTICE`・`pyproject.toml` の `authors`・README のライセンス節 |
| 3 | PyPI の名前 | **`skopost`** | `pyproject.toml` の `name`。PyPI へのアップロードは公開後に別途（未実施） |
| 4 | 版の番号 | 配布の版は **0.1.0** のまま | 内部の 1.1.0.dev0・SARIF の版は「スキーマの版」で別。README・ARCHITECTURE §2.3・CHANGELOG に説明。内部の試験は変えていない |
| 5 | 履歴 | **1 つのコミットにまとめた** | 第 2 節。退避は手元の外（リポジトリの外の bundle）にだけ置き、リポジトリには残していない |
| 6 | 連絡の方法 | GitHub の **Private vulnerability reporting** | SECURITY.md・CODE_OF_CONDUCT.md |
| 7 | 公開の時期 | 作者が釦を押すとき | **商標の確認（第 5 節。J-PlatPat など）をしてからを推奨** |

---

## 1. 公開の手順（ユーザーの作業）

公開（可視性の変更）・PyPI/npm へのアップロード・タグやリリースの公開は、作者が行う。

1. **（推奨）先に商標を確認する**（第 5 節）。
2. **リポジトリを公開にする**：GitHub のリポジトリ画面 → **Settings** → **General** → いちばん下の **Danger Zone** → **Change visibility** → **Make public** → 確認の文字を入力して決定。
3. **非公開の脆弱性報告を有効にする**：**Settings** → **Code security**（表示によっては「Code security and analysis」/「Advanced Security」）→ **Private vulnerability reporting** → **Enable**。
   これで SECURITY.md の「Security タブ → Report a vulnerability」が使えるようになります（公開リポジトリでのみ使える機能）。
4. **説明文とトピックを設定する**：リポジトリのトップ画面の右上「About」の歯車 →
   - Description（説明文）の案：`Static analyzer for AI agent tool setups: dangerous tool combinations and the smallest set of human checkpoints (research preview)`
   - Topics の案：`ai-agents` `mcp` `security` `static-analysis` `least-privilege` `python`
5. **v0.1.0-preview のリリースを作る**：トップ画面右の **Releases** → **Draft a new release** → **Choose a tag** に `v0.1.0-preview` と入力して作成 → タイトル `Skopost 0.1.0-preview` → 本文に `docs/RELEASE-NOTES-0.1.0.md` を貼る → **Set as a pre-release** に印 → **Publish release**。
6. **（任意）PyPI に出す**：`python -m build` で `dist/` を作り、`twine upload dist/*`（PyPI のアカウントと API トークンが必要。トークンはリポジトリに入れない）。先に TestPyPI で試すのが安全。

---

## 2. 履歴の整理（1 つの初期コミットにまとめる）

**実施済み（2026-10-15）**：作者の決定（「全て任せる」）の範囲で、非公開のままの `main` を 1 コミットに置き換えた（force push）。以下は、そのとき使った手順の記録。退避は `git bundle create <リポジトリの外>/skopost-before-squash.bundle --all`（枝としてリポジトリに残さない）。

ねらい：コミットメッセージのセッション URL・内部の作業メモ、過去の版にだけ残る内部の名前を、公開される履歴から外す。ファイルの中身（ツリー）は今の `main` と完全に同じにする。

```sh
# 0) 最新にそろえ、作業中の変更がないことを確かめる
git checkout main
git pull --rebase origin main
git status                      # 「nothing to commit」であること

# 1) 旧 main を退避（消さない。いつでも戻せるように）
git branch archive/pre-public-main main
git push origin archive/pre-public-main      # ← 退避を GitHub にも置く場合。ただし公開後は誰でも読めるので、
                                             #    履歴を見せたくないなら push せず手元だけ（または別の非公開リポジトリ）に置く

# 2) 履歴のない新しい枝を作り、今のファイルをそのまま 1 コミットにする
git checkout --orphan public-main
git commit -m "Skopost 0.1.0-preview (initial public commit)"
#   作者名とメールは公開される。GitHub の noreply アドレス（Settings → Emails）を使うと個人のメールが出ない：
#   git -c user.name="<表示名>" -c user.email="<ID+ユーザー名>@users.noreply.github.com" commit -m "..."

# 3) ツリーが旧 main と同一であることを確かめる（何も表示されなければ同一）
git diff main public-main
git rev-parse main^{tree} public-main^{tree}  # 2 行が同じ値

# 4) 新しい枝を main にする（手元）
git branch -M public-main main               # 手元の main が新しい 1 コミットに置き換わる

# 5) ★作者の承認の後にだけ★ GitHub の main を置き換える
git push --force-with-lease origin main
```

注意：
- 公開「前」に行う。公開後に書き換えても、すでに複製した人の手元には古い履歴が残る。
- **GitHub は書き換え前のコミットを、SHA を知る人にはしばらく見せることがある**（内部に保持されるため）。完全に消したい場合は、新しいリポジトリを作ってそこへ 1 コミットを push し、古いリポジトリは非公開のまま残す（または削除する）方が確実。
- 退避ブランチ `archive/pre-public-main` を公開リポジトリに push すると、整理の意味がなくなる。
- 2026-10-15 に、手元の別ディレクトリ（複製）で手順 1〜3 を試し、`git diff` が空・ツリーの値が一致することを確認した（push はしていない）。

少数の意味のあるコミットに分けたい場合（任意）：手順 2 の代わりに、`git checkout --orphan public-main` → `git rm -r --cached .` → 「本体（skopost/・skopost.py）」「試験（tests/・corpus/）」「文書」などの順に `git add` と `git commit` を繰り返す。最後に手順 3 で同一を確かめる。

---

## 3. 公開前の点検の結果（2026-10-15）

走査した文字列：鍵らしきもの（`sk-`・`AKIA`・`-----BEGIN`・`ghp_`・`xox`・パスワードらしき値）、メールアドレス・本名・電話、内部の参照（製品名・作業記録の場所・個人のアカウント名・セッション URL）、絶対パス（`/home/user`）。

| 種類 | 現在のファイル | 履歴だけ | 対応 |
|---|---|---|---|
| 鍵らしき文字列 | 試験用の偽の値だけ（`tests/test_ingest_adapters.py`・`tests/test_contract_ingest.py`、検出の正規表現 `skopost/ingest/base.py`）。`"sk-" + "Z"*40` のように組み立てる形で、本物の鍵ではない | 同じ偽の値 | 対応不要 |
| メールアドレス | なし | コミットの作者・メッセージの `noreply@anthropic.com`（共同作者の表記） | 履歴の整理で消えた |
| 本名・住所・電話 | 著作者の表記（`NOTICE`・`pyproject.toml`・`LICENSE` の著作権表示）だけ | なし | 決定済み（第 0 節の 2） |
| 内部の製品名 | 例のファイル名・名前にあった → `notes-agent` に改名して解消 | 過去の版に残る | 履歴の整理で消える |
| 作業記録の場所への言及 | なし | `docs/ARCHITECTURE.md` の過去の版 | 履歴の整理で消える |
| セッション URL | なし | 全コミットのメッセージ | 履歴の整理で消える |
| 絶対パス | なし | なし | — |
| 開発の進め方のメモ（「担当 A〜F」「段 1〜3」「原則 N」・旧置き場 `projects/skopost/`） | `docs/ARCHITECTURE.md`・`docs/GRAPH.md`・`corpus/*.py` などに残る（秘密ではない） | 同じ | 未修正。公開して困るなら作者の判断で書き換える |

---

## 4. パッケージ化の確認（2026-10-15）

- `pyproject.toml`（setuptools・依存ゼロ・`requires-python = ">=3.10"`）。Python 3.9 は `dataclass(slots=True)` を使っているため動かない（試験で確認）。3.10・3.11・3.12・3.13 で試験が通る。
- 新しい venv で `pip install .` と `python -m build`（sdist と wheel）が通り、`skopost --help` と `skopost check examples/notes-agent.json`（終了コード 2＝危ない道あり）が動いた。アップロードはしていない。

## 5. 名前と商標（確認点の整理。法的助言ではない）

| 調べたところ | 結果 |
|---|---|
| PyPI `skopost`・`skopost-agent`・`skopost-map`・`skopost-cli`・`skopost-audit` | 2026-10-15 時点で未登録（`pypi.org/pypi/<名前>/json` が 404） |
| PyPI `skopos`・`skopos-audit` | 登録済み（無関係の別の計画） |
| npm `skopost` | 未登録（404） |
| J-PlatPat（日本）・USPTO（米国）・EUIPO / TMview（欧州） | **未確認・要作者の確認**。検索ページは画面操作が必要な作りで、この環境からは検索できなかった |

**作者の確認結果（2026-10-16・作者の申告）**：同一・類似の登録の被りは 0 件。確認した検索先と検索語の控えは作者の手元（この記録は申告であり、こちらでは検索していない）。

作者が確かめるとよい点：「Skopost」「Skopos」「スコポス」「スコポスト」の同一・類似の登録の有無、区分は第 9 類（ソフトウェア）と第 42 類（ソフトウェアの提供・設計）。気になる登録があれば専門家（弁理士）へ。
