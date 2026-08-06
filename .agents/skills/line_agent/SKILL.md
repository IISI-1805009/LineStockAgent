---
name: line_agent
description: 處理 LINE Webhook 伺服器與 Cloudflare Tunnel 啟動，當觸發條件為 `/lineagent` 或「啟動LINE」時觸發。負責自動建立內網穿透並更新 LINE Webhook 網址。
---

# LINE Agent 啟動規範 (Line Agent Rules)

- **工作目錄**：所有操作必須限制在 `/Users/hank/Project/LineStockAgent/line_agent_service/` 目錄內。
- 負責管理與啟動 LINE Webhook 伺服器與內網穿透工具。
- **啟動處理原則**：當收到啟動指令時，必須：
  1. 確保不在系統環境執行，改用虛擬環境執行腳本（例如執行 `/Users/hank/Project/LineStockAgent/line_agent_service/venv/bin/python3 start_agent.py`）。
  2. 若要在背景長駐，請提示使用者可以使用 `launchctl load ~/Library/LaunchAgents/com.hank.lineagent.plist` 來達成開機自動啟動。
