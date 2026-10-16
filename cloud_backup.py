import json
import os
import re
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import boto3
from apscheduler.schedulers.background import BackgroundScheduler
from botocore.config import Config


RETENTION_DAYS = 30
BACKUP_KEY_PREFIX = "assessment-backup-"


@dataclass(frozen=True)
class R2BackupConfig:
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket: str
    prefix: str
    hour: int

    @classmethod
    def from_environment(cls):
        account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
        access_key_id = os.getenv("R2_ACCESS_KEY_ID", "").strip()
        secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY", "")
        bucket = os.getenv("R2_BUCKET", "").strip()
        prefix = os.getenv("R2_BACKUP_PREFIX", "school-assessment/backups").strip("/")
        try:
            hour = int(os.getenv("CLOUD_BACKUP_HOUR", "2"))
        except ValueError as error:
            raise ValueError("CLOUD_BACKUP_HOUR must be an integer from 0 to 23.") from error

        config = cls(account_id, access_key_id, secret_access_key, bucket, prefix, hour)
        config.validate()
        return config

    def validate(self):
        if not re.fullmatch(r"[a-fA-F0-9]{32}", self.account_id):
            raise ValueError("R2_ACCOUNT_ID must be the 32-character Cloudflare account ID.")
        if not self.access_key_id or not self.secret_access_key:
            raise ValueError("Set R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY.")
        if not self.bucket:
            raise ValueError("Set R2_BUCKET to a private Cloudflare R2 bucket.")
        if not 0 <= self.hour <= 23:
            raise ValueError("CLOUD_BACKUP_HOUR must be an integer from 0 to 23.")
        if any(part in {".", ".."} for part in self.prefix.split("/")):
            raise ValueError("R2_BACKUP_PREFIX must not contain '.' or '..' path components.")

    @property
    def endpoint_url(self):
        return f"https://{self.account_id}.r2.cloudflarestorage.com"

    @property
    def object_prefix(self):
        return f"{self.prefix}/{BACKUP_KEY_PREFIX}" if self.prefix else BACKUP_KEY_PREFIX


def create_r2_client(config):
    return boto3.client(
        "s3",
        endpoint_url=config.endpoint_url,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=10,
            read_timeout=60,
        ),
    )


def quote_mysql_identifier(value):
    return f"`{value.replace('`', '``')}`"


def write_mysql_snapshot(connection_factory, output_path):
    connection = connection_factory()
    try:
        with connection.cursor() as cursor, output_path.open("w", encoding="utf-8", newline="\n") as dump:
            cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            dump.write("SET FOREIGN_KEY_CHECKS=0;\n")

            cursor.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
            table_rows = cursor.fetchall()
            for table_row in table_rows:
                table_name = next(iter(table_row.values()))
                quoted_table = quote_mysql_identifier(table_name)

                cursor.execute(f"SHOW CREATE TABLE {quoted_table}")
                create_row = cursor.fetchone()
                create_statement = list(create_row.values())[1]
                dump.write(f"\nDROP TABLE IF EXISTS {quoted_table};\n{create_statement};\n")

                cursor.execute(f"SELECT * FROM {quoted_table}")
                while True:
                    rows = cursor.fetchmany(500)
                    if not rows:
                        break
                    columns = list(rows[0].keys())
                    quoted_columns = ", ".join(quote_mysql_identifier(column) for column in columns)
                    placeholders = ", ".join(["%s"] * len(columns))
                    insert = f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({placeholders})"
                    for row in rows:
                        statement = cursor.mogrify(insert, tuple(row[column] for column in columns))
                        if isinstance(statement, bytes):
                            statement = statement.decode("utf-8")
                        dump.write(f"{statement};\n")

            dump.write("\nSET FOREIGN_KEY_CHECKS=1;\n")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def build_backup_archive(database_engine, database_path, connection_factory, uploads_dir, archive_path):
    database_engine = database_engine.lower()
    uploads_dir = Path(uploads_dir)
    database_path = Path(database_path)
    archive_path = Path(archive_path)
    upload_count = 0

    with tempfile.TemporaryDirectory(prefix="assessment-backup-") as temp_dir:
        temp_dir = Path(temp_dir)
        if database_engine == "sqlite":
            if not database_path.is_file():
                raise FileNotFoundError(f"SQLite database not found: {database_path}")
            snapshot_path = temp_dir / "assessment.sqlite3"
            with closing(sqlite3.connect(str(database_path), timeout=30)) as source:
                with closing(sqlite3.connect(str(snapshot_path))) as snapshot:
                    source.backup(snapshot)
            database_archive_path = "database/assessment.sqlite3"
        elif database_engine == "mysql":
            snapshot_path = temp_dir / "assessment.sql"
            write_mysql_snapshot(connection_factory, snapshot_path)
            database_archive_path = "database/assessment.sql"
        else:
            raise ValueError(f"Unsupported database engine for backup: {database_engine}")

        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "database_engine": database_engine,
            "includes_uploads": True,
        }

        with zipfile.ZipFile(
            archive_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            archive.write(snapshot_path, database_archive_path)
            for path in uploads_dir.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    archive.write(path, Path("uploads") / path.relative_to(uploads_dir))
                    upload_count += 1
            manifest["upload_file_count"] = upload_count
            archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")


def remove_expired_backups(client, config):
    paginator = client.get_paginator("list_objects_v2")
    backups = []
    for page in paginator.paginate(Bucket=config.bucket, Prefix=config.object_prefix):
        for item in page.get("Contents", []):
            key = item["Key"]
            if key.startswith(config.object_prefix) and key.endswith(".zip"):
                backups.append(key)

    backups.sort(reverse=True)
    expired = backups[RETENTION_DAYS:]
    for key in expired:
        client.delete_object(Bucket=config.bucket, Key=key)
    return len(expired)


def run_cloud_backup(database_engine, database_path, connection_factory, uploads_dir, config=None, client=None):
    config = config or R2BackupConfig.from_environment()
    config.validate()
    client = client or create_r2_client(config)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    object_key = f"{config.object_prefix}{timestamp}.zip"
    with tempfile.TemporaryDirectory(prefix="assessment-cloud-backup-") as temp_dir:
        archive_path = Path(temp_dir) / "assessment-backup.zip"
        build_backup_archive(
            database_engine, database_path, connection_factory, uploads_dir, archive_path
        )
        client.upload_file(
            str(archive_path),
            config.bucket,
            object_key,
            ExtraArgs={"ContentType": "application/zip"},
        )
        uploaded = client.head_object(Bucket=config.bucket, Key=object_key)
        if uploaded.get("ContentLength") != archive_path.stat().st_size:
            raise RuntimeError("Cloud backup upload verification failed: object size does not match.")

    deleted_count = remove_expired_backups(client, config)
    print(f"Cloud backup uploaded to {object_key}; removed {deleted_count} expired backup(s).")
    return {"key": object_key, "deleted": deleted_count}


def start_cloud_backup_scheduler(database_engine, database_path, connection_factory, uploads_dir):
    if os.getenv("CLOUD_BACKUP_ENABLED", "0").strip().lower() not in {"1", "true", "yes"}:
        print("Cloud backups are disabled. Set CLOUD_BACKUP_ENABLED=1 after configuring R2.")
        return None

    config = R2BackupConfig.from_environment()
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_cloud_backup,
        trigger="cron",
        hour=config.hour,
        minute=0,
        args=[database_engine, database_path, connection_factory, uploads_dir, config],
        id="daily-cloud-backup",
        replace_existing=True,
        next_run_time=datetime.now().astimezone(),
        coalesce=True,
        max_instances=1,
        misfire_grace_time=24 * 60 * 60,
    )
    scheduler.start()
    print(
        f"Daily Cloudflare R2 backups enabled for {config.hour:02d}:00 local time "
        f"with {RETENTION_DAYS}-day retention."
    )
    return scheduler


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")

    from app import DB_ENGINE, DB_PATH, UPLOAD_DIR, db

    result = run_cloud_backup(DB_ENGINE, DB_PATH, db, UPLOAD_DIR)
    print(f"Backup uploaded: {result['key']}")
    print(f"Expired backups deleted: {result['deleted']}")
