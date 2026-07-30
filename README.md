# CompTIA Security+ SY0-701 影片伴讀課

把 [CompTIA Security+ SY0-701 study notes](https://github.com/htlin222/CompTIA-security-plus-notes)
的 **83 個考綱主題**，一對一配上經過驗證的 YouTube 影片。

**線上課程**：<https://security-plus-course.pages.dev>
**對應筆記**：<https://htlin222.github.io/CompTIA-security-plus-notes>

---

## 這是什麼

不是又一份播放清單，也不是筆記的替代品。它是**筆記的入口**。

面對一頁 8000 字的 Zero Trust 筆記，沒有背景的人不知道從哪裡開始讀。
影片解決的就是這件事：先用 10 分鐘把觀念講到聽得懂，再進筆記補細節。

所以每個單元固定給你三件事：

1. **一支主講影片** — 多數來自 Professor Messer 的官方 SY0-701 對照課程，逐條對應考綱編號
2. **一段自我檢核** — 「怎麼確認自己真的懂了」，答不出來就代表影片白看了
3. **一個回筆記的入口** — 同名筆記頁的 ELI5、下層概念、情境案例與練習題

外加每個單元都標到 **NIST／MITRE ATT&CK／RFC 的原始文件**，連結全數經 API 重驗。

| | |
|---|---|
| 章節 / 單元 | 5 / 83（對齊 SY0-701 五大考科） |
| 影片 | 318 個欄位 · 去重 305 支 · 69 小時 43 分 |
| 標準依據 | 10 個家族 · 39 條原始引用 |
| 連結有效率 | 305 / 305（100%） |
| 誠實留空 | 3 格（附說明查過什麼、為什麼不合格） |

---

## 三條不可退讓的規則

這門課花最多力氣在「不要騙人」上，因為幾百個格子最容易出的事就是連結是編的。

**一、video ID 一律取自實際搜尋結果。**
`tools/search_candidates.py` 對 83 個主題各跑三個角度的 YouTube 搜尋，
**5800 多筆原始結果全部留在 `course/data/candidates/`**。
最後只選 3–4 支，但「當時看過哪些、為什麼沒選」留得下來——
沒有這份紀錄，之後沒有人能檢查這個選擇合不合理，影片下架時也沒辦法重挑。

**二、不信任任何上游宣稱，包括自己剛才說已經驗證過的。**

```
make audit     離線稽核：設定檔、配額、影片長度、實證深度（確定性，不打網路）
make verify    打真實 API：每個 YouTube 連結重打 oEmbed、
               每條標準依據重打 CSRC / IETF / MITRE / NVD
```

**三、找不到合格影片就留空並說明。**
硬塞一支「大致相關」的比留空更糟——它會讓人以為這個主題已經被講過了。

---

## 標準依據怎麼驗

資安沒有 PubMed，但有四種一樣能程式化重驗的權威來源：

| type | 端點 | 驗什麼 |
|------|------|--------|
| `nist` | csrc.nist.gov 出版頁 | 頁面標題必須含該編號 |
| `rfc` | IETF datatracker API | 回傳正式標題 |
| `attck` | attack.mitre.org 技術頁 | 頁面標題必須含 technique id |
| `cve` | NVD REST API 2.0 | 回傳該 CVE 的描述 |

NIST 的網址規則不只一種（`800-53r5` 是 `/800/53/r5/`、`800-63b` 是 `/800/63/b/`、
FIPS 又是另一套），憑印象寫十之八九會連到 404 或**別份文件**——後者更危險，
因為它看起來完全正常。所以有 `tools/resolve_nist.py` 逐一試打取回真實網址：

```bash
uv run python tools/resolve_nist.py "SP 800-53 Rev. 5" "FIPS 197"
# ✓ SP 800-53 Rev. 5   https://csrc.nist.gov/pubs/sp/800/53/r5/final
#     SP 800-53 Rev. 5, Security and Privacy Controls for Information Systems and Organizations
```

---

## 從頭重建

需要 [uv](https://docs.astral.sh/uv/)。建置腳本只用 Python 標準庫，沒有執行期相依。

```bash
uv run python src/build/sync_notes.py      # 1. 從筆記 repo 抓 83 個 topic
uv run python tools/search_candidates.py   # 2. 每個主題搜三個角度（會跑一陣子）
uv run python tools/assemble.py            # 3. 確定性選片，組出 ch1..ch5.json
uv run python tools/fetch_meta.py          # 4. 抓真實長度／觀看數／可否嵌入
uv run python tools/assemble.py            # 5. 再組一次（這次會排除不可嵌入的）
uv run python tools/build_evidence.py      # 6. 產生單元層級的考綱與標準對應
make check && make verify                  # 7. 全綠才算數
make deploy
```

步驟 3 與 5 都要跑，是因為第一輪還沒有中繼資料，選片器不知道哪些影片不能嵌入。

## 指令

```
make build     course/ → dist/，配額不符會直接失敗
make audit     離線稽核（確定性，不打網路，可放 CI）
make test      前端純邏輯單元測試（node:test，零依賴）
make verify    重驗每個影片連結與每條標準依據（打真實 API）
make serve     本機預覽 http://localhost:8899
make og        重新產生社群預覽圖（由 course.config.json 生成，不會留下上一門課的文案）
make check     lint + test + build + audit，提交前跑這個
make deploy    部署到 Cloudflare Pages
```

## 換成你自己的主題

框架是 [curate-course](https://github.com/htlin222/curate-course)，主題無關。
`course/` 底下整組換掉就是另一門課，`src/` 不用動。
本課程對框架的改動（實證來源、筆記面板、og 生成）都寫在
[設計文件](docs/plans/2026-07-31-security-plus-course-design.md)裡。

## 授權與聲明

程式碼 MIT。**與 CompTIA 無關**，未經其認可或背書；CompTIA、Security+ 與 SY0-701
為 CompTIA 的商標。影片版權歸原 YouTube 頻道所有，本站僅提供連結。
課程依 SY0-701 考綱編排，但不保證涵蓋所有命題範圍。
