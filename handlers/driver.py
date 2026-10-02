from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import database as db
import keyboards as kb
import matching
from states import (
    DRIVER_NAME,
    DRIVER_PHONE,
    DRIVER_CAR,
    DRIVER_ONLINE_DIRECTION,
    BALANCE_TOPUP_AMOUNT,
    BALANCE_TOPUP_SCREENSHOT,
)
from config import ADMIN_IDS, CAR_CAPACITY, TX_TYPE_LABELS, TX_STATUS_LABELS


# ---------------------------------------------------------------------------
# HAYDOVCHI BO'LISH (ariza)
# ---------------------------------------------------------------------------

async def start_application(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await db.get_user(update.effective_user.id)
    if user and user["role"] == "driver":
        await update.message.reply_text("Siz allaqachon haydovchisiz ✅")
        return ConversationHandler.END
    await update.message.reply_text("👤 Ism va familiyangizni yozing:", reply_markup=kb.cancel_kb())
    return DRIVER_NAME


async def app_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["full_name"] = update.message.text
    await update.message.reply_text("📱 Telefon raqamingizni yozing (masalan: +998901234567):")
    return DRIVER_PHONE


async def app_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = update.message.text
    await update.message.reply_text("🚗 Mashina rusumi va raqamini yozing (masalan: Cobalt oq, 01A123BC):")
    return DRIVER_CAR


async def app_car_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    car_info = update.message.text
    full_name = context.user_data.get("full_name")
    phone = context.user_data.get("phone")

    app_id = await db.create_driver_application(update.effective_user.id, full_name, phone, car_info)
    context.user_data.clear()

    await update.message.reply_text(
        "✅ Arizangiz qabul qilindi. Admin tasdiqlagach xabar beramiz.",
        reply_markup=kb.main_menu(False),
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text="📝 Yangi haydovchilik arizasi:\n\n"
                f"👤 {full_name}\n"
                f"📱 {phone}\n"
                f"🚗 {car_info}\n"
                f"🆔 {update.effective_user.id}",
                reply_markup=kb.application_actions_kb(app_id),
            )
        except Exception:
            pass
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# HAYDOVCHI PANELI
# ---------------------------------------------------------------------------

async def driver_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await db.get_user(update.effective_user.id)
    if not user or user["role"] != "driver":
        await update.message.reply_text("Siz haydovchi emassiz.")
        return
    if not user["is_enabled"]:
        await update.message.reply_text("❗️Sizning haydovchilik profilingiz vaqtincha nofaol qilingan.")
        return

    if user["driver_status"] == "busy":
        await update.message.reply_text("🚖 Siz hozir safardasiz.", reply_markup=kb.driver_busy_kb())
    elif user["driver_status"] == "online":
        seats = user["current_seats"]
        direction_id = await db.get_driver_direction(update.effective_user.id)
        position = await db.queue_position(update.effective_user.id, direction_id) if direction_id else None
        lines = ["Haydovchi paneli:"]
        if position:
            lines.append(f"🔢 Navbatdagi joyingiz: {position}-o'rin.")
        if seats > 0:
            lines.append(f"👥 Hozirda sizda: {seats}/{CAR_CAPACITY} kishi.")
        await update.message.reply_text("\n".join(lines), reply_markup=kb.driver_panel_kb(True, seats))
    else:
        await update.message.reply_text("Haydovchi paneli:", reply_markup=kb.driver_panel_kb(False))


async def go_online_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await db.get_user(update.effective_user.id)
    if not user or user["role"] != "driver" or not user["is_enabled"]:
        return ConversationHandler.END
    directions = await db.list_directions()
    await update.message.reply_text("📍 Qaysi yo'nalishga chiqasiz?", reply_markup=kb.directions_kb(directions, "drv_dir"))
    return DRIVER_ONLINE_DIRECTION


async def go_online_direction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    direction_id = int(query.data.split(":")[1])
    await matching.driver_goes_online(context, query.from_user.id, direction_id)
    direction = await db.get_direction(direction_id)
    await query.edit_message_text(f"🟢 Siz liniyaga chiqdingiz: {direction['name']}")
    await context.bot.send_message(chat_id=query.from_user.id, text="Haydovchi paneli:", reply_markup=kb.driver_panel_kb(True, 0))
    return ConversationHandler.END


async def go_offline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await db.get_user(update.effective_user.id)
    if not user or user["role"] != "driver":
        return
    await matching.driver_goes_offline(context, update.effective_user.id)
    await update.message.reply_text("🔴 Siz liniyadan chiqdingiz.", reply_markup=kb.driver_panel_kb(False))


# ---------------------------------------------------------------------------
# ZAKAZNI QABUL / RAD ETISH
# ---------------------------------------------------------------------------

async def driver_accept_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    order_id = int(query.data.split(":")[1])
    result = await matching.driver_accepts_order(context, query.from_user.id, order_id)
    if result == "ok":
        order = await db.get_order(order_id)
        driver = await db.get_user(query.from_user.id)
        order_fee = int(await db.get_setting("order_fee", "0") or "0") * order["passenger_count"]
        text = (
            f"✅ Siz №{order_id} zakazni qabul qildingiz.\n"
            f"📱 Yo'lovchi telefoni: {order['phone']}\n"
            f"👥 {order['passenger_count']} kishi"
        )
        if order.get("comment"):
            text += f"\n💬 Izoh: {order['comment']}"
        if order_fee > 0:
            text += f"\n💰 Balansdan {order_fee:,} so'm yechildi. Joriy balans: {driver['balance']:,} so'm.".replace(",", " ")
        await query.edit_message_text(text)
    elif result == "no_capacity":
        await query.edit_message_text("⚠️ Ushbu zakaz endi sig'maydi (joy yetarli emas). Boshqa zakazlarni kuting.")
    elif result == "no_balance":
        await query.edit_message_text(
            "⚠️ Balansingizda mablag' yetarli emas. Iltimos, avval balansni to'ldiring "
            "(💰 Balans → ➕ Balansni to'ldirish)."
        )
    else:
        await query.edit_message_text("❗️Bu zakaz allaqachon boshqa haydovchiga tegishli yoki bekor qilingan.")
    await query.answer()


async def driver_reject_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    order_id = int(query.data.split(":")[1])
    ok = await matching.driver_rejects_order(context, query.from_user.id, order_id)
    if ok:
        await query.edit_message_text(f"❌ №{order_id} zakazni rad etdingiz. U boshqa haydovchiga taklif qilinadi.")
    else:
        await query.edit_message_text("❗️Bu zakaz sizga endi tegishli emas.")
    await query.answer()


# ---------------------------------------------------------------------------
# FAOL ZAKAZLARIM
# ---------------------------------------------------------------------------

async def show_active_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await db.get_user(update.effective_user.id)
    if not user or user["role"] != "driver":
        return
    orders = await db.list_driver_active_orders(update.effective_user.id)
    if not orders:
        await update.message.reply_text("Hozircha faol zakazlaringiz yo'q.")
        return
    directions = {d["id"]: d["name"] for d in await db.list_directions()}
    for o in orders:
        text = (
            f"№{o['id']}\n"
            f"🕐 {matching.format_order_time(o['created_at'])}\n"
            f"📍 {directions.get(o['direction_id'])}\n"
            f"👥 {o['passenger_count']} kishi\n"
            f"📱 {o['phone']}"
        )
        if o.get("comment"):
            text += f"\n💬 {o['comment']}"
        await update.message.reply_text(text, reply_markup=kb.active_order_kb(o["id"]))


async def request_cancellation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    order_id = int(query.data.split(":")[1])
    ok = await matching.driver_requests_cancellation(context, query.from_user.id, order_id)
    if ok:
        await query.edit_message_text(query.message.text + "\n\n🚫 Bekor qilish so'rovi adminga yuborildi.")
        await query.answer("Yuborildi")
    else:
        await query.answer("Bu zakazni bekor qilib bo'lmaydi.", show_alert=True)
    await query.answer()


# ---------------------------------------------------------------------------
# JO'NASH VA SAFARNI YAKUNLASH
# ---------------------------------------------------------------------------

async def depart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await db.get_user(update.effective_user.id)
    if not user or user["role"] != "driver" or user["driver_status"] != "online":
        return
    ok = await matching.driver_departs(context, update.effective_user.id)
    if not ok:
        await update.message.reply_text("Avval kamida bitta zakaz qabul qiling.")
        return
    seats = (await db.get_user(update.effective_user.id))["current_seats"]
    await update.message.reply_text(
        f"🚀 Siz {seats} kishi bilan yo'lga chiqdingiz.", reply_markup=kb.driver_busy_kb()
    )


async def finish_trip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await db.get_user(update.effective_user.id)
    if not user or user["role"] != "driver" or user["driver_status"] != "busy":
        return
    await matching.driver_finishes_trip(context, update.effective_user.id)
    await update.message.reply_text(
        "🏁 Safar yakunlandi. Yana liniyaga chiqishingiz mumkin.",
        reply_markup=kb.driver_panel_kb(False),
    )


# ---------------------------------------------------------------------------
# BALANS
# ---------------------------------------------------------------------------

async def show_balance_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await db.get_user(update.effective_user.id)
    if not user or user["role"] != "driver":
        await update.message.reply_text("Siz haydovchi emassiz.")
        return
    await update.message.reply_text(
        f"💰 Balansingiz: {user['balance']:,} so'm".replace(",", " "),
        reply_markup=kb.balance_menu_kb(),
    )


async def start_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await db.get_user(update.effective_user.id)
    if not user or user["role"] != "driver":
        return ConversationHandler.END
    await update.message.reply_text(
        "💵 To'ldirmoqchi bo'lgan summani kiriting (faqat raqam, so'mda):",
        reply_markup=kb.cancel_kb(),
    )
    return BALANCE_TOPUP_AMOUNT


async def topup_amount_invalid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Iltimos, faqat musbat butun son kiriting (masalan: 50000).")
    return BALANCE_TOPUP_AMOUNT


async def topup_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = int(update.message.text)
    if amount <= 0:
        return await topup_amount_invalid(update, context)
    context.user_data["topup_amount"] = amount

    card_number = await db.get_setting("payment_card_number")
    card_name = await db.get_setting("payment_card_name")
    if not card_number:
        await update.message.reply_text(
            "⚠️ Hozircha to'lov uchun karta ma'lumotlari sozlanmagan. Admin bilan bog'laning."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"💳 To'lovni quyidagi kartaga amalga oshiring:\n\n"
        f"Karta raqami: {card_number}\n"
        f"Ism familiya: {card_name}\n"
        f"Summa: {amount:,} so'm\n\n".replace(",", " ") +
        "To'lovni amalga oshirgach, chekning skrinshotini (rasm) shu yerga yuboring:",
        reply_markup=kb.cancel_kb(),
    )
    return BALANCE_TOPUP_SCREENSHOT


async def topup_screenshot_invalid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Iltimos, to'lov chekining skrinshotini rasm sifatida yuboring.")
    return BALANCE_TOPUP_SCREENSHOT


async def topup_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = context.user_data.get("topup_amount")
    if not amount:
        await update.message.reply_text("Xatolik yuz berdi, iltimos qaytadan boshlang.")
        return ConversationHandler.END

    file_id = update.message.photo[-1].file_id
    driver_id = update.effective_user.id
    user = await db.get_user(driver_id)

    tx_id = await db.create_transaction(
        driver_id, "topup_request", amount, status="pending", screenshot_file_id=file_id
    )
    context.user_data.clear()

    await update.message.reply_text(
        "✅ So'rovingiz adminga yuborildi. Tasdiqlangach balansingiz to'ladi.",
        reply_markup=kb.balance_menu_kb(),
    )

    caption = (
        f"💰 YANGI TO'LOV SO'ROVI (№{tx_id})\n\n"
        f"👤 {user['full_name']}\n"
        f"📱 {user['phone']}\n"
        f"🆔 {driver_id}\n"
        f"💵 Summa: {amount:,} so'm".replace(",", " ")
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_photo(
                chat_id=admin_id, photo=file_id, caption=caption, reply_markup=kb.topup_review_kb(tx_id)
            )
        except Exception:
            pass
    return ConversationHandler.END


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await db.get_user(update.effective_user.id)
    if not user or user["role"] != "driver":
        return
    txs = await db.list_driver_transactions(update.effective_user.id, limit=20)
    if not txs:
        await update.message.reply_text("Tranzaksiyalar tarixi bo'sh.")
        return
    lines = ["🧾 Oxirgi tranzaksiyalar:\n"]
    for tx in txs:
        label = TX_TYPE_LABELS.get(tx["type"], tx["type"])
        status = TX_STATUS_LABELS.get(tx["status"], tx["status"])
        sign = "+" if tx["amount"] >= 0 else ""
        time_str = matching.format_order_time(tx["created_at"])
        line = f"{time_str} — {label}: {sign}{tx['amount']:,} so'm — {status}".replace(",", " ")
        if tx.get("comment") and tx["type"] in ("admin_topup", "admin_withdraw"):
            line += f"\n   💬 {tx['comment']}"
        lines.append(line)
    await update.message.reply_text("\n".join(lines))
