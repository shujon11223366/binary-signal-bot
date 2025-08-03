import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

BOT_TOKEN = "7925099120:AAEQ8njhIlRzy1hzD04PmjjK95_WsQ8Krp4"
API_BASE = "https://web-production-f901.up.railway.app"

timeframes = ["30s", "1m", "5m", "15m", "30m", "1h", "4h"]
pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "BTC/USD", "ETH/USD", "EUR/JPY", "OTC/USD"]

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
    await query.edit_message_text(f"✅ Timeframe: {tf}\n\n💱 Choose a trading pair:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_pair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pair = query.data.split(":")[1]
    tf = context.user_data.get("timeframe", "1m")

    try:
        res = requests.get(f"{API_BASE}/get-signal?pair={pair}&timeframe={tf}").json()
    except Exception as e:
        await query.edit_message_text(f"⚠ Error fetching signal: {str(e)}")
        return

    if "error" in res:
        await query.edit_message_text(f"❌ API Error: {res['error']}")
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
    keyboard = [[InlineKeyboardButton("🔄 Get Another Signal", callback_data="restart")]]
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# ✅ Proper async-safe main() with no asyncio.run()
async def main():
    logging.basicConfig(level=logging.INFO)
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_timeframe, pattern="^tf:"))
    app.add_handler(CallbackQueryHandler(handle_pair, pattern="^pair:"))
    app.add_handler(CallbackQueryHandler(restart, pattern="^restart$"))
    print("🤖 Bot is running...")
    await app.run_polling()

# ✅ Detect if inside Railway and run without crashing
import asyncio
asyncio.get_event_loop().create_task(main())
asyncio.get_event_loop().run_forever()