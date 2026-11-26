# AI UI skills 使用文件

Emil Kowalski 的 AI UI skills 是一組給 coding agent（以 Claude Code 為主）用的指令包：讓 agent 做介面、動畫、手勢時照他的設計工程標準來，也幫忙審查、壓力測試和清理動畫。aiforui.dev 的首頁說：「The workflows are built around Claude Code, but the core of the course ... applies to any coding agent.」（<https://aiforui.dev/>）

這份文件是 Lumen 介面大改前的研究，資料讀取日期 2026-11-26。**還沒有安裝任何 skill。**

| 文件 | 內容 |
|---|---|
| [skills-catalog.md](skills-catalog.md) | 20 個 skill 的總表、逐項資料、兩個網站的差異 |
| [workflows.md](workflows.md) | 12 個流程：觸發條件、用哪個 skill、步驟、驗收、陷阱 |
| [prompt-library.md](prompt-library.md) | 每個 skill 四種 prompt：一般、Lumen 專用、嚴格審查、修 bug／重構 |
| [installation-plan.md](installation-plan.md) | 安裝指令、時機、寫入位置、驗證、更新、移除、風險 |

來源：
- skills.sh：<https://www.skills.sh/emilkowalski/skills>（20 個 skill）
- aiforui.dev：<https://aiforui.dev/skills>（19 個，沒有 write-swift）
- GitHub：<https://github.com/emilkowalski/skills>

## 何時用哪個 skill

aiforui.dev 依專案進行的順序分成五類（<https://aiforui.dev/skills>：「Ordered in the way you'd reach for them in an actual project」）：

| 情況 | Skill |
|---|---|
| 不知道用哪個 | `ask-emil`，或直接用主 skill `emil-design-eng` |
| 知道要什麼效果，不知道叫什麼 | `animation-vocabulary` |
| 自己寫還是用套件 | `pick-ui-library` |
| 還在比較方向 | `prototype` |
| 做一個動畫 | `animate` |
| 好幾個元素一起動 | `choreograph` |
| 想要 Apple 那種流暢、有物理感的動態 | `apple-design` |
| 拖、滑、抽屜 | `gestures` |
| 網頁在手機上像網站 | `mobile-native` |
| 動畫卡、掉幀 | `animation-performance` |
| 上線前用極端資料測 | `break-ui` |
| 合併前審動畫 | `review-animations`（只審不改，結論 Approve 或 Block） |
| 整個 app 哪裡該動 | `find-animation-opportunities`（唯讀） |
| 整個 app 的動畫改善計畫 | `improve-animations`（只寫計畫） |
| 動畫太多 | `remove-animations` |
| Expo／React Native | `animate-expo` |
| Sonner toast | `ask-sonner` |
| session 結束時把修正變成規則 | `learn-taste`（寫 `DESIGN.md`） |
| Swift | `write-swift`（只在 skills.sh） |

## Claude Code 在 UI 工作的決策流程

```
收到 UI 任務
├─ 這是動態／介面的事嗎？不是 → 不用這些 skill
├─ 只要名詞 → animation-vocabulary
├─ 還沒決定做法
│   ├─ 要不要用套件 → pick-ui-library（Lumen 無 React，多半自己寫）
│   └─ 方向未定 → prototype
├─ 動手做
│   ├─ 單一元素 → animate
│   ├─ 多元素 → choreograph
│   ├─ 手勢 → gestures（+ apple-design）
│   └─ 說不出是哪一種 → emil-design-eng
├─ 做完、合併前
│   ├─ 極端資料 → break-ui
│   ├─ 效能 → animation-performance
│   └─ 審查 → review-animations：Block 就修，再審一次
└─ 整個 app
    ├─ 少了什麼 → find-animation-opportunities
    ├─ 太多 → remove-animations
    └─ 全面計畫 → improve-animations → 按計畫逐項實作 → review-animations
```

原則：
1. **先問要不要動**。animate、emil-design-eng、animate-expo 都先判斷該不該加動畫（各 skill 頁）。Lumen 是天天開的筆記工具，常用的介面要少動。
2. **用專門的 skill**。emil-design-eng 什麼都做，但「not as focused as the others」（<https://aiforui.dev/skills/emil-design-eng>）。
3. **唯讀的 skill 先跑**。find-animation-opportunities、improve-animations、review-animations 不改原始碼，適合先跑。
4. **Lumen 的限制要寫進 prompt**：純 JS 與 CSS、沒有 React、沒有建置步驟；Tauri 打包後跑在 WKWebView（Safari 引擎）。沒寫的話，skill 可能會建議 Motion 或 Sonner 這類 React 套件。
5. **改完照原本的方式驗證**：用 Safari 引擎測編輯器（scratchpad 的 WKWebView 測試）、i18n 檢查、`node` 語法檢查。

## 安裝、更新、移除的原則

細節見 [installation-plan.md](installation-plan.md)。
- **裝在使用者目錄，只裝給 Claude Code，指名要裝的 skill**：`-g -a claude-code --skill ...`（已決定）。關掉匿名使用資料：指令前加 `DISABLE_TELEMETRY=1`（已決定）。不在 Lumen repo 裡建立 `.agents/`、`.claude/`、`skills-lock.json`。
- **分批裝**。用不到的不裝：animate-expo、ask-sonner、write-swift 等。
- **裝前先讀 SKILL.md**，特別是有警告的三個：emil-design-eng、animate（Snyk Warn）、write-swift（shell 指令）。
- **更新前**：先 `npx skills check`，看 GitHub 的改動，再 `npx skills update <名稱>`。
- **移除**：指名移除，不用 `--all`。

## 常見錯誤與排除

| 症狀 | 可能原因 | 處理 |
|---|---|---|
| `/` 選單看不到新 skill | session 是安裝前開的；或裝到別的 agent | 開新 session；`npx skills list -g -a claude-code` |
| `/pick-ui-library` 不會自己被用到 | SKILL.md 設了 `disable-model-invocation: true` | 正常，手動輸入 |
| skill 建議裝 Motion、Sonner、React 套件 | skill 預設 React 生態 | prompt 寫明 Lumen 是純 JS 與 CSS，請它用 CSS transition、WAAPI 或原生 JS |
| prototype 不知道把版本放哪 | Lumen 沒有前端路由 | 請它用一個開發用的切換開關，放在 `static/` 內，完成後移除 |
| review-animations 一直 Block | 照作者的嚴格規則，預設會挑出問題 | 逐項修；不同意的項目寫下理由，由你決定 |
| learn-taste 想寫 `CLAUDE.md` | 示範把寫進 `CLAUDE.md` 當反例，正確是 `DESIGN.md` | 改用 `DESIGN.md`；CLAUDE.md 的改動依專案規則先問 |
| 安裝時跳出要選 agent | 沒指定 `-a` | 中止，改用 `-a claude-code` |
| 下載失敗、HTTP 503 | GitHub 暫時不穩 | 晚點再試，或手動安裝（安裝計畫第 8 節） |
| 改完後舊筆記格式變了 | skill 改到編輯器（`wys.js`、`props.js`） | 跑 400 篇筆記的往返測試（rt.html），結果要 0 changed |
