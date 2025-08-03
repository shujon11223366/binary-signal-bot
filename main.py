from flask import Flask, request, jsonify
from datetime import datetime
import pandas as pd
import numpy as np
import requests
import threading
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# === Flask App ===
app = Flask(__name__)
API_KEY = "0a25bcb593e047b2aded75b1db91b130"

# === Bot Settings ===
BOT_TOKEN = "7925099120:AAEQ8njhIlRzy1hzD04PmjjK95_WsQ8Krp4"
API_BASE = "https://web-production-187f2.up.railway.app"
timeframes = ["30s", "1m", "5m", "15m", "30m", "1h", "4h"]
pairs = [
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD",
    "BTC/USD", "ETH/USD", "EUR/JPY", "GBP/JPY"
]

# === Candle Fetch ===
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
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)
    df = df[::-1]
    return df.reset_index(drop=True)

def compute_rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ma_up = up.rolling(window=period).mean()
    ma_down = down.rolling(window=period).mean()
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))

def analyze_signals(df):
    df['ema_fast'] = df['close'].ewm(span=5).mean()
    df['ema_slow'] = df['close'].ewm(span=10).mean()
    df['rsi'] = compute_rsi(df['close'], 14)
    df['macd'] = df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()
    last = df.iloc[-1]

    signal = "BUY" if last['ema_fast'] > last['ema_slow'] else "SELL"
    reason = [f"EMA crossover {'up' if signal == 'BUY' else 'down'}"]
    confidence = 60

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

# === Telegram Bot Logic ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(tf, callback_data=f"tf:{tf}") for tf in timeframes[:3]],
                [InlineKeyboardButton(tf, callback_data=f"tf:{tf}") for tf in timeframes[3:]]]
    await update.message.reply_text("🕐 Choose a timeframe:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_timeframe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tf = query.data.split(":")[1]
    context.user_data["timeframe"] = tf

    keyboard = []
    row = []
    for i, pair in enumerate(pairs):
        row.append(InlineKeyboardButton(pair, callback_data=f"pair:{pair}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    await query.edit_message_text(
        text=f"✅ Timeframe selected: {tf}\n\n💱 Now choose a trading pair:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_pair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pair = query.data.split(":")[1]
    tf = context.user_data.get("timeframe", "1m")

    url = f"{API_BASE}/get-signal?pair={pair}&timeframe={tf}"
    res = requests.get(url).json()

    if "error" in res:
        await query.edit_message_text(f"❌ Error: {res['error']}")
        return

    action = res['action']
    color = "🟢" if action == "BUY" else "🔴"
    msg = (
        f"{color} *{action} SIGNAL*\n"
        f"💱 Pair: `{res['pair']}`\n"
        f"📈 Entry: `{res['entry_price']}`\n"
        f"⏱ Expiration: `{res['expiration']}`\n"
        f"🔍 Confidence: `{res['confidence']}`\n"
        f"⚠️ Risk Level: `{res['risk_level']}`\n"
        f"🧠 Reason: _{res['analysis']}_\n"
        f"🕐 Time: `{res['timestamp']}`\n\n"
        f"⏳ Valid for: {res['valid_for']}"
    )

    keyboard = [[InlineKeyboardButton("🔄 Get Another Signal", callback_data="again")]]
    await query.edit_message_text(text=msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    return await start(update, context)

# === Start Telegram Bot Thread ===
def start_bot():
    logging.basicConfig(level=logging.INFO)
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_timeframe, pattern=r"^tf:"))
    app.add_handler(CallbackQueryHandler(handle_pair, pattern=r"^pair:"))
    app.add_handler(CallbackQueryHandler(handle_restart, pattern="^again$"))
    print("🤖 Telegram bot is running...")
    app.run_polling()

# === Main Entrypoint ===
if __name__ == "__main__":
    threading.Thread(target=start_bot).start()
    app.run(host="0.0.0.0", port=8080)