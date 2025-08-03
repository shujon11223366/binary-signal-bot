import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, CallbackContext
)

BOT_TOKEN = "7925099120:AAEQ8njhIlRzy1hzD04PmjjK95_WsQ8Krp4"
API_BASE = "https://web-production-f901.up.railway.app"

timeframes = ["30s", "1m", "5m", "15m", "30m", "1h", "4h"]
pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "BTC/USD", "ETH/USD", "EUR/JPY", "OTC/USD"]

def start(update: Update, context: CallbackContext):
    keyboard = [[InlineKeyboardButton(tf, callback_data=f"tf:{tf}") for tf in timeframes[:3]],
                [InlineKeyboardButton(tf, callback_data=f"tf:{tf}") for tf in timeframes[3:]]]
    update.message.reply_text("🕐 Choose a timeframe:", reply_markup=InlineKeyboardMarkup(keyboard))

def handle_timeframe(update: Update, context: CallbackContext):
    query = update.callback_query
    tf = query.data.split(":")[1]
    context.user_data["timeframe"] = tf
    keyboard = [[InlineKeyboardButton(p, callback_data=f"pair:{p}") for p in pairs[i:i+2]] for i in range(0, len(pairs), 2)]
    query.edit_message_text(f"✅ Timeframe: {tf}\n\n💱 Choose a trading pair:", reply_markup=InlineKeyboardMarkup(keyboard))

def handle_pair(update: Update, context: CallbackContext):
    query = update.callback_query
    pair = query.data.split(":")[1]
    tf = context.user_data.get("timeframe", "1m")

    try:
        res = requests.get(f"{API_BASE}/get-signal?pair={pair}&timeframe={tf}").json()
    except Exception as e:
        query.edit_message_text(f"⚠ Error fetching signal: {str(e)}")
        return

    if "error" in res:
        query.edit_message_text(f"❌ API Error: {res['error']}")
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
    query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

def restart(update: Update, context: CallbackContext):
    start(update, context)

def main():
    logging.basicConfig(level=logging.INFO)
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(handle_timeframe, pattern="^tf:"))
    dp.add_handler(CallbackQueryHandler(handle_pair, pattern="^pair:"))
    dp.add_handler(CallbackQueryHandler(restart, pattern="^restart$"))

    print("🤖 Bot is running...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()