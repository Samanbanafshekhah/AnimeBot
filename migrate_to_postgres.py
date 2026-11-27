"""Copy the local SQLite data to the bot's Postgres database."""
import sqlite3
from contextlib import closing
from getpass import getpass
from dotenv import dotenv_values

from animeSuggest import BASE_DIR, Store


TABLES = {
    "users": "id,language",
    "history": "user_id,anime_id,status",
    "translations": "source_hash,text",
    "anime_titles": "anime_id,title,english_title",
    "watchlist": "user_id,anime_id,saved_at",
    "preferences": "user_id,genre,min_score,max_episodes",
}


def migrate(source, destination):
    counts = {}
    with destination.transaction():
        for table, columns in TABLES.items():
            order = " ORDER BY rowid" if table == "watchlist" else ""
            rows = source.execute(f"SELECT {columns} FROM {table}{order}").fetchall()
            placeholders = ",".join("?" for _ in columns.split(","))
            destination.db.executemany(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                rows,
            )
            counts[table] = len(rows)
    return counts


def main():
    path = BASE_DIR / "animebot.sqlite3"
    if not path.is_file():
        raise SystemExit("Local animebot.sqlite3 was not found.")
    configured = dotenv_values(BASE_DIR / ".env.render").get("DATABASE_URL")
    url = (configured or getpass("Postgres connection string: ")).strip()
    if not url.startswith(("postgresql://", "postgres://")):
        raise SystemExit("Enter a Postgres connection URL.")
    try:
        # A snapshot keeps the copy consistent across all tables.
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as source:
            source.execute("BEGIN")
            destination = Store(None, url)
            with closing(destination.db):
                counts = migrate(source, destination)
    except Exception as exc:
        raise SystemExit(f"Migration failed ({type(exc).__name__}).") from None
    print("Migration complete. Source rows processed:")
    for table, count in counts.items():
        print(f"  {table}: {count}")


if __name__ == "__main__":
    main()
