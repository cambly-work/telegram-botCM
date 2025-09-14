# db.py
import logging
import os
from typing import Optional, Any, AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import asyncpg
import re

logger = logging.getLogger("db")

_pool: Optional[asyncpg.Pool] = None


def _schema_path() -> str:
    return os.path.join(os.path.dirname(__file__), "schema.sql")


# ---------- SQL splitter, aware of $$...$$, $tag$...$tag$, '...', "..." ----------
_dollar_tag_re = re.compile(r"\$[A-Za-z_][A-Za-z_0-9]*\$|\$\$")

def _split_sql_statements(sql: str) -> list[str]:
    """
    Разбивает SQL-скрипт на отдельные операторы по ';',
    игнорируя ';' внутри:
      - одинарных кавычек '...'
      - двойных кавычек "...";
      - dollar-quoted блоков $$...$$ или $tag$...$tag$.

    Возвращает список операторов БЕЗ завершающей ';'.
    """
    sql = (sql or "").replace("\ufeff", "")  # убрать BOM
    stmts = []
    buf = []
    i = 0
    n = len(sql)

    in_single = False
    in_double = False
    in_dollar = False
    dollar_tag = None  # например: $$ или $tag$

    while i < n:
        ch = sql[i]

        # внутри dollar-quote
        if in_dollar:
            if sql.startswith(dollar_tag, i):
                buf.append(dollar_tag)
                i += len(dollar_tag)
                in_dollar = False
                dollar_tag = None
                continue
            buf.append(ch)
            i += 1
            continue

        # внутри '...'
        if in_single:
            buf.append(ch)
            # экранирование через два одинарных апострофа '' Postgres понимает,
            # но здесь достаточно простой проверки backslash'а
            if ch == "'" and (i == 0 or sql[i - 1] != "\\"):
                in_single = False
            i += 1
            continue

        # внутри "...":
        if in_double:
            buf.append(ch)
            if ch == '"' and (i == 0 or sql[i - 1] != "\\"):
                in_double = False
            i += 1
            continue

        # вход в dollar-quote
        if ch == "$":
            m = _dollar_tag_re.match(sql, i)
            if m:
                tag = m.group(0)
                in_dollar = True
                dollar_tag = tag
                buf.append(tag)
                i += len(tag)
                continue

        # вход в обычные кавычки
        if ch == "'":
            in_single = True
            buf.append(ch)
            i += 1
            continue
        if ch == '"':
            in_double = True
            buf.append(ch)
            i += 1            # noqa
            continue

        # разделитель операторов
        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                stmts.append(stmt)
            buf = []
            i += 1
            continue

        # обычный символ
        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts
# -------------------------------------------------------------------------------

def _strip_sql_line_comments(chunk: str) -> str:
    """
    Убираем строки, состоящие только из комментариев '-- ...' или пустые.
    ВАЖНО: вызывать уже ПОСЛЕ разбиения по операторам, чтобы не задеть
    комментарии внутри функций/процедур.
    """
    cleaned_lines = []
    for line in (chunk or "").splitlines():
        s = line.strip()
        if s.startswith("--") or s == "":
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def _redact_dsn(dsn: str) -> str:
    """Скрыть пароль в DSN для логов."""
    try:
        p = urlparse(dsn)
        if p.password:
            netloc = p.netloc.replace(f":{p.password}@", ":***@")
            return p._replace(netloc=netloc).geturl()
    except Exception:
        pass
    return dsn


async def init_db(dsn: str) -> None:
    """
    Инициализирует пул подключений и прогоняет schema.sql при первом запуске.
    Повторные вызовы — no-op.
    """
    global _pool
    if _pool:
        return

    logger.info("Connecting PostgreSQL: %s", _redact_dsn(dsn))
    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=1,
        max_size=10,
        command_timeout=60,
        init=_on_connect_init,
    )
    logger.info("PostgreSQL pool created")

    schema_file = _schema_path()
    if os.path.exists(schema_file):
        await _run_schema(schema_file)
        logger.info("Schema applied from %s", schema_file)
    else:
        logger.warning("Schema file not found at %s — skipping", schema_file)


async def _on_connect_init(conn: asyncpg.Connection) -> None:
    """Инициализация state для каждого нового соединения пула."""
    # единая тайм-зона на БД-уровне
    await conn.execute("SET TIME ZONE 'UTC'")


async def _run_schema(schema_file_path: str) -> None:
    """
    Безопасный прогон schema.sql:
    - корректно разбивает операторы;
    - вычищает «пустые»/комментарные блоки;
    - гарантирует наличие ';' перед выполнением.
    """
    if not schema_file_path or not os.path.exists(schema_file_path):
        logger.info("Schema file not found or not provided: %s", schema_file_path)
        return

    logger.info("Applying schema from: %s", schema_file_path)
    with open(schema_file_path, "r", encoding="utf-8") as f:
        sql = f.read()

    # Разбиваем умным сплиттером, чтобы не резать функции/процедуры
    statements = _split_sql_statements(sql)

    assert _pool is not None, "DB pool is not initialized"
    async with _pool.acquire() as conn:
        for idx, raw_stmt in enumerate(statements, start=1):
            # удаляем полностью-комментарные строки и лишние пустые
            stmt = _strip_sql_line_comments(raw_stmt)
            if not stmt:
                continue
            try:
                final_stmt = stmt if stmt.endswith(";") else stmt + ";"
                await conn.execute(final_stmt)
            except Exception:
                logger.error("Schema statement failed (chunk #%s):\n%s", idx, stmt)
                raise
    logger.info("Schema applied successfully.")


async def close_db() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL pool closed")


# ──────────────────────────────────────────────────────────────────────────────
# Базовые helpers
# ──────────────────────────────────────────────────────────────────────────────
async def fetch(query: str, *args: Any) -> list[asyncpg.Record]:
    assert _pool is not None, "DB pool is not initialized"
    async with _pool.acquire() as conn:
        return await conn.fetch(query, *args)

async def fetchrow(query: str, *args: Any) -> Optional[asyncpg.Record]:
    assert _pool is not None, "DB pool is not initialized"
    async with _pool.acquire() as conn:
        return await conn.fetchrow(query, *args)

async def fetchval(query: str, *args: Any) -> Any:
    assert _pool is not None, "DB pool is not initialized"
    async with _pool.acquire() as conn:
        return await conn.fetchval(query, *args)

async def execute(query: str, *args: Any) -> str:
    assert _pool is not None, "DB pool is not initialized"
    async with _pool.acquire() as conn:
        return await conn.execute(query, *args)

async def execute_many(query: str, args_seq: list[tuple[Any, ...]]) -> None:
    """
    Батч-выполнение одного и того же запроса с разными параметрами (в транзакции).
    Пример: await execute_many("INSERT INTO t(a,b) VALUES($1,$2)", [(1,2),(3,4)])
    """
    assert _pool is not None, "DB pool is not initialized"
    async with _pool.acquire() as conn:
        async with conn.transaction():
            for args in args_seq:
                await conn.execute(query, *args)


# ──────────────────────────────────────────────────────────────────────────────
# Расширенные helpers
# ──────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    """
    Ручной захват соединения из пула.
    Пример:
        async with db.acquire() as conn:
            await conn.execute(...)
    """
    assert _pool is not None, "DB pool is not initialized"
    conn = await _pool.acquire()
    try:
        yield conn
    finally:
        await _pool.release(conn)

@asynccontextmanager
async def transaction() -> AsyncIterator[asyncpg.Connection]:
    """
    Контекстный менеджер транзакции.
    Пример:
        async with db.transaction() as conn:
            await conn.execute(...)
            await conn.execute(...)
    """
    assert _pool is not None, "DB pool is not initialized"
    async with _pool.acquire() as conn:
        async with conn.transaction():
            yield conn


# ──────────────────────────────────────────────────────────────────────────────
# Диагностика
# ──────────────────────────────────────────────────────────────────────────────
async def db_health() -> bool:
    """Простой healthcheck БД."""
    try:
        val = await fetchval("SELECT 1")
        return val == 1
    except Exception as e:
        logger.warning("DB healthcheck failed: %s", e)
        return False

async def is_db_connected() -> bool:
    """Быстрая проверка соединения с БД."""
    try:
        await fetchrow("SELECT 1")
        return True
    except Exception as e:
        logger.error("Database connection check failed: %s", e)
        return False
