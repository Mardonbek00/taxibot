"""
Zakaz - haydovchi moslashtirish logikasi (o'rindiq to'ldirish modeli).

Qoidalar:
- Har bir mashinada CAR_CAPACITY (odatda 4) o'rin bor.
- Liniyadagi (navbatdagi, online) haydovchilarga ularning BO'SH o'rniga mos
  keladigan zakazlar taklif qilinadi. Har bir zakaz ALOHIDA xabar (SMS)
  sifatida keladi — mijoz telefon raqami va izohi bilan.
- Haydovchi zakazni qabul qilsa -> o'sha zakaz unga biriktiriladi, band
  o'rinlari ortadi. Endi unga taklif qilingan, lekin YANGI bo'sh o'rniga
  SIG'MAYDIGAN zakazlar avtomatik undan bo'shatiladi (boshqa haydovchiga
  yoki kutish holatiga qaytadi).
- Mashina to'lsa (4/4) -> haydovchi avtomatik navbatdan chiqadi va "safarda"
  holatiga o'tadi (faqat "Safarni yakunlash" tugmasi qoladi).
- Haydovchi istalgan vaqtda "Jo'nash" tugmasini bosib, hozirgi band
  o'rinlar bilan yo'lga chiqishi mumkin (navbatdan chiqadi).
- Har bir taklif qilingan zakazga OFFER_TIMEOUT_SECONDS beriladi; shu
  vaqtda javob bo'lmasa, taklif bekor qilinadi VA o'sha haydovchi uchun
  "rad etilgan" deb belgilanadi (shu sababli darhol yana o'shanga
  taklif qilinmaydi) — boshqa haydovchiga yoki kutish holatiga o'tadi.
- Haydovchi "Rad etish" tugmasini bossa, o'sha (faqat o'sha) zakaz undan
  bo'shatilib qayta taqsimlanadi (yana o'shanga taklif qilinmaydi).
"""
import time
from datetime import datetime, timezone, timedelta

import database as db
import keyboards as kb
from config import CAR_CAPACITY, OFFER_TIMEOUT_SECONDS, ORDER_EXPIRY_SECONDS, ADMIN_IDS

TASHKENT_TZ = timezone(timedelta(hours=5))


def _format_time(ts: int) -> str:
    return datetime.fromtimestamp(ts, TASHKENT_TZ).strftime("%H:%M")


def format_order_time(ts: int) -> str:
    return _format_time(ts)


async def _direction_name(direction_id: int) -> str:
    d = await db.get_direction(direction_id)
    return d["name"] if d else "?"


def _order_card_text(order: dict, direction_name: str) -> str:
    lines = [
        f"🔔 YANGI ZAKAZ №{order['id']}",
        "",
        f"🕐 Kelib tushgan vaqti: {_format_time(order['created_at'])}",
        f"📍 Yo'nalish: {direction_name}",
        f"👥 Necha kishi: {order['passenger_count']}",
    ]
    if order.get("comment"):
        lines.append(f"💬 Izoh: {order['comment']}")
    lines.append("")
    lines.append(f"⏱ Javob berish uchun {OFFER_TIMEOUT_SECONDS} soniya vaqtingiz bor.")
    return "\n".join(lines)


async def _offer_single_order(context, order: dict, driver_id: int):
    """Bitta zakazni haydovchiga ALOHIDA xabar sifatida yuboradi va message_id ni saqlaydi."""
    direction_name = await _direction_name(order["direction_id"])
    text = _order_card_text(order, direction_name)
    try:
        msg = await context.bot.send_message(
            chat_id=driver_id,
            text=text,
            reply_markup=kb.single_order_offer_kb(order["id"]),
        )
        await db.set_offer_message_id(order["id"], msg.message_id)
    except Exception:
        pass


async def _close_offer_message(context, order: dict, driver_id: int, note: str):
    """Taklif xabarini (bo'shatilgan/muddati tugagan sabab bilan) tahrirlab, tugmalarni olib tashlaydi."""
    message_id = order.get("offer_message_id")
    if not message_id:
        return
    try:
        await context.bot.edit_message_text(
            chat_id=driver_id,
            message_id=message_id,
            text=_order_card_text(order, await _direction_name(order["direction_id"])) + f"\n\n{note}",
            reply_markup=None,
        )
    except Exception:
        pass


async def _schedule_expiry(context, order_id: int, driver_id: int, direction_id: int):
    async def _expire_later():
        import asyncio

        await asyncio.sleep(OFFER_TIMEOUT_SECONDS)
        order = await db.get_order(order_id)
        if not order:
            return
        if order["status"] == "kutilmoqda" and order["offered_to_driver"] == driver_id:
            await _close_offer_message(context, order, driver_id, "⏱ Vaqt tugadi.")
            await db.clear_order_offer(order_id)
            await db.add_rejection(order_id, driver_id)  # yana o'shanga darhol qaytmasin
            await run_matching(context, direction_id)

    context.application.create_task(_expire_later())


async def get_queue_snapshot(direction_id: int) -> dict[int, int]:
    """Yo'nalishdagi (online) haydovchilarning joriy o'rinlarini {driver_id: o'rin} ko'rinishida qaytaradi."""
    queue = await db.queue_list(direction_id)
    return {
        d["driver_id"]: i
        for i, d in enumerate((x for x in queue if x["driver_status"] == "online"), start=1)
    }


async def notify_position_changes(context, direction_id: int, before: dict[int, int], exclude: set[int] | None = None):
    """`before` bilan solishtirib, faqat o'rni HAQIQATAN o'zgargan haydovchilarga xabar yuboradi."""
    exclude = exclude or set()
    after = await get_queue_snapshot(direction_id)
    for driver_id, new_pos in after.items():
        if driver_id in exclude:
            continue
        old_pos = before.get(driver_id)
        if old_pos is not None and old_pos != new_pos:
            try:
                await context.bot.send_message(
                    chat_id=driver_id,
                    text=f"🔢 Navbatdagi joyingiz o'zgardi: {old_pos}-o'rindan {new_pos}-o'ringa.",
                )
            except Exception:
                pass


async def run_matching(context, direction_id: int):
    """
    Yo'nalishdagi navbat bo'yicha zakazlarni qayta taqsimlaydi.
    Har bir online haydovchi o'z bo'sh joyiga (current_seats asosida) mos
    keladigan barcha zakazlarni ko'rishi mumkin (bir nechtasi bir vaqtda
    taklif qilinishi mumkin — u orasidan tanlaydi). Bitta zakaz bir vaqtning
    o'zida faqat bitta haydovchiga taklif qilinadi; agar navbatdagi birinchi
    haydovchi uni rad etsa/muddati tugasa yoki unga sig'masa, navbatdagi
    keyingi haydovchiga o'tadi.
    """
    queue = await db.queue_list(direction_id)
    online_drivers = [d for d in queue if d["driver_status"] == "online"]
    if not online_drivers:
        return

    driver_remaining: dict[int, int] = {}
    for d in online_drivers:
        driver = await db.get_user(d["driver_id"])
        driver_remaining[d["driver_id"]] = CAR_CAPACITY - driver["current_seats"]

    all_waiting = await db.list_waiting_orders(direction_id)

    # 1) Joriy taklif qilingan, lekin endi sig'maydigan zakazlarni bo'shatamiz
    for o in all_waiting:
        drv = o["offered_to_driver"]
        if drv is not None and drv in driver_remaining:
            if o["passenger_count"] > driver_remaining[drv]:
                await _close_offer_message(context, o, drv, "❗️Joy yetmagani uchun bekor qilindi.")
                await db.clear_order_offer(o["id"])
                o["offered_to_driver"] = None

    # 2) Taklif qilinmagan (yoki hozirgina bo'shagan) zakazlarni navbat
    #    tartibida birinchi mos keluvchi (va vaqtida rad etmagan/o'tkazib
    #    yubormagan) haydovchiga taklif qilamiz. Bir marta rad etilgan yoki
    #    muddati o'tgan zakaz o'sha haydovchiga boshqa hech qachon qaytmaydi —
    #    faqat yangi qo'shilgan yoki hali rad etmagan boshqa haydovchiga boradi.
    expires_at = int(time.time()) + OFFER_TIMEOUT_SECONDS
    for o in all_waiting:
        if o["offered_to_driver"] is not None:
            continue  # allaqachon kimgadir taklif qilingan

        assigned_driver_id = None
        for d in online_drivers:
            driver_id = d["driver_id"]
            rejected = await db.get_rejected_order_ids(driver_id)
            if o["id"] in rejected:
                continue
            if o["passenger_count"] <= driver_remaining.get(driver_id, 0):
                assigned_driver_id = driver_id
                break

        if assigned_driver_id is not None:
            await db.set_order_offer(o["id"], assigned_driver_id, expires_at)
            await _schedule_expiry(context, o["id"], assigned_driver_id, direction_id)
            fresh_order = await db.get_order(o["id"])
            await _offer_single_order(context, fresh_order, assigned_driver_id)


async def _schedule_order_expiry(context, order_id: int, direction_id: int):
    """Agar zakaz ORDER_EXPIRY_SECONDS ichida hech qanday haydovchi tomonidan
    qabul qilinmasa, uni bekor qilib, mijozga xabar beradi."""
    async def _expire_later():
        import asyncio

        await asyncio.sleep(ORDER_EXPIRY_SECONDS)
        order = await db.get_order(order_id)
        if not order or order["status"] != "kutilmoqda":
            return  # allaqachon qabul qilingan yoki boshqa sababda yopilgan

        if order["offered_to_driver"]:
            await _close_offer_message(context, order, order["offered_to_driver"], "Zakaz muddati tugagani uchun bekor qilindi.")
            await db.clear_order_offer(order_id)

        await db.set_order_status(order_id, "bekor_qilingan")
        try:
            await context.bot.send_message(
                chat_id=order["client_id"],
                text=f"❌ Zakazingiz (№{order_id}) bekor qilindi — hozirda haydovchilar yo'q. "
                "Iltimos, qaytadan buyurtma bering.",
            )
        except Exception:
            pass

    context.application.create_task(_expire_later())


async def new_order_created(context, order_id: int, direction_id: int):
    await run_matching(context, direction_id)
    await _schedule_order_expiry(context, order_id, direction_id)


async def driver_goes_online(context, driver_id: int, direction_id: int):
    user = await db.get_user(driver_id)
    before = await get_queue_snapshot(direction_id)
    await db.update_user(driver_id, driver_status="online", current_seats=0)
    await db.queue_join(driver_id, direction_id, bool(user and user["is_vip"]))
    position = await db.queue_position(driver_id, direction_id)
    if position:
        try:
            await context.bot.send_message(chat_id=driver_id, text=f"🔢 Navbatdagi joyingiz: {position}-o'rin.")
        except Exception:
            pass
    # VIP boshiga qo'yilganda, undan keyingi haydovchilarning o'rni siljigan bo'lishi mumkin
    await notify_position_changes(context, direction_id, before, exclude={driver_id})
    await run_matching(context, direction_id)


async def driver_goes_offline(context, driver_id: int, direction_id: int | None = None):
    if direction_id is None:
        direction_id = await db.get_driver_direction(driver_id)
    # taklif qilingan (hali javobsiz) zakazlarni bo'shatamiz
    offered = await db.list_offered_orders(driver_id)
    for o in offered:
        await _close_offer_message(context, o, driver_id, "Haydovchi liniyadan chiqdi.")
        await db.clear_order_offer(o["id"])
    before = await get_queue_snapshot(direction_id) if direction_id is not None else {}
    await db.update_user(driver_id, driver_status="offline")
    await db.queue_leave(driver_id, direction_id)
    if direction_id is not None:
        await notify_position_changes(context, direction_id, before)
        await run_matching(context, direction_id)


async def driver_accepts_order(context, driver_id: int, order_id: int):
    order = await db.get_order(order_id)
    if not order or order["status"] != "kutilmoqda" or order["offered_to_driver"] != driver_id:
        return "expired"

    driver = await db.get_user(driver_id)
    remaining = CAR_CAPACITY - driver["current_seats"]
    if order["passenger_count"] > remaining:
        # kamdan-kam holat (poyga sharoiti): joy yetmay qoldi
        await db.clear_order_offer(order_id)
        return "no_capacity"

    order_fee = int(await db.get_setting("order_fee", "0") or "0") * order["passenger_count"]
    if order_fee > 0 and driver["balance"] < order_fee:
        await db.clear_order_offer(order_id)
        await db.add_rejection(order_id, driver_id)
        await run_matching(context, order["direction_id"])
        return "no_balance"

    direction_id = order["direction_id"]
    await db.set_order_status(order_id, "tasdiqlangan", driver_id=driver_id)

    new_seats = driver["current_seats"] + order["passenger_count"]
    await db.update_user(driver_id, current_seats=new_seats)

    if order_fee > 0:
        await db.update_balance(driver_id, -order_fee)
        await db.create_transaction(
            driver_id, "order_fee", -order_fee, status="completed", order_id=order_id,
            comment=f"№{order_id} zakaz uchun xizmat haqi ({order['passenger_count']} kishi)",
        )

    direction_name = await _direction_name(direction_id)
    try:
        await context.bot.send_message(
            chat_id=order["client_id"],
            text="✅ Sizga haydovchi topildi!\n\n"
            f"👤 Ism: {driver['full_name']}\n"
            f"🚗 Mashina: {driver['car_info']}\n"
            f"📞 Haydovchi telefoni: {driver['phone']}\n"
            f"📍 Yo'nalish: {direction_name}",
        )
    except Exception:
        pass

    if new_seats >= CAR_CAPACITY:
        # mashina to'ldi -> avtomatik jo'naydi
        before = await get_queue_snapshot(direction_id)
        await db.queue_leave(driver_id, direction_id)
        await db.update_user(driver_id, driver_status="busy")
        driver_after = await db.get_user(driver_id)
        balance_line = f"\n💰 Balansdan {order_fee:,} so'm yechildi. Joriy balans: {driver_after['balance']:,} so'm.".replace(",", " ") if order_fee > 0 else ""
        try:
            await context.bot.send_message(
                chat_id=driver_id,
                text=f"🚗 Mashinangiz to'ldi ({new_seats}/{CAR_CAPACITY})! Avtomatik yo'lga chiqdingiz.{balance_line}",
                reply_markup=kb.driver_busy_kb(),
            )
        except Exception:
            pass
        await notify_position_changes(context, direction_id, before)
    else:
        driver_after = await db.get_user(driver_id)
        balance_line = f"\n💰 Balansdan {order_fee:,} so'm yechildi. Joriy balans: {driver_after['balance']:,} so'm.".replace(",", " ") if order_fee > 0 else ""
        try:
            await context.bot.send_message(
                chat_id=driver_id,
                text=f"✅ №{order_id} zakaz qabul qilindi.\n"
                f"👥 Hozirda sizda: {new_seats}/{CAR_CAPACITY} kishi.{balance_line}\n\n"
                "Yana zakaz kutasizmi yoki hoziroq jo'naysizmi?",
                reply_markup=kb.driver_online_kb(new_seats),
            )
        except Exception:
            pass

    await run_matching(context, direction_id)
    return "ok"


async def driver_rejects_order(context, driver_id: int, order_id: int):
    order = await db.get_order(order_id)
    if not order or order["offered_to_driver"] != driver_id:
        return False
    await db.clear_order_offer(order_id)
    await db.add_rejection(order_id, driver_id)
    await run_matching(context, order["direction_id"])
    return True


async def driver_departs(context, driver_id: int):
    """Haydovchi 'Jo'nash' tugmasini qo'lda bosganda."""
    driver = await db.get_user(driver_id)
    if not driver or driver["current_seats"] <= 0:
        return False

    direction_id = await db.get_driver_direction(driver_id)

    # hali javob berilmagan takliflarni bo'shatamiz
    offered = await db.list_offered_orders(driver_id)
    for o in offered:
        await _close_offer_message(context, o, driver_id, "Haydovchi yo'lga chiqdi.")
        await db.clear_order_offer(o["id"])

    before = await get_queue_snapshot(direction_id) if direction_id is not None else {}
    await db.queue_leave(driver_id, direction_id)
    await db.update_user(driver_id, driver_status="busy")

    if direction_id is not None:
        await notify_position_changes(context, direction_id, before)
        await run_matching(context, direction_id)
    return True


async def driver_finishes_trip(context, driver_id: int):
    await db.finish_driver_orders(driver_id)
    await db.update_user(driver_id, driver_status="offline", current_seats=0)


async def passenger_cancels_order(context, order: dict):
    """Yo'lovchi o'z zakazini bekor qilganda: haydovchini butunlay emas, faqat shu
    zakaz bo'yicha band qilingan o'rinlarni bo'shatadi."""
    order_id = order["id"]
    direction_id = order["direction_id"]

    if order["status"] == "kutilmoqda":
        if order["offered_to_driver"]:
            await _close_offer_message(context, order, order["offered_to_driver"], "Yo'lovchi zakazni bekor qildi.")
        await db.set_order_status(order_id, "bekor_qilingan")
        return

    if order["status"] == "tasdiqlangan" and order["driver_id"]:
        driver_id = order["driver_id"]
        driver = await db.get_user(driver_id)
        if driver:
            new_seats = max(0, driver["current_seats"] - order["passenger_count"])
            await db.update_user(driver_id, current_seats=new_seats)
        try:
            await context.bot.send_message(
                chat_id=driver_id,
                text=f"❗️Yo'lovchi №{order_id} zakazni bekor qildi.",
            )
        except Exception:
            pass
        await db.set_order_status(order_id, "bekor_qilingan")
        driver = await db.get_user(driver_id)
        if driver and driver["driver_status"] == "online":
            await run_matching(context, direction_id)
        return

    await db.set_order_status(order_id, "bekor_qilingan")


async def admin_reassign_order(context, order_id: int):
    order = await db.get_order(order_id)
    if not order or order["status"] != "kutilmoqda":
        return
    await db.clear_order_offer(order_id)
    await db.clear_rejections_for_order(order_id)
    await run_matching(context, order["direction_id"])


async def admin_delete_order(context, order_id: int):
    order = await db.get_order(order_id)
    if not order:
        return
    if order["offered_to_driver"]:
        await _close_offer_message(context, order, order["offered_to_driver"], "Zakaz admin tomonidan bekor qilindi.")
    await db.set_order_status(order_id, "bekor_qilingan")
    try:
        await context.bot.send_message(chat_id=order["client_id"], text="❌ Sizning zakazingiz admin tomonidan bekor qilindi.")
    except Exception:
        pass
    if order["driver_id"]:
        try:
            await context.bot.send_message(chat_id=order["driver_id"], text=f"❌ №{order_id} zakaz admin tomonidan bekor qilindi.")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# BEKOR QILISH (haydovchi tomonidan bekor qilish so'rovi)
# ---------------------------------------------------------------------------

async def driver_requests_cancellation(context, driver_id: int, order_id: int):
    order = await db.get_order(order_id)
    if not order or order["driver_id"] != driver_id or order["status"] != "tasdiqlangan":
        return False

    driver = await db.get_user(driver_id)
    direction_name = await _direction_name(order["direction_id"])
    text = (
        f"🚫 BEKOR QILISH SO'ROVI — №{order_id}\n\n"
        f"📍 Yo'nalish: {direction_name}\n"
        f"👥 {order['passenger_count']} kishi\n\n"
        f"👤 Haydovchi: {driver['full_name']}\n"
        f"📞 Haydovchi telefoni: {driver['phone']}\n\n"
        f"📞 Yo'lovchi telefoni: {order['phone']}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=text, reply_markup=kb.cancel_request_admin_kb(order_id))
        except Exception:
            pass
    return True


async def admin_confirms_cancellation(context, order_id: int):
    order = await db.get_order(order_id)
    if not order or order["status"] != "tasdiqlangan" or not order["driver_id"]:
        return False

    driver_id = order["driver_id"]
    driver = await db.get_user(driver_id)

    # to'langan xizmat haqini aniq summasi bilan qaytaramiz
    fee_tx = await db.get_order_fee_transaction(order_id)
    refund_amount = -fee_tx["amount"] if fee_tx else 0

    if refund_amount > 0:
        await db.update_balance(driver_id, refund_amount)
        await db.create_transaction(
            driver_id, "order_fee_refund", refund_amount, status="completed", order_id=order_id,
            comment=f"№{order_id} zakaz bekor qilingani uchun qaytarildi",
        )

    if driver:
        new_seats = max(0, driver["current_seats"] - order["passenger_count"])
        await db.update_user(driver_id, current_seats=new_seats)

    await db.set_order_status(order_id, "bekor_qilingan")

    driver_after = await db.get_user(driver_id)
    refund_line = f"\n💰 {refund_amount:,} so'm balansingizga qaytarildi. Joriy balans: {driver_after['balance']:,} so'm.".replace(",", " ") if refund_amount > 0 else ""
    try:
        await context.bot.send_message(
            chat_id=driver_id,
            text=f"✅ №{order_id} zakaz bo'yicha bekor qilish so'rovingiz tasdiqlandi.{refund_line}",
        )
    except Exception:
        pass
    try:
        await context.bot.send_message(
            chat_id=order["client_id"],
            text=f"❌ Sizning №{order_id} zakazingiz bekor qilindi.",
        )
    except Exception:
        pass
    return True
