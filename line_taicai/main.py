from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent
import os
import uvicorn
from router import process_line_message
from core import database
import scheduler
from core import ai_agent

load_dotenv("/Users/hank/Project/LineStockAgent/.env")

app = FastAPI(title="Taicai LINE Bot & Dashboard")
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
def startup_event():
    scheduler.start_scheduler()

@app.on_event("shutdown")
def shutdown_event():
    scheduler.stop_scheduler()

channel_secret = os.getenv('LINE_CHANNEL_SECRET')
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')

configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)

@app.post("/callback")
async def callback(request: Request, background_tasks: BackgroundTasks):
    signature = request.headers.get('X-Line-Signature')
    body = await request.body()
    try:
        handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    print("Received MessageEvent!", flush=True)
    user_id = event.source.user_id
    user_message = event.message.text
    print(f"User: {user_id}, Message: {user_message}", flush=True)
    
    # Process message via router
    reply_text = process_line_message(user_message, user_id)
    print(f"Reply text: {reply_text}", flush=True)
    
    if reply_text:
        try:
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message_with_http_info(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=reply_text)]
                    )
                )
            print("Successfully replied!", flush=True)
        except Exception as e:
            print(f"Failed to reply: {e}", flush=True)

# ==== Web Dashboard & APIs ====

@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    liff_id = os.getenv('LIFF_ID', '')
    dev_userid = os.getenv('DEV_USERID', '')
    update_time = database.get_last_update_time()
    
    market_timing = "⚪ 中立觀望"
    try:
        import json
        if os.path.exists("data/market_summary.json"):
            with open("data/market_summary.json", "r", encoding="utf-8") as f:
                ms = json.load(f)
                m_rsi = ms.get("TWII_rsi", 50.0)
                m_bias = ms.get("TWII_bias", 0.0)
                if m_rsi < 35 or m_bias < -5.0:
                    market_timing = "🔴 超賣（買進時機）"
                elif m_rsi > 75 or m_bias > 10.0:
                    market_timing = "🟢 超買（逢高減碼）"
    except Exception:
        pass
        
    return templates.TemplateResponse("index.html", {"request": request, "liff_id": liff_id, "dev_userid": dev_userid, "update_time": update_time, "market_timing": market_timing})

@app.get("/api/portfolio/{user_id}")
def api_get_portfolio(user_id: str):
    portfolio = database.get_user_portfolio(user_id)
    unsettled = database.get_unsettled_amount(user_id)
    return {"status": "success", "user_id": user_id, "data": portfolio, "unsettled": unsettled}

@app.get("/api/watchlist/{user_id}")
def api_get_watchlist(user_id: str):
    watchlist = database.get_user_watchlist(user_id)
    return {"status": "success", "user_id": user_id, "data": watchlist}

@app.get("/api/history/{user_id}")
def api_get_history(user_id: str):
    history = database.get_user_history(user_id)
    return {"status": "success", "user_id": user_id, "data": history}

@app.delete("/api/history/{user_id}/{record_id}")
def api_delete_history(user_id: str, record_id: int):
    database.delete_history_record(user_id, record_id)
    return {"status": "success"}

# ==== CRUD Models & Endpoints ====

class WatchlistRequest(BaseModel):
    stock_code: str
    is_etf: bool = False

class InventoryRequest(BaseModel):
    stock_code: str
    shares: int
    price: float
    is_etf: bool = False

class EmailBindRequest(BaseModel):
    email: str

class UserSettings(BaseModel):
    notify_enabled: bool
    notify_time: str

class DevResolveRequest(BaseModel):
    input_val: str
    password: str

@app.get("/api/user/{user_id}/email")
def api_get_email(user_id: str):
    email = database.get_email_by_user_id(user_id)
    if email:
        return {"email": email}
    raise HTTPException(status_code=404, detail="Email not found")

@app.post("/api/user/{user_id}/email")
def api_bind_email(user_id: str, req: EmailBindRequest):
    try:
        success, msg = database.bind_user_email(user_id, req.email)
        return {"status": "success", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/{user_id}/settings")
def api_get_settings(user_id: str):
    return database.get_user_settings(user_id)

@app.put("/api/user/{user_id}/settings")
def api_update_settings(user_id: str, req: UserSettings):
    database.update_user_settings(user_id, req.notify_enabled, req.notify_time)
    return {"status": "success"}

@app.post("/api/dev/resolve_user")
def api_dev_resolve_user(req: DevResolveRequest):
    import os
    expected_password = os.getenv("DEV_PASSWORD")
    if not expected_password or req.password != expected_password:
        raise HTTPException(status_code=401, detail="密碼錯誤或未設定開發者密碼")
    
    if "@" in req.input_val:
        user_id = database.get_user_id_by_email(req.input_val)
        if not user_id:
            raise HTTPException(status_code=404, detail="找不到該信箱綁定的使用者")
        return {"user_id": user_id}
    else:
        # 當作 user_id 檢查是否存在
        if not database.check_user_exists(req.input_val):
            raise HTTPException(status_code=404, detail="找不到該 User ID")
        return {"user_id": req.input_val}

def resolve_stock_code(input_val: str) -> str:
    input_val = input_val.strip()
    import json, os
    names_file = "data/tw_stock_names.json"
    if os.path.exists(names_file):
        try:
            with open(names_file, "r", encoding="utf-8") as f:
                mapping = json.load(f)
            if input_val in mapping:
                return mapping[input_val]
        except Exception:
            pass
    return input_val

@app.post("/api/watchlist/{user_id}")
def api_add_watchlist(user_id: str, req: WatchlistRequest, background_tasks: BackgroundTasks):
    stock_code = resolve_stock_code(req.stock_code)
    success, msg, is_new = database.add_to_watchlist(user_id, stock_code, req.is_etf)
    if success:
        if is_new:
            background_tasks.add_task(database.check_and_trigger_new_stock, stock_code)
            msg += " (此為新股票，系統正於背景抓取資料，請於一分鐘後重整)"
        return {"status": "success", "message": msg}
    else:
        raise HTTPException(status_code=400, detail=msg)

@app.delete("/api/watchlist/{user_id}/{stock_code}")
def api_remove_watchlist(user_id: str, stock_code: str):
    success = database.remove_from_watchlist(user_id, stock_code)
    if success:
        return {"status": "success", "message": "已從關注清單移除"}
    else:
        raise HTTPException(status_code=404, detail="找不到該股票")

@app.post("/api/inventory/buy/{user_id}")
def api_buy_inventory(user_id: str, req: InventoryRequest, background_tasks: BackgroundTasks):
    try:
        stock_code = resolve_stock_code(req.stock_code)
        success, msg, is_new = database.register_buy(user_id, stock_code, req.shares, req.price, req.is_etf)
        if is_new:
            background_tasks.add_task(database.check_and_trigger_new_stock, stock_code)
            msg += " (此為新股票，系統正於背景抓取資料，請於一分鐘後重整)"
        return {"status": "success", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/inventory/sell/{user_id}")
def api_sell_inventory(user_id: str, req: InventoryRequest):
    try:
        success, msg = database.register_sell(user_id, req.stock_code, req.shares, req.price)
        if success:
            return {"status": "success", "message": msg}
        else:
            raise HTTPException(status_code=400, detail=msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/inventory/edit/{user_id}")
def api_edit_inventory(user_id: str, req: InventoryRequest):
    try:
        success, msg = database.edit_inventory(user_id, req.stock_code, req.shares, req.price)
        if success:
            return {"status": "success", "message": msg}
        else:
            raise HTTPException(status_code=400, detail=msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/inventory/delete/{user_id}/{stock_code}")
def api_delete_inventory(user_id: str, stock_code: str):
    try:
        success, msg = database.delete_inventory(user_id, stock_code)
        if success:
            return {"status": "success", "message": msg}
        else:
            raise HTTPException(status_code=400, detail=msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health_check/{stock_code}")
def api_health_check(stock_code: str):
    conn = database.get_connection()
    import sqlite3
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM market_data WHERE stock_code = ?", (stock_code,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="找不到該股票資料")
        
    stock_data = dict(row)
    stock_name = stock_data.get('stock_name', '')
    
    news = ai_agent.get_stock_news(stock_name, stock_code)
    report_html = ai_agent.generate_health_check_report(stock_data, news)
    
    return {"status": "success", "html": report_html}

@app.get("/api/market_trend")
def api_market_trend():
    import json
    import os
    file_path = "data/market_summary.json"
    cache_file = "data/market_trend_cache.json"
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="尚未產生大盤數據，請等待背景更新或手動執行一次更新。")
        
    with open(file_path, "r", encoding="utf-8") as f:
        market_data = json.load(f)
        
    current_update_date = market_data.get("update_date")
    
    # 檢查硬碟持久化快取
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                saved_cache = json.load(f)
            saved_update_date = saved_cache.get("update_date", "")
            if saved_update_date and saved_cache.get("html"):
                # 如果快取的資料時間與目前市場資料時間一致，代表市場資料未更新，直接使用快取
                if saved_update_date == current_update_date:
                    return {"status": "success", "html": saved_cache["html"]}
        except Exception:
            pass
            
    # 產生新報告
    report_html = ai_agent.generate_market_trend_report(market_data)
    
    # 寫入硬碟快取
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"update_date": current_update_date, "html": report_html}, f, ensure_ascii=False)
    except Exception as e:
        print(f"Failed to write cache: {e}")
    
    return {"status": "success", "html": report_html}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
