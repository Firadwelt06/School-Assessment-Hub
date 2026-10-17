import type {
  ImageStore,
  NewSubmission,
  PortalStore,
  RateLimitRecord,
  Submission,
  Teacher,
} from "./portal-store.js";

export class D1PortalStore implements PortalStore {
  constructor(private readonly db: D1Database) {}

  getRateLimit(rateKey: string) {
    return this.db.prepare(
      "SELECT attempts, window_started FROM rate_limits WHERE rate_key = ?",
    ).bind(rateKey).first<RateLimitRecord>();
  }

  async recordRateLimitedAttempt(rateKey: string, now: number) {
    await this.db.prepare(
      `INSERT INTO rate_limits(rate_key, attempts, window_started) VALUES (?, 1, ?)
       ON CONFLICT(rate_key) DO UPDATE SET
       attempts = CASE WHEN ? - window_started >= 900 THEN 1 ELSE attempts + 1 END,
       window_started = CASE WHEN ? - window_started >= 900 THEN ? ELSE window_started END`,
    ).bind(rateKey, now, now, now, now).run();
  }

  async findTeacherForSession(tokenHash: string, now: number) {
    const teacher = await this.db.prepare(
      `SELECT teachers.id, teachers.username, teachers.full_name
       FROM sessions JOIN teachers ON teachers.id = sessions.teacher_id
       WHERE sessions.token_hash = ? AND sessions.expires_at > ? AND teachers.active = 1`,
    ).bind(tokenHash, now).first<Teacher & { id: number }>();
    return teacher ? { ...teacher, id: String(teacher.id) } : null;
  }

  async findTeacherForLogin(username: string) {
    const teacher = await this.db.prepare(
      "SELECT id, username, full_name, password_hash, active FROM teachers WHERE username = ? AND active = 1",
    ).bind(username).first<Omit<Teacher, "id"> & { id: number; password_hash: string; active: number }>();
    return teacher
      ? { ...teacher, id: String(teacher.id), active: Boolean(teacher.active) }
      : null;
  }

  async createTeacher(input: {
    id: string;
    username: string;
    full_name: string;
    password_hash: string;
    created_at: string;
  }) {
    try {
      await this.db.prepare(
        "INSERT INTO teachers(username, full_name, password_hash, created_at) VALUES (?, ?, ?, ?)",
      ).bind(input.username, input.full_name, input.password_hash, input.created_at).run();
      return true;
    } catch (error) {
      if (String(error).includes("UNIQUE constraint failed")) return false;
      throw error;
    }
  }

  async deleteExpiredSessions(now: number) {
    await this.db.prepare("DELETE FROM sessions WHERE expires_at <= ?").bind(now).run();
  }

  async createSession(input: { token_hash: string; teacher_id: string; expires_at: number }) {
    await this.db.prepare(
      "INSERT INTO sessions(token_hash, teacher_id, expires_at) VALUES (?, ?, ?)",
    ).bind(input.token_hash, Number(input.teacher_id), input.expires_at).run();
  }

  async deleteSession(tokenHash: string) {
    await this.db.prepare("DELETE FROM sessions WHERE token_hash = ?").bind(tokenHash).run();
  }

  async getTeacherPassword(teacherId: string) {
    return this.db.prepare(
      "SELECT password_hash FROM teachers WHERE id = ? AND active = 1",
    ).bind(Number(teacherId)).first<{ password_hash: string }>();
  }

  async updateTeacherPassword(teacherId: string, passwordHash: string) {
    await this.db.prepare("UPDATE teachers SET password_hash = ? WHERE id = ?")
      .bind(passwordHash, Number(teacherId)).run();
  }

  async deleteTeacherSessions(teacherId: string) {
    await this.db.prepare("DELETE FROM sessions WHERE teacher_id = ?").bind(Number(teacherId)).run();
  }

  async createSubmission(submission: NewSubmission, _imageUploadKey?: string) {
    await this.db.prepare(
      `INSERT INTO question_submissions
      (id, teacher_id, subject, topic, class_name, stem, option_a, option_b, option_c,
       option_d, correct_option, difficulty, explanation, standard, image_key, status, submitted_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)`,
    ).bind(
      submission.id,
      Number(submission.teacher_id),
      submission.subject,
      submission.topic,
      submission.class_name,
      submission.stem,
      submission.option_a,
      submission.option_b,
      submission.option_c,
      submission.option_d,
      submission.correct_option,
      submission.difficulty,
      submission.explanation,
      submission.standard,
      submission.image_key,
      submission.submitted_at,
    ).run();
  }

  async createImageUpload(_key: string, _teacherId: string, _expiresAt: number) {}

  async ownsImageUpload(_key: string, _teacherId: string, _now: number) {
    return false;
  }

  async removeImageUpload(_key: string) {}

  async listTeacherSubmissions(teacherId: string) {
    const result = await this.db.prepare(
      "SELECT * FROM question_submissions WHERE teacher_id = ? ORDER BY submitted_at DESC LIMIT 100",
    ).bind(Number(teacherId)).all<Submission>();
    return result.results.map((item) => ({ ...item, teacher_id: String(item.teacher_id) }));
  }

  async getTeacherSubmissionImageKey(id: string, teacherId: string) {
    const submission = await this.db.prepare(
      "SELECT image_key FROM question_submissions WHERE id = ? AND teacher_id = ?",
    ).bind(id, Number(teacherId)).first<{ image_key: string | null }>();
    return submission?.image_key ?? null;
  }

  async getSubmissionImageKey(id: string) {
    const submission = await this.db.prepare(
      "SELECT image_key FROM question_submissions WHERE id = ?",
    ).bind(id).first<{ image_key: string | null }>();
    return submission?.image_key ?? null;
  }

  async listPendingSubmissions(cursor: string) {
    const result = await this.db.prepare(
      `SELECT s.id, s.teacher_id, t.full_name AS teacher_name, t.username AS teacher_username,
        s.subject, s.topic, s.class_name, s.stem, s.option_a, s.option_b, s.option_c, s.option_d,
        s.correct_option, s.difficulty, s.explanation, s.standard, s.image_key IS NOT NULL AS image,
        s.submitted_at
       FROM question_submissions s JOIN teachers t ON t.id = s.teacher_id
       WHERE s.status = 'pending' AND s.id > ?
       ORDER BY s.id LIMIT 101`,
    ).bind(cursor).all<Omit<Submission, "image_key" | "status" | "feedback"> & { image: number; teacher_id: number }>();
    return result.results.map((item) => ({ ...item, teacher_id: String(item.teacher_id), image: Boolean(item.image) }));
  }

  async applyDecision(
    id: string,
    status: "approved" | "rejected",
    feedback: string,
    decidedAt: string,
  ): Promise<"updated" | "already_synced" | "conflict"> {
    const update = await this.db.prepare(
      "UPDATE question_submissions SET status = ?, feedback = ?, decided_at = ? WHERE id = ? AND status = 'pending'",
    ).bind(status, feedback, decidedAt, id).run();
    if (update.meta.changes > 0) return "updated";
    const current = await this.db.prepare(
      "SELECT status FROM question_submissions WHERE id = ?",
    ).bind(id).first<{ status: string }>();
    return current?.status === status ? "already_synced" : "conflict";
  }

  async findTeacherByUsername(username: string) {
    const teacher = await this.db.prepare(
      "SELECT id, active FROM teachers WHERE username = ?",
    ).bind(username).first<{ id: number; active: number }>();
    return teacher ? { id: String(teacher.id), active: Boolean(teacher.active) } : null;
  }

  async setTeacherActive(teacherId: string, active: boolean) {
    await this.db.prepare("UPDATE teachers SET active = ? WHERE id = ?")
      .bind(Number(active), Number(teacherId)).run();
  }
}

export class R2ImageStore implements ImageStore {
  constructor(private readonly bucket: R2Bucket) {}

  async put(key: string, data: Uint8Array, contentType: string) {
    await this.bucket.put(key, data, {
      httpMetadata: { contentType, cacheControl: "private, no-store" },
    });
  }

  async get(key: string) {
    const object = await this.bucket.get(key);
    if (!object) return null;
    return {
      data: new Uint8Array(await object.arrayBuffer()),
      contentType: object.httpMetadata?.contentType ?? "application/octet-stream",
    };
  }

  async getReadUrl(_key: string) {
    return null;
  }

  async getUploadUrl(_key: string, _contentType: string, _size: number) {
    return null;
  }

  getAllowedImageSource() {
    return null;
  }

  async finalizeUpload(_key: string) {}

  async delete(key: string) {
    await this.bucket.delete(key);
  }
}
