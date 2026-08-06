import time
import os
import re
import email
from email.header import decode_header
from imapclient import IMAPClient
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from core import database
import urllib.request
import urllib.parse
import json
import traceback

# 載入 .env (從專案根目錄)
dotenv_path = "/Users/hank/Project/LineStockAgent/.env"
load_dotenv(dotenv_path)

USERNAME = os.getenv("SHARED_EMAIL_ACCOUNT")
PASSWORD = os.getenv("SHARED_EMAIL_PASSWORD")
if PASSWORD:
    PASSWORD = re.sub(r'\s+', '', PASSWORD)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

def send_line_message(user_id, text):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("No LINE_CHANNEL_ACCESS_TOKEN found, skipping push notification.")
        return
        
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    data = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": text
            }
        ]
    }
    
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req) as response:
            print(f"LINE push message sent to {user_id}. Status: {response.status}")
    except Exception as e:
        print(f"Failed to send LINE push message: {e}")

def parse_kgi_email(text):
    """
    解析凱基證券純文字信件
    回傳: (stock_code, action, shares, price) 或 None
    """
    # 尋找股票代號 例如 世芯-KY(3661) 或 (0050)
    stock_match = re.search(r'\n([^\(\n]*)\((\d{4,5})\)\s*\n', text)
    if not stock_match:
        # Try finding just (3661)
        stock_match = re.search(r'\((\d{4,5})\)', text)
        
    if not stock_match:
        return None
        
    stock_code = stock_match.group(2) if len(stock_match.groups()) > 1 else stock_match.group(1)
    
    # 尋找買賣別、股數、價格
    # 格式通常是:
    # 買
    # 10 股
    # 台幣
    # 3380.0000
    # 買
    # 10 股
    # 台幣
    # 3380.0000
    trade_match = re.search(r'(買|賣)\s*\n\s*([\d,]+)\s*股\s*\n\s*台幣\s*\n\s*(\d+(?:\.\d+)?)', text)
    if not trade_match:
        return None
        
    action_str = trade_match.group(1)
    shares_str = trade_match.group(2).replace(',', '')
    shares = int(shares_str)
    price = float(trade_match.group(3))
    
    action = 'BUY' if action_str == '買' else 'SELL'
    
    return stock_code, action, shares, price

def extract_original_recipient(msg):
    """
    從轉寄信件中找出原始收件者
    回傳所有可能的信箱列表
    """
    possible_emails = []
    
    # 萃取字串中所有 email 格式
    def extract_emails_from_string(text):
        if not text:
            return
        matches = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
        for m in matches:
            email_lower = m.lower()
            if email_lower not in possible_emails:
                possible_emails.append(email_lower)

    # 1. 檢查標頭
    for header in ["X-Forwarded-For", "X-Forwarded-To"]:
        val = msg.get(header)
        if val:
            extract_emails_from_string(val)
            
    # 2. 檢查內文 To:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    to_match = re.search(r'^To:.*<([^>]+)>', body, re.MULTILINE)
                    if to_match:
                        extract_emails_from_string(to_match.group(1))
                except:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
            to_match = re.search(r'^To:.*<([^>]+)>', body, re.MULTILINE)
            if to_match:
                extract_emails_from_string(to_match.group(1))
        except:
            pass
            
    # 3. 檢查普通的 To 標頭做為 fallback
    to_header = msg.get("To")
    if to_header:
        extract_emails_from_string(to_header)
        
    return possible_emails

def process_email(msg):
    # 取得信件標題
    subject_tuple = decode_header(msg["Subject"])[0]
    subject = subject_tuple[0]
    encoding = subject_tuple[1]
    if isinstance(subject, bytes):
        try:
            subject = subject.decode(encoding if encoding else "utf-8")
        except:
            subject = str(subject)
            
    print(f"Processing email: {subject}")
    
    # 檢查是否為券商信件 (目前支援凱基)
    if "凱基" not in subject and "成交" not in subject:
        print("Not a recognized broker email.")
        return
        
    # 找出綁定的使用者
    emails_to_check = extract_original_recipient(msg)
    user_id = None
    original_email = None
    
    for email_addr in emails_to_check:
        print(f"Checking email: {email_addr}")
        user_id = database.get_user_id_by_email(email_addr)
        if user_id:
            original_email = email_addr
            break
            
    if not user_id:
        print(f"Could not find any bound LINE user for emails: {emails_to_check}")
        return
        
    print(f"Matched user: {user_id} (email: {original_email})")
        
    # 擷取信件內文
    body = ""
    html_body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                try:
                    body += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                except:
                    pass
            elif ctype == "text/html":
                try:
                    html_body += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                except:
                    pass
    else:
        ctype = msg.get_content_type()
        if ctype == "text/html":
            try:
                html_body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
            except:
                pass
        else:
            try:
                body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
            except:
                pass
                
    if html_body:
        # 嘗試用 bs4 把 HTML 轉成文字，保留原本的行內換行
        soup = BeautifulSoup(html_body, 'html.parser')
        body = soup.get_text(separator='\n').strip()
            
    if not body:
        print("Empty email body.")
        return
        
    # 解析交易資訊
    trade_info = parse_kgi_email(body)
    if not trade_info:
        print("Failed to parse trade info from email.")
        return
        
    stock_code, action, shares, price = trade_info
    print(f"Parsed Trade: {action} {stock_code}, {shares} shares @ {price}")
    
    # 更新資料庫
    if action == 'BUY':
        success, reply_msg, is_new = database.register_buy(user_id, stock_code, shares, price)
    else:
        success, reply_msg = database.register_sell(user_id, stock_code, shares, price)
        
    print(f"Database update result: {reply_msg}")
    
    # 推播通知給使用者
    action_ch = "買進" if action == 'BUY' else "賣出"
    current_time_str = time.strftime('%Y/%m/%d %H:%M:%S', time.localtime())
    notification = f"✅ 已更新 {stock_code} 庫存 ({current_time_str})\n動作：{action_ch} {shares} 股 @ {price}"
    send_line_message(user_id, notification)
    
    # 若為新股票，觸發背景抓取資料
    if action == 'BUY' and is_new:
        database.check_and_trigger_new_stock(stock_code)


def run_idle_loop():
    if not USERNAME or not PASSWORD:
        print("SHARED_EMAIL_ACCOUNT or SHARED_EMAIL_PASSWORD not set. Email monitor won't start.")
        return

    print("Starting IMAP IDLE email monitor...")
    
    while True:
        try:
            with IMAPClient("imap.gmail.com") as server:
                server.login(USERNAME, PASSWORD)
                server.select_folder('INBOX')
                
                print("Connected to IMAP. Entering IDLE mode...")
                server.idle()
                
                while True:
                    # Wait for up to 29 minutes (IDLE timeout)
                    responses = server.idle_check(timeout=29 * 60)
                    
                    if responses:
                        # Event received, need to stop IDLE to run fetch
                        server.idle_done()
                        
                        # Check for new messages
                        messages = server.search(['UNSEEN'])
                        if messages:
                            print(f"Found {len(messages)} new messages.")
                            for uid, message_data in server.fetch(messages, 'RFC822').items():
                                try:
                                    msg = email.message_from_bytes(message_data[b'RFC822'])
                                    process_email(msg)
                                    # Mark as read
                                    server.add_flags(uid, [b'\\Seen'])
                                except Exception as e:
                                    print(f"Error processing email {uid}: {e}")
                                    traceback.print_exc()
                        
                        # Resume IDLE
                        print("Resuming IDLE mode...")
                        server.idle()
                    else:
                        # Timeout reached, renew IDLE session to prevent disconnect
                        print("IDLE timeout reached. Renewing session...")
                        server.idle_done()
                        server.idle()
                        
        except Exception as e:
            print(f"IMAP connection error: {e}. Reconnecting in 30 seconds...")
            traceback.print_exc()
            time.sleep(30)

if __name__ == "__main__":
    run_idle_loop()
