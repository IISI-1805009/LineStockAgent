import os
import json
import sys
import requests
import sqlite3

# Add parent directory to path to import database functions
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import database

def get_notion_token():
    try:
        with open("/Users/hank/.gemini/settings.json", "r") as f:
            settings = json.load(f)
            return settings["mcpServers"]["notion"]["env"]["NOTION_TOKEN"]
    except Exception:
        pass
        
    try:
        with open("/Users/hank/Project/LineStockAgent/.env", "r") as f:
            for line in f:
                if line.startswith("NOTION_TOKEN="):
                    return line.split("=")[1].strip().strip('"').strip("'")
    except Exception:
        pass
        
    return os.environ.get("NOTION_TOKEN")

NOTION_TOKEN = get_notion_token()
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def query_notion_db(db_id):
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    results = []
    has_more = True
    next_cursor = None
    
    while has_more:
        payload = {}
        if next_cursor:
            payload["start_cursor"] = next_cursor
            
        response = requests.post(url, headers=HEADERS, json=payload)
        if response.status_code != 200:
            print(f"Error querying DB {db_id}: {response.text}")
            break
            
        data = response.json()
        results.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        next_cursor = data.get("next_cursor")
        
    return results

def extract_code(page):
    try:
        # Check if '代號' exists as rich_text
        if "代號" in page["properties"]:
            return page["properties"]["代號"]["rich_text"][0]["plain_text"]
    except (KeyError, IndexError):
        pass
    
    # Fallback to checking title for '2330 台積電' format
    for prop in page["properties"].values():
        if prop["type"] == "title":
            try:
                title = prop["title"][0]["plain_text"]
                # return first word if it looks like a code or title
                return title.split()[0]
            except (KeyError, IndexError):
                pass
    return ""

def extract_number(page, property_name):
    try:
        val = page["properties"][property_name].get("number")
        return float(val) if val is not None else 0.0
    except KeyError:
        return 0.0

def migrate_user(user_name: str, user_id: str):
    print(f"Starting migration for {user_name} (ID: {user_id})...")
    
    try:
        with open("/Users/hank/Project/LineStockAgent/line_taicai/db_ids.json", "r") as f:
            db_ids = json.load(f)
    except Exception as e:
        print(f"Error reading db_ids.json: {e}")
        return False, f"讀取 Notion 資料庫 ID 失敗：{e}"

    # 1. 轉移關注清單 (is_etf = 0)
    watchlist_db = db_ids.get("關注")
    if watchlist_db:
        print("Migrating general watchlist...")
        pages = query_notion_db(watchlist_db)
        for page in pages:
            code = extract_code(page)
            if code:
                database.add_to_watchlist(user_id, code, is_etf=False)

    # 2. 轉移 ETF 關注清單 (is_etf = 1)
    etf_db = db_ids.get("ETF關注")
    if etf_db:
        print("Migrating ETF watchlist...")
        pages = query_notion_db(etf_db)
        for page in pages:
            code = extract_code(page)
            if code:
                database.add_to_watchlist(user_id, code, is_etf=True)

    # 3. 轉移個人庫存
    inventory_db = db_ids.get(user_name)
    if inventory_db:
        print(f"Migrating inventory for {user_name}...")
        pages = query_notion_db(inventory_db)
        for page in pages:
            code = extract_code(page)
            if code:
                shares = int(extract_number(page, "目前庫存"))
                avg_cost = extract_number(page, "庫存成本")
                
                if shares > 0:
                    is_etf = code.startswith("00")
                    database.register_buy(user_id, code, shares, avg_cost, is_etf=is_etf)
    else:
        print(f"No inventory DB found for {user_name}")

    print("Migration complete!")
    return True, f"✅ 已成功將 {user_name} 的 Notion 資料 (庫存、關注清單、ETF關注清單) 轉移至專屬資料庫！"

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        migrate_user(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python migration.py <user_name> <user_id>")
