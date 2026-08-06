import json
import requests
import statistics
import urllib3
import time
import os
import yfinance as yf
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
TARGETS_FILE = "data/targets.json"
LATEST_DATA_FILE = "data/latest_data.json"
ADVANCED_METRICS_FILE = "data/advanced_metrics.json"

ENDPOINTS = {
    "TWSE_STATS": "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
    "TPEx_STATS": "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis",
    "INST_TRADES": "https://openapi.twse.com.tw/v1/fund/T86_ALL"
    # 注：月營收正確 API 已改用 FinMind (fetch_monthly_revenue)
}

def fetch_json(url: str, retries: int = 3, backoff: int = 2) -> Any:
    for i in range(retries):
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, verify=False, timeout=20)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            if i == retries - 1: print(f"Failed to fetch {url}: {e}")
        time.sleep(backoff * (i + 1))
    return []

def clean_num(val) -> Optional[float]:
    if val is None: return None
    if isinstance(val, (int, float)): return val
    s = str(val).strip().replace(",", "")
    if s in ["", "-", "--", "N/A"]: return None
    try:
        return float(s)
    except:
        return None

def get_momentum(yoy=None, stock_trend=None, price_3m_chg=None):
    """Multi-source momentum with price momentum fallback."""
    if yoy is not None:
        if yoy >= 20: return "🚀 強勁"
        if yoy >= 5: return "📈 穩健"
        if yoy >= -5: return "⚖️ 盤整"
        if yoy >= -20: return "📉 衰退"
        return "⚠️ 警戒"
    
    # Fallback 1: 近 3 個月股價漲幅作為替代動能指標
    if price_3m_chg is not None:
        if price_3m_chg >= 15: return "🚀 強勁 (價動)"
        if price_3m_chg >= 5:  return "📈 穩健 (價動)"
        if price_3m_chg >= -5: return "⚖️ 盤整 (價動)"
        if price_3m_chg >= -15: return "📉 衰退 (價動)"
        return "⚠️ 警戒 (價動)"
    
    # Fallback 2: 均線跨度判斷
    if stock_trend == "多頭排列":
        return "📈 穩健 (均線)"
    return "未知"

def get_targets():
    try:
        with open(TARGETS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except: return []

def fetch_monthly_revenue(target_codes: list) -> dict:
    """
    使用 FinMind 公開 API 批次抴取所有目標標的的月營收，
    計算 YoY 成長率。上市與上櫃股均支援。
    Returns: {code: {"yoy": float, "consec_3m": bool, "turnaround": bool}} 
    """
    from datetime import datetime, timedelta
    start_date = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
    url_base = "https://api.finmindtrade.com/api/v4/data"
    revenue_map = {}
    
    for code in target_codes:
        # ETF 不抓營收
        if code.startswith('00'):
            continue
        try:
            r = requests.get(
                url_base,
                params={'dataset': 'TaiwanStockMonthRevenue', 'data_id': code, 'start_date': start_date},
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=10,
                verify=False
            )
            if r.status_code != 200:
                continue
            records = r.json().get('data', [])
            if len(records) < 2:
                continue
                
            # 排序確保最新在最後
            records = sorted(records, key=lambda x: (x.get('revenue_year', 0), x.get('revenue_month', 0)))
            
            recent_yoys = []
            for i in range(1, 4):
                if len(records) >= i:
                    rec = records[-i]
                    cur_rev = rec.get('revenue', 0)
                    cur_year = rec.get('revenue_year')
                    cur_month = rec.get('revenue_month')
                    
                    prev_year_rec = next(
                        (x for x in records if x.get('revenue_year') == cur_year - 1 and x.get('revenue_month') == cur_month),
                        None
                    )
                    if prev_year_rec and prev_year_rec.get('revenue', 0) > 0:
                        yoy = round(((cur_rev - prev_year_rec['revenue']) / prev_year_rec['revenue']) * 100, 2)
                        recent_yoys.append(yoy)
            
            if not recent_yoys:
                continue
                
            latest_yoy = recent_yoys[0]
            consec_3m = len(recent_yoys) == 3 and all(y > 0 for y in recent_yoys)
            
            # 轉機訊號：上個月 YoY < 0，這個月 YoY > 0
            turnaround = False
            if len(recent_yoys) >= 2:
                turnaround = (recent_yoys[1] < 0) and (recent_yoys[0] > 0)
                
            revenue_map[code] = {
                "yoy": latest_yoy,
                "consec_3m": consec_3m,
                "turnaround": turnaround
            }
        except Exception as e:
            print(f"[FinMind] 抓取 {code} 營收失敗: {e}")
        time.sleep(0.15)  # 避免被阻擋
    
    return revenue_map

def fetch_finmind_dataset(dataset: str, data_id: str, start_date: str) -> list:
    url_base = "https://api.finmindtrade.com/api/v4/data"
    for i in range(3):
        try:
            r = requests.get(
                url_base,
                params={'dataset': dataset, 'data_id': data_id, 'start_date': start_date},
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=15,
                verify=False
            )
            if r.status_code == 200:
                return r.json().get('data', [])
        except Exception as e:
            time.sleep(1 * (i + 1))
    return []

def process_advanced_metrics(code: str) -> dict:
    # ETF 不抓財報
    if code.startswith('00'):
        return {}
        
    start_date_5y = (datetime.now() - timedelta(days=365*6)).strftime('%Y-%m-%d')
    print(f"Fetching {code} advanced financial data...")
    
    is_data = fetch_finmind_dataset('TaiwanStockFinancialStatements', code, start_date_5y)
    bs_data = fetch_finmind_dataset('TaiwanStockBalanceSheet', code, start_date_5y)
    cf_data = fetch_finmind_dataset('TaiwanStockCashFlowsStatement', code, start_date_5y)
    per_data = fetch_finmind_dataset('TaiwanStockPER', code, start_date_5y)
    div_data = fetch_finmind_dataset('TaiwanStockDividend', code, start_date_5y)
    
    time.sleep(0.5)
    
    metrics = {}
    
    # 1. PE / PB lowest 20%
    if per_data:
        pes = [d['PER'] for d in per_data if d.get('PER') and d['PER'] > 0]
        pbs = [d['PBR'] for d in per_data if d.get('PBR') and d['PBR'] > 0]
        if pes and len(pes) > 100:
            current_pe = pes[-1]
            pe_20th = sorted(pes)[int(len(pes)*0.2)]
            metrics['pe_5y_lowest_20'] = current_pe <= pe_20th
        if pbs and len(pbs) > 100:
            current_pb = pbs[-1]
            pb_20th = sorted(pbs)[int(len(pbs)*0.2)]
            metrics['pb_5y_lowest_20'] = current_pb <= pb_20th

    if not is_data or not bs_data or not cf_data:
        return metrics
        
    is_by_date = {}
    for d in is_data:
        date = d['date']
        if date not in is_by_date: is_by_date[date] = {}
        is_by_date[date][d['type']] = d['value']
        
    bs_by_date = {}
    for d in bs_data:
        date = d['date']
        if date not in bs_by_date: bs_by_date[date] = {}
        bs_by_date[date][d['type']] = d['value']
        
    cf_by_date = {}
    for d in cf_data:
        date = d['date']
        if date not in cf_by_date: cf_by_date[date] = {}
        cf_by_date[date][d['type']] = d['value']
        
    sorted_dates = sorted(list(set(is_by_date.keys()) & set(bs_by_date.keys()) & set(cf_by_date.keys())))
    if sorted_dates:
        latest_date = sorted_dates[-1]
        prev_year_date = str(int(latest_date[:4])-1) + latest_date[4:]
        if prev_year_date not in sorted_dates and len(sorted_dates) >= 5:
            prev_year_date = sorted_dates[-5]
            
        latest_is = is_by_date.get(latest_date, {})
        latest_bs = bs_by_date.get(latest_date, {})
        prev_is = is_by_date.get(prev_year_date, {})
        prev_bs = bs_by_date.get(prev_year_date, {})
        
        def calc_turnover(is_d, bs_d):
            rev = is_d.get('Revenue', 0)
            cogs = is_d.get('CostOfGoodsSold', 0)
            ar = bs_d.get('AccountsReceivableNet', 0)
            inv = bs_d.get('Inventories', 0)
            ar_days = (ar / rev * 90) if rev > 0 else 999
            inv_days = (inv / cogs * 90) if cogs > 0 else 999
            return ar_days, inv_days
            
        ar_days, inv_days = calc_turnover(latest_is, latest_bs)
        prev_ar_days, prev_inv_days = calc_turnover(prev_is, prev_bs)
        
        metrics['ar_days_improved'] = ar_days <= prev_ar_days
        metrics['inv_days_improved'] = inv_days <= prev_inv_days
        metrics['gross_margin_yoy'] = latest_is.get('GrossProfit', 0) > prev_is.get('GrossProfit', 0)
        metrics['operating_margin_yoy'] = latest_is.get('OperatingIncome', 0) > prev_is.get('OperatingIncome', 0)
        metrics['pre_tax_yoy'] = latest_is.get('PreTaxIncome', 0) > prev_is.get('PreTaxIncome', 0)
        metrics['net_income_yoy'] = latest_is.get('IncomeAfterTaxes', 0) > prev_is.get('IncomeAfterTaxes', 0)
        
        # 5 year Cash Flows & Dividends
        years_data = {}
        for d in sorted_dates:
            year = d[:4]
            if year not in years_data: years_data[year] = {'ocf': 0, 'icf': 0, 'net_income': 0, 'eps': 0}
            years_data[year]['ocf'] += cf_by_date[d].get('CashFlowsFromOperatingActivities', cf_by_date[d].get('NetCashInflowFromOperatingActivities', 0))
            years_data[year]['icf'] += cf_by_date[d].get('CashProvidedByInvestingActivities', 0)
            years_data[year]['net_income'] += is_by_date[d].get('IncomeAfterTaxes', 0)
            years_data[year]['eps'] += is_by_date[d].get('EPS', 0)
            
        recent_years = sorted(years_data.keys())[-5:]
        
        fcf_positive_count = 0
        fcf_total = 0
        ocf_to_ni_over_100_count = 0
        ocf_to_ni_total = []
        
        for y in recent_years:
            ocf = years_data[y]['ocf']
            fcf = ocf + years_data[y]['icf']
            ni = years_data[y]['net_income']
            if fcf > 0: fcf_positive_count += 1
            fcf_total += fcf
            if ni > 0 and (ocf / ni) >= 1.0:
                ocf_to_ni_over_100_count += 1
            if ni > 0:
                ocf_to_ni_total.append(ocf / ni)
                
        metrics['fcf_3_of_5_positive'] = fcf_positive_count >= 3
        metrics['fcf_5y_avg_positive'] = fcf_total > 0
        metrics['ocf_ni_3_of_5_over_100'] = ocf_to_ni_over_100_count >= 3
        metrics['ocf_ni_5y_avg_over_100'] = (sum(ocf_to_ni_total)/len(ocf_to_ni_total)) >= 1.0 if ocf_to_ni_total else False
        
        # Dividend Payout
        if div_data:
            div_by_year = {}
            for d in div_data:
                # "114年第4季" or "2024"
                y_str = str(d.get('year', ''))
                if '年' in y_str:
                    try:
                        y = int(y_str.split('年')[0]) + 1911
                    except: continue
                else:
                    try:
                        y = int(y_str[:4])
                    except: continue
                
                if y not in div_by_year: div_by_year[y] = 0
                div_by_year[y] += d.get('StockEarningsDistribution', 0) + d.get('CashEarningsDistribution', 0)
            
            payout_over_50_count = 0
            payouts = []
            for y in recent_years:
                div = div_by_year.get(int(y), 0)
                eps = years_data[y]['eps']
                if eps > 0:
                    payout = div / eps
                    payouts.append(payout)
                    if payout >= 0.5: payout_over_50_count += 1
            
            metrics['div_payout_3_of_5_over_50'] = payout_over_50_count >= 3
            metrics['div_payout_5y_avg_over_50'] = (sum(payouts)/len(payouts)) >= 0.5 if payouts else False

    return metrics

def get_consecutive_dividend_years(code: str, exchange: str) -> dict:
    """Fetch consecutive dividend years and 5-year avg yield from yfinance."""
    suffix = ".TW" if exchange != "TPEx" else ".TWO"
    if code in ["^TWII", "^TWOI"]: return {"consec": 0, "avg_yield_5y": 0.0}
    try:
        tkr = yf.Ticker(f"{code}{suffix}")
        
        # 1. 抓取 5 年平均殖利率
        avg_yield_5y = 0.0
        info = tkr.info
        
        if not info or len(info) < 5:
            return None
            
        if "fiveYearAvgDividendYield" in info and info["fiveYearAvgDividendYield"]:
            avg_yield_5y = float(info["fiveYearAvgDividendYield"])
            
        # 2. 計算連續配息年數
        divs = tkr.dividends
        consec = 0
        if not divs.empty:
            years = sorted(divs.index.year.unique().tolist(), reverse=True)
            if years:
                current_year = datetime.now().year
                check_year = years[0] if (years[0] == current_year or years[0] == current_year - 1) else -1
                
                if check_year != -1:
                    for y in years:
                        if y == check_year:
                            consec += 1
                            check_year -= 1
                        elif y > check_year:
                            continue
                        else:
                            break
                            
        return {"consec": consec, "avg_yield_5y": avg_yield_5y}
    except Exception as e:
        print(f"Failed to fetch dividend for {code}: {e}")
        return None

def fetch_yahoo_data(code: str, market: str = ".TW") -> Optional[Dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0"}
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{code}{market}?interval=1d&range=3y"
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200: return None
        data = r.json()
        result = data['chart']['result'][0]
        meta = result['meta']
        indicators = result['indicators']['quote'][0]
        
        # Get adjclose if available
        adjclose = []
        if 'adjclose' in result['indicators'] and result['indicators']['adjclose']:
            adjclose = result['indicators']['adjclose'][0].get('adjclose', [])
            
        closes = indicators.get('close', [])
        opens = indicators.get('open', [])
        highs = indicators.get('high', [])
        lows = indicators.get('low', [])
        volumes = indicators.get('volume', [])
        
        valid_closes = []
        valid_opens = []
        valid_highs = []
        valid_lows = []
        valid_volumes = []
        
        for i in range(len(closes)):
            if closes[i] is not None:
                c = closes[i]
                o = opens[i] if len(opens) > i and opens[i] is not None else c
                h = highs[i] if len(highs) > i and highs[i] is not None else c
                l = lows[i] if len(lows) > i and lows[i] is not None else c
                v = volumes[i] if len(volumes) > i and volumes[i] is not None else 0
                
                # Apply adjclose ratio
                if len(adjclose) > i and adjclose[i] is not None and c > 0:
                    ratio = adjclose[i] / c
                    c = adjclose[i]
                    o = o * ratio
                    h = h * ratio
                    l = l * ratio
                
                valid_closes.append(c)
                valid_opens.append(o)
                valid_highs.append(h)
                valid_lows.append(l)
                valid_volumes.append(v)
        
        return {
            "price": meta.get("regularMarketPrice") or (valid_closes[-1] if valid_closes else None),
            "name": meta.get("longName") or meta.get("shortName"),
            "history": valid_closes,
            "opens": valid_opens,
            "highs": valid_highs,
            "lows": valid_lows,
            "volumes": valid_volumes,
            "type": meta.get("instrumentType") # ETF or EQUITY
        }
    except: return None

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1: return [50] * len(prices)
    deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    rsi_list: list[float] = [50.0] * period
    
    if avg_loss == 0:
        rsi_list.append(100)
    else:
        rs = avg_gain / avg_loss
        rsi_list.append(100 - (100 / (1 + rs)))
    
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi_list.append(100)
        else:
            rs = avg_gain / avg_loss
            rsi_list.append(100 - (100 / (1 + rs)))
            
    return rsi_list

def calculate_atr(highs, lows, closes, period=14):
    if len(closes) < period + 1: return 0
    tr_list = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], 
                 abs(highs[i] - closes[i-1]), 
                 abs(lows[i] - closes[i-1]))
        tr_list.append(tr)
    return sum(tr_list[-period:]) / period

def detect_rsi_divergence(closes, rsi_series, atr=0, lookback=60):
    if len(closes) < lookback or len(rsi_series) < lookback:
        return "None"
    
    recent_closes = closes[-lookback:]
    recent_rsis = rsi_series[-lookback:]
    
    current_close = recent_closes[-1]
    current_rsi = recent_rsis[-1]
    
    past_closes = recent_closes[:-2]
    past_rsis = recent_rsis[:-2]
    
    if not past_closes:
        return "None"
        
    min_past_close = min(past_closes)
    min_idx = past_closes.index(min_past_close)
    min_past_rsi = past_rsis[min_idx]
    
    max_past_close = max(past_closes)
    max_idx = past_closes.index(max_past_close)
    max_past_rsi = past_rsis[max_idx]
    
    volatility = (atr / current_close) if current_close > 0 else 0
    
    # Bullish Divergence
    if current_close <= min_past_close * 1.01 and current_rsi > min_past_rsi + 5 and current_rsi < 50:
        if volatility > 0.02:
            return "Bullish"
            
    # Bearish Divergence
    if current_close >= max_past_close * 0.99 and current_rsi < max_past_rsi - 5 and current_rsi > 50:
        if volatility > 0.02:
            return "Bearish"
            
    return "None"

def calculate_ema(prices, days):
    if not prices: return []
    ema = [prices[0]]
    multiplier = 2 / (days + 1)
    for price in prices[1:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    return ema

def calculate_kd(highs, lows, closes, period=9):
    if len(closes) < period: 
        return 50, 50, 50, 50
    k, d = 50, 50
    k_list, d_list = [], []
    
    for i in range(period - 1, len(closes)):
        sub_highs = highs[i - period + 1: i + 1]
        sub_lows = lows[i - period + 1: i + 1]
        hh = max(sub_highs)
        ll = min(sub_lows)
        
        if hh == ll:
            rsv = 50
        else:
            rsv = (closes[i] - ll) / (hh - ll) * 100
            
        k = (2/3) * k + (1/3) * rsv
        d = (2/3) * d + (1/3) * k
        k_list.append(k)
        d_list.append(d)
        
    prev_k = k_list[-2] if len(k_list) > 1 else 50
    prev_d = d_list[-2] if len(d_list) > 1 else 50
        
    return k, d, prev_k, prev_d

def calculate_indicators(yahoo_data: Dict[str, Any]):
    closes = yahoo_data["history"]
    opens = yahoo_data.get("opens", closes)
    highs = yahoo_data.get("highs", closes)
    lows = yahoo_data.get("lows", closes)
    volumes = yahoo_data.get("volumes", []) # Assuming volume data might be available, fallback to empty if not
    price = yahoo_data["price"]
    
    ma5 = statistics.mean(closes[-5:]) if len(closes) >= 5 else statistics.mean(closes)
    ma20 = statistics.mean(closes[-20:]) if len(closes) >= 20 else statistics.mean(closes)
    ma60 = statistics.mean(closes[-60:]) if len(closes) >= 60 else statistics.mean(closes)
    
    # Bollinger Bands
    std20 = statistics.stdev(closes[-20:]) if len(closes) >= 20 else 0
    bb_upper = ma20 + (2 * std20)
    bb_lower = ma20 - (2 * std20)
    
    atr = calculate_atr(highs, lows, closes)
    
    rsi_series = calculate_rsi(closes)
    current_rsi = rsi_series[-1] if rsi_series else 50
    rsi_div = detect_rsi_divergence(closes, rsi_series, atr=atr)
    
    kd_k, kd_d, prev_k, prev_d = calculate_kd(highs, lows, closes)
    
    is_bottom_golden_cross = kd_k < 35 and prev_k <= prev_d and kd_k > kd_d
    
    # 策略判斷：黃金買點 (KD < 40 + RSI > 50 + 量增 + 站上 MA20 + 黃金交叉)
    vol_ma5 = statistics.mean(volumes[-5:]) if len(volumes) >= 5 else 0
    vol_ma20 = statistics.mean(volumes[-20:]) if len(volumes) >= 20 else 0
    prev_vol_ma5 = statistics.mean(volumes[-6:-1]) if len(volumes) >= 6 else 0
    
    current_vol = volumes[-1] if volumes else 0
    is_up_day = closes[-1] > closes[-2] if len(closes) > 1 else True
    is_volume_surge = (current_vol > vol_ma5) and is_up_day
    is_volume_drop = (current_vol > vol_ma5) and not is_up_day
    
    # 選項C：量能築底確認 (近 5 日均量 > 近 20 日均量，且量能持續放大)
    is_vol_warming = (vol_ma5 > vol_ma20 * 1.1) and (vol_ma5 >= prev_vol_ma5)
    
    is_golden_buy = (kd_k < 40 and kd_d < 40 and 
                     prev_k <= prev_d and kd_k > kd_d and 
                     price > ma20 and current_rsi > 50 and is_volume_surge)
    
    # Advanced Breakout Analytics (VCP & Accumulation)
    recent_5d_low = min(lows[-5:]) if len(lows) >= 5 else min(lows)  # type: ignore
    recent_20d_high = max(highs[-20:]) if len(highs) >= 20 else max(highs)  # type: ignore
    recent_20d_low = min(lows[-20:]) if len(lows) >= 20 else min(lows)  # type: ignore
    
    # MACD Calculation
    ema12 = calculate_ema(closes, 12)
    ema26 = calculate_ema(closes, 26)
    dif = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
    macd9 = calculate_ema(dif, 9)
    osc = [d - m for d, m in zip(dif, macd9)]
    is_macd_golden = False
    if len(osc) >= 2:
        is_macd_golden = osc[-2] <= 0 and osc[-1] > 0 and dif[-1] < 0

    # Hammer Bottom (探底針)
    is_hammer_bottom = False
    if len(opens) > 0 and len(highs) > 0 and len(lows) > 0 and len(closes) > 0:
        c_open, c_high, c_low, c_close = opens[-1], highs[-1], lows[-1], closes[-1]
        lower_shadow = min(c_open, c_close) - c_low
        body = abs(c_close - c_open)
        total_range = c_high - c_low
        if body > 0 and total_range > 0:
            is_hammer_bottom = (lower_shadow > 2 * body) and (lower_shadow > 0.5 * total_range) and is_volume_surge
    
    # Shooting Star / 爆量長上影線 (頭部反轉警訊)
    # 條件：上影線 > 2倍實體 + 上影線占總體 50% 以上 + 爆量 + 股價在 MA20 上方或 RSI > 70
    is_shooting_star = False
    if len(opens) > 0 and len(highs) > 0 and len(lows) > 0 and len(closes) > 0:
        c_open, c_high, c_low, c_close = opens[-1], highs[-1], lows[-1], closes[-1]
        upper_shadow = c_high - max(c_open, c_close)
        body = abs(c_close - c_open)
        total_range = c_high - c_low
        is_high_vol = current_vol > vol_ma5 * 1.5  # 量能爆大：至少 1.5個均量
        is_overbought_zone = price > ma20 or current_rsi > 70
        if total_range > 0:
            is_shooting_star = (
                upper_shadow > 2 * max(body, 0.001 * price) and  # 上影線體長超過 2倍實體
                upper_shadow > 0.5 * total_range and              # 上影線占總體半以上
                is_high_vol and                                    # 爆量確認
                is_overbought_zone                                 # 在高檔區或 RSI 高熱
            )
    
    # VCP (Volatility Contraction Pattern) Detection
    # If the 20-day range is tight (< 8%) and price is near MA20
    price_range_pct = (recent_20d_high - recent_20d_low) / recent_20d_low if recent_20d_low > 0 else 0
    is_vcp = price_range_pct < 0.08 and abs(price - ma20)/ma20 < 0.03
    
    # Moving Average Compression (MA5, MA20, MA60 within 3% of each other)
    ma_max = max(ma5, ma20, ma60)
    ma_min = min(ma5, ma20, ma60)
    is_ma_compressed = (ma_max - ma_min) / ma_min < 0.03 if ma_min > 0 else False
    
    # Breakout logic: Price broke above 20d high or compressed MAs today
    is_breakout = price > max(ma20, ma60) and price >= recent_20d_high * 0.98
    
    technical_flags = []
    if is_vcp: technical_flags.append("VCP")
    if is_ma_compressed: technical_flags.append("MACompressed")
    if is_breakout: technical_flags.append("Breakout")
    if is_golden_buy: technical_flags.append("GoldenBuy")
    if is_volume_surge: technical_flags.append("VolumeSurge")
    if is_volume_drop: technical_flags.append("VolumeDrop")
    if is_vol_warming: technical_flags.append("VolWarming")
    if is_shooting_star: technical_flags.append("ShootingStar")
    if is_bottom_golden_cross: technical_flags.append("BottomGoldenCross")
    if is_macd_golden: technical_flags.append("MACDGolden")
    if is_hammer_bottom: technical_flags.append("HammerBottom")

    return {
        "ma5": ma5,
        "ma20": ma20,
        "ma60": ma60,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "rsi": current_rsi,
        "rsi_divergence": rsi_div,
        "atr": atr,
        "recent_5d_low": recent_5d_low,
        "recent_20d_high": recent_20d_high,
        "kd_k": kd_k,
        "kd_d": kd_d,
        "current_vol": current_vol,
        "vol_ma5": vol_ma5,
        "vol_ma20": vol_ma20,
        "technical_flags": technical_flags,
        "is_new_stock": len(closes) < 500
    }

def get_suggested_prices(price, indicators, momentum, market_trend, is_etf, current_yield, target_price=None):
    # 1. Suggested Buy Logic (Triple Consensus)
    # Factor 1: Technical Support (Bollinger Lower + MA)
    stock_trend = "多頭排列" if indicators["ma20"] > indicators["ma60"] else "空/盤整"
    
    # Safe support level (using Bollinger Lower or MA20)
    # floor support at 85% of MA20 to ensure it stays grounded
    safe_ma_support = indicators["ma20"] * 0.85
    calculated_support = min(indicators["ma20"], indicators["bb_lower"]) if indicators["bb_lower"] > 0 else indicators["ma20"]
    support = max(safe_ma_support, calculated_support)
    
    # Factor 2: Momentum & Market Adjustment
    if momentum == "🚀 強勁": base_discount = 0.97
    elif momentum == "📈 穩健": base_discount = 0.95
    elif momentum == "⚖️ 盤整": base_discount = 0.92
    else: base_discount = 0.90
    
    if market_trend == "空頭": base_discount -= 0.02
    if indicators["rsi"] > 70: base_discount -= 0.03
    if indicators["rsi"] < 30: base_discount += 0.02
    
    tech_buy_price = support * base_discount
    
    # Factor 3: Institutional Target Price (if available)
    # We take 75% of institutional target as a safe buy zone
    if target_price and target_price > 0:
        # Sanity check: If target price is too extreme (hallucinated or typo), ignore it.
        if target_price > price * 2.5 or target_price < price * 0.4:
            print(f"⚠️ 警告: 目標價 ({target_price}) 與現價 ({price}) 偏差過大，可能為異常資料，將自動忽略該目標價。")
            target_price = None

    if target_price and target_price > 0:
        inst_buy_price = target_price * 0.75
        # 70% Weight on Tech, 30% on Institutional Consensus
        buy_price = (tech_buy_price * 0.7) + (inst_buy_price * 0.3)
    else:
        buy_price = tech_buy_price
    
    # Yield Floor Adjustment
    is_high_yield = is_etf or (current_yield and current_yield >= 3.5)
    if is_high_yield and current_yield and current_yield > 0:
        target_yield = 6.5 if is_etf else 7.5
        yield_floor_price = price * (current_yield / target_yield)
        buy_price = max(buy_price, yield_floor_price)
        
    # 2. Suggested Sell Logic (Consensus Weighted)
    # Factor 1: ATR based Trailing Stop
    atr_factor = 2.5
    if indicators["rsi"] > 80: atr_factor = 1.5 
    atr_stop = price - (indicators["atr"] * atr_factor) if indicators["atr"] > 0 else price * 0.95
    
    # Factor 2: Institutional Consensus (90% of Target)
    # 結合技術壓力區
    bb_upper = indicators.get("bb_upper", price * 1.05)
    recent_20d_high = indicators.get("recent_20d_high", price * 1.05)
    tech_resistance = max(bb_upper, recent_20d_high)
    
    if target_price and target_price > 0:
        # 有目標價時：尊重法人定價，但也要考慮技術壓力
        inst_sell_price = target_price * 0.90
        sell_price = max(inst_sell_price, tech_resistance)
    else:
        # 無目標價時：依賴技術面與動能
        if is_high_yield:
            # 高股息 ETF：防守型，獲利達標或碰壓力就跑
            sell_price = max(price * 1.06, bb_upper)
        elif momentum == "🚀 強勁" or "Breakout" in indicators.get("technical_flags", []):
            # 強勢股或剛突破：讓子彈飛，以更高的技術壓力或大前高做為目標
            sell_price = max(price * 1.12, tech_resistance)
        elif momentum == "📈 穩健":
            sell_price = max(price * 1.08, recent_20d_high)
        else:
            # 盤整或偏弱：反彈有賺就跑
            sell_price = max(price * 1.05, recent_20d_high)
            
    # 安全底線：確保賣出價至少有 3% 的利潤空間
    sell_price = max(sell_price, price * 1.03)
    
    # 三價連動保護：確保 stop_loss < buy_price < sell_price
    atr_stop = min(atr_stop, buy_price * 0.95)  # 停損不得高於買入價的 95%
    sell_price = max(sell_price, buy_price * 1.05)  # 賣出價至少要比買入價高 5%

    return round(buy_price, 2), round(sell_price, 2), round(atr_stop, 2), stock_trend

def fetch_institutional_data():
    url = "https://www.twse.com.tw/fund/T86?response=json&selectType=ALL"
    data = fetch_json(url)
    inst_data = {}
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 只追蹤持倉/關注標的的籌碼歷史，避免檔案膨脹
    target_codes_set = set(t["code"] for t in get_targets())
    
    history_file = "data/chip_history.json"
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
            # 清理：移除不再追蹤的標的
            history = {k: v for k, v in history.items() if k in target_codes_set}
        except:
            history = {}
    else:
        history = {}

    if isinstance(data, dict) and data.get("stat") == "OK":
        for row in data.get("data", []):
            if len(row) < 11: continue
            code = row[0].strip()
            fb_str = str(row[4]).replace(",", "")
            tb_str = str(row[10]).replace(",", "")
            try:
                fb = int(fb_str) // 1000
                tb = int(tb_str) // 1000
            except:
                fb, tb = 0, 0
            
            # 只儲存與處理持倉標的
            if code in target_codes_set:
                if code not in history: history[code] = []
                if not history[code] or history[code][-1].get("date") != today:
                    history[code].append({"date": today, "ForeignBuy": fb, "TrustBuy": tb})
                else:
                    history[code][-1] = {"date": today, "ForeignBuy": fb, "TrustBuy": tb}
                    
                history[code] = history[code][-20:]  # 擴展至 20 天以支援更完整的連買判斷
            
            # inst_data 仍需儲存所有當日數據（用於 inst_buy_ratio 計算）
            f_consec, t_consec = 0, 0
            if code in history:
                for item in reversed(history[code]):
                    if item.get("ForeignBuy", 0) > 0: f_consec += 1
                    else: break
                for item in reversed(history[code]):
                    if item.get("TrustBuy", 0) > 0: t_consec += 1
                    else: break
                
            inst_data[code] = {
                "ForeignBuy": fb, 
                "TrustBuy": tb, 
                "ForeignConsecutiveBuy": f_consec, 
                "TrustConsecutiveBuy": t_consec
            }

    try:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to save chip_history: {e}")
        
    return inst_data

def run_update(target_prices_input=None):
    targets = get_targets()
    target_codes = list(set(t["code"] for t in targets))
    results = {code: {"Code": code, "UpdateDate": datetime.now().strftime("%Y-%m-%d")} for code in target_codes}

    # 1. Fetch Price & Stats
    print("Fetching real-time and fundamental data...")
    twse_s = fetch_json(ENDPOINTS["TWSE_STATS"])
    tpex_s = fetch_json(ENDPOINTS["TPEx_STATS"])
    
    # 準備計算全市場中位數
    market_pe_list = []
    market_pb_list = []
    
    for i in twse_s:
        c = i.get("Code", "").strip()
        pe = clean_num(i.get("PEratio"))
        pb = clean_num(i.get("PBratio"))
        if pe and pe > 0: market_pe_list.append(pe)
        if pb and pb > 0: market_pb_list.append(pb)
        
        if c in results:
            results[c].update({
                "PE": pe, 
                "Yield": clean_num(i.get("DividendYield")), 
                "PB": pb,
                "Name": i.get("Name", "").strip(),
                "NameSource": "OpenAPI",
                "Exchange": "TWSE"
            })

    if tpex_s:
        for i in tpex_s:
            c = i.get("SecuritiesCompanyCode", "").strip()
            pe = clean_num(i.get("PriceEarningRatio"))
            pb = clean_num(i.get("PriceBookRatio"))
            if pe and pe > 0: market_pe_list.append(pe)
            if pb and pb > 0: market_pb_list.append(pb)
            
            if c in results:
                results[c].update({
                    "PE": pe, 
                    "Yield": clean_num(i.get("YieldRatio")), 
                    "PB": pb,
                    "Name": i.get("CompanyName", "").strip(),
                    "NameSource": "OpenAPI",
                    "Exchange": "TPEx"
                })

    market_pe_median = statistics.median(market_pe_list) if market_pe_list else 15.0
    market_pb_median = statistics.median(market_pb_list) if market_pb_list else 1.5

    print("Fetching monthly revenue (FinMind)...")
    revenue_yoy_map = fetch_monthly_revenue(target_codes)
    for code, rev_data in revenue_yoy_map.items():
        if code in results:
            results[code].update({
                "RevenueYoY": rev_data["yoy"], 
                "Consecutive3M_Growth": rev_data["consec_3m"],
                "TurnaroundSignal": rev_data["turnaround"],
                "Momentum": get_momentum(yoy=rev_data["yoy"])
            })

    print("Fetching institutional trades...")
    inst_data = fetch_institutional_data()

    print("Fetching advanced financial statements (FinMind)...")
    
    advanced_metrics_cache = {}
    if os.path.exists(ADVANCED_METRICS_FILE):
        try:
            with open(ADVANCED_METRICS_FILE, "r", encoding="utf-8") as f:
                advanced_metrics_cache = json.load(f)
        except Exception as e:
            print(f"Failed to load {ADVANCED_METRICS_FILE}: {e}")
            
    advanced_metrics_map = {}
    for code in target_codes:
        # 只在快取沒有，或是需要定期更新時抓取 (這裡簡化為若有空值就重抓)
        cached_data = advanced_metrics_cache.get(code)
        if cached_data and len(cached_data) > 2:
            advanced_metrics_map[code] = cached_data
            continue
            
        try:
            new_data = process_advanced_metrics(code)
            if new_data:
                advanced_metrics_map[code] = new_data
                advanced_metrics_cache[code] = new_data
            else:
                advanced_metrics_map[code] = cached_data or {}
        except Exception as e:
            print(f"Failed to fetch advanced metrics for {code}: {e}")
            advanced_metrics_map[code] = cached_data or {}
            
    # 儲存快取
    try:
        with open(ADVANCED_METRICS_FILE, "w", encoding="utf-8") as f:
            json.dump(advanced_metrics_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to save {ADVANCED_METRICS_FILE}: {e}")

    print("Fetching consecutive dividend years...")
    div_cache_file = "data/dividend_cache.json"
    div_cache = {}
    if os.path.exists(div_cache_file):
        try:
            with open(div_cache_file, "r", encoding="utf-8") as f:
                div_cache = json.load(f)
        except Exception:
            pass

    for code in results:
        exchange = results[code].get("Exchange", "TWSE")
        
        div_data = None
        if code in div_cache:
            div_data = div_cache[code]
        else:
            div_data = get_consecutive_dividend_years(code, exchange)
            if div_data is not None:
                div_cache[code] = div_data
            else:
                div_data = {"consec": 0, "avg_yield_5y": 0.0}
                
        results[code]["ConsecutiveDividendYears"] = div_data["consec"]
        results[code]["AvgYield5Y"] = div_data["avg_yield_5y"]
        # Save market medians for recommendation engine
        results[code]["MarketPEMedian"] = market_pe_median
        results[code]["MarketPBMedian"] = market_pb_median
        
        # Merge advanced metrics
        adv = advanced_metrics_map.get(code, {})
        for k, v in adv.items():
            results[code][k] = v
            
    try:
        with open(div_cache_file, "w", encoding="utf-8") as f:
            json.dump(div_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to save {div_cache_file}: {e}")

    # 2. Yahoo Data & Advanced Pricing
    print("Fetching market index...")
    market_data = fetch_yahoo_data("^TWII", "")
    market_trend = "未知"
    m_rsi = 50.0
    m_bias = 0.0
    if market_data and market_data["history"]:
        m_closes = market_data["history"]
        m_ma20 = statistics.mean(m_closes[-20:]) if len(m_closes) >= 20 else statistics.mean(m_closes)
        m_ma60 = statistics.mean(m_closes[-60:]) if len(m_closes) >= 60 else statistics.mean(m_closes)
        market_trend = "多頭" if m_ma20 > m_ma60 else "空頭"
        
        rsi_series = calculate_rsi(m_closes)
        if len(rsi_series) > 0:
            m_rsi = float(rsi_series[-1])
            
        if m_ma60 > 0 and market_data["price"]:
            m_bias = ((market_data["price"] - m_ma60) / m_ma60) * 100
            
    market_summary = {
        "TWII_price": market_data["price"] if market_data else None,
        "TWII_ma20": m_ma20 if market_data else None,
        "TWII_ma60": m_ma60 if market_data else None,
        "TWII_trend": market_trend,
        "TWII_rsi": round(m_rsi, 2),
        "TWII_bias": round(m_bias, 2),
        "market_pe_median": market_pe_median,
        "market_pb_median": market_pb_median,
        "update_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        with open("data/market_summary.json", "w", encoding="utf-8") as f:
            json.dump(market_summary, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to write market_summary.json: {e}")

    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    success_count = 0
    lock = threading.Lock()

    def process_stock(code):
        nonlocal success_count
        yahoo = fetch_yahoo_data(code, ".TW") or fetch_yahoo_data(code, ".TWO")
        if not yahoo or yahoo['price'] is None:
            print(f"Warning: Cannot fetch price for {code}, skipping.")
            return

        with lock:
            success_count += 1
        
        price = yahoo["price"]
        is_etf = (yahoo.get("type") == "ETF")
        
        # Calculate Indicators
        inds = calculate_indicators(yahoo)
        stock_trend = "多頭排列" if inds["ma20"] > inds["ma60"] else "空/盤整"
        
        # Momentum fallback：用近 3 個月股價漲幅作為替代動能指標
        momentum = results[code].get("Momentum", "未知")
        if momentum == "未知":
            closes = yahoo.get("history", [])
            price_3m_chg = None
            if len(closes) >= 60:
                price_3m_ago = closes[-60]
                if price_3m_ago > 0:
                    price_3m_chg = round((price - price_3m_ago) / price_3m_ago * 100, 2)
            momentum = get_momentum(stock_trend=stock_trend, price_3m_chg=price_3m_chg)
            results[code]["Momentum"] = momentum
            
        current_yield = results[code].get("Yield")
        if not current_yield or current_yield == 0:
            try:
                t = yf.Ticker(f"{code}.TW")
                info = t.info
                # dividendYield is already in percentage format (e.g., 5.55)
                dy = info.get("dividendYield")
                if dy is None:
                    # 'yield' is usually in decimal (e.g., 0.0555)
                    raw_yield = info.get("yield")
                    if raw_yield:
                        dy = raw_yield * 100
                if dy:
                    current_yield = round(float(dy), 2)
                    results[code]["Yield"] = current_yield
            except Exception:
                pass
        
        # Institutional Buy Ratio
        foreign_buy = inst_data.get(code, {}).get("ForeignBuy", 0)
        trust_buy = inst_data.get(code, {}).get("TrustBuy", 0)
        current_vol_shares = inds.get("current_vol", 0)
        current_vol_lots = current_vol_shares / 1000 if current_vol_shares > 0 else 1
        inst_buy_ratio = (foreign_buy + trust_buy) / current_vol_lots if current_vol_lots > 0 else 0
        
        # Assign Market Trend based on Exchange
        exchange = results[code].get("Exchange", "TWSE")
        stock_market_trend = market_trend
        
        # Use target price if available
        t_price_input = target_prices_input.get(code) if target_prices_input else None
        
        if isinstance(t_price_input, dict):
            t_price = t_price_input.get("平均") or list(t_price_input.values())[0]
            results[code]["TargetPriceDetails"] = t_price_input
        else:
            t_price = t_price_input
            results[code]["TargetPriceDetails"] = {"系統共識": t_price} if t_price else None

        results[code]["TargetPrice"] = t_price
        
        buy_price, sell_price, stop_loss_price, stock_trend = get_suggested_prices(
            price, inds, momentum, stock_market_trend, is_etf, current_yield, target_price=t_price
        )
            
        if not results[code].get("Name"):
             results[code]["Name"] = yahoo["name"]
             results[code]["NameSource"] = "Yahoo"

        results[code].update({
            "Price": round(price, 2),
            "SuggestedBuy": buy_price,
            "SuggestedSell": sell_price,
            "SuggestedStopLoss": stop_loss_price,
            "Type": yahoo.get("type"),
            "MA5": round(float(inds.get("ma5", inds["ma20"])), 2),
            "MA20": round(inds["ma20"], 2),
            "MA60": round(inds["ma60"], 2),
            "MarketTrend": stock_market_trend,
            "StockTrend": stock_trend,
            "InstBuyRatio": round(inst_buy_ratio, 4),
            "RSI": round(inds["rsi"], 2),
            "ATR": round(inds["atr"], 2),
            "TargetPrice": t_price,
            "TechnicalFlags": inds.get("technical_flags", []),
            "KD_K": round(float(inds.get("kd_k", 50)), 2),
            "KD_D": round(float(inds.get("kd_d", 50)), 2),
            "RSIDivergence": inds.get("rsi_divergence", "None"),
            "is_new_stock": inds.get("is_new_stock", False),
            "ForeignBuy": inst_data.get(code, {}).get("ForeignBuy", 0),
            "TrustBuy": inst_data.get(code, {}).get("TrustBuy", 0)
        })

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_stock, code) for code in target_codes]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Error processing stock: {e}")

    if (success_count / len(target_codes)) < 0.7:
        raise RuntimeError("Integrity check failed.")

    with open(LATEST_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    return results

def validate_consensus_targets(targets, consensus_targets):
    target_codes = set(t["code"] for t in targets if not t["code"].startswith("00")) # Exclude ETFs
    consensus_codes = set(consensus_targets.keys())
    
    missing_codes = target_codes - consensus_codes
    if missing_codes:
        raise RuntimeError(f"Validation Error: 缺少以下股票的法人目標價資料: {missing_codes}")
        
    forbidden_terms = ["樂觀", "保守", "最高", "最低", "高點", "低點", "共識", "估值", "技術目標"]
    for code in target_codes:
        targets_info = consensus_targets.get(code, {})
        for inst_name in targets_info.keys():
            if inst_name == "平均": continue
            for term in forbidden_terms:
                if term in inst_name:
                    raise RuntimeError(f"Validation Error: 股票 {code} 的法人名稱使用違規模糊字眼 '{term}' in '{inst_name}'")

if __name__ == "__main__":
    # According to the Taicai Skill Mandate (Section 0.1): 
    # Mandatory search for latest institutional targets before every update.
    print("🔍 [Mandatory] Searching for latest institutional target prices...")
    # (Note: In actual execution, the Agent uses its search tool to populate consensus_targets.json)
    
    # Load institutional consensus target prices from external file
    try:
        with open("data/consensus_targets.json", "r", encoding="utf-8") as f:
            consensus_targets = json.load(f)
    except Exception as e:
        print(f"Warning: Could not load consensus_targets.json, using empty defaults. Error: {e}")
        consensus_targets = {}

    targets = get_targets()
    try:
        validate_consensus_targets(targets, consensus_targets)
    except RuntimeError as e:
        print(f"❌ 嚴重錯誤: {e}")
        print("💡 提示: 請先執行網路搜尋找尋上述標的的最新外資與法人報告，並更新至 consensus_targets.json 後再執行更新！")
        exit(1)

    try: 
        run_update(target_prices_input=consensus_targets)
    except Exception as e: 
        import traceback; traceback.print_exc()
