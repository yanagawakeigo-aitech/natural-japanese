# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
# ]
# ///
"""analyze_wikinews.py — 生成AI登場前のニュース文（ウィキニュース日本語版）と GPT-2 生成記事に
lint.py を当て、検出器ごとの文書発火率と文体統計を出す（corpus/reports/press-style-research.md の再現用）。

データ: tanreinama/Japanese-Fakenews-Dataset の fakenews.csv（ウィキニュース日本語版の記事、CC BY 2.5。
isfake=0 が人間の原文、isfake=2 が GPT-2 日本語版 medium による全文生成）。著作権上コミットしないので、
実行前に取得しておく:

    curl -L -o corpus/experiments/press/fakenews.csv \
      https://raw.githubusercontent.com/tanreinama/Japanese-Fakenews-Dataset/master/fakenews.csv

使い方:
    uv run corpus/experiments/press/analyze_wikinews.py [人間側の本数=800] [GPT-2側の本数=400]
    → corpus/experiments/press/wikinews_lint_results.json（非コミット）
"""
import csv, json, random, re, statistics, sys, time
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "skills/natural-japanese/scripts"))
import lint  # noqa
from lint import run_lint, run_reading_load
from textcore import get_tokenizer, split_sentences_with_lines, iter_lines_with_no

csv.field_size_limit(10**9)
HERE = Path(__file__).parent
rows = list(csv.DictReader(open(HERE / "fakenews.csv", encoding="utf-8")))
random.seed(42)
human = [r for r in rows if r["isfake"] == "0" and len(r["context"]) >= 300]
fake = [r for r in rows if r["isfake"] == "2" and len(r["context"]) >= 300]
random.shuffle(human); random.shuffle(fake)
N_H, N_F = int(sys.argv[1]) if len(sys.argv) > 1 else 800, int(sys.argv[2]) if len(sys.argv) > 2 else 400
human, fake = human[:N_H], fake[:N_F]
print(f"human={len(human)} fake={len(fake)}", file=sys.stderr)

tok = get_tokenizer()
END_DESU = re.compile(r"(です|ます|ました|でした|ません|ください|ましょう)$")
END_DA = re.compile(r"(だ|である|であった|だった|た|する|ない|いる|ある|れる|られる|う|る)$")
ATTRIB = re.compile(r"(によると|によれば|としている|と述べた|と話した|と語った|と説明した|と発表した|を明らかにした|と報じた|と伝えた|という。)")
LEAD_DATE = re.compile(r"[0-9０-９]+日[、,（(]")
HALF = re.compile(r"[0-9]"); FULL = re.compile(r"[０-９]"); KANJINUM = re.compile(r"[一二三四五六七八九十百千]+(人|円|件|年|月|日|回|％|%|割|万|億)")
SUPERL = re.compile(r"(世界初|日本初|国内初|業界初|史上初|初めて|最大|最小|最高|最速|最長|最多|最新|唯一|No\.?1|ナンバーワン|画期的|革新的|圧倒的|飛躍的|劇的)")

def style_stats(text):
    sents = [s for _, s, _ in split_sentences_with_lines(iter_lines_with_no(text)) if s.strip()]
    lens = [len(s) for s in sents]
    n = len(sents)
    if n == 0:
        return None
    mean = statistics.mean(lens); sd = statistics.pstdev(lens) if n > 1 else 0.0
    cv = sd / mean if mean else 0.0
    desu = sum(1 for s in sents if END_DESU.search(s.rstrip("。」』）)")))
    da = sum(1 for s in sents if END_DA.search(s.rstrip("。」』）)")))
    nominal = 0
    for s in sents:
        ms = tok.tokenize(s.rstrip("。」』）)"))
        ms = [m for m in ms]
        while ms and ms[-1].part_of_speech()[0] in ("補助記号", "空白"):
            ms.pop()
        if ms and ms[-1].part_of_speech()[0] == "名詞":
            nominal += 1
    first = re.sub(r'^.{1,40}?(によると|によれば)[、,]?\s*', '', sents[0])
    return {
        "n_sent": n, "mean_len": mean, "cv": cv, "max_len": max(lens), "p90_len": sorted(lens)[int(0.9*(n-1))],
        "desu_ratio": desu / n, "da_ratio": da / n, "nominal_ratio": nominal / n,
        "attrib_per_sent": len(ATTRIB.findall(text)) / n,
        "lead_has_date": bool(LEAD_DATE.search(first)),
        "lead_len": len(first),
        "lead_ends_hatsuhyo": bool(re.search(r"(発表した|明らかにした|分かった|わかった|決まった|決めた|と報じた|開始した|した)$", first.rstrip("。"))),
        "half_digits": len(HALF.findall(text)), "full_digits": len(FULL.findall(text)), "kanji_num": len(KANJINUM.findall(text)),
        "quotes": text.count("「"), "superl": len(SUPERL.findall(text)), "chars": len(text),
        "dousha": text.count("同社") + text.count("同日") + text.count("同氏"),
    }

def run_set(docs, label):
    agg = {"default": Counter(), "business": Counter(), "tech": Counter()}
    agg_sev = {"default": Counter(), "business": Counter(), "tech": Counter()}
    reading = Counter()
    st = defaultdict(list)
    per_doc_examples = defaultdict(list)
    t0 = time.time()
    for i, r in enumerate(docs):
        text = r["context"]
        for genre in ("default", "business", "tech"):
            findings, stats = run_lint(text, genre=None if genre == "default" else genre)
            cats = {f.category for f in findings}
            for c in cats:
                agg[genre][c] += 1
            for f in findings:
                agg_sev[genre][(f.category, f.severity)] += 1
                if genre == "default" and len(per_doc_examples[f.category]) < 6:
                    per_doc_examples[f.category].append(f.excerpt[:60])
        rl, _ = run_reading_load(text)
        for c in {f.category for f in rl}:
            reading[c] += 1
        s = style_stats(text)
        if s:
            for k, v in s.items():
                st[k].append(v)
        if (i + 1) % 100 == 0:
            print(f"{label}: {i+1}/{len(docs)} ({time.time()-t0:.0f}s)", file=sys.stderr)
    n = len(docs)
    out = {"label": label, "n": n,
           "doc_rate": {g: {c: round(v / n, 4) for c, v in sorted(agg[g].items())} for g in agg},
           "finding_counts_by_sev": {g: {f"{c}|{s}": v for (c, s), v in sorted(agg_sev[g].items())} for g in agg_sev},
           "reading_load_doc_rate": {c: round(v / n, 4) for c, v in sorted(reading.items())},
           "examples": per_doc_examples,
           "style": {}}
    for k, vals in st.items():
        if isinstance(vals[0], bool):
            out["style"][k] = round(sum(vals) / len(vals), 4)
        else:
            out["style"][k] = {"mean": round(statistics.mean(vals), 3), "median": round(statistics.median(vals), 3),
                                "p10": round(sorted(vals)[int(0.1*(len(vals)-1))], 3), "p90": round(sorted(vals)[int(0.9*(len(vals)-1))], 3)}
    return out

res = {"human_wikinews": run_set(human, "human"), "fake_gpt2": run_set(fake, "fake")}
(HERE / "wikinews_lint_results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print("done", file=sys.stderr)
