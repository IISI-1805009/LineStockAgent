# LineStockAgent

LineStockAgent 是一個專門用來追蹤與管理台股、ETF 資訊的個人化自動服務，並結合了 LINE Bot 進行即時互動與查詢。本專案整合了資料抓取、選股建議、庫存損益管理等功能，並透過本機伺服器與 AI 助理提供順暢的操作體驗。

## 專案核心架構

本專案主要分為兩個獨立但相輔相成的服務模組：

### 1. `line_taicai` (台股資訊處理與儀表板)
此模組為專案的資料核心，負責台股市場資料的抓取、處理、分析與呈現。
* **資料儲存**：全面採用本地端 SQLite (`data/taicai.db`) 儲存，管理使用者的「庫存清單」、「關注清單」、「歷史交易紀錄」與「市場即時資料」。
* **分析與建議**：自動抓取最新的台股趨勢與財報數據，計算基本面與籌碼面指標（如本益比、外資投信買賣超），並產生專屬的短長線買賣建議與技術面評分。
* **網頁儀表板**：內建網頁介面 (Web UI)，能讓使用者一目了然地檢視持股損益、關注個股狀態，並透過視覺化標籤快速判斷目前的操作建議。

### 2. `line_agent_service` (LINE Webhook 伺服器)
此模組負責對外與使用者透過 LINE 進行互動，並作為指令的接收中樞。
* **Webhook 接收**：使用 FastAPI 建立伺服器，接收並處理來自 LINE 的使用者訊息。
* **內網穿透 (Cloudflare Tunnel)**：專案內附 `cloudflared` 執行檔，啟動時會自動建立內網穿透通道並更新 LINE Webhook 網址，解決本機開發與部署的網路限制。
* **AI Agent 互動**：結合 Gemini API，讓機器人具備語意理解能力。使用者可直接輸入自然語言（例如「幫我更新台股資料」、「賣出 1000 股台積電」），Agent 判斷意圖後會自動操作 SQLite 資料庫或背景執行更新腳本。

## 系統需求

* **作業系統**：macOS (針對 Apple Silicon ARM64 架構優化)
* **Python 環境**：建議 Python 3.9 或以上版本。
* **網路設定**：依賴 Cloudflare Tunnel，確保本機有對外連線能力即可。

## 環境變數與設定檔

在執行前，請確保根目錄或服務目錄下具備正確的 `.env` 檔案設定。相關細節請參考 `line_taicai/spec/ENV_SPEC.md`。必填項目包含：
* `LINE_CHANNEL_ACCESS_TOKEN` 及 `LINE_CHANNEL_SECRET`：LINE Bot 開發者金鑰。
* `GEMINI_API_KEY`：用來驅動 AI 自然語言解析的金鑰。

## 快速啟動

1. **安裝相依套件**：
   在 `line_agent_service/` 與 `line_taicai/` 目錄中，分別建立虛擬環境 (venv)，並執行：
   ```bash
   pip install -r requirements.txt
   ```
2. **啟動 LINE 服務器**：
   進入 `line_agent_service` 目錄，執行 `python start_agent.py`。系統會自動啟動背景伺服器、開啟 Cloudflare Tunnel 並完成 LINE 端的 Webhook 註冊。
3. **資料更新與儀表板**：
   系統背景服務會依據使用者指令（如輸入 `台菜資料更新`）觸發 `line_taicai/run_taicai.sh` 抓取最新資料，並更新至資料庫中。使用者也可以透過程式啟動的 Web UI 直接觀看。

## 注意事項
* **獨立工作區**：為確保各專案獨立，請避免跨資料夾混合設定檔案。
* **背景常駐服務**：若有修改 `router.py` 等伺服器核心邏輯，請務必重新啟動背景程序，以免快取未更新。
