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
    sync_teacher_accounts,
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
                submitted_at TEXT NOT NULL, reviewed_at TEXT NOT NULL DEFAULT '',
                decision_synced INTEGER NOT NULL DEFAULT 0)"""
            )
            connection.executescript(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE,
                    full_name TEXT, password_hash TEXT, role TEXT,
                    class_name TEXT DEFAULT '', subjects TEXT DEFAULT '',
                    active INTEGER DEFAULT 1, created_at TEXT
                );
                CREATE TABLE teacher_sync_state (
                    username TEXT PRIMARY KEY, synced_fingerprint TEXT NOT NULL
                );
                CREATE TABLE teacher_sync_conflicts (
                    username TEXT PRIMARY KEY, detected_at TEXT NOT NULL
                );
                CREATE TABLE questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT, topic TEXT,
                    class_name TEXT, image_path TEXT, stem TEXT, option_a TEXT,
                    option_b TEXT, option_c TEXT, option_d TEXT, correct_option TEXT,
                    difficulty TEXT, explanation TEXT, standard TEXT, created_by INTEGER,
                    created_at TEXT
                );
                """
            )
            connection.execute(
                "INSERT INTO users(username, full_name, password_hash, role, active) VALUES ('admin', 'Admin', 'hash', 'admin', 1)"
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
            if path.startswith("/api/sync/reviewed"):
                return {"submissions": [], "next_cursor": ""}
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
            if path == "/api/sync/reviewed":
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

    def test_teacher_sync_pushes_local_account_and_records_baseline(self):
        account = {
            "username": "ada.teacher",
            "full_name": "Ada Teacher",
            "password_hash": "a" * 32 + "$" + "b" * 64,
            "active": True,
        }
        with closing(self.connect()) as connection:
            connection.execute(
                "INSERT INTO users(username, full_name, password_hash, role, active) VALUES (?, ?, ?, 'teacher', 1)",
                (account["username"], account["full_name"], account["password_hash"]),
            )
            connection.commit()
        calls = []

        def portal_request(path, method="GET", payload=None, **kwargs):
            calls.append((path, method, payload))
            if path == "/api/sync/teachers":
                return {"teachers": []}
            if path == "/api/sync/teachers/upsert":
                return {"ok": True}
            raise AssertionError(f"Unexpected portal request: {path}")

        with patch("cloud_sync.portal_request", side_effect=portal_request):
            result = sync_teacher_accounts("sqlite", self.connect)

        self.assertEqual(result, {"imported": 0, "pushed": 1, "conflicts": []})
        self.assertEqual(calls[0][0], "/api/sync/teachers")
        self.assertEqual(calls[1][2], account)
        with closing(self.connect()) as connection:
            baseline = connection.execute(
                "SELECT synced_fingerprint FROM teacher_sync_state WHERE username = ?",
                (account["username"],),
            ).fetchone()
        self.assertIsNotNone(baseline)

    def test_teacher_sync_imports_portal_account_hash(self):
        account = {
            "username": "binta.teacher",
            "full_name": "Binta Teacher",
            "password_hash": "pbkdf2$100000$" + "a" * 32 + "$" + "b" * 64,
            "active": True,
        }
        with patch("cloud_sync.portal_request", return_value={"teachers": [account]}):
            result = sync_teacher_accounts("sqlite", self.connect)

        self.assertEqual(result, {"imported": 1, "pushed": 0, "conflicts": []})
        with closing(self.connect()) as connection:
            teacher = connection.execute(
                "SELECT full_name, password_hash, role FROM users WHERE username = ?",
                (account["username"],),
            ).fetchone()
        self.assertEqual(tuple(teacher), (account["full_name"], account["password_hash"], "teacher"))

    def test_teacher_sync_flags_two_sided_account_conflicts(self):
        username = "chika.teacher"
        local = {
            "username": username,
            "full_name": "Chika Teacher",
            "password_hash": "a" * 32 + "$" + "b" * 64,
            "active": True,
        }
        remote = {**local, "password_hash": "c" * 32 + "$" + "d" * 64}
        with closing(self.connect()) as connection:
            connection.execute(
                "INSERT INTO users(username, full_name, password_hash, role, active) VALUES (?, ?, ?, 'teacher', 1)",
                (username, local["full_name"], local["password_hash"]),
            )
            connection.execute(
                "INSERT INTO teacher_sync_state(username, synced_fingerprint) VALUES (?, ?)",
                (username, "e" * 64),
            )
            connection.commit()
        with patch("cloud_sync.portal_request", return_value={"teachers": [remote]}):
            result = sync_teacher_accounts("sqlite", self.connect)

        self.assertEqual(result["conflicts"], [username])
        with closing(self.connect()) as connection:
            conflict = connection.execute(
                "SELECT username FROM teacher_sync_conflicts WHERE username = ?",
                (username,),
            ).fetchone()
        self.assertEqual(conflict["username"], username)

    def reviewed_submission(self, status="approved"):
        return {
            **self.submission(),
            "status": status,
            "feedback": "Reviewed online.",
            "decided_at": "2026-10-16T12:00:00Z",
        }

    def sync_reviewed(self, reviewed):
        def portal_request(path, method="GET", payload=None, **kwargs):
            if path == "/api/sync/pending":
                return {"submissions": [], "next_cursor": ""}
            if path == "/api/sync/reviewed":
                return {"submissions": [reviewed], "next_cursor": ""}
            if path == "/api/sync/decisions":
                return {"synced_ids": [], "conflicts": []}
            if path.endswith("/image"):
                return b"\x89PNG\r\n\x1a\nimage", "image/png"
            raise AssertionError(f"Unexpected portal request: {path}")

        with patch("cloud_sync.portal_request", side_effect=portal_request):
            return sync_question_submissions("sqlite", self.connect, self.uploads_dir)

    def test_online_approval_imports_submission_and_question_idempotently(self):
        result = self.sync_reviewed(self.reviewed_submission())

        self.assertEqual(result["online_reviews_applied"], 1)
        with closing(self.connect()) as connection:
            submission = connection.execute(
                "SELECT status, feedback, decision_synced FROM question_submissions WHERE remote_id = ?",
                (REMOTE_ID,),
            ).fetchone()
            questions = connection.execute("SELECT stem, created_by FROM questions").fetchall()
        self.assertEqual(tuple(submission), ("approved", "Reviewed online.", 1))
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["stem"], "Which part absorbs water?")
        self.assertEqual(questions[0]["created_by"], 1)

        repeated = self.sync_reviewed(self.reviewed_submission())
        self.assertEqual(repeated["online_reviews_applied"], 0)
        with closing(self.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0], 1)

    def test_online_rejection_imports_feedback_without_creating_question(self):
        result = self.sync_reviewed(self.reviewed_submission("rejected"))

        self.assertEqual(result["online_reviews_applied"], 1)
        with closing(self.connect()) as connection:
            submission = connection.execute(
                "SELECT status, feedback FROM question_submissions WHERE remote_id = ?",
                (REMOTE_ID,),
            ).fetchone()
            question_count = connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        self.assertEqual(tuple(submission), ("rejected", "Reviewed online."))
        self.assertEqual(question_count, 0)

    def test_online_review_conflicting_with_local_decision_is_not_applied(self):
        with closing(self.connect()) as connection:
            connection.execute(
                """INSERT INTO question_submissions
                (remote_id, teacher_name, teacher_username, subject, topic, class_name, image_path,
                 stem, option_a, option_b, option_c, option_d, correct_option, difficulty,
                 explanation, standard, status, feedback, submitted_at)
                VALUES (?, 'Ada Teacher', 'ada.teacher', 'Science', 'Plants', 'SS1', '',
                'Question', 'A', 'B', 'C', 'D', 'A', 'easy', '', '', 'rejected',
                'Local decision', '2026-10-15T12:00:00Z')""",
                (REMOTE_ID,),
            )
            connection.commit()

        result = self.sync_reviewed(self.reviewed_submission("approved"))

        self.assertEqual(result["online_review_conflicts"], 1)
        with closing(self.connect()) as connection:
            submission = connection.execute(
                "SELECT status, feedback FROM question_submissions WHERE remote_id = ?",
                (REMOTE_ID,),
            ).fetchone()
            question_count = connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        self.assertEqual(tuple(submission), ("rejected", "Local decision"))
        self.assertEqual(question_count, 0)


if __name__ == "__main__":
    unittest.main()
