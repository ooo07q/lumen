# UI 工作流程

依 aiforui.dev 的分類（<https://aiforui.dev/skills>，01 Before you build → 05 Other skills）排成 12 個流程。每個 skill 的出處見 [skills-catalog.md](skills-catalog.md)，prompt 範本見 [prompt-library.md](prompt-library.md)。

所有流程共同的驗收，也就是 Lumen 原本就有的檢查：
- `node -e "new Function(...)"` 語法檢查 `static/*.js`；
- `python3 tools/i18n_check.py` 結果為 0 缺漏；
- 動到編輯器時，跑 400 篇筆記往返測試，結果為 0 changed；
- 在 Safari 引擎（WKWebView 測試程式）和 Chrome 各試一次；
- 中英介面都看過。

---

## 1. 開始新 UI 專案前（01 Before you build）

- **觸發**：要大改某個畫面，或不知道該從哪個 skill 開始。
- **Skill**：`ask-emil`；講不清效果時用 `animation-vocabulary`。
- **建議 prompt**：`/ask-emil 我要重做 Lumen 的筆記列表和側欄，從哪個 skill 開始、順序是什麼？`
- **步驟**：
  1. 寫下要改的畫面與原因。
  2. `/ask-emil` 拿到 skill 順序。
  3. 用 `/animation-vocabulary` 把想要的效果換成正確術語。
  4. 把順序記在這次的工作筆記。
- **驗收**：每個畫面有一串明確的 skill 順序；想要的效果都有術語。
- **陷阱**：ask-emil 的主流程含 animate-expo、ask-sonner（<https://www.skills.sh/emilkowalski/skills/ask-emil>），Lumen 用不到，要跳過。

## 2. 建立 prototype

- **觸發**：同一個介面有兩三種做法拿不定。
- **Skill**：`prototype`。
- **建議 prompt**：`/prototype 筆記屬性區做三種版本：收合摘要列、側邊面板、行內欄位。Lumen 是純 JS，不要新增路由，用開發用切換開關。`
- **步驟**：
  1. 說明要比較的介面與限制。
  2. 讓它做版本與切換器。
  3. 在 Safari 引擎和 Chrome 實際切換使用。
  4. 選定一個，請它實作並移除原型（<https://aiforui.dev/skills/prototype>：「After you choose one, it implements it and removes the prototype」）。
- **驗收**：版本之間真的不同，不是換顏色；選定後 repo 裡沒有留下原型程式碼（`git status` 檢查）。
- **陷阱**：skill 預設每個版本一個路由，Lumen 沒有路由；原型留在 `static/` 忘了刪。

## 3. 選擇 UI library

- **觸發**：想加一個元件（toast、指令選單、虛擬捲動等），不確定要不要用套件。
- **Skill**：`pick-ui-library`（只能手動呼叫）。
- **建議 prompt**：`/pick-ui-library Lumen 是不用建置步驟的純 JS，要做指令選單：自己寫還是有可直接用 <script> 載入、不需 React 的套件？`
- **步驟**：
  1. 說明需求與 Lumen 的限制。
  2. 拿到推薦。
  3. 確認推薦的套件不需要 React 與建置。
  4. 需要的話自己寫。
- **驗收**：結論說明為什麼用或不用；沒有新增 `package.json` 或 node_modules。
- **陷阱**：精選清單大多是 React 套件（<https://github.com/emilkowalski/skills/blob/main/skills/pick-ui-library/SKILL.md>）。Tauri 打包時外部 CDN 要另外處理。

## 4. 實作介面（02 Building the interface）

- **觸發**：開始改某個畫面的版面與互動。
- **Skill**：`emil-design-eng`；有專門 skill 時改用專門的。
- **建議 prompt**：`/emil-design-eng 重做 Lumen 的側欄：按壓狀態、hover、展開收合，用 static/style.css 的 token，不加 React。`
- **步驟**：
  1. 指定檔案（`static/style.css`、`static/app.js`）。
  2. 讓它改並附 Before／After／Why 表。
  3. 看表格逐項確認。
  4. 跑共同驗收。
- **驗收**：有 Before／After／Why 表；只動指定檔案；深淺色都正常。
- **陷阱**：主 skill 什麼都做，範圍容易變大；開始前先講清楚只改哪些檔案。

## 5. 實作動畫與手勢

- **觸發**：某個元素要動，或要拖、滑。
- **Skill**：`animate`（單一）、`choreograph`（多個）、`gestures`（手勢）、`apple-design`（Apple 手感）。
- **建議 prompt**：`/animate 筆記屬性區展開收合的動畫，用 CSS transition，支援 prefers-reduced-motion。`
- **步驟**：
  1. 讓 skill 先判斷要不要動。
  2. 實作。
  3. 多個元素再用 `/choreograph` 排時序。
  4. 跑 `/review-animations`（流程 9）。
- **驗收**：
  - 有理由說明為什麼要動；
  - 可中斷；
  - reduced motion 時不動或縮短；
  - 錯開每個元素 30–80ms、總長約 300ms 內（<https://aiforui.dev/skills/choreograph>）。
- **陷阱**：
  - skill 選了 Motion（React）；
  - 手勢用 keyframe 動畫，違反「Never use a keyframe animation on anything a gesture can touch」（gestures SKILL.md）；
  - 編輯器內加動畫影響打字。

## 6. 行動裝置體驗

- **觸發**：要在手機或平板上用 Lumen（目前沒規劃）。
- **Skill**：`mobile-native`。
- **建議 prompt**：`/mobile-native 在 iPhone Safari 開 Lumen：輸入框聚焦會放大、底部列被 home indicator 蓋住。`
- **步驟**：
  1. 描述症狀。
  2. 讓它對照症狀表修正。
  3. 看它標出哪些要真機驗證。
  4. 在真機測。
- **驗收**：它列出的「需要真機」項目都在真機確認過。
- **陷阱**：只在桌面瀏覽器模擬就當作完成（<https://www.skills.sh/emilkowalski/skills/mobile-native>）。

## 7. 效能優化（03 Refining and reviewing）

- **觸發**：動畫卡、捲動或拖曳掉幀，筆記多時特別明顯。
- **Skill**：`animation-performance`。
- **建議 prompt**：`/animation-performance 筆記列表有 3000 篇時展開資料夾會卡，找原因再改。`
- **步驟**：
  1. 重現並描述。
  2. 讓它先找掉幀原因（<https://aiforui.dev/skills/animation-performance>：先找原因再改程式）。
  3. 改用合成層屬性。
  4. 用 3000 篇以上的測試筆記庫再試。
- **驗收**：在 Safari 引擎和 Chrome 都不掉幀；沒有到處加 `will-change`。
- **陷阱**：問題不在動畫，在 DOM 數量（大列表），要用虛擬捲動或分批渲染。

## 8. UI 壓力測試

- **觸發**：功能做完、上線前。
- **Skill**：`break-ui`。
- **建議 prompt**：`/break-ui 測筆記列表、屬性區、搜尋結果：超長標題、全中文、emoji、上百個標籤、空筆記庫。`
- **步驟**：
  1. 讓它列每個欄位最長可能多長。
  2. 建最壞資料。
  3. 切換「Demo data / Worst case」看結果。
  4. 逐項修。
- **驗收**：報告的每項都修了或有說明；測試資料不寫進使用者的筆記庫，只放測試筆記庫。
- **陷阱**：測試資料留在 repo 或寫進真實 vault；忘了中英兩種介面文字長度不同。

## 9. 動畫審查

- **觸發**：合併或 commit 含動畫的改動前。
- **Skill**：`review-animations`。
- **建議 prompt**：`/review-animations 審這次 diff 裡 static/style.css 和 static/wys.js 的動態。`
- **步驟**：
  1. 審 diff。
  2. 逐項看 Before／After／Why 和檔名:行號。
  3. Block 就修。
  4. 再審，直到 Approve。
- **驗收**：結論是 Approve；不同意的項目有寫理由，由你決定。
- **陷阱**：只審動畫，不審其他程式碼（「does not ... review non-motion code」）。規則在 STANDARDS.md，這次沒讀到。

## 10. 全站動畫策略（04 Looking at the whole app）

- **觸發**：大改告一段落，要看整體。
- **Skill**：先 `find-animation-opportunities`（唯讀），再 `improve-animations`（只寫計畫）。
- **建議 prompt**：`/improve-animations 稽核 Lumen 全部動畫（static/style.css、app.js、wys.js），寫成可以分別執行的計畫。`
- **步驟**：
  1. 先找機會。
  2. 再出計畫。
  3. 你挑要做的。
  4. 逐項實作。
  5. 每項跑流程 9。
- **驗收**：計畫有優先順序和確切數值；稽核階段沒有改到原始碼（`git status` 乾淨）。
- **陷阱**：一次把所有計畫都做掉；計畫存放位置待確認，要先問它寫在哪。

## 11. 移除不必要動畫

- **觸發**：app 感覺慢、動畫太多。
- **Skill**：`remove-animations`。
- **建議 prompt**：`/remove-animations Lumen 是每天用的筆記工具，鍵盤操作和常開的面板不該有動畫，列出保留的和原因。`
- **步驟**：
  1. 讓它列出移除、縮短、保留的項目。
  2. 你確認。
  3. 套用。
  4. 跑共同驗收。
- **驗收**：鍵盤操作即時反應（<https://aiforui.dev/skills/remove-animations>：「moves on keydown, 0ms」）；有保留清單與理由。
- **陷阱**：全刪。S 頁說動畫能銜接突兀變化時，刪掉是錯的。

## 12. Expo／Sonner／個人偏好（05 Other skills）

- **Expo**（`animate-expo`）：只在 Expo 或 React Native 專案用，Lumen 不適用。
- **Sonner**（`ask-sonner`）：只在用 Sonner 的 React 專案用，Lumen 不適用。Lumen 的提示訊息是自己寫的。
- **個人偏好**（`learn-taste`）：
  - **觸發**：一個 session 裡糾正 agent 不只一次。
  - **建議 prompt**：`/learn-taste 整理這次 session 我修正過的地方，提議規則，先給我看，不要自己寫。`
  - **步驟**：
    1. 讓它提議規則與理由。
    2. 逐條同意或拒絕。
    3. 只寫同意的進 `DESIGN.md`。
  - **驗收**：每條規則都來自你實際的修正，沒有它自己編的理由（「Never invent a why」）。
  - **陷阱**：它能讀過去的對話紀錄（含筆記內容）。`DESIGN.md` 放在公開 repo 前要看過；不要讓它寫 `CLAUDE.md`。
