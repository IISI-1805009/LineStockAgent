import requests
import json
from collections import defaultdict

url_base = "https://api.finmindtrade.com/api/v4/data"

def test_api(dataset, data_id, start_date):
    r = requests.get(
        url_base,
        params={'dataset': dataset, 'data_id': data_id, 'start_date': start_date},
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    data = r.json().get('data', [])
    dates = defaultdict(list)
    for d in data:
        dates[d['date']].append(f"{d['type']} ({d['origin_name']})")
    
    # Just print types for the most recent date
    if dates:
        recent_date = sorted(dates.keys())[-1]
        print(f"Date: {recent_date}")
        for t in dates[recent_date]:
            print(t)
    else:
        print("No data or error:", r.status_code, r.text)

if __name__ == "__main__":
    print("=== Balance Sheet ===")
    test_api('TaiwanStockBalanceSheet', '2330', '2025-01-01')
    print("=== Cash Flow ===")
    test_api('TaiwanStockCashFlowsStatement', '2330', '2025-01-01')
