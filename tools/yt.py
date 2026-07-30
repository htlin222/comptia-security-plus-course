#!/usr/bin/env python3
"""YouTube innertube 用戶端：搜尋與播放清單列舉。

存在的理由只有一個——讓「video ID 取自實際搜尋結果」這條鐵則可以被重跑驗證。
策展腳本從這裡拿候選，不從任何人的記憶（含模型自己的）拿。

沒有相依套件，只用標準庫；沒有 API 金鑰，走的是網頁前端自己在用的公開端點。
"""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.parse
import urllib.request

KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
CTX = {"client": {"clientName": "WEB", "clientVersion": "2.20240101.00.00", "hl": "en", "gl": "US"}}
VIDEOS_ONLY = "EgIQAQ%3D%3D"  # 濾掉頻道與播放清單，只回影片


def _post(endpoint: str, body: dict, retries: int = 3) -> dict:
    url = f"https://www.youtube.com/youtubei/v1/{endpoint}?key={KEY}&prettyPrint=false"
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode(),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": UA,
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            with urllib.request.urlopen(req, timeout=60) as res:
                return json.loads(res.read())
        except Exception as e:  # 逾時與 5xx 都值得重試，別讓一次抖動毀掉整批
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last if last else RuntimeError("unreachable")


def find(node, key: str, out: list | None = None) -> list:
    out = [] if out is None else out
    if isinstance(node, dict):
        if key in node:
            out.append(node[key])
        for v in node.values():
            find(v, key, out)
    elif isinstance(node, list):
        for v in node:
            find(v, key, out)
    return out


def text_of(node) -> str:
    """viewModel 用 {content}，舊 renderer 用 {runs} 或 {simpleText}。"""
    if isinstance(node, dict):
        if isinstance(node.get("content"), str):
            return node["content"]
        if node.get("runs"):
            return "".join(r.get("text", "") for r in node["runs"])
        if isinstance(node.get("simpleText"), str):
            return node["simpleText"]
    return ""


def clock_to_seconds(clock: str) -> int:
    if not clock or ":" not in clock:
        return 0
    n = 0
    for p in clock.split(":"):
        if not p.isdigit():
            return 0
        n = n * 60 + int(p)
    return n


def parse_views(s: str) -> int:
    """'1.2M views' / '12,345 views' -> int。解析不出來回 0。"""
    m = re.match(r"([\d.,]+)\s*([KMB])?", (s or "").strip())
    if not m:
        return 0
    try:
        n = float(m.group(1).replace(",", ""))
    except ValueError:
        return 0
    return int(n * {"K": 1e3, "M": 1e6, "B": 1e9}.get(m.group(2) or "", 1))


def search(query: str) -> list[dict]:
    blob = _post("search", {"context": CTX, "query": query, "params": VIDEOS_ONLY})
    rows, seen = [], set()
    for vr in find(blob, "videoRenderer"):
        vid = vr.get("videoId")
        length = (vr.get("lengthText") or {}).get("simpleText", "")
        if not vid or vid in seen or not length:  # 沒有長度的是直播或 Shorts
            continue
        seen.add(vid)
        rows.append(
            {
                "videoId": vid,
                "title": text_of(vr.get("title")),
                "channel": text_of(vr.get("ownerText") or vr.get("longBylineText")),
                "duration": length,
                "seconds": clock_to_seconds(length),
                "views": parse_views(text_of(vr.get("viewCountText"))),
                "published": text_of(vr.get("publishedTimeText")),
            }
        )
    return rows


def _is_comments_token(token: str) -> bool:
    """同一份回應裡也有留言區的 continuation，跟去會離開影片清單。"""
    raw = urllib.parse.unquote(token)
    try:
        return b"comment" in base64.b64decode(raw + "=" * (-len(raw) % 4), validate=False)
    except Exception:
        return False


def playlist(playlist_id: str, max_pages: int = 20) -> list[dict]:
    rows, seen, used = [], set(), set()

    def collect(blob):
        for lv in find(blob, "lockupViewModel"):
            vid = lv.get("contentId")
            if not vid or len(vid) != 11 or vid in seen:
                continue
            meta = (lv.get("metadata") or {}).get("lockupMetadataViewModel") or {}
            length = ""
            for badge in find(lv.get("contentImage") or {}, "thumbnailBadgeViewModel"):
                if ":" in badge.get("text", ""):
                    length = badge["text"]
                    break
            seen.add(vid)
            rows.append(
                {
                    "videoId": vid,
                    "title": text_of(meta.get("title")),
                    "duration": length,
                    "seconds": clock_to_seconds(length),
                }
            )

    blob = _post("browse", {"context": CTX, "browseId": "VL" + playlist_id})
    collect(blob)
    for _ in range(max_pages):
        tokens = [
            t
            for c in find(blob, "continuationItemRenderer")
            if (t := (c.get("continuationEndpoint", {}).get("continuationCommand") or {}).get("token"))
            and not _is_comments_token(t)
            and t not in used
        ]
        if not tokens:
            break
        used.add(tokens[0])
        before = len(rows)
        blob = _post("browse", {"context": CTX, "continuation": tokens[0]})
        collect(blob)
        if len(rows) == before:
            break
        time.sleep(0.4)
    return rows
