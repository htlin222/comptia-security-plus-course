#!/usr/bin/env python3
"""替課程用到的每支影片抓 YouTube 的真實中繼資料，寫進 course/data/video-meta.json。

策展階段抄下來的長度與觀看數會過期，也可能一開始就抄錯。建置時以這份為準覆寫，
所以首頁的「課程時長」是真的，不是策展資料的宣稱值。

用法：
    python3 tools/fetch_meta.py           # 只補新影片
    python3 tools/fetch_meta.py --force   # 全部重抓（觀看數會變，偶爾跑一次）
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COURSE = Path(os.environ.get("COURSE") or ROOT / "course").resolve()
DATA = COURSE / "data"
OUT = DATA / "video-meta.json"

KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
CTX = {"client": {"clientName": "WEB", "clientVersion": "2.20240101.00.00", "hl": "en", "gl": "US"}}


def fetch(vid: str) -> tuple[str, dict]:
    body = {"context": CTX, "videoId": vid}
    try:
        req = urllib.request.Request(
            f"https://www.youtube.com/youtubei/v1/player?key={KEY}&prettyPrint=false",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "User-Agent": UA},
        )
        with urllib.request.urlopen(req, timeout=45) as res:
            blob = json.loads(res.read())
    except Exception as e:
        return vid, {"status": type(e).__name__}

    vd = blob.get("videoDetails") or {}
    secs = vd.get("lengthSeconds")
    if not secs or not str(secs).isdigit():
        # 影片被刪、設為私人或地區封鎖時就沒有 videoDetails
        reason = (blob.get("playabilityStatus") or {}).get("reason", "NO_DETAILS")
        return vid, {"status": reason}
    return vid, {
        "status": "OK",
        "seconds": int(secs),
        "views": int(vd.get("viewCount") or 0),
        "channel": vd.get("author") or "",
        "title": vd.get("title") or "",
        # 上課模式是內嵌播放的。不允許嵌入的影片在課程裡等於播不出來，
        # 所以嵌入權限跟長度一樣是選片條件，不是事後才發現的問題。
        "embeddable": embeddable(vid),
    }


OEMBED = "https://www.youtube.com/oembed?url={}&format=json"


def embeddable(vid: str) -> bool:
    """oEmbed 對不允許嵌入的影片回 401，是唯一可靠的判斷方式。"""
    url = OEMBED.format(
        urllib.parse.quote(f"https://www.youtube.com/watch?v={vid}", safe="")
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30):
            return True
    except urllib.error.HTTPError:
        return False
    except Exception:
        return True  # 網路抖動不該讓一支好影片被永久排除


def video_ids() -> list[str]:
    ids, seen = [], set()
    for path in sorted(DATA.glob("ch*.json")):
        for m in re.finditer(r"youtube\.com/watch\?v=([\w-]{11})", path.read_text()):
            if m.group(1) not in seen:
                seen.add(m.group(1))
                ids.append(m.group(1))
    return ids


def main() -> int:
    force = "--force" in sys.argv
    have = json.loads(OUT.read_text()) if OUT.exists() and not force else {}
    todo = [v for v in video_ids() if v not in have]
    print(f"抓 {len(todo)} 支影片的中繼資料（已有 {len(have)} 支）…")

    if todo:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for vid, meta in pool.map(fetch, todo):
                have[vid] = meta

    OUT.write_text(json.dumps(have, ensure_ascii=False, indent=1, sort_keys=True))
    ok = sum(1 for m in have.values() if m.get("status") == "OK")
    print(f"→ {OUT.relative_to(ROOT)}  {ok}/{len(have)} 取得成功")
    bad = {v: m["status"] for v, m in have.items() if m.get("status") != "OK"}
    if bad:
        print(f"\n✗ {len(bad)} 支拿不到中繼資料，多半已下架或設為私人：")
        for v, s in list(bad.items())[:20]:
            print(f"   https://youtu.be/{v} — {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
