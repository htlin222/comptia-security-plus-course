#!/usr/bin/env python3
"""把 NIST 文件編號解析成 csrc.nist.gov 上真實存在的出版頁網址與正式標題。

CSRC 的網址規則不只一種（800-53r5 是 /800/53/r5/，800-63b 是 /800/63/b/，
FIPS 又是另一套），憑印象寫網址十之八九會連到 404 或別份文件。這裡直接試打，
拿 200 且標題含編號的那一個。

用法：
    python3 tools/resolve_nist.py "SP 800-53r5" "SP 800-63b" "FIPS 197"
    python3 tools/resolve_nist.py --file ids.txt
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA = "curate-course/1.0"


def get(url: str) -> tuple[int, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.status, res.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def title_of(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    t = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    return t.split(" | ")[0].strip()


def candidates(ident: str) -> list[str]:
    """從編號生出所有可能的 CSRC 路徑。寧可多試幾個，也不要寫死一種規則。"""
    s = ident.strip().lower().replace("rev.", "r").replace("rev ", "r").replace(" ", "")
    out: list[str] = []

    m = re.match(r"sp(\d{3})-(\d+)([a-z])?(?:r(\d+))?", s)
    if m:
        series, num, suffix, rev = m.groups()
        stem = f"sp/{series}/{num}"
        tails = []
        if suffix and rev:
            tails += [f"{suffix}/r{rev}", f"{suffix}r{rev}"]
        elif suffix:
            tails += [suffix]
        elif rev:
            tails += [f"r{rev}"]
        else:
            tails += [""]
        for t in tails:
            base = f"{stem}/{t}".rstrip("/")
            # upd 是 CSRC 對「原版之後又出修訂」的路徑，常見於 800-63
            out += [f"{base}/final", f"{base}/upd2/final", f"{base}/upd1/final"]
        # 沒有修訂號時也試試最新修訂
        if not rev:
            out += [f"{stem}/r{n}/final" for n in range(5, 0, -1)]

    m = re.match(r"fips(\d+)-?(\d+)?", s)
    if m:
        num, rev = m.groups()
        out += [f"fips/{num}/{rev}/final" if rev else f"fips/{num}/final"]
        if rev:
            out += [f"fips/{num}-{rev}/final"]

    m = re.match(r"cswp(\d+)", s)
    if m:
        out += [f"cswp/{m.group(1)}/final", f"cswp/{m.group(1)}/ipd"]

    return [f"https://csrc.nist.gov/pubs/{p}" for p in dict.fromkeys(out)]


def resolve(ident: str) -> tuple[str, str | None, str]:
    for url in candidates(ident):
        code, html = get(url)
        if code != 200:
            continue
        title = title_of(html)
        if "Page Not Found" in title:
            continue
        # CSRC 標題寫「SP 800-53 Rev. 5」，編號習慣寫「SP 800-53r5」，先對齊再比
        def key_of(s: str) -> str:
            s = re.sub(r"rev\.?\s*", "r", s.lower())
            return re.sub(r"[^a-z0-9]", "", s)

        if key_of(ident) in key_of(title):
            return ident, url, title
    return ident, None, "查無 — 到 https://csrc.nist.gov/publications 手動找，別亂寫網址"


def main() -> int:
    if "--file" in sys.argv:
        ids = [x.strip() for x in Path(sys.argv[sys.argv.index("--file") + 1]).read_text().splitlines() if x.strip()]
    else:
        ids = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not ids:
        print(__doc__)
        return 2

    with ThreadPoolExecutor(max_workers=4) as pool:
        for ident, url, title in pool.map(resolve, ids):
            mark = "✓" if url else "✗"
            print(f"{mark} {ident:22} {url or ''}")
            print(f"    {title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
