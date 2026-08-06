import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Import our sandboxed tools
from tools import read_file, write_file, list_dir, BASE_WORKSPACE

load_dotenv("/Users/hank/Project/LineStockAgent/line_agent_service/.env")

# Initialize the Gemini client
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

# Define the system instruction to guide the agent
SYSTEM_INSTRUCTION = f"""
You are a helpful local assistant running on a Mac Mini.
You have access to a specific workspace directory via your tools.
Your root workspace is: {BASE_WORKSPACE}
You can read files, write files, and list directories within this workspace.
Always be polite and helpful. If a user asks you to do something outside your workspace, explain that you are restricted for security reasons.
Please respond in Traditional Chinese (繁體中文).
"""

def handle_agent_message(message_text: str, user_name: str = None) -> str:
    """Send a message to the agent and return its response."""
    try:
        # Define the tools available to the model
        agent_tools = [read_file, write_file, list_dir]
        
        # 動態注入使用者名稱
        current_instruction = SYSTEM_INSTRUCTION
        if user_name:
            current_instruction += f"\n【系統提示】目前與你對話的使用者是「{user_name}」。當收到買賣股票的指令時，請務必將操作應用於「{user_name}」的庫存資料庫中。"
        else:
            current_instruction += "\n【系統提示】目前未知對話者的身分，請引導使用者輸入「我是xxx」來綁定身分。"
        
        # We start a chat session. In a real persistent bot, you might want to 
        # keep the chat history in memory per user ID. For now, it's a single shot.
        chat = client.chats.create(
            model="gemini-1.5-pro",
            config=types.GenerateContentConfig(
                system_instruction=current_instruction,
                tools=agent_tools,
                temperature=0.2,
            )
        )
        
        # Send the user message
        response = chat.send_message(message_text)
        
        # The genai SDK automatically handles function calling under the hood for chats
        # when tools are provided. So we just return the final text response.
        return response.text
        
    except Exception as e:
        print(f"Agent error: {e}")
        return f"Agent 發生錯誤: {e}"
