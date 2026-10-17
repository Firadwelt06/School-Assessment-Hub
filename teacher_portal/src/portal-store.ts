export interface Teacher {
  id: string;
  username: string;
  full_name: string;
}

export interface PortalAdmin {
  username: string;
  full_name: string;
}

export interface TeacherAccount {
  username: string;
  full_name: string;
  password_hash: string;
  active: boolean;
}

export interface Submission {
  id: string;
  teacher_id: string;
  teacher_name?: string;
  teacher_username?: string;
  subject: string;
  topic: string;
  class_name: string;
  stem: string;
  option_a: string;
  option_b: string;
  option_c: string;
  option_d: string;
  correct_option: string;
  difficulty: string;
  explanation: string;
  standard: string;
  image_key: string | null;
  status: "pending" | "approved" | "rejected";
  feedback: string;
  submitted_at: string;
  decided_at?: string;
}

export interface NewSubmission {
  id: string;
  teacher_id: string;
  teacher_name: string;
  teacher_username: string;
  subject: string;
  topic: string;
  class_name: string;
  stem: string;
  option_a: string;
  option_b: string;
  option_c: string;
  option_d: string;
  correct_option: string;
  difficulty: string;
  explanation: string;
  standard: string;
  image_key: string | null;
  status: "pending";
  feedback: "";
  submitted_at: string;
}

export interface RateLimitRecord {
  attempts: number;
  window_started: number;
}

export interface PortalStore {
  getRateLimit(rateKey: string): Promise<RateLimitRecord | null>;
  recordRateLimitedAttempt(rateKey: string, now: number): Promise<void>;
  findTeacherForSession(tokenHash: string, now: number): Promise<Teacher | null>;
  findTeacherForLogin(username: string): Promise<(Teacher & { password_hash: string; active: boolean }) | null>;
  createTeacher(input: {
    id: string;
    username: string;
    full_name: string;
    password_hash: string;
    created_at: string;
  }): Promise<boolean>;
  deleteExpiredSessions(now: number): Promise<void>;
  createSession(input: { token_hash: string; teacher_id: string; expires_at: number }): Promise<void>;
  deleteSession(tokenHash: string): Promise<void>;
  getTeacherPassword(teacherId: string): Promise<{ password_hash: string } | null>;
  updateTeacherPassword(teacherId: string, passwordHash: string): Promise<void>;
  deleteTeacherSessions(teacherId: string): Promise<void>;
  findAdminForLogin(username: string): Promise<(PortalAdmin & { password_hash: string }) | null>;
  findAdminForSession(tokenHash: string, now: number): Promise<PortalAdmin | null>;
  saveAdmin(input: PortalAdmin & { password_hash: string }): Promise<void>;
  createAdminSession(input: { token_hash: string; username: string; expires_at: number }): Promise<void>;
  deleteAdminSession(tokenHash: string): Promise<void>;
  createSubmission(submission: NewSubmission, imageUploadKey?: string): Promise<void>;
  createImageUpload(key: string, teacherId: string, expiresAt: number): Promise<void>;
  ownsImageUpload(key: string, teacherId: string, now: number): Promise<boolean>;
  removeImageUpload(key: string): Promise<void>;
  listTeacherSubmissions(teacherId: string): Promise<Submission[]>;
  getTeacherSubmissionImageKey(id: string, teacherId: string): Promise<string | null>;
  getSubmissionImageKey(id: string): Promise<string | null>;
  listPendingSubmissions(cursor: string): Promise<Array<Omit<Submission, "image_key" | "status" | "feedback"> & { image: boolean }>>;
  listAdminSubmissions(status: Submission["status"] | "all"): Promise<Submission[]>;
  listReviewedSubmissions(cursor: string): Promise<Submission[]>;
  applyDecision(id: string, status: "approved" | "rejected", feedback: string, decidedAt: string): Promise<"updated" | "already_synced" | "conflict">;
  findTeacherByUsername(username: string): Promise<{ id: string; active: boolean } | null>;
  setTeacherActive(teacherId: string, active: boolean): Promise<void>;
  listTeacherAccounts(): Promise<TeacherAccount[]>;
  upsertTeacherAccount(account: TeacherAccount): Promise<void>;
}

export interface ImageStore {
  put(key: string, data: Uint8Array, contentType: string): Promise<void>;
  get(key: string): Promise<{ data: Uint8Array; contentType: string } | null>;
  getReadUrl(key: string): Promise<string | null>;
  getUploadUrl(
    key: string,
    contentType: string,
    size: number,
  ): Promise<{ url: string; headers: Record<string, string> } | null>;
  getAllowedImageSource(): string | null;
  finalizeUpload(key: string): Promise<void>;
  delete(key: string): Promise<void>;
}

export interface PortalEnv {
  store: PortalStore;
  images: ImageStore;
  SCHOOL_SIGNUP_CODE: string;
  SYNC_TOKEN: string;
}
