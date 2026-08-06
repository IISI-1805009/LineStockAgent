import json
import os
import sys

# Ensure ai_agent can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core import ai_agent

def main():
    file_path = "data/market_summary.json"
    cache_file = "data/market_trend_cache.json"

    if not os.path.exists(file_path):
        print("No market_summary.json found. Skipping.")
        sys.exit(1)
        
    with open(file_path, "r", encoding="utf-8") as f:
        market_data = json.load(f)

    current_update_date = market_data.get("update_date", "unknown")

    print(f"Generating AI market trend report for data at {current_update_date}...")
    report_html = ai_agent.generate_market_trend_report(market_data)

    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"update_date": current_update_date, "html": report_html}, f, ensure_ascii=False, indent=2)
        print("Market trend cache updated successfully.")
    except Exception as e:
        print(f"Failed to write cache: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
