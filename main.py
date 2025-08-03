from flask import Flask, request, jsonify
from datetime import datetime
import pandas as pd
import numpy as np
import requests

app = Flask(__name__)

API_KEY = "0a25bcb593e047b2aded75b1db91b130"

# === Get real-time candle data ===
def get_latest_candles(pair="EUR/USD", timeframe="1min", limit=50):
    url = "https://api.twelvedata.com/time_series"
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

    # Only convert OHLC to float
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)

    df = df[::-1]  # Reverse to chronological order
    return df.reset_index(drop=True)

# === RSI ===
def compute_rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ma_up = up.rolling(window=period).mean()
    ma_down = down.rolling(window=period).mean()
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))

# === Signal analysis ===
def analyze_signals(df):
    df['ema_fast'] = df['close'].ewm(span=5).mean()
    df['ema_slow'] = df['close'].ewm(span=10).mean()
    df['rsi'] = compute_rsi(df['close'], 14)
    df['macd'] = df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Always return BUY or SELL based on EMA crossover
    signal = "BUY" if last['ema_fast'] > last['ema_slow'] else "SELL"
    reason = [f"EMA crossover {'up' if signal == 'BUY' else 'down'}"]
    confidence = 60  # base confidence

    if signal == "BUY" and last['rsi'] < 35:
        reason.append("RSI supports BUY")
        confidence += 15
    elif signal == "SELL" and last['rsi'] > 65:
        reason.append("RSI supports SELL")
        confidence += 15

    if signal == "BUY" and last['macd'] > 0:
        reason.append("MACD supports BUY")
        confidence += 10
    elif signal == "SELL" and last['macd'] < 0:
        reason.append("MACD supports SELL")
        confidence += 10

    confidence = min(max(confidence, 40), 95)

    return signal, confidence, reason, last['close']

# === API route ===
@app.route("/get-signal")
def get_signal():
    pair = request.args.get("pair", "EUR/USD").replace("_", "/")
    tf = request.args.get("timeframe", "1m")
    tf_map = {
        "30s": "1min",  # fallback
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

# === Run server on port 8080 for Railway ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)