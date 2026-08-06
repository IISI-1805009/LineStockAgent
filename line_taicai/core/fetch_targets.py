import json
import os
import sys
import argparse
from typing import List, Dict, Any
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from google import genai
from dotenv import load_dotenv, find_dotenv

# Load env vars
load_dotenv(find_dotenv())
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

TARGETS_FILE = "data/targets.json"
CONSENSUS_FILE = "data/consensus_targets.json"

def fetch_news(code: str) -> str:
    """Fetch recent news articles regarding the stock's target price via Google News RSS"""
    query = f"{code} 法人 目標價"
    query_encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={query_encoded}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    results = ""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
        
        root = ET.fromstring(xml_data)
        items = root.findall('.//item')
        
        for item in items[:5]:  # Top 5 news
            title = item.findtext('title', '')
            description = item.findtext('description', '')
            results += f"Title: {title}\nSnippet: {description}\n\n"
    except Exception as e:
        print(f"Error fetching news for {code}: {e}")
    return results

def extract_targets_with_gemini(news_text: str, code: str) -> Dict[str, float]:
    """Use Gemini to extract target prices and return as a dict"""
    if not GEMINI_API_KEY or GEMINI_API_KEY.startswith("請在這裡貼上"):
        print("⚠️ Gemini API Key is missing or invalid.")
        return {}
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # We use a system instruction to strictly constrain the output format
    prompt = f"""
    分析以下新聞摘要中，各家法人或券商對股票代號 {code} 的「目標價」。
    
    規則：
    1. 只能輸出 JSON 格式，不要包含任何 markdown 語法 (如 ```json)
    2. JSON 的 key 必須是具體的法人名稱（例如：大摩、花旗、瑞銀、本土法人、外資A）。絕對不可使用違規字眼如「樂觀、保守、最高、最低、高點、低點、共識、估值、技術目標」。
    3. JSON 的 value 必須是數字 (float)
    4. 必須計算所有券商的平均值，並將其放入 key="平均" 中
    5. 如果沒有找到任何目標價資訊，請回傳 {{"平均": 0}}
    
    新聞摘要：
    {news_text}
    """
    
    import time
    
    max_retries = 3
    retry_delay = 10
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt,
            )
            text = response.text.strip()
            
            # strip out any backticks if the model still outputs them
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text.rsplit("\n", 1)[0]
            text = text.strip("`")
            
            data = json.loads(text)
            return data
            
        except Exception as e:
            error_str = str(e)
            print(f"Error parsing Gemini output for {code} (Attempt {attempt+1}/{max_retries}): {e}")
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                if attempt < max_retries - 1:
                    print(f"Rate limit hit. Waiting {retry_delay} seconds before retrying...")
                    time.sleep(retry_delay)
                    continue
            return {}
            
    return {}

def update_consensus(code: str, new_targets: Dict[str, float]):
    try:
        with open(CONSENSUS_FILE, "r", encoding="utf-8") as f:
            consensus = json.load(f)
    except Exception:
        consensus = {}
        
    consensus[code] = new_targets
    
    with open(CONSENSUS_FILE, "w", encoding="utf-8") as f:
        json.dump(consensus, f, indent=4, ensure_ascii=False)
    print(f"✅ Updated consensus targets for {code}: {new_targets}")

def main():
    parser = argparse.ArgumentParser(description="Fetch institutional targets for stocks.")
    parser.add_argument("--code", type=str, help="Specific stock code to fetch")
    parser.add_argument("--missing", action="store_true", help="Fetch for all stocks missing in consensus_targets")
    parser.add_argument("--all", action="store_true", help="Fetch for all stocks in targets.json")
    
    args = parser.parse_args()
    
    try:
        with open(TARGETS_FILE, "r", encoding="utf-8") as f:
            targets = json.load(f)
    except Exception as e:
        print(f"Could not load targets.json: {e}")
        return
        
    try:
        with open(CONSENSUS_FILE, "r", encoding="utf-8") as f:
            consensus = json.load(f)
    except: consensus = {}
        
    target_codes = set([t["code"] for t in targets if not t["code"].startswith("00")])
    
    codes_to_fetch = set()
    if args.code:
        codes_to_fetch.add(args.code)
    elif args.all:
        codes_to_fetch = target_codes
    elif args.missing:
        codes_to_fetch = target_codes - set(consensus.keys())
    else:
        print("Please specify --code, --missing, or --all")
        return
        
    if not codes_to_fetch:
        print("No stocks to fetch.")
        return
        
    print(f"Fetching targets for: {codes_to_fetch}")
    for code in codes_to_fetch:
        print(f"🔍 Scraping news for {code}...")
        news = fetch_news(code)
        if not news:
            print(f"No news found for {code}")
            continue
            
        print(f"🤖 Analyzing with Gemini for {code}...")
        extracted = extract_targets_with_gemini(news, code)
        
        if extracted and "平均" in extracted and extracted["平均"] > 0:
            update_consensus(code, extracted)
        else:
            print(f"⚠️ Could not extract valid targets for {code}")
            
        import time
        # 加入 4 秒延遲以符合免費版 Gemini 15 RPM 的限制
        print("Waiting 4 seconds to respect API rate limits...")
        time.sleep(4)

if __name__ == "__main__":
    main()
