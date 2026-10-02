"""
aiosqlite'ga o'xshash yupqa qatlam: asyncpg orqali Supabase (Postgres) bilan ishlaydi.
database.py'dagi so'rovlar deyarli o'zgarishsiz qoladi.
"""
import re
import asyncpg

from config import DATABASE_URL

# 'id' ustuni yo'q jadvallar (INSERT'dan keyin RETURNING id kerak emas)
_NO_ID_TABLES = {"order_rejections", "settings"}

_pool: asyncpg.Pool | None = None


class Row(dict):
    """aiosqlite.Row bilan moslik uchun (row_factory qiymati sifatida ishlatiladi)."""


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL o'rnatilmagan (Supabase ulanish manzili kerak)")
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
            ssl="require",
            statement_cache_size=0,  # Supabase pooler (pgbouncer) bilan ishlashi uchun
            command_timeout=30,
        )
    return _pool


async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _convert(sql: str) -> str:
    """SQLite sintaksisini Postgres'ga o'giradi: ? -> $1, INSERT OR IGNORE -> ON CONFLICT DO NOTHING."""
    ignore = re.match(r"\s*INSERT\s+OR\s+IGNORE\s+INTO", sql, re.I) is not None
    if ignore:
        sql = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", sql, count=1, flags=re.I)
        sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    n = 0

    def repl(_):
        nonlocal n
        n += 1
        return f"${n}"

    return re.sub(r"\?", repl, sql)


class _Cursor:
    def __init__(self, rows=None, lastrowid=None):
        self._rows = rows or []
        self.lastrowid = lastrowid

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return list(self._rows)


class _Connection:
    def __init__(self, conn: asyncpg.Connection):
        self._conn = conn
        self.row_factory = None  # moslik uchun; asyncpg Record dict(row) bilan ishlaydi

    async def execute(self, sql: str, params=()):
        sql = _convert(sql)
        params = list(params or [])
        head = sql.lstrip().split(None, 1)[0].upper()
        if head == "SELECT":
            return _Cursor(rows=await self._conn.fetch(sql, *params))
        if head == "INSERT":
            m = re.match(r"\s*INSERT\s+INTO\s+(\w+)", sql, re.I)
            table = m.group(1).lower() if m else ""
            if table not in _NO_ID_TABLES and "ON CONFLICT" not in sql.upper():
                row = await self._conn.fetchrow(sql + " RETURNING id", *params)
                return _Cursor(lastrowid=row["id"] if row else None)
        await self._conn.execute(sql, *params)
        return _Cursor()

    async def executescript(self, script: str):
        await self._conn.execute(script)

    async def commit(self):
        pass  # tranzaksiya blokdan chiqishda avtomatik commit qilinadi


class connect:
    """async with pg.connect() as db: ... — blok ichidagi hammasi bitta tranzaksiya."""

    async def __aenter__(self):
        self._pool = await _get_pool()
        self._raw = await self._pool.acquire()
        self._tr = self._raw.transaction()
        await self._tr.start()
        return _Connection(self._raw)

    async def __aexit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                await self._tr.commit()
            else:
                await self._tr.rollback()
        finally:
            await self._pool.release(self._raw)
        return False
