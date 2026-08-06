import subprocess
import time
import re
import os
import requests
from dotenv import load_dotenv

load_dotenv("/Users/hank/Project/LineStockAgent/.env")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_LOGIN_CHANNEL_ID = os.getenv("LINE_LOGIN_CHANNEL_ID")
LINE_LOGIN_CHANNEL_SECRET = os.getenv("LINE_LOGIN_CHANNEL_SECRET")
LIFF_ID = os.getenv("LIFF_ID")

def update_line_webhook(webhook_url: str):
    """Update LINE Bot Webhook URL."""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("Missing LINE_CHANNEL_ACCESS_TOKEN")
        return
        
    api_url = "https://api.line.me/v2/bot/channel/webhook/endpoint"
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "endpoint": f"{webhook_url}/callback"
    }
    
    try:
        # Retry mechanism because Cloudflare URLs take a moment to be reachable
        max_retries = 5
        for i in range(max_retries):
            time.sleep(3) # Wait before hitting LINE API
            response = requests.put(api_url, headers=headers, json=payload)
            if response.status_code == 200:
                print(f"✅ Successfully updated LINE Webhook to {webhook_url}/callback")
                return
            else:
                print(f"⚠️ Retry {i+1}/{max_retries}: Failed to update Webhook: {response.status_code} {response.text}")
        print("❌ Final failure updating Webhook.")
    except Exception as e:
        print(f"❌ Exception while updating Webhook: {e}")

def update_liff_endpoint(webhook_url: str):
    """Update LINE LIFF Endpoint URL."""
    if not LINE_LOGIN_CHANNEL_ID or not LINE_LOGIN_CHANNEL_SECRET or not LIFF_ID:
        print("Missing LINE Login credentials or LIFF_ID")
        return
        
    print("Requesting LINE Login access token...")
    token_url = "https://api.line.me/v2/oauth/accessToken"
    payload = {
        "grant_type": "client_credentials",
        "client_id": LINE_LOGIN_CHANNEL_ID,
        "client_secret": LINE_LOGIN_CHANNEL_SECRET
    }
    
    try:
        res = requests.post(token_url, data=payload)
        if res.status_code == 200:
            access_token = res.json().get("access_token")
            liff_api = f"https://api.line.me/liff/v1/apps/{LIFF_ID}/view"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            liff_payload = {
                "type": "full",
                "url": f"{webhook_url}/dashboard"
            }
            res_liff = requests.put(liff_api, headers=headers, json=liff_payload)
            if res_liff.status_code == 200:
                print(f"✅ Successfully updated LIFF Endpoint to {webhook_url}/dashboard")
            else:
                print(f"❌ Failed to update LIFF Endpoint: {res_liff.status_code} {res_liff.text}")
        else:
            print(f"❌ Failed to get LINE Login token: {res.status_code} {res.text}")
    except Exception as e:
        print(f"❌ Exception while updating LIFF Endpoint: {e}")

def main():
    print("Starting line_taicai services...")
    
    # 0. Kill any process using port 8002 to prevent Address already in use error
    print("Checking for zombie processes on port 8002...")
    try:
        subprocess.run("lsof -ti:8002 | xargs kill -9", shell=True, stderr=subprocess.DEVNULL)
        time.sleep(1) # wait for port to be released
    except Exception:
        pass
        
    # 1. Start FastAPI server in background
    uvicorn_process = subprocess.Popen(
        ["venv/bin/python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"],
        # allow uvicorn to print directly to service.log
    )
    
    # 2. Start Cloudflared named tunnel in background
    print("Starting cloudflared named tunnel for handstarlinebot.win...")
    cloudflared_process = subprocess.Popen(
        ["tools/cloudflared", "tunnel", "run", "--url", "http://127.0.0.1:8002", "linetaicai"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # 3. Start IMAP Email Monitor in background
    print("Starting IMAP Email Monitor...")
    email_monitor_process = subprocess.Popen(
        ["venv/bin/python", "-u", "-m", "core.email_monitor"]
    )
    
    # Register cleanup handlers to prevent zombie processes
    import atexit
    import signal
    import sys
    
    def cleanup():
        print("\nStopping services...")
        if uvicorn_process.poll() is None:
            uvicorn_process.terminate()
        if cloudflared_process.poll() is None:
            cloudflared_process.terminate()
        if email_monitor_process.poll() is None:
            email_monitor_process.terminate()
        print("Services stopped.")
        
    atexit.register(cleanup)
    
    def signal_handler(signum, frame):
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 網址已改由 .env (WEBHOOK_URL) 統一管理，不再寫入 tunnel_url.txt
    tunnel_url = os.getenv("WEBHOOK_URL", "https://handstarlinebot.win")
    print(f"\n🚀 Using Cloudflare URL from .env: {tunnel_url}\n")
    try:
        # Update LIFF Endpoint URL
        update_liff_endpoint(tunnel_url)
        
        # Start a thread to keep reading cloudflared output so the buffer doesn't block
        import threading
        def drain_output(stream):
            for _ in stream: pass
        threading.Thread(target=drain_output, args=(cloudflared_process.stderr,), daemon=True).start()
        threading.Thread(target=drain_output, args=(cloudflared_process.stdout,), daemon=True).start()
    except Exception as e:
        print(f"Error during initialization: {e}")
    
    print("Services are running. Press Ctrl+C to stop.")
    while True:
        # If any of the critical processes die, exit so launchd can restart the whole script
        if uvicorn_process.poll() is not None or cloudflared_process.poll() is not None or email_monitor_process.poll() is not None:
            print("A critical background process died. Exiting to allow restart.")
            sys.exit(1)
        time.sleep(1)

if __name__ == "__main__":
    main()
