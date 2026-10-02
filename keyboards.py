from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from config import PASSENGER_COUNTS, CAR_CAPACITY

# ---------------------------------------------------------------------------
# ASOSIY MENYU
# ---------------------------------------------------------------------------

def main_menu(is_driver: bool, is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [["🚕 Taxi zakaz qilish"]]
    if is_driver:
        rows.append(["🚦 Haydovchi paneli"])
        rows.append(["💰 Balans"])
    else:
        rows.append(["🧑‍✈️ Haydovchi bo'lish"])
    if is_admin:
        rows.append(["👑 Admin panel"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def admin_menu() -> ReplyKeyboardMarkup:
    rows = [
        ["📋 Faol zakazlar"],
        ["🚦 Navbatdagi shopirlar"],
        ["👨‍✈️ Shopirlar"],
        ["📝 Yangi arizalar"],
        ["💰 Zakaz narxini belgilash", "💳 Karta ma'lumotlari"],
        ["📢 Xabar yuborish"],
        ["⬅️ Asosiy menyu"],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["⬅️ Bekor qilish"]], resize_keyboard=True)


def phone_request_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def comment_skip_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["➖ Izohsiz davom etish"]], resize_keyboard=True, one_time_keyboard=True)


# ---------------------------------------------------------------------------
# YO'NALISH VA YO'LOVCHI SONI
# ---------------------------------------------------------------------------

def directions_kb(directions: list[dict], callback_prefix: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(d["name"], callback_data=f"{callback_prefix}:{d['id']}")]
        for d in directions
    ]
    return InlineKeyboardMarkup(rows)


def passenger_count_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"{n} kishi", callback_data=f"pcount:{n}")] for n in PASSENGER_COUNTS]
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# YO'LOVCHI: FAOL ZAKAZ
# ---------------------------------------------------------------------------

def order_waiting_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Zakazni bekor qilish", callback_data="order_cancel")]])


# ---------------------------------------------------------------------------
# HAYDOVCHI
# ---------------------------------------------------------------------------

def driver_panel_kb(online: bool, current_seats: int = 0) -> ReplyKeyboardMarkup:
    if online:
        return driver_online_kb(current_seats)
    rows = [["🟢 Liniyaga chiqish"], ["📋 Faol zakazlarim"], ["⬅️ Asosiy menyu"]]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def driver_online_kb(current_seats: int) -> ReplyKeyboardMarkup:
    rows = []
    if current_seats > 0:
        rows.append([f"🚀 Jo'nash ({current_seats}/{CAR_CAPACITY})"])
        rows.append(["📋 Faol zakazlarim"])
    rows.append(["🔴 Liniyadan chiqish"])
    rows.append(["⬅️ Asosiy menyu"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def driver_busy_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["📋 Faol zakazlarim"], ["🏁 Safarni yakunlash"]], resize_keyboard=True)


def offered_orders_kb(orders: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for o in orders:
        rows.append(
            [
                InlineKeyboardButton(f"✅ №{o['id']} ({o['passenger_count']} kishi)", callback_data=f"driver_accept:{o['id']}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"driver_reject:{o['id']}"),
            ]
        )
    return InlineKeyboardMarkup(rows)


def single_order_offer_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Qabul qilish", callback_data=f"driver_accept:{order_id}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"driver_reject:{order_id}"),
            ]
        ]
    )


def active_order_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🚫 Bekor qilish", callback_data=f"cancel_request:{order_id}")]]
    )


def cancel_request_admin_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"cancel_confirm:{order_id}")]]
    )


# ---------------------------------------------------------------------------
# HAYDOVCHI: BALANS
# ---------------------------------------------------------------------------

def balance_menu_kb() -> ReplyKeyboardMarkup:
    rows = [
        ["➕ Balansni to'ldirish"],
        ["🧾 Tarix"],
        ["⬅️ Asosiy menyu"],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def topup_review_kb(tx_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"topup_approve:{tx_id}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"topup_reject:{tx_id}"),
            ]
        ]
    )


# ---------------------------------------------------------------------------
# ADMIN: ZAKAZLAR
# ---------------------------------------------------------------------------

def admin_order_actions_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➡️ Navbatdagi shopirga yo'naltirish", callback_data=f"admin_reassign:{order_id}")],
            [InlineKeyboardButton("🗑 O'chirish", callback_data=f"admin_delete_order:{order_id}")],
        ]
    )


# ---------------------------------------------------------------------------
# ADMIN: SHOPIRLAR
# ---------------------------------------------------------------------------

def admin_driver_actions_kb(driver_id: int, is_enabled: bool, is_vip: bool) -> InlineKeyboardMarkup:
    enable_text = "🚫 Nofaol qilish" if is_enabled else "✅ Faol qilish"
    vip_text = "⭐ VIP olib tashlash" if is_vip else "⭐ VIP berish"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(enable_text, callback_data=f"admin_toggle_active:{driver_id}")],
            [InlineKeyboardButton(vip_text, callback_data=f"admin_toggle_vip:{driver_id}")],
            [
                InlineKeyboardButton("➕ Balans to'ldirish", callback_data=f"admin_balance_add:{driver_id}"),
                InlineKeyboardButton("➖ Balansdan yechish", callback_data=f"admin_balance_sub:{driver_id}"),
            ],
            [InlineKeyboardButton("🧾 Tranzaksiyalar", callback_data=f"admin_driver_tx:{driver_id}")],
            [InlineKeyboardButton("🗑 Haydovchini o'chirish", callback_data=f"admin_delete_driver:{driver_id}")],
        ]
    )


def confirm_delete_driver_kb(driver_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Ha, o'chirish", callback_data=f"admin_delete_driver_confirm:{driver_id}"),
                InlineKeyboardButton("⬅️ Bekor qilish", callback_data="admin_delete_driver_abort"),
            ]
        ]
    )


# ---------------------------------------------------------------------------
# ADMIN: NAVBAT BOSHQARISH
# ---------------------------------------------------------------------------

def admin_queue_item_kb(driver_id: int, direction_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⬆️", callback_data=f"queue_up:{direction_id}:{driver_id}"),
                InlineKeyboardButton("⬇️", callback_data=f"queue_down:{direction_id}:{driver_id}"),
                InlineKeyboardButton("❌", callback_data=f"queue_remove:{direction_id}:{driver_id}"),
            ]
        ]
    )


# ---------------------------------------------------------------------------
# ADMIN: ARIZALAR
# ---------------------------------------------------------------------------

def application_actions_kb(app_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Qabul qilish", callback_data=f"app_approve:{app_id}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"app_reject:{app_id}"),
            ]
        ]
    )


# ---------------------------------------------------------------------------
# ADMIN: XABAR YUBORISH (broadcast)
# ---------------------------------------------------------------------------

def broadcast_target_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📣 HAMMAGA", callback_data="bc_all")],
            [InlineKeyboardButton("🚗 HAYDOVCHILARGA", callback_data="bc_drivers")],
            [InlineKeyboardButton("🧑 YO'LOVCHILARGA", callback_data="bc_clients")],
            [InlineKeyboardButton("🚗 HAYDOVCHIGA", callback_data="bc_driver_one")],
            [InlineKeyboardButton("🧑 YO'LOVCHIGA", callback_data="bc_client_one")],
        ]
    )
