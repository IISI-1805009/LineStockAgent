import os
import requests
from dotenv import load_dotenv

load_dotenv("/Users/hank/Project/LineStockAgent/.env")
CLIENT_ID = os.getenv("LINE_LOGIN_CHANNEL_ID")
CLIENT_SECRET = os.getenv("LINE_LOGIN_CHANNEL_SECRET")
LIFF_ID = os.getenv("LIFF_ID")

# 1. Get Token using v2 API
token_url = "https://api.line.me/v2/oauth/accessToken"
payload = {
    "grant_type": "client_credentials",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET
}
res = requests.post(token_url, data=payload)
print("Token API Response:", res.status_code, res.text)
if res.status_code == 200:
    access_token = res.json().get("access_token")
    print("Got access token successfully")
    
    # 2. Update LIFF
    liff_api = f"https://api.line.me/liff/v1/apps/{LIFF_ID}/view"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # Read the actual tunnel url instead of example.com
    with open("/Users/hank/Project/LineStockAgent/line_taicai/tunnel_url.txt", "r") as f:
        url = f.read().strip()
        
    liff_payload = {
        "type": "full",
        "url": f"{url}/dashboard"
    }
    res_liff = requests.put(liff_api, headers=headers, json=liff_payload)
    print("LIFF API Response:", res_liff.status_code, res_liff.text)
