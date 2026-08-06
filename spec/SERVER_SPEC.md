# 雙伺服器架構說明文件 (Server Architecture Spec)

本專案 (`LineStockAgent`) 採用「雙伺服器架構 (Dual Server Architecture)」來分離「LINE 訊息接收路由」與「資料處理及視覺化儀表板」的職責。本文件詳細說明這兩個伺服器的職責、啟動方式與修改注意事項。

## 1. 架構概覽

專案主要由以下兩個獨立運作的背景伺服器組成：

1.  **`line_agent_service` (Webhook 路由與代理服務)**
    *   **職責**：作為 LINE Bot 的單一進入點 (Webhook Endpoint)，負責接收使用者在 LINE 上傳送的所有訊息。
    *   **行為**：攔截特定的系統指令（如「台菜更新」、「開啟專屬資料庫」等）並觸發對應的背景任務，其餘自然語言對話則轉交給 AI Agent (Gemini) 進行理解與回覆。
    *   **網路**：透過自建的 `cloudflared` Quick Tunnel 建立一個隨機的對外網址，並自動向 LINE 伺服器更新 Webhook。

2.  **`line_taicai` (台股核心服務與前端儀表板)**
    *   **職責**：處理台股買賣交易邏輯、計算交割金額、呼叫本地端 Ollama (Hermes 3) 生成盤後分析報告。
    *   **行為**：提供 `/api/*` 資料介面給前端，並伺服 HTML/JS 前端儀表板網頁 (`/dashboard`)。
    *   **網路**：通常掛載在一個固定的網域名稱 (例如設定在 `.env` 中 `WEBHOOK_URL` 的網址) 之下，以便提供穩定不變的網址讓使用者可以隨時透過 LINE 點擊瀏覽。

## 2. 服務管理與重啟機制 (Launchctl)

為了確保服務能在背景穩定長駐，這兩個伺服器皆使用 macOS 內建的 `launchd` 作為系統守護行程管理工具，分別對應兩個不同的 plist 設定檔：

| 服務名稱 | 專案目錄位置 | launchctl 服務代號 |
| :--- | :--- | :--- |
| **Agent 服務** | `line_agent_service/` | `com.hank.lineagent` |
| **Taicai 服務** | `line_taicai/` | `com.hank.linetaicai` |

### 重啟原則與指令 (極度重要)
只要修改了任何 Python 程式碼、HTML 模板，或是 `.env` 設定檔，舊的程式碼依然會留在系統記憶體中繼續運作。因此，修改完成後，**必須親自執行對應的重啟指令**，新版程式碼才會生效：

*   **只修改了 Agent 路由或 AI 邏輯時 (`line_agent_service`)**：
    ```bash
    launchctl unload ~/Library/LaunchAgents/com.hank.lineagent.plist
    launchctl load ~/Library/LaunchAgents/com.hank.lineagent.plist
    ```
*   **只修改了台股資料邏輯、交割計算或儀表板介面時 (`line_taicai`)**：
    ```bash
    launchctl unload ~/Library/LaunchAgents/com.hank.linetaicai.plist
    launchctl load ~/Library/LaunchAgents/com.hank.linetaicai.plist
    ```
*   **若兩邊都有修改，則必須兩邊的指令都執行。**

## 3. 常見問題與除錯指南

*   **修改了程式碼卻沒有生效？**
    請先確認你修改的是哪一個資料夾底下的程式碼，並對應執行上述正確的 `launchctl` 重啟指令。最常見的錯誤是「改了 `line_taicai` 的網頁，卻只重啟了 `line_agent`」。
*   **伺服器似乎沒有啟動 (Crash)？**
    如果服務啟動後立即崩潰（例如缺少 Python 套件 `jinja2`），你可以前往對應的 `logs/` 資料夾查看日誌：
    *   `line_agent_service/logs/service.log`
    *   `line_agent_service/logs/service_error.log`
