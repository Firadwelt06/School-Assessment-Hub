ALTER TABLE teachers ADD COLUMN subjects TEXT NOT NULL DEFAULT '[]';
ALTER TABLE teachers ADD COLUMN classes TEXT NOT NULL DEFAULT '[]';

CREATE TABLE IF NOT EXISTS exam_results (
    id TEXT PRIMARY KEY,
    student_name TEXT NOT NULL,
    student_username TEXT NOT NULL,
    class_name TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    subject TEXT NOT NULL,
    exam_type TEXT NOT NULL,
    score REAL NOT NULL,
    total INTEGER NOT NULL,
    submitted_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS exam_results_scope_idx
    ON exam_results(subject, class_name, submitted_at DESC);
