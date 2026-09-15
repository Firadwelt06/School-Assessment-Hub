"""Copy an existing SQLite assessment database into the configured MySQL database."""

import os
import sqlite3
import sys

import pymysql
from pathlib import Path
from dotenv import load_dotenv

# Load project .env so MYSQL_* settings are available when running this script
load_dotenv(Path(__file__).resolve().parent / ".env")


TABLES = (
    "users",
    "questions",
    "exams",
    "exam_questions",
    "attempts",
    "responses",
    "rewrite_permissions",
    "settings",
    "subject_access_codes",
)


def mysql_connection():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER",),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "school_assessment"),
        charset="utf8mb4",
        autocommit=False,
    )


def main():
    sqlite_path = sys.argv[1] if len(sys.argv) > 1 else os.getenv("DATABASE_PATH", "assessment.db")
    source = sqlite3.connect(sqlite_path)
    source.row_factory = sqlite3.Row
    target = mysql_connection()
    try:
        with target.cursor() as cursor:
            for table in reversed(TABLES):
                cursor.execute(f"DELETE FROM `{table}`")
            for table in TABLES:
                rows = source.execute(f"SELECT * FROM `{table}`").fetchall()
                if not rows:
                    continue
                columns = rows[0].keys()
                names = ", ".join(f"`{column}`" for column in columns)
                placeholders = ", ".join(["%s"] * len(columns))
                cursor.executemany(
                    f"INSERT INTO `{table}` ({names}) VALUES ({placeholders})",
                    [tuple(row[column] for column in columns) for row in rows],
                )
                print(f"Copied {len(rows)} rows from {table}")
        target.commit()
    except Exception:
        target.rollback()
        raise
    finally:
        source.close()
        target.close()


if __name__ == "__main__":
    main()
