#!/usr/bin/env python3
"""zh-report AI 腔回归审计:对中文报告/汇报类 markdown 做可机检的 AI 腔扫描。

Forked from B1lli/remove-ai-flavor-writing-skill scripts/audit_ai_flavor.py (MIT,
https://github.com/B1lli/remove-ai-flavor-writing-skill),保留其 Rule/severity/blocker
框架与部分规则;新增翻译腔阈值(WP:翻译腔)、弱动词配额(qu-ai-wei)、模糊程度词、
markdown 感知预处理等,面向 AI-OS 的 progress/reports/DEVELOP 语体。

定位是回归护栏:通过只说明常见模板壳和翻译腔硬指标基本清掉了,不等于文章写得好。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


# FW punct constants. Rationale (zh): see LICENSE-NOTES / progress notes.
# Raw fullwidth literals typed by agents get silently normalized to ASCII by the
# input pipeline, which also corrupts hand-typed test samples -> perfect false
# negatives. So this block is ASCII-only escapes; check_fixtures.py asserts it.
# --- FW punct constants (ASCII-only, asserted) ---
FW_COMMA = "\uff0c"
FW_SEMI = "\uff1b"
FW_COLON = "\uff1a"
FW_LP = "\uff08"
FW_RP = "\uff09"
FW_BANG = "\uff01"
FW_Q = "\uff1f"
FW_PERIOD = "\u3002"
IDEO_COMMA = "\u3001"
SENT_END_CLASS = f"{FW_PERIOD}!?{FW_BANG}{FW_Q}"
CLAUSE_SEP_RE = re.compile(f"[,;:{IDEO_COMMA}{FW_COMMA}{FW_SEMI}{FW_COLON}]")
# --- end FW punct constants ---


@dataclass(frozen=True)
class Rule:
    rule_id: str
    label: str
    severity: int
    pattern: re.Pattern[str] | None = None
    terms: tuple[str, ...] = ()


# ---- 词表/正则规则(命中一处记一条) ----------------------------------------

RULES = [
    # 继承自 B1lli(节选,适配报告语体)
    Rule(
        "lecture_marker",
        "讲义腔/空转套话",
        2,
        terms=(
            "总的来说",
            "总而言之",
            "综上所述",
            "值得注意的是",
            "值得一提的是",
            "需要指出的是",
            "不可否认",
            "不难看出",
            "由此可见",
            "在这个过程中",
            "说白了",
            "划重点",
        ),
    ),
    Rule(
        "assistant_route_marker",
        "助手路标词",
        3,
        terms=(
            "下面我们来",
            "接下来我会",
            "接下来我们",
            "我们可以看到",
            "希望这能帮到",
            "让我们",
        ),
    ),
    Rule(
        "essence_claim",
        "本质/核心式拔高",
        2,
        pattern=re.compile(r"本质上|核心在于|底层逻辑|真正[的重]?要的是"),
    ),
    Rule(
        "inflated_abstract_words",
        "黑话/抽象包装词",
        2,
        terms=(
            "赋能",
            "抓手",
            "深耕",
            "价值感",
            "长期主义",
            "意义深远",
            "前景广阔",
            "保驾护航",
            "行稳致远",
        ),
    ),
    Rule(
        "academic_filler",
        "模糊权威/公式化意义拔高",
        3,
        pattern=re.compile(
            rf"(?:研究表明|专家认为|业内普遍认为)(?![^。\n]{{0,12}}[({FW_LP}《\[])"
            r"|具有重要(?:理论|现实|指导)?意义|提供了新思路|开辟了新方向|奠定了(?:坚实)?基础"
        ),
    ),
    Rule(
        "rigid_enumeration",
        "首先/其次式整齐编号",
        1,
        pattern=re.compile(r"首先[^。\n]{0,80}其次|其次[^。\n]{0,80}(?:再次|最后)|一方面[^。\n]{0,80}另一方面"),
    ),
    Rule(
        "ending_cliche",
        "空洞积极结尾/假互动",
        3,
        pattern=re.compile(rf"(?:未来可期|拭目以待|更上一层楼|再创佳绩|欢迎(?:大家)?(?:讨论|指正|交流))[!{FW_BANG}。]?\s*$", re.M),
    ),
    # 新增:翻译腔硬指标
    Rule(
        "weak_verb",
        "弱动词硬造动宾(进行/加以…)",
        2,
        # 要求"了/着"或接抽象名词宾语,避免误伤"进行中"等合法用法
        pattern=re.compile(r"(?:进行|加以|开展|予以|给予)(?:了|着|[一-龥]{0,4}(?:工作|处理|分析|讨论|优化|排查|验证|测试|评估|梳理|调研|改造|修复))"),
    ),
    Rule(
        "zuochu",
        "作出/做出+抽象名词",
        1,
        pattern=re.compile(r"[作做]出(?:了)?(?:重要|重大|巨大|一定|相应)?的?(?:贡献|努力|改进|调整|决定|判断|回应)"),
    ),
    Rule(
        "youyu_shide",
        "由于…使得/导致(主语被吞)",
        2,
        pattern=re.compile(r"由于[^。\n]{2,30}(?:使得|导致|造成)"),
    ),
    Rule(
        "chenggong_de",
        "冗余副词(成功地/有效地…地)",
        1,
        pattern=re.compile(r"(?:成功|有效|完美|顺利|充分)地[一-龥]"),
    ),
    Rule(
        "zhiyi",
        "最…之一(蛇足)",
        1,
        pattern=re.compile(r"最[一-龥]{1,8}(?:的|之)[一-龥]{0,10}之一"),
    ),
    # vague_degree 改为整句级形状检测(见 audit_shape),避免"数字在前半句"误报、"(见图3)"漏报
    Rule(
        "adj_colon_opener",
        "形容词+冒号起手(逻辑很清晰:)",
        2,
        pattern=re.compile(rf"(?:^|[{SENT_END_CLASS}\n])[^,{FW_COMMA}。;{FW_SEMI}:{FW_COLON}\n]{{0,10}}(?:很|相当|非常|比较)[一-龥]{{1,4}}[:{FW_COLON}]", re.M),
    ),
]


# ---- markdown 感知预处理 ------------------------------------------------------

FENCE_RE = re.compile(r"```.*?```", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
MD_LINK_TARGET_RE = re.compile(r"\]\([^)\n]+\)")  # markdown 链接的 (target) 不算正文括号
URL_RE = re.compile(r"https?://\S+")
FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.S)


def strip_non_prose(text: str) -> str:
    """去掉代码块/行内代码/表格行/URL/frontmatter,保留行结构(行号对齐用等长空白不可行,
    直接以牺牲被剔除区域的检测为代价,保持其余行号一致)。"""
    text = FRONTMATTER_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    text = FENCE_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    text = INLINE_CODE_RE.sub("", text)
    text = MD_LINK_TARGET_RE.sub("]", text)
    text = URL_RE.sub("", text)
    lines = []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("|") or s.startswith("<"):  # 表格行/HTML
            lines.append("")
        else:
            lines.append(line)
    return "\n".join(lines)


def line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def excerpt(text: str, start: int, end: int) -> str:
    left = max(0, start - 20)
    right = min(len(text), end + 20)
    return text[left:right].replace("\n", "\\n")


# ---- 形状类检测(全文统计) ----------------------------------------------------

CJK_RE = re.compile(r"[一-龥]")


def prose_sentences(text: str) -> list[str]:
    """标题/列表标记之外的句子。"""
    out = []
    for line in text.split("\n"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        s = re.sub(r"^(?:[-*+]|\d+[.、))])\s*", "", s)
        out.extend(p for p in re.split(f"[{SENT_END_CLASS}]", s) if p.strip())
    return out


def audit_shape(text: str) -> list[dict]:
    findings: list[dict] = []

    # 以下两条阈值用 44 篇官媒/科技媒体范文校准(2026-07,修复全角切分 bug 后重算):
    # 范文分句 p50=10 字、p95=22 字、仅 3% 超 25 字;连环「的」每篇中位 0 处、p90 为 3 处。

    # 欧化长句:>25 字分句 ≥3 处且占全部分句 ≥15%(范文误报 ≤1/44;抓一逗到底/不加标点的病文)
    spans = []
    for sent in prose_sentences(text):
        spans += [len(CJK_RE.findall(sp)) for sp in CLAUSE_SEP_RE.split(sent)]
    spans = [x for x in spans if x > 0]
    long_spans = [x for x in spans if x > 25]
    if spans and len(long_spans) >= 3 and len(long_spans) / len(spans) >= 0.15:
        findings.append({
            "rule": "long_clause",
            "label": f"欧化长句:>25字分句 {len(long_spans)}处,占比{len(long_spans)/len(spans):.0%}",
            "severity": 2,
            "line": 1,
            "match": f"{len(long_spans)}/{len(spans)} spans",
            "excerpt": "范文里超 25 字的分句仅 3%;一逗到底请拆句",
        })

    # 连环「的」:一小句 ≥3 个「的」出现 ≥4 处(范文 p90 为 3 处)
    de_hits = []
    for sent in prose_sentences(text):
        for sp in CLAUSE_SEP_RE.split(sent):
            if sp.count("的") >= 3:
                de_hits.append(sp.strip()[:40])
    if len(de_hits) >= 4:
        findings.append({
            "rule": "de_chain",
            "label": f"连环「的」(一小句≥3个) 共{len(de_hits)}处",
            "severity": 1,
            "line": 1,
            "match": f"{len(de_hits)} spans",
            "excerpt": " / ".join(de_hits[:3]),
        })

    # 模糊程度词无数字:整句内没有任何"证据数字"(图3/表2 等引用编号不算证据)
    degree_re = re.compile(r"(?:显著|大幅|明显|极大|有效)(?:地)?(?:提升|提高|降低|下降|改善|优化|增强|减少|加快)")
    num_evidence_re = re.compile(r"(?<![图表例式第])\d")
    for lineno, raw_line in enumerate(text.split("\n"), start=1):
        s = raw_line.strip()
        if not s or s.startswith("#"):
            continue
        s = re.sub(rf"^(?:[-*+]|\d+[.{IDEO_COMMA}){FW_RP}])\s*", "", s)
        for sent in re.split(f"[{SENT_END_CLASS}]", s):
            m = degree_re.search(sent)
            if m and not num_evidence_re.search(sent):
                findings.append({
                    "rule": "vague_degree",
                    "label": "模糊程度词无数字",
                    "severity": 2,
                    "line": lineno,
                    "match": m.group(0),
                    "excerpt": sent.strip()[:44],
                })

    # 被字密度:每千汉字 >4 处「被」(排除术语:被试/被访者/被告/被害人/被保险人/被动/被迫/被称为/被誉为)
    cjk_total = len(CJK_RE.findall(text))
    bei = len(re.findall(r"被(?!试|访者|保险人|害人|告|动|迫|称|誉)", text))
    if cjk_total >= 300 and bei / cjk_total * 1000 > 4:
        findings.append({
            "rule": "passive_density",
            "label": f"被字密度偏高({bei}处/{cjk_total}字)",
            "severity": 1,
            "line": 1,
            "match": f"{bei} 被",
            "excerpt": "多数可改主动或换固有词(遇害/当选/获通过)",
        })

    # 弱动词配额(qu-ai-wei):每千字 >10(2026-07 范文校准:官媒中位 3.7、p90 9.4,原阈值 5 会误伤四成范文)
    weak = len(re.findall(r"(?:进行|开展|实施|推进|构建|打造|形成|实现|发挥)", text))
    if cjk_total >= 300 and weak / cjk_total * 1000 > 10:
        findings.append({
            "rule": "weak_verb_quota",
            "label": f"弱动词密度偏高({weak}处/{cjk_total}字)",
            "severity": 2,
            "line": 1,
            "match": f"{weak} weak verbs",
            "excerpt": "换成只有该场景能用的具体动作(跑通/修好/量到/砍掉)",
        })

    # 正文加粗密度:≥4 对 ** 且每千汉字 >6(密度病跟篇幅无关,不设字数门槛)
    bold = len(re.findall(r"\*\*[^*\n]{1,40}\*\*", text))
    if bold >= 4 and cjk_total > 0 and bold / cjk_total * 1000 > 6:
        findings.append({
            "rule": "bold_density",
            "label": f"正文加粗过密({bold}处/{cjk_total}字)",
            "severity": 1,
            "line": 1,
            "match": f"{bold} bold spans",
            "excerpt": "加粗只留真正要跳读锚定的词",
        })

    # 箭头链当因果连接词(语料实测头号符号腔):prose 行内 "A → B → C" 式推理链
    arrow_lines = []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("#"):
            continue
        # 两个以上 → 且行内含 CJK(排除纯英文命令行/纯数值迁移标注)
        if s.count("→") >= 2 and CJK_RE.search(s):
            arrow_lines.append(s[:44])
    if len(arrow_lines) >= 2:
        findings.append({
            "rule": "arrow_chain",
            "label": f"箭头链代替因果句 共{len(arrow_lines)}行",
            "severity": 2,
            "line": 1,
            "match": f"{len(arrow_lines)} arrow-chain lines",
            "excerpt": " / ".join(arrow_lines[:2]),
        })

    # emoji 状态位当谓语:✅⚠️❌ 开头的行占比
    status_lines = [s for s in text.split("\n") if re.match(r"^\s*(?:[-*+]\s*)?[✅⚠❌✓✗🔎]", s)]
    if len(status_lines) >= 5:
        findings.append({
            "rule": "emoji_status",
            "label": f"emoji/勾叉状态位过密({len(status_lines)}行)",
            "severity": 1,
            "line": 1,
            "match": f"{len(status_lines)} status lines",
            "excerpt": "状态位不替代谓语:正文要有动词判断句",
        })

    # 括号栈:一句内 ≥2 处括号、或括号内含分号/嵌套括号
    paren_hits = []
    for sent in prose_sentences(text):
        opens = sent.count("(") + sent.count(FW_LP)
        nested = (re.search(rf"[({FW_LP}][^){FW_RP}]*[({FW_LP}]", sent)
                  or re.search(rf"[({FW_LP}][^){FW_RP}]*[;{FW_SEMI}][^){FW_RP}]*[){FW_RP}]", sent))
        if opens >= 2 or nested:
            paren_hits.append(sent.strip()[:40])
    if len(paren_hits) >= 3:
        findings.append({
            "rule": "paren_stack",
            "label": f"括号栈(一句多层/多处括号) 共{len(paren_hits)}处",
            "severity": 1,
            "line": 1,
            "match": f"{len(paren_hits)} sentences",
            "excerpt": " / ".join(paren_hits[:2]),
        })

    # 加粗标签墙:连续 ≥3 行以 "**X**:" 或 "- **X**" 领起
    label_run, best_run, run_start, best_start = 0, 0, 0, 0
    for i, line in enumerate(text.split("\n"), start=1):
        if re.match(rf"^\s*(?:[-*+]\s*|\d+[.、]\s*)?\*\*[^*]{{1,24}}\*\*[:{FW_COLON}]?", line.strip()):
            if label_run == 0:
                run_start = i
            label_run += 1
            if label_run > best_run:
                best_run, best_start = label_run, run_start
        else:
            label_run = 0
    if best_run >= 4:
        findings.append({
            "rule": "label_wall",
            "label": f"加粗标签墙(连续{best_run}行 **X**: 同构)",
            "severity": 1,
            "line": best_start,
            "match": f"{best_run} consecutive label lines",
            "excerpt": "同构标签段合并成散文,或只保留真正要跳读锚定的",
        })

    # 「不是A,而是B」对照句式成口癖(AI 高频修辞框架):≥3 处且每千汉字 >0.8
    # 2026-07 hccw 语料实测:病文 1.0-1.4 处/千字;人工定稿章节 0.4-0.6 处/千字,阈值取中间偏严
    bushi_hits = []
    bushi_re = re.compile(rf"(?:不是|并非|不再是)[^;{FW_SEMI}]{{1,40}}?而是")
    for sent in prose_sentences(text):
        for m in bushi_re.finditer(sent):
            bushi_hits.append(sent.strip()[:40])
    if len(bushi_hits) >= 3 and cjk_total >= 300 and len(bushi_hits) / cjk_total * 1000 > 0.8:
        findings.append({
            "rule": "bushi_ershi",
            "label": f"「不是…而是…」对照句成口癖({len(bushi_hits)}处/{cjk_total}字)",
            "severity": 1,
            "line": 1,
            "match": f"{len(bushi_hits)} spans",
            "excerpt": " / ".join(bushi_hits[:3]),
        })

    # 段落长度过均匀(B1lli 原样保留)
    paragraph_lengths = [
        len(re.sub(r"\s+", "", block))
        for block in text.split("\n\n")
        if block.strip() and not block.strip().startswith("#")
    ]
    medium = [n for n in paragraph_lengths if 24 <= n <= 90]
    if len(medium) >= 5 and max(medium) - min(medium) <= 12:
        findings.append({
            "rule": "over_even_paragraphs",
            "label": "段落长度过于均匀",
            "severity": 1,
            "line": 1,
            "match": f"lengths={medium[:8]}",
            "excerpt": "段落重量要有变化:短拍/中等解释/厚段落/短落点",
        })

    return findings


# ---- 主流程 -------------------------------------------------------------------


def audit_text(raw: str) -> dict:
    text = strip_non_prose(raw)
    findings = []
    for rule in RULES:
        if rule.pattern:
            for m in rule.pattern.finditer(text):
                findings.append({
                    "rule": rule.rule_id,
                    "label": rule.label,
                    "severity": rule.severity,
                    "line": line_number(text, m.start()),
                    "match": m.group(0)[:40],
                    "excerpt": excerpt(text, m.start(), m.end()),
                })
        for term in rule.terms:
            start = 0
            while (idx := text.find(term, start)) >= 0:
                findings.append({
                    "rule": rule.rule_id,
                    "label": rule.label,
                    "severity": rule.severity,
                    "line": line_number(text, idx),
                    "match": term,
                    "excerpt": excerpt(text, idx, idx + len(term)),
                })
                start = idx + len(term)

    findings.extend(audit_shape(text))
    findings.sort(key=lambda f: (f["line"], -f["severity"], f["rule"]))
    score = sum(f["severity"] for f in findings)
    blockers = [f for f in findings if f["severity"] >= 3]
    return {
        "score": score,
        "finding_count": len(findings),
        "blocker_count": len(blockers),
        "status": "pass" if not blockers and score <= 4 else "review",
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Chinese report-style markdown for AI-flavor patterns.")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on-review", action="store_true")
    args = parser.parse_args()

    results, failed = {}, False
    for raw_path in args.paths:
        text = Path(raw_path).read_text(encoding="utf-8")
        result = audit_text(text)
        results[raw_path] = result
        failed = failed or result["status"] != "pass"

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for path, r in results.items():
            print(f"{path}: {r['status']} score={r['score']} findings={r['finding_count']} blockers={r['blocker_count']}")
            for f in r["findings"][:15]:
                print(f"  L{f['line']} [{f['label']}] {f['match']}")
            if len(r["findings"]) > 15:
                print(f"  ... {len(r['findings']) - 15} more")
    return 1 if args.fail_on_review and failed else 0


if __name__ == "__main__":
    sys.exit(main())
