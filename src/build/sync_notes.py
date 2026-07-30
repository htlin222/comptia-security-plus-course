#!/usr/bin/env python3
"""把 CompTIA-security-plus-notes 的 topic 頁抽成 course/data/notes-index.json。

這門課是那份筆記的影片伴讀，所以單元名稱、ELI5、概念清單、考點提示與練習題數
全部從筆記本身抽出來，不手抄一份——手抄的那一刻兩邊就開始漂移。

抓的是 GitHub 的 tarball（不需要 git、不需要權杖），所以 CI 也能跑。

用法：
    python3 sync_notes.py            # 抓遠端 tarball
    python3 sync_notes.py --local /path/to/notes   # 用本機 clone，離線可跑
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COURSE = Path(os.environ.get("COURSE") or ROOT / "course").resolve()
OUT = COURSE / "data" / "notes-index.json"

CFG = json.loads((COURSE / "course.config.json").read_text())
NOTES = CFG["notes"]
REPO, BRANCH = NOTES["repo"], NOTES["branch"]
SITE = NOTES["site"].rstrip("/")
TARBALL = f"https://codeload.github.com/{REPO}/tar.gz/refs/heads/{BRANCH}"

UA = "curate-course/1.0 (+https://github.com/htlin222/curate-course)"

# domain 目錄 -> 章節碼。筆記的目錄名就是唯一事實來源，換名字這裡會直接查無。
DOMAIN_DIR = re.compile(r"^domain-(\d)-")


def fetch_tree() -> dict[str, str]:
    """回傳 {relative path under content/: markdown 內容}。"""
    local = None
    if "--local" in sys.argv:
        local = Path(sys.argv[sys.argv.index("--local") + 1])

    files: dict[str, str] = {}
    if local:
        base = local / "content"
        for p in base.rglob("*.md"):
            files[str(p.relative_to(base))] = p.read_text(errors="replace")
        return files

    req = urllib.request.Request(TARBALL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as res:
        blob = res.read()
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for m in tar.getmembers():
            # <repo>-<branch>/content/…
            parts = m.name.split("/", 2)
            if len(parts) < 3 or parts[1] != "content" or not m.name.endswith(".md"):
                continue
            f = tar.extractfile(m)
            if f:
                files[parts[2]] = f.read().decode("utf-8", errors="replace")
    return files


FM = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def frontmatter(text: str) -> dict:
    """夠用的 YAML 子集解析：純量、清單、巢狀兩層。避免為了 3 個欄位裝 pyyaml。"""
    m = FM.match(text)
    if not m:
        return {}
    out: dict = {}
    key = None
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - ") and key:
            out.setdefault(key, []).append(line[4:].strip().strip('"').strip("'"))
            continue
        if ":" in line and not line.startswith(" "):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            out[key] = val if val else []
    return out


def body(text: str) -> str:
    m = FM.match(text)
    return text[m.end() :] if m else text


def section(md: str, heading: str) -> str:
    """抓 '## <heading>' 到下一個 '## ' 之間的內容。"""
    m = re.search(rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", md, re.S | re.M)
    return m.group(1).strip() if m else ""


def strip_md(s: str) -> str:
    """把行內 markdown 清成純文字，wikilink 取顯示文字。"""
    s = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", s)
    s = re.sub(r"\[\[([^\]]+)\]\]", r"\1", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"[*_`]", "", s)
    return re.sub(r"\s+", " ", s).strip()


HAN = re.compile(r"[一-鿿]")


def eli5(md: str) -> tuple[str, str]:
    """回傳 (英文, 繁中)。

    筆記裡有兩種排版：繁中版巢狀在英文版底下（zero-trust），或兩個 callout 並列
    （cia-triad）。只認其中一種會漏掉四成的主題，所以一律先把所有 eli5 區塊攤平，
    再用有沒有漢字來分英中——標題文案不見得每篇都寫「繁體中文版」。
    """
    def depth_of(line: str) -> int:
        """引言層級。筆記裡巢狀寫成 '> > '（中間有空白），數 '>' 才可靠。"""
        m = re.match(r"^((?:>\s*)+)", line)
        return m.group(1).count(">") if m else 0

    # 逐行掃而不是 finditer：外層 callout 的比對會把巢狀的內層一起吃掉，
    # finditer 從上一個 match 的結尾接著找，內層就永遠掃不到。
    lines_in = md.splitlines()
    heads = [i for i, ln in enumerate(lines_in) if re.match(r"^(?:>\s*)+\[!eli5\]", ln)]

    blocks: list[str] = []
    for i in heads:
        depth = depth_of(lines_in[i])
        lines = []
        for raw in lines_in[i + 1 :]:
            d = depth_of(raw)
            if d < depth:  # 離開這個 callout
                break
            if d > depth and "[!" in raw:  # 巢狀的下一層，交給它自己那一輪
                break
            lines.append(re.sub(rf"^(?:>\s*){{1,{depth}}}", "", raw))
        blocks.append("\n".join(lines))

    en = zh = ""
    for block in blocks:
        # ascii 圖與巢狀 callout 都不是散文，切掉
        prose = strip_md(block.split("```")[0])
        if not prose:
            continue
        if HAN.search(prose):
            zh = zh or prose
        else:
            en = en or prose
    return en, zh


WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def concepts(md: str) -> list[dict]:
    """Key Concepts 段落裡出現的 wikilink，就是這個 topic 的下層概念。"""
    out, seen = [], set()
    for slug, label in WIKILINK.findall(section(md, "Key Concepts")):
        slug = slug.strip()
        if slug in seen:
            continue
        seen.add(slug)
        out.append({"slug": slug, "label": (label or slug.replace("-", " ")).strip()})
    return out


def tips(md: str) -> list[str]:
    """Exam Tips 底下每個 callout 的內文，是最適合拿來當自我檢核的材料。"""
    out = []
    for m in re.finditer(r"^> \[!tip\][^\n]*\n((?:^>.*\n?)+)", section(md, "Exam Tips"), re.M):
        text = strip_md(" ".join(re.sub(r"^>\s?", "", x) for x in m.group(1).splitlines()))
        if text:
            out.append(text)
    return out


def question_count(md: str) -> int:
    m = re.search(r"\[!qbank\][^\n]*?\((\d+)\s+Questions?\)", md)
    if m:
        return int(m.group(1))
    return len(re.findall(r"^>\s\*\*Q\d+\.", md, re.M))


def main() -> int:
    files = fetch_tree()
    if not files:
        print("✗ 抓不到筆記內容", file=sys.stderr)
        return 1

    cases = {
        Path(p).stem.removeprefix("case-")
        for p in files
        if "/cases/" in p
    }

    topics: dict[str, dict] = {}
    for path, text in sorted(files.items()):
        parts = path.split("/")
        # 只要 domain 目錄下第一層的 topic 頁；concepts/ 與 cases/ 是下層資料
        if len(parts) != 2 or parts[1] in ("index.md",):
            continue
        dm = DOMAIN_DIR.match(parts[0])
        if not dm:
            continue

        slug = Path(parts[1]).stem
        fm = frontmatter(text)
        md = body(text)
        tags = fm.get("tags") or []
        weight = next((t.split("/")[1] for t in tags if t.startswith("weight/")), "")
        en, zh = eli5(md)

        topics[slug] = {
            "slug": slug,
            "title": (fm.get("title") or slug).strip(),
            "description": (fm.get("description") or "").strip(),
            "domain": int(dm.group(1)),
            "dir": parts[0],
            "weight": weight,
            "aliases": fm.get("aliases") or [],
            "eli5_en": en,
            "eli5_zh": zh,
            "concepts": concepts(md),
            "tips": tips(md),
            "questions": question_count(text),
            "url": f"{SITE}/{parts[0]}/{slug}",
            "case_url": f"{SITE}/{parts[0]}/cases/case-{slug}" if slug in cases else None,
        }

    payload = {
        "source": {"repo": REPO, "branch": BRANCH, "site": SITE},
        "counts": {
            "topics": len(topics),
            "concepts": sum(len(t["concepts"]) for t in topics.values()),
            "questions": sum(t["questions"] for t in topics.values()),
            "cases": sum(1 for t in topics.values() if t["case_url"]),
        },
        "topics": topics,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1))

    c = payload["counts"]
    print(f"→ {OUT.relative_to(ROOT) if OUT.is_relative_to(ROOT) else OUT}")
    print(
        f"   topic {c['topics']} · 概念連結 {c['concepts']} · 練習題 {c['questions']} · 案例 {c['cases']}"
    )
    by_domain: dict[int, int] = {}
    for t in topics.values():
        by_domain[t["domain"]] = by_domain.get(t["domain"], 0) + 1
    print("   " + " / ".join(f"D{k} {v}" for k, v in sorted(by_domain.items())))

    missing = [s for s, t in topics.items() if not t["eli5_zh"]]
    if missing:
        print(f"   ⚠ 缺繁中 ELI5 {len(missing)} 個：{'、'.join(missing[:6])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
