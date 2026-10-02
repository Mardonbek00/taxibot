from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import database as db
import keyboards as kb
import matching
from config import ADMIN_IDS, TX_TYPE_LABELS, TX_STATUS_LABELS
from states import (
    ADMIN_SET_FEE_AMOUNT,
    ADMIN_SET_CARD_NUMBER,
    ADMIN_SET_CARD_NAME,
    ADMIN_ADJUST_AMOUNT,
    ADMIN_ADJUST_COMMENT,
    BROADCAST_TARGET_NUMBER,
    BROADCAST_MESSAGE,
)


def is_admin(telegram_id: int) -> bool:
    return telegram_id in ADMIN_IDS


# ---------------------------------------------------------------------------
# ADMIN PANELGA KIRISH
# ---------------------------------------------------------------------------

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("👑 Admin panel:", reply_markup=kb.admin_menu())


# ---------------------------------------------------------------------------
# ARIZALAR
# ---------------------------------------------------------------------------

async def list_applications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "Yangi arizalar sizga alohida xabar sifatida kelib turadi va u yerda "
        "✅ Qabul qilish / ❌ Rad etish tugmalari bo'ladi."
    )


async def approve_application(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return
    app_id = int(query.data.split(":")[1])
    app = await db.get_application(app_id)
    if not app or app["status"] != "pending":
        await query.answer("Bu ariza allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    await db.set_application_status(app_id, "approved")
    await db.get_or_create_user(app["telegram_id"])
    await db.update_user(
        app["telegram_id"],
        role="driver",
        full_name=app["full_name"],
        phone=app["phone"],
        car_info=app["car_info"],
        driver_status="offline",
    )

    await query.edit_message_text(query.message.text + "\n\n✅ QABUL QILINDI")
    await query.answer("Qabul qilindi")
    try:
        await context.bot.send_message(
            chat_id=app["telegram_id"],
            text="🎉 Tabriklaymiz! Arizangiz tasdiqlandi, siz endi haydovchisiz.\n"
            "Asosiy menyudan 'Haydovchi paneli' bo'limiga kirishingiz mumkin.",
            reply_markup=kb.main_menu(True),
        )
    except Exception:
        pass


async def reject_application(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return
    app_id = int(query.data.split(":")[1])
    app = await db.get_application(app_id)
    if not app or app["status"] != "pending":
        await query.answer("Bu ariza allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    await db.set_application_status(app_id, "rejected")
    await query.edit_message_text(query.message.text + "\n\n❌ RAD ETILDI")
    await query.answer("Rad etildi")
    try:
        await context.bot.send_message(chat_id=app["telegram_id"], text="❌ Afsuski, haydovchilik arizangiz rad etildi.")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# FAOL ZAKAZLAR
# ---------------------------------------------------------------------------

async def list_active_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    orders = await db.list_active_orders()
    if not orders:
        await update.message.reply_text("Hozircha faol zakazlar yo'q.")
        return
    directions = {d["id"]: d["name"] for d in await db.list_directions()}
    for o in orders:
        status_text = "⏳ Kutilmoqda" if o["status"] == "kutilmoqda" else "✅ Tasdiqlangan"
        text = (
            f"№{o['id']} • {status_text}\n"
            f"🕐 {matching.format_order_time(o['created_at'])}\n"
            f"📍 {directions.get(o['direction_id'])}\n"
            f"👥 {o['passenger_count']} kishi\n"
            f"📱 {o['phone']}"
        )
        if o.get("comment"):
            text += f"\n💬 {o['comment']}"
        if o["driver_id"]:
            driver = await db.get_user(o["driver_id"])
            if driver:
                text += f"\n🚗 Haydovchi: {driver['full_name']}"
        await update.message.reply_text(text, reply_markup=kb.admin_order_actions_kb(o["id"]))


async def admin_reassign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return
    order_id = int(query.data.split(":")[1])
    await matching.admin_reassign_order(context, order_id)
    await query.answer("Navbatdagi shopirga yo'naltirildi (agar liniyada bo'sh shopir bo'lsa)")


async def admin_delete_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return
    order_id = int(query.data.split(":")[1])
    await matching.admin_delete_order(context, order_id)
    await query.edit_message_text(query.message.text + "\n\n🗑 O'CHIRILDI")
    await query.answer("O'chirildi")


# ---------------------------------------------------------------------------
# NAVBATDAGI SHOPIRLAR
# ---------------------------------------------------------------------------

async def choose_queue_direction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    directions = await db.list_directions()
    await update.message.reply_text(
        "📍 Qaysi yo'nalish navbatini ko'rmoqchisiz?", reply_markup=kb.directions_kb(directions, "admq_dir")
    )


async def show_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return
    direction_id = int(query.data.split(":")[1])
    await query.answer()
    await _render_queue(context, query.from_user.id, direction_id)


async def _render_queue(context, chat_id: int, direction_id: int):
    queue = await db.queue_list(direction_id)
    direction = await db.get_direction(direction_id)
    if not queue:
        await context.bot.send_message(chat_id=chat_id, text=f"📍 {direction['name']}\n\nNavbat bo'sh.")
        return
    await context.bot.send_message(chat_id=chat_id, text=f"📍 {direction['name']} — navbat:")
    for i, item in enumerate(queue, start=1):
        vip = " ⭐VIP" if item["is_vip"] else ""
        status = "🟢 bo'sh" if item["driver_status"] == "online" else "🚖 band"
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{i}. {item['full_name']}{vip} — {status}",
            reply_markup=kb.admin_queue_item_kb(item["driver_id"], direction_id),
        )


async def queue_up(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return
    _, direction_id, driver_id = query.data.split(":")
    direction_id = int(direction_id)
    before = await matching.get_queue_snapshot(direction_id)
    await db.queue_move(int(driver_id), direction_id, -1)
    await matching.notify_position_changes(context, direction_id, before)
    await query.answer("Yuqoriga surildi")


async def queue_down(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return
    _, direction_id, driver_id = query.data.split(":")
    direction_id = int(direction_id)
    before = await matching.get_queue_snapshot(direction_id)
    await db.queue_move(int(driver_id), direction_id, 1)
    await matching.notify_position_changes(context, direction_id, before)
    await query.answer("Pastga surildi")


async def queue_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return
    _, direction_id, driver_id = query.data.split(":")
    await matching.driver_goes_offline(context, int(driver_id), int(direction_id))
    await query.edit_message_text(query.message.text + "\n\n❌ Navbatdan olib tashlandi")
    await query.answer("Olib tashlandi")


# ---------------------------------------------------------------------------
# SHOPIRLAR RO'YXATI
# ---------------------------------------------------------------------------

async def list_drivers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    drivers = await db.list_drivers()
    if not drivers:
        await update.message.reply_text("Hozircha haydovchilar yo'q.")
        return
    for d in drivers:
        status = "✅ Faol" if d["is_enabled"] else "🚫 Nofaol"
        vip = "⭐ VIP" if d["is_vip"] else "oddiy"
        text = (
            f"👤 {d['full_name']}\n"
            f"📱 {d['phone']}\n"
            f"🚗 {d['car_info']}\n"
            f"Holat: {status} | {vip}\n"
            f"Liniya holati: {d['driver_status']}\n"
            f"💰 Balans: {d['balance']:,} so'm".replace(",", " ")
        )
        await update.message.reply_text(
            text, reply_markup=kb.admin_driver_actions_kb(d["telegram_id"], bool(d["is_enabled"]), bool(d["is_vip"]))
        )


async def toggle_active(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return
    driver_id = int(query.data.split(":")[1])
    driver = await db.get_user(driver_id)
    new_value = 0 if driver["is_enabled"] else 1
    await db.update_user(driver_id, is_enabled=new_value)
    if new_value == 0:
        await matching.driver_goes_offline(context, driver_id)
    await query.answer("Yangilandi")
    driver = await db.get_user(driver_id)
    await query.edit_message_reply_markup(
        reply_markup=kb.admin_driver_actions_kb(driver_id, bool(driver["is_enabled"]), bool(driver["is_vip"]))
    )


async def toggle_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return
    driver_id = int(query.data.split(":")[1])
    driver = await db.get_user(driver_id)
    new_value = 0 if driver["is_vip"] else 1
    await db.update_user(driver_id, is_vip=new_value)
    await query.answer("Yangilandi")
    driver = await db.get_user(driver_id)
    await query.edit_message_reply_markup(
        reply_markup=kb.admin_driver_actions_kb(driver_id, bool(driver["is_enabled"]), bool(driver["is_vip"]))
    )


async def ask_delete_driver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return
    driver_id = int(query.data.split(":")[1])
    await query.answer()
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=f"⚠️ Haqiqatan ham ID {driver_id} haydovchini o'chirmoqchimisiz? "
        "U haydovchilik ro'yxatidan butunlay chiqariladi (kerak bo'lsa qayta ariza topshirishi kerak bo'ladi).",
        reply_markup=kb.confirm_delete_driver_kb(driver_id),
    )


async def confirm_delete_driver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return
    driver_id = int(query.data.split(":")[1])
    await matching.driver_goes_offline(context, driver_id)
    await db.delete_driver(driver_id)
    await query.edit_message_text(f"🗑 Haydovchi (ID {driver_id}) o'chirildi.")
    await query.answer("O'chirildi")
    try:
        await context.bot.send_message(
            chat_id=driver_id,
            text="⚠️ Sizning haydovchilik profilingiz admin tomonidan o'chirildi. Qayta ariza topshirishingiz mumkin.",
        )
    except Exception:
        pass


async def abort_delete_driver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.edit_message_text("Bekor qilindi.")
    await query.answer()


# ---------------------------------------------------------------------------
# BEKOR QILISH (haydovchi bekor qilish so'rovini admin tasdiqlaydi)
# ---------------------------------------------------------------------------

async def confirm_cancellation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return
    order_id = int(query.data.split(":")[1])
    ok = await matching.admin_confirms_cancellation(context, order_id)
    if ok:
        await query.edit_message_text(query.message.text + "\n\n✅ TASDIQLANDI VA BEKOR QILINDI")
        await query.answer("Tasdiqlandi")
    else:
        await query.edit_message_text(query.message.text + "\n\n❗️Bu zakaz endi mavjud emas yoki allaqachon yakunlangan.")
        await query.answer("Xatolik")


# ---------------------------------------------------------------------------
# TO'LOV SOZLAMALARI (zakaz narxi, karta ma'lumotlari)
# ---------------------------------------------------------------------------

async def start_set_fee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    current = await db.get_setting("order_fee", "0")
    await update.message.reply_text(
        f"Hozirgi narx: {current} so'm (har bir yo'lovchidan).\n"
        "Har bir YO'LOVCHIDAN yechiladigan summani kiriting (faqat raqam). "
        "Masalan 5000 kiritsangiz, 1 kishilik zakazdan 5 000, 3 kishilikdan 15 000 so'm yechiladi:",
        reply_markup=kb.cancel_kb(),
    )
    return ADMIN_SET_FEE_AMOUNT


async def set_fee_invalid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Iltimos, faqat butun son kiriting (masalan: 5000).")
    return ADMIN_SET_FEE_AMOUNT


async def set_fee_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = int(update.message.text)
    if amount < 0:
        return await set_fee_invalid(update, context)
    await db.set_setting("order_fee", str(amount))
    await update.message.reply_text(
        f"✅ Endi har bir yo'lovchidan {amount:,} so'm yechiladi (masalan, 3 kishilik zakazdan {amount*3:,} so'm).".replace(",", " "),
        reply_markup=kb.admin_menu(),
    )
    return ConversationHandler.END


async def start_set_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    await update.message.reply_text("💳 Karta raqamini kiriting:", reply_markup=kb.cancel_kb())
    return ADMIN_SET_CARD_NUMBER


async def set_card_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["card_number"] = update.message.text
    await update.message.reply_text("👤 Karta egasining ism familiyasini kiriting:")
    return ADMIN_SET_CARD_NAME


async def set_card_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    card_number = context.user_data.pop("card_number", "")
    card_name = update.message.text
    await db.set_setting("payment_card_number", card_number)
    await db.set_setting("payment_card_name", card_name)
    await update.message.reply_text("✅ Karta ma'lumotlari saqlandi.", reply_markup=kb.admin_menu())
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# HAYDOVCHI TO'LOV SO'ROVLARINI TASDIQLASH
# ---------------------------------------------------------------------------

async def approve_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return
    tx_id = int(query.data.split(":")[1])
    tx = await db.get_transaction(tx_id)
    if not tx or tx["status"] != "pending":
        await query.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    await db.update_balance(tx["driver_id"], tx["amount"])
    await db.set_transaction_status(tx_id, "completed")
    await query.edit_caption(caption=(query.message.caption or "") + "\n\n✅ TASDIQLANDI")
    await query.answer("Tasdiqlandi")
    try:
        await context.bot.send_message(
            chat_id=tx["driver_id"],
            text=f"✅ To'lovingiz tasdiqlandi! Balansingiz {tx['amount']:,} so'mga to'ldirildi.".replace(",", " "),
        )
    except Exception:
        pass


async def reject_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return
    tx_id = int(query.data.split(":")[1])
    tx = await db.get_transaction(tx_id)
    if not tx or tx["status"] != "pending":
        await query.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    await db.set_transaction_status(tx_id, "rejected")
    await query.edit_caption(caption=(query.message.caption or "") + "\n\n❌ RAD ETILDI")
    await query.answer("Rad etildi")
    try:
        await context.bot.send_message(
            chat_id=tx["driver_id"],
            text=f"❌ To'lov so'rovingiz (№{tx_id}) rad etildi. Iltimos, admin bilan bog'laning.",
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# HAYDOVCHI BALANSINI QO'LDA BOSHQARISH
# ---------------------------------------------------------------------------

async def ask_balance_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return ConversationHandler.END
    action, driver_id = query.data.split(":")
    direction = "add" if action == "admin_balance_add" else "sub"
    context.user_data["balance_driver_id"] = int(driver_id)
    context.user_data["balance_direction"] = direction
    await query.answer()
    verb = "to'ldirish" if direction == "add" else "yechish"
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=f"💵 Balansni {verb} uchun summani kiriting (faqat raqam):",
        reply_markup=kb.cancel_kb(),
    )
    return ADMIN_ADJUST_AMOUNT


async def adjust_amount_invalid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Iltimos, faqat musbat butun son kiriting.")
    return ADMIN_ADJUST_AMOUNT


async def adjust_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = int(update.message.text)
    if amount <= 0:
        return await adjust_amount_invalid(update, context)
    context.user_data["balance_amount"] = amount
    await update.message.reply_text(
        "💬 Izoh qo'shmoqchimisiz? (masalan: \"naqd to'lov\"). Bo'lmasa, tugmani bosing.",
        reply_markup=kb.comment_skip_kb(),
    )
    return ADMIN_ADJUST_COMMENT


async def _apply_balance_adjustment(update: Update, context: ContextTypes.DEFAULT_TYPE, comment: str | None):
    driver_id = context.user_data.pop("balance_driver_id", None)
    direction = context.user_data.pop("balance_direction", None)
    amount = context.user_data.pop("balance_amount", None)
    if not driver_id or not amount:
        await update.message.reply_text("Xatolik yuz berdi, iltimos qaytadan boshlang.", reply_markup=kb.admin_menu())
        return ConversationHandler.END

    signed = amount if direction == "add" else -amount
    tx_type = "admin_topup" if direction == "add" else "admin_withdraw"
    await db.update_balance(driver_id, signed)
    await db.create_transaction(driver_id, tx_type, signed, status="completed", comment=comment)

    driver = await db.get_user(driver_id)
    verb = "to'ldirildi" if direction == "add" else "dan yechildi"
    await update.message.reply_text(
        f"✅ Balans {verb}. Yangi balans: {driver['balance']:,} so'm".replace(",", " "),
        reply_markup=kb.admin_menu(),
    )
    try:
        note = f"💰 Balansingiz{' ' + str(amount) + ' so‘mga to‘ldirildi' if direction == 'add' else ' dan ' + str(amount) + ' so‘m yechildi'}."
        if comment:
            note += f"\n💬 Izoh: {comment}"
        await context.bot.send_message(chat_id=driver_id, text=note)
    except Exception:
        pass
    return ConversationHandler.END


async def adjust_skip_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _apply_balance_adjustment(update, context, None)


async def adjust_with_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _apply_balance_adjustment(update, context, update.message.text)


async def show_driver_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return
    driver_id = int(query.data.split(":")[1])
    await query.answer()
    txs = await db.list_driver_transactions(driver_id, limit=20)
    if not txs:
        await context.bot.send_message(chat_id=query.from_user.id, text="Bu haydovchida tranzaksiyalar yo'q.")
        return

    lines = [f"🧾 Haydovchi (ID {driver_id}) tranzaksiyalari:\n"]
    for tx in txs:
        label = TX_TYPE_LABELS.get(tx["type"], tx["type"])
        status = TX_STATUS_LABELS.get(tx["status"], tx["status"])
        sign = "+" if tx["amount"] >= 0 else ""
        time_str = matching.format_order_time(tx["created_at"])
        line = f"{time_str} — {label}: {sign}{tx['amount']:,} so'm — {status}".replace(",", " ")
        if tx.get("comment"):
            line += f"\n   💬 {tx['comment']}"
        lines.append(line)
    await context.bot.send_message(chat_id=query.from_user.id, text="\n".join(lines))


# ---------------------------------------------------------------------------
# XABAR YUBORISH (broadcast)
# ---------------------------------------------------------------------------

async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("Xabarni kimga yubormoqchisiz?", reply_markup=kb.broadcast_target_kb())


async def broadcast_choose_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return ConversationHandler.END
    mapping = {"bc_all": "all", "bc_drivers": "drivers", "bc_clients": "clients"}
    context.user_data["broadcast_target"] = mapping[query.data]
    await query.answer()
    await context.bot.send_message(chat_id=query.from_user.id, text="✍️ Yubormoqchi bo'lgan xabar matnini kiriting:")
    return BROADCAST_MESSAGE


async def broadcast_choose_individual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q", show_alert=True)
        return ConversationHandler.END
    is_driver_target = query.data == "bc_driver_one"
    context.user_data["broadcast_target"] = "driver_one" if is_driver_target else "client_one"

    if is_driver_target:
        items = await db.list_drivers()
        label = "haydovchilar"
    else:
        items = await db.list_client_users()
        label = "yo'lovchilar"

    if not items:
        await query.answer()
        await context.bot.send_message(chat_id=query.from_user.id, text=f"Hozircha {label} ro'yxati bo'sh.")
        return ConversationHandler.END

    context.user_data["broadcast_list"] = [it["telegram_id"] for it in items]
    lines = [f"{i}. {it['full_name'] or it['telegram_id']}" for i, it in enumerate(items, start=1)]
    await query.answer()
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=f"{label.capitalize()} ro'yxati:\n\n" + "\n".join(lines) + "\n\nKerakli raqamni kiriting:",
        reply_markup=kb.cancel_kb(),
    )
    return BROADCAST_TARGET_NUMBER


async def broadcast_number_invalid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Noto'g'ri raqam. Iltimos, ro'yxatdagi raqamni qaytadan kiriting.")
    return BROADCAST_TARGET_NUMBER


async def broadcast_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = context.user_data.get("broadcast_list", [])
    idx = int(update.message.text)
    if idx < 1 or idx > len(items):
        return await broadcast_number_invalid(update, context)
    context.user_data["broadcast_single_target"] = items[idx - 1]
    await update.message.reply_text("✍️ Yubormoqchi bo'lgan xabar matnini kiriting:", reply_markup=kb.cancel_kb())
    return BROADCAST_MESSAGE


async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    target = context.user_data.pop("broadcast_target", None)
    single_target = context.user_data.pop("broadcast_single_target", None)
    context.user_data.pop("broadcast_list", None)

    if target == "all":
        recipients = await db.list_all_user_ids()
    elif target == "drivers":
        recipients = await db.list_driver_user_ids()
    elif target == "clients":
        recipients = await db.list_client_user_ids()
    elif target in ("driver_one", "client_one") and single_target:
        recipients = [single_target]
    else:
        await update.message.reply_text("Xatolik yuz berdi, iltimos qaytadan boshlang.", reply_markup=kb.admin_menu())
        return ConversationHandler.END

    sent = 0
    for chat_id in recipients:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
            sent += 1
        except Exception:
            pass

    await update.message.reply_text(f"✅ Xabar {sent} ta foydalanuvchiga yuborildi.", reply_markup=kb.admin_menu())
    return ConversationHandler.END
