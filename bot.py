import discord
import os
import requests
import asyncio
from dotenv import load_dotenv
import random
import sqlite3
from yahooquery import Ticker
from textblob import TextBlob
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator
import plotly.graph_objects as go
import logging
import time
import redis
import json
import schedule
import warnings
import pytz
from datetime import datetime
from discord.ext import commands

ADMIN_ID = "537099554986917889"

last_user_count = None  # cached user count
last_user_count_time = 0  # last updated timestamp (seconds)

# 🔹 Bot intents (required to read guild member info)
intents = discord.Intents.default()
intents.message_content = True # allow message content access
intents.members = True  # allow server member access
intents.guilds = True   # allow guild list access

# ✅ Create bot instance with `commands.Bot`
bot = commands.Bot(command_prefix="!", intents=intents)

HELP_MESSAGE = """
📚 **Stock Bot Help Menu**
📌 *This bot provides stock market insights, portfolio tracking, and financial news alerts.*

---

🔍 **Stock Information**
- `!price <TICKER>` – Get the current stock price and % change. Example: `!price AAPL`
- `!chart <TICKER> <PERIOD>` – Generate a stock price chart with indicators (SMA, EMA, RSI). Example: `!chart TSLA 1y`
  - Supported periods: `1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`, `10y`, `max`
- `!trend <TICKER>` – View the % change over the last 7 days. Example: `!trend NVDA`
- `!sentiment <TICKER>` – Analyze sentiment of the latest news related to the stock. Example: `!sentiment MSFT`

---

💰 **Portfolio Management**
- `!buy <TICKER> <QUANTITY>` – Buy shares of a stock. Example: `!buy AMZN 5`
- `!sell <TICKER> <QUANTITY>` – Sell shares. Example: `!sell AAPL 2`
- `!sellall` – Sell all holdings.
- `!balance` – Check your available cash balance.
- `!portfolio` – View your current stock holdings.
- `!pnl` – Get a profit/loss report for your investments.
- `!reset` – Reset your entire portfolio to its initial state.

---

📈 **Alerts and Watchlist**
- `!alert <TICKER> <PRICE>` – Set a price alert. Example: `!alert TSLA 200`
- `!alert list` – View active price alerts.
- `!alert remove <TICKER>` – Remove a specific alert. Example: `!alert remove TSLA`
- `!watchlist <TICKER>` – Add a stock to your watchlist. Example: `!watchlist GOOG`
- `!watchlist list` – View your watchlist.
- `!watchlist remove <TICKER>` – Remove a stock from watchlist. Example: `!watchlist remove GOOG`
- `!watchlist clear` – Clear your entire watchlist.

---

📰 **Financial News & Recommendations**
- `!news` – Get the latest financial headlines (Updated daily at 08:00 AM ET).
- `!recommend` – Get stock recommendations based on recent trends & sentiment.

---

📊 **Portfolio Analysis**
- `!portfolio_analysis` – Get a detailed analysis with performance charts.
- `!download_portfolio` – Download your portfolio as a CSV file.

---

🔔 **Smart Notifications**
- **🚨 Automated Alerts:**  
  - Stocks reaching your target price  
  - Daily market news at **08:00 AM ET**  

---

ℹ️ **Notes:**
- **Valid Ticker Symbols Only!** If you enter an incorrect ticker (e.g., `A1323`), the bot will warn you.
- **Example Usage:**  
  - ✅ `!price AAPL` – ✅ `!chart MSFT 1y`  
  - ❌ `!price XYZ123` → *Invalid ticker warning!*  
- Replace `<TICKER>` with a stock ticker (e.g., `AAPL` for Apple).  
- Replace `<QUANTITY>` with the number of shares you want to buy/sell.  

---

📢 **User Feedback Survey**
💡 Help us improve! Share your feedback: [Feedback Form](https://forms.gle/hFyj91rcYAxAkk9M6)

---

💬 **Need further assistance? Contact the bot admin!**  
🚀 *Stay ahead of the market with StockSage!*  
"""

# U.S. Eastern Time (New York)
NY_TZ = pytz.timezone("America/New_York")

warnings.simplefilter(action='ignore', category=FutureWarning)

CACHE_EXPIRY = 300  # 5 minutes (seconds)
MIN_FETCH_INTERVAL = 30  # minimum refetch interval per ticker (seconds)

# Configure logging and create logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

try:
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    r.ping()  # connectivity check
except redis.ConnectionError:
    logger.warning("Redis connection failed. Falling back to in-memory caching.")
    r = None  # use in-memory caching if Redis is unavailable

# cache store (in-memory fallback)
price_cache = {}
last_fetch_time = {}  # last network fetch time per ticker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Initialize portfolio database
with sqlite3.connect("portfolio.db") as conn:
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        user_id TEXT,
        ticker TEXT,
        quantity INTEGER,
        price REAL,
        trade_type TEXT,  -- 'buy' or 'sell'
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        balance REAL DEFAULT 10000.00  -- default starting balance $10,000
    )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            user_id TEXT,
            ticker TEXT,
            PRIMARY KEY (user_id, ticker)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            user_id TEXT,
            ticker TEXT,
            target_price REAL,
            PRIMARY KEY (user_id, ticker)
        )
    """)
    conn.commit()

# Initialize bot stats database
with sqlite3.connect("bot_stats.db") as conn:
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        servers INTEGER,
        users INTEGER,
        event_type TEXT,
        guild_id INTEGER,
        guild_name TEXT
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS unique_users (
        user_id TEXT PRIMARY KEY
    );
    """)
    conn.commit()

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

def validate_env_variables():
    required_vars = ["DISCORD_TOKEN", "NEWS_API_KEY"]  # include News API key as required

    missing = [var for var in required_vars if os.getenv(var) is None]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

# ✅ Stock price lookup
# Fetch company name directly from Yahoo Finance
def get_stock_price(ticker):
    try:
        stock = Ticker(ticker, max_retries=1, retry_pause=0.25, timeout=5)
        data = stock.quote_type.get(ticker, {})
        price_data = get_price_data(ticker, stock)
    except Exception as e:
        logger.warning(f"Price fetch failed for {ticker}: {e}")
        return "⚠️ Unable to fetch stock data right now (rate limit or network issue). Please try again in a minute."

    if price_data is None:
        return f"⚠️ Unable to fetch stock data for {ticker}. Please check the ticker symbol."

    company_name = data.get("longName", ticker)  # get company name
    current_price = price_data.get("regularMarketPrice", "N/A")
    previous_close = price_data.get("regularMarketPreviousClose", "N/A")

    # calculate absolute and percentage change
    if isinstance(current_price, (int, float)) and isinstance(previous_close, (int, float)):
        change = current_price - previous_close
        change_percent = (change / previous_close * 100) if previous_close else 0.0
        change_symbol = "🔺" if change >= 0 else "🔻"
    else:
        change, change_percent, change_symbol = "N/A", "N/A", ""

    return (
        f"📈 **{company_name} ({ticker})**\n"
        f"💰 **Current Price:** ${current_price:.2f}\n"
        f"{change_symbol} **Change (Prev Close):** {change:+.2f} ({change_percent:.2f}%)\n"
    )

def get_price_data(ticker, stock=None):
    """Safely extract ticker data from the price payload."""
    stock_obj = stock or Ticker(ticker, max_retries=1, retry_pause=0.25, timeout=5)
    price_payload = getattr(stock_obj, "price", {})
    if not isinstance(price_payload, dict):
        return None
    data = price_payload.get(ticker)
    if not isinstance(data, dict):
        return None
    return data

def get_stock_price_value(ticker):
    # Check cached price first
    cached_price = get_cached_stock_price(ticker)
    if cached_price is not None:
        return cached_price

    # Enforce per-ticker cooldown
    now = time.time()
    last_fetch = last_fetch_time.get(ticker)
    if last_fetch and now - last_fetch < MIN_FETCH_INTERVAL:
        return cached_price  # return None when cache is unavailable

    try:
        data = get_price_data(ticker)
    except Exception as e:
        logger.warning(f"Price fetch failed for {ticker}: {e}")
        return None

    current_price = data.get("regularMarketPrice")

    # Store in cache
    if isinstance(current_price, (int, float)):
        update_stock_price_cache(ticker, current_price)
        last_fetch_time[ticker] = time.time()
    else:
        last_fetch_time[ticker] = time.time()

    return current_price

def ensure_user_record(user_id):
    """Ensure a default balance row exists for the user."""
    with sqlite3.connect("portfolio.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, ?)",
            (user_id, 10000.00),
        )
        conn.commit()

# ✅ Retrieve user balance
def get_balance(user_id):
    ensure_user_record(user_id)
    with sqlite3.connect("portfolio.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else 10000.00

# ✅ Buy stock
def buy_stock(user_id, ticker, quantity):
    if not ticker.isalnum():  # ticker must be alphanumeric
        return "⚠️ Invalid ticker symbol."
    if not isinstance(quantity, int) or quantity <= 0:
        return "⚠️ Quantity must be a positive integer."
    
    current_price = get_stock_price_value(ticker)  # use the hardened price fetch helper

    if current_price is None:  # if ticker/price is invalid
        return f"⚠️ Unable to fetch stock data for {ticker}. Please check the ticker symbol."

    total_cost = float(quantity) * float(current_price)
    balance = get_balance(user_id)

    if balance < total_cost:
        return "⚠️ Insufficient funds."

    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()

    ensure_user_record(user_id)
    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (total_cost, user_id))

    cursor.execute("INSERT INTO trades (user_id, ticker, quantity, price, trade_type) VALUES (?, ?, ?, ?, 'buy')",
                   (user_id, ticker, quantity, current_price))

    conn.commit()
    conn.close()

    # detailed log entry
    logger.info(f"User {user_id} bought {quantity} shares of {ticker} at ${current_price:.2f}. New balance: ${balance - total_cost:.2f}")

    return f"✅ Bought {quantity} shares of {ticker} at ${current_price:.2f} each. 💰 New Balance: ${balance - total_cost:.2f}"

# ✅ Sell stock
def sell_stock(user_id, ticker, quantity):
    ensure_user_record(user_id)
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()

    try:
        # Check net owned shares (buys - sells)
        cursor.execute("""
            SELECT 
                COALESCE((SELECT SUM(quantity) FROM trades WHERE user_id = ? AND ticker = ? AND trade_type = 'buy'), 0) -
                COALESCE((SELECT SUM(quantity) FROM trades WHERE user_id = ? AND ticker = ? AND trade_type = 'sell'), 0)
        """, (user_id, ticker, user_id, ticker))

        owned_quantity = cursor.fetchone()[0]

        if owned_quantity < quantity:
            return f"⚠️ You only own {owned_quantity} shares of {ticker}. Cannot sell {quantity} shares."

        current_price = get_stock_price_value(ticker)

        if current_price is None:
            return f"⚠️ Unable to fetch stock data for {ticker}. Please check the ticker symbol."

        total_sale = quantity * current_price

        # Update cash balance
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (total_sale, user_id))

        # Insert sell trade record
        cursor.execute("INSERT INTO trades (user_id, ticker, quantity, price, trade_type) VALUES (?, ?, ?, ?, 'sell')",
                    (user_id, ticker, quantity, current_price))

        conn.commit()

        return f"✅ Sold {quantity} shares of {ticker} at ${current_price:.2f}. 💰 New Balance: ${get_balance(user_id):.2f}"

    finally:
        conn.close()  # 🚀 always close DB connection via finally

def sell_all_stocks(user_id):
    ensure_user_record(user_id)
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()

    # Get all currently held stocks and quantities
    cursor.execute("""
        SELECT ticker, 
               COALESCE(SUM(CASE WHEN trade_type = 'buy' THEN quantity ELSE 0 END), 0) -
               COALESCE(SUM(CASE WHEN trade_type = 'sell' THEN quantity ELSE 0 END), 0) AS owned_quantity
        FROM trades 
        WHERE user_id = ?
        GROUP BY ticker
        HAVING owned_quantity > 0
    """, (user_id,))
    
    holdings = cursor.fetchall()

    if not holdings:
        conn.close()
        return "⚠️ You do not own any stocks to sell."

    total_sale_value = 0
    messages = ["📢 **All Stocks Sold:**"]

    for ticker, owned_quantity in holdings:
        current_price = get_stock_price_value(ticker)
        if current_price is None:
            continue

        total_sale_value += owned_quantity * current_price

        # **Record sell trade**
        cursor.execute("INSERT INTO trades (user_id, ticker, quantity, price, trade_type) VALUES (?, ?, ?, ?, 'sell')",
                       (user_id, ticker, owned_quantity, current_price))

        messages.append(f"✅ Sold {owned_quantity} shares of {ticker} at ${current_price:.2f}.")

    # **Update cash balance**
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (total_sale_value, user_id))
    conn.commit()
    conn.close()

    messages.append(f"💰 **New Balance: ${get_balance(user_id):.2f}**")
    return "\n".join(messages)

# ✅ Trade history lookup
def get_trade_history(user_id):
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()

    cursor.execute("SELECT ticker, quantity, price, trade_type, timestamp FROM trades WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
    trades = cursor.fetchall()

    conn.close()

    if not trades:
        return "⚠️ No trade history found."

    history = ["📜 **Trade History**"]
    for trade in trades:
        t_type = "🟢 Bought" if trade[3] == "buy" else "🔴 Sold"
        history.append(f"{t_type} {trade[1]} {trade[0]} @ ${trade[2]:.2f} ({trade[4]})")

    return "\n".join(history)

# ✅ Calculate total P/L
def get_pnl(user_id):
    holdings = get_user_holdings(user_id)

    if not holdings:
        return "⚠️ No stocks owned."

    total_pnl = 0
    portfolio_summary = ["📈 **Portfolio Performance**"]

    for item in holdings:
        ticker = item["ticker"]
        quantity = item["net_qty"]
        total_cost = item["cost_basis"]
        current_price = get_stock_price_value(ticker)
        if not isinstance(current_price, (int, float)):
            continue

        current_value = quantity * current_price
        profit_loss = current_value - total_cost
        total_pnl += profit_loss

        portfolio_summary.append(f"📊 **{ticker}**: {quantity} shares")
        portfolio_summary.append(f"🔹 Cost: ${total_cost:.2f} | Value: ${current_value:.2f}")
        portfolio_summary.append(f"💰 **P/L: {'+' if profit_loss >= 0 else '-'}${abs(profit_loss):.2f}**\n")

    portfolio_summary.append(f"**Total P/L: {'+' if total_pnl >= 0 else '-'}${abs(total_pnl):.2f}**")
    return "\n".join(portfolio_summary)

def deposit_funds(user_id, amount):
    if amount <= 0:
        return "⚠️ Deposit amount must be greater than zero."
    
    ensure_user_record(user_id)
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    
    return f"✅ Deposited ${amount:.2f}. New balance: ${get_balance(user_id):.2f}"

def withdraw_funds(user_id, amount):
    balance = get_balance(user_id)
    if amount <= 0:
        return "⚠️ Withdrawal amount must be greater than zero."
    if amount > balance:
        return "⚠️ Insufficient funds."
    
    ensure_user_record(user_id)
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    
    return f"✅ Withdrawn ${amount:.2f}. New balance: ${get_balance(user_id):.2f}"

def get_leaderboard():
    with sqlite3.connect("portfolio.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, balance, (balance - 10000) / 10000 * 100 AS profit_pct
            FROM users ORDER BY balance DESC LIMIT 10
        """)
        rankings = cursor.fetchall()

    if not rankings:
        return "⚠️ No investment data available."

    leaderboard = ["🏆 **Top Investors**"]
    for i, (user_id, balance, profit_pct) in enumerate(rankings, start=1):
        leaderboard.append(f"{i}️⃣ <@{user_id}> - 💰 ${balance:.2f} (**{profit_pct:+.2f}%**)")

    return "\n".join(leaderboard)

def compare_users(user1, user2):
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()

    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user1,))
    balance1 = cursor.fetchone()
    
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user2,))
    balance2 = cursor.fetchone()
    
    conn.close()

    if not balance1 or not balance2:
        return "⚠️ One or both users have no investment data."

    pnl1 = balance1[0] - 10000
    pnl2 = balance2[0] - 10000

    return (
        f"📊 **Investment Comparison**\n"
        f"🔹 <@{user1}>: **{pnl1:+.2f}%**\n"
        f"🔹 <@{user2}>: **{pnl2:+.2f}%**"
    )

def get_user_holdings(user_id):
    """Compute current holdings from full trade history."""
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT ticker,
               SUM(CASE WHEN trade_type = 'buy' THEN quantity ELSE 0 END) AS buy_qty,
               SUM(CASE WHEN trade_type = 'buy' THEN quantity * price ELSE 0 END) AS buy_cost,
               SUM(CASE WHEN trade_type = 'sell' THEN quantity ELSE 0 END) AS sell_qty,
               SUM(CASE WHEN trade_type = 'sell' THEN quantity * price ELSE 0 END) AS sell_value
        FROM trades
        WHERE user_id = ?
        GROUP BY ticker
        """,
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    holdings = []
    for ticker, buy_qty, buy_cost, sell_qty, sell_value in rows:
        buy_qty = buy_qty or 0
        buy_cost = buy_cost or 0.0
        sell_qty = sell_qty or 0
        net_qty = buy_qty - sell_qty
        if net_qty <= 0:
            continue
        avg_buy_price = buy_cost / buy_qty if buy_qty else 0.0
        cost_basis = avg_buy_price * net_qty
        holdings.append(
            {
                "ticker": ticker,
                "buy_qty": buy_qty,
                "buy_cost": buy_cost,
                "net_qty": net_qty,
                "avg_buy_price": avg_buy_price,
                "cost_basis": cost_basis,
            }
        )

    return holdings

def get_portfolio(user_id):
    holdings = get_user_holdings(user_id)

    if not holdings:
        return "⚠️ You do not own any stocks."

    portfolio_summary = ["📊 **Your Portfolio Holdings**"]
    total_pnl = 0

    for item in holdings:
        ticker = item["ticker"]
        total_quantity = item["net_qty"]
        total_cost = item["cost_basis"]
        current_price = get_stock_price_value(ticker)
        if current_price is None:
            continue

        avg_buy_price = item["avg_buy_price"]
        current_value = total_quantity * current_price
        unrealized_pnl = current_value - total_cost
        total_pnl += unrealized_pnl

        portfolio_summary.append(
            f"📈 **{ticker}**: {total_quantity} shares\n"
            f"🔹 **Avg Buy Price:** ${avg_buy_price:.2f} | **Current Price:** ${current_price:.2f}\n"
            f"💰 **Unrealized P/L:** {'+' if unrealized_pnl >= 0 else '-'}${abs(unrealized_pnl):.2f}\n"
        )

    portfolio_summary.append(f"**Total P/L: {'+' if total_pnl >= 0 else '-'}${abs(total_pnl):.2f}**")
    portfolio_summary.append(f"💵 **Cash Balance: ${get_balance(user_id):.2f}**")

    return "\n".join(portfolio_summary)

def reset_portfolio(user_id):
    ensure_user_record(user_id)
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()

    # Delete trade history and holdings
    cursor.execute("DELETE FROM trades WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM alerts WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM watchlist WHERE user_id = ?", (user_id,))
    cursor.execute("UPDATE users SET balance = 10000 WHERE user_id = ?", (user_id,))

    conn.commit()
    conn.close()
    return "✅ Your investment portfolio has been reset to the initial state."

def add_to_watchlist(user_id, ticker):
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()

    cursor.execute("INSERT OR IGNORE INTO watchlist (user_id, ticker) VALUES (?, ?)", (user_id, ticker.upper()))
    conn.commit()
    conn.close()

    return f"✅ {ticker.upper()} added to your watchlist!"

def remove_from_watchlist(user_id, ticker):
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()

    # Check whether watchlist item exists
    cursor.execute("SELECT 1 FROM watchlist WHERE user_id = ? AND ticker = ?", (user_id, ticker.upper()))
    if not cursor.fetchone():
        conn.close()
        return f"⚠️ {ticker.upper()} is not in your watchlist."

    # Perform delete
    cursor.execute("DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (user_id, ticker.upper()))
    conn.commit()
    conn.close()
    return f"✅ {ticker.upper()} removed from your watchlist!"

def clear_watchlist(user_id):
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM watchlist WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return "✅ Your watchlist has been cleared."

def list_watchlist(user_id):
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()

    cursor.execute("SELECT ticker FROM watchlist WHERE user_id = ?", (user_id,))
    tickers = [row[0] for row in cursor.fetchall()]
    conn.close()

    if not tickers:
        return "⚠️ Your watchlist is empty."

    return "📋 **Your Watchlist:**\n" + "\n".join([f"🔹 {ticker}" for ticker in tickers])

def add_alert(user_id, ticker, target_price):
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()

    cursor.execute("INSERT OR REPLACE INTO alerts (user_id, ticker, target_price) VALUES (?, ?, ?)", 
                   (user_id, ticker.upper(), target_price))
    conn.commit()
    conn.close()

    return f"✅ Price alert set for {ticker.upper()} at ${target_price:.2f}."

def remove_alert(user_id, ticker):
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()

    # Check whether alert exists
    cursor.execute("SELECT 1 FROM alerts WHERE user_id = ? AND ticker = ?", (user_id, ticker.upper()))
    if not cursor.fetchone():
        conn.close()
        return f"⚠️ No alert set for {ticker.upper()}."

    # Perform delete
    cursor.execute("DELETE FROM alerts WHERE user_id = ? AND ticker = ?", (user_id, ticker.upper()))
    conn.commit()
    conn.close()
    return f"✅ Alert for {ticker.upper()} removed."

def clear_alerts(user_id):
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM alerts WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return "✅ All your alerts have been cleared."

def list_alerts(user_id):
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()

    cursor.execute("SELECT ticker, target_price FROM alerts WHERE user_id = ?", (user_id,))
    alerts = cursor.fetchall()
    conn.close()

    if not alerts:
        return "⚠️ No active alerts."

    return "📢 **Your Active Alerts:**\n" + "\n".join([f"🔹 {ticker} at ${price:.2f}" for ticker, price in alerts])

def get_portfolio_analysis(user_id):
    """
    Analyze and visualize a user portfolio (returns images for Discord upload).
    """
    holdings = get_user_holdings(user_id)

    if not holdings:
        return "⚠️ You do not own any stocks.", None

    tickers = [row["ticker"] for row in holdings]
    quantities = {row["ticker"]: row["net_qty"] for row in holdings}
    costs = {row["ticker"]: row["cost_basis"] for row in holdings}
    
    # Fetch current prices
    current_prices = {ticker: get_stock_price_value(ticker) for ticker in tickers}

    # Compute valuation and returns
    values = {ticker: quantities[ticker] * current_prices[ticker] for ticker in tickers}
    profits = {ticker: values[ticker] - costs[ticker] for ticker in tickers}
    total_cost = sum(costs.values())
    total_value = sum(values.values())

    # Build dataframe
    df = pd.DataFrame({
        "Ticker": tickers,
        "Quantity": [quantities[t] for t in tickers],
        "Cost": [costs[t] for t in tickers],
        "Current Value": [values[t] for t in tickers],
        "Profit": [profits[t] for t in tickers]
    })

    # 📊 **Pie chart: allocation by ticker**
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(values.values(), labels=tickers, autopct="%1.1f%%", startangle=140)
    ax.set_title(f"Portfolio Allocation for {user_id}")
    pie_chart_path = "portfolio_pie.png"
    plt.savefig(pie_chart_path)
    plt.close()

    # 📈 **Bar chart: profit/loss by ticker**
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(df["Ticker"], df["Profit"], color=['green' if p >= 0 else 'red' for p in df["Profit"]])
    ax.set_title(f"Profit/Loss per Stock for {user_id}")
    ax.set_xlabel("Stock Ticker")
    ax.set_ylabel("Profit ($)")
    bar_chart_path = "portfolio_profit.png"
    plt.savefig(bar_chart_path)
    plt.close()

    # 🏆 **Total portfolio summary**
    summary = (
        f"📊 **Portfolio Analysis for {user_id}**\n"
        f"💰 **Total Investment:** ${total_cost:.2f}\n"
        f"💹 **Current Portfolio Value:** ${total_value:.2f}\n"
        f"📈 **Total Profit/Loss:** ${total_value - total_cost:.2f}\n"
    )

    return summary, [pie_chart_path, bar_chart_path]

async def check_alerts():
    await bot.wait_until_ready()
    while not bot.is_closed():
        conn = sqlite3.connect("portfolio.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, ticker, target_price FROM alerts")
        alerts = cursor.fetchall()
        conn.close()

        for user_id, ticker, target_price in alerts:
            price = get_stock_price_value(ticker)
            if price is not None and isinstance(price, (int, float)) and price >= target_price:
                user = await bot.fetch_user(int(user_id))
                if user:
                    await user.send(f"🚨 {ticker} has reached ${price:.2f}!")
                    remove_alert(user_id, ticker)  # remove alert after notification

        await asyncio.sleep(600)  # check every 10 minutes (reduce API load)
    
async def send_daily_news():
    news = get_financial_news()
    if isinstance(news, list) and news:
        formatted_news = "\n\n".join([f"🔹 **{article.get('title', 'No Title')}**\n{article.get('url', '#')}" for article in news])
        for guild in bot.guilds:
            for channel in guild.text_channels:
                if channel.name == "news-channel":  # set your target news channel name
                    await channel.send(f"📢 **Latest Financial News**\n\n{formatted_news}")
                    break

def schedule_daily_news():
    schedule.every().day.at("08:00").do(lambda: asyncio.create_task(send_daily_news()))

async def schedule_runner():
    """Runner loop for `schedule` jobs."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        schedule.run_pending()
        await asyncio.sleep(30)

def get_trending_stocks():
    """
    Recommend stocks with strong 5-day performance.
    """
    trending_stocks = []
    tickers = ["AAPL", "TSLA", "MSFT", "GOOGL", "AMZN"]  # seed ticker list (expandable)

    for ticker in tickers:
        stock = Ticker(ticker)
        history = stock.history(period="5d")  # last 5 days of data
        if history is not None and not history.empty:
            close_prices = history["close"].values
            if len(close_prices) >= 2:
                change = (close_prices[-1] - close_prices[0]) / close_prices[0] * 100  # 5-day change rate
                trending_stocks.append((ticker, change))

    trending_stocks.sort(key=lambda x: x[1], reverse=True)  # sort by gain descending
    return trending_stocks[:3]  # return top 3 tickers

def get_sentiment_score(news_title):
    """
    Score sentiment from news headlines (more positive headlines => higher score).
    """
    return TextBlob(news_title).sentiment.polarity

def get_positive_news_stocks():
    """
    Recommend stocks with mostly positive headlines.
    """
    url = f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_API_KEY}"
    response = requests.get(url).json()
    
    stock_sentiments = {}

    if "articles" in response:
        for article in response["articles"]:
            title = article["title"]
            sentiment = get_sentiment_score(title)

            for ticker in ["AAPL", "TSLA", "MSFT", "GOOGL", "AMZN"]:  # watchlist ticker universe
                if ticker in title.upper():
                    stock_sentiments[ticker] = stock_sentiments.get(ticker, 0) + sentiment
    
    sorted_stocks = sorted(stock_sentiments.items(), key=lambda x: x[1], reverse=True)
    return sorted_stocks[:3]  # return top 3 recommendations

def get_trend(ticker):
    stock = Ticker(ticker)
    history = stock.history(period="7d")

    if history is None or history.empty:
        return f"⚠️ Unable to fetch trend data for {ticker}. Please check the ticker symbol."

    closing_prices = history['close'].values
    if len(closing_prices) < 2:
        return f"⚠️ Not enough data to calculate trend for {ticker}."

    trend = ((closing_prices[-1] - closing_prices[0]) / closing_prices[0]) * 100
    trend_symbol = "🔺" if trend >= 0 else "🔻"

    return f"📈 **{ticker}**: **{trend_symbol} {trend:.2f}%** change over the last 7 days."

def get_news_sentiment(ticker):
    url = f"https://newsapi.org/v2/everything?q={ticker}&apiKey={NEWS_API_KEY}"
    response = requests.get(url)
    data = response.json()

    if "articles" not in data or not data["articles"]:
        return f"⚠️ No news found for {ticker}. Please check if the ticker symbol is correct."

    sentiment_scores = []
    for article in data["articles"][:5]:  # analyze only the latest 5 articles
        text = article["title"] + ". " + (article["description"] if article["description"] else "")
        sentiment = TextBlob(text).sentiment.polarity
        sentiment_scores.append(sentiment)

    if not sentiment_scores:
        return f"⚠️ Not enough news data to analyze sentiment for {ticker}."

    avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)
    sentiment_symbol = "📈 Positive" if avg_sentiment > 0 else "📉 Negative"

    return f"📰 **{ticker} News Sentiment:** {sentiment_symbol} ({avg_sentiment:.2f})"

def get_top_stocks(limit=10):
    """
    Get top symbols using a market-cap benchmark.
    """
    stock_list = Ticker("^NDX").symbols  # fetch Nasdaq-100 symbols
    return stock_list[:limit]  # recommend top 10 symbols

def recommend_stocks():
    """
    Randomly choose candidate stocks and return trend + sentiment.
    """
    tickers = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN", "NVDA", "META", "NFLX", "DIS", "BABA"]
    selected_tickers = random.sample(tickers, 3)  # pick 3 random tickers
    recommendations = ["📢 **Investment Recommendations**\n"]

    for ticker in selected_tickers:
        trend = get_trend(ticker)  # 5-day trend
        sentiment = get_news_sentiment(ticker)  # news sentiment analysis
        recommendations.append(f"{trend}\n{sentiment}\n")

    return "\n".join(recommendations)

def add_percentage_alert(user_id, ticker, percentage_change):
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO alerts (user_id, ticker, target_price)
        VALUES (?, ?, ?)
    """, (user_id, ticker.upper(), percentage_change))

    conn.commit()
    conn.close()

    return f"✅ Price alert set for {ticker.upper()} at ±{percentage_change:.2f}% movement."

async def check_percentage_alerts():
    """
    Periodically check user-defined % alerts and send Discord notifications.
    """
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        conn = sqlite3.connect("portfolio.db")
        cursor = conn.cursor()
        
        cursor.execute("SELECT user_id, ticker, target_price FROM alerts")
        alerts = cursor.fetchall()
        conn.close()

        for user_id, ticker, target_change in alerts:
            current_price = get_stock_price_value(ticker)
            price_data = get_price_data(ticker)
            previous_close = price_data.get("regularMarketPreviousClose") if price_data else None

            if current_price and previous_close:
                percentage_change = ((current_price - previous_close) / previous_close) * 100
                
                if abs(percentage_change) >= target_change:
                    user = await bot.fetch_user(int(user_id))
                    if user:
                        await user.send(f"🚨 **Price Alert!** {ticker} has changed by {percentage_change:.2f}% (Target: ±{target_change:.2f}%).")
                        remove_alert(user_id, ticker)

        await asyncio.sleep(600)  # check every 10 minutes (reduce API load)

def get_stock_chart(ticker, period="10y"):
    try:
        # 📊 Fetch data
        stock = Ticker(ticker)
        history = stock.history(period=period)

        if history.empty:
            return None, f"⚠️ No data available for {ticker} over the period '{period}'."

        # ✅ Flatten MultiIndex
        history = history.reset_index()

        # Normalize date column from string values
        history["date"] = pd.to_datetime(history["date"].astype(str), errors="coerce")  # convert to datetime after string normalization
        history = history[["date", "close"]]  # keep only required columns

        # Add moving averages
        history["SMA_50"] = history["close"].rolling(window=50, min_periods=1).mean()
        history["SMA_200"] = history["close"].rolling(window=200, min_periods=1).mean()
        history["EMA_20"] = history["close"].ewm(span=20, adjust=False).mean()

        # Compute RSI
        delta = history["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=14, min_periods=1).mean()
        avg_loss = loss.rolling(window=14, min_periods=1).mean()
        rs = avg_gain / avg_loss
        history["RSI_14"] = 100 - (100 / (1 + rs))

        # 📈 Build chart
        fig, ax = plt.subplots(2, figsize=(10, 8), gridspec_kw={'height_ratios': [3, 1]})

        # 🔹 Price chart
        ax[0].plot(history["date"], history["close"], marker="o", linestyle="-", label=f"{ticker} Price", color="blue")
        ax[0].plot(history["date"], history["SMA_50"], linestyle="--", label="SMA 50", color="orange")
        ax[0].plot(history["date"], history["SMA_200"], linestyle="--", label="SMA 200", color="red")
        ax[0].plot(history["date"], history["EMA_20"], linestyle="-", label="EMA 20", color="green")

        # Format x-axis
        ax[0].xaxis.set_major_locator(MaxNLocator(10))
        ax[0].xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax[0].set_title(f"{ticker.upper()} Stock Price with Indicators ({period})", fontsize=14)
        ax[0].set_xlabel("Date", fontsize=12)
        ax[0].set_ylabel("Price (USD)", fontsize=12)
        ax[0].legend()
        ax[0].grid(True)

        # 🔹 RSI chart
        ax[1].plot(history["date"], history["RSI_14"], color="purple", label="RSI 14")
        ax[1].axhline(70, linestyle="--", color="red")  # overbought threshold
        ax[1].axhline(30, linestyle="--", color="green")  # oversold threshold
        ax[1].set_ylabel("RSI Value")
        ax[1].set_xlabel("Date")
        ax[1].set_title("Relative Strength Index (RSI)")
        ax[1].legend()
        ax[1].grid(True)

        # Save chart
        chart_path = f"{ticker}_chart.png"
        plt.tight_layout()
        plt.savefig(chart_path)
        plt.close()

        return chart_path, None

    except Exception as e:
        err_text = str(e)
        if "429" in err_text or "ResponseError" in err_text:
            return None, "⚠️ Unable to fetch chart data right now (rate limit). Please try again in a few minutes."
        return None, f"⚠️ Unable to generate chart right now. {e}"

def create_plotly_chart(ticker, period="1y"):
    stock = Ticker(ticker)
    history = stock.history(period=period)

    if history.empty:
        return None, f"⚠️ No data available for {ticker} over the period '{period}'."

    # Normalize dataframe
    history = history.reset_index()
    history["date"] = pd.to_datetime(history["date"])
    if history["date"].iloc[0].tzinfo is not None:
        history["date"] = history["date"].dt.tz_convert(None)
    else:
        history["date"] = history["date"].dt.tz_localize(None)
    history = history[["date", "close"]]

    # Plotly Build chart
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=history["date"],
        y=history["close"],
        mode='lines',
        line=dict(color='gold', width=2),
        fill='tozeroy',
        name=ticker
    ))

    # Configure layout
    fig.update_layout(
        title=f"{ticker.upper()} Stock Price Over {period}",
        xaxis_title="Date",
        yaxis_title="Price (USD)",
        template="plotly_dark",
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=False),
        font=dict(size=14)
    )

    # Save chart as PNG
    chart_path = f"{ticker}_plotly_chart.png"
    fig.write_image(chart_path)
    return chart_path, None

def export_portfolio_to_csv(user_id):
    holdings = get_user_holdings(user_id)

    if not holdings:
        return None, "⚠️ You do not own any stocks."

    data = []
    for item in holdings:
        ticker = item["ticker"]
        quantity = item["net_qty"]
        total_cost = item["cost_basis"]
        current_price = get_stock_price_value(ticker)
        if current_price is None:
            continue
        avg_buy_price = item["avg_buy_price"] if quantity > 0 else 0
        current_value = quantity * current_price
        profit_loss = current_value - total_cost
        data.append([ticker, quantity, avg_buy_price, current_price, profit_loss])

    df = pd.DataFrame(data, columns=["Ticker", "Quantity", "Avg Buy Price", "Current Price", "Profit/Loss"])
    file_path = f"{user_id}_portfolio.csv"
    df.to_csv(file_path, index=False)
    return file_path, None

def get_cached_stock_price(ticker):
    if r:
        cached_price = r.get(f"stock_price:{ticker}")
        if cached_price:
            return float(cached_price)
    else:
        cached_data = price_cache.get(ticker)
        if cached_data and time.time() - cached_data[1] < CACHE_EXPIRY:
            return cached_data[0]
    return None

def update_stock_price_cache(ticker, price):
    """Store stock price in cache."""
    price_cache[ticker] = (price, time.time())
    if r:
        try:
            r.setex(f"stock_price:{ticker}", CACHE_EXPIRY, price)
        except redis.RedisError:
            pass

async def send_chart(channel, ticker, period="1mo"):
    chart_path = f"{ticker}_chart.png"

    try:
        # (1) Build chart example
        plt.figure(figsize=(6, 4))
        plt.plot([1, 2, 3], [4, 5, 6])  # simple line plot example
        plt.title(f"Stock Chart for {ticker}")
        plt.savefig(chart_path)  # save file
        plt.close()

        # (2) send file to Discord channel
        await channel.send(file=discord.File(chart_path))
    finally:
        if os.path.exists(chart_path):
            os.remove(chart_path)

async def send_portfolio_csv(channel, user_id):
    file_path = f"{user_id}_portfolio.csv"

    # (1) generate CSV file
    data = {"Ticker": ["AAPL", "TSLA"], "Quantity": [10, 5], "Price": [150, 800]}
    df = pd.DataFrame(data)
    df.to_csv(file_path, index=False)

    # (2) CSV send file to Discord channel
    await channel.send(file=discord.File(file_path))

    # (3) delete file after sending
    os.remove(file_path)

def get_financial_news():
    cache_key = "news_cache"
    
    if r:  # use cache only when Redis is available
        cached_news = r.get(cache_key)
        if cached_news:
            return json.loads(cached_news)

    # fetch latest business headlines from News API
    url = f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_API_KEY}"
    response = requests.get(url).json()

    if "articles" in response:
        news = response["articles"][:5]  # keep top 5 articles
        if r:
            r.setex(cache_key, 1800, json.dumps(news))  # cache for 30 minutes
        return news

    return "⚠️ Unable to fetch news."

async def send_help_message(channel):
    """Send the help message in multiple chunks to avoid character limits."""
    chunks = HELP_MESSAGE.split("\n\n")  # split by paragraph breaks
    for chunk in chunks:
        await channel.send(chunk.strip())  # trim whitespace before sending

def log_user_interaction(user_id):
    """Record user interactions in the database."""
    with sqlite3.connect("bot_stats.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS unique_users (
                user_id TEXT PRIMARY KEY
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO unique_users (user_id) VALUES (?)", (user_id,))
        conn.commit()

# Run when the bot is ready
@bot.event
async def on_ready():
    if not hasattr(bot, "news_scheduled"):  # prevent duplicate scheduling
        schedule_daily_news()
        bot.news_scheduled = True

    if not hasattr(bot, "background_tasks_started"):
        bot.loop.create_task(schedule_runner())
        bot.loop.create_task(check_alerts())
        bot.background_tasks_started = True

    print(f'✅ Logged in as {bot.user}!')

def get_unique_user_count():
    """Count users who actually interacted with the bot."""
    with sqlite3.connect("bot_stats.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM unique_users")
        result = cursor.fetchone()
        return result[0] if result else 0

def get_total_user_count():
    global last_user_count, last_user_count_time

    # return cached value for requests within 10 seconds
    if time.time() - last_user_count_time < 10:
        return last_user_count

    # fetch a fresh user count
    last_user_count = sum(guild.member_count for guild in bot.guilds)
    last_user_count_time = time.time()
    
    return last_user_count

async def update_bot_stats():
    """Update global server/user bot stats."""
    total_servers = len(bot.guilds)
    total_users = get_total_user_count()
    unique_users = get_unique_user_count()  # ✅ include interacted-user count

    with sqlite3.connect("bot_stats.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO stats (servers, users, event_type)
            VALUES (?, ?, 'update')
        """, (total_servers, total_users))
        conn.commit()

    # ✅ admin log output
    logger.info(f"[ADMIN] Unique Users (Actual Bot Users): {unique_users}")

@bot.event
async def on_guild_join(guild):
    await asyncio.sleep(5)
    await update_bot_stats()
    logger.info(f"✅ Bot joined: {guild.name} (ID: {guild.id}) | Total servers: {len(bot.guilds)}")

@bot.event
async def on_guild_remove(guild):
    await asyncio.sleep(5)
    await update_bot_stats()
    logger.info(f"❌ Bot removed from: {guild.name} (ID: {guild.id}) | Total servers: {len(bot.guilds)}")

@bot.command()
async def stats(ctx):
    total_servers = len(bot.guilds)
    total_users = sum(guild.member_count for guild in bot.guilds)

    await ctx.send(
        f"📊 **Bot Statistics:**\n"
        f"🔹 Connected Servers: {total_servers}\n"
        f"🔹 Unique Users: {total_users}"
    )

# ✅ Message handler (user commands)
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    user_id = str(message.author.id)  # store user ID
    log_user_interaction(user_id)
    content = message.content.lower()  # 🔹 define content variable first

    # ping check
    if message.content.lower() == "ping":
        await message.channel.send("pong!")

    # Stock price lookup (!price <ticker>)
    # Handle !price command
    elif message.content.startswith("!price"):
        try:
            # parse ticker symbol
            parts = message.content.split()
            if len(parts) < 2:
                await message.channel.send("⚠️ Please provide a stock ticker symbol. Example: `!price AAPL`")
                return
            
            ticker = parts[1].upper()

            # validate ticker symbol
            if not ticker.isalnum():  # ticker must contain letters/numbers only
                await message.channel.send(f"⚠️ `{ticker}` is not a valid stock ticker symbol. Please use a valid symbol (e.g., AAPL).")
                return

            # validate availability through Yahoo Finance
            price = get_stock_price_value(ticker)
            if price is None:
                await message.channel.send(f"⚠️ `{ticker}` is not a valid stock ticker symbol or is not available.")
            else:
                response_message = get_stock_price(ticker)
                await message.channel.send(response_message)
        except IndexError:
            await message.channel.send("⚠️ Please provide a stock ticker symbol. Example: `!price AAPL`")

    # ✅ Handle `!news` by fetching financial headlines
    elif content == "!news":
        news = get_financial_news()

        if isinstance(news, list) and news:
            formatted_news = "\n\n".join([f"🔹 **{article.get('title', 'No Title')}**\n{article.get('url', '#')}" for article in news])
        else:
            formatted_news = "⚠️ No recent financial news available."

        await message.channel.send(f"📢 **Latest Financial News**\n\n{formatted_news}")
    
    elif message.content.startswith("!buy"):
        parts = message.content.split()
        if len(parts) < 3 or not parts[2].isdigit():
            await message.channel.send("⚠️ Please provide a valid stock ticker and quantity. Example: `!buy AAPL 10`")
            return

        _, ticker, quantity = parts
        response_message = buy_stock(user_id, ticker.upper(), int(quantity))
        await message.channel.send(response_message)

    elif message.content.lower() == "!sellall":
            await message.channel.send(sell_all_stocks(user_id))

    elif message.content.startswith("!sell"):
        parts = message.content.split()
        if len(parts) < 3 or not parts[2].isdigit():
            await message.channel.send("⚠️ Please provide a valid stock ticker and quantity. Example: `!sell TSLA 5`")
            return

        _, ticker, quantity = parts
        response_message = sell_stock(user_id, ticker.upper(), int(quantity))
        await message.channel.send(response_message)

    elif message.content.lower() == "!balance":
        await message.channel.send(f"💰 Current Balance: ${get_balance(user_id):.2f}")

    elif message.content.lower() == "!history":
        await message.channel.send(get_trade_history(user_id))

    elif message.content.lower() == "!pnl":
        await message.channel.send(get_pnl(user_id))

    elif message.content.startswith("!deposit"):
        parts = message.content.split()
        if len(parts) < 2 or not parts[1].replace('.', '', 1).isdigit() or float(parts[1]) <= 0:
            await message.channel.send("⚠️ Please enter a valid amount greater than zero. Example: `!deposit 1000`")
            return
        amount = float(parts[1])
        response = deposit_funds(user_id, amount)
        await message.channel.send(response)
    
    elif message.content.startswith("!withdraw"):
        parts = message.content.split()
        if len(parts) < 2 or not parts[1].replace('.', '', 1).isdigit() or float(parts[1]) <= 0:
            await message.channel.send("⚠️ Please enter a valid amount greater than zero. Example: `!withdraw 500`")
            return
        amount = float(parts[1])
        response = withdraw_funds(user_id, amount)
        await message.channel.send(response)
    
    elif message.content.lower() == "!leaderboard":
        await message.channel.send(get_leaderboard())
    
    elif message.content.startswith("!compare"):
        parts = message.content.split()
        if len(parts) < 3:
            await message.channel.send("⚠️ Usage: `!compare @user1 @user2`")
            return
        user1 = parts[1].strip("<@!>")
        user2 = parts[2].strip("<@!>")
        await message.channel.send(compare_users(user1, user2))
    
    elif message.content.startswith("!watchlist"):
        parts = message.content.split()
        if len(parts) < 2:
            await message.channel.send("⚠️ Usage:\n`!watchlist <TICKER>` → Add ticker\n`!watchlist remove <TICKER>` → Remove ticker\n`!watchlist list` → View watchlist\n`!watchlist clear` → Remove all watchlist items")
            return

        action = parts[1].lower()
        
        if action == "list":
            response = list_watchlist(user_id)
        elif action == "remove" and len(parts) > 2:
            response = remove_from_watchlist(user_id, parts[2].upper())
        elif action == "clear":
            response = clear_watchlist(user_id)
        else:
            response = add_to_watchlist(user_id, parts[1].upper())

        await message.channel.send(response)
    
    elif message.content.lower() == "!portfolio":
        await message.channel.send(get_portfolio(user_id))
    
    elif message.content.lower() == "!reset":
        await message.channel.send(reset_portfolio(user_id))
    
    elif message.content.startswith("!alert"):
        parts = message.content.split()
        
        if len(parts) == 1:
            await message.channel.send("⚠️ Usage: `!alert <TICKER> <PRICE>` or `!alert list` or `!alert remove <TICKER>`")
            return
        
        action = parts[1].lower()
        
        if action == "list":
            response = list_alerts(user_id)
        elif action == "remove" and len(parts) > 2:
            response = remove_alert(user_id, parts[2].upper())
        elif len(parts) == 3 and parts[2].replace('.', '', 1).isdigit():
            response = add_alert(user_id, parts[1].upper(), float(parts[2]))
        else:
            response = "⚠️ Invalid command. Example: `!alert AAPL 150`"

        await message.channel.send(response)
    
    elif content.startswith("!recommend"):
        response = recommend_stocks()
        await message.channel.send(response)

    elif content.startswith("!trend"):
        parts = content.split()
        if len(parts) < 2:
            await message.channel.send("⚠️ Please provide a stock ticker. Example: `!trend AAPL`")
        else:
            response = get_trend(parts[1].upper())
            await message.channel.send(response)

    elif content.startswith("!sentiment"):
        parts = content.split()
        if len(parts) < 2:
            await message.channel.send("⚠️ Please provide a stock ticker. Example: `!sentiment TSLA`")
        else:
            response = get_news_sentiment(parts[1].upper())
            await message.channel.send(response)

    # 📊 **Portfolio analysis command**
    elif content.startswith("!portfolio_analysis"):
        response, image_paths = get_portfolio_analysis(user_id)
        await message.channel.send(response)
        
        if image_paths:
            for path in image_paths:
                with open(path, "rb") as file:
                    await message.channel.send(file=discord.File(file))
                    os.remove(path)  # cleanup after sending
    
    elif content.startswith("!chart"):
        parts = content.split()
        if len(parts) < 2:
            await message.channel.send("⚠️ Please provide a stock ticker. Example: `!chart AAPL`")
            return

        ticker = parts[1].upper()
        valid_periods = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max"]
        period = parts[2] if len(parts) > 2 and parts[2] in valid_periods else "1mo"

        chart_path, error_msg = get_stock_chart(ticker, period)
        if error_msg:
            await message.channel.send(error_msg)
        else:
            await message.channel.send(f"📊 {ticker} stock chart with indicators for {period}:")
            await message.channel.send(file=discord.File(chart_path))
    
    elif message.content.lower() == "!download_portfolio":
        user_id = str(message.author.id)
        file_path, error = export_portfolio_to_csv(user_id)
        if error:
            await message.channel.send(error)
        else:
            await message.channel.send("📄 Here is your portfolio CSV file:", file=discord.File(file_path))

    elif message.content.lower() == "!help":
        await send_help_message(message.channel)
    
    # ✅ call `bot.process_commands()` only for non-command input
    else:
        await bot.process_commands(message)

# Bot startup
validate_env_variables()  # validate environment variables
bot.run(TOKEN)
