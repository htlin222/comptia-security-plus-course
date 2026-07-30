#!/usr/bin/env python3
"""產生單元層級的標準依據 course/data/unit-evidence-2.json。

刻意只放能從已驗證資料推導出來的欄位：

    exam_scope      考綱編號，取自 Professor Messer 影片標題裡的官方編號
    standard_basis  該主題所屬家族的主要標準文件，取自 drill-evidence
    citations       同上，帶 type/url，make verify 會逐條重打 API

不自動生成散文式的摘要。填不出來的欄位就留空——把版面填滿但內容含糊，
比空著更糟：讀的人會以為那格已經有人查證過了。

用法：
    python3 tools/build_evidence.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(__file__).resolve().parents[1]
COURSE = Path(os.environ.get("COURSE") or ROOT / "course").resolve()
DATA = COURSE / "data"
OUT = DATA / "unit-evidence-2.json"

CFG = json.loads((COURSE / "course.config.json").read_text())
NOTES = json.loads((DATA / "notes-index.json").read_text())["topics"]
SEED = json.loads((DATA / "curation-seed.json").read_text())["topics"]
MESSER = {v["videoId"]: v for v in json.loads((DATA / "messer-playlist.json").read_text())}
FAMILIES = {c["id"]: c for c in json.loads((DATA / "drill-evidence-1.json").read_text())["categories"]}

sys.path.insert(0, str(COURSE))
from taxonomy import families  # noqa: E402

OBJ = re.compile(r"-\s*([1-5]\.\d)\s*$")


def objective(slug: str) -> str:
    """考綱編號。Messer 把它寫在標題結尾，主課沒有的話退而取延伸影片的。"""
    seed = SEED.get(slug, {})
    for vid in [seed.get("lesson"), *seed.get("messer", [])]:
        m = OBJ.search(MESSER.get(vid or "", {}).get("title", ""))
        if m:
            return m.group(1)
    # Messer 沒有單獨影片的主題，編號在種子檔手寫（來源是官方課程索引）
    return seed.get("objective", "")


def family_of(slug: str) -> str | None:
    note = NOTES[slug]
    probe = {
        "name": f"{slug.replace('-', ' ')} {note['title']}",
        "why": " ".join(c["label"] for c in note["concepts"][:8]),
    }
    return families.classify(probe)


def main() -> int:
    chapters = {c["source"]: c["code"] for c in CFG["chapters"]}
    unit_of: dict[str, str] = {}
    for src in chapters:
        for u in json.loads((DATA / f"{src}.json").read_text())["units"]:
            unit_of[u["note"]["slug"]] = u["id"]

    topics, no_obj, no_fam = [], [], []
    for slug in sorted(NOTES, key=lambda s: (NOTES[s]["domain"], s)):
        uid = unit_of.get(slug)
        if not uid:
            continue
        obj, fam = objective(slug), family_of(slug)
        if not obj:
            no_obj.append(slug)
        if not fam:
            no_fam.append(slug)

        entry: dict = {
            "unit": uid,
            "name": NOTES[slug]["title"],
            "evidence_grade": FAMILIES[fam]["evidence_grade"] if fam else "advisory",
        }
        if obj:
            entry["exam_scope"] = f"SY0-701 考綱 {obj}"
        if fam:
            f = FAMILIES[fam]
            primary = f["citations"][0]
            entry["standard_basis"] = f"{f['name']}：{primary['id']}《{primary['title']}》"
            entry["citations"] = f["citations"]
        topics.append(entry)

    OUT.write_text(
        json.dumps(
            {
                "_readme": [
                    "由 tools/build_evidence.py 產生，不要手改——重跑會蓋掉。",
                    "要補人工撰寫的欄位（common_trap、caveats 之類）請放到 unit-evidence-1.json，",
                    "同一個 unit id 會以後讀到的檔為準。",
                ],
                "topics": topics,
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    print(f"→ {OUT.relative_to(ROOT)}  {len(topics)} 個單元")
    print(f"   有考綱編號 {len(topics) - len(no_obj)} · 有標準家族 {len(topics) - len(no_fam)}")
    if no_obj:
        print(f"   ⚠ 沒有考綱編號 {len(no_obj)}：{'、'.join(no_obj[:8])}")
    if no_fam:
        print(f"   ⚠ 歸不到標準家族 {len(no_fam)}：{'、'.join(no_fam[:8])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
