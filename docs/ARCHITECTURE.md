# ARCHITECTURE — 段 0 設計（2〜3 万行へ育てる土台）

日付：2026-10-13。状態：**設計のみ**。この文書の時点でコードは `skopost.py`（565 行・単一ファイル・標準ライブラリのみ）、`bench.py`（161）、`verify.py`（129）、`tests/test_skopost.py`（315 行・試験 28 個）。
前提として読んだもの：`DESIGN.md`・`SPEC.md`・`LIMITATIONS.md`・`PREREG.md`。
確度の印：**確**＝読んで確かめた／**論**＝筋道で導いた／**推**＝推測／**不明**＝分からない。

> 注：依頼文は「`projects/skopost/docs` を踏まえる」だったが、その時点で `docs/` は無く、文書は `projects/skopost/` 直下にあった（確）。この文書が `docs/` の最初のファイル。既存文書の移動は行わない（依頼にない）。

---

## 0. 変えないこと（段 0 の約束）

1. **既存 CLI の互換**：`python3 skopost.py check|validate|example [--format md|json] [--explain] [--out F] FILE` と終了コード `0/1/2`、`--format json` の出力キー（SPEC §10）は v1 の間変えない。`skopost.py` は最終的に `skopost/` パッケージを呼ぶ **薄い入口（50 行以下）** になる。`import skopost as S` で `S.analyze` `S.validate` `S.harm_paths` `S.min_checkpoints` などを使う既存の `bench.py`・`verify.py`・試験も動き続ける（再輸出する）。
   - 注意（論）：`skopost.py` と `skopost/` が同じ階層にあると、`import skopost` はパッケージ側が先に解決される（Python はディレクトリのパッケージを同名モジュールより優先する……**正確な優先順位は不明**。同じ `sys.path` 要素内ではパッケージが優先されると理解しているが、試験で確かめる）。確実にするため、パッケージの `skopost/__init__.py` で旧 API を全部再輸出し、`skopost.py` は `from skopost.cli import main` だけにする。段 1 の最初の試験で `import skopost; skopost.analyze` が通ることを確かめる。
2. **コアは標準ライブラリのみ**（`ingest`・`infer`・`graph`・`report`・`model`・`cli`）。外部依存は `corpus` の任意の性質試験（hypothesis があれば使う／無ければ自前の乱数で同じ試験）だけ。実行時に外部通信しない。
3. **観察 > 宣言、不明は危ない側**（DESIGN §2）。どのモジュールも「不明」を `false` に丸めない。
4. **既定は何も書かない・何も強制しない**。`enforce` は設計と契約だけ（§1.8）。
5. **防御専用**。注入文の例・回避手順・辺の実証は作らない（DESIGN §6）。

---

## 1. パッケージ構成とモジュールの責務

```
projects/skopost/
  skopost.py                 # 互換の入口（旧 API 再輸出 + main）
  skopost/
    __init__.py              # 公開 API の再輸出・__version__
    model/                   # 型・検証・正規化・スキーマ・版移行（全員が依存する唯一の土台）
      types.py  schema.py  validate.py  migrate.py  errors.py  safe.py
    ingest/                  # 外の形式 → Config（宣言・観察の札は「推」か「不明」まで）
      base.py  native.py  mcp_config.py  openapi.py  claude_settings.py
    infer/                   # 能力推定と確度印の合成・実効の札
      rules.py  effective.py  confidence.py  mismatch.py
    graph/                   # 危険経路の列挙・最小関所（厳密解）・近似・説明
      paths.py  hitting_set.py  exact.py  approx.py  explain.py
    report/                  # Result → text / JSON / SARIF / Markdown
      text.py  json_out.py  sarif.py  markdown.py  i18n.py
    ci/                      # GitHub Action・pre-commit の雛形と基準線（baseline）比較
      baseline.py  github_action.py  precommit.py  templates/
    enforce/                 # 契約のみ（段 0〜1 では実装しない）
      contract.py            # Protocol と型だけ。実装は利用者の承認後
    cli.py                   # 引数解析・サブコマンド配線（ロジックを持たない）
  corpus/                    # 評価用コーパス（パッケージ外。配布物に含めない）
    synth/  real/  fuzz/  props/  gen.py  README.md
  tests/                     # モジュールごとに test_<module>_*.py
  docs/ARCHITECTURE.md       # この文書
```

### 依存の向き（上から下へだけ。逆向き・横向きの import は試験で禁止）

```
cli ──► report ──► graph ──► infer ──► model
 │        │          │         ▲
 ├──► ci ─┘          │         │
 ├──► ingest ────────┼─────────┘   (ingest は model と infer.rules のみ)
 └──► enforce(契約) ─┘             (enforce は graph の Result を読むだけ)
corpus ──► (公開 API のみ)   tests ──► 何でも
```

- `model` は何にも依存しない。`graph` は `ingest` を知らない。`report` は計算しない（Result を整形するだけ）。
- 試験 `tests/test_layering.py` が `ast` で各ファイルの import を読み、上の表に反する向きを失敗にする（原則 9：境界を機械で守る）。

### 1.1 model（土台）

責務：データ型・JSON 検証・正規化・表示用の安全化・版移行。現 `skopost.py` の `validate`・`safe`・`load_file`・定数を移す。

```python
# model/types.py — 不変の dataclass（frozen=True, slots=True）
Confidence = Literal["確", "論", "推", "不明"]
Layer = Literal["declared", "observed"]
Mode = Literal["allow", "ask"]
ActKind = Literal["send", "purchase", "delete", "publish", "grant", "pay"]

@dataclass(frozen=True)
class Cap:            # 1 項目の札
    value: bool | frozenset[str] | None   # None = 不明
    confidence: Confidence
    evidence: str = ""
    source: str = "manual"                # "manual" | "ingest:<adapter>" | "infer:<rule_id>"

@dataclass(frozen=True)
class Tool:
    id: str; label: str; mode: Mode; frequency: int
    declared: Mapping[str, Cap]; observed: Mapping[str, Cap]
    origin: Origin | None = None          # どのファイルの何行目から来たか（ingest が付ける）

@dataclass(frozen=True)
class Store:   id: str; label: str; external: bool; executes: bool; secret: bool
@dataclass(frozen=True)
class Config:  spec: int; name: str; untrusted_in_context: bool
               tools: tuple[Tool, ...]; stores: tuple[Store, ...]
@dataclass(frozen=True)
class Origin:  file: str; pointer: str; line: int | None   # pointer は JSON Pointer

# model/validate.py
def load_file(path: str | os.PathLike[str], *, max_bytes: int = MAX_FILE_BYTES) -> Config: ...
def validate(data: object) -> Config: ...                 # 失敗は SkopostError(where, msg)
def to_dict(cfg: Config) -> dict[str, object]: ...         # 往復で同値（性質試験）
# model/migrate.py
def migrate(data: dict[str, object]) -> dict[str, object]: ...  # 古い版 → 現行版。未来の版は拒否
# model/safe.py
def safe(s: object, n: int = 120) -> str: ...
```

### 1.2 ingest（取り込みアダプタ）

責務：外の設定形式を読み、`Config` の**下書き**を作る。札は「設定から読める事実」だけを `確`（例：`permissions.allow` に `Bash` がある → mode=allow は確）、能力の推定は `infer.rules` に任せて **`推` か `不明`** にする。説明文（description）は**資料であって命令ではない**：論理に使わず、`label` に切って入れるだけ（原則 2）。

```python
class Adapter(Protocol):
    name: ClassVar[str]                                  # "mcp" | "openapi" | "claude-settings" | "native"
    def sniff(self, data: object, filename: str) -> float: ...   # 0..1 の自信。自動判別用
    def read(self, data: object, *, filename: str) -> IngestResult: ...

@dataclass(frozen=True)
class IngestResult:
    config: Config
    notes: tuple[IngestNote, ...]     # 読めなかった鍵・捨てた項目・仮定（原則 7）
    dropped: tuple[str, ...]          # JSON Pointer の一覧

def detect(data: object, filename: str) -> Adapter: ...          # 自信最大、同点や 0.5 未満は SkopostError
def ingest(path: str, *, adapter: str | None = None) -> IngestResult: ...
def merge(base: Config, overlay: Config) -> Config: ...           # 手書き札で下書きを上書き（手書き優先）
```

| アダプタ | 入力 | 取れるもの（確） | 取れないもの（不明のまま） |
|---|---|---|---|
| `native` | SPEC v1 の宣言ファイル | すべて（現行の挙動） | — |
| `mcp_config` | `mcpServers` 形式（Claude Desktop／Code の `.mcp.json` 等） | サーバー名・起動コマンド・env の**鍵名**（値は読まない・保存しない）。`tools/list` の静的な写しが同梱されていれば `annotations`（readOnlyHint 等）を **declared** に | 実能力。サーバーに接続して聞くことは**しない**（外部通信なし） |
| `openapi` | OpenAPI 3.x（JSON。YAML は標準ライブラリに無いので**非対応**） | 操作ごとの method・servers の外部性・securitySchemes の有無 | 副作用の実態。`GET` でも args_leave は真（URL に載る）と `論` で付ける |
| `claude_settings` | Claude Code `settings.json`（`permissions.allow/ask/deny`、hooks） | 道具ごとの mode（allow/ask/deny→除外）。`Bash(*)` 等のパターン | パターンが実際に何に一致するか。ワイルドカードは危ない側（広い方）に読む |

- 各形式の鍵名・意味は**版によって変わる可能性があり、段 1 の着手時に一次資料で確かめ直す（現時点は不明を含む）**。特に Claude Code settings の `permissions` 文法と MCP の `annotations` の正確な鍵名は、記憶に頼らず担当が仕様を読んで `ingest/<x>.py` の冒頭に出典と確認日を書く。
- 秘密の扱い（原則 11）：env の値・ヘッダの値・トークンらしき文字列は読んだ直後に捨て、`Config` にも報告にも入れない。試験で `sk-`・`AKIA`・`-----BEGIN` を含む入力を通し、出力に現れないことを確かめる。

### 1.3 infer（能力推定と確度）

責務：(a) ingest が渡した事実から規則で札を推定、(b) 確度の合成、(c) 置き場の畳み込みで実効の札（SPEC §6）、(d) 宣言と観察の食い違い。現 `_layer_value`・`effective`・`_min_conf`・`mismatches` を移す。

```python
@dataclass(frozen=True)
class Rule:
    id: str                       # "R-OPENAPI-GET-ARGS" のような固定 ID（報告に出す）
    applies: Callable[[Fact], bool]
    infer: Callable[[Fact], Mapping[str, Cap]]
    max_confidence: Confidence    # 規則が出せる上限。規則は「確」を出せない（上限は「論」）

def infer_caps(facts: Sequence[Fact], rules: Sequence[Rule] = DEFAULT_RULES) -> dict[str, dict[str, Cap]]: ...
def combine(a: Cap, b: Cap) -> Cap: ...       # 手書き > 規則。同じ出どころなら危ない側。確度は弱い方
def effective(tool: Tool, stores: Mapping[str, Store], layer: Layer) -> EffectiveCaps: ...
def mismatches(cfg: Config) -> list[Mismatch]: ...

@dataclass(frozen=True)
class EffectiveCaps:
    exec: bool; net: bool; secret: bool; args_leave: bool; acts: frozenset[str]
    confidence: Mapping[str, Confidence]
    assumed: frozenset[str]       # 不明 → 真と仮定した項目
```

- 不変条件（性質試験にする）：**規則・取り込みは「確」を作らない**（「確」は人の手書きか、設定ファイルの構文上の事実だけ）。不明を足しても道は減らない（単調性）。
- LLM による推定は**入れない**（DESIGN §3 の却下を維持）。

### 1.4 graph（危険経路と最小関所）

責務：危ない道の列挙（SPEC §7）と、道をすべて断つ最小の関所集合。現 `harm_paths`・`min_checkpoints`・`apply_checkpoints` を移す。

用語の正確さ（論）：現在の問題は「各道（1〜2 個の道具の集合）に少なくとも 1 つ関所を置く」＝**最小ヒッティングセット**（道が 2 個組なので頂点被覆＋単独頂点の強制）であり、フロー網の最小カットそのものではない。依頼の「最小カット厳密解」はこの意味で扱う。2 段の道に限れば「最小頂点被覆」で、一般グラフでは NP 困難だが、二部グラフ（読む側 R と送る側 S が分かれる場合）なら König の定理で多項式時間に解ける。**R と S が同じ道具でもよい（SPEC §7）ため一般には二部にならない**。

```python
@dataclass(frozen=True)
class HarmPath:
    kind: Literal["exec", "act", "exfil"]     # 将来 3 段以上を足すときは kind を増やす
    tools: tuple[str, ...]; via: tuple[str, ...]; confidence: Confidence

def harm_paths(cfg: Config, layer: Layer) -> list[HarmPath]: ...
def min_checkpoints(cfg: Config, paths: Sequence[HarmPath], *,
                    exact_limit: int = 20, max_alternatives: int = 5,
                    time_budget_s: float = 5.0) -> Checkpoints: ...
def apply_checkpoints(cfg: Config, cut: Iterable[str]) -> Config: ...
def explain(cfg: Config, paths: Sequence[HarmPath], cp: Checkpoints) -> dict[str, list[str]]: ...

@dataclass(frozen=True)
class Checkpoints:
    exact: bool                   # 厳密に最小と証明できたか
    method: Literal["trivial", "bipartite-konig", "branch-and-bound", "greedy"]
    primary: tuple[str, ...]; alternatives: tuple[tuple[str, ...], ...]
    lower_bound: int              # 近似のとき、最小の下界（LP 緩和や独立な道の数）
```

厳密解の方針（段 2 で実装）：
1. 単独の道 `[T]` の T は必ず入れる（強制）→ 残りから外す。
2. 残りが二部なら König（Hopcroft–Karp）で多項式時間・厳密。
3. 二部でなければ分枝限定（下界＝互いに素な道の数）。現行の「20 個以下なら全探索」を置き換え、**64 道具でも実用時間で厳密になる見込み（推。段 2 で測る）**。`time_budget_s` を超えたら貪欲＋下界を出し `exact=false` と明記（原則 4）。
4. 同じ大きさの案の順位は `frequency` の合計（現行どおり）。

### 1.5 report（出力）

責務：`AnalysisResult` を整形するだけ。計算しない・ファイルを書かない（書くのは cli）。

```python
def render(res: AnalysisResult, cfg: Config, fmt: Literal["text","json","sarif","md"], *,
           explain: bool = False, lang: Literal["ja","en"] = "ja") -> str: ...
def to_json(res: AnalysisResult) -> dict[str, object]: ...   # SPEC §10 と同一（互換）
def to_sarif(res: AnalysisResult, cfg: Config, *, artifact_uri: str) -> dict[str, object]: ...
```

- SARIF 2.1.0：道 1 本＝`result` 1 件。`ruleId` は `SKP-EXEC`・`SKP-ACT`・`SKP-EXFIL`・`SKP-MISMATCH-UNDER`。位置は ingest の `Origin`（無ければ宣言ファイルの先頭）。確度 → `level`（確/論=error、推=warning、不明仮定のみ=note）。**SARIF の細部（GitHub のコード スキャンが要求する最小の鍵）は段 2 で公式スキーマに対して検証する。現時点で手元に公式スキーマは無い（不明）**。
- 全形式に「走らせなかった検査」「仮定した項目」欄を必ず出す（原則 7）。
- 既存の `md` は現 `report_md` と**バイト一致**を試験で保証（互換）。`text` は端末向けの短縮版（新規）。

### 1.6 ci（GitHub Action・pre-commit）

責務：CI で回す雛形と、**基準線との差分**判定（新しく増えた道だけで失敗させる）。

```python
def load_baseline(path: str) -> Baseline: ...
def diff(prev: Baseline, cur: AnalysisResult) -> BaselineDiff: ...   # added / removed / unchanged（path_key で照合）
def write_baseline(res: AnalysisResult) -> str: ...                  # 文字列を返す。書くのは cli（--out）
```

- 雛形：`ci/templates/action.yml`（composite action。`python3 -m skopost check --format sarif` → `github/codeql-action/upload-sarif` を **SHA 固定**で呼ぶ。原則 12）、`ci/templates/.pre-commit-hooks.yaml`。
- この木の CI を有効化・push で起動することは**しない**（雛形を置くだけ。原則 1）。

### 1.7 cli

`check` `validate` `example`（現行）に加え `ingest`（外形式 → 宣言ファイルの下書きを標準出力へ）、`diff`（基準線比較）、`schema`（JSON スキーマを出す）。`--format text|json|sarif|md`。既定の `md` と既存の引数・終了コードは不変。`python3 -m skopost` でも動く（`skopost/__main__.py`）。

### 1.8 enforce（防御専用・契約のみ）

**実装は利用者の承認待ち**。段 0〜1 では `enforce/contract.py` に型と Protocol だけを置き、実装クラスは作らない。試験は「実装が無いこと」と「呼ぶと NotImplementedError」を確かめるだけ。

```python
@dataclass(frozen=True)
class EnforcementPlan:
    target: Literal["claude-settings"]           # 最初の対象案（不明：他の対象は未定）
    changes: tuple[PlannedChange, ...]           # allow → ask の移し替えのみ
    dry_run: bool = True                         # 既定ドライラン。False は明示の旗と確認文が必要

class Enforcer(Protocol):
    def plan(self, cfg: Config, cp: Checkpoints) -> EnforcementPlan: ...   # 何も書かない
    def apply(self, plan: EnforcementPlan, *, confirm_token: str) -> ApplyReport: ...
```

契約（将来の実装が守ること）：
- **締める方向だけ**（allow→ask・追加の確認）。緩める変更（ask→allow、deny の削除）は型の上で表せないようにする。
- 既定ドライラン。適用には `--apply` と、計画の内容から計算した確認文字列の手入力を要求。適用前に元ファイルの複製を残し、上書き前に差分を表示。
- 外部通信なし・他人のシステムに触れない・実行時の遮断（フックで道具呼び出しを止める等）は**この契約の外**（必要になったら別途設計と承認）。

### 1.9 corpus（評価用）

責務：合成生成器（現 `bench.py` の生成部を移す）、**実例**コーパス（公開されている設定例を、鍵・個人名・ホスト名を除いて匿名化したもの。出典とライセンスを各ファイルに記録。集め方は段 3 で決める。**集められる量は不明**）、ファズ（壊れた JSON・巨大入力・Unicode・深い入れ子）、性質試験（総当たりとの照合・単調性・往復）。`corpus/` はパッケージの外に置き、コアは依存しない。

---

## 2. データモデルと版管理

### 2.1 JSON スキーマ

- `skopost/model/schema.py` に **Draft 2020-12 の JSON スキーマを Python の dict として**持ち、`python3 -m skopost schema` で出す。検証そのものは標準ライブラリだけの自前検証器（`validate.py`）で行い、スキーマは「文書と外部ツール向け」。両者の一致は試験（スキーマから生成した正例・負例を両方に通す）で守る。
- 対象スキーマ：`config.v1`（SPEC そのもの）、`config.v2`（下記）、`result.v1`（SPEC §10）、`baseline.v1`、`ingest-notes.v1`。

### 2.2 v2 の追加（下書き・段 1 で確定）

| 追加 | 目的 | v1 との関係 |
|---|---|---|
| tool.`origin`（file/pointer/line） | SARIF の位置・どこから来た札か | 任意。無ければ従来どおり |
| cap.`source`（manual / ingest:x / infer:rule） | 出どころの追跡 | 任意。v1 読み込み時は manual |
| top.`imports`（取り込んだ元ファイルの一覧と sha256） | 再現性 | 任意 |
| 上限 `MAX_TOOLS` 64 → 256 | 実構成の大きさ | 厳密解の速度が段 2 で確かめられたら上げる（**確かめられなければ 64 のまま**） |

### 2.3 版の規則

- `skopost` 鍵（整数）＝入力仕様の版。読めるのは **現行と 1 つ前**。古い版は `migrate()` で現行に上げてから検証。未来の版は拒否（終了 1）。
- 出力 JSON の `skopost` 鍵は**結果の版**で、入力の版とは独立に上げる。v1 の鍵を消す・意味を変える変更は版を上げる。鍵の追加だけなら版据え置き。
- **配布の版とスキーマの版は別（2026-10-15 決定）**：PyPI・タグ・リリースの「配布の版」は `pyproject.toml` の `version`（0.1.0）。`skopost/model/version.py` の `__version__`（1.1.0.dev0）と SARIF 出力の `version`/`semanticVersion` は、出力形式・内部の互換の版（スキーマの版）で、配布の版とは独立に上げる。内部の試験はスキーマの版を前提にしているので変えない。
- パッケージ版 `skopost.__version__`（SemVer）。CLI の互換を壊すのは 2.0.0 のみ。
- 各版の正例・負例ファイルを `tests/fixtures/spec-v{n}/` に固定し、以降の全版で読めることを試験（原則 12）。

---

## 3. 行数・試験数の目標と事前登録する主張

行数は「実装 / 試験」の目安（推。段ごとに見直す）。合計で実装 約 9,000・試験 約 12,000・コーパスと文書 約 5,000＝**約 2.6 万行**。

| モジュール | 実装行 | 試験行 | 試験数 | 事前登録する主張（反証可能な形・測る段） |
|---|---|---|---|---|
| model | 900 | 1,400 | 120 | M1：v1 の既存 3 例と全 fixtures が v2 読み込みでも同じ `Config` になる（厳密）。M2：`to_dict∘validate` が往復で同値（性質試験 1 万例で 0 件失敗）。M3：ファズ 10 万例で例外は `SkopostError` だけ（他の例外 0 件） |
| ingest | 2,000 | 2,500 | 200 | I1：各アダプタで「確」が付くのは構文上の事実だけ（規則由来の確 0 件）。I2：秘密らしき値が出力に現れない（埋め込み 1,000 例で 0 件）。I3：実例コーパスの各形式で、読めなかった鍵が `notes` に 100% 記録される。I4：自動判別の誤り率 < 2%（混在コーパスで） |
| infer | 900 | 1,300 | 120 | F1：不明を増やして道が減る例は 0（単調性・性質試験）。F2：規則が「確」を出す例 0。F3：現行 `effective` と全合成例で一致（移植の正しさ） |
| graph | 1,500 | 2,500 | 180 | G1：厳密解は総当たりと全例で同じ大きさ（n≤14 で 5 万例）。G2：n=64・道 500 本で厳密解の 95 パーセンタイル < 2 秒（**外れる可能性あり。外れたら上限を下げる**）。G3：二部の場合 König と分枝限定が一致。G4：近似のとき `lower_bound ≤ 真の最小 ≤ |primary|` が全例で成立 |
| report | 1,100 | 1,300 | 100 | R1：`md` 出力が現行 `report_md` とバイト一致（既存例・合成 1,000 例）。R2：SARIF が公式 2.1.0 スキーマで検証を通る（段 2 でスキーマを入手できた場合。できなければ「未検証」と書く）。R3：全形式に「走らせなかった検査」欄がある |
| ci | 600 | 800 | 60 | C1：基準線の差分は道の順序・道具の並べ替えに不変（性質試験）。C2：雛形内の外部 action は全部 SHA 固定（文字列検査） |
| enforce | 150（契約のみ） | 150 | 10 | E1：段 0〜1 で書き込みを行うコード経路が 0（`open(..., "w")` 等の静的検査）。E2：緩める変更を型で表せない |
| cli | 400 | 900 | 80 | L1：既存の CLI 試験 28 個が無修正で通る。L2：既存 3 例で終了コードと JSON が段 0 と同一 |
| corpus | 1,200 | 600 | 40 | P1〜P9（PREREG.md）を新しい graph で再走し、旧結果と同じ判定になる（違えば RESULTS.md に書く）。K1：実例コーパスで declared の失敗率 g を測る（**予想は置かない＝不明。集まった件数を先に記録**） |
| 共通（layering・秘密検査） | 250 | 650 | 30 | X1：依存の向き違反 0。X2：リポジトリ内に鍵らしき文字列 0 |

- 主張は各段の**着手前**に `prereg.json` と同形式（`prereg-<module>.json`）でコミットし、結果は外れも含めて RESULTS に書く（PREREG.md の運用を踏襲）。

---

## 4. 並行実装の担当分割（触るファイルが重ならない境界）

1 つの仕事に担当は 1 人にする。着手前に担当名を記録する。

| 段 | 担当 | 触ってよいファイル | 待つもの |
|---|---|---|---|
| 1 | **A：土台** | `skopost/__init__.py`・`skopost/model/**`・`skopost/cli.py`・`skopost/__main__.py`・`skopost.py`・`tests/test_model_*`・`tests/test_cli_*`・`tests/test_layering.py`・`tests/fixtures/**` | なし。**段 1 は A だけ**（型が決まるまで他は始めない） |
| 2 | **B：取り込み** | `skopost/ingest/**`・`tests/test_ingest_*`・`tests/fixtures/ingest/**` | A の `types.py` 凍結 |
| 2 | **C：推定** | `skopost/infer/**`・`tests/test_infer_*` | 同上 |
| 2 | **D：グラフ** | `skopost/graph/**`・`tests/test_graph_*` | 同上（infer の `EffectiveCaps` 型は A が `model/types.py` に置く） |
| 2 | **E：出力・CI** | `skopost/report/**`・`skopost/ci/**`・`tests/test_report_*`・`tests/test_ci_*` | 同上（`AnalysisResult` 型も A が置く） |
| 3 | **F：コーパス** | `corpus/**`・`bench.py`・`verify.py`・`prereg-*.json`・`RESULTS.md` | B〜E の公開 API |
| — | **enforce** | `skopost/enforce/contract.py` のみ（A が段 1 で置く）。実装は**利用者の承認まで誰も担当しない** | 利用者の承認 |

境界の規則：
- **共有する型はすべて `model/types.py`**（A だけが変更できる）。B〜E が型の変更を要するときは A に依頼し、A が 1 コミットで入れる。
- `skopost/__init__.py` の再輸出の追加も A だけ。B〜E は自分のパッケージの `__init__.py` で公開する。
- 試験ファイルは接頭辞で分けるので衝突しない。共通の試験補助は `tests/helpers.py`（A 所有）。
- 段 2 の 4 担当は同じブランチでなく、それぞれ別ブランチで作業し、A（または レビュー担当）が順に統合する（**統合の順番は不明。段 1 終了時に決める**）。

---

## 5. 限界・やらないこと

- **札の正しさは確かめない**。ingest と infer は下書きを作るだけで、実能力の観察（ソースを読む・動かす）は人の仕事のまま。自動で「確」は付かない。
- **外部通信をしない**：MCP サーバーに接続して `tools/list` を取る、OpenAPI を URL から取る、などは作らない。手元のファイルだけ。
- **YAML は読まない**（標準ライブラリに無い）。OpenAPI は JSON のみ。YAML 対応は任意の外部依存として将来検討（コアには入れない）。
- **道は 2 段まで**（SPEC §7）。3 段以上の一般経路・時間順序・文脈内の値追跡は作らない（LIMITATIONS 参照）。graph の型は拡張できる形にしておくが、段 0〜3 の範囲外。
- **enforce は実装しない**（契約だけ）。実行時の遮断・フック・他人のシステムへの適用は範囲外。
- **辺の実証・注入文の生成・公開 MCP サーバーの採点・作者の告発につながる一覧**は作らない（DESIGN §3・§6）。
- **LLM による札の推定は入れない**。
- 行数の目標は目安。中身のない行で数を満たすことはしない（目標に届かなければ届かないと書く）。
- 不明のまま残っている点（再掲）：~~同名パッケージと `skopost.py` の import 優先順位の細部~~（段 1 で確かめた。下の「段 1 の結果」）／Claude Code settings と MCP annotations の現行の正確な鍵名／SARIF 公式スキーマの入手可否／64 道具での厳密解の実時間／実例コーパスの収集可能量／段 2 の統合順。

## 走らせなかった検査

- 既存の試験（`python3 -m unittest discover -s tests`）は走らせていない：この段はコードを変えていないため。
- import 優先順位の確認試験は未実施（段 1 の最初の作業）。→ 段 1 で実施（下）。

---

## 段 1 の結果（2026-10-13・担当 A：土台）

### 「不明」欄への追記：import の優先順位（確・Python 3.11.15 で試験）

- 同じ `sys.path` 要素に `m.py` と `m/__init__.py`（通常のパッケージ）があると、**パッケージが import される**（確）。
- `m/` に `__init__.py` が無い（名前空間パッケージ）ときは、**`m.py` が import される**（確）。段 1 の途中、`skopost/__init__.py` を置く前は実際に `skopost.py` が読まれた。
- `python3 skopost.py ...` で走らせたとき、スクリプトの中の `import skopost` はパッケージに解決される（sys.path[0] がスクリプトの階層のため。確）。
- 試験：`tests/test_cli_compat.py` の `ImportPrecedence`（上の 2 つを一時ディレクトリで毎回確かめる・実物の `skopost` がパッケージに解決されること・`runpy` でスクリプトと `-m` の両方の入口）。
- 3.11 以外の版での挙動は試していない（不明。ただし CPython の FileFinder の順序に依る挙動で、段 1 で読んだ範囲では版による違いを示す資料は見ていない）。

### できたもの

- `skopost/model/`：定数・例外（`SkopostError`・空実装用の `NotImplementedYet`）・不変の型（`types.py`。段 2 の全担当が使う型をすべて置いた：Cap・Tool・Store・Config・Origin・ImportRecord・Fact・IngestNote・IngestResult・EffCap・EffectiveCaps・Mismatch・Assumed・HarmPath・Checkpoints・DeclaredOnly・Summary・AnalysisResult・Baseline・BaselineDiff）・`FrozenMap`・v1 の検証器（旧 API そのまま）・型付きの読み込み `parse`/`load`（v1・v2）・版移行 `migrate`・変換 `convert`（旧辞書・入力 JSON・結果 JSON との往復）・JSON スキーマ（config.v1・config.v2・result.v1）と標準ライブラリだけの小さな検証器・`__version__`（1.1.0.dev0）。
- **v2 を確定**：v1 に任意の鍵 `tools[].origin`・`observed.*.source`・`imports` を足しただけ。`MAX_TOOLS` は 64 のまま（厳密解の速度が確かめられるまで上げない）。v1 の入力は v1 の検証器だけで読む（v2 の鍵が紛れていれば v1 の規則で拒否）。
- `skopost/compat/v1.py`（**新設・§1 の表に無かった層**）：単一ファイル時代の解析・報告部分を一字も変えずに移した凍結の参照実装。現行の CLI はこれを使う。依存は model だけ。所有は A。段 2 の実装が契約試験で一致したら cli の配線を切り替える（統合の順番は依然として不明）。
- `skopost/cli.py`・`__main__.py`・`skopost.py`（22 行の薄い入口）。`--help` の文・出力・終了コードは v1.0.0 とバイト一致（黄金ファイル `tests/fixtures/golden-v1.0.0/`。計算秒数だけ伏せた）。新しいサブコマンド（ingest・diff・schema）は段 1 では足していない（`--help` の文を変えないため）。
- 段 2 の空実装：`ingest/api.py`・`infer/api.py`＋`infer/rules.py`・`graph/api.py`・`report/api.py`・`ci/api.py`。呼ぶと `NotImplementedYet`（担当名を名乗る）。`enforce/contract.py`：型と Protocol だけ（`PlannedChange` は allow→ask 以外を生成できない・`dry_run` 既定 True・`get_enforcer` は常に未実装）。
- 依存の向き：`tests/test_layering.py`（ast で全ファイルの import を読む。逆向き・横向き・標準ライブラリ外・通信や外部プロセスの import・動的 import を失敗にする。検査自身の自己試験つき）。表に `compat`（model のみ）と `infer.rules`（ingest が読める唯一の infer）を足した。
- 契約試験：`tests/test_contract_{signatures,infer,graph,report,ci,ingest,enforce}.py`。空実装のあいだは「未実装」で飛ぶ（段 1 で 38 件）。`tests/test_contract_selfcheck.py` が v1 を型で包んだ参照の実装を差し込み、契約試験が参照で全部緑になることを確かめる（試験の側の誤りを見つけるため）。

### 所有の追記（§4 の表への追加）

| 担当 | 追加で所有するファイル |
|---|---|
| A | `skopost/compat/**`・`skopost/model/**`（examples・schema を含む）・`tests/helpers.py`・`tests/test_contract_*.py`（契約は A が持ち、段 2 の担当は自分の `tests/test_<module>_*` に詳細試験を書く）・`tests/fixtures/spec-v*/`・`tests/fixtures/golden-v1.0.0/` |
| B〜E | 自分のパッケージの `api.py` の中身と、パッケージ内の新しいファイル。**`api.py` の署名は変えない**（`test_contract_signatures` が固定）。変えたいときは A に依頼 |

### 段 1 で見つけたこと（直していない・記録のみ）

1. **単調性 F1 は v1 の参照実装で成り立たない場合がある**（確・試験 `V1StoreUnknownQuirk`）：v1 は `writes_stores`・`reads_stores` が不明のとき「置き場なし」と読む（SPEC にない v1 の設計判断。コードの注記は「過大警報にならない」）ので、置き場の札を不明にすると道が減ることがある。ARCHITECTURE §1.3 の不変条件「不明を足しても道は減らない」と食い違う。契約試験は置き場の札を F1 の対象から外した。**どちらに寄せるかは根幹の判断（危険経路の定義）で、Mythos に残す**。
2. **v1 の検証器は `"skopost": true` と `"skopost": 1.0` を通す**（確・試験 `LegacyQuirks`）：`== 1` の比較のため。CLI の互換のため旧 API は据え置き、型付きの `parse` は拒否する。
3. v1 の `min_checkpoints` は同じ大きさの案を 200 件で打ち切るので、案が 200 件を超える構成では第一案が frequency 最小でない可能性がある（論・コードを読んで。試験の乱数構成は道具 8 個以下なので当たらない）。契約試験の「第一案は v1 と同じ」はこの範囲で成り立つ。
4. 宣言の層の道の確度は v1 では「宣言」という印で、確度の 4 値の外（`HarmPath.confidence` に「宣言」を許した）。

### 走らせた検査

- `python3 -m unittest discover -s tests`：175 本・失敗 0・飛ばし 38（段 2 の空実装）。既存 `tests/test_skopost.py` 28 本は無修正で緑。
- `python3 verify.py --quick`：試験緑・例 2 つとも終了コード 2・予想 9 件中当たり 6・外れ 3（P5・P7・P9。段 1 の前と同じ数字）・終了コード 3。
- 黄金ファイルとの比較（例 2 つ × md／--explain／json、example、--help、validate、未知のコマンド）：計算秒数を除きバイト一致。

### 走らせなかった検査

- `verify.py --full`：時間がかかり、解析エンジン（compat.v1）は一字も変えていないため。
- ファズ 10 万例（M3）：段 1 は 3,000 例（環境変数 `SKOPOST_FUZZ` で増やせる）。10 万例は段 3 の corpus/fuzz で回す。
- 性質試験 1 万例（M2）：段 1 は乱数構成 60 例（`SKOPOST_TEST_SEEDS` で増やせる）。
- Python 3.11 以外での試験：手元に無いため（不明）。
- SARIF の公式スキーマでの検証：スキーマが手元に無いため（不明・段 2）。

---

## 統合の結果（2026-10-13・統合担当）

ユーザー決定：graph の既定方針は v1 のまま（monotone は `harm_paths_policy`／`analyze_policy` で選べる）。能力判定の重複は infer に寄せる。

### したこと

1. **graph → infer**：`graph.caps.effective(policy="v1")`・`graph.analysis.mismatches`・`assumed_unknown(policy="v1")` は infer を呼ぶ。graph の自前の計算は `_effective_local`・`_mismatches_local`・`_assumed_unknown_local` として残し、infer との一致を試験（`test_graph_paths.CrossCheckWithInfer`）。monotone は graph の自前のまま。
2. **`infer_caps` の既定値＝`DEFAULT_RULES`**（署名の契約試験を更新。署名の表示を保つため `DEFAULT_RULES` は repr が名前の tuple）。規則なしは `infer_caps(facts, ())`。
3. **事実の鍵名**：ingest が `name`・`description`・`schema.properties`（MCP）、`name`・`description`（OpenAPI の operationId・summary・description）、`claude.tool`（Claude 設定）を出すようにした。OpenAPI の外部判定は ingest の `openapi.server_external` に統一（infer 側を変更）。説明文は秘密らしき値を消して 2,000 字で切る。説明文から札は作らない（infer が危ない側を「推」で足すだけ）。
4. **cli**（`skopost/pipeline.py` が ingest → infer → graph → report を組む）：
   - `check FILE [--format md|json|text|sarif] [--explain] [--out F] [--baseline B] [--adapter auto|native|mcp|openapi|claude-settings]`
   - `baseline FILE [--adapter A] [--out F]`：基準線を出す。`validate` も `--adapter` を受ける。
   - 終了コード：0＝道なし／2＝道あり／1＝入力の誤り。`--baseline` のときは「新しく増えた道」があれば 2。取り込みの notes と基準線の差は標準エラーへ。
   - **既存の使い方（md・json・`--adapter`／`--baseline` なし）は compat.v1 のまま（切り替えていない）**。新しい流れが同じバイトを出すことは `test_integration.NewPipelineMatchesLegacy`（例・spec-v1 の正例・乱数 60 構成）で確認済み。`--help` は v1.0.0 と同じ文のまま（新しい引数は載っていない）。
   - 推定は不明の集合の札（acts など）を狭めない（狭めると道が減るため）。推定で道が減らないことを乱数で試験。
5. **雛形**：action.yml と .pre-commit-hooks.yaml が呼ぶコマンドを実際に走らせる試験（`test_integration.Templates`）。
6. **結合試験**：`examples/integration/` に 5 種（MCP・OpenAPI・Claude 設定・v1 宣言 2 種）、黄金ファイル `tests/fixtures/integration/`。
7. **壊れた入力**：`tests/test_fuzz_pipeline.py`（通しの構造の変異・cli のバイト列の変異）。

### 見つけたこと（直していない・記録のみ）

1. **既存の読み込み（`--adapter` なし）は深い入れ子の JSON で RecursionError を外へ出す**（確・`model.validate.read_json_file`）。終了コード 1 にならずトレースバックになる。新しい流れ（`--adapter`）は入力の誤り（1）。既存の挙動を変えるため直していない。
2. **pre-commit 雛形は `pass_filenames: true` だが、check はファイルを 1 つしか見ない**（論・引数解析を読んで。複数渡ると最後の 1 つだけ）。
3. `--format` の誤りの文言を「md か json（新しい流れでは text・sarif も）」に変えた（終了コード 1 は同じ。旧文言の黄金ファイルは無い）。
4. 推定（infer）が実際に効くのは観察の札が無い真偽の項目だけ（値は元々「不明→真」なので、確度と根拠が付くだけ）。手書き・取り込みの札があればそちらが勝つ。集合の札は上の理由で使わない。道の数を推定で減らす設計は無い。

### 走らせた検査

- `python3 -m unittest discover -s tests`：304 本・失敗 0。`tests/test_skopost.py` 28 本は無修正で緑。
- `python3 verify.py --quick`：当たり 6・外れ 3（不変）。
- 壊れた入力：model の Fuzz 10 万例（19.8 秒）・通しの構造の変異 10 万例（36.8 秒）・cli のバイト列の変異 10 万例（40.9 秒）。いずれも SkopostError 以外 0 件（上の 1 を除く。既知として数えた）。

### 走らせなかった検査

- `verify.py --full`：時間がかかり、解析エンジン（compat.v1）は変えていないため。
- SARIF の公式スキーマでの検証・GitHub 上で Action を実際に動かすこと：スキーマが手元に無い／この木の CI は有効化しない（不明）。
- 実在の第三者の設定ファイルでの試験：examples/integration は合成（実例の集め方は段 3）。
- Python 3.11 以外：手元に無い（不明）。
