# Skills 目錄

Emil Kowalski 的 AI UI skills，依兩個網站整理，資料讀取日期 2026-11-26。

- **S** = skills.sh：作者頁 <https://www.skills.sh/emilkowalski/skills>，每個 skill 一頁 `https://www.skills.sh/emilkowalski/skills/<名稱>`
- **A** = aiforui.dev：總覽 <https://aiforui.dev/skills>，每個 skill 一頁 `https://aiforui.dev/skills/<名稱>`
- **R** = GitHub repo <https://github.com/emilkowalski/skills>（README 與 `skills/<名稱>/SKILL.md`）

「待確認」表示兩個網站都沒寫，或頁面讀不到。引文保留英文原文。

## 讀取狀況

| 來源 | 讀到的 | 沒讀到的 |
|---|---|---|
| S | 作者頁、20 個 skill 頁 | 每頁的 SKILL.md 摘錄被截斷（「Show more」），只看得到開頭 |
| A | 總覽、19 個 skill 頁、首頁 | /team、/login（與 skills 無關，沒讀） |
| R | README、`skills/` 目錄；完整 SKILL.md 只讀到 3 個：animation-vocabulary、pick-ui-library、gestures | 其餘 17 個 SKILL.md 在 GitHub 回 HTTP 503；STANDARDS.md、API.md、cheatsheet 沒讀 |

所以 S 欄位多半只有摘錄開頭，A 欄位比較完整（每頁有用途、適用時機、範例 prompt、前後對照）。三個 SKILL.md 全文讀到的 skill，資料最可靠。

## 總表

安裝狀態（2026-11-27）：第一批 4 個已裝在使用者目錄 `~/.claude/skills/`，只給 Claude Code；本專案（`~/Lumen`）沒有裝任何 skill。
- 指令：`DISABLE_TELEMETRY=1 npx skills@latest add emilkowalski/skills --skill emil-design-eng --skill review-animations --skill animation-vocabulary --skill ask-emil -a claude-code -g -y`（CLI 1.9.0）
- 版本：GitHub commit `64eb3deb9a5fbfa041faf783e0bc3fd635872e9c`（2026-11-15）。裝好的檔案和 repo 內容逐檔相同。
- 寫入：`~/.claude/skills/<名稱>/`（直接複製，不是 symlink）；全域鎖定檔 `~/.agents/.skill-lock.json`（記錄來源、commit、資料夾雜湊）。另有 npx 的套件快取。

| Skill | 來源 | 分類（A） | 用途 | 適合任務 | 不適合任務 | 範例 prompt | 輸出／影響範圍 | 安裝狀態 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| animation-vocabulary | S、A | 01 Before you build | 把模糊描述對到動畫的正確術語 | 會描述效果但不知道叫什麼 | 設計或實作動畫（SKILL.md：「For naming an effect, not designing or building one」） | `/animation-vocabulary the thing where the button shrinks a bit when you click it` | 只回文字，不改檔 | 已安裝（2026-11-27），測過 | SKILL.md 全文已讀；只用內建詞彙表 |
| pick-ui-library | S、A | 01 Before you build | 從作者的精選清單挑一個函式庫 | 元件要自己寫還是用套件 | 清單外的需求（會說明並改用一般知識） | `/pick-ui-library the price needs to animate when it changes, what should I install?` | 建議；被要求時會安裝並接上 | 未安裝 | 先讀 `package.json`；`disable-model-invocation: true`（只能手動呼叫） |
| prototype | S、A | 01 Before you build | 同一塊 UI 做幾個不同版本，用切換器比較 | 探索階段，要在真的 app 裡比較 | 審查現有 UI、規劃修正、選套件（S） | `/prototype try three different directions for the download button` | 新增路由與切換器；選定後實作該版並移除原型 | 未安裝 | 每個版本放在自己的路由（A） |
| ask-emil | S、A | 01 Before you build | 依情況推薦一個 skill 或一串順序 | 知道要做什麼，不知道用哪個 skill | 待確認 | `/ask-emil I just built a settings page, what should I check before shipping?` | 只回建議 | 已安裝（2026-11-27），只能手動 `/ask-emil` | 推薦前先讀各 skill 的 SKILL.md（S） |
| emil-design-eng | S、A | 02 Building the interface | 主 skill：作者的設計工程想法，以動畫為主 | 不確定用哪個 skill 時 | 有專門 skill 的任務（A：專門 skill「better at specific tasks」） | `/emil-design-eng make this button feel more responsive` | 修改程式碼，附 Before／After／Why 表 | 已安裝（2026-11-27），測過 | S 的 Snyk 稽核為 Warn |
| animate | S、A | 02 Building the interface | 從零做一個動畫，依序決定要不要動、用什麼、屬性、曲線、時長 | 要讓某個元素動起來 | 稽核整個程式碼、審 diff、找機會、React Native（S） | `/animate animate this dropdown so it opens from the button` | 動畫程式碼 | 未安裝 | 工具在 CSS transition、keyframes、WAAPI、Motion 間選；S 的 Snyk 為 Warn |
| choreograph | S、A | 02 Building the interface | 協調好幾個一起動的元素 | 列表錯開、hero 動畫、刪除項目後其他項目補位 | 單一動畫的曲線與時長（屬 animate，S） | `/choreograph when I delete a card from this list the others jump into place. Fix it` | 修改時序 | 未安裝 | 錯開每個元素 30–80ms、總長約 300ms 內（A） |
| apple-design | S、A | 02 Building the interface | 把 Apple WWDC 的介面與流暢動態原則轉成網頁做法 | 想讓產品像 Apple 生態系的一部分 | 待確認 | `/apple-design what spring should I use for this drawer` | 修改程式碼 | 未安裝 | 主要依據 WWDC 2018「Designing Fluid Interfaces」（S） |
| gestures | S、A | 02 Building the interface | 拖曳、滑動、抽屜等手勢 | 任何能拖、滑、甩、長按的東西；手勢卡頓 | 有現成函式庫能做的互動（建議先用 Vaul） | `/gestures the drawer jumps when I let go halfway` | 程式碼與做法 | 未安裝 | SKILL.md 全文已讀；觸控目標至少 44×44px |
| mobile-native | S、A | 02 Building the interface | 修掉網頁在手機上像網站不像 app 的小問題 | 手機或觸控裝置的體驗 | 設計或審查動畫、React Native（S） | `/mobile-native the page zooms in when I focus the email input` | 修改程式碼；說明哪些修正從程式碼可驗證、哪些要真機 | 未安裝 | 有「symptom table」對照症狀 |
| animation-performance | S、A | 03 Refining and reviewing | 讓動畫維持每秒 60 幀 | 動畫有效能問題 | 選曲線與時長、判斷該不該動、RN 執行緒（S） | `/animation-performance this sidebar animation is janky on my phone` | 修改程式碼 | 未安裝 | 先找掉幀原因再改程式（A） |
| break-ui | S、A | 03 Refining and reviewing | 用最壞情況的資料測 UI | 上線前測新功能 | 重新設計元件、評品味、審動畫（S） | `/break-ui try to break the member row in the team settings` | 報告、「Demo data / Worst case」切換、逐項修正 | 未安裝 | 會加入測試資料與切換器 |
| review-animations | S、A | 03 Refining and reviewing | 依作者規則嚴格審查動畫，最後給 Approve 或 Block | 合併或發 PR 前 | 寫功能、修無關 bug、審非動畫程式碼（S） | `/review-animations check the motion in src/components/dialog.tsx` | 審查報告（每項附檔名:行號與數值），不改檔 | 已安裝（2026-11-27），只能手動 `/review-animations` | 規則在 STANDARDS.md（沒讀到），以「The Ten Non-Negotiable Standards」為核心 |
| find-animation-opportunities | S、A | 04 Looking at the whole app | 找出真正需要動畫的地方，也列出不該動的 | 隨時；稽核整個 app | 審查現有動畫、規劃修正、實作（S） | `/find-animation-opportunities what should and shouldn't animate in our dashboard` | 唯讀建議（A：「It's read-only」） | 未安裝 | S：「Expect to reject most candidate」 |
| improve-animations | S、A | 04 Looking at the whole app | 稽核全部動畫，寫成有優先順序、可交給其他 agent 執行的計畫 | 想改善整個 app 的動態 | 審單一 diff（屬 review-animations）、自己實作（S） | `/improve-animations survey this app and write plans I can hand off` | 計畫；交出計畫前不改原始碼 | 未安裝 | 計畫存在哪裡：待確認 |
| remove-animations | S、A | 04 Looking at the whole app | 移除或縮短不必要的動畫 | 動畫太多、app 感覺慢 | 新增動畫（S） | `/remove-animations the app feels slow, find the animations we don't need` | 移除或縮短動畫，列出保留項與原因 | 未安裝 | S：動畫能銜接突兀變化時，全刪是錯的 |
| animate-expo | S、A | 05 Other skills | React Native／Expo 的動畫，與 Expo 團隊合作 | Expo 或 React Native app | 網頁 | `/animate-expo the collapsing header stutters on Android` | 程式碼（Reanimated、手勢、觸覺回饋） | 未安裝 | 本專案不是 RN，用不到 |
| ask-sonner | S、A | 05 Other skills | Sonner（作者的 toast 函式庫）的設定與修正 | 正在用 Sonner | 沒用 Sonner 的專案 | `/ask-sonner my toasts show up twice in development` | 程式碼 | 未安裝 | Sonner 是 React 函式庫；本專案沒用 |
| learn-taste | S、A | 05 Other skills | 把這次 session 的設計修正整理成規則 | session 結束、糾正 agent 不只一次時 | 改元件程式碼（S：不改元件程式碼） | `/learn-taste go through this session and pull out everything I corrected` | 寫入 `DESIGN.md`（只寫使用者同意的） | 未安裝 | 可讀 `~/.claude/projects/<project>/` 的對話紀錄（S） |
| write-swift | **只有 S** | 無（A 沒有） | 寫現代 Swift（到 Swift 6.4） | 待確認 | 待確認 | 待確認 | 待確認 | 未安裝 | S 警告：「Contains Shell Commands」；R 的 README 也沒列 |

## 兩個網站的差異

| 項目 | skills.sh（S） | aiforui.dev（A） |
|---|---|---|
| skill 數 | 「20 skills」 | 「Available skills 19」 |
| write-swift | 有，列第 12 | 沒有，全站沒提到 Swift |
| 首頁的 skill 清單 | — | 首頁寫「28 UI skills」，但列出的是 26 個課程用名稱（typography、color、ui-polish、unslop-design 等），只有 prototype、ask-emil、mobile-native、learn-taste 與 /skills 頁重疊。這些是課程內容，不在 /skills 頁上，也沒有安裝指令 |
| 安裝指令 | 作者頁：`npx skills add emilkowalski/skills`；skill 頁：`npx skills add https://github.com/emilkowalski/skills --skill <名稱>` | `npx skills@latest add emilkowalski/skills`；`npx skills@latest add emilkowalski/skills --skill <名稱>` |
| 排序 | 依安裝數 | 依「實際專案裡用到的順序」，分 01–05 五類 |
| 日期 | 「First Seen」 | 「Updated」（最近更新 2026-11-15） |
| improve-animations | — | 總覽寫「plans for subagents to execute」，skill 頁寫「ready for a cheaper model to execute」，同站兩處說法不同 |
| 安全稽核 | 每頁有 Agent Trust Hub／Socket／Snyk 結果；emil-design-eng、animate 的 Snyk 為 Warn | 沒有 |
| GitHub 星數 | 59.5K（skill 頁）、59.9k（repo 頁） | 59,838 |

兩邊的用途描述沒有互相矛盾，只是詳略不同。兩邊說法不同的地方都照原樣列在上表，沒有合併。

## 各 skill 詳細資料

每個 skill 列出名稱、來源、分類、用途、適合與不適合的任務、範例 prompt、輸出／影響範圍、安裝需求、已知限制、備註。兩個網站都沒寫的欄位標「待確認」。

共同事項：
- **作者**：Emil Kowalski（A 每頁「By Emil Kowalski」）。
- **呼叫方式**：A 每頁有「Invoke with」，即 `/<名稱>`。
- **安裝需求**：兩站都沒寫每個 skill 的需求。CLI 需要 Node.js 22.20 以上（<https://github.com/vercel-labs/skills>）。本機是 v24.11.1。
- **版本與授權**：每個 skill 的版本都沒寫，repo 是 MIT 授權（R）。

### 1. animation-vocabulary
- **來源**：S、A <https://aiforui.dev/skills/animation-vocabulary>、R（SKILL.md 全文）
- **分類**：01 Before you build
- **用途**：「The exact word you need to describe what you want.」（A）；SKILL.md 寫「Reverse-lookup glossary that turns a vague description of a web animation or motion effect into its exact term」
- **適合**：「When you can describe an effect but don't know what it's called」（A）
- **不適合**：「For naming an effect, not designing or building one.」（R）
- **範例 prompt**：`/animation-vocabulary what's it called when one shape turns into another one?`（A）；SKILL.md 的例子：popover 從按鈕長出來 → Origin-aware animation；一張圖變成另一張 → Morph；iOS 拉過頭回彈 → Rubber-banding
- **輸出**：只有文字，格式是 `**術語** — 解釋`，最符合的排第一，再列一到兩個替代詞（R）
- **限制**：「Stay within this glossary」，詞彙表裡沒有就直說（R）
- **搭配**：Animate、Choreograph（A）

### 2. pick-ui-library
- **來源**：S、A <https://aiforui.dev/skills/pick-ui-library>、R（SKILL.md 全文）
- **分類**：01 Before you build
- **用途**：「Picks the library for a frontend task from a short, curated list I use and trust.」（A）；「This prevents the agent from building a custom toast or installing an abandoned package.」（A）
- **適合**：「When you're wondering whether to build a component yourself or use a library.」（A）
- **不適合**：清單外的需求會直說，改用一般知識推薦；沒被要求時不換掉既有套件（「churn the dependency」，R）
- **範例 prompt**：`/pick-ui-library what should I use for the OTP input on the login page`、`/pick-ui-library we need a command menu, should we build it or install a library?`（A）
- **輸出**：一個推薦與理由；被要求時會安裝並接上（R）
- **精選清單**（R）：base-ui、cmdk、Sonner、Vaul、input-otp、Leva、motion／Framer Motion、NumberFlow、torph、Cobe、Satori、shiki、Liveline、recharts、dnd kit、Virtuoso、zustand、clsx、cva、next-themes
- **限制**：frontmatter 有 `disable-model-invocation: true`，Claude 不會自動叫用，要手動輸入 `/pick-ui-library`（R）
- **本專案備註**：清單幾乎都是 React 套件。Lumen 是純 JS，沒有 `package.json`，用處有限
- **搭配**：Ask Sonner、Prototyping（A）

### 3. prototype
- **來源**：S、A <https://aiforui.dev/skills/prototype>
- **分類**：01 Before you build
- **用途**：「Builds a few genuinely different versions of the UI you describe and puts them behind a switcher」（A）
- **適合**：「When you are in the exploration phase of your project or feature」（A）
- **不適合**：審查現有 UI、規劃修正、選套件（S）
- **範例 prompt**：`/prototype not sure if the share menu should be a modal or a popover`、`/prototype build me a new multi-step onboarding in three different ways`（A）
- **輸出**：每個版本在自己的路由全尺寸呈現，有切換器、編號、重播動畫的按鍵，可把選定版本存在網址。「After you choose one, it implements it and removes the prototype.」（A）
- **限制**：待確認
- **本專案備註**：Lumen 沒有前端路由，「每個版本一個路由」要怎麼套用，待實際試
- **搭配**：Design Engineering、Review Animations（A）

### 4. ask-emil
- **來源**：S、A <https://aiforui.dev/skills/ask-emil>
- **分類**：01 Before you build
- **用途**：「Describe your situation, it'll point you to the right one, or the right sequence of them.」（A）
- **適合**：「When you know what you want to do but not which skill does it.」（A）
- **不適合**：待確認
- **範例 prompt**：`/ask-emil the whole app feels slow, which skill should I run?`（A）
- **輸出**：建議；推薦前會先讀各 skill 的 SKILL.md，摘要「for orientation only」（S）
- **主流程**（S）：prototype（可選）→ pick-ui-library → animate → choreograph → gestures → animate-expo → ask-sonner
- **限制**：待確認

### 5. emil-design-eng
- **來源**：S、A <https://aiforui.dev/skills/emil-design-eng>
- **分類**：02 Building the interface
- **用途**：「The main skill. If you don't know which skill to use, use this one. It does a lot of things well, but is not as focused as the others.」（A）；README：「mostly animation, but also some design advice」（R）
- **適合**：「Use it whenever it's hard to pick a specific skill for the task.」（A）
- **不適合**：有專門 skill 的任務（A）
- **範例 prompt**：`/emil-design-eng review this popover and tell me what you'd change`（A）
- **輸出**：修改程式碼，審查時用「Before, After, Why table」（A）
- **具體做法**（A）：依使用頻率與情境決定要不要動；偏好自訂曲線，例如 `cubic-bezier(0.23, 1, 0.32, 1)`；按壓狀態、從觸發點長出的 popover、同組 tooltip 只有第一個延遲 500ms
- **限制**：S 的 Snyk 稽核為 Warn，原因沒寫，待確認

### 6. animate
- **來源**：S、A <https://aiforui.dev/skills/animate>
- **分類**：02 Building the interface
- **用途**：「Builds an animation from scratch while making the right decisions in the right order」（A）
- **適合**：「Use it when you want to animate an element and want to do it right.」（A）
- **不適合**：稽核程式碼、審 diff、找機會、React Native（S）
- **範例 prompt**：`/animate add a press state to all our buttons`（A）
- **輸出**：動畫程式碼；工具從「CSS transition, keyframes, WAAPI, or Motion」中選，可中斷，支援 reduced motion（A）
- **前後對照**（A）：「scale 0 → 1 · ease-in · 400ms in, 400ms out」改成「scale 0.95 → 1 · custom ease-out · 300ms in, 150ms out」
- **限制**：S 的 Snyk 為 Warn，原因待確認

### 7. choreograph
- **來源**：S、A <https://aiforui.dev/skills/choreograph>
- **分類**：02 Building the interface
- **用途**：「Coordinates several elements that animate together, avoiding generic grouped animations.」（A）
- **適合**：「When more than one thing moves at once」（A）
- **不適合**：單一動畫的曲線與時長，屬 animate（S）
- **範例 prompt**：`/choreograph the order confirmation screen just appears. Sequence the checkmark, title, and receipt`（A）
- **輸出**：每個元素分成「a lead, support, or detail」；錯開每個元素 30–80ms、總長約 300ms 內（A）；「Sequence only when order carries meaning」（S）

### 8. apple-design
- **來源**：S、A <https://aiforui.dev/skills/apple-design>
- **分類**：02 Building the interface
- **用途**：「Apple's principles for interface design and fluid motion, distilled from their WWDC design talks and translated for the web.」（A）
- **適合**：「As long as you want your product to feel like it belongs in the Apple ecosystem」（A）
- **範例 prompt**：`/apple-design the sheet feels dead when I let go of it`（A）
- **輸出**：游標 1:1 跟隨、放開時依動量投射落點、動畫從目前位置開始可中斷；也談材質、層次、字體（A）
- **本專案備註**：Lumen 要打包成 macOS app（Tauri，WKWebView），這個 skill 最貼近

### 9. gestures
- **來源**：S、A <https://aiforui.dev/skills/gestures>、R（SKILL.md 全文）
- **分類**：02 Building the interface
- **用途**：「Build drag, swipe, and sheet interactions that track the finger 1:1 and stay interruptible.」（R）
- **適合**：抽屜、sheet、滑動關閉、拖曳排序、下拉更新、長按確認，或手勢卡頓（R）
- **不適合**：已有函式庫能做的互動，抽屜預設「default to Vaul」（R）
- **範例 prompt**：`/gestures add drag to this notification so I can swipe it away`（A）
- **規則**（R）：按住時 1:1 追蹤不加緩動，放開後用帶初速的彈簧；「Never use a keyframe animation on anything a gesture can touch.」；觸控目標至少 44×44px；要在真的手機上測

### 10. mobile-native
- **來源**：S、A <https://aiforui.dev/skills/mobile-native>
- **分類**：02 Building the interface
- **用途**：「Makes your web app feel better on touch devices.」（A）
- **適合**：手機或觸控裝置（A）
- **不適合**：設計或審查動畫、React Native（S）
- **範例 prompt**：`/mobile-native our bottom bar sits under the home indicator`（A）
- **輸出**：hover 包進 `@media (hover: hover)`、移除點擊高亮、用 `dvh`、修輸入框放大、點擊延遲、瀏海安全區（A）
- **限制**：「If you can't run it on hardware, say which of the fixes below you can verify from code and which need a real device.」（S）
- **本專案備註**：Lumen 目前是桌面用，手機版還沒規劃

### 11. animation-performance
- **來源**：S、A <https://aiforui.dev/skills/animation-performance>
- **分類**：03 Refining and reviewing
- **用途**：「If your animation doesn't run at 60 frames per second, nothing else matters.」（A）
- **適合**：「When you encounter any performance issues with your animations.」（A）
- **不適合**：選曲線與時長、判斷要不要動、RN 執行緒（S）
- **範例 prompt**：`/animation-performance should I add will-change to these cards`（A）
- **輸出**：把 layout／paint 屬性換成合成層屬性（例如用 `transform` 代替 `margin`）；抓 React 每幀重新渲染、繼承的 CSS 變數、到處加 `will-change`（A）

### 12. break-ui
- **來源**：S、A <https://aiforui.dev/skills/break-ui>
- **分類**：03 Refining and reviewing
- **用途**：「Tries to break your UI by using worst-case data」（A）
- **適合**：「I personally use it before I ship any feature.」（A）
- **不適合**：重新設計元件（屬 prototype）、評品味、審動畫（S）
- **範例 prompt**：`/break-ui stress test this table with the worst data you can think of`（A）
- **輸出**：最壞資料集（長、短、缺漏、極大、空、非拉丁字、emoji）、「Demo data / Worst case」切換、報告與逐項修正（A）
- **本專案備註**：Lumen 的筆記標題、標籤、別名有長短中英混合，正好適用

### 13. review-animations
- **來源**：S、A <https://aiforui.dev/skills/review-animations>
- **分類**：03 Refining and reviewing
- **用途**：「A strict review that results in an approval or a block decision.」（A）
- **適合**：「Before merging or putting out a PR that involves animations.」（A）
- **不適合**：「does not write features, fix unrelated bugs, or review non-motion code」（S）
- **範例 prompt**：`/review-animations review the motion in my current branch`（A）
- **輸出**：每項附「exact values and file:line」，最後 Approve 或 Block（A）
- **限制**：規則在 STANDARDS.md，網站上沒公開，沒讀到（待確認）

### 14. find-animation-opportunities
- **來源**：S、A <https://aiforui.dev/skills/find-animation-opportunities>
- **分類**：04 Looking at the whole app
- **用途**：找值得加動畫的地方，也說哪些不該動（A）
- **適合**：「Honestly, whenever you feel like it.」（A）
- **不適合**：審查現有動畫、規劃修正、實作（S）
- **範例 prompt**：`/find-animation-opportunities find animation opportunities in the account menu. People open it all day, factor this in`（A）
- **輸出**：「It's read-only, it only suggests what could be done.」（A）

### 15. improve-animations
- **來源**：S、A <https://aiforui.dev/skills/improve-animations>
- **分類**：04 Looking at the whole app
- **用途**：「Audits all the animations in your codebase and writes prioritized, self-contained plans that any agent can execute.」（A）
- **不適合**：審單一 diff、自己實作（S：「does not implement fixes itself」）
- **範例 prompt**：`/improve-animations quick pass on easing across the app`（A）
- **輸出**：計畫；「Leaves your source untouched until you hand a plan off.」（A）。計畫寫在哪個檔案：待確認
- **差異**：總覽說交給 subagents，skill 頁說交給較便宜的模型

### 16. remove-animations
- **來源**：S、A <https://aiforui.dev/skills/remove-animations>
- **分類**：04 Looking at the whole app
- **用途**：「The opposite of finding opportunities: removes the animations your app doesn't need.」（A）
- **適合**：檢查 app 或某功能有沒有多餘動畫（A）
- **不適合**：新增動畫（S）
- **範例 prompt**：`/remove-animations we animate way too much, tone it down`（A）
- **輸出**：「Removes or shortens the ones that don't make sense」，列出保留項與原因（A）；目標包括鍵盤操作的動畫、高頻介面、功能性資料、純裝飾

### 17. animate-expo
- **來源**：S、A <https://aiforui.dev/skills/animate-expo>
- **分類**：05 Other skills
- **用途**：React Native／Expo 動畫，「Made in collaboration with the Expo team.」（A）
- **適合**：Expo 或 React Native app（A）
- **輸出**：原生 stack 轉場、form sheet、原生 tab；Reanimated 在 UI 執行緒跑動畫；觸覺回饋（A）
- **需求**：頁面提到 Reanimated 4、Worklets，但沒列為需求（待確認）
- **本專案備註**：用不到

### 18. ask-sonner
- **來源**：S、A <https://aiforui.dev/skills/ask-sonner>
- **分類**：05 Other skills
- **用途**：「Your guide to Sonner, my toast library.」（A）
- **適合**：「When you are using Sonner」（A）
- **範例 prompt**：`/ask-sonner my Tailwind classes don't work on the toasts`（A）
- **輸出**：在根部掛一個 `<Toaster />`；`toast.promise` 等用法；修正重複、樣式失效、被 modal 蓋住（A）
- **本專案備註**：Sonner 是 React 函式庫，Lumen 沒用

### 19. learn-taste
- **來源**：S、A <https://aiforui.dev/skills/learn-taste>
- **分類**：05 Other skills
- **用途**：「Collects every design correction you made during a session and turns each one into a strict rule with reasoning」（A）
- **適合**：「At the end of a session where you corrected the agent more than once.」（A）
- **不適合**：改元件程式碼（S：不改元件程式碼）
- **範例 prompt**：`/learn-taste prune, DESIGN.md is getting long`（A）
- **輸出**：提議規則，使用者同意的才寫進 `DESIGN.md`；「Never invent a why」；能用 lint 規則就建議 lint（S、A）
- **限制**：可讀過去的對話紀錄，Claude Code 存在 `~/.claude/projects/<project>/` 的 JSONL（S）。這些紀錄含使用者的筆記內容，見 [installation-plan.md](installation-plan.md) 的風險
- **本專案備註**：A 的示範把寫進 `CLAUDE.md` 當反例，改寫 `DESIGN.md`

### 20. write-swift（只在 skills.sh）
- **來源**：只有 S <https://www.skills.sh/emilkowalski/skills/write-swift>；A 與 R 的 README 都沒有
- **分類**：A 沒有分類
- **用途**：寫現代 Swift，「current through Swift 6.4」，以 Swift 6.3 為基準，標 ⚠ 的是尚未發布的 6.4 功能，並發用 Swift 6.2 模型（S）
- **適合、不適合、範例 prompt、輸出**：待確認（SKILL.md 讀不到）
- **需求**：會要求先看 `swift --version`（S）
- **限制**：S 警告「Contains Shell Commands. This skill contains shell command directives (`!`command``) that may execute system commands. Review carefully before installing.」
- **本專案備註**：Lumen 用 Tauri（Rust），不寫 Swift，除非之後做 macOS 原生外掛
