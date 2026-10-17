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
        assessment_app.execute(
            """INSERT OR REPLACE INTO users
            (username, full_name, password_hash, role, class_name, subjects, active, created_at)
            VALUES (?, ?, ?, 'teacher', '', 'Biology', 1, ?)""",
            (
                "teacher.name",
                "Teacher Name",
                assessment_app.hash_password("OldTeacherPass123"),
                "2026-10-15T12:00:00",
            ),
        )
        with patch.object(assessment_app, "send_portal_teacher_password_hash") as reset_password:
            response = self.client.post(
                "/admin/question-submissions/reset-password",
                data={"username": "teacher.name", "password": "TemporaryPass123"},
            )

        self.assertEqual(response.status_code, 302)
        reset_password.assert_called_once()
        username, full_name, password_hash, active = reset_password.call_args.args
        self.assertEqual((username, full_name, active), ("teacher.name", "Teacher Name", True))
        self.assertTrue(assessment_app.check_password("TemporaryPass123", password_hash))
        self.assertEqual(
            assessment_app.query(
                "SELECT password_hash FROM users WHERE username = ?",
                ("teacher.name",),
                one=True,
            )["password_hash"],
            password_hash,
        )

    def test_admin_can_enable_or_disable_a_portal_teacher(self):
        with patch.object(assessment_app, "send_portal_teacher_status") as set_status:
            response = self.client.post(
                "/admin/question-submissions/teacher-access",
                data={"username": "teacher.name", "active": "0"},
            )

        self.assertEqual(response.status_code, 302)
        set_status.assert_called_once_with("teacher.name", False)

    def test_teacher_results_require_both_assigned_subject_and_class(self):
        teacher_id = assessment_app.execute(
            """INSERT INTO users
            (username, full_name, password_hash, role, class_name, subjects, active, created_at)
            VALUES (?, ?, ?, 'teacher', '', 'Biology', 1, ?)""",
            ("scope.teacher", "Scope Teacher", assessment_app.hash_password("TeacherPass123"),
             "2026-10-15T12:00:00"),
        )
        assessment_app.execute(
            "INSERT INTO teacher_class_assignments(teacher_id, class_name) VALUES (?, ?)",
            (teacher_id, "SS1"),
        )
        inserted_usernames = []
        for index, (username, name, subject, class_name) in enumerate(
            [
                ("scope.student.allowed", "Assigned Student", "Biology", "SS1"),
                ("scope.student.class", "Wrong Class Student", "Biology", "SS2"),
                ("scope.student.subject", "Wrong Subject Student", "Chemistry", "SS1"),
            ]
        ):
            inserted_usernames.append(username)
            student_id = assessment_app.execute(
                """INSERT INTO users
                (username, full_name, password_hash, role, class_name, active, created_at)
                VALUES (?, ?, ?, 'student', ?, 1, ?)""",
                (username, name, assessment_app.hash_password("StudentPass123"), class_name,
                 "2026-10-15T12:00:00"),
            )
            exam_id = assessment_app.execute(
                """INSERT INTO exams
                (title, subject, class_name, exam_type, duration_minutes, created_by, published, created_at)
                VALUES (?, ?, ?, 'quiz', 30, ?, 1, ?)""",
                (f"Scope Exam {index}", subject, class_name, teacher_id, "2026-10-15T12:00:00"),
            )
            assessment_app.execute(
                """INSERT INTO attempts
                (exam_id, student_id, score, total, started_at, submitted_at)
                VALUES (?, ?, 8, 10, ?, ?)""",
                (exam_id, student_id, "2026-10-16T11:30:00", "2026-10-16T12:00:00"),
            )

        with self.client.session_transaction() as session:
            session["user_id"] = teacher_id

        try:
            dashboard = self.client.get("/dashboard").get_data(as_text=True)
            rankings = self.client.get("/rankings").get_data(as_text=True)
            analytics = self.client.get("/analytics").get_data(as_text=True)
            report = self.client.get("/reports/results.csv").get_data(as_text=True)

            for output in (dashboard, rankings, report):
                self.assertIn("Assigned Student", output)
                self.assertNotIn("Wrong Class Student", output)
                self.assertNotIn("Wrong Subject Student", output)
            self.assertIn("1", analytics)
            self.assertNotIn("Wrong Class Student", analytics)
            self.assertNotIn("Wrong Subject Student", analytics)
        finally:
            assessment_app.execute(
                "DELETE FROM attempts WHERE student_id IN (SELECT id FROM users WHERE username LIKE 'scope.student.%')"
            )
            assessment_app.execute(
                "DELETE FROM teacher_class_assignments WHERE teacher_id = ?",
                (teacher_id,),
            )
            assessment_app.execute(
                "DELETE FROM exams WHERE created_by = ?",
                (teacher_id,),
            )
            assessment_app.execute(
                "DELETE FROM users WHERE username = ? OR username IN (?, ?, ?)",
                ( "scope.teacher", *inserted_usernames),
            )


if __name__ == "__main__":
    unittest.main()
