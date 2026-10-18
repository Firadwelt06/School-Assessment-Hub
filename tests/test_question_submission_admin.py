import io
import os
import tempfile
import unittest
from datetime import datetime, timedelta
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

    def test_admin_class_filter_matches_teacher_class_assignments(self):
        teacher_ids = []
        for username, class_name in (
            ("filter.teacher.ss1", "SS1"),
            ("filter.teacher.ss2", "SS2"),
        ):
            teacher_id = assessment_app.execute(
                """INSERT INTO users
                (username, full_name, password_hash, role, class_name, subjects, active, created_at)
                VALUES (?, ?, ?, 'teacher', '', 'Biology', 1, ?)""",
                (
                    username,
                    username,
                    assessment_app.hash_password("TeacherPass123"),
                    "2026-10-15T12:00:00",
                ),
            )
            teacher_ids.append(teacher_id)
            assessment_app.execute(
                "INSERT INTO teacher_class_assignments(teacher_id, class_name) VALUES (?, ?)",
                (teacher_id, class_name),
            )

        try:
            response = self.client.get("/admin?role=teacher&class_name=SS1")
            page = response.get_data(as_text=True)

            self.assertEqual(response.status_code, 200)
            self.assertIn("filter.teacher.ss1", page)
            self.assertNotIn("filter.teacher.ss2", page)
        finally:
            for teacher_id in teacher_ids:
                assessment_app.execute(
                    "DELETE FROM teacher_class_assignments WHERE teacher_id = ?",
                    (teacher_id,),
                )
                assessment_app.execute("DELETE FROM users WHERE id = ?", (teacher_id,))

    def test_manual_teacher_creation_assigns_selected_classes(self):
        previous_classes = assessment_app.query(
            "SELECT value FROM settings WHERE key = ?",
            ("managed_classes",),
            one=True,
        )
        assessment_app.upsert_setting("managed_classes", "SS1, SS2")
        username = "manual.teacher.classes"
        try:
            response = self.client.post(
                "/admin",
                data={
                    "action": "user",
                    "username": username,
                    "full_name": "Manual Teacher",
                    "password": "LocalTeacherPass123",
                    "role": "teacher",
                    "subjects": "Biology",
                    "teacher_classes": ["SS1", "SS2"],
                },
            )

            self.assertEqual(response.status_code, 302)
            teacher = assessment_app.query(
                "SELECT id, password_hash FROM users WHERE username = ?",
                (username,),
                one=True,
            )
            self.assertTrue(
                assessment_app.check_password("LocalTeacherPass123", teacher["password_hash"])
            )
            self.assertEqual(
                [
                    row["class_name"]
                    for row in assessment_app.query(
                        "SELECT class_name FROM teacher_class_assignments WHERE teacher_id = ? ORDER BY class_name",
                        (teacher["id"],),
                    )
                ],
                ["SS1", "SS2"],
            )
        finally:
            teacher = assessment_app.query(
                "SELECT id FROM users WHERE username = ?",
                (username,),
                one=True,
            )
            if teacher:
                assessment_app.execute(
                    "DELETE FROM teacher_class_assignments WHERE teacher_id = ?",
                    (teacher["id"],),
                )
                assessment_app.execute("DELETE FROM users WHERE id = ?", (teacher["id"],))
            if previous_classes:
                assessment_app.upsert_setting("managed_classes", previous_classes["value"])
            else:
                assessment_app.execute(
                    "DELETE FROM settings WHERE key = ?",
                    ("managed_classes",),
                )

    def test_manual_teacher_creation_requires_valid_class_assignment(self):
        response = self.client.post(
            "/admin",
            data={
                "action": "user",
                "username": "manual.teacher.no-class",
                "full_name": "Teacher Without Class",
                "password": "LocalTeacherPass123",
                "role": "teacher",
                "subjects": "Biology",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(
            assessment_app.query(
                "SELECT id FROM users WHERE username = ?",
                ("manual.teacher.no-class",),
                one=True,
            )
        )

    def test_teacher_csv_accepts_class_name_column_and_assigns_class(self):
        previous_classes = assessment_app.query(
            "SELECT value FROM settings WHERE key = ?",
            ("managed_classes",),
            one=True,
        )
        assessment_app.upsert_setting("managed_classes", "SS1, SS2")
        username = "csv.teacher.class"
        try:
            response = self.client.post(
                "/admin",
                data={
                    "action": "teachers_csv",
                    "teachers_csv": (
                        io.BytesIO(
                            b"username,full_name,password,subjects,class_name\n"
                            b"csv.teacher.class,CSV Teacher,TeacherPass123,Biology,SS1\n"
                        ),
                        "teachers.csv",
                    ),
                },
                content_type="multipart/form-data",
            )

            self.assertEqual(response.status_code, 302)
            teacher = assessment_app.query(
                "SELECT id FROM users WHERE username = ?",
                (username,),
                one=True,
            )
            self.assertIsNotNone(teacher)
            self.assertEqual(
                assessment_app.query(
                    "SELECT class_name FROM teacher_class_assignments WHERE teacher_id = ?",
                    (teacher["id"],),
                    one=True,
                )["class_name"],
                "SS1",
            )
        finally:
            teacher = assessment_app.query(
                "SELECT id FROM users WHERE username = ?",
                (username,),
                one=True,
            )
            if teacher:
                assessment_app.execute(
                    "DELETE FROM teacher_class_assignments WHERE teacher_id = ?",
                    (teacher["id"],),
                )
                assessment_app.execute("DELETE FROM users WHERE id = ?", (teacher["id"],))
            if previous_classes:
                assessment_app.upsert_setting("managed_classes", previous_classes["value"])
            else:
                assessment_app.execute(
                    "DELETE FROM settings WHERE key = ?",
                    ("managed_classes",),
                )

    def test_expired_registration_codes_are_deleted_automatically(self):
        expired_code = "expired-test-code"
        valid_code = "valid-test-code"
        assessment_app.execute(
            """INSERT INTO subject_access_codes
            (subject, role, code, expires_at, active, created_by, created_at)
            VALUES (?, 'student', ?, ?, 1, ?, ?)""",
            (
                "",
                expired_code,
                (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds"),
                self.admin_id,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        assessment_app.execute(
            """INSERT INTO subject_access_codes
            (subject, role, code, expires_at, active, created_by, created_at)
            VALUES (?, 'student', ?, ?, 1, ?, ?)""",
            (
                "",
                valid_code,
                (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds"),
                self.admin_id,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )

        self.assertFalse(assessment_app.valid_access_code(expired_code, "student"))
        self.assertIsNone(
            assessment_app.query(
                "SELECT id FROM subject_access_codes WHERE code = ?",
                (expired_code,),
                one=True,
            )
        )
        self.assertTrue(assessment_app.valid_access_code(valid_code, "student"))
        assessment_app.execute(
            "DELETE FROM subject_access_codes WHERE code = ?",
            (valid_code,),
        )

    def test_admin_page_shows_local_backup_button_and_teacher_class_field(self):
        response = self.client.get("/admin")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('action="/admin/backups/create"', page)
        self.assertIn("Create local backup", page)
        self.assertIn('name="teacher_classes"', page)
        self.assertIn("Sync now", page)

    def test_local_backup_can_be_downloaded_and_restored_with_safety_copy(self):
        original_backup_dir = assessment_app.LOCAL_BACKUP_DIR
        original_upload_dir = assessment_app.UPLOAD_DIR
        with tempfile.TemporaryDirectory(prefix="assessment-admin-backup-") as backup_dir, tempfile.TemporaryDirectory(
            prefix="assessment-admin-uploads-"
        ) as uploads_dir:
            assessment_app.LOCAL_BACKUP_DIR = Path(backup_dir)
            assessment_app.UPLOAD_DIR = Path(uploads_dir)
            (assessment_app.UPLOAD_DIR / "before.txt").write_text("before", encoding="utf-8")
            try:
                create_response = self.client.post("/admin/backups/create")
                self.assertEqual(create_response.status_code, 302)
                backup = assessment_app.available_local_backups()[0]["name"]
                download = self.client.get(f"/admin/backups/{backup}")
                self.assertEqual(download.status_code, 200)
                self.assertEqual(download.mimetype, "application/zip")
                download.close()

                assessment_app.execute(
                    "INSERT INTO settings(key, value) VALUES (?, ?)",
                    ("local_restore_test", "should be removed"),
                )
                (assessment_app.UPLOAD_DIR / "after.txt").write_text("after", encoding="utf-8")
                restore_response = self.client.post(
                    "/admin/backups/restore",
                    data={"backup_name": backup, "restore_confirmation": "RESTORE"},
                )

                self.assertEqual(restore_response.status_code, 302)
                self.assertEqual(restore_response.location, "/login")
                self.assertIsNone(
                    assessment_app.query(
                        "SELECT value FROM settings WHERE key = ?",
                        ("local_restore_test",),
                        one=True,
                    )
                )
                self.assertTrue((assessment_app.UPLOAD_DIR / "before.txt").exists())
                self.assertFalse((assessment_app.UPLOAD_DIR / "after.txt").exists())
                self.assertEqual(len(assessment_app.available_local_backups()), 2)
                with self.client.session_transaction() as session:
                    self.assertNotIn("user_id", session)
            finally:
                assessment_app.LOCAL_BACKUP_DIR = original_backup_dir
                assessment_app.UPLOAD_DIR = original_upload_dir

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
            results = self.client.get(
                "/reports/results?class_name=SS1&subject=Biology&exam_type=quiz"
            ).get_data(as_text=True)
            detailed_report = self.client.get(
                "/reports/results/details.csv?class_name=SS1&subject=Biology&exam_type=quiz"
            ).get_data(as_text=True)

            for output in (dashboard, rankings, report, results, detailed_report):
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
