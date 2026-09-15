# natural-japanese

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/coji/natural-japanese)](https://github.com/coji/natural-japanese/releases)

仕事の日本語を、読みやすくわかりやすく書く・直すための [Agent Skill](https://docs.claude.com/en/docs/claude-code/skills) です。議事録・調査レポート・社内ガイド・リサーチメモ・スライド構成といった仕事の文書から、note・ブログ・エッセイまで扱います。

AIと文書を作るとき、毎回プロンプトに書いている指示があるはずです。結論から書いて。論旨を明確に。見出しは端的に。専門用語は文中で説明して。このスキルは、そうした指示を「書く前の設計」「書くときの制約」「書いた後の検査」の全工程に組み込みます。AI臭さ（AIっぽい／機械翻訳っぽい）の除去も工程の一部です。

> **English summary:** An Agent Skill for writing clear, readable Japanese work documents — designing the argument before writing, constraining generation with a 12-article style constitution, then mechanically detecting "AI-smelling" patterns via sudachipy morphological analysis and iterating until the text converges.

同じリポジトリに、姉妹スキル [`press-japanese`](./skills/press-japanese/SKILL.md) を同梱しています。プレスリリース（PR TIMES・ニュースリリース）、新聞記事のような報道文、HP掲載のお知らせ、研究成果リリースを、渡されたソースだけに基づいて「ソースにないことは書かない」制約で書く・直すためのスキルです。詳しくは後述の「[press-japanese](#press-japanese--発表文報道文をソースに忠実に書く)」を参照してください。

## 設計思想

軸は二つあります。

第一に「検出は機械、判断は人間（またはAI）」。AI は自分自身の AI 臭さを認識しにくい、という前提に立つ設計です。修正の前に、まず [`lint.py`](./skills/natural-japanese/scripts/lint.py) が形態素解析（[sudachipy](https://github.com/WorksApplications/sudachi.rs)）で決定的に検出します。

- 禁止語・紋切り型フレーズ（[`forbidden-patterns.md`](./skills/natural-japanese/references/forbidden-patterns.md)）
- 文リズムの単調さ、段落構造の均質さ
- 英語統語の直訳調（無生物主語+他動詞、連体修飾の入れ子など）

何をどう直すかはエージェント（あなた）の判断に委ねます。

第二に「事後修正より生成時制約」。AI臭は個々の語句だけでなく、段落の均質さや論旨の運びといった構造にも染み込むため、書き上がってから消そうとすると書き直しに近い作業になります。だから書く前に読者・主メッセージ・見出しスケルトンを決めます。書くときは「結論から書く」「見出しはメッセージにする」「同じ鋳型を3回繰り返さない」など12箇条の文体憲法（[`writing-constitution.md`](./skills/natural-japanese/references/writing-constitution.md)）を制約として、発生自体を防ぎます。文書タイプ別の型は [`doctypes/`](./skills/natural-japanese/references/doctypes/) にまとめてあります。

一方で、語順・読点の位置・一文一義・主語述語の距離といった「そもそも読みにくい」領域では、機械的な閾値化ができないことがコーパス検証でわかっています（[`readability-sweep.md`](./corpus/reports/readability-sweep.md)）。ここは機械に任せず、AI 自身が周回ごとに目視でレビューします。参照するのは一般原則（[`readability-principles.md`](./skills/natural-japanese/references/readability-principles.md)）と悪文パターンカタログ（[`readability-antipatterns.md`](./skills/natural-japanese/references/readability-antipatterns.md)）で、判断の重みづけがジャンルごとにどう違うかは [`genre-notes.md`](./skills/natural-japanese/references/genre-notes.md) にまとめてあります。

ただし、判定はできなくても「ここを見てください」という指し示しは機械にもできます。それが v1.4.0 で追加した読解負荷レーン（`lint.py --reading-load`）で、使い方は後述します。

## 前提条件

Python スクリプトの実行には [uv](https://docs.astral.sh/uv/) が必要です。

```bash
brew install uv
```

Homebrew を使わない場合は [uv 公式のインストールガイド](https://docs.astral.sh/uv/getting-started/installation/) を参照してください。

`pip install` や venv の手動セットアップは不要です。依存関係はスクリプト自身に書いてあり、`uv run` が実行時に自動で取ってきます（PEP 723 インラインメタデータ）。

## インストール

4つの方法がありますが、どれで入れても中身は同じです。ふだんの Claude Code なら 1 が最も簡単です。`/plugin` コマンドで更新まで管理したい場合は 3 を選んでください。

### 1. `npx skills add`（推奨）

```bash
npx skills add coji/natural-japanese
```

`skills/natural-japanese/` を読み取り、`~/.agents/skills/` などエージェントの設定ディレクトリにインストールします。

### 2. `npx openskills install`（Claude Code 以外のエージェントでも使う場合）

```bash
npx openskills install coji/natural-japanese
npx openskills sync
```

`AGENTS.md` を経由して Cursor / Windsurf / Aider / Codex など、AGENTS.md を読めるあらゆるエージェントから利用できます。

### 3. Claude Code plugin marketplace

```
/plugin marketplace add coji/natural-japanese
/plugin install natural-japanese@natural-japanese
```

`.claude-plugin/` のマニフェストを使い、`skills/natural-japanese/` をプラグインとして配布します。

### 4. GitHub Releases の `.skill`(zip)をダウンロード

[Releases](https://github.com/coji/natural-japanese/releases) から `natural-japanese.skill` をダウンロードして展開し、任意のエージェントのスキルディレクトリに配置してください。

## 使い方

一例から。AIがよく書くこんな文があるとします。

> リモートワークの普及は、働き方に大きな変化をもたらした。重要なのは、通勤時間の削減による生活の質の向上だ。また、オフィスコストの削減という企業側のメリットも見逃せない。このように、リモートワークは労働者と企業の双方にとって恩恵のある働き方だと言えるだろう。

`lint.py` が `重要なのは` `このように` `と言えるだろう` の3語を検出し、AIが文脈で判断して直すと、こうなります。

> リモートワークが広まってから、通勤で潰れていた1時間が自分の時間に戻ってきた人は多いはずだ。企業側もオフィスの家賃を削れる。誰も損をしていないように見える働き方だが、実際にそう言い切れるのかは、もう少し先まで見ないと分からない。

定型句を外すだけでなく、結論を押し付ける構えを、留保を残す言い方に変えるところまでが仕事です。ほかの事例は [`examples.md`](./skills/natural-japanese/references/examples.md) にあります。

スキルをインストールした状態で、以下のような場面で自動的に発動します。

- 議事録やレポート、企画書といった仕事の文書の作成・校正（文字起こしからの議事録化も含む）
- 「結論から書いて」「論旨を明確に」「見出しを端的に」「専門用語をわかりやすく説明して」といった指示
- 「AIっぽい」「機械翻訳っぽい」「不自然」といった指摘への修正
- AI臭さの診断・採点（書き換えずにスコアと理由だけ欲しいとき）
- 「読みにくい」「何が言いたいか分からない」「一文が長い」「読点の位置がおかしい」といった読みやすさの改善依頼
- note やブログ、エッセイの新規執筆・下書き、既存文章のリライト・推敲
- 文体プロファイル（`style-profile.md`）のセットアップ

診断は `/natural-japanese score <ファイル>` で呼び出せます。自然度スコアは0〜100で、高いほど自然です。

フローは一回検出して終わりではありません。lint の指摘を「直す / 理由を付けて残す」に仕分けし、修正が新しい指摘を生まなくなるまで——つまり収束するまで——ループします。周回ごとの差分は lint の `--baseline` オプションで機械的に追跡できます（解消・新規・継続の分類）。作業中の中間ファイルは完了時にすべて削除され、残るのは完成した文書だけです。

詳しいフローは [`SKILL.md`](./skills/natural-japanese/SKILL.md) を参照してください。

## press-japanese — 発表文・報道文をソースに忠実に書く

[`skills/press-japanese/`](./skills/press-japanese/) は、企業広報と記者の仕事に特化した姉妹スキルです。プレスリリース（PR TIMES 型）、報道記事（発表もの）、コーポレートサイトのお知らせ、研究成果リリースの4つの型を持ち、`natural-japanese` の設計（検出は機械、判断はAI。事後修正より生成時制約）に「ソース忠実」という制約を足しています。

- **ソースにないことは書かない**。原稿の前に事実表（[`assets/fact-sheet-template.md`](./skills/press-japanese/assets/fact-sheet-template.md)）を作り、原稿はその表にある事実だけで書きます。書けない箇所は推測で埋めず【要確認】として残し、納品時に一覧で渡します（[`source-fidelity.md`](./skills/press-japanese/references/source-fidelity.md)）
- **生成AI登場前の作法を制約にする**。逆三角形、5W1Hのリード、記者ハンドブック準拠の表記、地の文は事実で評価はコメント枠、という新聞社と大企業の広報の型に沿って書きます（[`press-style.md`](./skills/press-japanese/references/press-style.md)）。広報文に固有のAI臭（「実現します」の連発、「につきまして」、箇条書き病、捏造コメント）は [`ai-smell-in-press.md`](./skills/press-japanese/references/ai-smell-in-press.md)
- **忠実さを機械で照合する**。[`factcheck.py`](./skills/press-japanese/scripts/factcheck.py) が原稿の数値・日付・固有名詞・カタカナ語・引用・最上級表現をソースと突き合わせ、ソースにない要素を列挙します。[`press_check.py`](./skills/press-japanese/scripts/press_check.py) はこれに広報常套句の密度と `lint.py --genre press` を加えて一括で回します

```bash
uv run skills/press-japanese/scripts/factcheck.py draft.md --source memo.md            # 忠実性の照合
uv run skills/press-japanese/scripts/press_check.py draft.md --source memo.md         # 忠実性 + 常套句 + AI臭（lint --genre press）
```

呼び出しは `/press-japanese [release|article|notice|research] <ソース>`（書く）、`/press-japanese check <原稿> --source <ソース>`（検査のみ）。どのモデルでも忠実さが保てるよう、事実表という中間表現と機械検査を工程に組み込んでいますが、起草と判断は `claude-opus-5` 以上（Codex なら既定モデルで `model_reasoning_effort = "high"`）を推奨します。段階ごとの推奨と、弱いモデルで回すときの分割手順は [`model-workflow.md`](./skills/press-japanese/references/model-workflow.md) にあります。

設計の根拠（生成AI登場前のニュース文で `lint.py` を実測して `press` プロファイルを校正した結果と、参照した規範資料の一覧）は [`corpus/reports/press-style-research.md`](./corpus/reports/press-style-research.md) を参照してください。

### Codex で使う

Codex CLI は `.agents/skills/`（作業ディレクトリから git ルートまで）、`~/.agents/skills/`、`~/.codex/skills/` の SKILL.md を読みます。どちらのスキルも同じ形式なので、次のいずれかで入ります。

```bash
npx skills add coji/natural-japanese        # skills/ 配下の両スキルを ~/.agents/skills/ 等へ
# または Codex の中で
$skill-installer install https://github.com/coji/natural-japanese/tree/main/skills/press-japanese
```

入れたら Codex を再起動します。`press_check.py` は `natural-japanese` の `lint.py` を `~/.agents/skills/natural-japanese/` などから自動で探すので、両方入れておくとAI臭の検査まで一括で動きます。

## 検査スクリプト単体の使い方

検査層の3スクリプトは、スキルを介さず単体でも使えます。役割ごとに分かれています。共有基盤の `textcore.py` は3スクリプトが内部で使うだけで、直接実行するものではありません。

### `lint.py` — 疑いの検出

```bash
uv run skills/natural-japanese/scripts/lint.py path/to/draft.md
uv run skills/natural-japanese/scripts/lint.py path/to/draft.md --json
```

ジャンルが明確なら `--genre tech|business|essay|press` を指定してください。コーパス校正済みの閾値プロファイルに切り替わり、誤検知が減ります（`press` は発表文・報道文向けで、`press-japanese` スキルが使います）。

読みやすさの推敲には `--reading-load` を追加します（opt-in）。一文が長すぎる・埋もれた列挙・二重否定・漢字の連続・「の」の連鎖——この5つを severity info のみで指し示します。指定しない限り出力は従来と変わらず、AI臭さの findings や `--baseline` 差分にも混ざりません。

CI ゲートではなく lint なので、検出件数に関わらず exit code は `0` です。検出結果をどう直すかは書き手（またはAI）の判断に委ねます。exit code が `1` になるのは、ファイル不在・ディレクトリ指定・読み取り不可といった入力エラーのときだけです。

### `outline.py` / `terms.py` — 判断ではなく素材の抽出

findings の代わりに、構造・用語の「素材」だけを機械的に抽出します。どちらも判断はせず抽出のみで、exit code の方針は `lint.py` と同じです。

```bash
uv run skills/natural-japanese/scripts/outline.py path/to/draft.md   # 見出し・各段落の先頭文・箇条書きプレースホルダを行番号付きで抽出
uv run skills/natural-japanese/scripts/terms.py path/to/draft.md     # カタカナ複合語/ASCII略語/固有名詞らしき語を初出順に抽出（説明マーカーの有無つき）
```

### `semantic.py` — 話題平板性の検出（EXPERIMENTAL・opt-in）

```bash
uv run skills/natural-japanese/scripts/semantic.py path/to/draft.md
```

文埋め込みで、隣接する文の類似度に起伏がない状態（話題の平板さ）を検出します。torch + sentence-transformers に依存し、初回に約1GBのモデルダウンロードを伴う重量級です。そのため `lint.py` には組み込まず、独立の opt-in エントリにしています。

## リポジトリ構成

```
skills/natural-japanese/            # スキル本体（single source of truth）
  SKILL.md                          # スキル定義
  references/                       # 文体憲法・禁止パターン・チェックリスト・翻訳調ガイド・読みやすさ原則/悪文カタログ/ジャンル差分など
  references/doctypes/              # 文書タイプ別の型（議事録・調査レポート・社内ガイド・メモ/DP・スライド）
  scripts/                          # textcore.py（共有基盤）/ lint.py・outline.py・terms.py（検査層エントリ）/ semantic.py（EXPERIMENTAL・opt-in）/ calibrate.py / fixtures
  assets/                           # style-profile テンプレート
skills/press-japanese/              # 姉妹スキル: 発表文・報道文をソースに忠実に書く
  SKILL.md                          # スキル定義（release / article / notice / research / check）
  references/                       # ソース忠実の原則・報道/広報の文体規範・広報文のAI臭カタログ・モデル別推奨・手動チェック・事例
  references/doctypes/              # プレスリリース・報道記事・HPのお知らせ・研究成果リリース
  scripts/                          # factcheck.py（忠実性の照合）/ press_check.py（一括検査）/ fixtures
  assets/                           # 事実表テンプレート・各文書タイプの骨組み
  agents/openai.yaml                # Codex 向けの表示メタデータ
corpus/reports/press-style-research.md  # press-japanese の調査報告（規範資料の一覧と lint の press プロファイル校正）
evals/                 # SKILL.md description のトリガー精度評価（両スキル）
.claude-plugin/        # Claude Code plugin manifest / marketplace 定義
dev/check-fixtures.sh  # fixture 回帰チェック（開発用）
dev/check-press-fixtures.sh  # factcheck.py の fixture 回帰チェック（開発用）
.githooks/pre-commit   # lint/fixtures 変更時に fixture 回帰チェックを実行
```

各スキルの本体は `skills/` 配下の1か所だけにあります。

### 開発者向け: pre-commit hook の有効化

```bash
git config core.hooksPath .githooks
```

`skills/natural-japanese/scripts/` の `lint.py` / `textcore.py` や `fixtures/` を変更した場合は、`./dev/check-fixtures.sh` で期待検出件数（fixture 回帰）を確認してください。`skills/press-japanese/scripts/factcheck.py` と同 `fixtures/` を変更した場合は `bash dev/check-press-fixtures.sh` です（こちらはリリース時の GitHub Actions でも実行されます）。前者は該当ファイルが staged されていれば pre-commit hook が自動で実行します。タグ `v*` を push すると GitHub Actions（`.github/workflows/release.yml`）が同じチェックを実行し、`.skill` をビルドして Release に添付します。

## 参考にした資料

このスキルの設計は、次の公開資料に大きく影響を受けています。感謝します。

- [AI臭さを消した日本語執筆エージェントの設計（なつ「いとおり」）](https://note.com/art_reflection/n/n7ffd5ce3320c) — 「AIは自分のAI臭さを認識できない → 機械検出で突きつけ、判断だけを委ねる」という本スキルの核となる考え方、濃淡設計、自己点検ループの元になった記事
- [日本語技術文書の文章規範（k16shikano）](https://gist.github.com/k16shikano/fd287c3133457c4fd8f5601d34aa817d) — 禁止語カタログのうち「LLMっぽい空句」のカテゴリ群（正面から系・空虚な形容・空虚な動詞）の出典
- [meiseki（bamboo-nova）](https://github.com/bamboo-nova/meiseki) — textlint の決定論的検出と LLM の文脈判断を組み合わせる、近い設計思想の日本語明晰化プラグイン。悪文カタログを読解負荷の大きい順に並べる構成の参考。v1.4.0 の読解負荷レーン（`--reading-load`）を作るきっかけにもなった

## ライセンス

MIT. See [LICENSE](./LICENSE).
