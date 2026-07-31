#!/usr/bin/env python3
"""抓課程用到的每支影片的英文字幕，存進 .cache/captions/（不進版控）。

**字幕不進版控。** 字幕是原頻道創作者的著作，整份存進 repo 等於轉載。
這裡只把它當建置時的暫存輸入，用來寫繁中導讀；進版控的只有兩樣東西：

    course/data/caption-index.json   每支影片有沒有字幕、人工還是自動、多少字（中繼資料）
    course/data/video-notes.json     人寫的繁中導讀（原創內容，不是逐字稿的改寫）

優先取人工字幕，沒有才退而取自動字幕——自動字幕會把專有名詞聽錯
（SIEM 變 seem、SAML 變 samul），拿它當導讀依據要多留意。

需要 yt-dlp（timedtext 端點現在需要對應的 session，直接打會拿到空回應）。

用法：
    python3 tools/fetch_captions.py              # 只補還沒抓過的
    python3 tools/fetch_captions.py --lessons    # 只抓 83 支主課
    python3 tools/fetch_captions.py --force      # 全部重抓
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COURSE = Path(os.environ.get("COURSE") or ROOT / "course").resolve()
DATA = COURSE / "data"
CACHE = ROOT / ".cache" / "captions"
INDEX = DATA / "caption-index.json"

VID = re.compile(r"youtube\.com/watch\?v=([\w-]{11})")


def videos(lessons_only: bool) -> list[tuple[str, str]]:
    """回傳 (videoId, 角色)。角色是 lesson / drill，決定優先順序。"""
    out, seen = [], set()
    for path in sorted(DATA.glob("ch*.json")):
        for unit in json.loads(path.read_text())["units"]:
            items = [("lesson", unit.get("lesson") or {})]
            if not lessons_only:
                items += [("drill", d) for d in unit.get("drills") or []]
            for role, v in items:
                m = VID.search(v.get("url") or "")
                if m and m.group(1) not in seen:
                    seen.add(m.group(1))
                    out.append((m.group(1), role))
    return out


def json3_to_text(path: Path) -> str:
    """json3 的字幕段落攤平成連續文字。時間軸對寫導讀沒用，丟掉。"""
    blob = json.loads(path.read_text(errors="replace"))
    parts = []
    for ev in blob.get("events") or []:
        for seg in ev.get("segs") or []:
            parts.append(seg.get("utf8", ""))
    text = re.sub(r"\s+", " ", "".join(parts))
    # 自動字幕常見的填充標記
    return re.sub(r"\[(Music|Applause|Laughter|__)\]", "", text, flags=re.I).strip()


def fetch(item: tuple[str, str]) -> tuple[str, dict]:
    vid, role = item
    url = f"https://www.youtube.com/watch?v={vid}"

    # 兩輪：先要人工字幕，沒有才收自動字幕。分開跑才知道拿到的是哪一種。
    for source, flag in (("manual", "--write-subs"), ("auto", "--write-auto-subs")):
        with tempfile.TemporaryDirectory() as tmp:
            cmd = [
                "yt-dlp", "--skip-download", "--no-warnings", "--no-progress",
                flag, "--sub-langs", "en.*", "--sub-format", "json3",
                "-o", f"{tmp}/%(id)s.%(ext)s", url,
            ]
            try:
                subprocess.run(cmd, capture_output=True, timeout=180, check=False)
            except subprocess.TimeoutExpired:
                return vid, {"source": "none", "reason": "yt-dlp 逾時", "role": role}

            files = sorted(Path(tmp).glob("*.json3"), key=lambda p: -p.stat().st_size)
            if not files:
                continue
            text = json3_to_text(files[0])
            if not text:
                continue
            CACHE.mkdir(parents=True, exist_ok=True)
            (CACHE / f"{vid}.txt").write_text(text)
            return vid, {"source": source, "words": len(text.split()), "role": role}

    return vid, {"source": "none", "reason": "這支影片沒有英文字幕", "role": role}


def main() -> int:
    if not shutil.which("yt-dlp"):
        print("✗ 找不到 yt-dlp。timedtext 端點需要對應的 session，直接打會拿到空回應。", file=sys.stderr)
        print("  安裝：uv tool install yt-dlp", file=sys.stderr)
        return 1

    force = "--force" in sys.argv
    todo_all = videos("--lessons" in sys.argv)
    have = json.loads(INDEX.read_text())["videos"] if INDEX.exists() and not force else {}
    todo = [(v, r) for v, r in todo_all if v not in have or not (CACHE / f"{v}.txt").exists()]

    print(f"抓 {len(todo)} 支影片的字幕（已有 {len(have)} 支）…")
    if todo:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for i, (vid, meta) in enumerate(pool.map(fetch, todo), 1):
                have[vid] = meta
                mark = {"manual": "✓", "auto": "~", "none": "✗"}[meta["source"]]
                print(f"   [{i}/{len(todo)}] {mark} {vid} {meta.get('words', meta.get('reason', ''))}")

    by = {"manual": 0, "auto": 0, "none": 0}
    for m in have.values():
        by[m["source"]] += 1
    INDEX.write_text(
        json.dumps(
            {
                "_readme": [
                    "只有中繼資料。字幕本身在 .cache/captions/，不進版控——那是原頻道的著作。",
                    "source=manual 是創作者自己上的字幕，auto 是 YouTube 自動聽打（專有名詞常錯）。",
                ],
                "counts": by,
                "videos": dict(sorted(have.items())),
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    print(f"\n→ {INDEX.relative_to(ROOT)}")
    print(f"   人工字幕 {by['manual']} · 自動字幕 {by['auto']} · 沒有字幕 {by['none']}")
    total = sum(m.get("words", 0) for m in have.values())
    print(f"   快取 {CACHE.relative_to(ROOT)}／共 {total:,} 字（不進版控）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
