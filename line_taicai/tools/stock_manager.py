import os
import sys

# Ensure database is accessible
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import database

def add_to_watchlist(user_id: str, stock_code: str) -> str:
    """
    將股票加入使用者的專屬關注清單。
    
    Args:
        user_id: LINE User ID (由系統自動注入，請直接帶入)
        stock_code: 股票代號 (例如: 2330)
    """
    success, msg = database.add_to_watchlist(user_id, stock_code)
    return msg

def remove_from_watchlist(user_id: str, stock_code: str) -> str:
    """
    將股票從使用者的專屬關注清單移除。
    
    Args:
        user_id: LINE User ID
        stock_code: 股票代號
    """
    deleted = database.remove_from_watchlist(user_id, stock_code)
    if deleted:
        return "成功從關注清單移除"
    else:
        return "您的關注清單中沒有這檔股票"

def buy_stock(user_id: str, stock_code: str, shares: int, price: float) -> str:
    """
    登記買進股票，更新庫存與歷史紀錄。
    
    Args:
        user_id: LINE User ID
        stock_code: 股票代號
        shares: 買進股數
        price: 買進單價
    """
    database.register_buy(user_id, stock_code, shares, price)
    return f"成功登記買進 {stock_code} 共 {shares} 股，單價 {price}"

def sell_stock(user_id: str, stock_code: str, shares: int, price: float) -> str:
    """
    登記賣出股票，扣除庫存並結算實現損益。
    
    Args:
        user_id: LINE User ID
        stock_code: 股票代號
        shares: 賣出股數
        price: 賣出單價
    """
    success, msg = database.register_sell(user_id, stock_code, shares, price)
    return msg

def get_stock_health(stock_code: str) -> str:
    """
    取得個股最新的健檢指標與操作建議。
    
    Args:
        stock_code: 股票代號
    """
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT stock_name, current_price, short_term_rec, short_term_reason, long_term_rec, long_term_reason, technical,
               eps, revenue_yoy, yield_percent, momentum_score
        FROM market_data WHERE stock_code = ?
    """, (stock_code,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return "目前資料庫中沒有這檔股票的最新資料。請稍後再試或確認代號是否正確。"
        
    name, price, st_rec, st_reason, lt_rec, lt_reason, tech, eps, yoy, yield_pct, momentum = row
    return (
        f"【{stock_code} {name}】健檢報告：\n"
        f"🔹 最新股價：{price}\n\n"
        f"🏃‍♂️ [短線波段] {st_rec}\n"
        f"理由：{st_reason}\n\n"
        f"🧘‍♂️ [長線存股] {lt_rec}\n"
        f"理由：{lt_reason}\n\n"
        f"🔹 技術指標：{tech}\n"
        f"🔹 動能：{momentum} | 營收 YoY: {yoy}% | 殖利率: {yield_pct}%\n"
    )
