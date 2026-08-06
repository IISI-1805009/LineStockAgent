import os
import requests
from datetime import datetime
from core import database
from dotenv import load_dotenv

load_dotenv("/Users/hank/Project/LineStockAgent/.env")

def send_line_push_message(user_id: str, message: str):
    LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("Missing LINE_CHANNEL_ACCESS_TOKEN for notifier.")
        return False
        
    api_url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    try:
        res = requests.post(api_url, headers=headers, json=payload)
        if res.status_code == 200:
            return True
        else:
            print(f"Failed to send push to {user_id}: {res.status_code} {res.text}")
            return False
    except Exception as e:
        print(f"Error sending push message to {user_id}: {e}")
        return False

def check_and_notify_all_users():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running daily notification check...", flush=True)
    now_dt = datetime.now()
    today_str = now_dt.strftime("%Y-%m-%d")
    current_time_str = now_dt.strftime("%H:%M")
    users = database.get_all_users_for_notification()
    
    for u in users:
        user_id = u['user_id']
        last_notified = u['last_notified_date']
        notify_enabled = u.get('notify_enabled', 1)
        notify_time = u.get('notify_time', '11:30')
        
        if not notify_enabled:
            continue
            
        if notify_time != current_time_str:
            continue
        
        if last_notified == today_str:
            continue
            
        portfolio = database.get_user_portfolio(user_id)
        watchlist = database.get_user_watchlist(user_id)
        
        alerts = []
        
        # Check inventory for 大買 or 大賣
        for p in portfolio:
            st = p.get('short_term_rec', '') or ''
            lt = p.get('long_term_rec', '') or ''
            if '大買' in st or '大買' in lt:
                alerts.append(f"🔴 [庫存] {p['name']}({p['code']}): 觸發大買建議！")
            elif "大賣" in p.get("long_term_rec", "") or "大賣" in p.get("short_term_rec", ""):
                alerts.append(f"🟢 [庫存] {p['name']}({p['code']}): 觸發大賣建議！")
                
        # Check watchlist for 大買
        for w in watchlist:
            st = w.get('short_term_rec', '') or ''
            lt = w.get('long_term_rec', '') or ''
            if '大買' in st or '大買' in lt:
                alerts.append(f"🔴 [關注] {w['name']}({w['code']}): 觸發大買建議！")
                
        if alerts:
            msg_header = "🔔 【台股投資助理】重要交易建議 🔔\n\n您的清單中出現以下操作建議：\n"
            msg_body = "\n".join(alerts)
            msg_footer = "\n\n👉 詳情請至專屬儀表板查看或直接對我輸入該股票進行健檢。"
            
            full_message = msg_header + msg_body + msg_footer
            success = send_line_push_message(user_id, full_message)
            if success:
                database.update_user_notified_date(user_id, today_str)
                print(f"Successfully sent daily notification to {user_id}.", flush=True)
