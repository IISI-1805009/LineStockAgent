import os
from openai import OpenAI
import opencc

def get_stock_news(stock_name: str, stock_code: str) -> str:
    """Fetch recent local news for a stock using Google News RSS (Taiwan)."""
    import urllib.request
    import urllib.parse
    import xml.etree.ElementTree as ET

    try:
        query = urllib.parse.quote(f"{stock_name} 股票")
        url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        response = urllib.request.urlopen(req)
        xml_data = response.read()
        root = ET.fromstring(xml_data)
        
        news_list = []
        for idx, item in enumerate(root.findall(".//item")[:5], 1):
            title = item.find("title").text
            pubDate = item.find("pubDate").text
            news_list.append(f"{idx}. {title} ({pubDate})")
            
        if not news_list:
            return "無法取得近期新聞。"
            
        return "\n".join(news_list)
    except Exception as e:
        print(f"Error fetching news for {stock_code}: {e}")
        return "新聞搜尋失敗，僅依據目前數據進行分析。"

def generate_health_check_report(stock_data: dict, news: str) -> str:
    """Generate a health check report using local Hermes 3 model."""
    import json
    try:
        raw_data_str = stock_data.get('raw_data', '{}')
        try:
            raw_data = json.loads(raw_data_str)
        except:
            raw_data = {}
            
        ma20 = raw_data.get('MA20', '未知')
        ma60 = raw_data.get('MA60', '未知')
        rsi = raw_data.get('RSI', '未知')
        
        client = OpenAI(
            base_url='http://localhost:11434/v1',
            api_key='ollama' # 本地端不需要真實金鑰
        )
        
        prompt = f"""
你是一位專業的台股分析師。請根據以下系統提供的個股數據與近期新聞，為這檔股票進行「股票健檢」，並給予具體的投資建議。

### 股票數據：
- 股票名稱與代號：{stock_data.get('stock_name', '未知')} ({stock_data.get('stock_code', '未知')})
- 最新股價：{stock_data.get('current_price', '未知')} 元
- 月線 (MA20)：{ma20} 元 ｜ 季線 (MA60)：{ma60} 元
- 營收成長 (YoY)：{stock_data.get('revenue_yoy', '未知')}%
- 外資平均目標價：{stock_data.get('target_price', '未知')} 元
- 籌碼面 (外資近一月買超)：{stock_data.get('foreign_buy', '未知')} 張
- 技術指標 (RSI)：{rsi}
- 系統短線建議：{stock_data.get('short_term_rec', '未知')} ({stock_data.get('short_term_reason', '未知')})
- 系統長線建議：{stock_data.get('long_term_rec', '未知')} ({stock_data.get('long_term_reason', '未知')})

### 近期新聞：
{news}

### 輸出要求：
請直接輸出 **HTML 格式**，不要包含 ```html 標籤。使用內聯樣式 (inline CSS) 確保在深色背景下依然美觀 (如使用 var(--text-primary) 或適當顏色)，並使用以下結構：
1. `<h3>最新健檢數據總結</h3>`：請用無序列表 (ul) 條列呈現上述的最新股價、月/季線、營收成長、目標價、籌碼與 RSI。並在每項後面加上簡短的狀態評語 (例如：極度強勁、極度超賣等)。
2. `<h3>近期新聞重點</h3>`：總結上述新聞的核心利多/利空。
3. `<h3>投資操作建議 (雙軌系統分析)</h3>`：請務必分成兩部分清楚說明：
   - 🏃‍♂️ **短線波段建議**：結合系統短線建議與最新新聞。若建議「觀望」，請強調「短線不接刀」等保護資金的觀念。
   - 🧘‍♂️ **長線存股建議**：強烈結合系統長線建議與理由！如果理由中出現「價值錯殺」、「乖離過大」、「嚴重超賣」等字眼，請向使用者解釋這是一檔「高成長優質股」，目前大跌是「長線撿便宜」的黃金買點；如果理由是「估值偏高」，請提醒耐心等待。
請用專業且生動的口吻撰寫，讓使用者能清楚理解短線投機與長線投資的區別。
"""

        response = client.chat.completions.create(
            model="hermes3:8b",
            messages=[
                {"role": "system", "content": "You are a professional Taiwanese stock analyst. You MUST reply in Traditional Chinese (zh-TW). 嚴禁使用簡體中文，請一律使用繁體中文回覆。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        
        raw_content = response.choices[0].message.content
        
        # 使用 OpenCC 強制轉換為台灣繁體中文
        converter = opencc.OpenCC('s2twp')
        zh_tw_content = converter.convert(raw_content)
        
        # 移除可能包含的 markdown 標記
        html_content = zh_tw_content.strip()
        if html_content.startswith("```html"):
            html_content = html_content[7:]
        if html_content.startswith("```"):
            html_content = html_content[3:]
        if html_content.endswith("```"):
            html_content = html_content[:-3]
            
        return html_content.strip()
    except Exception as e:
        error_msg = str(e)
        print(f"Error generating report: {error_msg}")
        return f"<h3>產生報告失敗</h3><p>請確認 Ollama 正在運行 (ollama run hermes3:8b)。錯誤訊息：{error_msg}</p>"

def generate_market_trend_report(market_data: dict) -> str:
    """Generate a market trend report using local Hermes 3 model."""
    import json
    try:
        client = OpenAI(
            base_url='http://localhost:11434/v1',
            api_key='ollama'
        )
        
        prompt = f"""
你是一位專業的台股大盤分析師。請根據以下系統提供的最新台股大盤數據，進行「大盤趨勢分析」，並給出具體的「資金保留比例與投資策略建議」。

【資金配置指導原則】
為了保持建議的一致性，請嚴格參考以下標準來給出建議投入資金：
- 若大盤趨勢為「多頭」或「強勢」，建議投入資金為 60% ~ 80%。
- 若大盤趨勢為「盤整」或「震盪」，建議投入資金為 40% ~ 50%。
- 若大盤趨勢為「空頭」或「弱勢」，建議投入資金為 10% ~ 30%。

### 市場數據：
- 更新時間：{market_data.get('update_date', '未知')}
- 加權指數 (大盤)：{market_data.get('TWII_price', '未知')}
- 大盤月線 (MA20)：{market_data.get('TWII_ma20', '未知')} ｜ 季線 (MA60)：{market_data.get('TWII_ma60', '未知')}
- 大盤趨勢：{market_data.get('TWII_trend', '未知')}
- 全市場 PE (本益比) 中位數：{market_data.get('market_pe_median', '未知')}
- 全市場 PB (股價淨值比) 中位數：{market_data.get('market_pb_median', '未知')}

### 輸出要求：
請直接輸出 **HTML 格式**，不要包含 ```html 標籤。使用內聯樣式 (inline CSS) 確保在深色背景下依然美觀。請務必「嚴格遵守」以下結構排版，直接替換其中的數據與分析即可：

<div style="font-size: 16px; line-height: 1.8;">
<p>目前整體建議：</p>

<p>📊 <strong>市場狀態：[你的結論，例如：⚖️ 盤整偏多]</strong> (大盤：{market_data.get('TWII_trend', '未知')})</p>

<p><strong>🔮 台股大盤趨勢預測：</strong></p>
<ul style="list-style-type: disc; padding-left: 20px; margin-left: 0;">
    <li><strong>短期 (1-2週)</strong>：[趨勢圖示與文字，例如 ⚖️ 震盪換手]
        <ul style="list-style-type: circle; padding-left: 20px; margin-left: 0;">
            <li><strong>預計區間：[填寫預測區間]</strong></li>
            <li><em>註：[填寫短期分析與均線狀況]</em></li>
        </ul>
    </li>
    <li><strong>中期 (1-3月)</strong>：[趨勢圖示與文字，例如 📈 多頭排列]
        <ul style="list-style-type: circle; padding-left: 20px; margin-left: 0;">
            <li><strong>預計區間：[填寫預測區間]</strong></li>
            <li><em>註：[填寫中期分析與估值狀況]</em></li>
        </ul>
    </li>
    <li><strong>長期 (6月+)</strong>：[趨勢圖示與文字，例如 💎 長多看漲]
        <ul style="list-style-type: circle; padding-left: 20px; margin-left: 0;">
            <li><strong>預計區間：[填寫預測區間]</strong></li>
            <li><em>註：[填寫長期護城河或大環境分析]</em></li>
        </ul>
    </li>
</ul>

<p>💡 <strong>總結建議：[填寫一句話總結]</strong><br>
💰 <strong>資金配置：建議投入資金：[X]% | 保留現金：[Y]% (注意：X與Y相加必須剛好等於100)</strong><br>
🕒 更新時間：{market_data.get('update_date', '未知')}</p>
</div>
"""

        response = client.chat.completions.create(
            model="hermes3:8b",
            messages=[
                {"role": "system", "content": "You are a professional Taiwanese stock analyst. You MUST reply in Traditional Chinese (zh-TW). 嚴禁使用簡體中文，請一律使用繁體中文回覆。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        
        raw_content = response.choices[0].message.content
        
        # 使用 OpenCC 強制轉換為台灣繁體中文
        converter = opencc.OpenCC('s2twp')
        zh_tw_content = converter.convert(raw_content)
        
        # 移除可能包含的 markdown 標記
        html_content = zh_tw_content.strip()
        if html_content.startswith("```html"):
            html_content = html_content[7:]
        if html_content.startswith("```"):
            html_content = html_content[3:]
        if html_content.endswith("```"):
            html_content = html_content[:-3]
            
        m_rsi = market_data.get('TWII_rsi', 50.0)
        m_bias = market_data.get('TWII_bias', 0.0)
        
        timing_html = ""
        if m_rsi < 35 or m_bias < -5.0:
            timing_html = f"""
<div style="background: rgba(231, 76, 60, 0.15); border-left: 5px solid #e74c3c; padding: 15px; margin-bottom: 20px; border-radius: 4px;">
    <h3 style="margin-top: 0; color: #e74c3c; display: flex; align-items: center; gap: 8px;">
        <span style="font-size: 24px;">🔴</span> 超賣（買進時機）
    </h3>
    <p style="margin: 0; color: var(--text-primary);">
        目前大盤 RSI ({m_rsi}) 或季線乖離率 ({m_bias}%) 處於極低水準，顯示市場出現非理性恐慌或超賣。
        歷史經驗顯示，這是長線資金分批撿便宜的絕佳時機！建議偏向買方操作。
    </p>
</div>
"""
        elif m_rsi > 75 or m_bias > 10.0:
            timing_html = f"""
<div style="background: rgba(46, 204, 113, 0.15); border-left: 5px solid #2ecc71; padding: 15px; margin-bottom: 20px; border-radius: 4px;">
    <h3 style="margin-top: 0; color: #2ecc71; display: flex; align-items: center; gap: 8px;">
        <span style="font-size: 24px;">🟢</span> 超買（逢高減碼）
    </h3>
    <p style="margin: 0; color: var(--text-primary);">
        目前大盤 RSI ({m_rsi}) 或季線乖離率 ({m_bias}%) 處於極高水準，顯示市場過熱。
        建議適度獲利了結或減碼，避免追高風險。
    </p>
</div>
"""
        else:
            timing_html = f"""
<div style="background: rgba(241, 196, 15, 0.15); border-left: 5px solid #f1c40f; padding: 15px; margin-bottom: 20px; border-radius: 4px;">
    <h3 style="margin-top: 0; color: #f1c40f; display: flex; align-items: center; gap: 8px;">
        <span style="font-size: 24px;">⚪</span> 中立觀望 (無極端訊號)
    </h3>
    <p style="margin: 0; color: var(--text-primary);">
        目前大盤 RSI ({m_rsi}) 與季線乖離率 ({m_bias}%) 處於正常區間，無明顯超買或超賣現象，請依循各股基本面進行操作。
    </p>
</div>
"""

        return (timing_html + html_content.strip()).strip()
    except Exception as e:
        error_msg = str(e)
        print(f"Error generating market report: {error_msg}")
        return f"<h3>產生報告失敗</h3><p>請確認 Ollama 正在運行 (ollama run hermes3:8b)。錯誤訊息：{error_msg}</p>"
