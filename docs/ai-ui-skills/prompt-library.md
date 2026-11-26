# Prompt 範本

每個 skill 有四種版本：**一般**、**Lumen**（本專案）、**嚴格審查**、**修 bug／重構**。一般版取自或改寫自兩個網站的範例 prompt（出處見 [skills-catalog.md](skills-catalog.md)），其他三種是依本專案寫的。

Lumen 版都要附上這段專案背景，複製時一起貼：

```
專案背景：Lumen 是本機的筆記 app。前端是 static/ 下的純 JS 與 CSS（app.js、wys.js 編輯器、props.js 屬性、
style.css），沒有 React、沒有建置步驟、沒有 package.json。之後用 Tauri 打包，macOS 上跑在 WKWebView（Safari 引擎），
所以要在 Safari 和 Chrome 都正常。顏色和尺寸用 style.css :root 的 token，深淺色都要支援。介面文字有中英兩版
（i18n-en.js），新文字要加英文。不要新增依賴、不要改編輯器把未改動的 Markdown 改寫。只改我指定的檔案。
```

下面以 `〔背景〕` 代表這段。

---

## animation-vocabulary
- **一般**：`/animation-vocabulary what's it called when one shape turns into another one?`
- **Lumen**：`/animation-vocabulary 筆記從列表打開時，標題像是從列表那一行移到編輯區頂端，這叫什麼？給我一個主要術語和一兩個相近的。`
- **嚴格審查**：`/animation-vocabulary 我們設計文件用了 "fade"、"slide"、"pop" 這三個詞描述屬性區的動畫，逐一說明它們是不是精確的術語，不精確就給正確的。`
- **修 bug／重構**：`/animation-vocabulary 側欄收合時內容會「先縮再跳」，這個問題叫什麼？我要用正確術語去問 /animation-performance。`

## pick-ui-library
- **一般**：`/pick-ui-library what should I use for the OTP input on the login page`
- **Lumen**：`/pick-ui-library 〔背景〕 要做指令選單（⌘K）：有沒有不需 React、可直接用 <script> 載入的套件？沒有的話自己寫要注意什麼？`
- **嚴格審查**：`/pick-ui-library 〔背景〕 檢查 static/ 裡我們自己寫的 toast、選單、拖曳，哪些應該換成套件、哪些自己寫比較好，每項給理由。不要安裝任何東西。`
- **修 bug／重構**：`/pick-ui-library 〔背景〕 搜尋結果超過 2000 筆時列表很卡，該用虛擬捲動套件還是自己分批渲染？只給建議，不要改依賴。`

## prototype
- **一般**：`/prototype try three different directions for the download button`
- **Lumen**：`/prototype 〔背景〕 筆記屬性區做三個真正不同的版本：收合摘要列、右側面板、行內欄位。Lumen 沒有路由，用開發用的切換開關（數字鍵切換），選定後實作並移除原型。`
- **嚴格審查**：`/prototype 〔背景〕 我覺得你給的三個版本太像，重做：每個版本的資訊層級和互動方式都要不同，並寫出每個版本的取捨。`
- **修 bug／重構**：`/prototype 〔背景〕 目前的「連接 AI」流程使用者常卡住，做三個流程的版本讓我比較，不要動後端 API。`

## ask-emil
- **一般**：`/ask-emil I just built a settings page, what should I check before shipping?`
- **Lumen**：`/ask-emil 〔背景〕 我要大改 Lumen 的整體介面（側欄、筆記列表、編輯器、AI 面板），給我 skill 的順序，略過 Expo 和 Sonner。`
- **嚴格審查**：`/ask-emil 這次改了屬性區和編輯器工具列，合併前我該依序跑哪些審查 skill？每個說明要找什麼。`
- **修 bug／重構**：`/ask-emil 整個 app 感覺很慢，但不確定是動畫還是渲染，先用哪個 skill 找原因？`

## emil-design-eng
- **一般**：`/emil-design-eng make this button feel more responsive`
- **Lumen**：`/emil-design-eng 〔背景〕 重做 static/style.css 的按鈕與側欄項目：按壓狀態、hover（只在有 hover 的裝置）、focus 樣式。附 Before／After／Why 表。`
- **嚴格審查**：`/emil-design-eng 〔背景〕 審 static/style.css 和 static/app.js 的互動細節，不要改檔，列出每個問題的 Before／After／Why 與檔名:行號，依影響排序。`
- **修 bug／重構**：`/emil-design-eng 〔背景〕 tooltip 每個都等 500ms 才出現，改成同一組裡第一個之後立刻出現，只改 tooltip 相關的程式。`

## animate
- **一般**：`/animate animate this dropdown so it opens from the button`
- **Lumen**：`/animate 〔背景〕 屬性區展開收合加動畫：先判斷該不該動；要動就用 CSS transition，從標題列展開，可中斷，prefers-reduced-motion 時不動。`
- **嚴格審查**：`/animate 〔背景〕 這是我寫的選單動畫（static/style.css .menu），照你會通過嚴格審查的標準重寫，說明每個數值的理由。`
- **修 bug／重構**：`/animate 〔背景〕 對話框從 scale 0 長出來、進出都 400ms，改成正確的進出場，不改其他樣式。`

## choreograph
- **一般**：`/choreograph when I delete a card from this list the others jump into place. Fix it`
- **Lumen**：`/choreograph 〔背景〕 刪除筆記後列表其他項會跳上來，排好離開與補位的時序，總長 300ms 內，鍵盤刪除時不要動畫。`
- **嚴格審查**：`/choreograph 〔背景〕 審 AI 面板打開時的所有動態（面板、步驟清單、按鈕），每個元素標出 lead／support／detail，哪些應該不動。只報告不改。`
- **修 bug／重構**：`/choreograph 〔背景〕 AI 整理完成時，報告、變更清單、按鈕同時跳出來很亂，重排順序，只在順序有意義時才錯開。`

## apple-design
- **一般**：`/apple-design what spring should I use for this drawer`
- **Lumen**：`/apple-design 〔背景〕 Lumen 會打包成 macOS app，讓側欄拖曳調寬度和收合像 macOS 原生：1:1 跟隨、放開時依速度決定收合或展開。`
- **嚴格審查**：`/apple-design 〔背景〕 依 Apple 的流暢介面原則審 Lumen 的面板與側欄，列出哪裡不能中斷、哪裡沒從目前位置開始動。只報告。`
- **修 bug／重構**：`/apple-design 〔背景〕 側欄收合動畫做到一半再按一次會跳回起點，改成從目前位置反向。`

## gestures
- **一般**：`/gestures make this bottom sheet draggable with swipe to dismiss`
- **Lumen**：`/gestures 〔背景〕 筆記列表支援拖曳排序與拖進資料夾：按住時 1:1 跟隨，放開用帶速度的彈簧，觸控目標至少 44×44px，不用 keyframe 動畫。`
- **嚴格審查**：`/gestures 〔背景〕 審 static/app.js 裡所有拖曳相關程式，列出不能中斷、會跳、或用了 keyframe 的地方。只報告。`
- **修 bug／重構**：`/gestures 〔背景〕 拖曳附件到編輯器時，放開後位置會跳一下，找原因並修正。`

## mobile-native
- **一般**：`/mobile-native the page zooms in when I focus the email input`
- **Lumen**：`/mobile-native 〔背景〕 在 iPhone Safari 開 Lumen：檢查 hover 黏住、點擊閃灰、100vh、輸入框放大、瀏海安全區，標出哪些需要真機驗證。`
- **嚴格審查**：`/mobile-native 〔背景〕 依你的症狀表逐項檢查 static/style.css 與 index.html，只報告，每項說明能不能從程式碼確認。`
- **修 bug／重構**：`/mobile-native 〔背景〕 iPad 上點按鈕後一直保持 hover 樣式，修掉，不影響桌面。`

## animation-performance
- **一般**：`/animation-performance this sidebar animation is janky on my phone`
- **Lumen**：`/animation-performance 〔背景〕 筆記庫有 3000 篇時，展開資料夾和捲動列表會卡，先找出掉幀原因再改，在 Safari 引擎驗證。`
- **嚴格審查**：`/animation-performance 〔背景〕 掃描 static/style.css 和 app.js，列出會觸發 layout／paint 的動畫屬性、不必要的 will-change、每幀重算的地方。只報告。`
- **修 bug／重構**：`/animation-performance 〔背景〕 側欄寬度動畫用的是 width，改成合成層屬性，外觀要一樣。`

## break-ui
- **一般**：`/break-ui stress test this table with the worst data you can think of`
- **Lumen**：`/break-ui 〔背景〕 測筆記列表、屬性區、搜尋結果、AI 報告：超長中英標題、emoji、上百個標籤、空筆記庫、一字標題。測試資料只放測試筆記庫，不寫進我的 vault。`
- **嚴格審查**：`/break-ui 〔背景〕 列出每個顯示使用者資料的欄位最長可能多長，以及目前在哪個長度會壞，只出報告。`
- **修 bug／重構**：`/break-ui 〔背景〕 標籤很多時屬性區會撐破版面，修掉並加最壞資料的切換，修完移除切換。`

## review-animations
- **一般**：`/review-animations check the motion in src/components/dialog.tsx`
- **Lumen**：`/review-animations 審這次 diff 裡 static/style.css、app.js、props.js 的動態，Lumen 是純 CSS 與 JS。`
- **嚴格審查**：`/review-animations 用你最嚴格的標準審全部動態，預設標出問題，每項給確切數值與檔名:行號，最後 Approve 或 Block。`
- **修 bug／重構**：`/review-animations 我已依上次的 Block 修正，重審同樣的檔案，只看上次的問題有沒有解決、有沒有新問題。`

## find-animation-opportunities
- **一般**：`/find-animation-opportunities where would animation actually help in this app`
- **Lumen**：`/find-animation-opportunities 〔背景〕 Lumen 是每天開很多次的筆記工具，找出真正需要動態的地方，也列出該保持靜止的，考慮使用頻率。唯讀。`
- **嚴格審查**：`/find-animation-opportunities 〔背景〕 只留你最有把握的三個機會，其餘說明為什麼拒絕。`
- **修 bug／重構**：`/find-animation-opportunities 〔背景〕 使用者說存檔、AI 完成時沒有回饋，看哪些狀態變化需要動態來交代，不要加裝飾性動畫。`

## improve-animations
- **一般**：`/improve-animations quick pass on easing across the app`
- **Lumen**：`/improve-animations 〔背景〕 稽核 Lumen 全部動畫，寫成有優先順序、各自獨立的計畫，先告訴我計畫會寫在哪個檔案，不要改原始碼。`
- **嚴格審查**：`/improve-animations 〔背景〕 只審側欄、屬性區、AI 面板，每個問題附確切數值，依影響排序。`
- **修 bug／重構**：`/improve-animations 〔背景〕 把全站的緩動曲線和時長統一成幾個 CSS token，寫成計畫，標出要改的每個位置。`

## remove-animations
- **一般**：`/remove-animations we animate way too much, tone it down`
- **Lumen**：`/remove-animations 〔背景〕 Lumen 是工作工具：鍵盤操作、常開的面板、資料本身都不該有動畫。列出移除、縮短、保留三類與理由，先給我看再改。`
- **嚴格審查**：`/remove-animations 〔背景〕 每個動畫都要能說出存在理由，說不出的列為移除候選，只報告。`
- **修 bug／重構**：`/remove-animations 〔背景〕 用方向鍵切換筆記時清單高亮有延遲，改成按下就移動。`

## animate-expo
- **一般**：`/animate-expo add a nice transition when you open a post`
- **Lumen**：不適用。Lumen 不是 React Native，日後若做行動版 app 再用。
- **嚴格審查**：`/animate-expo audit the motion in this Expo app and list anything that runs on the JS thread`（一般專案用）
- **修 bug／重構**：`/animate-expo the collapsing header stutters on Android`

## ask-sonner
- **一般**：`/ask-sonner my toasts show up twice in development`
- **Lumen**：不適用。Lumen 沒用 Sonner。
- **嚴格審查**：`/ask-sonner review our toast setup and calls, flag anything that should be toast.promise`（一般專案用）
- **修 bug／重構**：`/ask-sonner my Tailwind classes don't work on the toasts`

## learn-taste
- **一般**：`/learn-taste go through this session and pull out everything I corrected`
- **Lumen**：`/learn-taste 整理這次 session 我對 Lumen 介面的修正，每條提議規則與理由（理由要來自我說過的話），先給我看，同意的才寫進 docs/DESIGN.md，不要碰 CLAUDE.md。`
- **嚴格審查**：`/learn-taste prune，DESIGN.md 太長了：合併重複的，刪掉沒有實際修正來源的規則，給我看刪改清單。`
- **修 bug／重構**：`/learn-taste 我一直在修同樣的間距和字級問題，能改成檢查（lint 或 CSS token 限制）的就提議檢查，不要只寫句子。`

## write-swift（只在 skills.sh）
- **一般**：待確認。兩個網站都沒有範例 prompt，SKILL.md 沒讀到。
- **Lumen**：不適用。Lumen 用 Tauri（Rust），不寫 Swift。
- **嚴格審查**：待確認。
- **修 bug／重構**：待確認。
- 注意：skills.sh 標示這個 skill 含 shell 指令，裝之前要讀過 SKILL.md。
