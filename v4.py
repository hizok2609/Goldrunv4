import requests
import time
from datetime import datetime
import os

# =========================
# CONFIG
# =========================


API_KEY = os.getenv("API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SYMBOL = "XAU/USD"

EMA_FAST = 50
EMA_SLOW = 200
RSI_PERIOD = 14
ATR_PERIOD = 14

TP_POINTS = 3.0
SL_POINTS = 2.0

COOLDOWN_MINUTES = 20
last_signal_time = None

# =========================
# TELEGRAM
# =========================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        requests.post(url, data=payload)
    except Exception as e:
        print("Telegram Error:", e)

# =========================
# GET MARKET DATA
# =========================
def get_data(interval="5min", outputsize=250):
    url = (
        f"https://api.twelvedata.com/time_series?"
        f"symbol={SYMBOL}&interval={interval}&outputsize={outputsize}&apikey={API_KEY}"
    )

    response = requests.get(url).json()

    if "values" not in response:
        print("DATA ERROR")
        print(response)
        return None

    candles = response["values"]
    candles.reverse()

    closes = []
    highs = []
    lows = []
    opens = []

    for candle in candles:
        closes.append(float(candle["close"]))
        highs.append(float(candle["high"]))
        lows.append(float(candle["low"]))
        opens.append(float(candle["open"]))

    return {
        "close": closes,
        "high": highs,
        "low": lows,
        "open": opens
    }

# =========================
# EMA CALCULATION
# =========================
def calculate_ema(prices, period):
    multiplier = 2 / (period + 1)

    ema = prices[0]

    for price in prices[1:]:
        ema = (price - ema) * multiplier + ema

    return ema

# =========================
# RSI CALCULATION
# =========================
def calculate_rsi(prices, period=14):
    gains = []
    losses = []

    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]

        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    return rsi

# =========================
# ATR CALCULATION
# =========================
def calculate_atr(highs, lows, closes, period=14):
    trs = []

    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )

        trs.append(tr)

    atr = sum(trs[-period:]) / period

    return atr

# =========================
# TREND FILTER
# =========================
def trend_bias(closes):
    ema50 = calculate_ema(closes[-100:], EMA_FAST)
    ema200 = calculate_ema(closes[-250:], EMA_SLOW)

    if ema50 > ema200:
        return "BULLISH"

    elif ema50 < ema200:
        return "BEARISH"

    return "NEUTRAL"

# =========================
# BOS DETECTION
# =========================
def bullish_bos(highs, closes):
    recent_high = max(highs[-6:-1])
    current_close = closes[-1]

    return current_close > recent_high


def bearish_bos(lows, closes):
    recent_low = min(lows[-6:-1])
    current_close = closes[-1]

    return current_close < recent_low

# =========================
# STRONG CANDLE FILTER
# =========================
def strong_bullish_candle(opens, highs, closes):
    body = abs(closes[-1] - opens[-1])
    wick = highs[-1] - closes[-1]

    return body > wick * 2


def strong_bearish_candle(opens, lows, closes):
    body = abs(closes[-1] - opens[-1])
    wick = closes[-1] - lows[-1]

    return body > wick * 2

# =========================
# LIQUIDITY SWEEP
# =========================
def liquidity_sweep_buy(lows, opens, closes):
    previous_low = min(lows[-6:-1])

    swept = lows[-1] < previous_low
    recovery = closes[-1] > opens[-1]

    return swept and recovery


def liquidity_sweep_sell(highs, opens, closes):
    previous_high = max(highs[-6:-1])

    swept = highs[-1] > previous_high
    rejection = closes[-1] < opens[-1]

    return swept and rejection

# =========================
# SESSION FILTER
# =========================
def valid_session():
    hour = datetime.utcnow().hour

    london = 7 <= hour <= 16
    new_york = 12 <= hour <= 21

    return london or new_york

# =========================
# COOLDOWN FILTER
# =========================
def cooldown_active():
    global last_signal_time

    if last_signal_time is None:
        return False

    elapsed = (datetime.utcnow() - last_signal_time).total_seconds() / 60

    return elapsed < COOLDOWN_MINUTES

# =========================
# MAIN ANALYSIS
# =========================
def analyze_market():
    global last_signal_time

    trend_data = get_data("1h")
    structure_data = get_data("15min")
    entry_data = get_data("5min")

    if trend_data is None or structure_data is None or entry_data is None:
        return

    closes = entry_data["close"]
    highs = entry_data["high"]
    lows = entry_data["low"]
    opens = entry_data["open"]

    trend = trend_bias(trend_data["close"])

    rsi = calculate_rsi(closes)
    atr = calculate_atr(highs, lows, closes)

    current_price = closes[-1]

    print("====================")
    print("INSTITUTIONAL SMC PRECISION BOT V4 LITE")
    print("====================")
    print(f"Price: {current_price}")
    print(f"Trend: {trend}")
    print(f"RSI: {round(rsi, 2)}")
    print(f"ATR: {round(atr, 2)}")

    if cooldown_active():
        print("Cooldown active")
        return

    if not valid_session():
        print("Outside trading session")
        return

    if atr < 2.0:
        print("Low volatility")
        return

    # =========================
    # BUY CONDITIONS
    # =========================
    buy_signal = (
        trend == "BULLISH"
        and bullish_bos(structure_data["high"], structure_data["close"])
        and liquidity_sweep_buy(lows, opens, closes)
        and rsi > 50
        and strong_bullish_candle(opens, highs, closes)
    )

    # =========================
    # SELL CONDITIONS
    # =========================
    sell_signal = (
        trend == "BEARISH"
        and bearish_bos(structure_data["low"], structure_data["close"])
        and liquidity_sweep_sell(highs, opens, closes)
        and rsi < 50
        and strong_bearish_candle(opens, lows, closes)
    )

    # =========================
    # BUY EXECUTION
    # =========================
    if buy_signal:
        entry = current_price
        tp = round(entry + TP_POINTS, 2)
        sl = round(entry - SL_POINTS, 2)

        message = (
            f"BUY SIGNAL\n\n"
            f"Entry: {entry}\n"
            f"Take Profit: {tp}\n"
            f"Stop Loss: {sl}\n"
            f"Trend: Bullish\n"
            f"Institutional Setup Confirmed"
        )

        print(message)
        send_telegram(message)

        last_signal_time = datetime.utcnow()

    # =========================
    # SELL EXECUTION
    # =========================
    elif sell_signal:
        entry = current_price
        tp = round(entry - TP_POINTS, 2)
        sl = round(entry + SL_POINTS, 2)

        message = (
            f"SELL SIGNAL\n\n"
            f"Entry: {entry}\n"
            f"Take Profit: {tp}\n"
            f"Stop Loss: {sl}\n"
            f"Trend: Bearish\n"
            f"Institutional Setup Confirmed"
        )

        print(message)
        send_telegram(message)

        last_signal_time = datetime.utcnow()

    else:
        print("No valid institutional setup")

# =========================
# BOT LOOP
# =========================
while True:
    try:
        analyze_market()

    except Exception as e:
        print("ERROR:", e)

    print("Waiting 5 minutes...")
    time.sleep(300)