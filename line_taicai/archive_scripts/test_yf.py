import yfinance as yf
tkr = yf.Ticker("2330.TW")
print("fiveYearAvgDividendYield" in tkr.info)
print(tkr.info.get("fiveYearAvgDividendYield"))
