# Environment Variables 參數說明文件 (.env Spec)

本文件整理了系統中 `.env` 檔案內所使用的各項環境變數，說明其用途與影響的系統功能。

## 1. AI 服務與 API 串接

*   **`GEMINI_API_KEY`**
    *   **用途**：Google Gemini AI 服務的 API 密鑰。
    *   **影響範圍**：系統使用 AI 進行台股大盤趨勢分析、個股健檢報告或任何依賴大型語言模型 (LLM) 生成的功能時，需透過此金鑰進行驗證。

## 2. LINE Messaging API (LINE Bot 設定)

*   **`LINE_CHANNEL_SECRET`**
    *   **用途**：LINE 官方帳號的頻道機密碼。
    *   **影響範圍**：當 LINE 伺服器發送 Webhook 請求到我們的背景系統時，會用此 Secret 來驗證訊息的數位簽章，確保請求來源安全合法。
*   **`LINE_CHANNEL_ACCESS_TOKEN`**
    *   **用途**：LINE 官方帳號的存取權杖。
    *   **影響範圍**：系統主動推送訊息、回覆使用者訊息（例如：傳送投資建議、觸發選單）時，必須帶上此 Token 作為身分驗證。

## 3. LINE LIFF & Login (儀表板與前端身分驗證)

*   **`LIFF_ID`**
    *   **用途**：LINE Front-end Framework (LIFF) 的 App ID。
    *   **影響範圍**：前端儀表板網頁 (Dashboard) 載入時，需要傳入此 ID 啟動 LIFF SDK，藉此自動獲取進入網頁的使用者身分 (LINE User ID)。
*   **`LIFF_URL`**
    *   **用途**：LIFF 應用程式的外部短網址。
    *   **影響範圍**：通常作為提供給使用者的捷徑連結，點擊後會在 LINE App 內直接展開儀表板畫面。
*   **`LINE_LOGIN_CHANNEL_ID`**
    *   **用途**：LINE Login 頻道的 ID。
    *   **影響範圍**：在系統啟動 (`start_agent.py`) 時，用於請求授權以自動透過 API 更新 LIFF 的端點網址 (Endpoint URL)。
*   **`LINE_LOGIN_CHANNEL_SECRET`**
    *   **用途**：LINE Login 頻道的機密碼。
    *   **影響範圍**：與 `LINE_LOGIN_CHANNEL_ID` 搭配使用，以取得操作 LIFF 設定的 Access Token。

## 4. 系統自動化與資料庫

*   **`LINE_NOTIFY_TOKEN`**
*   **`SHARED_EMAIL_ACCOUNT`**
    *   **用途**：系統專用的共用 Gmail 信箱帳號。
    *   **影響範圍**：背景的信件監控服務 (`email_monitor.py`) 會自動登入此信箱，用來接收券商發出的電子報、交割通知或是系統警報信件，並進行後續解析。
*   **`SHARED_EMAIL_PASSWORD`**
    *   **用途**：對應 Gmail 帳號的「應用程式專用密碼」(App Password)。
    *   **影響範圍**：提供 IMAP 或 SMTP 協定登入驗證使用。

## 5. 開發者與除錯設定 (Developer Settings)

*   **`DEV_USERID`**
    *   **用途**：指定為「開發者」的 LINE User ID。
    *   **影響範圍**：當以此身分開啟前端儀表板時，網頁會解鎖並顯示「進階開發者區塊」，允許進行系統管理或除錯操作。
*   **`DEV_PASSWORD`**
    *   **用途**：開發者驗證密碼。
    *   **影響範圍**：當開發者在儀表板中使用進階權限（如：模擬查詢他人信箱綁定的帳戶資料）時，需輸入此密碼作為第二層安全防護。
*   **`WEBHOOK_URL`**
    *   **用途**：系統的對外服務網址（通常為 Cloudflare Tunnel 自訂網域）。
    *   **影響範圍**：`start_agent.py` 啟動時會讀取此網址，並自動更新 LINE Webhook Endpoint 與 LIFF 應用的 Endpoint。
