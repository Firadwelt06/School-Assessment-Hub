CREATE TABLE IF NOT EXISTS portal_admins (
    username TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS portal_admin_sessions (
    token_hash TEXT PRIMARY KEY,
    username TEXT NOT NULL REFERENCES portal_admins(username) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS portal_admin_sessions_expiry_idx
    ON portal_admin_sessions(expires_at);
