#!/usr/bin/env python3
"""獨立驗證所有標準依據是否真實存在，且標題與識別碼對得上。

資安沒有 PubMed。能被程式重驗的權威來源是這四種，各走各的端點：

    nist   SP／FIPS／CSWP   csrc.nist.gov 出版頁，標題必須含編號
    rfc    RFC 8446         datatracker API，回傳正式標題
    attck  T1566.001        attack.mitre.org 技術頁，標題必須含編號
    cve    CVE-2021-44228   NVD REST API 2.0

不信任任何上游宣稱（含 agent 自稱已驗證），一律重打。捏造一條 NIST 依據比不寫更糟——
讀的人會拿它去跟稽核員解釋。這是最後一道關卡。

用法：
    python3 verify_refs.py           # 驗證並列出不符者
    python3 verify_refs.py --fix     # 額外用 API 回傳值覆寫 title
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("COURSE") or ROOT / "course").resolve() / "data"

CONTACT = os.environ.get("CONTACT_EMAIL", "curate-course@example.com")
UA = f"curate-course/1.0 (mailto:{CONTACT})"

DATATRACKER = "https://datatracker.ietf.org/api/v1/doc/document/rfc{}/?format=json"
NVD = "https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={}"
ATTCK = "https://attack.mitre.org/techniques/{}/"
CROSSREF = "https://api.crossref.org/works/"


def get(url: str, timeout: int = 45) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, res.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def page_title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if not m:
        return ""
    t = re.sub(r"&reg;|&#174;", "", m.group(1))
    t = re.sub(r"\s+", " ", t).strip()
    # "SP 800-207, Zero Trust Architecture | CSRC" -> 去掉站名尾巴
    return t.split(" | ")[0].strip()


# ── 各來源的查核 ────────────────────────────────────────────────────────────
# 每個回傳 (ok, 實際標題或失敗原因)


def check_nist(ref: dict) -> tuple[bool, str]:
    url = ref.get("url") or ""
    if "csrc.nist.gov" not in url and "nvlpubs.nist.gov" not in url:
        return False, "url 必須指向 csrc.nist.gov 的出版頁"
    code, html = get(url)
    if code != 200:
        return False, f"HTTP {code}"
    title = page_title(html)
    if "Page Not Found" in title:
        return False, "CSRC 查無此出版品"
    # 編號必須出現在頁面標題裡，否則就是連到別份文件了
    ident = norm(ref.get("id", ""))
    return (ident in norm(title), title)


def check_rfc(ref: dict) -> tuple[bool, str]:
    num = re.sub(r"\D", "", ref.get("id", ""))
    if not num:
        return False, "RFC 編號解析不出來"
    code, body = get(DATATRACKER.format(num))
    if code != 200 or not body:
        return False, f"HTTP {code}"
    try:
        return True, json.loads(body).get("title", "")
    except json.JSONDecodeError:
        return False, "datatracker 回傳非 JSON"


def check_attck(ref: dict) -> tuple[bool, str]:
    tid = (ref.get("id") or "").strip().upper()
    if not re.fullmatch(r"T\d{4}(\.\d{3})?", tid):
        return False, "ATT&CK technique id 格式不對"
    code, html = get(ATTCK.format(tid.replace(".", "/")))
    if code != 200:
        return False, f"HTTP {code}"
    title = page_title(html)
    return (norm(tid) in norm(title), title)


def check_cve(ref: dict) -> tuple[bool, str]:
    cid = (ref.get("id") or "").strip().upper()
    if not re.fullmatch(r"CVE-\d{4}-\d{4,}", cid):
        return False, "CVE 編號格式不對"
    code, body = get(NVD.format(cid))
    if code != 200 or not body:
        return False, f"HTTP {code}"
    try:
        vulns = json.loads(body).get("vulnerabilities") or []
    except json.JSONDecodeError:
        return False, "NVD 回傳非 JSON"
    if not vulns:
        return False, "NVD 查無此 CVE"
    desc = next(
        (d["value"] for d in vulns[0]["cve"]["descriptions"] if d.get("lang") == "en"), ""
    )
    return True, desc[:120]


def check_doi(ref: dict) -> tuple[bool, str]:
    doi = (ref.get("id") or "").strip()
    code, body = get(CROSSREF + urllib.parse.quote(doi, safe=""))
    if code != 200 or not body:
        return False, f"HTTP {code}"
    try:
        msg = json.loads(body)["message"]
    except (json.JSONDecodeError, KeyError):
        return False, "Crossref 查無此 DOI"
    title = (msg.get("title") or [""])[0]
    return bool(title), title


CHECKS = {
    "nist": check_nist,
    "rfc": check_rfc,
    "attck": check_attck,
    "cve": check_cve,
    "doi": check_doi,
}

BLOBS: dict[Path, dict] = {}


def collect() -> list[tuple[str, str, dict]]:
    """回傳 (檔名, 類別／單元 id, ref dict)。ref 是可就地修改的參照。

    兩層都要掃：`drill-evidence-*.json` 的類別層級與單元層級的實證。
    只驗其中一層等於留了一半的門沒鎖。
    """
    out = []
    sources = [
        ("drill-evidence-*.json", "categories", "id"),
        ("unit-evidence-*.json", "topics", "unit"),
        ("oe-*.json", "conditions", "unit"),  # 舊命名，仍支援
    ]
    for pattern, key, id_field in sources:
        for path in sorted(DATA.glob(pattern)):
            blob = json.loads(path.read_text())
            BLOBS[path] = blob
            for entry in blob.get(key, []):
                if not isinstance(entry, dict):
                    continue
                eid = entry.get(id_field, "?")
                for c in entry.get("citations", []):
                    out.append((path.name, eid, c))
    return out


def main() -> int:
    fix = "--fix" in sys.argv
    rows = collect()
    if not rows:
        print("沒有任何標準依據可驗——實證層是空的")
        return 0

    unknown = [r for r in rows if r[2].get("type") not in CHECKS]
    rows = [r for r in rows if r[2].get("type") in CHECKS]

    by_type: dict[str, int] = {}
    for _, _, c in rows:
        by_type[c["type"]] = by_type.get(c["type"], 0) + 1
    print(
        f"檢查 {len(rows)} 條標準依據（"
        + "、".join(f"{n} 條 {t}" for t, n in sorted(by_type.items()))
        + "）…\n"
    )

    # 每條各打一次外部 API，併發但別把 NVD 打爆（未帶金鑰時速率很緊）
    def run(item):
        _, _, ref = item
        time.sleep(0.35 if ref["type"] == "cve" else 0.05)
        return item, CHECKS[ref["type"]](ref)

    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, rows))

    missing, mismatch = [], []
    for (fname, eid, ref), (ok, actual) in results:
        if not ok:
            missing.append((fname, eid, ref, actual))
            continue
        claimed = ref.get("title", "")
        a, b = norm(actual), norm(claimed)
        if claimed and not (a.startswith(b[:40]) or b.startswith(a[:40]) or b[:40] in a):
            mismatch.append((fname, eid, ref, claimed, actual))
        if fix:
            ref["title"] = actual

    if unknown:
        print(f"✗ 缺少可驗證的 type {len(unknown)} 條（要 {'／'.join(CHECKS)}）：")
        for f, eid, c in unknown[:10]:
            print(f"   {f} · {eid} · {str(c)[:70]}")

    if missing:
        print(f"\n✗ API 查無此條 {len(missing)} 條（極可能是捏造的）：")
        for f, eid, ref, why in missing[:20]:
            print(f"   {f} · {eid} · {ref.get('type')}:{ref.get('id')} — {why}")

    if mismatch:
        print(f"\n⚠ 標題與識別碼不符 {len(mismatch)} 條：")
        for _f, eid, ref, claimed, actual in mismatch[:15]:
            print(f"   {eid} · {ref.get('type')}:{ref.get('id')}")
            print(f"      宣稱: {claimed[:78]}")
            print(f"      實際: {actual[:78]}")

    ok_n = len(rows) - len(missing) - len(mismatch)
    print(f"\n通過 {ok_n} / {len(rows)}（{ok_n / max(len(rows), 1) * 100:.1f}%）")

    if fix:
        for path, blob in BLOBS.items():
            path.write_text(json.dumps(blob, ensure_ascii=False, indent=1))
        print(f"→ --fix：已用 API 回傳值覆寫 {len(BLOBS)} 個檔案的 title")

    return 1 if (missing or unknown) else 0


if __name__ == "__main__":
    sys.exit(main())
