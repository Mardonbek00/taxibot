"""
Ma'lumotlar bazasi qatlami.
Barcha SQL so'rovlar va biznes-logika (navbat, zakaz taqsimlash) shu yerda joylashgan.
"""
import time

import pg
from config import DEFAULT_DIRECTIONS

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              BIGSERIAL PRIMARY KEY,
    telegram_id     BIGINT UNIQUE NOT NULL,
    full_name       TEXT,
    phone           TEXT,
    role            TEXT NOT NULL DEFAULT 'client',   -- client | driver | admin
    car_info        TEXT,
    driver_status   TEXT NOT NULL DEFAULT 'offline',  -- offline | online | busy
    is_enabled      INTEGER NOT NULL DEFAULT 1,
    is_vip          INTEGER NOT NULL DEFAULT 0,
    current_seats   INTEGER NOT NULL DEFAULT 0,
    balance         BIGINT NOT NULL DEFAULT 0,        -- so'mda
    created_at      BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS directions (
    id      BIGSERIAL PRIMARY KEY,
    name    TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id                  BIGSERIAL PRIMARY KEY,
    client_id           BIGINT NOT NULL,
    direction_id        BIGINT NOT NULL,
    phone               TEXT,
    passenger_count     INTEGER NOT NULL DEFAULT 1,
    comment             TEXT,
    status              TEXT NOT NULL DEFAULT 'kutilmoqda',
    driver_id           BIGINT,
    offered_to_driver   BIGINT,
    offer_expires_at    BIGINT,
    offer_message_id    BIGINT,
    created_at          BIGINT NOT NULL,
    updated_at          BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS driver_queue (
    id              BIGSERIAL PRIMARY KEY,
    driver_id       BIGINT NOT NULL,
    direction_id    BIGINT NOT NULL,
    position        BIGINT NOT NULL,
    joined_at       BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS driver_applications (
    id          BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    full_name   TEXT,
    phone       TEXT,
    car_info    TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_rejections (
    order_id    BIGINT NOT NULL,
    driver_id   BIGINT NOT NULL,
    PRIMARY KEY (order_id, driver_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id                  BIGSERIAL PRIMARY KEY,
    driver_id           BIGINT NOT NULL,
    type                TEXT NOT NULL,
    amount              BIGINT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'completed',
    comment             TEXT,
    screenshot_file_id  TEXT,
    order_id            BIGINT,
    created_at          BIGINT NOT NULL,
    updated_at          BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key     TEXT PRIMARY KEY,
    value   TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status, direction_id);
CREATE INDEX IF NOT EXISTS idx_queue_dir ON driver_queue (direction_id, position);
CREATE INDEX IF NOT EXISTS idx_tx_driver ON transactions (driver_id, id DESC);
"""

_TABLES = ("users", "directions", "orders", "driver_queue", "driver_applications",
           "order_rejections", "transactions", "settings")


def now() -> int:
    return int(time.time())


async def init_db():
    async with pg.connect() as db:
        await db.executescript(SCHEMA)

        # Supabase'ning ochiq API (anon kalit) orqali jadvallarga kirib bo'lmasligi uchun RLS yoqamiz.
        # Bot to'g'ridan-to'g'ri postgres roli bilan ulangani uchun RLS unga to'sqinlik qilmaydi.
        for t in _TABLES:
            await db.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")

        cur = await db.execute("SELECT COUNT(*) FROM directions")
        (count,) = await cur.fetchone()
        if count == 0:
            for name in DEFAULT_DIRECTIONS:
                await db.execute("INSERT INTO directions (name) VALUES (?)", (name,))
            await db.commit()


# ---------------------------------------------------------------------------
# USERS
# ---------------------------------------------------------------------------

async def get_or_create_user(telegram_id: int, full_name: str = None) -> dict:
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cur.fetchone()
        if row:
            return dict(row)
        await db.execute(
            "INSERT INTO users (telegram_id, full_name, created_at) VALUES (?, ?, ?)",
            (telegram_id, full_name, now()),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cur.fetchone()
        return dict(row)


async def get_user(telegram_id: int) -> dict | None:
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def update_user(telegram_id: int, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [telegram_id]
    async with pg.connect() as db:
        await db.execute(f"UPDATE users SET {cols} WHERE telegram_id=?", values)
        await db.commit()


async def list_drivers() -> list[dict]:
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute(
            "SELECT * FROM users WHERE role='driver' ORDER BY is_vip DESC, full_name"
        )
        return [dict(r) for r in await cur.fetchall()]


async def delete_driver(driver_id: int):
    """Haydovchini butunlay o'chiradi (rolini 'client'ga qaytaradi, navbatdan chiqaradi)."""
    async with pg.connect() as db:
        await db.execute("DELETE FROM driver_queue WHERE driver_id=?", (driver_id,))
        await db.execute(
            "UPDATE users SET role='client', driver_status='offline', current_seats=0, "
            "is_vip=0, is_enabled=1, car_info=NULL WHERE telegram_id=?",
            (driver_id,),
        )
        await db.commit()


async def get_user_by_id(user_id: int) -> dict | None:
    """id (PK) bo'yicha, ko'pincha driver_id/client_id sifatida telegram_id ishlatiladi"""
    return await get_user(user_id)


# ---------------------------------------------------------------------------
# DIRECTIONS
# ---------------------------------------------------------------------------

async def list_directions() -> list[dict]:
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute("SELECT * FROM directions ORDER BY id")
        return [dict(r) for r in await cur.fetchall()]


async def get_direction(direction_id: int) -> dict | None:
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute("SELECT * FROM directions WHERE id=?", (direction_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# DRIVER APPLICATIONS (haydovchi bo'lish uchun ariza)
# ---------------------------------------------------------------------------

async def create_driver_application(telegram_id: int, full_name: str, phone: str, car_info: str) -> int:
    async with pg.connect() as db:
        cur = await db.execute(
            "INSERT INTO driver_applications (telegram_id, full_name, phone, car_info, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (telegram_id, full_name, phone, car_info, now()),
        )
        await db.commit()
        return cur.lastrowid


async def get_application(app_id: int) -> dict | None:
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute("SELECT * FROM driver_applications WHERE id=?", (app_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def set_application_status(app_id: int, status: str):
    async with pg.connect() as db:
        await db.execute("UPDATE driver_applications SET status=? WHERE id=?", (status, app_id))
        await db.commit()


# ---------------------------------------------------------------------------
# DRIVER QUEUE (navbat)
# ---------------------------------------------------------------------------

async def queue_join(driver_id: int, direction_id: int, is_vip: bool):
    async with pg.connect() as db:
        # avval shu haydovchini shu yo'nalishdagi navbatdan tozalab qo'yamiz (takror bo'lmasin)
        await db.execute(
            "DELETE FROM driver_queue WHERE driver_id=? AND direction_id=?",
            (driver_id, direction_id),
        )
        if is_vip:
            cur = await db.execute(
                "SELECT MIN(position) FROM driver_queue WHERE direction_id=?", (direction_id,)
            )
            (min_pos,) = await cur.fetchone()
            position = (min_pos or 0) - 1000
        else:
            cur = await db.execute(
                "SELECT MAX(position) FROM driver_queue WHERE direction_id=?", (direction_id,)
            )
            (max_pos,) = await cur.fetchone()
            position = (max_pos or 0) + 1000
        await db.execute(
            "INSERT INTO driver_queue (driver_id, direction_id, position, joined_at) VALUES (?, ?, ?, ?)",
            (driver_id, direction_id, position, now()),
        )
        await db.commit()


async def queue_leave(driver_id: int, direction_id: int = None):
    async with pg.connect() as db:
        if direction_id is not None:
            await db.execute(
                "DELETE FROM driver_queue WHERE driver_id=? AND direction_id=?",
                (driver_id, direction_id),
            )
        else:
            await db.execute("DELETE FROM driver_queue WHERE driver_id=?", (driver_id,))
        await db.commit()


async def queue_list(direction_id: int) -> list[dict]:
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute(
            """SELECT dq.*, u.full_name, u.car_info, u.is_vip, u.driver_status
               FROM driver_queue dq JOIN users u ON u.telegram_id = dq.driver_id
               WHERE dq.direction_id=? ORDER BY dq.position ASC""",
            (direction_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def queue_front(direction_id: int) -> dict | None:
    rows = await queue_list(direction_id)
    for r in rows:
        if r["driver_status"] == "online":
            return r
    return None


async def queue_position(driver_id: int, direction_id: int) -> int | None:
    """Haydovchining shu yo'nalishdagi navbatda nechinchi o'rinda turganini qaytaradi (1-dan boshlab)."""
    rows = await queue_list(direction_id)
    for i, r in enumerate(rows, start=1):
        if r["driver_id"] == driver_id:
            return i
    return None


async def queue_move(driver_id: int, direction_id: int, delta_positions: int):
    """Admin uchun: navbatda haydovchini yuqoriga/pastga surish"""
    rows = await queue_list(direction_id)
    ids = [r["driver_id"] for r in rows]
    if driver_id not in ids:
        return
    idx = ids.index(driver_id)
    new_idx = max(0, min(len(ids) - 1, idx + delta_positions))
    if new_idx == idx:
        return
    ids.insert(new_idx, ids.pop(idx))
    async with pg.connect() as db:
        for i, drv_id in enumerate(ids):
            await db.execute(
                "UPDATE driver_queue SET position=? WHERE driver_id=? AND direction_id=?",
                (i * 1000, drv_id, direction_id),
            )
        await db.commit()


# ---------------------------------------------------------------------------
# ORDERS (zakazlar)
# ---------------------------------------------------------------------------

async def get_active_order_for_client(client_id: int) -> dict | None:
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute(
            "SELECT * FROM orders WHERE client_id=? AND status IN ('kutilmoqda','tasdiqlangan') "
            "ORDER BY id DESC LIMIT 1",
            (client_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def create_order(client_id: int, direction_id: int, phone: str, passenger_count: int, comment: str | None = None) -> int:
    async with pg.connect() as db:
        cur = await db.execute(
            "INSERT INTO orders (client_id, direction_id, phone, passenger_count, comment, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (client_id, direction_id, phone, passenger_count, comment, now(), now()),
        )
        await db.commit()
        return cur.lastrowid


async def get_order(order_id: int) -> dict | None:
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute("SELECT * FROM orders WHERE id=?", (order_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def list_waiting_orders(direction_id: int) -> list[dict]:
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute(
            "SELECT * FROM orders WHERE direction_id=? AND status='kutilmoqda' ORDER BY id",
            (direction_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def list_unoffered_waiting_orders(direction_id: int) -> list[dict]:
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute(
            "SELECT * FROM orders WHERE direction_id=? AND status='kutilmoqda' "
            "AND offered_to_driver IS NULL ORDER BY id",
            (direction_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def list_offered_orders(driver_id: int) -> list[dict]:
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute(
            "SELECT * FROM orders WHERE offered_to_driver=? AND status='kutilmoqda' ORDER BY id",
            (driver_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def set_order_offer(order_id: int, driver_id: int, expires_at: int):
    async with pg.connect() as db:
        await db.execute(
            "UPDATE orders SET offered_to_driver=?, offer_expires_at=? WHERE id=?",
            (driver_id, expires_at, order_id),
        )
        await db.commit()


async def set_offer_message_id(order_id: int, message_id: int | None):
    async with pg.connect() as db:
        await db.execute("UPDATE orders SET offer_message_id=? WHERE id=?", (message_id, order_id))
        await db.commit()


async def clear_order_offer(order_id: int):
    async with pg.connect() as db:
        await db.execute(
            "UPDATE orders SET offered_to_driver=NULL, offer_expires_at=NULL, offer_message_id=NULL WHERE id=?",
            (order_id,),
        )
        await db.commit()


async def list_driver_active_orders(driver_id: int) -> list[dict]:
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute(
            "SELECT * FROM orders WHERE driver_id=? AND status='tasdiqlangan' ORDER BY id",
            (driver_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def finish_driver_orders(driver_id: int):
    async with pg.connect() as db:
        await db.execute(
            "UPDATE orders SET status='yakunlangan', updated_at=? WHERE driver_id=? AND status='tasdiqlangan'",
            (now(), driver_id),
        )
        await db.commit()


async def get_driver_direction(driver_id: int) -> int | None:
    async with pg.connect() as db:
        cur = await db.execute("SELECT direction_id FROM driver_queue WHERE driver_id=? LIMIT 1", (driver_id,))
        row = await cur.fetchone()
        return row[0] if row else None


async def add_rejection(order_id: int, driver_id: int):
    async with pg.connect() as db:
        await db.execute(
            "INSERT OR IGNORE INTO order_rejections (order_id, driver_id) VALUES (?, ?)",
            (order_id, driver_id),
        )
        await db.commit()


async def get_rejected_order_ids(driver_id: int) -> set[int]:
    async with pg.connect() as db:
        cur = await db.execute("SELECT order_id FROM order_rejections WHERE driver_id=?", (driver_id,))
        rows = await cur.fetchall()
        return {r[0] for r in rows}


async def clear_rejections_for_order(order_id: int):
    async with pg.connect() as db:
        await db.execute("DELETE FROM order_rejections WHERE order_id=?", (order_id,))
        await db.commit()


async def list_active_orders() -> list[dict]:
    """Admin panel uchun: barcha kutilayotgan va tasdiqlangan zakazlar"""
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute(
            "SELECT * FROM orders WHERE status IN ('kutilmoqda','tasdiqlangan') ORDER BY id DESC"
        )
        return [dict(r) for r in await cur.fetchall()]


async def set_order_offered(order_ids: list[int], driver_id: int | None):
    if not order_ids:
        return
    async with pg.connect() as db:
        q = f"UPDATE orders SET offered_to_driver=? WHERE id IN ({','.join('?' * len(order_ids))})"
        await db.execute(q, [driver_id, *order_ids])
        await db.commit()


async def set_order_status(order_id: int, status: str, driver_id: int | None = None):
    async with pg.connect() as db:
        if driver_id is not None:
            await db.execute(
                "UPDATE orders SET status=?, driver_id=?, offered_to_driver=NULL, updated_at=? WHERE id=?",
                (status, driver_id, now(), order_id),
            )
        else:
            await db.execute(
                "UPDATE orders SET status=?, offered_to_driver=NULL, updated_at=? WHERE id=?",
                (status, now(), order_id),
            )
        await db.commit()


async def get_active_order_for_driver(driver_id: int) -> dict | None:
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute(
            "SELECT * FROM orders WHERE driver_id=? AND status='tasdiqlangan' ORDER BY id DESC LIMIT 1",
            (driver_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def clear_offer_for_driver(driver_id: int):
    async with pg.connect() as db:
        await db.execute(
            "UPDATE orders SET offered_to_driver=NULL WHERE offered_to_driver=? AND status='kutilmoqda'",
            (driver_id,),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# SOZLAMALAR (order narxi, karta ma'lumotlari va h.k.)
# ---------------------------------------------------------------------------

async def get_setting(key: str, default: str | None = None) -> str | None:
    async with pg.connect() as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else default


async def set_setting(key: str, value: str):
    async with pg.connect() as db:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# BALANS VA TRANZAKSIYALAR
# ---------------------------------------------------------------------------

async def update_balance(driver_id: int, delta: int):
    async with pg.connect() as db:
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE telegram_id=?", (delta, driver_id)
        )
        await db.commit()


async def create_transaction(
    driver_id: int,
    tx_type: str,
    amount: int,
    status: str = "completed",
    comment: str | None = None,
    screenshot_file_id: str | None = None,
    order_id: int | None = None,
) -> int:
    async with pg.connect() as db:
        cur = await db.execute(
            "INSERT INTO transactions (driver_id, type, amount, status, comment, screenshot_file_id, "
            "order_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (driver_id, tx_type, amount, status, comment, screenshot_file_id, order_id, now(), now()),
        )
        await db.commit()
        return cur.lastrowid


async def get_transaction(tx_id: int) -> dict | None:
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute("SELECT * FROM transactions WHERE id=?", (tx_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def set_transaction_status(tx_id: int, status: str, comment: str | None = None):
    async with pg.connect() as db:
        if comment is not None:
            await db.execute(
                "UPDATE transactions SET status=?, comment=?, updated_at=? WHERE id=?",
                (status, comment, now(), tx_id),
            )
        else:
            await db.execute(
                "UPDATE transactions SET status=?, updated_at=? WHERE id=?",
                (status, now(), tx_id),
            )
        await db.commit()


async def list_driver_transactions(driver_id: int, limit: int = 20) -> list[dict]:
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute(
            "SELECT * FROM transactions WHERE driver_id=? ORDER BY id DESC LIMIT ?",
            (driver_id, limit),
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_order_fee_transaction(order_id: int) -> dict | None:
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute(
            "SELECT * FROM transactions WHERE order_id=? AND type='order_fee' AND status='completed' "
            "ORDER BY id DESC LIMIT 1",
            (order_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# XABAR YUBORISH (broadcast) UCHUN RO'YXATLAR
# ---------------------------------------------------------------------------

async def list_all_user_ids() -> list[int]:
    async with pg.connect() as db:
        cur = await db.execute("SELECT telegram_id FROM users")
        return [r[0] for r in await cur.fetchall()]


async def list_driver_user_ids() -> list[int]:
    async with pg.connect() as db:
        cur = await db.execute("SELECT telegram_id FROM users WHERE role='driver'")
        return [r[0] for r in await cur.fetchall()]


async def list_client_user_ids() -> list[int]:
    async with pg.connect() as db:
        cur = await db.execute("SELECT telegram_id FROM users WHERE role='client'")
        return [r[0] for r in await cur.fetchall()]


async def list_client_users() -> list[dict]:
    async with pg.connect() as db:
        db.row_factory = pg.Row
        cur = await db.execute("SELECT * FROM users WHERE role='client' ORDER BY full_name")
        return [dict(r) for r in await cur.fetchall()]
