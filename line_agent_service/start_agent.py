import os
import time
import subprocess
import re
import requests
import sys
from dotenv import load_dotenv

# 強制關閉 stdout 緩衝，確保日誌能即時輸出到檔案
sys.stdout.reconfigure(line_buffering=True)

# 載入環境變數
load_dotenv("/Users/hank/Project/LineStockAgent/line_agent_service/.env")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

def update_line_webhook(url: str):
    """呼叫 LINE API 更新 Webhook 網址"""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("❌ 找不到 LINE_CHANNEL_ACCESS_TOKEN，請確認 .env 檔案設定。")
        return

    endpoint = f"{url}/callback"
    print(f"🔄 準備將 LINE Webhook 更新為: {endpoint}")

    api_url = "https://api.line.me/v2/bot/channel/webhook/endpoint"
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "endpoint": endpoint
    }

    try:
        # 增加重試機制，因為 Cloudflare 剛產生網址時，網路可能還沒完全打通
        max_retries = 3
        for attempt in range(max_retries):
            response = requests.put(api_url, headers=headers, json=payload)
            if response.status_code == 200:
                print("✅ LINE Webhook 更新成功！")
                return
            else:
                print(f"⚠️ LINE Webhook 更新失敗: {response.status_code} - {response.text}")
                if attempt < max_retries - 1:
                    print(f"⏳ 等待 3 秒後進行第 {attempt+2} 次重試...")
                    time.sleep(3)
        print("❌ LINE Webhook 更新最終失敗，請稍後手動重啟。")
    except Exception as e:
        print(f"❌ 呼叫 LINE API 發生錯誤: {e}")

def main():
    workspace = "/Users/hank/Project/LineStockAgent/line_agent_service"
    
    # 1. 啟動 FastAPI 伺服器 (Uvicorn)
    print("🚀 啟動本地 FastAPI 伺服器...")
    uvicorn_cmd = ["/Users/hank/Project/LineStockAgent/line_agent_service/venv/bin/uvicorn", "main:app", "--port", "8000"]
    uvicorn_process = subprocess.Popen(uvicorn_cmd, cwd=workspace)
    
    # 給伺服器一點時間啟動
    time.sleep(2)

    # 2. 啟動 Cloudflare Quick Tunnel
    print("☁️  啟動 Cloudflare Quick Tunnel...")
    cloudflared_cmd = ["./cloudflared", "tunnel", "--url", "http://localhost:8000"]
    
    # Cloudflared 的網址資訊會輸出在 stderr
    cloudflared_process = subprocess.Popen(
        cloudflared_cmd, 
        cwd=workspace,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )

    url_regex = re.compile(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com')
    webhook_updated = False

    try:
        # 3. 持續讀取 cloudflared 的輸出，捕捉網址
        for line in cloudflared_process.stderr:
            print(f"[Cloudflared] {line.strip()}", flush=True)
            
            if not webhook_updated:
                match = url_regex.search(line)
                if match:
                    public_url = match.group(0)
                    print(f"\n🎉 成功捕捉到 Cloudflare 網址: {public_url}\n")
                    # 4. 更新 LINE Webhook
                    update_line_webhook(public_url)
                    webhook_updated = True
                    print("\n⚡ 系統已準備就緒，您可以開始在 LINE 進行對話了！(請保持此視窗開啟)\n")

        # 等待程序結束
        uvicorn_process.wait()
        cloudflared_process.wait()

    except KeyboardInterrupt:
        print("\n🛑 收到中斷訊號，正在關閉伺服器與通道...")
        uvicorn_process.terminate()
        cloudflared_process.terminate()
        print("👋 系統已安全關閉。")

if __name__ == "__main__":
    main()
