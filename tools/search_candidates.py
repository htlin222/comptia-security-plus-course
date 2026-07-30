#!/usr/bin/env python3
"""為 83 個考綱主題各跑幾個 YouTube 搜尋，把原始結果留在 course/data/candidates/。

留原始結果是刻意的：策展最後只會留 3–4 支影片，但「當時看過哪些、為什麼沒選」
沒有留下來的話，之後沒有人能檢查這個選擇合不合理，也沒辦法在影片下架時重挑。

用法：
    python3 tools/search_candidates.py            # 只補還沒有結果的主題
    python3 tools/search_candidates.py --force    # 全部重跑
"""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import yt

ROOT = Path(__file__).resolve().parents[1]
COURSE = Path(os.environ.get("COURSE") or ROOT / "course").resolve()
DATA = COURSE / "data"
OUT = DATA / "candidates"

NOTES = json.loads((DATA / "notes-index.json").read_text())["topics"]
SEED = json.loads((DATA / "curation-seed.json").read_text())["topics"]

# 三個角度分別對應三種 kind：精講找短講解、深講找完整課、實作找操作示範。
# 一個角度只搜一次會讓整門課的影片型態趨同，是策展最常見的失敗模式。
ANGLES = [
    ("core", "{t} explained cybersecurity"),
    ("deep", "{t} CompTIA Security+ SY0-701"),
    ("lab", "{t} demo tutorial hands on"),
]


def queries(slug: str) -> list[tuple[str, str]]:
    topic = NOTES[slug]
    # 標題有時是全稱（Security Information and Event Management），別名才是考場用語
    term = topic["title"]
    out = [(kind, tpl.format(t=term)) for kind, tpl in ANGLES]
    for extra in SEED.get(slug, {}).get("q", []):
        out.append(("core", extra))
    return out


def run(slug: str) -> tuple[str, int]:
    rows, seen = [], set()
    for kind, q in queries(slug):
        try:
            hits = yt.search(q)
        except Exception as e:
            print(f"   ✗ {slug} / {q}: {type(e).__name__}", file=sys.stderr)
            continue
        for r in hits:
            if r["videoId"] in seen:
                continue
            seen.add(r["videoId"])
            rows.append({**r, "angle": kind, "query": q})
    (OUT / f"{slug}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    return slug, len(rows)


def main() -> int:
    force = "--force" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    if "--only" in sys.argv:
        todo = [s for s in sys.argv[sys.argv.index("--only") + 1].split(",") if s in NOTES]
    else:
        todo = [s for s in NOTES if force or not (OUT / f"{s}.json").exists()]
    print(f"搜尋 {len(todo)} 個主題 × {len(ANGLES)} 個角度…")
    if not todo:
        print("已全部有候選，加 --force 可重跑")
        return 0

    total = 0
    with ThreadPoolExecutor(max_workers=5) as pool:
        for slug, n in pool.map(run, todo):
            total += n
            print(f"   {slug}: {n}")
    print(f"\n→ {OUT.relative_to(ROOT)}  共 {total} 筆候選")
    return 0


if __name__ == "__main__":
    sys.exit(main())
