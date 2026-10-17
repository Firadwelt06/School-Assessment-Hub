import io
import sqlite3
import tempfile
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch

from cloud_sync import (
    PortalSyncError,
    _PortalRedirectHandler,
    portal_request,
    sync_question_submissions,
)


REMOTE_ID = "123e4567-e89b-12d3-a456-426614174000"


class CloudSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.database_path = self.root / "assessment.db"
        self.uploads_dir = self.root / "uploads"
        self.uploads_dir.mkdir()
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute(
                """CREATE TABLE question_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, remote_id TEXT UNIQUE NOT NULL,
                teacher_name TEXT NOT NULL, teacher_username TEXT NOT NULL,
                subject TEXT NOT NULL, topic TEXT NOT NULL, class_name TEXT NOT NULL,
                image_path TEXT NOT NULL, stem TEXT NOT NULL, option_a TEXT NOT NULL,
                option_b TEXT NOT NULL, option_c TEXT NOT NULL, option_d TEXT NOT NULL,
                correct_option TEXT NOT NULL, difficulty TEXT NOT NULL, explanation TEXT NOT NULL,
                standard TEXT NOT NULL, status TEXT NOT NULL, feedback TEXT NOT NULL,
                submitted_at TEXT NOT NULL, decision_synced INTEGER NOT NULL DEFAULT 0)"""
            )
            connection.commit()

    def tearDown(self):
        self.temp_dir.cleanup()

    def connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def test_portal_requests_send_sync_token_as_bearer_authorization(self):
        response = MagicMock()
        response.headers.get_content_type.return_value = "application/json"
        response.read.return_value = b"{}"
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        token = "private-test-token-value-with-at-least-32-characters"

        with patch.dict(
            "os.environ",
            {
                "CLOUD_PORTAL_URL": "https://portal.example.workers.dev",
                "CLOUD_PORTAL_SYNC_TOKEN": token,
            },
        ), patch("cloud_sync.urllib.request.build_opener", return_value=opener):
            portal_request("/api/sync/pending")

        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), f"Bearer {token}")

    def submission(self):
        return {
            "id": REMOTE_ID,
            "teacher_name": "Ada Teacher",
            "teacher_username": "ada.teacher",
            "subject": "Science",
            "topic": "Plants",
            "class_name": "SS1",
            "stem": "Which part absorbs water?",
            "option_a": "Leaf",
            "option_b": "Root",
            "option_c": "Flower",
            "option_d": "Stem",
            "correct_option": "B",
            "difficulty": "easy",
            "explanation": "Roots absorb water from the soil.",
            "standard": "",
            "image": True,
            "submitted_at": "2026-10-15T12:00:00.000Z",
        }

    def test_http_errors_identify_endpoint_and_cloudflare_ray_without_token(self):
        token = "private-test-token-value-with-at-least-32-characters"
        error = urllib.error.HTTPError(
            "https://portal.example.workers.dev/api/sync/pending",
            403,
            "Forbidden",
            {"CF-Ray": "ray-test-123"},
            io.BytesIO(b"Forbidden"),
        )

        with patch.dict(
            "os.environ",
            {
                "CLOUD_PORTAL_URL": "https://portal.example.workers.dev",
                "CLOUD_PORTAL_SYNC_TOKEN": token,
            },
        ), patch("cloud_sync.urllib.request.build_opener") as build_opener:
            build_opener.return_value.open.side_effect = error
            with self.assertRaises(PortalSyncError) as raised:
                portal_request("/api/sync/pending")

        self.assertIn("GET /api/sync/pending", str(raised.exception))
        self.assertIn("HTTP 403", str(raised.exception))
        self.assertIn("ray-test-123", str(raised.exception))
        self.assertNotIn(token, str(raised.exception))

    def test_cross_origin_redirect_does_not_forward_authorization_or_cookies(self):
        request = urllib.request.Request(
            "https://portal.example.workers.dev/api/sync/submissions/image",
            headers={"Authorization": "Bearer private-token", "Cookie": "portal_session=private"},
        )
        redirected = _PortalRedirectHandler().redirect_request(
            request,
            None,
            302,
            "Found",
            Message(),
            "https://private-bucket.s3.amazonaws.com/image?signature=private",
        )

        self.assertIsNotNone(redirected)
        self.assertIsNone(redirected.get_header("Authorization"))
        self.assertIsNone(redirected.get_header("Cookie"))

    def test_sync_downloads_question_and_optional_image_once(self):
        def portal_request(path, **kwargs):
            if path.startswith("/api/sync/pending"):
                return {"submissions": [self.submission()], "next_cursor": ""}
            if path.endswith("/image"):
                return b"\x89PNG\r\n\x1a\nimage", "image/png"
            raise AssertionError(f"Unexpected portal request: {path}")

        with patch("cloud_sync.portal_request", side_effect=portal_request):
            result = sync_question_submissions("sqlite", self.connect, self.uploads_dir)

        self.assertEqual(result["imported"], 1)
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT remote_id, status, image_path FROM question_submissions"
            ).fetchone()
        self.assertEqual(row["remote_id"], REMOTE_ID)
        self.assertEqual(row["status"], "pending")
        self.assertTrue((self.uploads_dir / row["image_path"]).is_file())

        with patch("cloud_sync.portal_request", side_effect=portal_request):
            result = sync_question_submissions("sqlite", self.connect, self.uploads_dir)
        self.assertEqual(result["imported"], 0)

    def test_sync_sends_and_records_offline_review_decisions(self):
        with closing(self.connect()) as connection:
            connection.execute(
                """INSERT INTO question_submissions
                (remote_id, teacher_name, teacher_username, subject, topic, class_name, image_path,
                 stem, option_a, option_b, option_c, option_d, correct_option, difficulty,
                 explanation, standard, status, feedback, submitted_at)
                VALUES (?, 'Ada Teacher', 'ada.teacher', 'Science', 'Plants', 'SS1', '',
                'Question', 'A', 'B', 'C', 'D', 'A', 'easy', '', '', 'approved',
                'Ready for review', '2026-10-15T12:00:00.000Z')""",
                (REMOTE_ID,),
            )
            connection.commit()

        def portal_request(path, method="GET", payload=None, **kwargs):
            if path == "/api/sync/pending":
                return {"submissions": [], "next_cursor": ""}
            if path == "/api/sync/decisions":
                self.assertEqual(payload["decisions"][0]["id"], REMOTE_ID)
                return {"synced_ids": [REMOTE_ID], "conflicts": []}
            raise AssertionError(f"Unexpected portal request: {path}")

        with patch("cloud_sync.portal_request", side_effect=portal_request):
            result = sync_question_submissions("sqlite", self.connect, self.uploads_dir)

        self.assertEqual(result["decisions_synced"], 1)
        with closing(self.connect()) as connection:
            synced = connection.execute(
                "SELECT decision_synced FROM question_submissions WHERE remote_id = ?",
                (REMOTE_ID,),
            ).fetchone()[0]
        self.assertEqual(synced, 1)


if __name__ == "__main__":
    unittest.main()
