import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext

TOKEN = os.getenv("BOT_TOKEN")

def start(update: Update, context: CallbackContext):
    buttons = [
        [InlineKeyboardButton("1m", callback_data="1m"),
         InlineKeyboardButton("5m", callback_data="5m")]
    ]
    update.message.reply_text(
        "⏳ Select Timeframe:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

def main():
    updater = Updater(TOKEN)
    updater.dispatcher.add_handler(CommandHandler('start', start))
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()