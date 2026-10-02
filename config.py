import os

# === SOZLAMALAR ===

# BotFather'dan olingan token shu yerga yoziladi (yoki muhit o'zgaruvchisi orqali)
BOT_TOKEN = os.getenv("BOT_TOKEN", "8246805236:AAEbhsr0rvasyN8yZL0hAxjU9CBcn-UEuVk")

# Admin(lar)ning Telegram ID raqamlari (bir nechta bo'lishi mumkin)
# Telegram ID ni bilish uchun @userinfobot ga yozing
ADMIN_IDS = [
    5821724830,  # <-- shu yerga o'z Telegram ID raqamingizni yozing
]

# Supabase (Postgres) ulanish manzili — Supabase > Connect > Session pooler.
# Faqat muhit o'zgaruvchisi orqali bering (kodga yozmang).
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres.wlsfkjyfqxoyteietkba:Mardon.1607@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres")

# Boshlang'ich yo'nalishlar ro'yxati (bot birinchi marta ishga tushganda bazaga yoziladi)
# Keyinchalik directions jadvaliga to'g'ridan-to'g'ri qo'shish/o'chirish mumkin
DEFAULT_DIRECTIONS = [
    "O'qchi - Yaypan",
    "Yaypan - O'qchi"
]

# Bitta zakazda qatnashuvchilar soni uchun variantlar
PASSENGER_COUNTS = [1, 2, 3, 4]
 
# Mashinada nechta yo'lovchi sig'adi (haydovchi bir nechta zakazni birlashtirib olishi mumkin)
CAR_CAPACITY = 4
 
# Haydovchiga taklif qilingan zakazni qabul/rad qilish uchun berilgan vaqt (soniyada)
OFFER_TIMEOUT_SECONDS = 90
 
# Zakaz yaratilgandan keyin hech kim qabul qilmasa, necha soniyadan keyin
# avtomatik bekor qilinishi va mijozga xabar berilishi kerak
ORDER_EXPIRY_SECONDS = 900
 
# Tranzaksiya turlari va holatlari uchun ko'rinadigan nomlar
TX_TYPE_LABELS = {
    "topup_request": "Balansni to'ldirish",
    "order_fee": "Zakaz xizmat haqi",
    "admin_topup": "Admin to'ldirdi",
    "admin_withdraw": "Admin yechdi",
}
TX_STATUS_LABELS = {
    "pending": "⏳ Kutilmoqda",
    "completed": "✅ Amalga oshirildi",
    "rejected": "❌ Rad etildi",
}
 
