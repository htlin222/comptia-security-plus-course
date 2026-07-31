#!/usr/bin/env python3
"""把快取字幕壓成精簡檢視，供人撰寫繁中導讀時參考。

不是要重現逐字稿——寫導讀需要知道的是「這支影片的結構與重點擺在哪」，
不是每一句話。所以取開頭（主題與範圍）加上均勻取樣的幾段（骨架），
其餘丟掉。輸出只印到終端機，不寫檔。

用法：
    python3 tools/caption_digest.py --role lesson --skip 0 --take 8
    python3 tools/caption_digest.py --ids zC_Pndpg8-c,SBcDGb9l6yo
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COURSE = Path(os.environ.get("COURSE") or ROOT / "course").resolve()
DATA = COURSE / "data"
CACHE = ROOT / ".cache" / "captions"

INDEX = json.loads((DATA / "caption-index.json").read_text())["videos"]
NOTES_PATH = DATA / "video-notes.json"
DONE = set(json.loads(NOTES_PATH.read_text())["videos"]) if NOTES_PATH.exists() else set()

HEAD_WORDS = 150   # 開頭：主題、範圍、講者怎麼定調
WINDOW = 65        # 中段取樣窗大小
WINDOWS = 3        # 取幾個窗


def meta() -> dict:
    """videoId -> {title, channel, duration, unit, role}。導讀要對得上是哪一格。"""
    out = {}
    for path in sorted(DATA.glob("ch*.json")):
        for unit in json.loads(path.read_text())["units"]:
            pairs = [("lesson", unit.get("lesson") or {})]
            pairs += [("drill", d) for d in unit.get("drills") or []]
            for role, v in pairs:
                url = v.get("url") or ""
                if "watch?v=" not in url:
                    continue
                vid = url.split("watch?v=")[1][:11]
                out.setdefault(
                    vid,
                    {
                        "title": v.get("title") or v.get("name") or "",
                        "channel": v.get("channel") or "",
                        "duration": v.get("duration") or "",
                        "unit": unit["name"],
                        "role": role,
                    },
                )
    return out


def digest(text: str) -> str:
    words = text.split()
    if len(words) <= HEAD_WORDS + WINDOW * WINDOWS:
        return " ".join(words)

    parts = [" ".join(words[:HEAD_WORDS])]
    rest = words[HEAD_WORDS:]
    step = len(rest) // (WINDOWS + 1)
    for i in range(1, WINDOWS + 1):
        start = step * i
        parts.append(" ".join(rest[start : start + WINDOW]))
    return "\n  […]\n".join(parts)


def main() -> int:
    args = sys.argv
    M = meta()

    if "--ids" in args:
        ids = args[args.index("--ids") + 1].split(",")
    else:
        role = args[args.index("--role") + 1] if "--role" in args else None
        skip = int(args[args.index("--skip") + 1]) if "--skip" in args else 0
        take = int(args[args.index("--take") + 1]) if "--take" in args else 8
        pool = [
            v
            for v, m in INDEX.items()
            if (not role or m.get("role") == role) and v not in DONE
        ]
        ids = sorted(pool)[skip : skip + take]

    print(f"# {len(ids)} 支待寫（已完成 {len(DONE)}）\n")
    for vid in ids:
        m = M.get(vid, {})
        cap = INDEX.get(vid, {})
        path = CACHE / f"{vid}.txt"
        if not path.exists():
            print(f"## {vid} — 快取裡沒有字幕，先跑 fetch_captions.py\n")
            continue
        flag = "自動字幕（專有名詞可能聽錯）" if cap.get("source") == "auto" else "人工字幕"
        print(f"## {vid} · {m.get('unit', '?')} · {m.get('role', '?')}")
        print(f"   {m.get('channel', '')} — {m.get('title', '')} · {m.get('duration', '')} · {flag}")
        print(f"  {digest(path.read_text())}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
