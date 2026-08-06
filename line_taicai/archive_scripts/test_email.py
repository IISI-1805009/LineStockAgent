import sys
sys.path.append('.')
import os
from imapclient import IMAPClient
import email
import re
from dotenv import load_dotenv
import email_monitor

load_dotenv('/Users/hank/Project/LineStockAgent/.env')
USERNAME = os.getenv("SHARED_EMAIL_ACCOUNT")
PASSWORD = os.getenv("SHARED_EMAIL_PASSWORD")
if PASSWORD:
    PASSWORD = re.sub(r'\s+', '', PASSWORD)

with IMAPClient("imap.gmail.com") as server:
    server.login(USERNAME, PASSWORD)
    server.select_folder('INBOX')
    server.remove_flags(11, [b'\\Seen'])
    
    messages = server.search(['UNSEEN'])
    print(f"Found {len(messages)} UNSEEN messages")
    for uid, message_data in server.fetch(messages, 'RFC822').items():
        if uid != 11:
            continue
        print(f"Processing UID {uid}")
        msg = email.message_from_bytes(message_data[b'RFC822'])
        try:
            email_monitor.process_email(msg)
            server.add_flags(uid, [b'\\Seen'])
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error: {e}")
