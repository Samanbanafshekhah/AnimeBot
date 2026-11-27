"""Provide the Store with PostgreSQL transactions and reusable connections."""
from contextlib import contextmanager

from psycopg_pool import ConnectionPool


class PostgresConnection:
    def __init__(self, database_url):
        self.pool = ConnectionPool(
            database_url, min_size=0, max_size=2, timeout=12, max_idle=60,
            kwargs={"autocommit": True, "connect_timeout": 8}, open=True,
            check=ConnectionPool.check_connection,
        )
        self.connection = None

    def execute(self, sql, values=()):
        sql = sql.replace("?", "%s")
        if self.connection is None:
            raise RuntimeError("Database queries require a transaction")
        return self.connection.execute(sql, values)

    def executemany(self, sql, rows):
        with self.connection.cursor() as cursor:
            cursor.executemany(sql.replace("?", "%s"), rows)

    @contextmanager
    def transaction(self):
        if self.connection is not None:
            with self.connection.transaction():
                yield
            return
        with self.pool.connection() as connection, connection.transaction():
            self.connection = connection
            try:
                yield
            finally:
                self.connection = None

    def close(self):
        self.pool.close()
