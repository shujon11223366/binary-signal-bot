import asyncio
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from flask import Flask, request, jsonify
from threading import Thread

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

app = Flask(__name__)

# === CONFIG ===
API_KEY = "0a25bcb593e047b2aded75b1db91b130"
BOT_TOKEN = "7925099120:AAEQ8njhIlRzy1hzD04PmjjK95_WsQ8Krp4"
API_BASE = "https://web-production-187f2.up.railway.app"
timeframes = ["30s", "1m", "5m", "15m", "30m", "1h", "4h"]
pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "BTC/USD", "ETH/USD"]

# === API ROUTE ===
@app.route("/get-signal")
def get_signal():
    pair = request.args.get("pair", "EUR/USD").replace("_", "/")
    tf = request.args.get("timeframe", "1m")
    tf_map = {
        "30s": "1min", "1m": "1min", "5m": "5min",
        "15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h"
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

# === INDICATORS ===
def get_latest_candles(pair, timeframe, limit=50):
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": pair,
        "interval": timeframe,
        "outputsize": limit,
        "apikey": API_KEY
    }
    r = requests.get(url, params=params).json()
    if "values" not in r:
        raise Exception(f"TwelveData Error: {r.get('message', 'Unknown error')}")
    df = pd.DataFrame(r["values"])
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)
    return df[::-1].reset_index(drop=True)

def compute_rsi(series, period=14):
    delta = series.diff()
    up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
    ma_up, ma_down = up.rolling(window=period).mean(), down.rolling(window=period).mean()
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))

def analyze_signals(df):
    df["ema_fast"] = df["close"].ewm(span=5).mean()
    df["ema_slow"] = df["close"].ewm(span=10).mean()
    df["rsi"] = compute_rsi(df["close"], 14)
    df["macd"] = df["close"].ewm(span=12).mean() - df["close"].ewm(span=26).mean()
    last = df.iloc[-1]
    signal = "BUY" if last["ema_fast"] > last["ema_slow"] else "SELL"
    reasons = [f"EMA crossover {'up' if signal == 'BUY' else 'down'}"]
    confidence = 60

    if signal == "BUY" and last["rsi"] < 35:
        reasons.append("RSI supports BUY")
        confidence += 15
    elif signal == "SELL" and last["rsi"] > 65:
        reasons.append("RSI supports SELL")
        confidence += 15

    if signal == "BUY" and last["macd"] > 0:
        reasons.append("MACD supports BUY")
        confidence += 10
    elif signal == "SELL" and last["macd"] < 0:
        reasons.append("MACD supports SELL")
        confidence += 10

    return signal, min(confidence, 95), reasons, last["close"]

# === TELEGRAM BOT ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(tf, callback_data=f"tf:{tf}") for tf in timeframes[:3]],
                [InlineKeyboardButton(tf, callback_data=f"tf:{tf}") for tf in timeframes[3:]]]
    await update.message.reply_text("🕐 Choose a timeframe:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_timeframe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tf = query.data.split(":")[1]
    context.user_data["timeframe"] = tf
    keyboard = [[InlineKeyboardButton(p, callback_data=f"pair:{p}") for p in pairs[i:i+2]] for i in range(0, len(pairs), 2)]
    await query.edit_message_text(f"✅ Timeframe: {tf}\n💱 Choose a pair:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_pair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pair = query.data.split(":")[1]
    tf = context.user_data.get("timeframe", "1m")
    res = requests.get(f"{API_BASE}/get-signal?pair={pair}&timeframe={tf}").json()

    if "error" in res:
        await query.edit_message_text(f"❌ Error: {res['error']}")
        return

    icon = "🟢" if res['action'] == "BUY" else "🔴"
    msg = (
        f"{icon} *{res['action']} SIGNAL*\n"
        f"💱 Pair: `{res['pair']}`\n"
        f"📈 Entry: `{res['entry_price']}`\n"
        f"⏱ Expiry: `{res['expiration']}`\n"
        f"📊 Confidence: `{res['confidence']}`\n"
        f"⚠ Risk: `{res['risk_level']}`\n"
        f"🧠 Reason: _{res['analysis']}_\n"
        f"🕓 Time: `{res['timestamp']}`\n"
        f"⏳ Valid: {res['valid_for']}"
    )
    keyboard = [[InlineKeyboardButton("🔄 Get New Signal", callback_data="restart")]]
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# === ASYNC START ===
async def run_bot():
    logging.basicConfig(level=logging.INFO)
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_timeframe, pattern="^tf:"))
    app.add_handler(CallbackQueryHandler(handle_pair, pattern="^pair:"))
    app.add_handler(CallbackQueryHandler(restart, pattern="^restart$"))
    await app.run_polling()

# === LAUNCH ===
if __name__ == "__main__":
    Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()
    asyncio.run(run_bot())