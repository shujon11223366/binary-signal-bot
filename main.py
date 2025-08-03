import asyncio
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from multiprocessing import Process
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    CallbackQueryHandler, 
    ContextTypes
)

# Initialize Flask App
app = Flask(__name__)

# ======================
#      CONFIGURATION
# ======================
API_KEY = "0a25bcb593e047b2aded75b1db91b130"  # TwelveData API Key
BOT_TOKEN = "7925099120:AAEQ8njhIlRzy1hzD04PmjjK95_WsQ8Krp4"  # Telegram Bot Token
API_BASE = "https://web-production-187f2.up.railway.app"  # Your Railway App URL

TIMEFRAMES = ["30s", "1m", "5m", "15m", "30m", "1h", "4h"]
PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "BTC/USD", "ETH/USD"]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ======================
#      FLASK ROUTES
# ======================
@app.route("/get-signal")
def get_signal():
    """API endpoint to generate trading signals"""
    try:
        pair = request.args.get("pair", "EUR/USD").replace("_", "/")
        tf = request.args.get("timeframe", "1m")
        
        # Timezone-aware timestamp
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        candles = get_latest_candles(pair, tf)
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
        logger.error(f"Error in get_signal: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/favicon.ico')
def favicon():
    return '', 404

# ======================
#  TECHNICAL ANALYSIS
# ======================
def get_latest_candles(pair: str, timeframe: str, limit: int = 50) -> pd.DataFrame:
    """Fetch candle data from TwelveData API"""
    try:
        tf_map = {
            "30s": "1min", "1m": "1min", "5m": "5min",
            "15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h"
        }
        interval = tf_map.get(timeframe, "1min")
        
        params = {
            "symbol": pair,
            "interval": interval,
            "outputsize": limit,
            "apikey": API_KEY
        }
        
        response = requests.get(
            "https://api.twelvedata.com/time_series",
            params=params,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        if "values" not in data:
            raise ValueError(f"API Error: {data.get('message', 'No candle data')}")
            
        df = pd.DataFrame(data["values"])
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype(float)
            
        return df[::-1].reset_index(drop=True)
        
    except Exception as e:
        logger.error(f"Error fetching candles: {str(e)}")
        raise

def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index"""
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    
    ma_up = up.rolling(window=period).mean()
    ma_down = down.rolling(window=period).mean()
    
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))

def analyze_signals(df: pd.DataFrame) -> tuple:
    """Generate trading signals based on technical indicators"""
    try:
        # Calculate indicators
        df["ema_fast"] = df["close"].ewm(span=5).mean()
        df["ema_slow"] = df["close"].ewm(span=10).mean()
        df["rsi"] = compute_rsi(df["close"], 14)
        df["macd"] = df["close"].ewm(span=12).mean() - df["close"].ewm(span=26).mean()
        
        last = df.iloc[-1]
        signal = "BUY" if last["ema_fast"] > last["ema_slow"] else "SELL"
        reasons = [f"EMA crossover {'up' if signal == 'BUY' else 'down'}"]
        confidence = 60

        # RSI confirmation
        if signal == "BUY" and last["rsi"] < 35:
            reasons.append("RSI supports BUY")
            confidence += 15
        elif signal == "SELL" and last["rsi"] > 65:
            reasons.append("RSI supports SELL")
            confidence += 15

        # MACD confirmation
        if signal == "BUY" and last["macd"] > 0:
            reasons.append("MACD supports BUY")
            confidence += 10
        elif signal == "SELL" and last["macd"] < 0:
            reasons.append("MACD supports SELL")
            confidence += 10

        return signal, min(confidence, 95), reasons, last["close"]
        
    except Exception as e:
        logger.error(f"Error in analyze_signals: {str(e)}")
        raise

# ======================
#   TELEGRAM BOT
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    try:
        keyboard = [
            [InlineKeyboardButton(tf, callback_data=f"tf:{tf}") for tf in TIMEFRAMES[:3]],
            [InlineKeyboardButton(tf, callback_data=f"tf:{tf}") for tf in TIMEFRAMES[3:]]
        ]
        await update.message.reply_text(
            "🕐 Choose a timeframe:", 
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Error in start handler: {str(e)}")
        raise

async def handle_timeframe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle timeframe selection"""
    try:
        query = update.callback_query
        await query.answer()
        tf = query.data.split(":")[1]
        context.user_data["timeframe"] = tf
        
        keyboard = [
            [InlineKeyboardButton(p, callback_data=f"pair:{p}") for p in PAIRS[i:i+2]] 
            for i in range(0, len(PAIRS), 2)
        ]
        
        await query.edit_message_text(
            f"✅ Timeframe: {tf}\n💱 Choose a pair:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Error in timeframe handler: {str(e)}")
        await query.edit_message_text("❌ Error processing your request")

async def handle_pair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pair selection and display signal"""
    try:
        query = update.callback_query
        await query.answer()
        pair = query.data.split(":")[1]
        tf = context.user_data.get("timeframe", "1m")
        
        res = requests.get(
            f"{API_BASE}/get-signal?pair={pair.replace('/', '_')}&timeframe={tf}",
            timeout=10
        ).json()

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
        await query.edit_message_text(
            msg, 
            parse_mode="Markdown", 
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Error in pair handler: {str(e)}")
        await query.edit_message_text("❌ Failed to fetch signal")

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restart the conversation"""
    await start(update, context)

async def run_bot():
    """Start the Telegram bot"""
    try:
        application = ApplicationBuilder().token(BOT_TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(handle_timeframe, pattern="^tf:"))
        application.add_handler(CallbackQueryHandler(handle_pair, pattern="^pair:"))
        application.add_handler(CallbackQueryHandler(restart, pattern="^restart$"))
        
        logger.info("Starting bot polling...")
        await application.run_polling()
    except Exception as e:
        logger.error(f"Bot crashed: {str(e)}")
        raise

# ======================
#      ENTRY POINT
# ======================
if __name__ == "__main__":
    try:
        # Start Flask API in a separate process
        api_process = Process(target=app.run, kwargs={
            'host': '0.0.0.0',
            'port': 8080,
            'debug': False
        })
        api_process.start()
        
        # Start Telegram Bot
        asyncio.run(run_bot())
        
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        api_process.terminate()
    except Exception as e:
        logger.error(f"Main process error: {str(e)}")
        api_process.terminate()