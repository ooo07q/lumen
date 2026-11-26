# 安裝計畫

2026-11-27 已照第 1 節的指令裝好第一批（第 9 節）。實際寫入的位置見第 4 節的「實際結果」；第二批之後還沒裝。

**已決定（2026-11-26）**：
- 裝在使用者目錄 `~/.claude/skills/`（`-g`），不裝進 Lumen 專案。
- 關掉匿名使用資料：每個 `npx skills` 指令前都加 `DISABLE_TELEMETRY=1`。

資料來源：
- CLI README：<https://github.com/vercel-labs/skills>
- 指令說明：<https://github.com/vercel-labs/skills/blob/main/docs/commands.md>
- 各 agent 的路徑：<https://github.com/vercel-labs/skills/blob/main/docs/agents.md>
- 疑難排解：<https://github.com/vercel-labs/skills/blob/main/docs/troubleshooting.md>
- skills.sh 說明：<https://www.skills.sh/docs>、<https://www.skills.sh/docs/faq>

## 1. 官方安裝指令

兩個網站寫法不同，都照原樣列出：

| 出處 | 指令 |
|---|---|
| skills.sh 作者頁 | `npx skills add emilkowalski/skills` |
| skills.sh 各 skill 頁 | `npx skills add https://github.com/emilkowalski/skills --skill <名稱>` |
| aiforui.dev 總覽、GitHub README | `npx skills@latest add emilkowalski/skills` |
| aiforui.dev 各 skill 頁 | `npx skills@latest add emilkowalski/skills --skill <名稱>` |

差別只在有沒有 `@latest`，以及來源寫成 `owner/repo` 還是完整網址。CLI 兩種都接受（commands.md 的來源格式）。

本專案建議的寫法（只裝 Claude Code，指定 skill，不互動）：

```bash
DISABLE_TELEMETRY=1 npx skills@latest add emilkowalski/skills \
  --skill emil-design-eng --skill review-animations --skill animation-vocabulary --skill ask-emil \
  -a claude-code -g -y
```

`DISABLE_TELEMETRY=1`（或 `DO_NOT_TRACK=1`）關掉匿名使用資料，也會關掉安全稽核的查詢（README）。更新、移除、檢查時也要加。

- `-a claude-code`：只裝給 Claude Code（commands.md：「Target specific agents」）
- `-g`：裝到使用者目錄，不裝進專案（「Install to user directory instead of project」）
- `-s/--skill`：只裝指定的 skill
- `-y`：不跳確認（「Skip all confirmation prompts」）
- 不要用 `--all`：它會「Install all skills to all agents without prompts」

要先看清單、不安裝：`npx skills add emilkowalski/skills -l`（`-l, --list`：「List available skills without installing」）。

## 2. 建議的安裝時機

- **現在不裝**：Lumen 正在跑 AI 整理的測試，路線圖下一步是 CLAUDE.md，接著是 Tauri 打包。
- **UI/UX 大改正式開始、要動 `static/` 的 CSS 和 JS 之前**，先裝第一批（見第 9 節）。
- 一次只加一批，每批裝完照第 6 節驗證，再用一兩個實際任務試過，才加下一批。

## 3. 安裝前要檢查的項目

1. **Node 版本**：CLI 要 Node.js 22.20 以上（README）。本機是 v24.11.1，符合。
2. **名稱衝突**：`~/.claude/skills/` 已有 jev-effort-high、jev-effort-low、model-auto-switch、model-auto-switch-workspace、nlm、style、synced。Emil 的 20 個名稱都不重複。安裝前再跑一次 `ls ~/.claude/skills/` 確認。
3. **專案目錄**：`~/Lumen` 目前沒有 `.claude/`、`.agents/`、`skills-lock.json`。在專案內安裝（不加 `-g`）會建立這些，而 Lumen 是公開 repo，見第 5 節。
4. **先看內容再裝**：skills.sh 寫「we cannot guarantee the quality or security of every skill listed」（<https://www.skills.sh/docs>）。安裝前到 GitHub 讀要裝的 SKILL.md。
5. **稽核結果**（各 skill 頁）：emil-design-eng、animate 的 Snyk 是 Warn；write-swift 標「Contains Shell Commands」。這三個要特別讀過。
6. **遙測**：CLI 預設送匿名使用資料（「collects anonymous usage data」）。已決定關掉：每個指令前加 `DISABLE_TELEMETRY=1`（troubleshooting.md）。

## 4. 可能寫入的目錄與檔案

依 agents.md 和 README：

| 範圍 | Claude Code 的位置 | 其他會建立的 |
|---|---|---|
| 專案（預設） | `<專案>/.claude/skills/<名稱>/` | 主副本在 `<專案>/.agents/skills/<名稱>/`，`.claude/skills/` 是指向它的 symlink（預設「Symlink (Recommended)」）；鎖定檔 `skills-lock.json`（記錄來源與 `computedHash`，位置只寫「project」，推測在專案根目錄，待確認） |
| 使用者（`-g`） | `~/.claude/skills/<名稱>/` | 全域鎖定檔，檔名與位置文件沒寫，待確認 |

- `--copy` 會改用複製，不建立 symlink（「Copy files instead of symlinking」）。
- 用 `-g` 時，主副本放在哪裡、是否也是 symlink，文件沒寫清楚，待確認。裝完用 `ls -la ~/.claude/skills/` 看。
- 安裝本身不會改 `CLAUDE.md`、`AGENTS.md` 或 `settings.json`，文件沒提到會改。
- **實際結果（2026-11-27，CLI 1.9.0，`-g -a claude-code`）**：
  - 只給 Claude Code 時是直接複製（`copied`），沒有建立 `~/.agents/skills/` 主副本，也沒有 symlink。
  - 寫入 `~/.claude/skills/<名稱>/`（SKILL.md，review-animations 另有 STANDARDS.md）。
  - 全域鎖定檔是 `~/.agents/.skill-lock.json`，記錄來源、commit、資料夾雜湊。
  - npx 把 CLI 放在 npm 快取。
  - `settings.json`、Lumen repo 都沒變。
- **skill 用的時候**可能寫檔：
  - learn-taste 寫 `DESIGN.md`；
  - prototype 加路由與切換器；
  - break-ui 加測試資料與切換器；
  - improve-animations 寫計畫（檔名待確認）。

## 5. 避免覆蓋既有設定

- **用 `-g -a claude-code`，不在專案內安裝**：不會在公開的 Lumen repo 裡建立 `.agents/`、`.claude/`、`skills-lock.json`。
- 如果之後決定裝進專案，先決定這些要不要進 git。不進就加到 `.gitignore`，要進就讓別人 clone 後能用 `npx skills experimental_install` 還原。這要你決定。
- **不要用 `--all`、`-a '*'`**：會裝給偵測到的所有 agent。
- **不要用 `--rename`** 改成跟既有 skill 同名。
- **移除時**：`remove --all` 和 `--skill '*'` 只刪鎖定檔記錄的 skill，手寫的資料夾「listed as skipped and never deleted」（commands.md），所以不會刪到你自己的 style、nlm 等。仍建議指名移除，不用 `--all`。
- 安裝前把 `~/.claude/skills/` 的清單存一份（`ls -la ~/.claude/skills/ > 某處`），裝完比對。

## 6. 安裝後驗證

1. `npx skills list -g -a claude-code`：列出已安裝的 skill（`list`：「Similar to `npm ls`」）。
2. `ls -la ~/.claude/skills/`：新的資料夾在，舊的七個都還在。
3. `npx skills check`：有更新或本地改動時 exit code 1。
4. 開新的 Claude Code session，輸入 `/` 看選單裡有沒有新 skill。再跑一個不改檔的試驗：`/animation-vocabulary the thing where the button shrinks a bit when you click it`，應該回一個術語。
5. `pick-ui-library` 設了 `disable-model-invocation: true`，Claude 不會自動用它。只有手動輸入 `/pick-ui-library` 才會跑，這是正常的。

## 7. 更新與移除

| 動作 | 指令（commands.md） |
|---|---|
| 檢查有沒有更新 | `npx skills check` |
| 更新全部 | `npx skills update`（會問範圍）；只更新全域 `npx skills update -g` |
| 更新一個 | `npx skills update <名稱>` |
| 固定版本 | 來源寫成 `emilkowalski/skills@<tag 或 commit>`（`owner/repo@v1.2.3`） |
| 移除一個 | `npx skills remove <名稱> -g -a claude-code`（別名 `rm`） |
| 移除整個來源 | `npx skills remove emilkowalski/skills`（刪掉這個來源的所有 skill） |

更新後再照第 6 節驗證，並看 GitHub 的 commit 記錄有什麼改動。

## 8. 安裝失敗的替代方案

1. **手動安裝**：從 <https://github.com/emilkowalski/skills> 下載 `skills/<名稱>/` 資料夾（SKILL.md 和附檔，如 review-animations 的 STANDARDS.md、ask-sonner 的 API.md），放到 `~/.claude/skills/<名稱>/`。CLI 不會追蹤手動安裝的 skill，更新要自己來，`remove --all` 也不會刪它。
2. **不安裝，只用一次**：`npx skills use emilkowalski/skills@<名稱> | claude` 把 skill 當成一次性的 prompt（README 的 `use` 指令）。
3. **固定在某個 commit**：更新後壞了，就裝回 `emilkowalski/skills@<舊 commit>`。
4. **GitHub 連不上**：這次讀 SKILL.md 時 GitHub 回了 HTTP 503。遇到就晚點再試，不要一直重試。
5. **權限錯誤**：確認目標目錄可寫（README：「Ensure you have write access to the target directory」）。

## 9. 建議的分批

| 批次 | Skill | 理由 |
|---|---|---|
| 第一批 | emil-design-eng、review-animations、animation-vocabulary、ask-emil | 主 skill、審查、詞彙、導覽。只有 emil-design-eng 會改檔 |
| 第二批 | animate、choreograph、apple-design、animation-performance、remove-animations、find-animation-opportunities、improve-animations、break-ui | 實際改 Lumen 的介面時再裝 |
| 視需要 | prototype、learn-taste、gestures | prototype 要先確認在沒有路由的 Lumen 怎麼放；learn-taste 會讀過去的對話紀錄，見第 10 節 |
| 不裝 | animate-expo、ask-sonner、pick-ui-library、mobile-native、write-swift | Lumen 不是 React Native，沒用 Sonner 和 React，目前也不做手機版。write-swift 有 shell 指令警告，Lumen 也不寫 Swift |

## 10. 風險

- **品質與安全**：skills.sh 不保證每個 skill 的品質或安全。有兩個 Snyk Warn、一個 shell 指令警告。
- **learn-taste 讀對話紀錄**：可以讀 `~/.claude/projects/<project>/` 的 JSONL。這些紀錄有你的筆記內容。skill 在本機執行，讀紀錄不會把內容送出去，但它整理出的規則會寫進 `DESIGN.md`；放在公開 repo 時要先看過內容。
- **遙測**：預設送出 skill 名稱與來源；已決定關掉（`DISABLE_TELEMETRY=1`）。
- **不是為 Lumen 寫的**：很多做法假設 React、Motion、Tailwind。Lumen 是純 JS 和 CSS，請 skill 依 Lumen 的寫法實作，見 [prompt-library.md](prompt-library.md)。
- **規則看不到**：review-animations 依「my rules」（STANDARDS.md）審查。這次沒讀到 STANDARDS.md，裝之前要讀。
