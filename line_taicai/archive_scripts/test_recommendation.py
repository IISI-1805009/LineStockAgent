import sys
sys.path.append("/Users/hank/Project/LineStockAgent/line_taicai")
from recommendation_engine import decide_recommendation

def test_engine():
    indicators = {
        "ma5": 105, "ma20": 100, "ma60": 95,
        "rsi": 50, "kd_k": 50, "kd_d": 50,
        "technical_flags": ["VCP"],
        "is_new_stock": False
    }
    adv_metrics = {
        'pe_5y_lowest_20': True,
        'pb_5y_lowest_20': True,
        'ar_days_improved': True,
        'inv_days_improved': True,
        'gross_margin_yoy': True,
        'operating_margin_yoy': True,
        'pre_tax_yoy': True,
        'net_income_yoy': True,
        'fcf_3_of_5_positive': True,
        'fcf_5y_avg_positive': True,
        'ocf_ni_3_of_5_over_100': True,
        'ocf_ni_5y_avg_over_100': True,
        'div_payout_3_of_5_over_50': True,
        'div_payout_5y_avg_over_50': True,
        'turnaround': True
    }
    
    st_rec, st_reason, lt_rec, lt_reason = decide_recommendation(
        price=102, buy_point=100, sell_point=110, momentum="🚀 強勁",
        indicators=indicators, inst_type="EQUITY", target_price=120,
        consec_3m=True, consecutive_dividend_years=5, avg_yield_5y=6.0,
        adv_metrics=adv_metrics
    )
    print("ST Rec:", st_rec)
    print("ST Reason:", st_reason)
    print("LT Rec:", lt_rec)
    print("LT Reason:", lt_reason)

if __name__ == "__main__":
    test_engine()
