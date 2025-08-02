from flask import Flask, request, jsonify
from datetime import datetime
import pandas as pd
import numpy as np
import requests

app = Flask(__name__)

API_KEY = "0a25bcb593e047b2aded75b1db91b130"

# === Fetch real-time candles from TwelveData ===
def get_latest_candles(pair="EUR/USD", timeframe="1min", limit=50):
    url = f"https://api.twelvedata.com/time_series"
    params = {
        "symbol": pair.upper().replace("_", "/"),
        "interval": timeframe,
        "outputsize": limit,
        "apikey": API_KEY
    }
    r = requests.get(url, params=params)
    data = r.json()

    if "values" not in data:
        raise Exception(f"TwelveData Error: {data.get('message', 'No data')}")

    df = pd.DataFrame(data["values"])
    df = df.rename(columns={"open": "open", "high": "high", "low": "low", "close": "close"})

    # Convert only OHLC columns to float
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)

    df = df[::-1]  # Reverse to chronological order
    return df.reset_index(drop=True)

# === RSI Calculation ===
def compute_rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ma_up = up.rolling(window=period).mean()
    ma_down = down.rolling(window=period).mean()
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))

# === Signal Logic ===
def analyze_signals(df):
    df['ema_fast'] = df['close'].ewm(span=5).mean()
    df['ema_slow'] = df['close'].ewm(span=10).mean()
    df['rsi'] = compute_rsi(df['close'], 14)
    df['macd'] = df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()

    last = df.iloc[-1]
    prev = df.iloc[-2]

    signal = "WAIT"
    reason = []
    confidence = 50

    if prev['ema_fast'] < prev['ema_slow'] and last['ema_fast'] > last['ema_slow']:
        signal = "BUY"
        reason.append("EMA crossover up")
        confidence += 20
    elif prev['ema_fast'] > prev['ema_slow'] and last['ema_fast'] < last['ema_slow']:
        signal = "SELL"
        reason.append("EMA crossover down")
        confidence += 20

    if last['rsi'] < 30:
        signal = "BUY"
        reason.append("RSI < 30 (oversold)")
        confidence += 15
    elif last['rsi'] > 70:
        signal = "SELL"
        reason.append("RSI > 70 (overbought)")
        confidence += 15

    if last['macd'] > 0 and signal == "BUY":
        reason.append("MACD supports uptrend")
        confidence += 10
    elif last['macd'] < 0 and signal == "SELL":
        reason.append("MACD supports downtrend")
        confidence += 10

    if signal == "WAIT":
        confidence = 40
        reason.append("No strong signal yet")

    return signal, confidence, reason, last['close']

# === API Endpoint ===
@app.route("/get-signal")
def get_signal():
    pair = request.args.get("pair", "EUR/USD").replace("_", "/")
    tf = request.args.get("timeframe", "1m")
    tf_map = {
        "30s": "1min",
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
        "4h": "4h"
    }
    timeframe = tf_map.get(tf, "1min")

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    try:
        candles = get_latest_candles(pair, timeframe)
        signal, confidence, reasons, close_price = analyze_signals(candles)

        return jsonify({
            "pair": pair.upper(),
            "action": signal,
            "entry_price": f"${round(close_price, 5)}",
            "expiration": tf,
            "confidence": f"{confidence}%",
            "risk_level": "LOW" if confidence >= 85 else "MEDIUM" if confidence >= 70 else "HIGH",
            "analysis": ", ".join(reasons),
            "valid_for": "Next 1–2 candles",
            "timestamp": now
        })
    except Exception as e:
        return jsonify({"error": str(e)})

# === Run the server ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)