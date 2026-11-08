CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS sessions_expiry_idx ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS question_submissions (
    id TEXT PRIMARY KEY,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id),
    subject TEXT NOT NULL,
    topic TEXT NOT NULL,
    class_name TEXT NOT NULL DEFAULT '',
    stem TEXT NOT NULL,
    option_a TEXT NOT NULL,
    option_b TEXT NOT NULL,
    option_c TEXT NOT NULL,
    option_d TEXT NOT NULL,
    correct_option TEXT NOT NULL CHECK(correct_option IN ('A', 'B', 'C', 'D')),
    difficulty TEXT NOT NULL CHECK(difficulty IN ('easy', 'medium', 'hard')),
    explanation TEXT NOT NULL DEFAULT '',
    standard TEXT NOT NULL DEFAULT '',
    image_key TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
    feedback TEXT NOT NULL DEFAULT '',
    submitted_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE INDEX IF NOT EXISTS submissions_teacher_idx ON question_submissions(teacher_id, submitted_at DESC);
CREATE INDEX IF NOT EXISTS submissions_pending_idx ON question_submissions(status, id);

CREATE TABLE IF NOT EXISTS rate_limits (
    rate_key TEXT PRIMARY KEY,
    attempts INTEGER NOT NULL,
    window_started INTEGER NOT NULL
);
