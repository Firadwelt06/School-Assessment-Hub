import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath


DATABASE_MEMBER = "database/assessment.sqlite3"
MYSQL_DATABASE_MEMBER = "database/assessment.sql"
MANIFEST_MEMBER = "manifest.json"
MAX_BACKUP_BYTES = 4 * 1024 * 1024 * 1024


class LocalBackupError(ValueError):
    pass


def build_local_backup(database_engine, database_path, connection_factory, uploads_dir, archive_path):
    from cloud_backup import build_backup_archive

    build_backup_archive(
        database_engine,
        database_path,
        connection_factory,
        uploads_dir,
        archive_path,
    )


def _iter_mysql_statements(sql_path):
    with Path(sql_path).open("r", encoding="utf-8") as source:
        def characters():
            while chunk := source.read(65536):
                yield from chunk

        chars = iter(characters())
        statement = []
        quote = None
        escaped = False
        pending = None
        while True:
            character = pending if pending is not None else next(chars, None)
            pending = None
            if character is None:
                break
            statement.append(character)
            if quote:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    following = next(chars, None)
                    if following == quote:
                        statement.append(following)
                    else:
                        quote = None
                        pending = following
            elif character in {"'", '"', "`"}:
                quote = character
            elif character == ";":
                statement_text = "".join(statement).strip()
                if statement_text:
                    yield statement_text[:-1].strip()
                statement = []
        if quote:
            raise LocalBackupError("The MySQL backup contains an unterminated SQL string.")
        if "".join(statement).strip():
            raise LocalBackupError("The MySQL backup contains an incomplete SQL statement.")


def _validate_mysql_dump(sql_path):
    tables = set()
    statement_count = 0
    for statement in _iter_mysql_statements(sql_path):
        statement_count += 1
        match = re.match(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?([A-Za-z0-9_]+)`?",
            statement,
            re.IGNORECASE,
        )
        if match:
            tables.add(match.group(1).casefold())
    if statement_count < 4 or not {"users", "settings", "attempts"}.issubset(tables):
        raise LocalBackupError("The MySQL backup does not contain a complete School Assessment Hub database.")


def _validate_member_name(name):
    if "\\" in name or "\x00" in name:
        raise LocalBackupError("The backup contains an unsafe file path.")
    raw_parts = name.split("/")
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} or ":" in part for part in raw_parts)
    ):
        raise LocalBackupError("The backup contains an unsafe file path.")
    if name in {DATABASE_MEMBER, MYSQL_DATABASE_MEMBER, MANIFEST_MEMBER}:
        return
    if path.parts[0] != "uploads" or len(path.parts) < 2:
        raise LocalBackupError("The backup contains an unexpected file.")


def _validate_database(database_path):
    try:
        with closing(sqlite3.connect(str(database_path), timeout=30)) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise LocalBackupError("The backup database failed its integrity check.")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if not {"users", "settings"}.issubset(tables):
                raise LocalBackupError("The backup does not contain a School Assessment Hub database.")
            user_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(users)")
            }
            if not {"id", "role"}.issubset(user_columns):
                raise LocalBackupError("The backup database has an incompatible users table.")
    except sqlite3.Error as error:
        raise LocalBackupError("The backup database could not be read.") from error


def _extract_and_validate(archive_path, destination, database_engine):
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as error:
        raise LocalBackupError("Choose a valid local backup ZIP file.") from error

    with archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)) or len({name.casefold() for name in names}) != len(names):
            raise LocalBackupError("The backup contains duplicate file paths.")
        total_size = 0
        entry_map = {}
        for entry in entries:
            _validate_member_name(entry.filename)
            if entry.is_dir() or entry.flag_bits & 0x1:
                raise LocalBackupError("The backup contains an unsupported file entry.")
            total_size += entry.file_size
            if total_size > MAX_BACKUP_BYTES:
                raise LocalBackupError("The backup is larger than the supported restore limit.")
            entry_map[entry.filename] = entry

        database_member = DATABASE_MEMBER if database_engine == "sqlite" else MYSQL_DATABASE_MEMBER
        if database_member not in entry_map or MANIFEST_MEMBER not in entry_map:
            raise LocalBackupError("The ZIP is missing its database or backup manifest.")
        manifest_info = entry_map[MANIFEST_MEMBER]
        if manifest_info.file_size > 65536:
            raise LocalBackupError("The backup manifest is too large.")
        try:
            manifest = json.loads(archive.read(MANIFEST_MEMBER))
        except (UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile) as error:
            raise LocalBackupError("The backup manifest is invalid.") from error
        if (
            not isinstance(manifest, dict)
            or manifest.get("database_engine") != database_engine
            or manifest.get("includes_uploads") is not True
        ):
            raise LocalBackupError(f"Only complete {database_engine.upper()} backups can be restored here.")
        upload_entries = [
            name for name in entry_map
            if name.startswith("uploads/")
        ]
        if manifest.get("upload_file_count") != len(upload_entries):
            raise LocalBackupError("The backup manifest does not match its uploaded files.")
        try:
            corrupt_entry = archive.testzip()
        except (OSError, zipfile.BadZipFile, RuntimeError) as error:
            raise LocalBackupError("The backup ZIP could not be verified.") from error
        if corrupt_entry:
            raise LocalBackupError("The backup ZIP contains a damaged file.")

        destination.mkdir(parents=True, exist_ok=True)
        database_path = destination / (
            "assessment.sqlite3" if database_engine == "sqlite" else "assessment.sql"
        )
        uploads_path = destination / "uploads"
        uploads_path.mkdir(parents=True, exist_ok=True)
        for name, entry in entry_map.items():
            if name == MANIFEST_MEMBER:
                continue
            if name == database_member:
                output_path = database_path
            else:
                output_path = uploads_path.joinpath(*PurePosixPath(name).parts[1:])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, output_path.open("wb") as output:
                shutil.copyfileobj(source, output)

    if database_engine == "sqlite":
        _validate_database(database_path)
    else:
        _validate_mysql_dump(database_path)
    return database_path, uploads_path


def _restore_mysql_database(connection_factory, sql_path):
    _validate_mysql_dump(sql_path)
    connection = connection_factory()
    try:
        with connection.cursor() as cursor:
            for statement in _iter_mysql_statements(sql_path):
                cursor.execute(statement)
        connection.commit()
    except Exception as error:
        try:
            connection.rollback()
        except Exception as rollback_error:
            raise LocalBackupError(
                f"MySQL restore failed ({error}); rollback also failed ({rollback_error})."
            ) from error
        raise LocalBackupError(f"MySQL restore failed: {error}") from error
    finally:
        connection.close()


def restore_local_backup(database_engine, database_path, connection_factory, uploads_dir, archive_path):
    database_path = Path(database_path)
    uploads_dir = Path(uploads_dir)
    if uploads_dir.is_symlink():
        raise LocalBackupError("The uploads folder is a symbolic link and cannot be safely restored.")
    uploads_dir.parent.mkdir(parents=True, exist_ok=True)
    if database_engine not in {"sqlite", "mysql"}:
        raise LocalBackupError("Only SQLite or MySQL local backups can be restored.")
    with tempfile.TemporaryDirectory(
        prefix="assessment-restore-", dir=uploads_dir.parent
    ) as temp_dir:
        temp_dir = Path(temp_dir)
        database_snapshot, restored_uploads = _extract_and_validate(
            archive_path, temp_dir / "restored", database_engine
        )
        previous_uploads = temp_dir / "previous-uploads"
        if database_engine == "sqlite":
            if uploads_dir.exists():
                os.replace(uploads_dir, previous_uploads)
            try:
                os.replace(restored_uploads, uploads_dir)
                with closing(sqlite3.connect(str(database_snapshot), timeout=30)) as source:
                    with closing(sqlite3.connect(str(database_path), timeout=30)) as destination:
                        source.backup(destination)
            except Exception:
                if uploads_dir.exists():
                    shutil.rmtree(uploads_dir)
                if previous_uploads.exists():
                    os.replace(previous_uploads, uploads_dir)
                raise
        else:
            _restore_mysql_database(connection_factory, database_snapshot)
            if uploads_dir.exists():
                os.replace(uploads_dir, previous_uploads)
            try:
                os.replace(restored_uploads, uploads_dir)
            except Exception:
                if previous_uploads.exists():
                    os.replace(previous_uploads, uploads_dir)
                raise
