from telegram import Bot, BotCommand
from telegram.ext import Application
from conf import TOKEN, url
async def set_menu_button():
    bot = Bot(TOKEN)
    await bot.set_chat_menu_button(
        menu_button={
            "type": "web_app",
            "text": "Открыть Mini App",
            "web_app": {"url": url}
        }
    )

if __name__ == "__main__":
    print("start")
    application = Application.builder().token(TOKEN).build()
    application.run_polling()
