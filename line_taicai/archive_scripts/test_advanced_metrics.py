import sys
sys.path.append("/Users/hank/Project/LineStockAgent/line_taicai")
import json
from taicai_manager import process_advanced_metrics

def test_single():
    metrics = process_advanced_metrics('2330')
    print(json.dumps(metrics, indent=2))

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()
    test_single()
