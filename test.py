from yahooquery import Ticker

def test_yahoo_finance_api(ticker):
    stock = Ticker(ticker)
    
    # 기본 주식 정보 가져오기
    company_info = stock.quote_type.get(ticker, {})
    price_data = stock.price.get(ticker, {})

    # 테스트 출력
    print("📌 Yahoo Finance API Test Results:")
    print("✅ Ticker:", ticker)
    print("🏢 Company Name:", company_info.get("longName", "N/A"))
    print("💰 Current Price:", price_data.get("regularMarketPrice", "N/A"))
    print("📉 Previous Close:", price_data.get("regularMarketPreviousClose", "N/A"))

# 테스트 실행 (애플 주가 조회)
test_yahoo_finance_api("AAPL")
