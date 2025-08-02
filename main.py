from flask import Flask, request, jsonify
from datetime import datetime
import pandas as pd
import numpy as np
import requests
import time

app = Flask(__name__)

# === Get candles from TradingView (used by Pocket Option) ===
def get_latest_candles(pair="EURUSD", timeframe="1", limit=50):
    pair = pair.upper().replace("/", "")
    symbol = f"FX:{pair}" if "OTC" not in pair else f"PO:{pair.replace('OTC', '')}"

    resolution = {
        "30s": "0.5",
        "1m": "1",
        "5m": "5",
        "15m": "15",
        "30m": "30",
        "1h": "60",
        "4h": "240"
    }.get(timeframe, "1")

    url = "https://scanner.tradingview.com/america/scan"
    payload = {
        "symbols": {"tickers": [symbol], "query": {"types": []}},
        "columns": ["close", f"high", f"low", f"open"]
    }

    candles_url = f"https://tvc4.forexpros.com/{int(time.time())}/4/1/8/history?symbol={symbol}&resolution={resolution}&from={int(time.time()) - 60 * 100}&to={int(time.time())}"

    r = requests.get(candles_url)
    if r.status_code != 200:
        raise Exception("Failed to fetch candles")
    data = r.json()

    if "c" not in data:
        raise Exception("No candle data")

    df = pd.DataFrame({
        "open": data["o"],
        "high": data["h"],
        "low": data["l"],
        "close": data["c"]
    })

    return df.tail(limit)

# === RSI ===
def compute_rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ma_up = up.rolling(window=period).mean()
    ma_down = down.rolling(window=period).mean()
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))

# === Indicator Analysis ===
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
    pair = request.args.get("pair", "EURUSD")
    timeframe = request.args.get("timeframe", "1m")

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    try:
        candles = get_latest_candles(pair, timeframe)
        signal, confidence, reasons, close_price = analyze_signals(candles)

        return jsonify({
            "pair": pair.upper().replace("_", "/"),
            "action": signal,
            "entry_price": f"${round(close_price, 5)}",
            "expiration": timeframe,
            "confidence": f"{confidence}%",
            "risk_level": "LOW" if confidence >= 85 else "MEDIUM" if confidence >= 70 else "HIGH",
            "analysis": ", ".join(reasons),
            "valid_for": "Next 1–2 candles",
            "timestamp": now
        })
    except Exception as e:
        return jsonify({"error": str(e)})

# === Run App ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)