# CompTIA Security+ SY0-701 影片伴讀課 — 設計

日期：2026-07-31
狀態：已實作並上線

## 一句話

把 [CompTIA-security-plus-notes](https://github.com/htlin222/CompTIA-security-plus-notes)
的 83 個考綱主題，一對一配上經過驗證的 YouTube 影片，做成一個能回連筆記、
每個單元都標得出 NIST／MITRE ATT&CK 原始出處的靜態課程網站。

## 為什麼是伴讀而不是取代

筆記已經有 563 個概念、83 篇情境案例、332 題練習題與 646 段 ELI5。它缺的不是內容，
是**入口**——面對一頁 8000 字的 Zero Trust 筆記，沒有背景的人不知道從哪裡開始讀。

影片解決的就是這件事：先用 10 分鐘把觀念講到聽得懂，再進筆記補細節。
所以這門課的設計目標不是「內容最多」，而是**每一格都對得回筆記的同一個主題**。
分工寫在課程的立場頁裡：影片負責懂，筆記負責熟。

## 架構

```
CompTIA-security-plus-notes (v4)          ← 內容的唯一事實來源
        │  sync_notes.py 抓 tarball
        ▼
course/data/notes-index.json               83 topic × {title, ELI5, 概念, 考點提示, 練習題數}
        │
        ├── curation-seed.json             主課對應（人工判斷）＋ 額外搜尋關鍵字
        ├── candidates/<slug>.json         5800+ 筆真實搜尋結果（保留，供日後複查）
        ├── unit-copy.json                 83 個繁中單元名稱與自我檢核（人工撰寫）
        │        │  assemble.py 確定性選片
        │        ▼
        ├── ch1..ch5.json                  83 單元 × (1 主課 + 2–3 延伸)
        ├── video-meta.json                每支影片的真實長度／觀看數／頻道／可否嵌入
        ├── drill-evidence-1.json          10 個主題家族的標準依據（人工撰寫）
        └── unit-evidence-1/2.json         立場三條（人工）＋ 83 單元的考綱與標準對應（生成）
                 │  src/build/build.py
                 ▼
             dist/course.json → Cloudflare Pages
```

框架沿用 [curate-course](https://github.com/htlin222/curate-course)，只動 `course/`
與少數幾處必要的框架改動（見下）。

## 五個決策

**一、顆粒度對到 topic 而不是官方 objective。**
官方考綱只有 28 條 objective，對到筆記的 83 頁是一對多，連結關係會鬆掉。
改用 topic 一對一，代價是章節內單元數較多，但「看完影片點進同名筆記頁」這條路徑
才成立——那是這門課存在的唯一理由。考綱編號仍然標在每個單元的「考綱落點」欄位。

**二、主課優先用 Professor Messer 的官方對照課程。**
他的 121 支影片標題自帶考綱編號，是唯一能程式化對照的來源。83 個主題裡 71 個
用得上；剩下 12 個 Messer 沒有單獨講（SIEM、SOAR、SSO、PAM、聯邦、威脅獵捕…），
改由搜尋結果遞補，並在選片理由裡寫明「Messer 沒有單獨講這個主題」——
硬塞一支「大致相關」的比留空更糟，它會讓人以為這個主題已經被講過了。

**三、實證層從 PubMed 換成 NIST／ATT&CK／CVE／RFC。**
資安沒有 PubMed，但有四種一樣能程式化重驗的權威來源。`verify_refs.py` 整個改寫：

| type | 端點 | 驗什麼 |
|------|------|--------|
| `nist` | csrc.nist.gov 出版頁 | 頁面標題必須含該編號 |
| `rfc` | IETF datatracker API | 回傳正式標題 |
| `attck` | attack.mitre.org 技術頁 | 頁面標題必須含 technique id |
| `cve` | NVD REST API 2.0 | 回傳該 CVE 的描述 |

NIST 的網址規則不只一種（`800-53r5` 是 `/800/53/r5/`、`800-63b` 是 `/800/63/b/`、
FIPS 又是另一套），憑印象寫十之八九會連到 404 或別份文件，所以另外寫了
`tools/resolve_nist.py` 逐一試打取回真實網址。

**四、策展用確定性選片器，不用「感覺」。**
83 個主題 × 3 個角度（精講／深講／實作）跑 innertube 搜尋，原始結果全部留在
`course/data/candidates/`。選片器對真實結果打分：主題詞重疊、觀看數、頻道信任度、
長度區間、型態多樣性。判斷仍是人下的，寫在規則裡而不是逐格挑，好處是可複製、
可稽核、影片下架時只換那一格。

三條排除規則是踩過坑才加的：
- **領域脈絡**：AAA 撞到「AAA 遊戲」、automation 撞到 Zapier 教學、
  authentication 撞到 FastAPI 教學。候選必須帶資安／IT 脈絡詞或出自可信頻道。
- **可嵌入**：上課模式是內嵌播放，不允許嵌入的影片在課程裡等於死格子。
  `fetch_meta.py` 打 oEmbed 記錄嵌入權限，選片時就排除，不是事後才發現。
- **單元內標題去重**：不同頻道常有一模一樣的標題（"Virtualization Explained"
  就有兩支），對學習者是同一格內容重複兩次。

**五、留空要說明，而且要留得下來。**
最後有 3 格找不到合格影片，照實留空並註記「搜過 N 支候選、為什麼都不合格」。
`audit` 的 `allowMissingUrls` 設 12，代表這是被容許的狀態而不是待辦事項。

## 對框架的改動

`course/` 以外動到的，都是原本寫死了主題假設的地方：

| 檔案 | 改了什麼 | 為什麼 |
|------|---------|--------|
| `src/build/verify_refs.py` | PubMed／Crossref → NIST／RFC／ATT&CK／CVE | 換領域必須換來源 |
| `src/build/audit.py` | PMID 格式檢查 → 依 type 分別檢查 | 同上 |
| `src/build/build.py` | 讀 `unit-evidence-*.json`；單元名稱參與分面抽取；`notes_*` 統計 | 舊命名寫死、分面無來源 |
| `src/build/seo.py` | 新增 `render_og()`，og.html 改由設定檔生成 | og.html 原本硬編碼上一門課的文案 |
| `src/web/js/render.js` | 新增 `noteBox()`；引用渲染改為來源無關 | 伴讀面板；PubMed 網址原本寫死 |
| `src/web/css/note.css` | 新增 | 同上 |
| `src/build/sync_notes.py` | 新增 | 筆記橋接 |
| `tools/*` | 新增 | 策展工具鏈 |

`noteBox` 只要單元有 `note.url` 就渲染，欄位全部選用——它是主題無關的框架功能
（「單元掛一份外部筆記」），不是這門課的專屬 hack，值得回饋給 curate-course。

## 成品數字

| 項目 | 數字 |
|------|------|
| 章節 / 單元 | 5 / 83（對齊考綱五大考科與筆記 83 個 topic） |
| 影片欄位 / 去重 | 318 / 305 |
| 課程時長 | 69 小時 43 分 |
| 主課來源 | Professor Messer 71 · 搜尋遞補 12 |
| 標準依據 | 10 個家族 · 39 條原始引用 · 388 條逐一重驗 100% 通過 |
| 連結有效率 | 305 / 305（100%） |
| 誠實留空 | 3 格 |

## 驗收

```bash
make check     # lint + 18 個前端測試 + build + audit → 全綠
make verify    # 305 個連結 100% 有效、388 條標準依據 100% 通過
```

## 已知的坑與後續

- **筆記有 31 個主題沒有繁中 ELI5**，課程會退回顯示英文版。補在筆記那邊比補在
  這裡好——這裡只是讀取端。
- **單元層級的實證只有機器可推導的欄位**（考綱落點、標準依據、引用）。
  `common_trap` 與 `pitfalls` 這類要人寫的欄位目前只有立場頁那三條有。
  真要補，放進 `unit-evidence-3.json`（檔名排序在後者勝出）。
- **giscus 的 repoId／categoryId 待填**。要先到 <https://github.com/apps/giscus>
  安裝到本 repo，再把 id 填進 `course.config.json` 的 `discussions`。
- **23 個延伸影片歸不到標準家族**，只是拿不到類別層級的引用，不影響單元層級。
  想收斂就補 `course/taxonomy/families.py` 的規則。
- **觀看數會變**，`tools/fetch_meta.py --force` 偶爾重跑一次。
