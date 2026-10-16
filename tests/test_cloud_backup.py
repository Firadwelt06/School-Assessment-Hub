import json
import io
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path

from cloud_backup import (
    R2BackupConfig,
    build_backup_archive,
    remove_expired_backups,
    run_cloud_backup,
)


class FakePaginator:
    def __init__(self, objects):
        self.objects = objects

    def paginate(self, **kwargs):
        return [{"Contents": self.objects}]


class FakeR2Client:
    def __init__(self, objects):
        self.objects = objects
        self.deleted = []
        self.uploads = {}

    def get_paginator(self, operation):
        if operation != "list_objects_v2":
            raise AssertionError(f"Unexpected paginator: {operation}")
        return FakePaginator(self.objects)

    def delete_object(self, **kwargs):
        self.deleted.append(kwargs["Key"])

    def upload_file(self, path, bucket, key, ExtraArgs):
        self.uploads[key] = Path(path).read_bytes()
        self.objects.append({"Key": key})

    def head_object(self, **kwargs):
        content = self.uploads[kwargs["Key"]]
        return {"ContentLength": len(content)}


class CloudBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.database_path = self.root / "assessment.db"
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
            connection.execute("INSERT INTO sample(value) VALUES (?)", ("consistent snapshot",))
            connection.commit()

        self.uploads_dir = self.root / "uploads"
        self.uploads_dir.mkdir()
        (self.uploads_dir / "school-logo.png").write_bytes(b"logo")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sqlite_archive_contains_snapshot_uploads_and_manifest(self):
        archive_path = self.root / "backup.zip"
        build_backup_archive("sqlite", self.database_path, None, self.uploads_dir, archive_path)

        with zipfile.ZipFile(archive_path) as archive:
            self.assertIn("database/assessment.sqlite3", archive.namelist())
            self.assertIn("uploads/school-logo.png", archive.namelist())
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["database_engine"], "sqlite")
            self.assertEqual(manifest["upload_file_count"], 1)

            snapshot_path = self.root / "restored.sqlite3"
            snapshot_path.write_bytes(archive.read("database/assessment.sqlite3"))
        with closing(sqlite3.connect(snapshot_path)) as snapshot:
            row = snapshot.execute("SELECT value FROM sample").fetchone()
        self.assertEqual(row[0], "consistent snapshot")

    def test_retention_deletes_only_backups_beyond_thirty_newest(self):
        config = R2BackupConfig(
            account_id="a" * 32,
            access_key_id="key",
            secret_access_key="secret",
            bucket="private-backups",
            prefix="school/backups",
            hour=2,
        )
        keys = [
            f"{config.object_prefix}202610{i:02d}T020000000000Z.zip"
            for i in range(1, 32)
        ]
        client = FakeR2Client([{"Key": key} for key in keys])

        deleted = remove_expired_backups(client, config)

        self.assertEqual(deleted, 1)
        self.assertEqual(client.deleted, [keys[0]])

    def test_r2_config_rejects_path_traversal_prefix(self):
        config = R2BackupConfig(
            account_id="a" * 32,
            access_key_id="key",
            secret_access_key="secret",
            bucket="private-backups",
            prefix="../outside",
            hour=2,
        )
        with self.assertRaisesRegex(ValueError, "must not contain"):
            config.validate()

    def test_cloud_backup_uploads_a_verifiable_archive(self):
        config = R2BackupConfig(
            account_id="a" * 32,
            access_key_id="key",
            secret_access_key="secret",
            bucket="private-backups",
            prefix="school/backups",
            hour=2,
        )
        client = FakeR2Client([])

        result = run_cloud_backup(
            "sqlite",
            self.database_path,
            None,
            self.uploads_dir,
            config=config,
            client=client,
        )

        self.assertEqual(result["deleted"], 0)
        archive = zipfile.ZipFile(io.BytesIO(client.uploads[result["key"]]))
        self.assertIn("database/assessment.sqlite3", archive.namelist())
        self.assertIn("uploads/school-logo.png", archive.namelist())


if __name__ == "__main__":
    unittest.main()
