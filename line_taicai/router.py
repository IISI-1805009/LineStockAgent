import os
import urllib.request
import urllib.parse
import json
from openai import OpenAI
from tools.stock_manager import add_to_watchlist, remove_from_watchlist, buy_stock, sell_stock, get_stock_health

ollama_client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

SYSTEM_INSTRUCTION_TEMPLATE = """
你是一個專業的台股投資助理 (Taicai Agent)。
你的主要任務是判斷使用者的意圖，並呼叫對應的工具 (tools) 來協助使用者。
使用者可能會要求：健檢股票、買進、賣出、新增關注或刪除關注。
請務必精準提取出「股票代號」、「股數」與「單價」等資訊，並呼叫工具。
如果你無法理解，請用繁體中文回覆說明。
"""

HERMES_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_to_watchlist",
            "description": "將股票加入使用者的專屬關注清單",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_code": {"type": "string", "description": "股票代號"}
                },
                "required": ["stock_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_watchlist",
            "description": "將股票從使用者的專屬關注清單移除",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_code": {"type": "string", "description": "股票代號"}
                },
                "required": ["stock_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buy_stock",
            "description": "登記買進股票",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_code": {"type": "string", "description": "股票代號"},
                    "shares": {"type": "integer", "description": "股數"},
                    "price": {"type": "number", "description": "單價"}
                },
                "required": ["stock_code", "shares", "price"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sell_stock",
            "description": "登記賣出股票",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_code": {"type": "string", "description": "股票代號"},
                    "shares": {"type": "integer", "description": "股數"},
                    "price": {"type": "number", "description": "單價"}
                },
                "required": ["stock_code", "shares", "price"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_health",
            "description": "取得股票的健檢資訊與分析",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_code": {"type": "string", "description": "股票代號"}
                },
                "required": ["stock_code"]
            }
        }
    }
]

def process_line_message(user_message: str, user_id: str) -> str:
    message = user_message.strip()
    
    # 處理信箱綁定
    if message.startswith("/綁定信箱"):
        parts = message.split()
        if len(parts) >= 2:
            email = parts[1].strip()
            from core import database
            success, reply = database.bind_user_email(user_id, email)
            return reply
        else:
            return "請輸入正確格式，例如：/綁定信箱 myemail@gmail.com"

    # 處理特殊固定指令 (Rich Menu)
    if message == "開啟專屬資料庫":
        tunnel_url = os.getenv("WEBHOOK_URL", "https://handstarlinebot.win")
            
        dashboard_url = f"{tunnel_url}/dashboard?user_id={user_id}"
        return f"📊 [專屬儀表板]\n{dashboard_url}"
        
    if message == "個股健檢":
        return "🔍 請告訴我您想健檢哪一檔股票？ (例如: 2330)"
        
    if message == "新增關注清單":
        return "⭐ 請輸入您想加入關注的股票代號？ (例如: 2330)"
        
    if message == "刪除關注清單":
        return "🗑️ 請輸入您想從關注清單移除的股票代號？"
        
    if message == "登記買進":
        return "💰 請告訴我您買進了什麼股票？\n(例如：我買了 1000 股 2330，單價 850)"
        
    if message == "登記賣出":
        return "📉 請告訴我您賣出了什麼股票？\n(例如：我賣了 1000 股 2330，單價 900)"
        
    # 如果不是上述固定指令，則交給 Hermes AI 代理處理 (理解自然語言並呼叫工具)
    try:
        messages = [
            {"role": "system", "content": SYSTEM_INSTRUCTION_TEMPLATE.format(user_id=user_id)},
            {"role": "user", "content": message}
        ]
        
        response = ollama_client.chat.completions.create(
            model="hermes3:8b",
            messages=messages,
            tools=HERMES_TOOLS,
            temperature=0.2
        )
        
        msg = response.choices[0].message
        
        if msg.tool_calls:
            tool_call = msg.tool_calls[0]
            func_name = tool_call.function.name
            
            args = {}
            if tool_call.function.arguments:
                try:
                    args = json.loads(tool_call.function.arguments)
                except Exception as e:
                    print(f"Failed to parse tool arguments: {e}")
            
            if func_name == "add_to_watchlist":
                args["user_id"] = user_id
                return add_to_watchlist(**args)
            elif func_name == "remove_from_watchlist":
                args["user_id"] = user_id
                return remove_from_watchlist(**args)
            elif func_name == "buy_stock":
                args["user_id"] = user_id
                return buy_stock(**args)
            elif func_name == "sell_stock":
                args["user_id"] = user_id
                return sell_stock(**args)
            elif func_name == "get_stock_health":
                return get_stock_health(**args)
            else:
                return f"未知的操作指令: {func_name}"
                
        return msg.content or "無法理解您的指令。"
    except Exception as e:
        print(f"Agent error: {e}")
        return f"抱歉，系統處理時發生錯誤：{e}"
