# O'qchi-Yaypan Taxi Telegram Bot (python-telegram-bot versiyasi)

Bu loyiha `python-telegram-bot` kutubxonasi asosida qurilgan — bu kutubxona
sizning serveringizda avval to'g'ridan-to'g'ri (proxysiz) ishlagani sababli shu
versiya tanlandi.

## O'rnatish

1. Python 3.10+ kerak.
2. Kutubxonalarni o'rnating:
   ```
   pip install -r requirements.txt
   ```
3. Supabase: loyiha oching → **Connect → Session pooler** dagi manzilni nusxalang va muhit o'zgaruvchisi qiling:
   ```
   DATABASE_URL=postgresql://postgres.xxxx:PAROL@aws-0-xxx.pooler.supabase.com:5432/postgres
   BOT_TOKEN=...
   ```
   Jadvallar bot birinchi ishga tushganda o'zi yaratiladi.
4. `config.py` faylini oching:
   - `BOT_TOKEN` — @BotFather'dan olingan tokenni yozing.
     ⚠️ Agar avval boshqa joyda (masalan boshqa suhbatda) tokeningizni ulashgan
     bo'lsangiz, @BotFather orqali uni bekor qilib (`Revoke`), yangisini oling.
   - `ADMIN_IDS` — o'zingizning Telegram ID raqamingizni kiriting (@userinfobot).
   - `DEFAULT_DIRECTIONS` — kerakli yo'nalishlar ro'yxatini o'zgartiring.
5. Botni ishga tushiring:
   ```
   python main.py
   ```

Birinchi marta `ADMIN_IDS` ichidagi ID bilan botga `/start` yozganingizda,
sizga avtomatik admin roli beriladi.

## Bo'limlar

### Yo'lovchi
- 🚕 Taxi zakaz qilish → yo'nalish → yo'lovchilar soni → telefon raqami → "mashina kutilmoqda" holati.
- Bitta foydalanuvchi bir vaqtda faqat bitta faol zakazga ega bo'ladi.
- Haydovchi topilgach, uning ismi va mashinasi ko'rsatiladi.

### Haydovchi
- "Haydovchi bo'lish" orqali ariza yuboriladi, admin tasdiqlagach avtomatik haydovchi bo'ladi.
- "Haydovchi paneli" → "Liniyaga chiqish" → yo'nalish tanlanadi → navbatga qo'shiladi.
- Navbat FIFO; VIP haydovchilar liniyaga chiqqanda navbat boshiga qo'yiladi.
- **O'rindiq to'ldirish modeli**: mashinada 4 o'rin bor (config.py dagi `CAR_CAPACITY`). Haydovchiga bo'sh joyiga mos keladigan barcha kutilayotgan zakazlar bir vaqtda taklif qilinadi (har biriga ✅ Qabul / ❌ Rad etish tugmalari bilan).
- Zakaz qabul qilinganda, agar unga endi sig'maydigan boshqa taklif qilingan zakaz bo'lsa, u avtomatik undan bo'shatilib, navbatdagi keyingi haydovchiga (yoki keyinroq shu haydovchiga, agar joy bo'shasa) taklif qilinadi.
- Har bir taklifga 60 soniya (config.py dagi `OFFER_TIMEOUT_SECONDS`) beriladi — javob bo'lmasa, avtomatik bekor qilinib qayta taqsimlanadi.
- Rad etilgan zakaz o'sha haydovchiga qayta taklif qilinmaydi (boshqasiga o'tadi).
- Mashina to'lganda (4/4) haydovchi **avtomatik** navbatdan chiqib "safarda" holatiga o'tadi.
- Haydovchi istalgan vaqtda "🚀 Jo'nash" tugmasini bosib, hozirgi yo'lovchilar bilan (mashina to'lmasa ham) yo'lga chiqishi mumkin.
- Safar tugagach "🏁 Safarni yakunlash" tugmasi bosiladi — shu safardagi barcha zakazlar yakunlanadi.

### Admin panel
- 📋 Faol zakazlar — o'chirish yoki navbatdagi haydovchiga qayta yo'naltirish.
- 🚦 Navbatdagi shopirlar — navbatni ko'rish, tartibini o'zgartirish, olib tashlash.
- 👨‍✈️ Shopirlar — faol/nofaol qilish, VIP status berish/olib tashlash, balansni boshqarish (to'ldirish/yechish, izoh bilan), tranzaksiyalar tarixini ko'rish, haydovchini butunlay o'chirish.
- 📝 Yangi arizalar — arizalar alohida xabar sifatida keladi (✅/❌ tugmalari bilan).
- 💰 Zakaz narxini belgilash — har bir qabul qilingan zakazdan avtomatik yechiladigan summani sozlash.
- 💳 Karta ma'lumotlari — haydovchilar balans to'ldirishda ko'radigan karta raqami va ism-familiyani sozlash.
- 📢 Xabar yuborish — HAMMAGA / HAYDOVCHILARGA / YO'LOVCHILARGA / bitta HAYDOVCHIGA / bitta YO'LOVCHIGA xabar yuborish (individual tanlovda ro'yxatdan raqam kiritiladi).

### Haydovchi balansi
- Har bir haydovchining balansi bor (so'mda). Admin belgilagan narx har bir qabul qilingan zakazdan avtomatik yechiladi va bu haydovchiga xabar qilinadi. Balans yetarli bo'lmasa, zakazni qabul qila olmaydi.
- "💰 Balans" → "➕ Balansni to'ldirish": summani kiritadi, karta ma'lumotlarini ko'radi, to'lov skrinshotini yuboradi → so'rov adminga (rasm + ✅/❌ tugmalar bilan) boradi → admin tasdiqlasa balans avtomatik to'ladi.
- "🧾 Tarix": barcha tranzaksiyalar (to'ldirish, zakaz xizmat haqi, qaytarilgan pul, admin tomonidan qo'lda o'zgartirishlar) holati bilan (kutilmoqda/amalga oshirildi/rad etildi) ko'rinadi.

### Faol zakazlar va bekor qilish
- Haydovchi "📋 Faol zakazlarim" orqali hozirgi qabul qilingan zakazlarini (telefon raqami, izohi bilan) ko'radi.
- Har bir faol zakaz ostida "🚫 Bekor qilish" tugmasi bor — bosilsa, adminga haydovchi va yo'lovchi telefon raqamlari bilan so'rov keladi.
- Admin "✅ Tasdiqlash" tugmasini bossa: zakaz bekor qilinadi, haydovchi bandligi bo'shaydi, va o'sha zakaz uchun yechilgan xizmat haqi to'liq haydovchi balansiga qaytariladi.

### Maxfiylik
- Yo'lovchining telefon raqami haydovchiga zakaz TAKLIF qilinganda ko'rinmaydi — faqat u zakazni qabul qilgandan keyin ko'rinadi.

## Loyihaning tuzilishi

```
taxi_bot_ptb/
├── config.py         # sozlamalar
├── database.py        # SQLite bilan ishlash
├── matching.py         # zakaz-haydovchi taqsimlash logikasi
├── keyboards.py        # tugmalar
├── states.py            # ConversationHandler holatlari
├── main.py              # botni ishga tushirish, barcha handlerlar ro'yxati
└── handlers/
    ├── common.py       # /start, asosiy menyu
    ├── passenger.py    # yo'lovchi oqimi
    ├── driver.py       # haydovchi oqimi
    └── admin.py        # admin panel
```

## Agar ulanish xatosi chiqsa

Agar `Cannot connect to host api.telegram.org` kabi xato chiqsa:
```
curl -4 -v https://api.telegram.org
```
buyrug'ini ishga tushiring va natijani tekshiring — bu odatda server tarmog'i
yoki IPv6 sozlamasi bilan bog'liq bo'ladi.
