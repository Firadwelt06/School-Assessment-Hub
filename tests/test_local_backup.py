import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path

from local_backup import (
    LocalBackupError,
    build_local_backup,
    restore_local_backup,
)


class LocalBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="assessment-local-backup-tests-")
        self.root = Path(self.temp_dir.name)
        self.database = self.root / "assessment.db"
        with closing(sqlite3.connect(self.database)) as connection:
            connection.executescript(
                """
                CREATE TABLE users (id INTEGER PRIMARY KEY, role TEXT NOT NULL);
                CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO users(role) VALUES ('admin');
                INSERT INTO settings(key, value) VALUES ('school_name', 'Local School');
                """
            )
        self.uploads = self.root / "uploads"
        (self.uploads / "questions").mkdir(parents=True)
        (self.uploads / "questions" / "diagram.png").write_bytes(b"saved image")
        self.archive = self.root / "assessment-local-backup.zip"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_restore_recovers_database_and_replaces_uploads(self):
        build_local_backup("sqlite", self.database, None, self.uploads, self.archive)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE settings SET value = 'Changed School'")
            connection.commit()
        (self.uploads / "questions" / "diagram.png").write_bytes(b"changed image")
        (self.uploads / "stale-file.txt").write_text("remove on restore", encoding="utf-8")

        restore_local_backup("sqlite", self.database, None, self.uploads, self.archive)

        with closing(sqlite3.connect(self.database)) as connection:
            setting = connection.execute(
                "SELECT value FROM settings WHERE key = 'school_name'"
            ).fetchone()
        self.assertEqual(setting[0], "Local School")
        self.assertEqual(
            (self.uploads / "questions" / "diagram.png").read_bytes(),
            b"saved image",
        )
        self.assertFalse((self.uploads / "stale-file.txt").exists())

    def test_restore_rejects_path_traversal_without_changing_data(self):
        malicious_archive = self.root / "malicious.zip"
        with zipfile.ZipFile(malicious_archive, "w") as archive:
            archive.writestr("../outside.txt", "unsafe")
            archive.writestr(
                "manifest.json",
                json.dumps({
                    "database_engine": "sqlite",
                    "includes_uploads": True,
                    "upload_file_count": 0,
                }),
            )

        with self.assertRaisesRegex(LocalBackupError, "unsafe file path"):
            restore_local_backup("sqlite", self.database, None, self.uploads, malicious_archive)

        with closing(sqlite3.connect(self.database)) as connection:
            setting = connection.execute(
                "SELECT value FROM settings WHERE key = 'school_name'"
            ).fetchone()
        self.assertEqual(setting[0], "Local School")
        self.assertEqual(
            (self.uploads / "questions" / "diagram.png").read_bytes(),
            b"saved image",
        )
        self.assertFalse((self.root / "outside.txt").exists())

    def test_restore_rejects_unrelated_sqlite_database(self):
        unrelated_database = self.root / "unrelated.sqlite3"
        with closing(sqlite3.connect(unrelated_database)) as connection:
            connection.execute("CREATE TABLE other_data (value TEXT)")
            connection.commit()
        archive_path = self.root / "unrelated.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.write(unrelated_database, "database/assessment.sqlite3")
            archive.writestr(
                "manifest.json",
                json.dumps({
                    "database_engine": "sqlite",
                    "includes_uploads": True,
                    "upload_file_count": 0,
                }),
            )

        with self.assertRaisesRegex(LocalBackupError, "School Assessment Hub database"):
            restore_local_backup("sqlite", self.database, None, self.uploads, archive_path)

    def test_restore_handles_backup_without_upload_files(self):
        empty_uploads = self.root / "empty-uploads"
        empty_uploads.mkdir()
        archive_path = self.root / "empty-uploads.zip"
        build_local_backup("sqlite", self.database, None, empty_uploads, archive_path)
        (self.uploads / "questions" / "diagram.png").unlink()

        restore_local_backup("sqlite", self.database, None, self.uploads, archive_path)

        self.assertEqual(list(self.uploads.iterdir()), [])

    def test_mysql_local_restore_applies_validated_sql_and_restores_uploads(self):
        sql_dump = """SET FOREIGN_KEY_CHECKS=0;
DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (`id` int NOT NULL);
DROP TABLE IF EXISTS `settings`;
CREATE TABLE `settings` (`key` varchar(255) NOT NULL);
DROP TABLE IF EXISTS `attempts`;
CREATE TABLE `attempts` (`id` int NOT NULL);
INSERT INTO `settings` (`key`) VALUES ('text with ; semicolon');
SET FOREIGN_KEY_CHECKS=1;
"""
        archive_path = self.root / "mysql-backup.zip"
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("database/assessment.sql", sql_dump)
            archive.writestr("uploads/restored.txt", "restored")
            archive.writestr(
                "manifest.json",
                json.dumps({
                    "database_engine": "mysql",
                    "includes_uploads": True,
                    "upload_file_count": 1,
                }),
            )

        class FakeCursor:
            def __init__(self, connection):
                self.connection = connection

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, statement):
                self.connection.statements.append(statement)

        class FakeConnection:
            def __init__(self):
                self.statements = []
                self.committed = False
                self.rolled_back = False

            def cursor(self):
                return FakeCursor(self)

            def commit(self):
                self.committed = True

            def rollback(self):
                self.rolled_back = True

            def close(self):
                pass

        connection = FakeConnection()

        restore_local_backup(
            "mysql",
            self.root / "mysql-database",
            lambda: connection,
            self.uploads,
            archive_path,
        )

        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertEqual(len(connection.statements), 9)
        self.assertIn("text with ; semicolon", connection.statements[7])
        self.assertEqual((self.uploads / "restored.txt").read_text(encoding="utf-8"), "restored")

    def test_mysql_local_backup_contains_database_snapshot_and_uploads(self):
        class FakeCursor:
            def __init__(self):
                self.statement = ""
                self.rows = []

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, statement):
                self.statement = statement
                self.rows = []
                if statement.startswith("SHOW FULL TABLES"):
                    self.rows = [
                        {"Tables_in_school": "users"},
                        {"Tables_in_school": "settings"},
                        {"Tables_in_school": "attempts"},
                    ]
                elif statement.startswith("SHOW CREATE TABLE"):
                    table = statement.rsplit("`", 2)[1]
                    self.rows = [{
                        "Table": table,
                        "Create Table": f"CREATE TABLE `{table}` (`id` int NOT NULL)",
                    }]

            def fetchall(self):
                return self.rows

            def fetchone(self):
                return self.rows[0]

            def fetchmany(self, size):
                if self.statement.startswith("SELECT * FROM `users`") and not self.rows:
                    self.rows = [{"id": 1}]
                    return self.rows
                self.rows = []
                return []

            def mogrify(self, statement, values):
                return b"INSERT INTO `users` (`id`) VALUES (1)"

        class FakeConnection:
            def cursor(self):
                return FakeCursor()

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        archive_path = self.root / "mysql-local-backup.zip"
        build_local_backup(
            "mysql",
            self.root / "unused-mysql-path",
            FakeConnection,
            self.uploads,
            archive_path,
        )

        with zipfile.ZipFile(archive_path) as archive:
            self.assertIn("database/assessment.sql", archive.namelist())
            self.assertIn("uploads/questions/diagram.png", archive.namelist())
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["database_engine"], "mysql")
