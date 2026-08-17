#!/usr/bin/env python3
"""正向风格度量:报告一份文档离 44 篇专业范文的基线有多远。

与 audit_zh.py(负面扣分)互补:这里不扣分,只给"往哪儿靠"的靶子。
基线来自 2026-07 的范文校准(scripts/calibrate_zh.py 可对语料重算)。
用法:python3 scripts/style_metrics.py <file.md> [...]
"""

from __future__ import annotations

import statistics as st
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from audit_zh import strip_non_prose, prose_sentences, CJK_RE, CLAUSE_SEP_RE  # noqa: E402

# 2026-07 范文基线(44 篇,calibrate_zh.py 重算后同步更新这里)
BASELINE = {
    "bold_per_k": (0.0, "范文全语料为 0"),
    "bullet_line_share": (0.02, "41/44 为零;仅真实枚举"),
    "sent_mean": ((34, 49), "四桶均值区间"),
    "clause_p50": (10, "分句中位"),
    "clause_p95": (22, "分句 p95"),
    "arrow_lines": (0, "箭头链行数"),
    "emoji_status_lines": (0, "emoji 状态位行数"),
}


def metrics(text: str) -> dict:
    body = strip_non_prose(text)
    cjk = len(CJK_RE.findall(body))
    if cjk < 100:
        return {}
    sents = prose_sentences(body)
    slens = [len(CJK_RE.findall(s)) for s in sents if len(CJK_RE.findall(s)) >= 3]
    spans = sorted(x for s in sents for x in
                   (len(CJK_RE.findall(sp)) for sp in CLAUSE_SEP_RE.split(s)) if x > 0)
    lines = [l for l in text.split("\n") if l.strip()]
    return {
        "bold_per_k": round(len(re.findall(r"\*\*[^*\n]{1,40}\*\*", body)) / cjk * 1000, 1),
        "bullet_line_share": round(
            sum(1 for l in lines if re.match(r"^\s*(?:[-*+]|\d+[.、])\s", l)) / len(lines), 2),
        "sent_mean": round(st.mean(slens), 1) if slens else 0,
        "clause_p50": spans[len(spans) // 2] if spans else 0,
        "clause_p95": spans[int(len(spans) * 0.95)] if spans else 0,
        "arrow_lines": sum(1 for l in lines if l.count("→") >= 2 and CJK_RE.search(l)),
        "emoji_status_lines": sum(1 for l in lines if re.match(r"^\s*(?:[-*+]\s*)?[✅⚠❌✓✗🔎]", l)),
    }


def verdict(key: str, val) -> str:
    ref = BASELINE[key][0]
    if isinstance(ref, tuple):
        lo, hi = ref
        return "ok" if lo * 0.7 <= val <= hi * 1.3 else "off"
    if key in ("bold_per_k", "bullet_line_share", "arrow_lines", "emoji_status_lines"):
        return "ok" if val <= max(ref, 0.05 if key == "bullet_line_share" else 1) else "off"
    return "ok" if val <= ref * 1.6 else "off"


def main() -> int:
    for path in sys.argv[1:]:
        m = metrics(Path(path).read_text(encoding="utf-8"))
        print(f"\n{path}")
        if not m:
            print("  (汉字不足 100,跳过)")
            continue
        for k, v in m.items():
            ref, note = BASELINE[k]
            print(f"  {k:20s} {v!s:>7}  基线 {ref!s:>9}  [{verdict(k, v)}]  {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
