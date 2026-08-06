---
name: line_taicai_assistant
description: 處理獨立的台股 LINE Bot 與儀表板專案，當觸發條件為 `/linetaicai` 時觸發。負責不依賴 Notion 的本地端資料庫更新與網頁呈現。
---

# Line Taicai 專案規範 (Line Taicai Rules)

- **工作目錄**：所有操作必須限制在 `line_taicai/` 目錄內。
- **定位**：此專案已整合所有舊有 `taicai` 專案的功能，專注於透過 SQLite 提供 LINE Bot 回覆、儀表板網頁以及背景排程爬蟲。
- **資料更新原則**：
  - 更新資料時，必須呼叫 `line_taicai/fetch_targets.py` 與 `line_taicai/taicai_manager.py` 來獲取原始 JSON 資料。
  - 獲取 JSON 資料後，必須呼叫 `line_taicai/database.py` 內的 `sync_market_data_from_taicai()` 寫入本地資料庫。
- **新增股票自動化處理原則**：當有新的股票加入（如加入關注清單）時，必須：
  1. 自動透過網路搜尋或抓取工具，取得該股票最新的「法人目標價」資訊。
  2. 將目標價資料補入 `line_taicai/consensus_targets.json` 中。
  3. 觸發並執行更新腳本，自動抓取該股的技術面與籌碼面資料並寫入資料庫。
- **賣出股票紀錄原則**：當執行賣出股票操作時，除了更新各庫存資料庫的剩餘股數外，**必須**將該筆賣出交易記錄到歷史記錄庫中，包含賣出標的、股數與價格等資訊。
- **背景任務與重啟原則**：專案透過 APScheduler (`scheduler.py`) 負責在台股交易期間（平日 09:00 - 15:00）自動執行背景資料更新。
  - **【極度重要】**只要修改了專案內的 Python 程式碼 (例如 `recommendation_engine.py`, `database.py`, `taicai_manager.py` 等)，**必須**立刻重啟 `start_agent.py` 背景任務 (可使用 `lsof -ti:8002 | xargs kill -9 ; /Users/hank/Project/LineStockAgent/line_taicai/venv/bin/python3 start_agent.py`)，以確保背景排程機器人能夠載入最新的程式碼邏輯，避免快取到舊版程式碼而發生錯誤。
