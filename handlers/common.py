from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import database as db
import keyboards as kb
from config import ADMIN_IDS


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user = await db.get_or_create_user(update.effective_user.id, update.effective_user.full_name)

    if update.effective_user.id in ADMIN_IDS and user["role"] != "admin":
        await db.update_user(update.effective_user.id, role="admin")
        user["role"] = "admin"

    is_admin = user["role"] == "admin"
    is_driver = user["role"] == "driver"

    greeting = "Assalomu alaykum, Admin! 👋" if is_admin else "🚕 O'qchi-Yaypan taxi botiga xush kelibsiz!"
    await update.message.reply_text(
        f"{greeting}\n\nQuyidagilardan birini tanlang:",
        reply_markup=kb.main_menu(is_driver, is_admin),
    )


async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user = await db.get_or_create_user(update.effective_user.id, update.effective_user.full_name)
    is_admin = user["role"] == "admin"
    is_driver = user["role"] == "driver"
    await update.message.reply_text("Asosiy menyu:", reply_markup=kb.main_menu(is_driver, is_admin))
    return ConversationHandler.END


async def cancel_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user = await db.get_or_create_user(update.effective_user.id, update.effective_user.full_name)
    is_admin = user["role"] == "admin"
    is_driver = user["role"] == "driver"
    await update.message.reply_text("Bekor qilindi.", reply_markup=kb.main_menu(is_driver, is_admin))
    return ConversationHandler.END
