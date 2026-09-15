# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
# ]
# ///
"""factcheck.py — 原稿の数値・日付・固有名詞・引用・最上級表現をソースと突き合わせる。

設計原則は natural-japanese の lint.py と同じ「検出は機械、判断はAI」。
原稿にあってソースにない要素を「疑い」として列挙するだけで、直すかどうかは
判断しない。findings の件数に関わらず exit code は 0（lint であって CI ゲートでは
ない）。入力エラー（ファイル不在・読み取り不可・--source なし）のときだけ exit 1。

使い方:
    uv run scripts/factcheck.py <draft.md> --source <src1> [--source <src2> ...] [--json]
    --source にはファイルかディレクトリ（*.md / *.txt を再帰的に読む）を渡せる。
    事実表（assets/fact-sheet-template.md で作ったもの）もソースとして渡してよい。

検出カテゴリ（severity）:
    unsupported_number (critical)     原稿の数値（単位つき）がソースにない
    unsupported_date (critical)       原稿の日付がソースにない
    unsupported_quote (critical)      「」内の12字以上の引用がソースに一致しない
    unsupported_proper_noun (warn)    固有名詞（社名・人名・地名・製品名）がソースにない
    unsupported_term (warn)           カタカナ語・英字略語・URL/メールがソースにない
    superlative_without_source (warn) 最上級・「初」の語がソースにない
    number_unit_mismatch (info)       数値はソースにあるが単位・付属表現が違う
    date_partial_match (info)         月日だけ一致し、年がソースで確認できない等
    superlative_in_source (info)      最上級の語はソースにある（根拠の記載は人が確認）
    speculation_marker (info)         推定・見込みの語（ソース側の有無を添える）
    source_fact_unused (info)         ソースにある数値・固有名詞が原稿に出てこない（網羅の確認用）

実装メモ:
    - このスクリプトは press-japanese スキル単体で動くよう自己完結にしてある
      （natural-japanese の textcore.py には依存しない）。
    - 照合は NFKC 正規化・空白除去・桁区切り除去のうえで行う。表記ゆれ（全角半角、
      「株式会社」の有無、人名の空白）は吸収するが、それ以上の同義判定はしない。
    - sudachipy は固有名詞の抽出にだけ使う（SplitMode.C）。1行ずつトークナイズする。
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
UNIT_RE = (
    r"(?:年度|年間|年代|世紀|年|カ月|か月|ヶ月|ヵ月|月|日間|日|時間|時|分|秒|"
    r"人|名|社|店舗|店|カ所|か所|箇所|ヵ所|ヶ所|カ国|か国|件|個|台|本|冊|回|部|"
    r"円|ドル|ユーロ|%|％|ポイント|pt|割|倍|km|kg|cm|mm|m|g|t|GB|MB|TB|ha|㎡|m2|"
    r"歳|世帯|校|棟|室|席|便|路線|種|品目|語|人分|食|杯|軒|つ)"
)
UNIT_PATTERN = re.compile(UNIT_RE)
BIG_UNITS = {"兆": 10**12, "億": 10**8, "万": 10**4}

NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9.])"
    r"(\d+(?:\.\d+)?(?:[兆億万]\d*(?:\.\d+)?)*)"
    r"(" + UNIT_RE + r")?"
)
HYPHEN_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])\d+(?:-\d+){1,}(?![A-Za-z0-9])")
DATE_FULL_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
DATE_YM_RE = re.compile(r"(\d{4})年(\d{1,2})月(?!\d*日)")
DATE_MD_RE = re.compile(r"(?<!\d)(?<!年)(\d{1,2})月(\d{1,2})日")
DATE_Y_RE = re.compile(r"(?<!\d)(\d{4})年(?!\d{1,2}月)")
DATE_ERA_RE = re.compile(r"(令和|平成|昭和)(\d{1,2}|元)年(?:(\d{1,2})月(?:(\d{1,2})日)?)?")
ERA_BASE = {"令和": 2018, "平成": 1988, "昭和": 1925}

KATAKANA_RE = re.compile(r"[ァ-ヶー]{3,}")
ACRONYM_RE = re.compile(r"(?<![A-Za-z0-9])(?=[A-Za-z0-9\-]*[A-Z0-9])[A-Z][A-Za-z0-9\-]{1,}(?![A-Za-z0-9])")
URL_RE = re.compile(r"https?://[^\s）)」』\]]+|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
QUOTE_RE = re.compile(r"「([^「」]+)」")
PLACEHOLDER_RE = re.compile(r"【[^】]*】")
FACT_ID_RE = re.compile(r"(?<![A-Za-z0-9])[FSQ]\d{1,3}(?![A-Za-z0-9])|※\d+")
CODE_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)

SUPERLATIVE_RE = re.compile(
    r"(世界初|日本初|国内初|業界初|史上初|県内初|地域初|初めて|初の|世界最大|国内最大|業界最大|"
    r"最大級|最大|最小|最高|最速|最長|最多|最軽量|最安|最新|唯一|No\.?\s?1|ナンバーワン|"
    r"トップクラス|随一|画期的|革新的|圧倒的|飛躍的|劇的|抜本的)"
)
SPECULATION_RE = re.compile(
    r"(見込み|見込ま|見込む|予定|期待され|期待でき|可能性|とみられ|と見られ|と考えられ|見通し|"
    r"目指し|目指す|目標|方針|計画して|想定して)"
)
COMPANY_SUFFIX_RE = re.compile(
    r"(株式会社|有限会社|合同会社|合資会社|一般社団法人|一般財団法人|公益社団法人|公益財団法人|"
    r"国立大学法人|学校法人|医療法人|社会福祉法人|独立行政法人|国立研究開発法人|特定非営利活動法人|"
    r"\(株\)|（株）|㈱|\(有\)|（有）)"
)
ORG_SUFFIX_TOKENS = {
    "株式会社", "有限会社", "合同会社", "大学", "大学院", "研究科", "研究所", "省", "庁", "市", "区",
    "町", "村", "県", "府", "都", "銀行", "病院", "協会", "財団", "機構", "学会", "センター", "工場",
    "支店", "本店", "店", "社", "グループ", "ホールディングス",
}
GENERIC_KATAKANA_SKIP = {"メール", "ページ", "サイト", "リリース", "プレスリリース", "ニュースリリース", "コメント"}

# ---------------------------------------------------------------------------
# データ構造
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class Finding:
    line: int
    category: str
    excerpt: str
    severity: str  # info | warn | critical
    detail: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


SEVERITY_LABEL = {"info": "情報", "warn": "警告", "critical": "重大"}
SEVERITY_ORDER = {"critical": 0, "warn": 1, "info": 2}


# ---------------------------------------------------------------------------
# 入力
# ---------------------------------------------------------------------------
def read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"ファイルが見つかりません: {path}")
    if path.is_dir():
        raise IsADirectoryError(f"ディレクトリが指定されました: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def collect_sources(paths: list[Path]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for p in paths:
        if p.is_dir():
            files = sorted(q for q in p.rglob("*") if q.suffix.lower() in {".md", ".txt", ".markdown"})
            if not files:
                raise FileNotFoundError(f"ディレクトリに *.md / *.txt がありません: {p}")
            for q in files:
                out.append((str(q), read_text(q)))
        else:
            out.append((str(p), read_text(p)))
    return out


def strip_noise(text: str) -> str:
    """HTMLコメント・コードフェンス内・【要確認】プレースホルダ・事実ID(F1等)を空白で潰す（行番号は保つ）。"""
    text = HTML_COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    lines = text.split("\n")
    in_fence = False
    for i, ln in enumerate(lines):
        if CODE_FENCE_RE.match(ln):
            in_fence = not in_fence
            lines[i] = ""
            continue
        if in_fence:
            lines[i] = ""
            continue
        ln = PLACEHOLDER_RE.sub(lambda m: " " * len(m.group(0)), ln)
        ln = FACT_ID_RE.sub(lambda m: " " * len(m.group(0)), ln)
        lines[i] = ln
    return "\n".join(lines)


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"(?<=\d)[,，](?=\d{3})", "", t)
    t = t.replace("‐", "-").replace("‑", "-").replace("‒", "-").replace("–", "-").replace("—", "-").replace("―", "-").replace("−", "-")
    t = t.replace("～", "~").replace("〜", "~")
    return t


def compact(text: str) -> str:
    return re.sub(r"\s+", "", normalize(text))


def strip_org_suffix(name: str) -> str:
    return COMPANY_SUFFIX_RE.sub("", name)


# ---------------------------------------------------------------------------
# 抽出: 数値・日付
# ---------------------------------------------------------------------------
def parse_number_value(s: str) -> float | None:
    """'1万2000' -> 12000, '3億5000万' -> 350000000, '9800' -> 9800, '12.5' -> 12.5"""
    total = 0.0
    rest = s
    matched_big = False
    for m in re.finditer(r"(\d+(?:\.\d+)?)([兆億万])", s):
        total += float(m.group(1)) * BIG_UNITS[m.group(2)]
        matched_big = True
        rest = s[m.end():]
    if matched_big:
        if rest:
            try:
                total += float(rest)
            except ValueError:
                return None
        return total
    try:
        return float(s)
    except ValueError:
        return None


@dataclasses.dataclass
class NumItem:
    line: int
    surface: str   # '9800円'
    value: float
    unit: str      # '円' or ''


@dataclasses.dataclass
class DateItem:
    line: int
    surface: str
    y: int | None
    m: int | None
    d: int | None


def extract_dates(text: str) -> tuple[list[DateItem], str]:
    """日付を抽出し、抽出した部分を空白で潰したテキストも返す（数値抽出の二重取りを防ぐ）。"""
    items: list[DateItem] = []
    lines = text.split("\n")
    out_lines: list[str] = []
    for no, ln in enumerate(lines, start=1):
        s = ln

        def blank(m):
            return " " * len(m.group(0))

        for m in DATE_ERA_RE.finditer(s):
            era, y, mo, d = m.group(1), m.group(2), m.group(3), m.group(4)
            yy = ERA_BASE[era] + (1 if y == "元" else int(y))
            items.append(DateItem(no, m.group(0), yy, int(mo) if mo else None, int(d) if d else None))
        s = DATE_ERA_RE.sub(blank, s)
        for m in DATE_FULL_RE.finditer(s):
            items.append(DateItem(no, m.group(0), int(m.group(1)), int(m.group(2)), int(m.group(3))))
        s = DATE_FULL_RE.sub(blank, s)
        for m in DATE_YM_RE.finditer(s):
            items.append(DateItem(no, m.group(0), int(m.group(1)), int(m.group(2)), None))
        s = DATE_YM_RE.sub(blank, s)
        for m in DATE_MD_RE.finditer(s):
            items.append(DateItem(no, m.group(0), None, int(m.group(1)), int(m.group(2))))
        s = DATE_MD_RE.sub(blank, s)
        for m in DATE_Y_RE.finditer(s):
            items.append(DateItem(no, m.group(0), int(m.group(1)), None, None))
        s = DATE_Y_RE.sub(blank, s)
        out_lines.append(s)
    return items, "\n".join(out_lines)


def extract_numbers(text: str) -> list[NumItem]:
    items: list[NumItem] = []
    for no, ln in enumerate(text.split("\n"), start=1):
        s = HYPHEN_NUMBER_RE.sub(lambda m: " " * len(m.group(0)), ln)
        for m in NUMBER_RE.finditer(s):
            raw, unit = m.group(1), m.group(2) or ""
            val = parse_number_value(raw)
            if val is None:
                continue
            # 単位なしの一桁・二桁（「3つ」は単位あり扱い、「第1」「1.」は無視）は雑音が多いので除外
            if not unit and val < 100:
                continue
            items.append(NumItem(no, raw + unit, val, unit))
    return items


def extract_hyphen_numbers(text: str) -> list[tuple[int, str]]:
    out = []
    for no, ln in enumerate(text.split("\n"), start=1):
        for m in HYPHEN_NUMBER_RE.finditer(ln):
            out.append((no, m.group(0)))
    return out


# ---------------------------------------------------------------------------
# 抽出: 固有名詞（sudachipy）・カタカナ語・英字略語・URL・引用
# ---------------------------------------------------------------------------
_tokenizer = None


def get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        from sudachipy import Dictionary

        _tokenizer = Dictionary().create()
    return _tokenizer


def _split_mode_c():
    from sudachipy import SplitMode

    return SplitMode.C


def extract_proper_nouns(text: str) -> list[tuple[int, str]]:
    tok = get_tokenizer()
    mode = _split_mode_c()
    out: list[tuple[int, str]] = []
    for no, ln in enumerate(text.split("\n"), start=1):
        if not ln.strip():
            continue
        # sudachi の入力長制限（約49KB）対策: 長い行は分割
        chunks = [ln[i:i + 8000] for i in range(0, len(ln), 8000)]
        for chunk in chunks:
            morphemes = tok.tokenize(chunk, mode)
            run: list[str] = []
            run_has_proper = False
            for mo in morphemes:
                pos = mo.part_of_speech()
                surf = mo.surface()
                is_proper = pos[0] == "名詞" and pos[1] == "固有名詞"
                is_suffix = pos[0] == "名詞" and surf in ORG_SUFFIX_TOKENS
                if is_proper or (run and is_suffix) or (not run and surf in {"株式会社", "有限会社", "合同会社"}):
                    run.append(surf)
                    run_has_proper = run_has_proper or is_proper
                    continue
                if run:
                    if run_has_proper:
                        out.append((no, "".join(run)))
                    run, run_has_proper = [], False
            if run and run_has_proper:
                out.append((no, "".join(run)))
    return out


def extract_katakana(text: str, min_len: int) -> list[tuple[int, str]]:
    out = []
    for no, ln in enumerate(text.split("\n"), start=1):
        for m in KATAKANA_RE.finditer(ln):
            w = m.group(0)
            if len(w) >= min_len and w not in GENERIC_KATAKANA_SKIP:
                out.append((no, w))
    return out


def extract_acronyms(text: str) -> list[tuple[int, str]]:
    out = []
    for no, ln in enumerate(text.split("\n"), start=1):
        ln2 = URL_RE.sub(lambda m: " " * len(m.group(0)), ln)
        for m in ACRONYM_RE.finditer(ln2):
            w = m.group(0)
            if len(w) >= 2:
                out.append((no, w))
    return out


def extract_urls(text: str) -> list[tuple[int, str]]:
    return [(no, m.group(0)) for no, ln in enumerate(text.split("\n"), start=1) for m in URL_RE.finditer(ln)]


def extract_quotes(text: str) -> list[tuple[int, str]]:
    return [(no, m.group(1)) for no, ln in enumerate(text.split("\n"), start=1) for m in QUOTE_RE.finditer(ln)]


# ---------------------------------------------------------------------------
# 照合
# ---------------------------------------------------------------------------
def longest_common_substring_ratio(a: str, b: str) -> float:
    """a（引用）が b（ソース）にどれだけ連続一致するか。簡易DP（a は短い前提）。"""
    if not a or not b:
        return 0.0
    best = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best / len(a)


def dedupe_keep_order(items: list[tuple[int, str]]) -> list[tuple[int, str]]:
    seen: set[str] = set()
    out = []
    for no, w in items:
        if w in seen:
            continue
        seen.add(w)
        out.append((no, w))
    return out


def run_factcheck(draft_raw: str, sources: list[tuple[str, str]], *, min_katakana: int = 3) -> tuple[list[Finding], dict]:
    draft = normalize(strip_noise(draft_raw))
    # ソース側は HTML コメントだけ落とす（説明用コメントが照合対象に混ざるのを防ぐ。
    # 【要確認】やコードフェンスはソースの本文でありうるので残す）
    src_text_raw = "\n".join(HTML_COMMENT_RE.sub(" ", t) for _, t in sources)
    src_norm = normalize(src_text_raw)
    src_compact = compact(src_text_raw)
    src_compact_nosuffix = strip_org_suffix(src_compact)
    src_compact_lower = src_compact.lower()

    findings: list[Finding] = []

    # --- 日付 ---
    draft_dates, draft_wo_dates = extract_dates(draft)
    src_dates, src_wo_dates = extract_dates(src_norm)
    src_full = {(d.y, d.m, d.d) for d in src_dates if d.y and d.m and d.d}
    src_ym = {(d.y, d.m) for d in src_dates if d.y and d.m}
    src_md = {(d.m, d.d) for d in src_dates if d.m and d.d}
    src_years = {d.y for d in src_dates if d.y}
    for d in draft_dates:
        if compact(d.surface) in src_compact:
            continue
        if d.y and d.m and d.d:
            if (d.y, d.m, d.d) in src_full:
                continue
            if (d.m, d.d) in src_md:
                findings.append(Finding(d.line, "date_partial_match", d.surface, "info",
                                        f"月日はソースにあるが「{d.y}年」つきの表記はない。年をソースで確認"))
                continue
            findings.append(Finding(d.line, "unsupported_date", d.surface, "critical", "この日付はソースに見当たらない"))
        elif d.y and d.m:
            if (d.y, d.m) in src_ym or any(f[0] == d.y and f[1] == d.m for f in src_full):
                continue
            findings.append(Finding(d.line, "unsupported_date", d.surface, "critical", "この年月はソースに見当たらない"))
        elif d.m and d.d:
            if (d.m, d.d) in src_md:
                continue
            findings.append(Finding(d.line, "unsupported_date", d.surface, "critical", "この月日はソースに見当たらない"))
        elif d.y:
            if d.y in src_years or str(d.y) in src_compact:
                continue
            findings.append(Finding(d.line, "unsupported_date", d.surface, "critical", "この年はソースに見当たらない"))

    # --- 数値 ---
    src_numbers = extract_numbers(src_wo_dates)
    src_values = {}
    for n in src_numbers:
        src_values.setdefault(n.value, set()).add(n.unit)
    draft_numbers = extract_numbers(draft_wo_dates)
    for n in draft_numbers:
        if compact(n.surface) in src_compact:
            continue
        if n.value in src_values:
            units = src_values[n.value]
            if n.unit in units:
                continue
            findings.append(Finding(n.line, "number_unit_mismatch", n.surface, "info",
                                    f"同じ値 {n.value:g} はソースにあるが単位・付属表現が違う（ソース側: {', '.join(u or '（単位なし）' for u in sorted(units))}）"))
            continue
        findings.append(Finding(n.line, "unsupported_number", n.surface, "critical",
                                "この数値はソースに見当たらない。換算・丸めなら事実表の備考に計算を書き、なければ削るか【要確認】に"))
    for no, hn in extract_hyphen_numbers(draft):
        if compact(hn) not in src_compact:
            findings.append(Finding(no, "unsupported_number", hn, "critical", "この番号（電話・郵便番号等）はソースに見当たらない"))

    # --- 引用 ---
    for no, q in dedupe_keep_order(extract_quotes(draft)):
        qc = compact(q)
        if qc in src_compact:
            continue
        if len(qc) >= 12:
            ratio = longest_common_substring_ratio(qc, src_compact)
            if ratio >= 0.6:
                findings.append(Finding(no, "unsupported_quote", f"「{q}」", "critical",
                                        f"ソースに近い文字列はある（連続一致 {ratio:.0%}）が一字一句同じではない。引用なら原文に戻し、要約なら「」を外す"))
            else:
                findings.append(Finding(no, "unsupported_quote", f"「{q}」", "critical", "この引用はソースに見当たらない（創作の疑い）"))
        else:
            if strip_org_suffix(qc) and strip_org_suffix(qc) in src_compact_nosuffix:
                continue
            findings.append(Finding(no, "unsupported_proper_noun", f"「{q}」", "warn", "「」で囲まれた名称がソースに見当たらない"))

    # --- 固有名詞 ---
    reported: set[str] = set()
    for no, name in dedupe_keep_order(extract_proper_nouns(draft)):
        key = strip_org_suffix(compact(name))
        if not key or len(key) < 2:
            continue
        if key in src_compact_nosuffix or compact(name) in src_compact:
            continue
        # 人名の空白ゆれ・姓だけの一致（「田中社長」）を許容
        if len(key) <= 3 and key in src_compact_nosuffix:
            continue
        if key in reported:
            continue
        reported.add(key)
        findings.append(Finding(no, "unsupported_proper_noun", name, "warn",
                                "固有名詞がソースに見当たらない。表記ゆれなら事実表の正式表記に合わせ、ソースにない語なら削る"))

    # --- カタカナ語・英字略語・URL ---
    for no, w in dedupe_keep_order(extract_katakana(draft, min_katakana)):
        if compact(w) in src_compact or compact(w) in reported:
            continue
        findings.append(Finding(no, "unsupported_term", w, "warn", "このカタカナ語はソースに見当たらない（言い換えによる情報の追加の疑い）"))
    src_norm_lower = src_norm.lower()
    for no, w in dedupe_keep_order(extract_acronyms(draft)):
        pat = r"(?<![A-Za-z0-9])" + re.escape(w.lower()) + r"(?![A-Za-z0-9])"
        if re.search(pat, src_norm_lower):
            continue
        findings.append(Finding(no, "unsupported_term", w, "warn", "この英字略語・型番はソースに見当たらない"))
    for no, u in dedupe_keep_order(extract_urls(draft)):
        if compact(u).lower() in src_compact_lower:
            continue
        findings.append(Finding(no, "unsupported_term", u, "warn", "このURL・メールアドレスはソースに見当たらない"))

    # --- 最上級・推定 ---
    for no, ln in enumerate(draft.split("\n"), start=1):
        for m in SUPERLATIVE_RE.finditer(ln):
            w = m.group(1)
            if compact(w) in src_compact:
                findings.append(Finding(no, "superlative_in_source", w, "info", "最上級・評価語はソースにもある。根拠（調査名・時期・対象）が同じ文か注記にあるかを確認"))
            else:
                findings.append(Finding(no, "superlative_without_source", w, "warn", "最上級・評価語がソースにない。根拠がなければ削る"))
        for m in SPECULATION_RE.finditer(ln):
            w = m.group(1)
            in_src = compact(w) in src_compact
            findings.append(Finding(no, "speculation_marker", w, "info",
                                    "推定・予定の語。" + ("ソースにも同じ語がある" if in_src else "ソースにこの語はない。確度を上げていないか確認")))

    # --- 網羅（ソースにあって原稿にない）---
    draft_compact = compact(strip_noise(draft_raw))
    draft_compact_nosuffix = strip_org_suffix(draft_compact)
    unused: list[str] = []
    seen_unused: set[str] = set()
    unused_numbers = 0
    for n in src_numbers:
        if not n.unit:
            continue
        if compact(n.surface) not in draft_compact and n.surface not in seen_unused:
            seen_unused.add(n.surface)
            unused.append(n.surface)
            unused_numbers += 1
    for d in src_dates:
        if compact(d.surface) not in draft_compact and d.surface not in seen_unused:
            seen_unused.add(d.surface)
            unused.append(d.surface)
    for _, name in dedupe_keep_order(extract_proper_nouns(src_norm)):
        key = strip_org_suffix(compact(name))
        if len(key) >= 2 and key not in draft_compact_nosuffix and name not in seen_unused:
            seen_unused.add(name)
            unused.append(name)
    for item in unused:
        findings.append(Finding(0, "source_fact_unused", item, "info", "ソースにあるが原稿に出てこない（意図して落としたか確認。5W1Hの欠落の疑い）"))

    findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.line))
    by_cat: dict[str, int] = {}
    for f in findings:
        by_cat[f.category] = by_cat.get(f.category, 0) + 1
    n_src_numbers = len({n.surface for n in src_numbers if n.unit})
    stats = {
        "total_findings": len(findings),
        "by_category": by_cat,
        "unsupported_total": sum(v for k, v in by_cat.items() if k.startswith("unsupported_")),
        "draft_numbers": len(draft_numbers),
        "draft_dates": len(draft_dates),
        "source_numbers_with_unit": n_src_numbers,
        "source_numbers_used_ratio": round(1 - unused_numbers / n_src_numbers, 3) if n_src_numbers else None,
        "sources": [name for name, _ in sources],
    }
    return findings, stats


# ---------------------------------------------------------------------------
# 出力
# ---------------------------------------------------------------------------
def print_human_report(path: Path, findings: list[Finding], stats: dict) -> None:
    print(f"=== factcheck: {path} ===")
    print(f"ソース: {', '.join(stats['sources'])}")
    print(f"検出件数: {stats['total_findings']}（unsupported: {stats['unsupported_total']}）")
    if stats["by_category"]:
        print("カテゴリ別内訳:")
        for cat, n in sorted(stats["by_category"].items(), key=lambda kv: -kv[1]):
            print(f"  - {cat}: {n}")
    if stats["source_numbers_used_ratio"] is not None:
        print(f"ソース側の単位つき数値の使用率: {stats['source_numbers_used_ratio']:.0%}")
    print()
    unused = [f for f in findings if f.category == "source_fact_unused"]
    for f in findings:
        if f.category == "source_fact_unused":
            continue
        print(f"[{SEVERITY_LABEL[f.severity]}] L{f.line} ({f.category})")
        print(f"    該当箇所: {f.excerpt}")
        print(f"    詳細    : {f.detail}")
        print()
    if unused:
        shown = unused[:30]
        print(f"[情報] ソースにあって原稿に出てこない要素（{len(unused)}件{'、先頭30件のみ表示' if len(unused) > 30 else ''}）:")
        print("    " + " / ".join(f.excerpt for f in shown))
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="原稿の数値・日付・固有名詞・引用・最上級をソースと突き合わせる")
    parser.add_argument("draft", type=Path, help="照合する原稿（Markdown/テキスト）")
    parser.add_argument("--source", "-s", type=Path, action="append", required=True,
                        help="ソースのファイルかディレクトリ（複数指定可）。事実表も渡せる")
    parser.add_argument("--json", action="store_true", help="機械可読な JSON で出力する")
    parser.add_argument("--min-katakana", type=int, default=3, help="照合対象にするカタカナ語の最短文字数（既定 3）")
    args = parser.parse_args()

    try:
        draft = read_text(args.draft)
        sources = collect_sources(args.source)
    except (FileNotFoundError, IsADirectoryError, PermissionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    findings, stats = run_factcheck(draft, sources, min_katakana=args.min_katakana)
    if args.json:
        print(json.dumps({"file": str(args.draft), "stats": stats, "findings": [f.to_dict() for f in findings]},
                         ensure_ascii=False, indent=2))
    else:
        print_human_report(args.draft, findings, stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
