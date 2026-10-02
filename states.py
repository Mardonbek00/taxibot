# Zakaz berish (yo'lovchi)
ORDER_DIRECTION, ORDER_PCOUNT, ORDER_PHONE, ORDER_COMMENT = range(4)

# Haydovchi bo'lish (ariza)
DRIVER_NAME, DRIVER_PHONE, DRIVER_CAR = range(4, 7)

# Liniyaga chiqish (haydovchi)
DRIVER_ONLINE_DIRECTION = 7

# Balansni to'ldirish (haydovchi)
BALANCE_TOPUP_AMOUNT, BALANCE_TOPUP_SCREENSHOT = range(8, 10)

# Admin: zakaz narxini belgilash
ADMIN_SET_FEE_AMOUNT = 10

# Admin: karta ma'lumotlarini sozlash
ADMIN_SET_CARD_NUMBER, ADMIN_SET_CARD_NAME = range(11, 13)

# Admin: haydovchi balansini qo'lda o'zgartirish
ADMIN_ADJUST_AMOUNT, ADMIN_ADJUST_COMMENT = range(13, 15)

# Admin: xabar yuborish (broadcast)
BROADCAST_TARGET_NUMBER, BROADCAST_MESSAGE = range(15, 17)
