# press-japanese SKILL.md description — trigger-precision check

Eval set: `evals/press-japanese-evals.json` (22 positive / 12 negative, train/test split
recorded in the file). Judgment method is the same role-play used for
`natural-japanese` (`evals/RESULTS.md`): for each query, judge whether the description
text alone would make Claude Code consult the skill, assuming Claude's known
undertrigger tendency (a borderline case is scored "does not trigger" unless the
description contains a clear textual anchor for that phrasing).

## Iteration 0 — initial description (self-judged, 2026-09)

Anchors the description relies on: the document types (プレスリリース / PR TIMES /
ニュースリリース / 報道発表資料 / 新聞・通信社の記事 / 発表もの / ストレートニュース /
取材メモからの記事化 / HP掲載のお知らせ / 研究成果リリース), the constraint phrasings
(「ソースにないことは書かない」「創作しない」「盛らない」「事実だけで」「資料の範囲で」),
the role phrasings (「記者として」「広報として」), the conversion phrasings
(「リリースを記事にして」「記事風に」「新聞のように」「PR TIMES用に」「HPのお知らせ文に」),
and the review phrasings (「AIっぽい」「誇張が気になる」「記者に伝わるか見て」
「事実確認して」「捏造がないかチェック」). Exclusions name the natural-japanese
document types, English press releases, advertising copy / LP / SNS / メルマガ, and 社内報.

| id | query | expected | judged | anchor |
|----|-------|----------|--------|--------|
| p1 | このメモからPR TIMES用のプレスリリースを書いて | trigger | trigger | PR TIMES用に |
| p2 | 新サービスのニュースリリース、資料の範囲で書いてほしい | trigger | trigger | ニュースリリース, 資料の範囲で |
| p3 | このリリースを新聞記事風にして | trigger | trigger | 記事風に |
| p4 | 取材メモから記事を起こして。事実だけで | trigger | trigger | 取材メモからの記事化, 事実だけで |
| p5 | 料金改定のお知らせをHPに載せる文にして | trigger | trigger | HP掲載のお知らせ（料金改定） |
| p6 | 論文の内容を研究成果のプレスリリースにまとめて | trigger | trigger | 研究成果リリース |
| p7 | この発表文、AIっぽいし盛りすぎ。直して | trigger | trigger | AIっぽい, 盛らない |
| p8 | 広報として、この資料を報道発表資料の形にして | trigger | trigger | 広報として, 報道発表資料 |
| p9 | 記者として、この発表を記事にしてください。創作は禁止 | trigger | trigger | 記者として, 創作しない |
| p10 | このプレスリリースに捏造がないかソースと照合して | trigger | trigger | 捏造がないかチェック |
| p11 | 障害のお知らせ文をコーポレートサイト用に書いて | trigger | trigger | コーポレートサイト, 障害 |
| p12 | ストレートニュースの形で400字にまとめて | trigger | trigger | ストレートニュース |
| p13 | リリースの誇張が気になる。記者に伝わるか見て | trigger | trigger | 誇張が気になる, 記者に伝わるか見て |
| p14 | 人事異動のニュースリリースを作って | trigger | trigger | ニュースリリース, 人事 |
| p15 | この社内資料から、盛らずにプレスリリースを起こして | trigger | trigger | 盛らない, プレスリリース |
| p16 | 発表資料をもとに新聞のような記事を書いて | trigger | trigger | 新聞のように |
| p17 | 大学の研究成果を発表文にしたい。論文はこれ | trigger | trigger | 研究成果を発表文に |
| p18 | イベント開催のお知らせをホームページに出したい | trigger | trigger | HP掲載のお知らせ（イベント） |
| p19 | このリリース、事実確認して。資料と違うところある？ | trigger | trigger | 事実確認して |
| p20 | 報道機関向けの発表文を、資料にない情報を足さずに書いて | trigger | trigger | 発表文, ソースにないことは書かない |
| p21 | 記事化しやすいリリースに直して | trigger | trigger | 既存の発表文の校正 |
| p22 | ニュース記事っぽく、発表内容を三人称で書き直して | trigger | trigger | 記事風に |
| n1 | この議事録を読みやすくして | no-trigger | no-trigger | 議事録 is named as natural-japanese territory |
| n2 | 英語のプレスリリースを書いて | no-trigger | no-trigger | explicit exclusion |
| n3 | LPのキャッチコピーを10案出して | no-trigger | no-trigger | explicit exclusion |
| n4 | noteの記事を書いて | no-trigger | no-trigger | note記事 named as natural-japanese territory |
| n5 | このコードにコメントを追加して | no-trigger | no-trigger | unrelated |
| n6 | SNS投稿文を5本作って | no-trigger | no-trigger | explicit exclusion |
| n7 | 調査レポートの結論を先に書き直して | no-trigger | no-trigger | 調査レポート named as natural-japanese territory |
| n8 | 社内報のコラムを書いて | no-trigger | no-trigger | explicit exclusion |
| n9 | メルマガの文面を考えて | no-trigger | no-trigger | explicit exclusion |
| n10 | この日本語の文章を英語に訳して | no-trigger | no-trigger | unrelated |
| n11 | 提案書のスライド構成を作って | no-trigger | no-trigger | natural-japanese territory |
| n12 | この一文の誤字を直して | no-trigger | no-trigger | unrelated |

Score: 34/34 by self-judgment (train 21/21, test 13/13). This is a desk check by the
author of the description, not a measured run; treat it as iteration 0 and re-run the
role-play (or `claude plugin eval`) after any description change. The known
risk is the boundary with `natural-japanese` on generic "書いて" requests that mention
a company announcement without naming a document type (e.g. 「新製品の発表を文章にして」):
the description does not contain an anchor for that phrasing, so it would likely fall
to natural-japanese, which is acceptable because that skill hands press work over
when the user clarifies.
