#!/usr/bin/env python3
"""把 notes-index + curation-seed + candidates 組成各章的 ch*.json。

選片規則刻意寫成確定性的：同樣的候選永遠選出同樣的影片，任何人重跑都能複製，
也才能在影片下架時只換那一格而不動其他。判斷仍是人下的——權重與排除規則寫在這裡，
挑不出合格影片時寧可留空並註記，不用「大致相關」的填滿版面。

用法：
    python3 tools/assemble.py            # 產生 ch1..ch5.json
    python3 tools/assemble.py --report   # 只印選片結果，不寫檔
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COURSE = Path(os.environ.get("COURSE") or ROOT / "course").resolve()
DATA = COURSE / "data"
CAND = DATA / "candidates"

CFG = json.loads((COURSE / "course.config.json").read_text())
NOTES = json.loads((DATA / "notes-index.json").read_text())["topics"]
SEED = json.loads((DATA / "curation-seed.json").read_text())["topics"]
COPY = json.loads((DATA / "unit-copy.json").read_text())["units"]
MESSER = {v["videoId"]: v for v in json.loads((DATA / "messer-playlist.json").read_text())}
# 第一輪組裝時還沒有中繼資料，查不到的一律放行；跑過 fetch_meta 再組一次就會生效
META = json.loads((DATA / "video-meta.json").read_text()) if (DATA / "video-meta.json").exists() else {}

CHAPTERS = {c["code"]: c for c in CFG["chapters"]}
AUDIT = CFG["audit"]


def clock(s: str) -> int:
    n = 0
    for p in (s or "0").split(":"):
        n = n * 60 + int(p)
    return n


DRILL_MIN = clock(AUDIT["duration"]["drill"]["min"])
DRILL_MAX = clock(AUDIT["duration"]["drill"]["max"])
MIN_VIEWS = AUDIT["minViews"]

# 選片時明顯要避開的東西：考古題背誦、整包 N 小時的懶人包、付費導流、舊版考綱
BAD_TITLE = re.compile(
    r"\b(dump|braindump|exam questions|actual exam|practice test|full course in one|"
    r"in one video|passed my exam|my exam experience|free voucher|discount code|"
    r"sy0-?[56]01|sy0-?401)\b",
    re.I,
)

# 關鍵字撞名是這種搜尋最大的失敗來源：AAA 撞到「AAA 遊戲」、automation 撞到
# Zapier 教學、authentication 撞到 FastAPI 教學。所以要求候選必須帶資安／IT 的
# 脈絡詞，或出自可信頻道；兩者都沒有就直接淘汰，不管它多熱門。
SECURITY_CONTEXT = re.compile(
    r"\b(security|secure|cyber|infosec|comptia|sy0|cissp|attack|attacker|threat|"
    r"vulnerab|exploit|hack|hacker|malware|ransomware|phishing|forensic|incident|"
    r"encrypt|decrypt|cryptograph|firewall|vpn|pki|certificate|tls|ssl|siem|soar|"
    r"soc|edr|xdr|dlp|iam|mfa|zero.trust|pentest|penetration|compliance|gdpr|hipaa|"
    r"pci|nist|iso.?27001|risk|audit|governance|privacy|network|protocol|authentication|"
    r"authorization|access control|identity|log|backup|disaster recovery|resilien)\b",
    re.I,
)

# 同名不同界的主題，出現就直接排除
OFF_TOPIC = re.compile(
    r"\b(game|gaming|gamedev|unity|unreal|minecraft|roblox|anime|"
    r"fastapi|django|react|flutter|wordpress|shopify|zapier|notion|excel|photoshop|"
    r"forex|trading|nft|airdrop|weight loss|recipe)\b",
    re.I,
)
LAB_HINT = re.compile(
    r"\b(lab|demo|demonstration|tutorial|hands.?on|walkthrough|how to|"
    r"configure|configuring|setup|setting up|install|practical|in action)\b",
    re.I,
)

# 講得清楚、更新頻率穩定的頻道給加分。不是白名單制——沒在名單上的照樣能被選中。
TRUSTED = {
    "professor messer": 3.0,
    "ibm technology": 2.5,
    "computerphile": 2.5,
    "powercert animated videos": 2.0,
    "the ciso perspective": 2.0,
    "practical networking": 2.0,
    "networkchuck": 1.5,
    "david bombal": 1.5,
    "john hammond": 1.5,
    "certbros": 1.5,
    "stationx with nathan house": 1.5,
    "hussein nasser": 1.5,
    "f5 devcentral": 1.2,
    "eye on tech": 1.0,
    "sans institute": 1.5,
    "cloudflare": 1.2,
    "google cloud tech": 1.0,
    "microsoft security": 1.0,
}

STOP = {
    "the", "a", "an", "of", "and", "or", "to", "in", "for", "on", "with", "vs",
    "what", "is", "are", "how", "explained", "security", "cyber", "cybersecurity",
}


def tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in STOP and len(w) > 2}


def kind_of(row: dict) -> str:
    if LAB_HINT.search(row["title"]):
        return "lab"
    if row["seconds"] >= 900:
        return "deep"
    return "core"


def score(row: dict, terms: set[str], want_kind: str) -> float:
    t = tokens(row["title"])
    overlap = len(t & terms)
    if not overlap:
        return -1  # 標題跟主題沒有任何實詞交集，不管多熱門都不是這一格的影片
    s = overlap * 3.0
    s += math.log10(max(row["views"], 1)) * 0.8
    s += TRUSTED.get(row["channel"].strip().lower(), 0)
    if kind_of(row) == want_kind:
        s += 2.0
    # 3–20 分鐘最適合當學習單元；太短講不完，太長不會有人看第二次
    if 180 <= row["seconds"] <= 1200:
        s += 1.0
    elif row["seconds"] > 3600:
        s -= 2.0
    return s


def eligible(row: dict, used: set[str]) -> bool:
    if row["videoId"] in used or row["views"] < MIN_VIEWS:
        return False
    if not (DRILL_MIN <= row["seconds"] <= DRILL_MAX):
        return False
    if META.get(row["videoId"], {}).get("embeddable") is False:
        return False  # 內嵌播不出來的影片，放進課程只會變成死格子
    blob = f"{row['title']} {row['channel']}"
    if BAD_TITLE.search(blob) or OFF_TOPIC.search(blob):
        return False
    # 可信頻道本來就只做這個領域，標題不見得會再寫一次「security」
    return bool(SECURITY_CONTEXT.search(blob)) or row["channel"].strip().lower() in TRUSTED


def terms_of(slug: str) -> set[str]:
    n = NOTES[slug]
    t = tokens(n["title"]) | tokens(slug.replace("-", " "))
    for a in n["aliases"]:
        t |= tokens(a)
    return t


def messer_item(vid: str, kind: str) -> dict:
    m = MESSER.get(vid, {})
    return {
        "name": re.sub(r"\s*[-–]\s*CompTIA.*$", "", m.get("title", vid)).strip(),
        "kind": kind,
        "url": f"https://www.youtube.com/watch?v={vid}",
        "channel": "Professor Messer",
        "duration": m.get("duration", ""),
        "why": "Professor Messer 官方 SY0-701 課程，逐條對應考綱編號",
    }


def build_unit(code: str, idx: int, slug: str, want_drills: int, used: set[str]) -> dict:
    note = NOTES[slug]
    seed = SEED.get(slug, {})
    copy = COPY.get(slug, {})
    terms = terms_of(slug)
    cands = json.loads((CAND / f"{slug}.json").read_text())

    unit: dict = {
        "id": f"{code.lower()}-u{idx}",
        "name": copy.get("name") or note["title"],
        "type": "topic",
        "assessment": copy.get("assessment", ""),
        "note": {
            "slug": slug,
            "title": note["title"],
            "url": note["url"],
            "caseUrl": note["case_url"],
            "questions": note["questions"],
            "concepts": [c["label"] for c in note["concepts"]][:10],
            "eli5": note["eli5_zh"] or note["eli5_en"],
            "eli5Lang": "zh" if note["eli5_zh"] else "en",
            "weight": note["weight"],
        },
        "drills": [],
    }

    by_id = {c["videoId"]: c for c in cands}

    def from_candidate(vid: str, why: str) -> dict:
        """指定的 ID 必須在該主題的搜尋結果裡找得到，否則就是憑空冒出來的。"""
        c = by_id.get(vid)
        if not c:
            raise SystemExit(
                f"✗ {slug}: 種子指定的 {vid} 不在 candidates/{slug}.json 裡。\n"
                f"  先用 tools/search_candidates.py --only {slug} 把它搜出來，"
                f"不要直接寫一個沒有搜尋結果佐證的 ID。"
            )
        return {
            "title": c["title"],
            "name": c["title"],
            "channel": c["channel"],
            "url": f"https://www.youtube.com/watch?v={vid}",
            "duration": c["duration"],
            "why": why,
        }

    # ── 主課 ────────────────────────────────────────────────────────────
    if seed.get("lesson") and seed["lesson"] in MESSER:
        vid = seed["lesson"]
        m = MESSER[vid]
        unit["lesson"] = {
            "title": re.sub(r"\s*[-–]\s*CompTIA.*$", "", m.get("title", "")).strip() or note["title"],
            "channel": "Professor Messer",
            "url": f"https://www.youtube.com/watch?v={vid}",
            "duration": m.get("duration", ""),
            "why": "Professor Messer 官方 SY0-701 課程，這一格逐條對應考綱編號",
        }
        used.add(vid)
    elif seed.get("lesson"):
        les = from_candidate(
            seed["lesson"],
            seed.get("lessonWhy")
            or f"Messer 官方課程沒有單獨講這個主題，改用 {by_id[seed['lesson']]['channel']} 這支",
        )
        les.pop("name", None)
        unit["lesson"] = les
        used.add(seed["lesson"])
    else:
        pick = max(
            (c for c in cands if eligible(c, used)),
            key=lambda c: score(c, terms, "core"),
            default=None,
        )
        if pick and score(pick, terms, "core") > 0:
            unit["lesson"] = {
                "title": pick["title"],
                "channel": pick["channel"],
                "url": f"https://www.youtube.com/watch?v={pick['videoId']}",
                "duration": pick["duration"],
                "why": copy.get("lessonWhy")
                or f"Messer 官方課程沒有單獨講這個主題，改用 {pick['channel']} 這支講得最完整的",
            }
            used.add(pick["videoId"])
        else:
            unit["lesson"] = {
                "title": note["title"],
                "url": None,
                "note": (
                    f"搜過 {len(cands)} 支候選（{'、'.join(sorted({c['query'] for c in cands}))}），"
                    "沒有一支同時滿足主題相符、觀看數門檻與長度區間，暫時留空"
                ),
            }

    # ── 延伸影片 ────────────────────────────────────────────────────────
    for vid in seed.get("messer", []):
        if len(unit["drills"]) >= want_drills or vid in used:
            continue
        m = MESSER.get(vid, {})
        unit["drills"].append(messer_item(vid, "deep" if m.get("seconds", 0) >= 900 else "core"))
        used.add(vid)

    # 指定的延伸影片先進場，自動選片只補剩下的格子
    for vid in seed.get("pin", []):
        if len(unit["drills"]) >= want_drills or vid in used:
            continue
        c = by_id.get(vid)
        item = from_candidate(vid, f"{c['channel']}，指定收錄")
        item.pop("title", None)
        item["kind"] = kind_of(c)
        unit["drills"].append(item)
        used.add(vid)

    # 不同頻道常有一模一樣的標題（"Virtualization Explained" 就有兩支）。
    # 對學習者來說那是同一格內容重複兩次，選一支就好。
    taken_titles = {
        re.sub(r"[^a-z0-9]", "", (d.get("name") or "").lower())
        for d in unit["drills"]
    } | {re.sub(r"[^a-z0-9]", "", (unit["lesson"].get("title") or "").lower())}

    def best(want: str, only_this_kind: bool):
        pool = [
            c
            for c in cands
            if eligible(c, used)
            and re.sub(r"[^a-z0-9]", "", c["title"].lower()) not in taken_titles
            and (not only_this_kind or kind_of(c) == want)
        ]
        if not pool:
            return None
        pick = max(pool, key=lambda c: score(c, terms, want))
        return pick if score(pick, terms, want) > 0 else None

    def add(pick: dict) -> None:
        k = kind_of(pick)
        have.add(k)
        taken_titles.add(re.sub(r"[^a-z0-9]", "", pick["title"].lower()))
        label = {"lab": "實作示範", "deep": "完整講解"}.get(k, "短講補強")
        unit["drills"].append(
            {
                "name": pick["title"],
                "kind": k,
                "url": f"https://www.youtube.com/watch?v={pick['videoId']}",
                "channel": pick["channel"],
                "duration": pick["duration"],
                "why": f"{pick['channel']}，{label}",
            }
        )
        used.add(pick["videoId"])

    # 先讓三種型態各拿一支，一個單元裡三支都是同型態的話學起來很單調
    have = {d["kind"] for d in unit["drills"]}
    for want in ("deep", "lab", "core"):
        if len(unit["drills"]) >= want_drills:
            break
        if want in have:
            continue
        if pick := best(want, True):
            add(pick)

    # 型態湊不齊就用綜合分數補滿，不強求
    while len(unit["drills"]) < want_drills:
        pick = best("core", False)
        if not pick:
            break
        add(pick)

    # 補不滿就誠實留空，不要拿不相關的影片填版面。
    # 同一單元可能不只缺一格，名稱要編號，否則稽核會判定為重複項目。
    while len(unit["drills"]) < want_drills:
        n = sum(1 for d in unit["drills"] if not d.get("url")) + 1
        unit["drills"].append(
            {
                "name": f"{note['title']}（待補 {n}）",
                "kind": "core",
                "url": None,
                "note": f"搜過 {len(cands)} 支候選，符合主題且過得了觀看數與長度門檻的不足這一格",
            }
        )

    return unit


def main() -> int:
    report = "--report" in sys.argv
    order = sorted(NOTES, key=lambda s: (NOTES[s]["domain"], s))
    used: set[str] = set()
    stats = {"lesson_messer": 0, "lesson_search": 0, "lesson_missing": 0, "drill_missing": 0}

    for code in CHAPTERS:
        ch = CHAPTERS[code]
        n = int(code[2:])
        slugs = [s for s in order if NOTES[s]["domain"] == n]
        per = ch["drills"] // ch["units"]
        assert len(slugs) == ch["units"], f"{code}: 筆記有 {len(slugs)} 個主題，設定寫 {ch['units']}"

        units = [build_unit(code, i + 1, s, per, used) for i, s in enumerate(slugs)]
        for u in units:
            if not u["lesson"].get("url"):
                stats["lesson_missing"] += 1
            elif "Messer" in (u["lesson"].get("channel") or ""):
                stats["lesson_messer"] += 1
            else:
                stats["lesson_search"] += 1
            stats["drill_missing"] += sum(1 for d in u["drills"] if not d.get("url"))

        blob = {"chapter": code, "units": units}
        if not report:
            (DATA / f"{ch['source']}.json").write_text(json.dumps(blob, ensure_ascii=False, indent=1))
        print(f"{code} {ch['title']}: {len(units)} 單元 · 每單元 {per} 支延伸")

    print(
        f"\n主課：Messer {stats['lesson_messer']} · 搜尋遞補 {stats['lesson_search']}"
        f" · 留空 {stats['lesson_missing']}"
    )
    print(f"延伸影片留空 {stats['drill_missing']} 格 · 全課去重後用到 {len(used)} 支影片")
    return 0


if __name__ == "__main__":
    sys.exit(main())
