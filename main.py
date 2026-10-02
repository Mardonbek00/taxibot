import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

from config import BOT_TOKEN
import database as db
from states import (
    ORDER_DIRECTION,
    ORDER_PCOUNT,
    ORDER_PHONE,
    ORDER_COMMENT,
    DRIVER_NAME,
    DRIVER_PHONE,
    DRIVER_CAR,
    DRIVER_ONLINE_DIRECTION,
    BALANCE_TOPUP_AMOUNT,
    BALANCE_TOPUP_SCREENSHOT,
    ADMIN_SET_FEE_AMOUNT,
    ADMIN_SET_CARD_NUMBER,
    ADMIN_SET_CARD_NAME,
    ADMIN_ADJUST_AMOUNT,
    ADMIN_ADJUST_COMMENT,
    BROADCAST_TARGET_NUMBER,
    BROADCAST_MESSAGE,
)
from handlers import common, passenger, driver, admin


class _HealthCheckHandler(BaseHTTPRequestHandler):
    """Render (va shunga o'xshash hostinglar) 'portni tinglab turibsizmi' deb
    tekshiradi. Bot o'zi run_polling() bilan ishlagani uchun hech qanday portni
    ochmaydi va host uni 'ishlamayapti' deb hisoblab, doim qayta ishga tushiradi
    (aynan shu narsa 'timeout' xatosiga sabab bo'ladi). Shu oddiy server esa
    faqat 'OK' deb javob berib, host tekshiruvini qondiradi."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot ishlamoqda")

    def log_message(self, format, *args):
        pass  # konsolni keraksiz loglar bilan to'ldirmaslik uchun


def _start_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), _HealthCheckHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logging.info(f"Health-check server {port}-portda ishga tushdi")


def _self_ping_loop():
    """Render bepul rejasi 15 daqiqa hech qanday tashqi so'rov kelmasa,
    servisni 'uxlatib' qo'yadi. Buning oldini olish uchun bot o'zining
    ochiq portiga (RENDER_EXTERNAL_URL) har 10 daqiqada bir marta so'rov
    yuborib turadi — bu Render uchun 'faol' so'rov hisoblanadi.
    Bu rasman kafolatlangan yechim emas (Render buni rasman qo'llab-
    quvvatlamaydi), lekin amalda ishlaydi."""
    import time
    import urllib.request

    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        logging.info("RENDER_EXTERNAL_URL topilmadi — self-ping o'chirilgan (lokal ishga tushirishda normal holat)")
        return

    def _loop():
        while True:
            time.sleep(600)  # 10 daqiqa — 15 daqiqalik chegaradan xavfsiz kam
            try:
                urllib.request.urlopen(url, timeout=10)
                logging.info("Self-ping yuborildi: %s", url)
            except Exception as e:
                logging.warning("Self-ping xatosi: %s", e)

    threading.Thread(target=_loop, daemon=True).start()


async def post_init(application: Application):
    await db.init_db()


async def post_shutdown(application: Application):
    import pg
    await pg.close_pool()


def main():
    logging.basicConfig(level=logging.INFO)

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()

    CANCEL_FALLBACKS = [
        MessageHandler(filters.Regex("^⬅️ Bekor qilish$"), common.cancel_action),
        MessageHandler(filters.Regex("^⬅️ Asosiy menyu$"), common.back_to_main),
    ]

    # ------------------------------------------------------------------
    # YO'LOVCHI: ZAKAZ BERISH
    # ------------------------------------------------------------------
    order_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🚕 Taxi zakaz qilish$"), passenger.start_order)],
        states={
            ORDER_DIRECTION: [CallbackQueryHandler(passenger.choose_direction, pattern=r"^order_dir:\d+$")],
            ORDER_PCOUNT: [CallbackQueryHandler(passenger.choose_passenger_count, pattern=r"^pcount:\d+$")],
            ORDER_PHONE: [
                MessageHandler(filters.CONTACT, passenger.receive_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^⬅️"), passenger.wrong_phone_input),
            ],
            ORDER_COMMENT: [
                MessageHandler(filters.Regex("^➖ Izohsiz davom etish$"), passenger.skip_comment),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^⬅️"), passenger.receive_comment),
            ],
        },
        fallbacks=CANCEL_FALLBACKS,
    )

    # ------------------------------------------------------------------
    # HAYDOVCHI BO'LISH (ariza)
    # ------------------------------------------------------------------
    driver_app_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🧑‍✈️ Haydovchi bo'lish$"), driver.start_application)],
        states={
            DRIVER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^⬅️"), driver.app_full_name)],
            DRIVER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^⬅️"), driver.app_phone)],
            DRIVER_CAR: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^⬅️"), driver.app_car_info)],
        },
        fallbacks=CANCEL_FALLBACKS,
    )

    # ------------------------------------------------------------------
    # HAYDOVCHI: LINIYAGA CHIQISH
    # ------------------------------------------------------------------
    driver_online_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🟢 Liniyaga chiqish$"), driver.go_online_start)],
        states={
            DRIVER_ONLINE_DIRECTION: [CallbackQueryHandler(driver.go_online_direction, pattern=r"^drv_dir:\d+$")],
        },
        fallbacks=[MessageHandler(filters.Regex("^⬅️ Asosiy menyu$"), common.back_to_main)],
    )

    # ------------------------------------------------------------------
    # HAYDOVCHI: BALANSNI TO'LDIRISH
    # ------------------------------------------------------------------
    topup_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Balansni to'ldirish$"), driver.start_topup)],
        states={
            BALANCE_TOPUP_AMOUNT: [
                MessageHandler(filters.Regex(r"^\d+$"), driver.topup_amount),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^⬅️"), driver.topup_amount_invalid),
            ],
            BALANCE_TOPUP_SCREENSHOT: [
                MessageHandler(filters.PHOTO, driver.topup_screenshot),
                MessageHandler(~filters.PHOTO & ~filters.Regex("^⬅️") & ~filters.COMMAND, driver.topup_screenshot_invalid),
            ],
        },
        fallbacks=CANCEL_FALLBACKS,
    )

    # ------------------------------------------------------------------
    # ADMIN: ZAKAZ NARXI VA KARTA MA'LUMOTLARI
    # ------------------------------------------------------------------
    set_fee_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 Zakaz narxini belgilash$"), admin.start_set_fee)],
        states={
            ADMIN_SET_FEE_AMOUNT: [
                MessageHandler(filters.Regex(r"^\d+$"), admin.set_fee_amount),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^⬅️"), admin.set_fee_invalid),
            ],
        },
        fallbacks=CANCEL_FALLBACKS,
    )

    set_card_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💳 Karta ma'lumotlari$"), admin.start_set_card)],
        states={
            ADMIN_SET_CARD_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^⬅️"), admin.set_card_number)],
            ADMIN_SET_CARD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^⬅️"), admin.set_card_name)],
        },
        fallbacks=CANCEL_FALLBACKS,
    )

    # ------------------------------------------------------------------
    # ADMIN: HAYDOVCHI BALANSINI QO'LDA BOSHQARISH
    # ------------------------------------------------------------------
    adjust_balance_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin.ask_balance_amount, pattern=r"^admin_balance_(add|sub):\d+$")],
        states={
            ADMIN_ADJUST_AMOUNT: [
                MessageHandler(filters.Regex(r"^\d+$"), admin.adjust_amount),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^⬅️"), admin.adjust_amount_invalid),
            ],
            ADMIN_ADJUST_COMMENT: [
                MessageHandler(filters.Regex("^➖ Izohsiz davom etish$"), admin.adjust_skip_comment),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^⬅️"), admin.adjust_with_comment),
            ],
        },
        fallbacks=CANCEL_FALLBACKS,
    )

    # ------------------------------------------------------------------
    # ADMIN: XABAR YUBORISH (broadcast)
    # ------------------------------------------------------------------
    broadcast_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin.broadcast_choose_group, pattern=r"^bc_(all|drivers|clients)$"),
            CallbackQueryHandler(admin.broadcast_choose_individual, pattern=r"^bc_(driver_one|client_one)$"),
        ],
        states={
            BROADCAST_TARGET_NUMBER: [
                MessageHandler(filters.Regex(r"^\d+$"), admin.broadcast_number),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^⬅️"), admin.broadcast_number_invalid),
            ],
            BROADCAST_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^⬅️"), admin.broadcast_send),
            ],
        },
        fallbacks=CANCEL_FALLBACKS,
    )

    app.add_handler(CommandHandler("start", common.cmd_start))

    app.add_handler(order_conv)
    app.add_handler(driver_app_conv)
    app.add_handler(driver_online_conv)
    app.add_handler(topup_conv)
    app.add_handler(set_fee_conv)
    app.add_handler(set_card_conv)
    app.add_handler(adjust_balance_conv)
    app.add_handler(broadcast_conv)

    # ------------------------------------------------------------------
    # ODDIY (conversationsiz) MATN TUGMALARI
    # ------------------------------------------------------------------
    app.add_handler(MessageHandler(filters.Regex("^⬅️ Asosiy menyu$"), common.back_to_main))
    app.add_handler(MessageHandler(filters.Regex("^🚦 Haydovchi paneli$"), driver.driver_panel))
    app.add_handler(MessageHandler(filters.Regex("^🔴 Liniyadan chiqish$"), driver.go_offline))
    app.add_handler(MessageHandler(filters.Regex("^🏁 Safarni yakunlash$"), driver.finish_trip))
    app.add_handler(MessageHandler(filters.Regex("^📋 Faol zakazlarim$"), driver.show_active_orders))
    app.add_handler(MessageHandler(filters.Regex("^💰 Balans$"), driver.show_balance_menu))
    app.add_handler(MessageHandler(filters.Regex("^🧾 Tarix$"), driver.show_history))

    app.add_handler(MessageHandler(filters.Regex("^👑 Admin panel$"), admin.show_admin_panel))
    app.add_handler(MessageHandler(filters.Regex("^📋 Faol zakazlar$"), admin.list_active_orders))
    app.add_handler(MessageHandler(filters.Regex("^🚦 Navbatdagi shopirlar$"), admin.choose_queue_direction))
    app.add_handler(MessageHandler(filters.Regex("^👨‍✈️ Shopirlar$"), admin.list_drivers))
    app.add_handler(MessageHandler(filters.Regex("^📝 Yangi arizalar$"), admin.list_applications))
    app.add_handler(MessageHandler(filters.Regex("^📢 Xabar yuborish$"), admin.start_broadcast))

    # "🚀 Jo'nash (N/4)" tugmasi dinamik matn bo'lgani uchun prefiks bo'yicha moslaymiz
    app.add_handler(MessageHandler(filters.Regex(r"^🚀 Jo'nash"), driver.depart))

    # ------------------------------------------------------------------
    # INLINE TUGMALAR (conversationdan tashqarida ham ishlaydigan)
    # ------------------------------------------------------------------
    app.add_handler(CallbackQueryHandler(passenger.cancel_order, pattern=r"^order_cancel$"))
    app.add_handler(CallbackQueryHandler(driver.driver_accept_order, pattern=r"^driver_accept:\d+$"))
    app.add_handler(CallbackQueryHandler(driver.driver_reject_order, pattern=r"^driver_reject:\d+$"))

    app.add_handler(CallbackQueryHandler(admin.approve_application, pattern=r"^app_approve:\d+$"))
    app.add_handler(CallbackQueryHandler(admin.reject_application, pattern=r"^app_reject:\d+$"))

    app.add_handler(CallbackQueryHandler(admin.admin_reassign, pattern=r"^admin_reassign:\d+$"))
    app.add_handler(CallbackQueryHandler(admin.admin_delete_order, pattern=r"^admin_delete_order:\d+$"))

    app.add_handler(CallbackQueryHandler(admin.show_queue, pattern=r"^admq_dir:\d+$"))
    app.add_handler(CallbackQueryHandler(admin.queue_up, pattern=r"^queue_up:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(admin.queue_down, pattern=r"^queue_down:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(admin.queue_remove, pattern=r"^queue_remove:\d+:\d+$"))

    app.add_handler(CallbackQueryHandler(admin.toggle_active, pattern=r"^admin_toggle_active:\d+$"))
    app.add_handler(CallbackQueryHandler(admin.toggle_vip, pattern=r"^admin_toggle_vip:\d+$"))
    app.add_handler(CallbackQueryHandler(admin.ask_delete_driver, pattern=r"^admin_delete_driver:\d+$"))
    app.add_handler(CallbackQueryHandler(admin.confirm_delete_driver, pattern=r"^admin_delete_driver_confirm:\d+$"))
    app.add_handler(CallbackQueryHandler(admin.abort_delete_driver, pattern=r"^admin_delete_driver_abort$"))

    app.add_handler(CallbackQueryHandler(driver.request_cancellation, pattern=r"^cancel_request:\d+$"))
    app.add_handler(CallbackQueryHandler(admin.confirm_cancellation, pattern=r"^cancel_confirm:\d+$"))

    app.add_handler(CallbackQueryHandler(admin.approve_topup, pattern=r"^topup_approve:\d+$"))
    app.add_handler(CallbackQueryHandler(admin.reject_topup, pattern=r"^topup_reject:\d+$"))
    app.add_handler(CallbackQueryHandler(admin.show_driver_transactions, pattern=r"^admin_driver_tx:\d+$"))

    print("Taxi bot ishga tushdi (python-telegram-bot)...")
    _start_health_check_server()
    _self_ping_loop()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
