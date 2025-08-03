import asyncio
import logging
import requests
import pandas as pd
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    CallbackQueryHandler, 
    ContextTypes
)

# ===== Configuration =====
API_KEY = "0a25bcb593e047b2aded75b1db91b130"  # Replace with your TwelveData API key
BOT_TOKEN = "7925099120:AAEQ8njhIlRzy1hzD04PmjjK95_WsQ8Krp4"  # Your Telegram bot token

TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h"]
PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "BTC/USD", "ETH/USD"]

# ===== Setup Logging =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===== Technical Analysis =====
def get_candles(pair: str, tf: str, limit=50) -> pd.DataFrame:
    """Fetch candle data from TwelveData API"""
    tf_map = {
        "1m": "1min", "5m": "5min", "15m": "15min",
        "30m": "30min", "1h": "1h", "4h": "4h"
    }
    
    try:
        response = requests.get(
            "https://api.twelvedata.com/time_series",
            params={
                "symbol": pair,
                "interval": tf_map.get(tf, "1min"),
                "outputsize": limit,
                "apikey": API_KEY
            },
            timeout=10
        )
        data = response.json()
        
        if "values" not in data:
            raise ValueError(data.get("message", "No candle data available"))
            
        df = pd.DataFrame(data["values"])
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype(float)
            
        return df.iloc[::-1].reset_index(drop=True)
        
    except Exception as e:
        logger.error(f"Candle fetch error: {e}")
        raise

def generate_signal(df: pd.DataFrame) -> dict:
    """Generate trading signal with analysis"""
    df["ema_fast"] = df["close"].ewm(span=5).mean()
    df["ema_slow"] = df["close"].ewm(span=10).mean()
    df["rsi"] = 100 - (100 / (1 + (df["close"].diff().clip(lower=0).rolling(14).mean() / 
                       (-df["close"].diff().clip(upper=0).rolling(14).mean()))
    df["macd"] = df["close"].ewm(span=12).mean() - df["close"].ewm(span=26).mean()
    
    last = df.iloc[-1]
    signal = "BUY" if last["ema_fast"] > last["ema_slow"] else "SELL"
    
    reasons = []
    confidence = 60
    
    # RSI Logic
    if (signal == "BUY" and last["rsi"] < 35) or (signal == "SELL" and last["rsi"] > 65):
        reasons.append(f"RSI {round(last['rsi'], 1)}")
        confidence += 15
    
    # MACD Logic
    if (signal == "BUY" and last["macd"] > 0) or (signal == "SELL" and last["macd"] < 0):
        reasons.append("MACD confirm")
        confidence += 10
    
    return {
        "action": signal,
        "price": round(last["close"], 5),
        "confidence": min(confidence, 95),
        "reasons": reasons
    }

# ===== Telegram Bot Handlers =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send timeframe selection menu"""
    keyboard = [
        [InlineKeyboardButton(tf, callback_data=f"tf_{tf}") for tf in TIMEFRAMES[:3]],
        [InlineKeyboardButton(tf, callback_data=f"tf_{tf}") for tf in TIMEFRAMES[3:]]
    ]
    await update.message.reply_text(
        "📊 Select Timeframe:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_timeframe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle timeframe selection"""
    query = update.callback_query
    await query.answer()
    tf = query.data.split("_")[1]
    context.user_data["timeframe"] = tf
    
    keyboard = [
        [InlineKeyboardButton(pair, callback_data=f"pair_{pair}") for pair in PAIRS[i:i+2]]
        for i in range(0, len(PAIRS), 2)
    ]
    await query.edit_message_text(
        f"⏱ Timeframe: {tf}\n\n💹 Select Pair:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_pair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate and display signal"""
    query = update.callback_query
    await query.answer()
    
    pair = query.data.split("_")[1]
    tf = context.user_data.get("timeframe", "1m")
    
    try:
        candles = get_candles(pair, tf)
        signal = generate_signal(candles)
        
        message = (
            f"🚀 *{signal['action']} Signal* 🚀\n"
            f"• Pair: `{pair}`\n"
            f"• Timeframe: `{tf}`\n"
            f"• Entry: `{signal['price']}`\n"
            f"• Confidence: `{signal['confidence']}%`\n"
            f"• Signals: {', '.join(signal['reasons'])}\n"
            f"• Time: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}`\n\n"
            f"_Valid for next 1-2 candles_"
        )
        
        keyboard = [[InlineKeyboardButton("🔄 New Signal", callback_data="restart")]]
        await query.edit_message_text(
            message,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard))
            
    except Exception as e:
        logger.error(f"Signal error: {e}")
        await query.edit_message_text("⚠ Error generating signal. Try again later.")

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restart the conversation"""
    await start(update, context)

# ===== Bot Setup =====
def run_bot():
    """Configure and start the bot"""
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_timeframe, pattern="^tf_"))
    application.add_handler(CallbackQueryHandler(handle_pair, pattern="^pair_"))
    application.add_handler(CallbackQueryHandler(restart, pattern="^restart$"))
    
    logger.info("Starting bot...")
    application.run_polling()

if __name__ == "__main__":
    run_bot()