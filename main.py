from flask import Flask, request, jsonify
from datetime import datetime
import random
import numpy as np
import pandas as pd

app = Flask(__name__)

# === Simulated Candle Fetch (to be replaced with real Pocket Option scraper) ===
def get_latest_candles(pair="EURUSD", timeframe="1m", limit=20):
    # Simulate OHLC candles: [open, high, low, close]
    closes = np.linspace(1.0, 1.1, limit) + np.random.normal(0, 0.001, limit)
    highs = closes + 0.001
    lows = closes - 0.001
    opens = closes - np.random.normal(0, 0.0005, limit)
    
    df = pd.DataFrame({
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes
    })
    return df

# === Indicator Calculation ===
def analyze_signals(df):
    df['ema_fast'] = df['close'].ewm(span=5).mean()
    df['ema_slow'] = df['close'].ewm(span=10).mean()
    df['rsi'] = compute_rsi(df['close'], 14)
    df['macd'] = df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()

    # Use last (closed) candle only
    last = df.iloc[-1]
    prev = df.iloc[-2]

    signal = "WAIT"
    reason = []
    confidence = 50

    # EMA crossover
    if prev['ema_fast'] < prev['ema_slow'] and last['ema_fast'] > last['ema_slow']:
        signal = "BUY"
        reason.append("EMA crossover up")
        confidence += 20
    elif prev['ema_fast'] > prev['ema_slow'] and last['ema_fast'] < last['ema_slow']:
        signal = "SELL"
        reason.append("EMA crossover down")
        confidence += 20

    # RSI
    if last['rsi'] < 30:
        signal = "BUY"
        reason.append("RSI < 30")
        confidence += 15
    elif last['rsi'] > 70:
        signal = "SELL"
        reason.append("RSI > 70")
        confidence += 15

    # MACD confirmation
    if last['macd'] > 0 and signal == "BUY":
        reason.append("MACD supports uptrend")
        confidence += 10
    elif last['macd'] < 0 and signal == "SELL":
        reason.append("MACD supports downtrend")
        confidence += 10

    if signal == "WAIT":
        confidence = 40
        reason.append("No strong signal yet")

    return signal, confidence, reason

# === RSI Function ===
def compute_rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ma_up = up.rolling(window=period).mean()
    ma_down = down.rolling(window=period).mean()
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))

# === Flask Endpoint ===
@app.route("/get-signal")
def get_signal():
    pair = request.args.get("pair", "EURUSD")
    timeframe = request.args.get("timeframe", "1m")
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    candles = get_latest_candles(pair, timeframe)
    signal, confidence, reasons = analyze_signals(candles)
    entry_price = round(candles.iloc[-1]['close'], 5)

    return jsonify({
        "pair": pair.replace("_", "/").upper(),
        "action": signal,
        "entry_price": f"${entry_price}",
        "expiration": timeframe,
        "confidence": f"{confidence}%",
        "risk_level": "LOW" if confidence >= 85 else "MEDIUM" if confidence >= 70 else "HIGH",
        "analysis": ", ".join(reasons),
        "valid_for": "Next 1–2 candles",
        "timestamp": now
    })

# === Run App ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)