# recommendation_engine.py
# 雙軌評分系統 (短線與長線獨立評估)

def _get_score_label(score, is_sell=False, sell_reason_type="profit"):
    if is_sell:
        if score >= 6:
            if sell_reason_type == "profit":
                return "🟢 大賣了結"
            else:
                return "🟢 大賣停損" # 理由中會說明是停損
        elif score >= 4:
            return "🟢 中賣減碼"
        elif score >= 1:
            return "🟢 小賣調節"
        else:
            return "⚪ 觀望"
    else:
        if score >= 8:
            return "🔴 大買佈局"
        elif score >= 5:
            return "🔴 中買佈局"
        elif score >= 3:
            return "🔴 小買試單"
        elif score >= 1:
            return "⚪ 觀望"
        else:
            return "👀 觀望"

def _calculate_short_term(price, indicators, momentum, inst_type, foreign_buy, trust_buy, f_consec, t_consec, market_trend, inst_buy_ratio, adv_metrics):
    """
    短線波段評分模型 (最高 10 分)
    """
    if inst_type == "ETF":
        return "不適用", "ETF 商品通常波動較小，短線波段不適用，請參考長線存股建議。"

    score = 0
    sell_score = 0
    flags = indicators.get("technical_flags", [])
    special_tags = []
    
    rsi = indicators.get("rsi", 50)
    kd_k = indicators.get("kd_k", 50)
    kd_d = indicators.get("kd_d", 50)
    
    # --- 扣板機 (賣出訊號) ---
    is_kd_death = kd_k >= 80 and kd_d >= 80 and kd_k <= kd_d
    sell_reason_type = "profit"
    if rsi > 80:
        sell_score += 3
        special_tags.append("RSI極度超買")
    if is_kd_death:
        sell_score += 2
        special_tags.append("KD高檔死叉")
    if "ShootingStar" in flags:
        sell_score += 3
        special_tags.append("爆量長上影線")
        
    if sell_score >= 4:
        label = _get_score_label(sell_score, is_sell=True, sell_reason_type="profit")
        reason = f"🏃‍♂️ [波段過熱] 短線 {', '.join(special_tags)}，回檔風險高，建議先行獲利了結或減碼。 ({int(sell_score)}/10)"
        return label, reason

    # --- 買進計分 ---
    # A. 技術與型態面 (最高 4 分)
    tech_score = 0
    if "BottomGoldenCross" in flags or "MACDGolden" in flags or "HammerBottom" in flags or (kd_k <= 25 and kd_d <= 25 and kd_k >= kd_d):
        tech_score += 2
        special_tags.append("底部反轉")
    if "VCP" in flags or "Breakout" in flags:
        tech_score += 2
        special_tags.append("型態突破")
    score += min(4, tech_score)
    
    # B. 資金籌碼動能 (最高 3 分)
    chip_score = 0
    is_highly_concentrated = (f_consec >= 2 or t_consec >= 2) and (inst_buy_ratio > 0.1)
    if is_highly_concentrated:
        chip_score += 2
        special_tags.append("籌碼高度集中")
        
    is_secret = (indicators.get("current_vol", 0) < indicators.get("vol_ma5", 0) * 0.6) and (price < indicators.get("ma20", price)) and (f_consec >= 2 or t_consec >= 2)
    if is_secret:
        chip_score += 1
        special_tags.append("偷偷吃貨")
    elif "VolumeSurge" in flags or "VolWarming" in flags:
        chip_score += 1
        
    score += min(3, chip_score)
    
    # B-2. 轉機與營收短線動能加分 (最高 2 分)
    momentum_score = 0
    if adv_metrics.get("turnaround", False) or adv_metrics.get("gross_margin_yoy", False) or adv_metrics.get("operating_margin_yoy", False):
        momentum_score += 1
        special_tags.append("轉機動能")
    if adv_metrics.get("net_income_yoy", False):
        momentum_score += 1
    score += min(2, momentum_score)
    
    # C. 短期趨勢 (最高 3 分)
    trend_score = 0
    ma5 = indicators.get("ma5", price)
    ma20 = indicators.get("ma20", price)
    if price > ma5:
        trend_score += 1
    if price > ma20:
        trend_score += 1
    if market_trend == "多頭":
        trend_score += 1
    score += min(3, trend_score)
    
    # D. 空頭瀑布防禦機制 (防接刀)
    ma60 = indicators.get("ma60", price)
    is_severe_downtrend = (price < ma20) and (price < ma60)
    if is_severe_downtrend:
        score -= 2
        special_tags.append("趨勢嚴重偏空")
        
    tag_str = f" ({', '.join(special_tags)})" if special_tags else ""
    
    if score >= 5:
        label = _get_score_label(score)
        reason = f"🏃‍♂️ [動能轉強] 短線型態與籌碼共振{tag_str}，具備波段發動條件。 ({int(score)}/10)"
        return label, reason
    elif score >= 3:
        label = _get_score_label(score)
        reason = f"🏃‍♂️ [潛伏試單] 底部型態浮現或法人初步進駐，可小量波段試單。 ({int(score)}/10)"
        return label, reason
    else:
        if price > ma20:
            return "💎 續抱待漲", f"🏃‍♂️ [趨勢延續] 短線無明顯發動訊號，但月線趨勢向上，已持有者續抱。 ({int(score)}/10)"
        return "👀 觀望", f"🏃‍♂️ [動能不足] 短線無明顯型態或籌碼發動訊號，建議觀望。 ({int(score)}/10)"

def _calculate_long_term(price, indicators, momentum, inst_type, market_trend, stock_trend, current_yield, target_price, revenue_yoy, consecutive_dividend_years, consec_3m, turnaround, avg_yield_5y, pe, pb, market_pe_median, market_pb_median, adv_metrics, stock_code=None):
    """
    長線存股評分模型 (最高 10 分)
    """
    score = 0
    sell_score = 0
    special_tags = []
    
    is_financial = stock_code and stock_code.startswith("28")
    
    ma20 = indicators.get("ma20", price)
    ma60 = indicators.get("ma60", price)
    rsi = indicators.get("rsi", 50)
    
    # 判斷是否為超級護城河 (三率三升 + 連續三個月營收成長)
    is_super_growth = consec_3m and adv_metrics.get('gross_margin_yoy') and adv_metrics.get('operating_margin_yoy') and adv_metrics.get('net_income_yoy')
    
    # 定存股判定 (連五年發放股息 + 殖利率 > 5 + 配息發放率穩定)
    is_super_dividend = (consecutive_dividend_years >= 5) and (avg_yield_5y > 5.0) and adv_metrics.get('div_payout_3_of_5_over_50', True)
    
    # 一般成長股判斷
    is_growth_stock = False
    has_strong_revenue = revenue_yoy and revenue_yoy >= 15.0
    has_high_upside = target_price and price and target_price > price * 1.20
    
    if is_super_growth or has_strong_revenue:
        is_growth_stock = True
    elif has_high_upside:
        is_growth_stock = True
        
    if is_super_growth:
        special_tags.append("超級成長股")
    elif is_growth_stock:
        special_tags.append("成長股")
        
    is_strong_dividend_stock = consecutive_dividend_years >= 5 and (avg_yield_5y >= 4.0 or current_yield >= 4.0)
    if is_super_dividend:
        special_tags.append("超級定存股")
    elif is_strong_dividend_stock:
        special_tags.append("優質定存股")
        
    # 現金流審查機制
    fcf_ok = adv_metrics.get('fcf_3_of_5_positive', True)
    ocf_ok = adv_metrics.get('ocf_ni_3_of_5_over_100', True)
    
    # 判斷是否為真地雷還是擴張期 (金融股與ETF豁免現金流審查)
    is_expanding = (revenue_yoy and revenue_yoy > 15.0) or is_super_growth
    is_declining = (revenue_yoy and revenue_yoy < 0)
    
    if inst_type != "ETF" and not is_financial and (not fcf_ok or not ocf_ok):
        if is_declining:
            special_tags.append("營運衰退且現金流惡化")
            sell_score += 4
            is_growth_stock = False
            is_super_growth = False
            is_strong_dividend_stock = False
            is_super_dividend = False
        elif is_expanding:
            special_tags.append("高成長極度燒錢")
        else:
            special_tags.append("獲利含金量偏低")
            sell_score += 2
        
    # --- 扣板機 (賣出訊號) ---
    is_trend_broken = price < ma60
    is_yield_lost = current_yield and current_yield < 3.0
    is_new_stock = indicators.get("is_new_stock", False)
    
    if is_new_stock:
        if is_trend_broken:
            sell_score += 4
            special_tags.append("新股破線避險")
            is_growth_stock = False
            is_super_growth = False
        else:
            special_tags.append("新股")
            
    elif is_trend_broken:
        if not is_growth_stock and not is_strong_dividend_stock:
            sell_score += 4
            special_tags.append("跌破長期支撐")
            
    if is_yield_lost and inst_type != "ETF":
        if not is_growth_stock:
            if revenue_yoy is not None and revenue_yoy < 0:
                if is_trend_broken:
                    sell_score += 4
                    special_tags.append("護城河破敗且破線")
                else:
                    sell_score += 2
                    special_tags.append("護城河衰退")
            else:
                if is_strong_dividend_stock:
                    if is_trend_broken:
                        sell_score += 3
                        special_tags.append("定存股配息中斷且破線")
                    else:
                        special_tags.append("殖利率偏低(價高)")
                else:
                    if is_trend_broken:
                        sell_score += 3
                        special_tags.append("缺乏殖利率保護")
        
    if sell_score >= 4:
        label = _get_score_label(sell_score, is_sell=True, sell_reason_type="loss")
        reason = f"🧘‍♂️ [破線停損] 結構性空頭或護城河破敗 ({', '.join(special_tags)})，建議長線出場或大幅減碼保本。 ({int(sell_score)}/10)"
        return label, reason

    # --- 買進計分 ---
    # A. 護城河 (價值或成長) (最高 4 分)
    val_score = 0
    if is_super_growth:
        val_score += 4
    else:
        if is_growth_stock:
            if revenue_yoy:
                if revenue_yoy >= 30.0:
                    val_score += 3
                elif revenue_yoy >= 15.0:
                    val_score += 2
            if target_price and price and target_price > price * 1.20:
                val_score += 1
        else:
            if current_yield:
                if current_yield >= 6.0:
                    val_score += 4 if is_super_dividend else 3
                elif current_yield >= 5.0:
                    val_score += 3
                elif current_yield >= 4.0:
                    val_score += 2
                elif current_yield > 0:
                    val_score += 1
            if revenue_yoy and revenue_yoy > 0:
                val_score += 1
            
    score += min(4, val_score)
    
    # B. 長線位階與撿便宜 (最高 4 分)
    trend_score = 0
    dip_tags = []
    
    is_super_cheap = adv_metrics.get('pe_5y_lowest_20') or adv_metrics.get('pb_5y_lowest_20') or (pe and pb and pe < market_pe_median and pb < market_pb_median)
    if is_super_cheap:
        if current_yield and current_yield >= 5.0:
            trend_score += 3
            dip_tags.append("極度便宜且具高殖利率")
        else:
            trend_score += 2
            dip_tags.append("極度便宜估值")
        
    if turnaround and price < ma60:
        trend_score += 2
        dip_tags.append("轉機底部浮現")
        
    if adv_metrics.get('inv_days_improved') and adv_metrics.get('ar_days_improved'):
        trend_score += 1
        dip_tags.append("營運體質改善")
        
    if is_growth_stock or (val_score >= 2) or is_strong_dividend_stock:
        if price < ma60 * 0.90:
            trend_score += 2
            dip_tags.append("乖離過大")
        elif price < ma60 * 0.95:
            trend_score += 1
            dip_tags.append("價值浮現")
            
        if rsi < 25:
            trend_score += 2
            dip_tags.append("極度恐慌")
        elif rsi < 35 and price < ma60:
            trend_score += 1
            dip_tags.append("嚴重超賣")
            
    score += min(4, trend_score)
    
    # C. 穩定籌碼面與大盤 (最高 2 分)
    if market_trend != "空頭":
        score += 1
    # 原本直接給籌碼1分，我們改由大盤與籌碼合併2分，這裡簡單給定基本分
    score += 1 
    
    if dip_tags:
        special_tags.extend(dip_tags)
        
    if score >= 5:
        label = _get_score_label(score)
        if dip_tags:
            reason = f"🧘‍♂️ [價值錯殺] {', '.join(dip_tags)}，基本面強勁的優質股迎來長線買點！ ({int(score)}/10)"
        else:
            reason = f"🧘‍♂️ [價值浮現] 具備長線護城河 (殖利率 {current_yield}%)，處於安全邊際之上，適合建倉存股。 ({int(score)}/10)"
        return label, reason
    elif score >= 3:
        label = _get_score_label(score)
        if dip_tags:
            reason = f"🧘‍♂️ [逢低佈局] {', '.join(dip_tags)}，可開始於下跌段分批撿便宜小量存股。 ({int(score)}/10)"
        else:
            reason = f"🧘‍♂️ [分批佈局] 價值面尚可，可於長期均線附近分批佈局小量存股。 ({int(score)}/10)"
        return label, reason
    else:
        if price > ma60:
            return "💎 續抱待漲", f"🧘‍♂️ [穩健續抱] 具備長期均線保護 (殖利率 {current_yield}%)，長線投資者請忽略短線震盪，續抱即可。 ({int(score)}/10)"
        return "👀 觀望", f"🧘‍♂️ [估值偏高] 目前長線安全邊際不足或缺乏護城河，建議等待大幅回檔再行評估。 ({int(score)}/10)"

def decide_recommendation(price, buy_point, sell_point, momentum, indicators, inst_type="EQUITY", target_price=None, target_details=None, foreign_buy=0, trust_buy=0, f_consec=0, t_consec=0, market_trend="未知", stock_trend="未知", inst_buy_ratio=0.0, current_yield=0.0, revenue_yoy=0.0, consecutive_dividend_years=0, consec_3m=False, turnaround=False, avg_yield_5y=0.0, pe=None, pb=None, market_pe_median=15.0, market_pb_median=1.5, adv_metrics=None, stock_code=None):
    """
    綜合評估長短線，回傳 (short_term_rec, short_term_reason, long_term_rec, long_term_reason)
    """
    if adv_metrics is None:
        adv_metrics = {}
        
    if price is None:
        return "👀 觀望", "無報價資料", "👀 觀望", "無報價資料"
        
    # 短線評估
    st_rec, st_reason = _calculate_short_term(
        price, indicators, momentum, inst_type, foreign_buy, trust_buy, f_consec, t_consec, market_trend, inst_buy_ratio, adv_metrics
    )
    
    # 長線評估
    lt_rec, lt_reason = _calculate_long_term(
        price, indicators, momentum, inst_type, market_trend, stock_trend, current_yield, target_price, revenue_yoy, consecutive_dividend_years, consec_3m, turnaround, avg_yield_5y, pe, pb, market_pe_median, market_pb_median, adv_metrics, stock_code
    )
    
    return st_rec, st_reason, lt_rec, lt_reason
