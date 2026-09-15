# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
# ]
# ///
"""press_check.py — 発表文・記事の機械検査を1コマンドにまとめる。

やること（順に）:
    1. factcheck.py     — ソース忠実性（--source があるとき）
    2. 広報常套句の密度  — 「実現」「貢献」「につきまして」等の重なり（このスクリプト内蔵）
    3. lint.py          — natural-japanese の AI臭検出を --genre press で実行（見つかったとき）

lint.py は press-japanese スキルに同梱していない。natural-japanese スキルの
scripts/lint.py を次の順で探す:
    $NATURAL_JAPANESE_LINT（ファイルパス）→ このスクリプトの ../../natural-japanese/scripts/lint.py
    → カレントディレクトリ配下の skills/natural-japanese, .claude/skills, .agents/skills
    → ~/.claude/skills, ~/.agents/skills, ~/.codex/skills
見つからなければその旨を表示し、references/checklist.md の手動チェックに委ねる。

使い方:
    uv run scripts/press_check.py <draft.md> --source <src> [--source <src2>] [--json]
    uv run scripts/press_check.py <draft.md> --no-lint          # 忠実性と常套句だけ
    uv run scripts/press_check.py <draft.md> --no-factcheck     # 常套句と lint だけ

exit code は常に 0（入力エラーのみ 1）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from factcheck import Finding, SEVERITY_LABEL, collect_sources, read_text, run_factcheck  # noqa: E402

# ---------------------------------------------------------------------------
# 広報常套句カタログ（references/ai-smell-in-press.md と対応）
# 単体では問題のない語が多い。密度と重なりを見る。
# ---------------------------------------------------------------------------
CLICHE_GROUPS: dict[str, list[str]] = {
    "抽象動詞": ["実現", "貢献", "推進", "強化", "加速", "創出", "提供することで", "を通じて", "の実現に向けて", "に向けた取り組み"],
    "装飾語": ["革新的", "画期的", "シームレス", "寄り添", "新たな価値", "豊かな社会", "さらなる", "最適な", "幅広い", "様々な", "さまざまな", "多様な", "圧倒的", "飛躍的"],
    "過剰敬語": ["につきまして", "させていただき", "いただけますと幸い", "のほど"],
    "テンプレ冒頭": ["昨今", "近年", "が求められる中", "が高まる中", "が深刻化する中"],
    "テンプレ結び": ["貢献してまいります", "取り組んでまいります", "努めてまいります", "今後の動向が注目", "期待が高まる", "と言えるだろう", "と言えるでしょう"],
    "数字のない量": ["多くの", "数多くの", "大幅に", "大きく", "劇的に"],
}
DENSITY_WARN_PER_1000 = 5.0  # 1000字あたりの総ヒット数がこれ以上なら warn
REPEAT_WARN = 3               # 同じ語がこれ以上なら warn


def detect_cliches(text: str) -> tuple[list[Finding], dict]:
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    body = re.sub(r"【[^】]*】", "", body)
    n_chars = max(len(re.sub(r"\s", "", body)), 1)
    lines = body.split("\n")
    counts: dict[str, int] = {}
    first_line: dict[str, int] = {}
    for no, ln in enumerate(lines, start=1):
        for group, words in CLICHE_GROUPS.items():
            for w in words:
                c = ln.count(w)
                if c:
                    counts[w] = counts.get(w, 0) + c
                    first_line.setdefault(w, no)
    total = sum(counts.values())
    per_1000 = total * 1000 / n_chars
    findings: list[Finding] = []
    for w, c in sorted(counts.items(), key=lambda kv: -kv[1]):
        group = next(g for g, ws in CLICHE_GROUPS.items() if w in ws)
        if c >= REPEAT_WARN:
            findings.append(Finding(first_line[w], "press_cliche_repeat", w, "warn",
                                    f"「{w}」（{group}）が{c}回。本文全体で1回に減らすか、具体的な動作・数値に置き換える"))
        else:
            findings.append(Finding(first_line[w], "press_cliche", w, "info", f"「{w}」（{group}）{c}回。単体では慣用。密度と重なりを見る"))
    if per_1000 >= DENSITY_WARN_PER_1000:
        findings.insert(0, Finding(0, "press_cliche_density", f"{total}件 / {n_chars}字（1000字あたり{per_1000:.1f}）", "warn",
                                   f"広報常套句の密度が高い（閾値 {DENSITY_WARN_PER_1000:.0f}/1000字）。抽象動詞は1文に1つ、装飾語は地の文から外す"))
    stats = {"cliche_total": total, "cliche_per_1000": round(per_1000, 2), "chars": n_chars, "cliche_counts": counts}
    return findings, stats


# ---------------------------------------------------------------------------
# lint.py の探索と実行
# ---------------------------------------------------------------------------
def find_lint() -> Path | None:
    env = os.environ.get("NATURAL_JAPANESE_LINT")
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env).expanduser())
    candidates.append(HERE.parent.parent / "natural-japanese" / "scripts" / "lint.py")
    cwd = Path.cwd()
    home = Path.home()
    for base in (cwd / "skills", cwd / ".claude" / "skills", cwd / ".agents" / "skills",
                 home / ".claude" / "skills", home / ".agents" / "skills", home / ".codex" / "skills"):
        candidates.append(base / "natural-japanese" / "scripts" / "lint.py")
    for c in candidates:
        if c.is_file():
            return c
    return None


def run_lint(lint_path: Path, draft: Path, genre: str, reading_load: bool) -> dict | None:
    runner = ["uv", "run", str(lint_path)] if shutil.which("uv") else [sys.executable, str(lint_path)]
    cmd = runner + [str(draft), "--json", "--genre", genre]
    if reading_load:
        cmd.append("--reading-load")
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"warning: lint.py の実行に失敗: {e}", file=sys.stderr)
        return None
    if res.returncode != 0:
        print(f"warning: lint.py が exit {res.returncode}: {res.stderr.strip()[:400]}", file=sys.stderr)
        return None
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        print("warning: lint.py の出力を JSON として読めない", file=sys.stderr)
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="発表文・記事の機械検査（忠実性・常套句・AI臭）を一括で行う")
    parser.add_argument("draft", type=Path)
    parser.add_argument("--source", "-s", type=Path, action="append", default=[], help="ソースのファイルかディレクトリ（複数可）")
    parser.add_argument("--genre", default="press", help="lint.py に渡す --genre（既定 press）")
    parser.add_argument("--reading-load", action="store_true", help="lint.py の読解負荷レーンも出す")
    parser.add_argument("--no-lint", action="store_true")
    parser.add_argument("--no-factcheck", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        draft_text = read_text(args.draft)
    except (FileNotFoundError, IsADirectoryError, PermissionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    report: dict = {"file": str(args.draft)}

    # 1. factcheck
    if not args.no_factcheck:
        if not args.source:
            report["factcheck"] = {"skipped": "--source が指定されていないため忠実性検査を省略"}
        else:
            try:
                sources = collect_sources(args.source)
            except (FileNotFoundError, IsADirectoryError, PermissionError) as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            fc_findings, fc_stats = run_factcheck(draft_text, sources)
            report["factcheck"] = {"stats": fc_stats, "findings": [f.to_dict() for f in fc_findings]}

    # 2. 常套句
    cl_findings, cl_stats = detect_cliches(draft_text)
    report["cliche"] = {"stats": cl_stats, "findings": [f.to_dict() for f in cl_findings]}

    # 3. lint
    if not args.no_lint:
        lint_path = find_lint()
        if lint_path is None:
            report["lint"] = {"skipped": "natural-japanese の lint.py が見つからない。references/checklist.md の手動チェックで代替する"}
        else:
            out = run_lint(lint_path, args.draft, args.genre, args.reading_load)
            report["lint"] = {"path": str(lint_path), "result": out} if out is not None else {"skipped": "lint.py の実行に失敗"}

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    # 人間向け
    print(f"=== press_check: {args.draft} ===\n")
    fc = report.get("factcheck")
    if fc:
        if "skipped" in fc:
            print(f"[忠実性] 省略: {fc['skipped']}\n")
        else:
            st = fc["stats"]
            print(f"[忠実性] 検出 {st['total_findings']} 件（unsupported: {st['unsupported_total']}）")
            for f in fc["findings"]:
                if f["category"] == "source_fact_unused":
                    continue
                print(f"  [{SEVERITY_LABEL[f['severity']]}] L{f['line']} ({f['category']}) {f['excerpt']}")
                print(f"      {f['detail']}")
            unused = [f["excerpt"] for f in fc["findings"] if f["category"] == "source_fact_unused"]
            if unused:
                print(f"  [情報] ソースにあって原稿にない要素 {len(unused)} 件: " + " / ".join(unused[:30]))
            print()
    print(f"[常套句] {cl_stats['cliche_total']} 件（1000字あたり {cl_stats['cliche_per_1000']}）")
    for f in cl_findings:
        print(f"  [{SEVERITY_LABEL[f.severity]}] L{f.line} ({f.category}) {f.excerpt}")
        print(f"      {f.detail}")
    print()
    li = report.get("lint")
    if li:
        if "skipped" in li:
            print(f"[AI臭] 省略: {li['skipped']}\n")
        else:
            res = li["result"]
            st = res.get("stats", {})
            print(f"[AI臭] lint.py --genre {args.genre}: {st.get('total_findings', 0)} 件 ({li['path']})")
            for cat, n in sorted(st.get("by_category", {}).items(), key=lambda kv: -kv[1]):
                print(f"  - {cat}: {n}")
            for f in res.get("findings", []):
                print(f"  [{SEVERITY_LABEL.get(f['severity'], f['severity'])}] L{f['line']} ({f['category']}) {f['excerpt'][:60]}")
            rl = res.get("reading_load")
            if rl:
                print(f"  読解負荷レーン: {len(rl.get('findings', []))} 件")
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
