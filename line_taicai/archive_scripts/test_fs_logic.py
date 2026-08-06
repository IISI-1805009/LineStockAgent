import requests
import json
import time
from datetime import datetime, timedelta

url_base = "https://api.finmindtrade.com/api/v4/data"

def fetch_finmind_dataset(dataset, code, start_date):
    for i in range(3):
        try:
            r = requests.get(
                url_base,
                params={'dataset': dataset, 'data_id': code, 'start_date': start_date},
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=10,
                verify=False
            )
            if r.status_code == 200:
                return r.json().get('data', [])
        except Exception as e:
            time.sleep(1 * (i + 1))
    return []

def process_financials(code):
    start_date = (datetime.now() - timedelta(days=365*6)).strftime('%Y-%m-%d')
    print(f"Fetching {code} financials from {start_date}...")
    
    # 1. Income Statement
    is_data = fetch_finmind_dataset('TaiwanStockFinancialStatements', code, start_date)
    time.sleep(0.2)
    # 2. Balance Sheet
    bs_data = fetch_finmind_dataset('TaiwanStockBalanceSheet', code, start_date)
    time.sleep(0.2)
    # 3. Cash Flow
    cf_data = fetch_finmind_dataset('TaiwanStockCashFlowsStatement', code, start_date)
    time.sleep(0.2)
    
    if not is_data or not bs_data or not cf_data:
        return None
        
    metrics = {}
    
    # Process IS
    is_by_date = {}
    for d in is_data:
        date = d['date']
        if date not in is_by_date: is_by_date[date] = {}
        is_by_date[date][d['type']] = d['value']
        
    # Process BS
    bs_by_date = {}
    for d in bs_data:
        date = d['date']
        if date not in bs_by_date: bs_by_date[date] = {}
        bs_by_date[date][d['type']] = d['value']
        
    # Process CF
    cf_by_date = {}
    for d in cf_data:
        date = d['date']
        if date not in cf_by_date: cf_by_date[date] = {}
        cf_by_date[date][d['type']] = d['value']
        
    sorted_dates = sorted(list(set(is_by_date.keys()) & set(bs_by_date.keys()) & set(cf_by_date.keys())))
    if not sorted_dates: return None
    
    # Extract latest quarter vs last year same quarter
    latest_date = sorted_dates[-1]
    prev_year_date = str(int(latest_date[:4])-1) + latest_date[4:]
    if prev_year_date not in sorted_dates:
        # Fallback to 4 quarters ago if exact date match fails
        if len(sorted_dates) >= 5:
            prev_year_date = sorted_dates[-5]
            
    latest_is = is_by_date[latest_date]
    latest_bs = bs_by_date[latest_date]
    
    prev_is = is_by_date.get(prev_year_date, {})
    prev_bs = bs_by_date.get(prev_year_date, {})
    
    def calc_turnover(is_dict, bs_dict):
        rev = is_dict.get('Revenue', 0)
        cogs = is_dict.get('CostOfGoodsSold', 0)
        ar = bs_dict.get('AccountsReceivableNet', 0)
        inv = bs_dict.get('Inventories', 0)
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
    
    # Calculate FCF and OCF for the last 5 years
    # Data is quarterly. We need annual or last 20 quarters.
    # Group by year
    years_data = {}
    for d in sorted_dates:
        year = d[:4]
        if year not in years_data: years_data[year] = {'ocf': 0, 'icf': 0, 'net_income': 0}
        years_data[year]['ocf'] += cf_by_date[d].get('CashFlowsFromOperatingActivities', cf_by_date[d].get('NetCashInflowFromOperatingActivities', 0))
        years_data[year]['icf'] += cf_by_date[d].get('CashProvidedByInvestingActivities', 0)
        years_data[year]['net_income'] += is_by_date[d].get('IncomeAfterTaxes', 0)
        
    recent_years = sorted(years_data.keys())[-6:-1] # get last 5 full/available years (exclude current incomplete year maybe? or just take last 5 years present)
    recent_years = sorted(years_data.keys())[-5:]
    
    fcf_positive_count = 0
    fcf_total = 0
    ocf_to_ni_over_100_count = 0
    ocf_to_ni_total = []
    
    for y in recent_years:
        ocf = years_data[y]['ocf']
        fcf = ocf + years_data[y]['icf'] # ICF is usually negative
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
    
    # ROE > 15%, OPM > 10%
    roe_high = True
    opm_high = True
    for y in recent_years:
        ni = years_data[y]['net_income']
        # Need equity for ROE, just get last quarter of the year equity
        # For simplicity in this test, let's just do OPM > 10%
        # OPM = OperatingIncome / Revenue
        pass
        
    return metrics

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()
    print(json.dumps(process_financials('2330'), indent=2))
