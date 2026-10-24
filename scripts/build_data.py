#!/usr/bin/env python3
"""text/ と problems/ の Markdown から、学習サイト用の JSON（app/data/）を生成する。

使い方:
    python3 scripts/build_data.py

- 入力の書式は tickets/02_問題集作成.md「アプリ読み込み用の書式」に従う。
- 書式の崩れ（選択肢不足・解説欠け・ID重複など）は警告として表示し、終了コード 1 を返す。
- 出力 JSON は手で編集しない。
"""
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT_DIR = ROOT / "text"
PROB_DIR = ROOT / "problems"
OUT_DIR = ROOT / "app" / "data"

CHAPTERS = [
    ("01", "人工知能とは", False),
    ("02", "人工知能をめぐる動向", False),
    ("03", "機械学習の概要", False),
    ("04", "ディープラーニングの概要", True),
    ("05", "ディープラーニングの要素技術", True),
    ("06", "ディープラーニングの応用例", True),
    ("07", "AIの社会実装に向けて", False),
    ("08", "AIに必要な数理・統計知識", False),
    ("09", "AIに関する法律と契約", True),
    ("10", "AI倫理・AIガバナンス", True),
]

warnings = []


def warn(msg):
    warnings.append(msg)
    print("WARN:", msg, file=sys.stderr)


# ---------------------------------------------------------------- problems
ID_RE = re.compile(r"^### (\d{2}-\d{3})\s*$")
CHOICE_RE = re.compile(r"^- ([A-D])\. (.*)$")
ANS_RE = re.compile(r"^- 正解: ([A-D])\s*$")
WHY_RE = re.compile(r"^- ([A-D]): ([○×])\s*[（(](.*)[）)]\s*$")


def split_blocks(lines):
    """'### ID' ごとにブロックを切る。戻り値: [(id, [lines])]"""
    blocks, cur, cur_id = [], None, None
    for ln in lines:
        m = ID_RE.match(ln)
        if m:
            if cur_id:
                blocks.append((cur_id, cur))
            cur_id, cur = m.group(1), []
        elif cur is not None:
            cur.append(ln)
    if cur_id:
        blocks.append((cur_id, cur))
    return blocks


def parse_question(qid, lines, src):
    q = {"id": qid, "ch": qid[:2], "lv": "", "type": "", "terms": [], "q": "", "c": []}
    body = []
    for ln in lines:
        s = ln.rstrip()
        if s.startswith("- 難易度:"):
            q["lv"] = s.split(":", 1)[1].strip()
        elif s.startswith("- 形式:"):
            q["type"] = s.split(":", 1)[1].strip()
        elif s.startswith("- 用語:"):
            q["terms"] = [t.strip() for t in re.split(r"[,、，]", s.split(":", 1)[1]) if t.strip()]
        elif CHOICE_RE.match(s):
            m = CHOICE_RE.match(s)
            if "ABCD"[len(q["c"])] != m.group(1):
                warn(f"{src} {qid}: 選択肢の記号が A〜D の順になっていない ({m.group(1)})")
            q["c"].append(m.group(2).strip())
        elif s and not s.startswith("---"):
            body.append(s)
    q["q"] = "\n".join(body).strip()
    if len(q["c"]) != 4:
        warn(f"{src} {qid}: 選択肢が {len(q['c'])} 個（4個必要）")
    if not q["q"]:
        warn(f"{src} {qid}: 問題文がない")
    return q


def parse_answer(qid, lines, src):
    a = {"ans": None, "why": [None] * 4, "bg": ""}
    for ln in lines:
        s = ln.rstrip()
        m = ANS_RE.match(s)
        if m:
            a["ans"] = "ABCD".index(m.group(1))
            continue
        m = WHY_RE.match(s)
        if m:
            a["why"]["ABCD".index(m.group(1))] = m.group(3).strip()
            a.setdefault("marks", {})[m.group(1)] = m.group(2)
            continue
        if s.startswith("背景:"):
            a["bg"] = s.split(":", 1)[1].strip()
        elif s.startswith("背景："):
            a["bg"] = s.split("：", 1)[1].strip()
    if a["ans"] is None:
        warn(f"{src} {qid}: 正解がない")
    for i, w in enumerate(a["why"]):
        if not w:
            warn(f"{src} {qid}: 選択肢 {'ABCD'[i]} の解説がない")
    marks = a.pop("marks", {})
    if a["ans"] is not None and marks and marks.get("ABCD"[a["ans"]]) != "○":
        warn(f"{src} {qid}: 正解 {'ABCD'[a['ans']]} に ○ が付いていない")
    return a


def parse_problem_file(path, kind):
    src = path.name
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    # セクション分割
    def section(name, stop_names):
        out, on = [], False
        for ln in lines:
            if ln.startswith("## "):
                head = ln[3:].strip()
                if head == name:
                    on = True
                    continue
                if on and head in stop_names:
                    break
                if on:
                    break
            if on:
                out.append(ln)
        return out

    q_lines = section("問題", ["解答・解説", "解答一覧"])
    a_lines = section("解答・解説", ["解答一覧"])
    if not q_lines:
        warn(f"{src}: '## 問題' セクションがない")
    if not a_lines:
        warn(f"{src}: '## 解答・解説' セクションがない")

    qs = {qid: parse_question(qid, b, src) for qid, b in split_blocks(q_lines)}
    ans = {qid: parse_answer(qid, b, src) for qid, b in split_blocks(a_lines)}
    for qid in qs:
        if qid not in ans:
            warn(f"{src} {qid}: 解答・解説がない")
            qs[qid].update({"ans": None, "why": [None] * 4, "bg": ""})
        else:
            qs[qid].update(ans[qid])
    for qid in ans:
        if qid not in qs:
            warn(f"{src} {qid}: 解答はあるが問題がない")
    for q in qs.values():
        q["src"] = kind
    return list(qs.values())


def build_problems():
    problems = []
    for path in sorted(PROB_DIR.glob("*.md")):
        name = path.stem
        if name.startswith("得点記録"):
            continue
        if name.startswith("模試"):
            src = "mock" + re.sub(r"\D", "", name)
        elif re.match(r"^\d{2}_", name):
            src = "basic"
        else:
            continue
        problems.extend(parse_problem_file(path, src))

    ids = Counter(p["id"] for p in problems)
    for qid, n in ids.items():
        if n > 1:
            warn(f"問題ID {qid} が {n} 回出てくる")

    # 正解位置の偏り（ファイル単位ではなく出題元単位で確認）
    for src in sorted({p["src"] + "/" + p["ch"] if p["src"] == "basic" else p["src"] for p in problems}):
        sel = [p for p in problems if (p["src"] + "/" + p["ch"] if p["src"] == "basic" else p["src"]) == src]
        dist = Counter("ABCD"[p["ans"]] for p in sel if p["ans"] is not None)
        total = sum(dist.values())
        if total:
            worst = max(dist.values()) / total
            if worst > 0.4:
                warn(f"{src}: 正解位置の偏り {dict(dist)}")
            print(f"{src}: {total}問  正解位置 {dict(sorted(dist.items()))}")
    return problems


# ---------------------------------------------------------------- text
def build_text():
    chapters = []
    for path in sorted(TEXT_DIR.glob("*.md")):
        m = re.match(r"^(\d{2})_(.+)$", path.stem)
        if not m:
            continue
        no = m.group(1)
        md = path.read_text(encoding="utf-8")
        lines = md.splitlines()
        title = next((ln[2:].strip() for ln in lines if ln.startswith("# ")), path.stem)
        title = re.sub(r"^\d{2}\s*", "", title)
        lead = next((ln[2:].strip() for ln in lines if ln.startswith("> ")), "")
        # ## ごとに節へ分割（コードブロック内の ## は無視）
        sections, cur, in_code = [], None, False
        for ln in lines:
            if ln.startswith("```"):
                in_code = not in_code
            if not in_code and ln.startswith("## "):
                cur = {"title": ln[3:].strip(), "md": [], "h3": []}
                sections.append(cur)
                continue
            if cur is not None:
                if not in_code and ln.startswith("### "):
                    cur["h3"].append(ln[4:].strip())
                cur["md"].append(ln)
        for s in sections:
            s["md"] = "\n".join(s["md"]).strip()
        if not sections:
            warn(f"{path.name}: '## ' の節がない")
        chapters.append({"no": no, "title": title, "lead": lead, "sections": sections,
                         "chars": len(md)})
        print(f"text {no}: {len(sections)}節 {sum(len(s['h3']) for s in sections)}項目 {len(md)}文字")
    return chapters


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    problems = build_problems()
    text = build_text()
    meta = {
        "built": date.today().isoformat(),
        "chapters": [{"no": n, "name": name, "key": key} for n, name, key in CHAPTERS],
        "counts": {
            "basic": sum(1 for p in problems if p["src"] == "basic"),
            "mock1": sum(1 for p in problems if p["src"] == "mock1"),
            "mock2": sum(1 for p in problems if p["src"] == "mock2"),
            "text": len(text),
        },
    }
    (OUT_DIR / "problems.json").write_text(json.dumps(problems, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (OUT_DIR / "text.json").write_text(json.dumps(text, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (OUT_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n出力: {OUT_DIR}  問題 {len(problems)}  テキスト {len(text)}章  警告 {len(warnings)}")
    return 1 if warnings else 0


if __name__ == "__main__":
    sys.exit(main())
