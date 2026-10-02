from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import database as db
import keyboards as kb
import matching
from states import ORDER_DIRECTION, ORDER_PCOUNT, ORDER_PHONE, ORDER_COMMENT


async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ⚠️ VAQTINCHA O'CHIRILGAN: "bitta mijoz - bitta faol zakaz" cheklovi.
    # Qayta yoqish uchun quyidagi blokni izohdan chiqaring:
    #
    # existing = await db.get_active_order_for_client(update.effective_user.id)
    # if existing:
    #     if existing["status"] == "kutilmoqda":
    #         await update.message.reply_text(
    #             "❗️Sizda allaqachon faol zakaz bor va u mashina kutmoqda.\n"
    #             "Yangi zakaz berish uchun avval eskisini bekor qiling.",
    #             reply_markup=kb.order_waiting_kb(),
    #         )
    #     else:
    #         driver = await db.get_user(existing["driver_id"])
    #         await update.message.reply_text(
    #             "❗️Sizda allaqachon faol zakaz bor.\n\n"
    #             f"👤 Haydovchi: {driver['full_name']}\n"
    #             f"🚗 Mashina: {driver['car_info']}\n\n"
    #             "Yangi zakaz berish uchun avval eskisini bekor qiling.",
    #             reply_markup=kb.order_waiting_kb(),
    #         )
    #     return ConversationHandler.END

    directions = await db.list_directions()
    if not directions:
        await update.message.reply_text("Hozircha yo'nalishlar mavjud emas.")
        return ConversationHandler.END

    await update.message.reply_text("📍 Yo'nalishni tanlang:", reply_markup=kb.directions_kb(directions, "order_dir"))
    return ORDER_DIRECTION


async def choose_direction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    direction_id = int(query.data.split(":")[1])
    context.user_data["direction_id"] = direction_id
    await query.edit_message_text("👥 Necha kishi ketasiz?")
    await context.bot.send_message(
        chat_id=update.effective_user.id, text="Sonini tanlang:", reply_markup=kb.passenger_count_kb()
    )
    return ORDER_PCOUNT


async def choose_passenger_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    count = int(query.data.split(":")[1])
    context.user_data["passenger_count"] = count
    await query.edit_message_text(f"👥 {count} kishi tanlandi.")
    await context.bot.send_message(
        chat_id=update.effective_user.id,
        text="📱 Endi telefon raqamingizni yuboring:",
        reply_markup=kb.phone_request_kb(),
    )
    return ORDER_PHONE


async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("direction_id") is None or context.user_data.get("passenger_count") is None:
        await update.message.reply_text("Xatolik yuz berdi, iltimos qaytadan boshlang.")
        return ConversationHandler.END

    context.user_data["phone"] = update.message.contact.phone_number
    await update.message.reply_text(
        "💬 Izoh qoldirmoqchimisiz? (masalan: \"pochta ham bor\", \"2-kirish oldida kutib turaman\")\n"
        "Bo'lmasa, pastdagi tugmani bosing.",
        reply_markup=kb.comment_skip_kb(),
    )
    return ORDER_COMMENT


async def _finalize_order(update: Update, context: ContextTypes.DEFAULT_TYPE, comment: str | None):
    direction_id = context.user_data.get("direction_id")
    passenger_count = context.user_data.get("passenger_count")
    phone = context.user_data.get("phone")

    order_id = await db.create_order(update.effective_user.id, direction_id, phone, passenger_count, comment)
    context.user_data.clear()

    user = await db.get_or_create_user(update.effective_user.id, update.effective_user.full_name)
    await update.message.reply_text(
        f"✅ Zakazingiz qabul qilindi (№{order_id}).\n🚖 Mashina kutilmoqda...",
        reply_markup=kb.main_menu(user["role"] == "driver"),
    )
    await update.message.reply_text("Zakaz holati:", reply_markup=kb.order_waiting_kb())

    await matching.new_order_created(context, order_id, direction_id)
    return ConversationHandler.END


async def skip_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _finalize_order(update, context, None)


async def receive_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _finalize_order(update, context, update.message.text)


async def wrong_phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Iltimos, pastdagi tugma orqali telefon raqamingizni yuboring 📱")
    return ORDER_PHONE


async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    order = await db.get_active_order_for_client(query.from_user.id)
    if not order:
        await query.answer("Faol zakaz topilmadi.", show_alert=True)
        return

    await matching.passenger_cancels_order(context, order)

    await query.edit_message_text("❌ Zakaz bekor qilindi.")
    await query.answer("Bekor qilindi")
