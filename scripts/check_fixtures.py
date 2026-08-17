#!/usr/bin/env python3
"""回归门:audit_zh 对 fixtures 的检出必须与 expected.json 完全一致。

改了规则/阈值后跑:python3 scripts/check_fixtures.py
预期变化时重建基线:python3 scripts/check_fixtures.py --rebaseline
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from audit_zh import audit_text  # noqa: E402

FIXTURES = Path(__file__).parent.parent / "fixtures"
EXPECTED = FIXTURES / "expected.json"


def assert_ascii_constants() -> None:
    """audit_zh.py 的全角常量区必须是纯 ASCII 源码(防输入管道归一化,见该区注释)。"""
    src = (Path(__file__).parent / "audit_zh.py").read_bytes()
    start = src.index(b"--- FW punct constants")
    end = src.index(b"--- end FW punct constants")
    block = src[start:end]
    bad = [b for b in block if b >= 0x80]
    if bad:
        raise SystemExit(f"FAIL: audit_zh.py 常量区含 {len(bad)} 个非 ASCII 字节——全角字面量混进来了,改用 \\uXXXX 转义")


def snapshot() -> dict:
    out = {}
    for md in sorted(FIXTURES.glob("*.md")):
        r = audit_text(md.read_text(encoding="utf-8"))
        out[md.name] = {
            "status": r["status"],
            "score": r["score"],
            "blocker_count": r["blocker_count"],
            "rules": dict(sorted(Counter(f["rule"] for f in r["findings"]).items())),
            "detail": sorted(f"{f['rule']}:L{f['line']}" for f in r["findings"]),
        }
    return out


def main() -> int:
    assert_ascii_constants()
    current = snapshot()
    if "--rebaseline" in sys.argv:
        EXPECTED.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"rebaselined {len(current)} fixtures -> {EXPECTED}")
        return 0
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    ok = True
    for name in sorted(set(expected) | set(current)):
        if expected.get(name) != current.get(name):
            ok = False
            print(f"MISMATCH {name}")
            print(f"  expected: {json.dumps(expected.get(name), ensure_ascii=False)}")
            print(f"  current : {json.dumps(current.get(name), ensure_ascii=False)}")
    print("fixtures regression:", "PASS" if ok else "FAIL", f"({len(current)} files)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
