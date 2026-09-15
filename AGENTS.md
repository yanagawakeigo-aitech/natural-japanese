# AGENTS.md

このリポジトリは [`natural-japanese`](./skills/natural-japanese/SKILL.md) という Agent Skill を配布するためのものです。
スキル本体は `skills/natural-japanese/` にあり、`SKILL.md` と `references/`・`scripts/`・`assets/` で構成されます。

## このスキルについて

仕事の日本語文書を読みやすくわかりやすく書く・直すためのスキルです。議事録・調査レポート・社内ガイド・リサーチメモ・スライド構成といったビジネス文書から、note・ブログ・エッセイまで扱います。AI臭さの除去は、このスキルの一工程として組み込まれています。

設計は二軸です。

- **検出は機械、判断はAI**: 疑いの検出は `skills/natural-japanese/scripts/lint.py`（sudachipy による形態素解析）が決定的に行い、どう直すかはAIが文脈で判断する
- **事後修正より生成時制約**: 書いた後にAI臭を消すより、書く前の設計（読者・主メッセージ・見出しスケルトン）と書くときの制約（`skills/natural-japanese/references/writing-constitution.md` の文体憲法12箇条）で発生自体を防ぐ

文書タイプ別の型は `skills/natural-japanese/references/doctypes/`、詳しい工程は [`SKILL.md`](./skills/natural-japanese/SKILL.md) を参照してください。

## press-japanese（姉妹スキル）

[`press-japanese`](./skills/press-japanese/SKILL.md) は、プレスリリース（PR TIMES・ニュースリリース）、新聞記事のような報道文、HP掲載のお知らせ、研究成果リリースを、渡されたソースだけに基づいて書く・直すためのスキルです。`natural-japanese` の設計に「ソースにないことは書かない」制約を足しています。

- **事実表を先に作る**: 原稿は `skills/press-japanese/assets/fact-sheet-template.md` で作った事実表にある事実だけで書く。書けない箇所は【要確認】で残す
- **忠実性は機械で照合する**: `skills/press-japanese/scripts/factcheck.py` が数値・日付・固有名詞・引用・最上級表現をソースと突き合わせる。`press_check.py` はこれに広報常套句の密度と `lint.py --genre press` を加える
- **生成AI登場前の作法を制約にする**: 逆三角形・5W1Hのリード・記者ハンドブック準拠の表記（`skills/press-japanese/references/press-style.md`）

文書タイプ別の型は `skills/press-japanese/references/doctypes/`、モデルごとの推奨は `skills/press-japanese/references/model-workflow.md` を参照してください。

## openskills 経由で読み込む場合

```bash
npx openskills install coji/natural-japanese
npx openskills sync
```

`npx openskills sync` がこの AGENTS.md 配下に `<available_skills>` ブロックを生成し、
Claude Code 以外のエージェント（Cursor, Windsurf, Aider, Codex 等）からもこのスキルを利用できるようにします。

## 検査スクリプトの実行

Python の実行は [uv](https://docs.astral.sh/uv/) を前提にしています。`pip install` や仮想環境の手動作成は不要です。機械検査層は役割ごとに3つのエントリに分かれています。

```bash
uv run skills/natural-japanese/scripts/lint.py path/to/draft.md      # 疑いの検出（--json / --genre / --baseline）
uv run skills/natural-japanese/scripts/outline.py path/to/draft.md   # スケルトン抽出（構造レビューの入力）
uv run skills/natural-japanese/scripts/terms.py path/to/draft.md     # 専門用語の初出・説明有無の一覧
uv run skills/press-japanese/scripts/factcheck.py draft.md --source memo.md      # 発表文の忠実性の照合（press-japanese）
uv run skills/press-japanese/scripts/press_check.py draft.md --source memo.md    # 忠実性 + 常套句 + lint --genre press を一括で
```

依存関係（sudachipy, sudachidict-core）は各スクリプト冒頭の PEP 723 インラインメタデータで宣言されているため、
`uv run` が自動的に解決します。共有基盤は `skills/natural-japanese/scripts/textcore.py` にまとまっています。
