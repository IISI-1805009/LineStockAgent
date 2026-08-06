import sqlite3
import json
import os
from datetime import datetime
import random

DB_PATH = "taicai.db"
TARGETS_FILE = "../taicai/targets.json"
LATEST_DATA_FILE = "../taicai/latest_data.json"

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 建立庫存資料表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            shares INTEGER NOT NULL DEFAULT 0,
            avg_cost REAL NOT NULL DEFAULT 0.0,
            UNIQUE(user_name, stock_code)
        )
    """)
    
    # 建立市場即時資料表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_data (
            stock_code TEXT PRIMARY KEY,
            stock_name TEXT NOT NULL,
            current_price REAL,
            suggested_buy REAL,
            suggested_sell REAL,
            recommendation TEXT,
            buy_reason TEXT,
            technical TEXT,
            update_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

def _get_recommendation_logic(data):
    # Try importing decide_recommendation from taicai
    import sys
    sys.path.append(os.path.abspath("../taicai"))
    try:
        from notion_updater import decide_recommendation
        indicators = {
            "rsi": data.get("RSI", 50),
            "atr": data.get("ATR", 0),
            "ma5": data.get("MA5", data.get("Price")),
            "ma20": data.get("MA20", data.get("Price")),
            "ma60": data.get("MA60", data.get("Price")),
            "kd_k": data.get("KD_K", 50),
            "kd_d": data.get("KD_D", 50),
            "rsi_divergence": data.get("RSIDivergence", "None"),
            "technical_flags": data.get("TechnicalFlags", [])
        }
        rec, buy_reason, sell_reason, target_list = decide_recommendation(
            data.get("Price"), 
            data.get("SuggestedBuy"), 
            data.get("SuggestedSell"), 
            data.get("Momentum", "未知"),
            indicators,
            inst_type=data.get("Type", "EQUITY"),
            target_price=data.get("TargetPrice"),
            target_details=data.get("TargetPriceDetails"),
            foreign_buy=data.get("ForeignBuy", 0),
            trust_buy=data.get("TrustBuy", 0),
            f_consec=data.get("ForeignConsecutiveBuy", 0),
            t_consec=data.get("TrustConsecutiveBuy", 0),
            market_trend=data.get("MarketTrend", "未知"),
            stock_trend=data.get("StockTrend", "未知"),
            inst_buy_ratio=data.get("InstBuyRatio", 0.0)
        )
        return rec, buy_reason, f"KD(K:{data.get('KD_K', 50):.0f}, D:{data.get('KD_D', 50):.0f}) / RSI({data.get('RSI', 50):.0f})"
    except Exception as e:
        print(f"Failed to import from notion_updater: {e}")
        return "👀 觀望", "", ""

def sync_mock_data():
    """Sync data from JSONs into SQLite to serve the dashboard."""
    if not os.path.exists(TARGETS_FILE) or not os.path.exists(LATEST_DATA_FILE):
        print("JSON files not found. Skipping sync.")
        return
        
    with open(TARGETS_FILE, 'r') as f:
        targets = json.load(f)
        
    with open(LATEST_DATA_FILE, 'r') as f:
        latest_data = json.load(f)
        
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Update Market Data
    for code, data in latest_data.items():
        rec, buy_reason, tech = _get_recommendation_logic(data)
        
        cursor.execute("""
            INSERT OR REPLACE INTO market_data 
            (stock_code, stock_name, current_price, suggested_buy, suggested_sell, recommendation, buy_reason, technical, update_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            code, 
            data.get("Name", "Unknown"),
            data.get("Price", 0),
            data.get("SuggestedBuy", 0),
            data.get("SuggestedSell", 0),
            rec,
            buy_reason,
            tech,
            datetime.now()
        ))
        
    # 2. Update Mock Inventory (Only insert if not exists to not overwrite testing data)
    for target in targets:
        user_name = target.get("db")
        code = target.get("code")
        
        if user_name in ["振", "芊"]:
            current_price = latest_data.get(code, {}).get("Price", 100)
            mock_shares = random.choice([1000, 2000, 3000, 500])
            mock_cost = current_price * random.uniform(0.85, 1.15)
            
            cursor.execute("""
                INSERT OR IGNORE INTO inventory (user_name, stock_code, shares, avg_cost)
                VALUES (?, ?, ?, ?)
            """, (user_name, code, mock_shares, mock_cost))
            
    conn.commit()
    conn.close()

def get_user_portfolio(user_name):
    """取得特定使用者的完整庫存與市場資訊"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            i.stock_code,
            m.stock_name,
            m.current_price,
            i.shares,
            i.avg_cost,
            m.suggested_buy,
            m.suggested_sell,
            m.recommendation,
            m.buy_reason,
            m.technical
        FROM inventory i
        LEFT JOIN market_data m ON i.stock_code = m.stock_code
        WHERE i.user_name = ?
    """, (user_name,))
    
    rows = cursor.fetchall()
    conn.close()
    
    portfolio = []
    for row in rows:
        code, name, price, shares, cost, s_buy, s_sell, rec, breason, tech = row
        price = price or 0
        cost = cost or 0
        shares = shares or 0
        
        market_value = price * shares
        total_cost = cost * shares
        pnl_amount = market_value - total_cost
        pnl_percent = (pnl_amount / total_cost * 100) if total_cost > 0 else 0
        
        portfolio.append({
            "code": code,
            "name": name,
            "current_price": price,
            "shares": shares,
            "avg_cost": cost,
            "pnl_amount": pnl_amount,
            "pnl_percent": pnl_percent,
            "suggested_buy": s_buy,
            "suggested_sell": s_sell,
            "recommendation": rec,
            "buy_reason": breason,
            "technical": tech
        })
        
    return portfolio

if __name__ == "__main__":
    init_db()
    sync_mock_data()
    print("Database initialized and synced.")
