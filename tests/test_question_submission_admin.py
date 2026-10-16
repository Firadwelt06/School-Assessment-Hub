import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TEST_DATABASE_DIR = tempfile.TemporaryDirectory(prefix="assessment-admin-tests-")
os.environ["DB_ENGINE"] = "sqlite"
os.environ["DATABASE_PATH"] = str(Path(TEST_DATABASE_DIR.name) / "assessment.db")

import app as assessment_app


class QuestionSubmissionAdminTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = assessment_app.app.test_client()
        cls.admin_id = assessment_app.query(
            "SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1",
            one=True,
        )["id"]

    def setUp(self):
        assessment_app.execute("DELETE FROM question_submissions")
        assessment_app.execute("DELETE FROM questions")
        self.submission_id = assessment_app.execute(
            """INSERT INTO question_submissions
            (remote_id, teacher_name, teacher_username, subject, topic, class_name, image_path,
             stem, option_a, option_b, option_c, option_d, correct_option, difficulty,
             explanation, standard, status, feedback, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '', ?)""",
            (
                "123e4567-e89b-12d3-a456-426614174000",
                "Teacher Name",
                "teacher.name",
                "Biology",
                "Roots",
                "SS1",
                "",
                "Which part absorbs water?",
                "Leaf",
                "Root",
                "Flower",
                "Stem",
                "B",
                "easy",
                "Roots absorb water.",
                "",
                "2026-10-15T12:00:00Z",
            ),
        )
        with self.client.session_transaction() as session:
            session["user_id"] = self.admin_id

    def test_approval_adds_question_to_bank_without_publishing_an_exam(self):
        response = self.client.post(
            f"/admin/question-submissions/{self.submission_id}/review",
            data={"status": "approved", "feedback": "Looks good."},
        )

        self.assertEqual(response.status_code, 302)
        question = assessment_app.query(
            "SELECT * FROM questions WHERE stem = ?",
            ("Which part absorbs water?",),
            one=True,
        )
        self.assertIsNotNone(question)
        self.assertEqual(question["created_by"], self.admin_id)
        self.assertEqual(
            assessment_app.query(
                "SELECT status, feedback, decision_synced FROM question_submissions WHERE id = ?",
                (self.submission_id,),
                one=True,
            )["status"],
            "approved",
        )
        self.assertEqual(
            assessment_app.query(
                "SELECT COUNT(*) AS count FROM exams WHERE published = 1",
                one=True,
            )["count"],
            0,
        )

    def test_rejection_keeps_question_out_of_bank_and_saves_feedback(self):
        response = self.client.post(
            f"/admin/question-submissions/{self.submission_id}/review",
            data={"status": "rejected", "feedback": "Please correct option B."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            assessment_app.query("SELECT COUNT(*) AS count FROM questions", one=True)["count"],
            0,
        )
        submission = assessment_app.query(
            "SELECT status, feedback FROM question_submissions WHERE id = ?",
            (self.submission_id,),
            one=True,
        )
        self.assertEqual(submission["status"], "rejected")
        self.assertEqual(submission["feedback"], "Please correct option B.")

    def test_duplicate_approval_is_refused(self):
        assessment_app.execute(
            """INSERT INTO questions
            (subject, topic, class_name, image_path, stem, option_a, option_b, option_c,
             option_d, correct_option, difficulty, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "Biology", "Roots", "SS1", "", "Which part absorbs water?",
                "Leaf", "Root", "Flower", "Stem", "B", "easy", self.admin_id,
                "2026-10-15T12:00:00",
            ),
        )

        response = self.client.post(
            f"/admin/question-submissions/{self.submission_id}/review",
            data={"status": "approved"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            assessment_app.query(
                "SELECT status FROM question_submissions WHERE id = ?",
                (self.submission_id,),
                one=True,
            )["status"],
            "pending",
        )

    def test_admin_can_reset_a_portal_teacher_password_through_sync(self):
        with patch.object(assessment_app, "send_portal_teacher_password_reset") as reset_password:
            response = self.client.post(
                "/admin/question-submissions/reset-password",
                data={"username": "teacher.name", "password": "TemporaryPass123"},
            )

        self.assertEqual(response.status_code, 302)
        reset_password.assert_called_once_with("teacher.name", "TemporaryPass123")

    def test_admin_can_enable_or_disable_a_portal_teacher(self):
        with patch.object(assessment_app, "send_portal_teacher_status") as set_status:
            response = self.client.post(
                "/admin/question-submissions/teacher-access",
                data={"username": "teacher.name", "active": "0"},
            )

        self.assertEqual(response.status_code, 302)
        set_status.assert_called_once_with("teacher.name", False)


if __name__ == "__main__":
    unittest.main()
