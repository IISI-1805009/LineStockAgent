import os
import sys
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)

from router import process_message
from database import get_user_portfolio

# Templates setup
templates = Jinja2Templates(directory="templates")

# Load environment variables
load_dotenv("/Users/hank/Project/LineStockAgent/line_agent_service/.env")

channel_secret = os.getenv('LINE_CHANNEL_SECRET')
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')

if channel_secret is None or channel_access_token is None:
    print("Warning: LINE_CHANNEL_SECRET or LINE_CHANNEL_ACCESS_TOKEN is missing in .env")

configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)

app = FastAPI()

@app.post("/callback")
async def callback(request: Request, background_tasks: BackgroundTasks):
    # get X-Line-Signature header value
    signature = request.headers.get('X-Line-Signature', '')

    # get request body as text
    body = await request.body()
    body_str = body.decode('utf-8')

    # handle webhook body
    try:
        handler.handle(body_str, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/channel secret.")
        raise HTTPException(status_code=400, detail="Invalid signature")

    return 'OK'

@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request, user: str = "振"):
    return templates.TemplateResponse("index.html", {"request": request, "user_name": user})

@app.get("/api/portfolio/{user_name}")
async def api_portfolio(user_name: str):
    data = get_user_portfolio(user_name)
    return {"status": "success", "user": user_name, "data": data}

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_text = event.message.text
    user_id = event.source.user_id
    
    # Process the message via our router
    reply_text = process_message(user_text, user_id)
    
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )
