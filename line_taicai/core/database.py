import sqlite3
import json
import os
from datetime import datetime, timedelta

DB_PATH = "/Users/hank/Project/LineStockAgent/line_taicai/data/taicai.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 用戶表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 關注清單
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            is_etf BOOLEAN DEFAULT 0,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, stock_code)
        )
    """)
    
    # 庫存清單
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            is_etf BOOLEAN DEFAULT 0,
            shares INTEGER NOT NULL DEFAULT 0,
            avg_cost REAL NOT NULL DEFAULT 0.0,
            bought_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, stock_code)
        )
    """)
    
    # 歷史紀錄表 (包含損益)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transaction_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            action TEXT NOT NULL, -- 'BUY' or 'SELL'
            shares INTEGER NOT NULL,
            price REAL NOT NULL,
            realized_pnl REAL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 信箱綁定表 (用於自動轉寄庫存更新)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_emails (
            user_id TEXT NOT NULL,
            email_address TEXT PRIMARY KEY,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 市場即時資料 (完全繼承舊版 taicai 所有欄位)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_data (
            stock_code TEXT PRIMARY KEY,
            stock_name TEXT NOT NULL,
            current_price REAL,
            suggested_buy REAL,
            suggested_sell REAL,
            recommendation TEXT,
            buy_reason TEXT,
            short_term_rec TEXT,
            short_term_reason TEXT,
            long_term_rec TEXT,
            long_term_reason TEXT,
            technical TEXT,
            
            eps REAL,
            revenue_yoy REAL,
            yield_percent REAL,
            momentum_score TEXT,
            foreign_buy INTEGER,
            trust_buy INTEGER,
            target_price REAL,
            
            raw_data TEXT, -- 保存完整的 JSON 以供後續擴展使用
            update_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 動態新增欄位 (如果舊資料庫沒有這四個欄位)
    try:
        cursor.execute("ALTER TABLE market_data ADD COLUMN short_term_rec TEXT")
        cursor.execute("ALTER TABLE market_data ADD COLUMN short_term_reason TEXT")
        cursor.execute("ALTER TABLE market_data ADD COLUMN long_term_rec TEXT")
        cursor.execute("ALTER TABLE market_data ADD COLUMN long_term_reason TEXT")
    except Exception:
        pass # 欄位已存在
        
    # 動態新增用戶設定欄位
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN last_notified_date TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN notify_enabled INTEGER DEFAULT 1")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN notify_time TEXT DEFAULT '11:30'")
    except Exception:
        pass
    
    conn.commit()
    conn.close()

def _get_recommendation_logic(data):
    # This logic now uses the local recommendation_engine.py
    try:
        from core.recommendation_engine import decide_recommendation
        indicators = {
            "rsi": data.get("RSI", 50),
            "atr": data.get("ATR", 0),
            "ma5": data.get("MA5", data.get("Price")),
            "ma20": data.get("MA20", data.get("Price")),
            "ma60": data.get("MA60", data.get("Price")),
            "kd_k": data.get("KD_K", 50),
            "kd_d": data.get("KD_D", 50),
            "rsi_divergence": data.get("RSIDivergence", "None"),
            "technical_flags": data.get("TechnicalFlags", []),
            "is_new_stock": data.get("is_new_stock", False)
        }
        st_rec, st_reason, lt_rec, lt_reason = decide_recommendation(
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
            inst_buy_ratio=data.get("InstBuyRatio", 0.0),
            current_yield=data.get("Yield") or 0.0,
            revenue_yoy=data.get("RevenueYoY", 0.0),
            consecutive_dividend_years=data.get("ConsecutiveDividendYears", 0),
            consec_3m=data.get("Consecutive3M_Growth", False),
            turnaround=data.get("TurnaroundSignal", False),
            avg_yield_5y=data.get("AvgYield5Y", 0.0),
            pe=data.get("PE"),
            pb=data.get("PB"),
            market_pe_median=data.get("MarketPEMedian", 15.0),
            market_pb_median=data.get("MarketPBMedian", 1.5),
            adv_metrics={
                'pe_5y_lowest_20': data.get('pe_5y_lowest_20', False),
                'pb_5y_lowest_20': data.get('pb_5y_lowest_20', False),
                'ar_days_improved': data.get('ar_days_improved', False),
                'inv_days_improved': data.get('inv_days_improved', False),
                'gross_margin_yoy': data.get('gross_margin_yoy', False),
                'operating_margin_yoy': data.get('operating_margin_yoy', False),
                'pre_tax_yoy': data.get('pre_tax_yoy', False),
                'net_income_yoy': data.get('net_income_yoy', False),
                'fcf_3_of_5_positive': data.get('fcf_3_of_5_positive', True),
                'fcf_5y_avg_positive': data.get('fcf_5y_avg_positive', True),
                'ocf_ni_3_of_5_over_100': data.get('ocf_ni_3_of_5_over_100', True),
                'ocf_ni_5y_avg_over_100': data.get('ocf_ni_5y_avg_over_100', True),
                'div_payout_3_of_5_over_50': data.get('div_payout_3_of_5_over_50', True),
                'div_payout_5y_avg_over_50': data.get('div_payout_5y_avg_over_50', True)
            },
            stock_code=data.get("Code", "")
        )
        tech_summary = f"KD({data.get('KD_K', 50):.0f},{data.get('KD_D', 50):.0f}) / RSI({data.get('RSI', 50):.0f})"
        return st_rec, st_reason, lt_rec, lt_reason, tech_summary
    except Exception as e:
        print(f"Failed to calculate recommendation for {data.get('Code')}: {e}")
        return "👀 觀望", "", "👀 觀望", "", ""

ETF_NAMES = {
    "0050": "元大台灣50",
    "0056": "元大高股息",
    "00713": "元大台灣高息低波",
    "00878": "國泰永續高股息",
    "00915": "凱基優選高股息30",
    "00918": "大華優利高填息30",
    "00919": "群益台灣精選高息",
    "00929": "復華台灣科技優息"
}

def sync_market_data_from_taicai():
    """Sync data from taicai/latest_data.json into SQLite."""
    latest_data_file = "/Users/hank/Project/LineStockAgent/line_taicai/data/latest_data.json"
    if not os.path.exists(latest_data_file):
        print("latest_data.json not found.")
        return
        
    with open(latest_data_file, 'r') as f:
        latest_data = json.load(f)
        
    conn = get_connection()
    cursor = conn.cursor()
    
    for code, data in latest_data.items():
        st_rec, st_reason, lt_rec, lt_reason, tech = _get_recommendation_logic(data)
        
        # 判斷名稱，若是清單中的 ETF 則換成中文
        stock_name = data.get("Name", "Unknown")
        if code in ETF_NAMES:
            stock_name = ETF_NAMES[code]
        
        cursor.execute("""
            INSERT OR REPLACE INTO market_data 
            (stock_code, stock_name, current_price, suggested_buy, suggested_sell, stop_loss,
             recommendation, buy_reason, short_term_rec, short_term_reason, long_term_rec, long_term_reason,
             technical, eps, revenue_yoy, yield_percent, 
             momentum_score, foreign_buy, trust_buy, target_price, raw_data, update_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            code, 
            stock_name,
            data.get("Price", 0),
            data.get("SuggestedBuy", 0),
            data.get("SuggestedSell", 0),
            data.get("SuggestedStopLoss", 0),
            st_rec, # fallback legacy
            st_reason, # fallback legacy
            st_rec,
            st_reason,
            lt_rec,
            lt_reason,
            tech,
            data.get("PE", 0), # Simplified mapping
            data.get("RevenueYoY", 0),
            data.get("Yield", 0),
            data.get("Momentum", ""),
            data.get("ForeignBuy", 0),
            data.get("TrustBuy", 0),
            data.get("TargetPrice", 0),
            json.dumps(data, ensure_ascii=False),
            datetime.now()
        ))
    
    conn.commit()
    conn.close()

# ==== 業務邏輯 API ====

def edit_inventory(user_id, stock_code, new_shares, new_avg_cost):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM inventory WHERE user_id = ? AND stock_code = ?", (user_id, stock_code))
        row = cursor.fetchone()
        if not row:
            return False, "找不到該股票庫存紀錄"
            
        cursor.execute(
            "UPDATE inventory SET shares = ?, avg_cost = ? WHERE user_id = ? AND stock_code = ?",
            (new_shares, new_avg_cost, user_id, stock_code)
        )
        conn.commit()
        return True, f"已成功將 {stock_code} 數量修改為 {new_shares} 股，成本為 {new_avg_cost} 元"
    except Exception as e:
        conn.rollback()
        return False, f"修改庫存失敗: {e}"
    finally:
        conn.close()

def delete_inventory(user_id, stock_code):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM inventory WHERE user_id = ? AND stock_code = ?", (user_id, stock_code))
        row = cursor.fetchone()
        if not row:
            return False, "找不到該股票庫存紀錄"
            
        cursor.execute("DELETE FROM inventory WHERE user_id = ? AND stock_code = ?", (user_id, stock_code))
        conn.commit()
        return True, f"已成功刪除 {stock_code} 的庫存紀錄"
    except Exception as e:
        conn.rollback()
        return False, f"刪除庫存失敗: {e}"
    finally:
        conn.close()

# ==== 查詢功能 ====

def register_user(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_all_users_for_notification():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, last_notified_date, notify_enabled, notify_time FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [{"user_id": row[0], "last_notified_date": row[1], "notify_enabled": row[2] if row[2] is not None else 1, "notify_time": row[3] or "11:30"} for row in rows]

def update_user_notified_date(user_id: str, date_str: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_notified_date = ? WHERE user_id = ?", (date_str, user_id))
    conn.commit()
    conn.close()

def get_user_settings(user_id: str):
    register_user(user_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT notify_enabled, notify_time FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"notify_enabled": bool(row[0] if row[0] is not None else 1), "notify_time": row[1] or "11:30"}
    return {"notify_enabled": True, "notify_time": "11:30"}

def update_user_settings(user_id: str, notify_enabled: bool, notify_time: str):
    register_user(user_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET notify_enabled = ?, notify_time = ? WHERE user_id = ?", (int(notify_enabled), notify_time, user_id))
    conn.commit()
    conn.close()

def bind_user_email(user_id: str, email: str):
    """綁定使用者的信箱，用於接收轉寄的成交回報"""
    register_user(user_id)
    conn = get_connection()
    cursor = conn.cursor()
    # 使用 REPLACE 來覆寫，如果同一個信箱已經綁過，就改綁到新的 user_id
    cursor.execute("""
        INSERT OR REPLACE INTO user_emails (user_id, email_address)
        VALUES (?, ?)
    """, (user_id, email))
    conn.commit()
    conn.close()
    return True, f"成功綁定信箱：{email}"

def get_user_id_by_email(email: str):
    """透過信箱反查綁定的 LINE user_id"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM user_emails WHERE email_address = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return None

def get_email_by_user_id(user_id: str):
    """透過 LINE user_id 反查綁定的信箱"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT email_address FROM user_emails WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return None

def add_to_watchlist(user_id: str, stock_code: str, is_etf: bool = False):
    register_user(user_id)
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO watchlist (user_id, stock_code, is_etf) VALUES (?, ?, ?)", (user_id, stock_code, is_etf))
        
        cursor.execute("SELECT 1 FROM market_data WHERE stock_code = ?", (stock_code,))
        is_new = cursor.fetchone() is None
        
        conn.commit()
        return True, "成功加入關注清單", is_new
    except sqlite3.IntegrityError:
        return False, "該股票已在關注清單中", False
    finally:
        conn.close()

def remove_from_watchlist(user_id, stock_code):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM watchlist WHERE user_id = ? AND stock_code = ?", (user_id, stock_code))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def register_buy(user_id: str, stock_code: str, shares: int, price: float, is_etf: bool = False):
    register_user(user_id)
    conn = get_connection()
    cursor = conn.cursor()
    
    # 紀錄買進至歷史紀錄 (交割計算需要)
    cursor.execute("""
        INSERT INTO transaction_history (user_id, stock_code, action, shares, price, realized_pnl)
        VALUES (?, ?, 'BUY', ?, ?, 0)
    """, (user_id, stock_code, shares, price))

    # 更新或插入庫存
    cursor.execute("SELECT id, shares, avg_cost FROM inventory WHERE user_id = ? AND stock_code = ?", (user_id, stock_code))
    row = cursor.fetchone()
    if row:
        inv_id, old_shares, old_cost = row
        new_shares = old_shares + shares
        new_cost = ((old_shares * old_cost) + (shares * price)) / new_shares
        cursor.execute("""
            UPDATE inventory SET shares = ?, avg_cost = ? WHERE id = ?
        """, (new_shares, new_cost, inv_id))
    else:
        cursor.execute("""
            INSERT INTO inventory (user_id, stock_code, is_etf, shares, avg_cost) VALUES (?, ?, ?, ?, ?)
        """, (user_id, stock_code, is_etf, shares, price))
        
    cursor.execute("SELECT 1 FROM market_data WHERE stock_code = ?", (stock_code,))
    is_new = cursor.fetchone() is None
        
    conn.commit()
    conn.close()
    return True, "成功買進", is_new

def register_sell(user_id, stock_code, shares, price):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT shares, avg_cost FROM inventory WHERE user_id = ? AND stock_code = ?", (user_id, stock_code))
    row = cursor.fetchone()
    if not row or row[0] < shares:
        conn.close()
        return False, "庫存不足"
        
    old_shares, old_cost = row
    realized_pnl = (price - old_cost) * shares
    
    # 交易紀錄
    cursor.execute("""
        INSERT INTO transaction_history (user_id, stock_code, action, shares, price, realized_pnl)
        VALUES (?, ?, 'SELL', ?, ?, ?)
    """, (user_id, stock_code, shares, price, realized_pnl))
    
    # 更新庫存
    new_shares = old_shares - shares
    if new_shares == 0:
        cursor.execute("DELETE FROM inventory WHERE user_id = ? AND stock_code = ?", (user_id, stock_code))
    else:
        cursor.execute("UPDATE inventory SET shares = ? WHERE user_id = ? AND stock_code = ?", (new_shares, user_id, stock_code))
        
    conn.commit()
    conn.close()
    return True, f"成功賣出，實現損益: {realized_pnl:.0f}"

def get_user_portfolio(user_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT i.stock_code, i.is_etf, i.shares, i.avg_cost, m.stock_name, m.current_price,
               m.recommendation, m.short_term_rec, m.long_term_rec, m.technical, m.suggested_buy, m.suggested_sell, m.stop_loss,
               m.target_price, m.buy_reason, m.short_term_reason, m.long_term_reason, m.momentum_score
        FROM inventory i
        LEFT JOIN market_data m ON i.stock_code = m.stock_code
        WHERE i.user_id = ? AND i.shares > 0
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    portfolio = []
    for r in rows:
        code, is_etf, shares, cost, name, price, rec, st_rec, lt_rec, tech, s_buy, s_sell, stop_loss, target_p, reason, st_reason, lt_reason, momentum = r
        price = price or 0
        pnl_amount = (price - cost) * shares if cost else 0
        pnl_percent = ((price - cost) / cost * 100) if cost and shares else 0
        portfolio.append({
            "code": code, "is_etf": bool(is_etf), "name": name, "shares": shares, "avg_cost": cost,
            "current_price": price, "pnl_amount": pnl_amount, "pnl_percent": pnl_percent,
            "recommendation": rec, "short_term_rec": st_rec, "long_term_rec": lt_rec, "technical": tech,
            "suggested_buy": s_buy, "suggested_sell": s_sell, "stop_loss": stop_loss,
            "target_price": target_p, "buy_reason": reason, "short_term_reason": st_reason, "long_term_reason": lt_reason, "momentum_score": momentum
        })
    return portfolio

def get_user_watchlist(user_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT w.stock_code, w.is_etf, m.stock_name, m.current_price, m.recommendation, m.short_term_rec, m.long_term_rec,
               m.buy_reason, m.short_term_reason, m.long_term_reason, m.technical, m.revenue_yoy, m.momentum_score, m.foreign_buy, 
               m.trust_buy, m.suggested_buy, m.target_price
        FROM watchlist w
        LEFT JOIN market_data m ON w.stock_code = m.stock_code
        WHERE w.user_id = ?
        ORDER BY w.added_at DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    watchlist = []
    for r in rows:
        watchlist.append({
            "code": r[0], "is_etf": bool(r[1]), "name": r[2], "current_price": r[3],
            "recommendation": r[4], "short_term_rec": r[5], "long_term_rec": r[6], "buy_reason": r[7], "short_term_reason": r[8], "long_term_reason": r[9],
            "technical": r[10], "revenue_yoy": r[11], "momentum_score": r[12], "foreign_buy": r[13], "trust_buy": r[14],
            "suggested_buy": r[15], "target_price": r[16]
        })
    return watchlist

def get_user_history(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, t.stock_code, m.stock_name, t.action, t.shares, t.price, t.realized_pnl, t.created_at
        FROM transaction_history t
        LEFT JOIN market_data m ON t.stock_code = m.stock_code
        WHERE t.user_id = ?
        ORDER BY t.created_at DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for row in rows:
        history.append({
            "id": row[0], "code": row[1], "name": row[2], "action": row[3], "shares": row[4],
            "price": row[5], "realized_pnl": row[6], "created_at": row[7]
        })
    return history

def delete_history_record(user_id: str, record_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transaction_history WHERE id = ? AND user_id = ?", (record_id, user_id))
    conn.commit()
    conn.close()
    return True

def get_unsettled_amount(user_id: str):
    """計算 T+2 內尚未交割的買進總額與明細"""
    conn = get_connection()
    cursor = conn.cursor()
    # 抓取過去 7 天的買進紀錄
    cursor.execute("""
        SELECT t.stock_code, m.stock_name, t.action, t.shares, t.price, t.created_at
        FROM transaction_history t
        LEFT JOIN market_data m ON t.stock_code = m.stock_code
        WHERE t.user_id = ? AND t.created_at >= date('now', '-7 days')
        ORDER BY t.created_at DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    details = []
    today = datetime.now().date()
    
    for r in rows:
        code, name, action, shares, price, created_at_str = r
        try:
            # created_at_str format: "YYYY-MM-DD HH:MM:SS"
            trade_time = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")
            trade_date = trade_time.date()
            
            # 簡易 T+2 營業日計算 (不含國定假日)
            settlement_date = trade_date
            days_added = 0
            while days_added < 2:
                settlement_date += timedelta(days=1)
                if settlement_date.weekday() < 5:
                    days_added += 1
            
            if today <= settlement_date:
                amount = shares * price if action == 'BUY' else -(shares * price)
                details.append({
                    "code": code,
                    "name": name,
                    "action": action,
                    "shares": shares,
                    "price": price,
                    "amount": amount,
                    "trade_date": trade_date.strftime("%m/%d"),
                    "settlement_date": settlement_date.strftime("%m/%d")
                })
        except Exception as e:
            print(f"Error parsing date {created_at_str}: {e}")
            continue
            
    # Calculate net per settlement date
    net_by_date = {}
    for d in details:
        date_str = d["settlement_date"]
        net_by_date[date_str] = net_by_date.get(date_str, 0) + d["amount"]
        
    # User only needs to prepare money if a specific settlement date has a positive net amount
    total_required = sum(amt for amt in net_by_date.values() if amt > 0)
            
    return {"total_amount": total_required, "net_by_date": net_by_date, "details": details}

def get_last_update_time():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(update_time) FROM market_data")
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        try:
            # The format is 'YYYY-MM-DD HH:MM:SS.mmmmmm' from python datetime
            # We can format it nicely
            from datetime import datetime
            dt = datetime.strptime(row[0].split('.')[0], "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%Y/%m/%d %H:%M:%S")
        except:
            return row[0]
    return "尚未更新"

import subprocess
import uuid
import os

def check_and_trigger_new_stock(stock_code: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM market_data WHERE stock_code = ?", (stock_code,))
    row = cursor.fetchone()
    conn.close()
    
    if row is None:
        print(f"Stock {stock_code} not found in database. Triggering background fetch...")
        try:
            targets_path = "/Users/hank/Project/LineStockAgent/line_taicai/data/targets.json"
            with open(targets_path, "r", encoding="utf-8") as f:
                targets = json.load(f)
                
            if not any(t.get("code") == stock_code for t in targets):
                targets.append({
                    "id": str(uuid.uuid4()),
                    "code": stock_code,
                    "db": "網頁新增"
                })
                with open(targets_path, "w", encoding="utf-8") as f:
                    json.dump(targets, f, ensure_ascii=False, indent=4)
                    
            consensus_path = "/Users/hank/Project/LineStockAgent/line_taicai/data/consensus_targets.json"
            script_dir = "/Users/hank/Project/LineStockAgent/line_taicai"
            
            if os.path.exists(consensus_path):
                with open(consensus_path, "r", encoding="utf-8") as f:
                    consensus = json.load(f)
                
                if stock_code not in consensus:
                    print(f"Fetching target price for new stock {stock_code}...")
                    python_cmd = "/Users/hank/Project/LineStockAgent/line_agent_service/venv/bin/python3"
                    subprocess.run([python_cmd, "fetch_targets.py", "--code", stock_code], cwd=script_dir, check=False)
            
            # 執行資料抓取腳本
            subprocess.run(["/bin/bash", "run_taicai.sh"], cwd=script_dir, check=True)
            
            # 同步資料
            sync_market_data_from_taicai()
            print(f"Successfully fetched and synced new stock {stock_code}")
        except Exception as e:
            print(f"Error fetching new stock {stock_code}: {e}")

if __name__ == "__main__":
    init_db()
    sync_market_data_from_taicai()
    print("line_taicai database initialized.")
