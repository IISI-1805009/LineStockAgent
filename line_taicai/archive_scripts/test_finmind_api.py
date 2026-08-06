import requests
import json

url_base = "https://api.finmindtrade.com/api/v4/data"

def test_api(dataset, data_id, start_date):
    print(f"Testing {dataset}...")
    r = requests.get(
        url_base,
        params={'dataset': dataset, 'data_id': data_id, 'start_date': start_date},
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    if r.status_code == 200:
        data = r.json().get('data', [])
        print(f"Count: {len(data)}")
        if data:
            print(f"Sample: {json.dumps(data[-1], ensure_ascii=False, indent=2)}")
    else:
        print(f"Error {r.status_code}: {r.text}")

if __name__ == "__main__":
    test_api("TaiwanStockFinancialStatements", "2330", "2023-01-01")
    test_api("TaiwanStockPER", "2330", "2024-06-01") # test recent PE
    test_api("TaiwanStockHoldingSharesPer", "2330", "2024-06-01")
    test_api("TaiwanStockDividend", "2330", "2018-01-01")
