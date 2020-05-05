import yfinance as yf

msft = yf.Ticker("MSFT")

# get stock info
print(msft.info)
