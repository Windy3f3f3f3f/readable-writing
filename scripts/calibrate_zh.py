#!/usr/bin/env python3
"""范文语料校准:重算 positive-style.md 与 audit 阈值引用的统计量。

语料版权各归原作者所有，因此不随 Skill 分发。运行时显式传入专业范文目录；如需比较
待改文档，再通过 ``--baseline`` 传入一个或多个 Markdown 文件。
"""
import argparse
import re
import sys
import json
import statistics as st
from pathlib import Path

sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
from audit_zh import audit_text, strip_non_prose, CJK_RE, CLAUSE_SEP_RE

def stats_for(text: str) -> dict:
    body = strip_non_prose(text)
    cjk = len(CJK_RE.findall(body))
    if cjk < 100:
        return {}
    sents = []
    for line in body.split('\n'):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        sents += [x for x in re.split(r'[。!?!?]', s) if len(CJK_RE.findall(x)) >= 3]
    slens = [len(CJK_RE.findall(x)) for x in sents]
    paras = [len(CJK_RE.findall(b)) for b in body.split('\n\n')
             if b.strip() and not b.strip().startswith('#')]
    paras = [p for p in paras if p >= 10]
    spans = []
    for x in sents:
        spans += [len(CJK_RE.findall(sp)) for sp in CLAUSE_SEP_RE.split(x)]
    long_span_share = sum(1 for sp in spans if sp > 25) / len(spans) if spans else 0
    lines = [l for l in text.split('\n') if l.strip()]
    bullet_share = sum(1 for l in lines if re.match(r'^\s*(?:[-*+]|\d+[.、])\s', l)) / len(lines)
    r = audit_text(text)
    return {
        'cjk': cjk,
        'sent_mean': round(st.mean(slens), 1) if slens else 0,
        'sent_cv': round(st.pstdev(slens) / st.mean(slens), 2) if slens and st.mean(slens) else 0,
        'para_mean': round(st.mean(paras), 1) if paras else 0,
        'long_span_share': round(long_span_share, 3),
        'bold_per_k': round(len(re.findall(r'\*\*[^*\n]{1,40}\*\*', body)) / cjk * 1000, 2),
        'bullet_line_share': round(bullet_share, 3),
        'arrow_lines': sum(1 for l in lines if l.count('→') >= 2),
        'de_per_k': round(body.count('的') / cjk * 1000, 1),
        'weak_per_k': round(len(re.findall(r'(?:进行|开展|实施|推进|构建|打造|形成|实现|发挥)', body)) / cjk * 1000, 2),
        'audit_score': r['score'],
        'audit_rules': sorted({f['rule'] for f in r['findings']}),
    }


def agg(rows: list[dict]) -> dict:
    if not rows:
        return {}
    keys = ['sent_mean', 'sent_cv', 'para_mean', 'long_span_share', 'bold_per_k',
            'bullet_line_share', 'de_per_k', 'weak_per_k', 'audit_score']
    return {k: round(st.mean([r[k] for r in rows]), 2) for k in keys} | {'n': len(rows)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "corpus",
        type=Path,
        help="专业中文范文目录；可按来源建立子目录，每个子目录放 Markdown 文件",
    )
    parser.add_argument(
        "--baseline",
        action="append",
        default=[],
        type=Path,
        help="可重复传入，用于比较的 Markdown 文档",
    )
    return parser.parse_args()


def main():
    from collections import Counter
    args = parse_args()
    if not args.corpus.is_dir():
        raise SystemExit(f"corpus directory not found: {args.corpus}")
    misfires = Counter()
    per_bucket = {}
    for bucket in sorted(args.corpus.iterdir()):
        if not bucket.is_dir():
            continue
        rows = []
        for f in sorted(bucket.glob('*.md')):
            s = stats_for(f.read_text(encoding='utf-8'))
            if s:
                rows.append(s)
                for rule in s['audit_rules']:
                    misfires[rule] += 1
        per_bucket[bucket.name] = agg(rows)
    baselines = [stats_for(p.read_text(encoding='utf-8')) for p in args.baseline]
    print(json.dumps({
        'buckets': per_bucket,
        'baseline': agg([row for row in baselines if row]),
        'audit_rule_fires_on_pro_corpus': dict(misfires.most_common()),
    }, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
