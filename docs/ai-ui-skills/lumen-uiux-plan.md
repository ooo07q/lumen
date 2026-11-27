# Lumen 介面改造：工作筆記

照 [workflows.md](workflows.md) 一步步做。每一步做完，在下面記結果。

## 第 1 步：要改的畫面和原因（流程 1）

2026-11-27。`/ask-emil` 只能由你手動叫用，這一步由 Claude 讀過它的 SKILL.md 後照它的規則排出順序。

現況：
- `static/style.css` 591 行、`app.js` 2401 行、`wys.js` 619 行、`index.html` 71 行。
- 動畫只有 4 個：轉圈、AI 打字游標、連接進度條（含 reduced motion）。
- 選單、對話框、提示訊息出現和消失都沒有過渡，按鈕沒有按下的回饋。

| 畫面 | 包含 | 要改的原因 |
|---|---|---|
| F. 共用元件 | 對話框、選單、提示訊息、按鈕、輸入框 | 每個畫面都用到；先統一，後面的畫面才一致 |
| A. 上方列 | 左右欄開關、上一頁、筆記庫選單、設定、搜尋與快速結果、Jev | 每天最常點的地方 |
| B. 左欄 | 日記／筆記／附件／知識庫、篩選、資料夾樹、待整理 | 項目多，hover 和選取狀態要清楚 |
| C. 筆記 | 分頁、標題列、工具列、閱讀、編輯器、屬性、版本、比較、附件檢視 | 主要工作區；編輯器不能因動畫影響打字 |
| D. 右欄「這篇」 | 建議、整理狀況、潛在連結、已連結、誰連到這頁 | 資訊多，層次要分清楚 |
| E. 右欄「AI」 | 對話、整理的計畫和步驟、對話紀錄、@ 選單 | 狀態多（找頁、回答、規劃、寫入），要看得出進度 |
| G. 開始畫面 | 選筆記庫、建立筆記庫 | 第一次使用的人先看到這裡 |

想要的效果，用正確的名稱（`animation-vocabulary`）：
- 選單、快速結果：從觸發的位置放大淡入（origin-aware pop in）
- 對話框：淡入加輕微放大（fade + scale from 0.97）
- 提示訊息：從下方滑入（slide up）
- 按鈕：按下時微縮（press feedback, scale 0.97）
- 右欄區塊、步驟清單：展開收合（collapse）
- 鍵盤操作（⌘K 類、方向鍵、打字）：不加動畫

## Skill 順序

| 步驟 | 流程 | Skill | 做什麼 |
|---|---|---|---|
| 2 | 4 | `emil-design-eng` | 一個畫面一個畫面改：按壓、hover、focus、間距、層次。順序 F → A → B → C → D → E → G。每個畫面附 Before／After／Why 表 |
| 3 | 5 | `animate`、`choreograph` | 只在有理由的地方加：選單、對話框、提示訊息、展開收合；鍵盤和打字不動 |
| 4 | 9 | `review-animations` | 審第 3 步的動畫。這個 skill 只能你叫用；你沒叫時由 Claude 照 STANDARDS.md 自審 |
| 5 | 8 | `break-ui` | 用最壞的資料測：超長標題、全中文、emoji、空筆記庫、上百個標籤。測試資料只放 LumenTest |
| 6 | 7 | `animation-performance` | 5000 篇筆記的資料夾樹、長筆記捲動 |
| 7 | 10、11 | `improve-animations`、`remove-animations` | 全部做完再看整體：缺的、多的 |

不做：
- 流程 2 `prototype`、流程 3 `pick-ui-library`：沒裝。遇到拿不定的設計再裝 prototype；Lumen 不加套件。
- 流程 6 `mobile-native`：目前不做手機版。
- 流程 12：Expo、Sonner 用不到；`learn-taste` 會讀對話紀錄，要用時先問。

每一步都跑共同驗收（workflows.md 開頭）：語法檢查、i18n 0 缺漏、動到編輯器時跑往返測試、Safari 引擎和 Chrome、中英介面。

## 第 2 步：共用元件（流程 4，emil-design-eng）

2026-11-27。只改 `static/style.css`，另在 `app.js` 的 `applyView` 加一行（切換主題時不淡入淡出）。

- 新增共用 token：`--ease-out`、`--ease-in-out`、`--ring`、`--shadow-pop`、`--shadow-modal`、`--backdrop`、`--hover`；深色模式有自己的陰影和遮罩。
- 按鈕：只過渡顏色、邊框和 transform；按下 `scale(0.97)`（選單項目和文字連結除外）；hover 只在有滑鼠的裝置；停用時半透明。
- 焦點：按鈕和連結用鍵盤時有 2px 外框；輸入框統一「邊框變色 + 3px 淺色光暈」。
- 次要按鈕 hover 不再變紅（紅色留給刪除）。
- 選單、快速結果、提示訊息共用 `--shadow-pop`；對話框和連接 AI 共用 `--shadow-modal` 與遮罩。
- 驗收：語法檢查、i18n 0 缺漏、WebKit 淺色和深色截圖。
