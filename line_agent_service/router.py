import subprocess
import os
import threading
import requests
import time
import json
from agent import handle_agent_message
from dotenv import load_dotenv

load_dotenv("/Users/hank/Project/LineStockAgent/line_agent_service/.env")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://handstarlinebot.win")

# 用來記錄上次執行台菜技能的時間
last_taicai_execution_time = 0

def push_line_message(user_id: str, text_msg: str):
    """透過 LINE Push API 主動傳送訊息給使用者"""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return
        
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
                "text": text_msg
            }
        ]
    }
    try:
        requests.post(api_url, headers=headers, json=payload)
    except Exception as e:
        print(f"Push message failed: {e}")

def run_skill_in_background(script_cmd, cwd, user_id):
    """在背景執行指令，依據結果推播成功或失敗通知"""
    global last_taicai_execution_time
    try:
        result = subprocess.run(
            script_cmd,
            cwd=cwd,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            error_output = result.stderr.strip()
            if not error_output:
                error_output = result.stdout.strip()
            push_line_message(user_id, f"⚠️ 執行台菜技能時發生錯誤：\n{error_output[-500:]}")
            last_taicai_execution_time = 0  # 失敗時重置冷卻時間
        else:
            dashboard_url = f"{WEBHOOK_URL}/dashboard?user_id={user_id}"
            push_line_message(user_id, f"✅ 台菜資料更新已順利完成！請前往專屬儀表板查看最新資料：\n{dashboard_url}")
    except Exception as e:
        push_line_message(user_id, f"⚠️ 執行台菜技能時發生錯誤：\n{str(e)}")
        last_taicai_execution_time = 0  # 失敗時重置冷卻時間



def process_message(user_message: str, user_id: str = "") -> str:
    """Route the message to the appropriate handler."""
    global last_taicai_execution_time
    message = user_message.strip()
    if message in ["開啟專屬資料庫", "開啟儀表板", "儀表板"]:
        dashboard_url = f"{WEBHOOK_URL}/dashboard?user_id={user_id}"
        return f"📊 [專屬儀表板]\n{dashboard_url}"
        
    if message in ["台菜資料更新", "台菜更新"]:
        # 防呆機制：10 分鐘 (600 秒) 內只能執行一次
        current_time = time.time()
        if current_time - last_taicai_execution_time < 600:
            remaining = int(600 - (current_time - last_taicai_execution_time))
            minutes = remaining // 60
            seconds = remaining % 60
            return f"⏳ 技能正在冷卻中！請等待 {minutes} 分 {seconds} 秒後再試一次。"
            
        # Execute the predefined skill script
        script_path = "/Users/hank/Project/LineStockAgent/taicai/run_taicai.sh"
        if os.path.exists(script_path):
            try:
                # 更新最後執行時間
                last_taicai_execution_time = current_time
                
                # 啟動獨立的執行緒在背景等待
                thread = threading.Thread(
                    target=run_skill_in_background,
                    args=(["bash", "run_taicai.sh"], "/Users/hank/Project/LineStockAgent/taicai", user_id)
                )
                thread.start()
                return "執行中，請稍後"
            except Exception as e:
                # 若啟動失敗，將時間重置，以便使用者能立刻重試
                last_taicai_execution_time = 0
                return f"啟動台菜技能時發生錯誤: {str(e)}"
        else:
            return f"找不到指定的技能腳本: {script_path}"
            
    else:
        # Pass to the sandboxed agent, using user_id directly
        return handle_agent_message(message, user_name=user_id)
