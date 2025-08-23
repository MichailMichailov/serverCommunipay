from django.core.management.base import BaseCommand
from telegram.ext import Application, CommandHandler

TOKEN = "..."

async def start(update, context): await update.message.reply_text("Привет!")

class Command(BaseCommand):
    help = "Run telegram bot (webhook-independent dev mode)"
    def handle(self, *args, **opts):
        app = Application.builder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.run_polling()
