import type { NewSubmission, PortalAdmin, PortalBranding, PortalEnv as Env, Submission, Teacher, TeacherAccount } from "./portal-store.js";

const SESSION_SECONDS = 7 * 24 * 60 * 60;
const RATE_LIMIT_WINDOW_SECONDS = 15 * 60;
const IMAGE_MAX_BYTES = 5 * 1024 * 1024;
const IMAGE_MIME_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);
const UUID_PATTERN = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
const PASSWORD_ITERATIONS = 100_000;
const DEFAULT_BRANDING: PortalBranding = {
  school_name: "School Assessment Hub",
  logo_present: false,
};
const BRAND_LOGO_KEY = "school-branding/logo";
const BRAND_LOGO_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);
const BRAND_LOGO_MAX_BYTES = 4 * 1024 * 1024;

const escapeHtml = (value: unknown) =>
  String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]!);

const json = (payload: unknown, status = 200, extraHeaders: HeadersInit = {}) =>
  new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      ...extraHeaders,
    },
  });

function page(
  title: string,
  content: string,
  teacher?: Teacher,
  notice = "",
  imageSource: string | null = null,
  script = "",
  admin?: PortalAdmin,
  branding: PortalBranding = DEFAULT_BRANDING,
  portalOrigin = "https://portal.invalid",
) {
  const nonce = toBase64Url(crypto.getRandomValues(new Uint8Array(18)));
  const description = `Online teacher portal for ${branding.school_name}: submit questions for school review.`;
  const previewImage = branding.logo_present ? `${portalOrigin}/brand/logo` : "";
  const nav = teacher
    ? `<header><a class="brand" href="/">${branding.logo_present ? '<img src="/brand/logo" alt="">' : ""}${escapeHtml(branding.school_name)}</a><span>${escapeHtml(teacher.full_name)} · ${escapeHtml(teacher.username)}</span><form method="post" action="/logout"><button>Sign out</button></form></header>`
    : admin
      ? `<header><a class="brand" href="/admin">${branding.logo_present ? '<img src="/brand/logo" alt="">' : ""}${escapeHtml(branding.school_name)}</a><span>Administrator · ${escapeHtml(admin.full_name)}</span><form method="post" action="/admin/logout"><button>Sign out</button></form></header>`
    : `<header><a class="brand" href="/">${branding.logo_present ? '<img src="/brand/logo" alt="">' : ""}${escapeHtml(branding.school_name)}</a><span>Teacher question portal</span></header>`;
  return new Response(
    `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(title)} · ${escapeHtml(branding.school_name)}</title><meta name="description" content="${escapeHtml(description)}"><meta property="og:type" content="website"><meta property="og:title" content="${escapeHtml(branding.school_name)}"><meta property="og:description" content="${escapeHtml(description)}">${previewImage ? `<meta property="og:image" content="${escapeHtml(previewImage)}"><meta property="og:image:secure_url" content="${escapeHtml(previewImage)}"><meta name="twitter:card" content="summary"><meta name="twitter:image" content="${escapeHtml(previewImage)}">` : ""}<style>
      :root{font-family:system-ui,Segoe UI,sans-serif;color:#172b4d;background:#f3f6fa}body{margin:0}header{display:flex;gap:1rem;align-items:center;justify-content:space-between;padding:1rem max(1rem,calc((100% - 960px)/2));background:#102a43;color:#fff}header a{color:#fff;font-weight:700;text-decoration:none}.brand{display:flex;align-items:center;gap:.6rem}.brand img{width:2rem;height:2rem;object-fit:contain;background:#fff;border-radius:4px}header span{font-size:.9rem}main{max-width:960px;margin:2rem auto;padding:0 1rem}.panel{background:#fff;border:1px solid #d7e0ea;border-radius:12px;padding:1.25rem;margin:1rem 0}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}label{display:block;font-weight:600}label small{display:block;color:#52677d;font-weight:400}input,select,textarea{box-sizing:border-box;width:100%;padding:.7rem;border:1px solid #829ab1;border-radius:6px;margin-top:.35rem;font:inherit}textarea{min-height:6rem}button,.button{display:inline-block;border:0;border-radius:6px;padding:.7rem 1rem;background:#0b65a5;color:white;font:inherit;font-weight:600;text-decoration:none;cursor:pointer}button.secondary{background:#e7eef5;color:#102a43}button.danger{background:#a61b1b}.full{grid-column:1/-1}.notice{padding:.8rem 1rem;background:#e6f4ea;border-radius:6px}.error{background:#fde8e8}.muted{color:#52677d}.status{font-weight:700}.status-pending{color:#8a4b08}.status-approved{color:#16723c}.status-rejected{color:#a61b1b}img.submission-image{display:block;max-width:min(100%,420px);max-height:320px;object-fit:contain;margin:.75rem 0;border:1px solid #d7e0ea}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:.7rem;border-bottom:1px solid #d7e0ea;vertical-align:top}.actions{display:flex;gap:.5rem;flex-wrap:wrap}@media(max-width:640px){header{flex-wrap:wrap}.grid{grid-template-columns:1fr}.full{grid-column:auto}table{display:block;overflow:auto}}
    </style></head><body>${nav}<main>${notice ? `<p class="notice">${escapeHtml(notice)}</p>` : ""}${content}</main>${script ? `<script nonce="${nonce}">${script}</script>` : ""}</body></html>`,
    {
      status: 200,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
        "Content-Security-Policy": `default-src 'self'; img-src 'self'${imageSource ? ` ${imageSource}` : ""}; connect-src 'self'${imageSource ? ` ${imageSource}` : ""}; script-src 'nonce-${nonce}'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'`,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "same-origin",
      },
    },
  );
}

function redirect(location: string, headers: HeadersInit = {}) {
  return new Response(null, { status: 303, headers: { Location: location, ...headers } });
}

function setCookie(token: string, maxAge = SESSION_SECONDS, secure = true) {
  return `portal_session=${token}; Path=/; HttpOnly;${secure ? " Secure;" : ""} SameSite=Lax; Max-Age=${maxAge}`;
}

function clearCookie(secure = true) {
  return `portal_session=; Path=/; HttpOnly;${secure ? " Secure;" : ""} SameSite=Lax; Max-Age=0`;
}

function setAdminCookie(token: string, secure = true) {
  return `portal_admin_session=${token}; Path=/admin; HttpOnly;${secure ? " Secure;" : ""} SameSite=Lax; Max-Age=${SESSION_SECONDS}`;
}

function clearAdminCookie(secure = true) {
  return `portal_admin_session=; Path=/admin; HttpOnly;${secure ? " Secure;" : ""} SameSite=Lax; Max-Age=0`;
}

function toHex(value: ArrayBuffer) {
  return [...new Uint8Array(value)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function fromHex(value: string) {
  return new Uint8Array(value.match(/.{2}/g)?.map((byte) => parseInt(byte, 16)) ?? []);
}

function toBase64Url(value: Uint8Array) {
  let binary = "";
  for (const byte of value) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromBase64Url(value: string) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=")), (char) =>
    char.charCodeAt(0),
  );
}

async function sha256(value: string) {
  return toHex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)));
}

async function hashPassword(
  password: string,
  salt = crypto.getRandomValues(new Uint8Array(16)),
  iterations = PASSWORD_ITERATIONS,
) {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", salt, iterations, hash: "SHA-256" },
    key,
    256,
  );
  return `pbkdf2$${iterations}$${toHex(salt.buffer)}$${toHex(bits)}`;
}

async function verifyPassword(password: string, stored: string) {
  const localHash = stored.match(/^([a-f0-9]{32})\$([a-f0-9]{64})$/i);
  if (localHash) {
    const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]);
    const bits = await crypto.subtle.deriveBits(
      { name: "PBKDF2", salt: new TextEncoder().encode(localHash[1]), iterations: 120_000, hash: "SHA-256" },
      key,
      256,
    );
    const candidate = toHex(bits);
    return candidate.length === localHash[2].length &&
      [...candidate].reduce((difference, character, index) =>
        difference | character.charCodeAt(0) ^ localHash[2].charCodeAt(index), 0) === 0;
  }
  const [algorithm, iterationsValue, saltValue, digest] = stored.split("$");
  if (algorithm !== "pbkdf2" || !iterationsValue || !saltValue || !digest) return false;
  const iterations = Number(iterationsValue);
  if (!Number.isInteger(iterations) || iterations < 100_000 || iterations > PASSWORD_ITERATIONS) return false;
  const candidate = await hashPassword(password, fromHex(saltValue), iterations);
  const candidateDigest = candidate.split("$")[3];
  if (candidateDigest.length !== digest.length) return false;
  let difference = 0;
  for (let index = 0; index < digest.length; index++) {
    difference |= digest.charCodeAt(index) ^ candidateDigest.charCodeAt(index);
  }

  return difference === 0;
}

function isPortablePasswordHash(value: unknown): value is string {
  return typeof value === "string" &&
    (/^[a-f0-9]{32}\$[a-f0-9]{64}$/i.test(value) ||
      /^pbkdf2\$100000\$[a-f0-9]{32}\$[a-f0-9]{64}$/i.test(value));
}

function formValue(form: FormData, key: string) {
  const value = form.get(key);
  return typeof value === "string" ? value : "";
}

function text(form: FormData, key: string) {
  return formValue(form, key).trim();
}

function normalizeUsername(value: string) {
  return value.trim().toLowerCase();
}

async function sameSecret(expected: string, supplied: string) {
  const expectedBytes = new TextEncoder().encode(expected);
  const suppliedBytes = new TextEncoder().encode(supplied);
  let difference = expectedBytes.length ^ suppliedBytes.length;
  const length = Math.max(expectedBytes.length, suppliedBytes.length);
  for (let index = 0; index < length; index++) {
    difference |= (expectedBytes[index] ?? 0) ^ (suppliedBytes[index] ?? 0);
  }
  return difference === 0;
}

async function rateLimitState(env: Env, request: Request, action: string) {
  const address = request.headers.get("CF-Connecting-IP")
    || request.headers.get("x-portal-client-ip")
    || "unknown";
  const key = await sha256(`${action}:${address}`);
  const now = Math.floor(Date.now() / 1000);
  const record = await env.store.getRateLimit(key);
  if (
    record &&
    now - record.window_started < RATE_LIMIT_WINDOW_SECONDS &&
    record.attempts >= 10
  ) {
    return { key, now, limited: true };
  }
  return { key, now, limited: false };
}

async function recordRateLimitedAttempt(env: Env, state: { key: string; now: number }) {
  await env.store.recordRateLimitedAttempt(state.key, state.now);
}

async function getTeacher(request: Request, env: Env): Promise<Teacher | null> {
  const token = request.headers.get("Cookie")?.match(/(?:^|;\s*)portal_session=([A-Za-z0-9_-]+)/)?.[1];
  if (!token) return null;
  const tokenHash = await sha256(token);
  const now = Math.floor(Date.now() / 1000);
  return env.store.findTeacherForSession(tokenHash, now);
}

async function getPortalAdmin(request: Request, env: Env): Promise<PortalAdmin | null> {
  const token = request.headers.get("Cookie")?.match(/(?:^|;\s*)portal_admin_session=([A-Za-z0-9_-]+)/)?.[1];
  if (!token) return null;
  return env.store.findAdminForSession(await sha256(token), Math.floor(Date.now() / 1000));
}

function validOrigin(request: Request) {
  return request.headers.get("Origin") === new URL(request.url).origin;
}

async function requireSyncToken(request: Request, env: Env) {
  const configured = env.SYNC_TOKEN ?? "";
  const supplied = request.headers.get("Authorization")?.replace(/^Bearer\s+/i, "") ?? "";
  return configured.length >= 32 && await sameSecret(configured, supplied);
}

async function readJson(request: Request, maxBytes = 64 * 1024) {
  const length = Number(request.headers.get("Content-Length") ?? 0);
  if (length > maxBytes) throw new Error("Request body is too large.");
  const body = await request.text();
  if (new TextEncoder().encode(body).length > maxBytes) throw new Error("Request body is too large.");
  return JSON.parse(body) as Record<string, unknown>;
}

function requestPortalOrigin(request: Request) {
  return `https://${new URL(request.url).host}`;
}

function loginPage(notice = "", success = false, branding = DEFAULT_BRANDING, portalOrigin = "https://portal.invalid") {
  const noticeBlock = notice
    ? `<p class="notice ${success ? "" : "error"}">${escapeHtml(notice)}</p>`
    : "";
  return page(
    "Teacher sign in",
    `<section class="panel"><h1>Teacher sign in</h1><p class="muted">Use your portal username and password.</p>${noticeBlock}
    <form method="post" action="/login" class="grid"><label class="full">Username<input name="username" autocomplete="username" required maxlength="64"></label>
    <label class="full">Password<input name="password" type="password" autocomplete="current-password" required maxlength="128"></label>
    <div class="full"><button>Sign in</button></div></form><p>New here? <a href="/register">Create a teacher account</a> with your school's signup code.</p></section>`,
    undefined, "", null, "", undefined, branding, portalOrigin,
  );
}

function registerPage(error = "", branding = DEFAULT_BRANDING, portalOrigin = "https://portal.invalid") {
  const errorNotice = error ? `<p class="notice error">${escapeHtml(error)}</p>` : "";
  return page(
    "Create teacher account",
    `<section class="panel"><h1>Create teacher account</h1><p class="muted">Ask your school administrator for the shared signup code. Use an individual account; do not reuse your school-system password.</p>${errorNotice}
    <form method="post" action="/register" class="grid"><label>Full name<input name="full_name" autocomplete="name" required maxlength="100"></label>
    <label>Username<input name="username" autocomplete="username" required minlength="3" maxlength="64" pattern="[A-Za-z0-9._-]+"></label>
    <label class="full">School signup code<input name="signup_code" type="password" autocomplete="off" required maxlength="128"></label>
    <label class="full">Password<input name="password" type="password" autocomplete="new-password" required minlength="8" maxlength="128"><small>Use at least 8 characters. Password reset is handled by your school administrator.</small></label>
    <div class="full"><button>Create account</button></div></form><p>Already registered? <a href="/login">Sign in</a>.</p></section>`,
    undefined, "", null, "", undefined, branding, portalOrigin,
  );
}

function submissionCard(item: Submission) {
  const status = item.status;
  const image = item.image_key
    ? `<img class="submission-image" src="/submissions/${encodeURIComponent(item.id)}/image" alt="Attached question image">`
    : "";
  return `<article class="panel"><h2>${escapeHtml(item.subject)} · ${escapeHtml(item.topic)}</h2>
    <p class="muted">${escapeHtml(item.class_name || "All classes")} · Submitted ${escapeHtml(item.submitted_at)}</p>
    <p class="status status-${escapeHtml(status)}">${escapeHtml(status[0].toUpperCase() + status.slice(1))}</p>
    ${image}<p><strong>${escapeHtml(item.stem)}</strong></p>
    <ol type="A"><li>${escapeHtml(item.option_a)}</li><li>${escapeHtml(item.option_b)}</li><li>${escapeHtml(item.option_c)}</li><li>${escapeHtml(item.option_d)}</li></ol>
    <p>Correct answer: <strong>${escapeHtml(item.correct_option)}</strong> · Difficulty: ${escapeHtml(item.difficulty)}</p>
    ${item.explanation ? `<p><strong>Explanation:</strong> ${escapeHtml(item.explanation)}</p>` : ""}
    ${item.standard ? `<p><strong>Standard:</strong> ${escapeHtml(item.standard)}</p>` : ""}
    ${item.feedback ? `<p class="notice ${status === "rejected" ? "error" : ""}"><strong>Administrator feedback:</strong> ${escapeHtml(item.feedback)}</p>` : ""}</article>`;
}

const batchSubmissionScript = String.raw`(() => {
  const form = document.getElementById("batch-question-form");
  if (!form) return;
  const preview = document.getElementById("batch-preview");
  const previewButton = document.getElementById("batch-preview-button");
  const submitButton = document.getElementById("batch-submit-button");
  const textInput = form.elements.namedItem("batch_text");
  const fileInput = form.elements.namedItem("batch_file");
  let prepared = null;

  const metadata = () => ({
    subject: form.elements.namedItem("subject").value.trim(),
    topic: form.elements.namedItem("topic").value.trim(),
    class_name: form.elements.namedItem("class_name").value.trim(),
    difficulty: form.elements.namedItem("difficulty").value
  });
  const validate = (items, defaults) => items.map((item, index) => {
    const question = { ...item };
    question.subject = (typeof item.subject === "string" && item.subject.trim()) || defaults.subject;
    question.topic = (typeof item.topic === "string" && item.topic.trim()) || defaults.topic;
    question.class_name = (typeof item.class_name === "string" && item.class_name.trim()) || defaults.class_name;
    question.difficulty = (typeof item.difficulty === "string" && item.difficulty.trim()) || defaults.difficulty || "medium";
    ["stem", "option_a", "option_b", "option_c", "option_d", "explanation", "standard"].forEach((field) => {
      question[field] = typeof item[field] === "string" ? item[field].trim() : "";
    });
    question.correct_option = typeof item.correct_option === "string" ? item.correct_option.trim().toUpperCase() : "";
    question._errors = [];
    const textFields = ["subject", "topic", "class_name", "difficulty", "stem", "option_a", "option_b", "option_c", "option_d", "correct_option", "explanation", "standard"];
    if (textFields.some((field) => item[field] !== undefined && typeof item[field] !== "string")) {
      question._errors.push("Question fields must be text.");
    }
    ["subject", "topic", "stem", "option_a", "option_b", "option_c", "option_d"].forEach((field) => {
      if (!question[field]) question._errors.push("Missing " + field.replace("_", " ") + ".");
    });
    if (!["A", "B", "C", "D"].includes(question.correct_option)) question._errors.push("Answer must be A, B, C, or D.");
    if (!["easy", "medium", "hard"].includes(question.difficulty)) question._errors.push("Difficulty must be easy, medium, or hard.");
    if (question._errors.length) question._label = "Question " + (index + 1) + ": " + question._errors.join(" ");
    return question;
  });
  const parseText = (value) => {
    const starts = [...value.matchAll(/^\s*\d+[.)]\s+/gm)];
    return starts.map((match, index) => {
      const start = match.index;
      const end = index + 1 < starts.length ? starts[index + 1].index : value.length;
      const block = value.slice(start, end).split(/\r?\n/);
      block[0] = block[0].replace(/^\s*\d+[.)]\s+/, "");
      const result = { stem: "", option_a: "", option_b: "", option_c: "", option_d: "", correct_option: "" };
      let current = "";
      for (const line of block) {
        const answer = line.match(/^\s*(?:answer|correct answer)\s*:\s*([A-D])\b/i);
        if (answer) { result.correct_option = answer[1].toUpperCase(); current = ""; continue; }
        const option = line.match(/^\s*([A-D])[.)]\s*(.*)$/i);
        if (option) { current = "option_" + option[1].toLowerCase(); result[current] = option[2].trim(); continue; }
        if (current) result[current] += (result[current] ? "\n" : "") + line.trim();
        else result.stem += (result.stem ? "\n" : "") + line.trim();
      }
      return result;
    });
  };
  const readItems = async () => {
    const file = fileInput.files && fileInput.files[0];
    if (file) {
      const payload = JSON.parse(await file.text());
      const items = Array.isArray(payload) ? payload : payload.questions;
      if (!Array.isArray(items)) throw new Error("JSON must contain a questions array.");
      const defaults = metadata();
      if (!Array.isArray(payload) && payload && typeof payload === "object") {
        ["subject", "topic", "class_name", "difficulty"].forEach((field) => {
          if (!defaults[field] && typeof payload[field] === "string") defaults[field] = payload[field].trim();
        });
      }
      return validate(items, defaults);
    }
    return validate(parseText(textInput.value), metadata());
  };
  const renderPreview = (items) => {
    preview.replaceChildren();
    if (!items.length) {
      preview.textContent = "No numbered questions found. Start each question with 1. and include A-D options plus Answer: B.";
      return false;
    }
    const valid = items.length <= 50 && items.every((item) => !item._errors.length);
    if (items.length > 50) preview.textContent = "A batch can contain no more than 50 questions.";
    items.forEach((item, index) => {
      const card = document.createElement("p");
      card.textContent = (index + 1) + ". " + item.stem + (item._errors.length ? " — " + item._errors.join(" ") : "");
      preview.append(card);
    });
    return valid;
  };
  form.addEventListener("input", () => { prepared = null; submitButton.disabled = true; });
  form.addEventListener("change", () => { prepared = null; submitButton.disabled = true; });
  previewButton.addEventListener("click", async () => {
    try {
      const items = await readItems();
      const valid = renderPreview(items);
      prepared = valid ? { ...metadata(), questions: items.map(({ _errors, _label, ...item }) => item) } : null;
      submitButton.disabled = !prepared;
    } catch (error) {
      preview.textContent = error instanceof Error ? error.message : "Could not read the selected question file.";
      prepared = null;
      submitButton.disabled = true;
    }
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!prepared) return;
    submitButton.disabled = true;
    try {
      const response = await fetch("/api/batch-submissions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(prepared)
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Batch submission failed.");
      window.location.href = "/?notice=" + encodeURIComponent("Submitted " + result.submitted + " questions for review.");
    } catch (error) {
      preview.textContent = error instanceof Error ? error.message : "Batch submission failed.";
      submitButton.disabled = false;
    }
  });
})();`;

function dashboardPage(
  teacher: Teacher,
  submissions: Submission[],
  notice = "",
  imageSource: string | null = null,
  branding = DEFAULT_BRANDING,
  portalOrigin = "https://portal.invalid",
) {
  const directImageUpload = `(() => {
    const form = document.querySelector('form[action="/submit"]');
    const imageInput = form?.querySelector('input[name="question_image"]');
    if (!form || !imageInput) return;
    const imageKeyInput = document.createElement("input");
    imageKeyInput.type = "hidden";
    imageKeyInput.name = "question_image_key";
    form.append(imageKeyInput);
    let submitting = false;
    form.addEventListener("submit", async (event) => {
      const file = imageInput.files?.[0];
      if (submitting || !file) return;
      event.preventDefault();
      const button = form.querySelector("button");
      if (button) button.disabled = true;
      try {
        const preparedResponse = await fetch("/api/image-upload", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content_type: file.type, size: file.size }),
        });
        if (preparedResponse.status === 501) {
          submitting = true;
          form.requestSubmit();
          return;
        }
        const prepared = await preparedResponse.json();
        if (!preparedResponse.ok) throw new Error(prepared.error || "Could not prepare the image upload.");
        const uploadResponse = await fetch(prepared.upload_url, {
          method: "PUT",
          headers: prepared.upload_headers,
          body: file,
        });
        if (!uploadResponse.ok) throw new Error("The image upload failed. Please retry.");
        imageKeyInput.value = prepared.image_key;
        imageInput.disabled = true;
        submitting = true;
        form.requestSubmit();
      } catch (error) {
        window.alert(error instanceof Error ? error.message : "The image upload failed. Please retry.");
        if (button) button.disabled = false;
      }
    });
  })();`;
  const records = submissions.length
    ? submissions.map(submissionCard).join("")
    : `<section class="panel"><p>No question submissions yet. Use the form below to submit your first question.</p></section>`;
  return page(
    "Teacher portal",
    `<h1>Teacher question portal</h1><p class="muted">Your questions are sent to the school administrator for review. Approval adds them to the local question bank; it does not publish an exam.</p>
    <details class="panel"><summary>Change your portal password</summary><form method="post" action="/change-password" class="grid">
    <label>Current password<input name="current_password" type="password" autocomplete="current-password" required maxlength="128"></label>
    <label>New password<input name="new_password" type="password" autocomplete="new-password" minlength="8" maxlength="128" required></label>
    <div class="full"><button class="secondary">Change password</button></div></form></details>
    <section class="panel"><h2>Submit a question</h2><form method="post" action="/submit" enctype="multipart/form-data" class="grid">
    <label>Subject<input name="subject" required maxlength="120"></label><label>Topic<input name="topic" required maxlength="200"></label>
    <label>Class or level<input name="class_name" maxlength="120" placeholder="Optional"></label>
    <label>Difficulty<select name="difficulty"><option value="easy">Easy</option><option value="medium" selected>Medium</option><option value="hard">Hard</option></select></label>
    <label class="full">Question text<textarea name="stem" required maxlength="5000"></textarea></label>
    <label>Option A<input name="option_a" required maxlength="2000"></label><label>Option B<input name="option_b" required maxlength="2000"></label>
    <label>Option C<input name="option_c" required maxlength="2000"></label><label>Option D<input name="option_d" required maxlength="2000"></label>
    <label>Correct option<select name="correct_option" required><option value="">Choose</option><option>A</option><option>B</option><option>C</option><option>D</option></select></label>
    <label>Question image <small>Optional; PNG, JPG, WEBP, or GIF; maximum 5 MB</small><input type="file" name="question_image" accept="image/png,image/jpeg,image/webp,image/gif"></label>
    <label class="full">Explanation <small>Optional</small><textarea name="explanation" maxlength="5000"></textarea></label>
    <label class="full">Curriculum standard <small>Optional</small><input name="standard" maxlength="500"></label>
    <div class="full"><button>Submit question for review</button></div></form></section>
    <section class="panel"><h2>Submit a batch of questions</h2>
      <p class="muted">Paste plain-text multiple-choice questions, preview them, then submit up to 50 without images. For questions with pictures, use the single-question form above so each image is attached correctly.</p>
      <p><a href="/batch-template.json">Download the JSON batch template</a>. You can also import a JSON file exported by the offline question form.</p>
      <form id="batch-question-form" class="grid">
        <label>Subject<input name="subject" required maxlength="120"></label>
        <label>Topic<input name="topic" required maxlength="200"></label>
        <label>Class or level<input name="class_name" maxlength="120"></label>
        <label>Difficulty<select name="difficulty"><option value="easy">Easy</option><option value="medium" selected>Medium</option><option value="hard">Hard</option></select></label>
        <label class="full">Paste questions<textarea name="batch_text" rows="10" placeholder="1. Question text\\nA. Option one\\nB. Option two\\nC. Option three\\nD. Option four\\nAnswer: B"></textarea></label>
        <label class="full">Or choose an exported JSON question file<input name="batch_file" type="file" accept=".json,application/json"></label>
        <div class="full actions"><button type="button" class="secondary" id="batch-preview-button">Preview batch</button><button id="batch-submit-button" disabled>Submit batch</button></div>
        <div class="full" id="batch-preview" aria-live="polite"></div>
      </form>
    </section>
    <h2>Your submissions</h2>${records}`,
    teacher,
    notice,
    imageSource,
    `${directImageUpload}${batchSubmissionScript}`,
    undefined,
    branding,
    portalOrigin,
  );
}

function adminLoginPage(notice = "", branding = DEFAULT_BRANDING, portalOrigin = "https://portal.invalid") {
  return page(
    "Portal administrator sign in",
    `<h1>Administrator sign in</h1><section class="panel">
      <form method="post" action="/admin/login" class="grid">
        <label>Username<input name="username" required autocomplete="username" maxlength="64"></label>
        <label>Password<input name="password" type="password" required autocomplete="current-password" maxlength="128"></label>
        <div class="full"><button>Sign in</button></div>
      </form>
    </section>`,
    undefined,
    notice,
    null,
    "",
    undefined,
    branding,
    portalOrigin,
  );
}

function portalAdminPage(
  admin: PortalAdmin,
  submissions: Submission[],
  status: Submission["status"] | "all",
  notice = "",
  imageSource: string | null = null,
  branding = DEFAULT_BRANDING,
  portalOrigin = "https://portal.invalid",
) {
  const filters = [
    ["pending", "Pending"],
    ["approved", "Approved"],
    ["rejected", "Rejected"],
    ["all", "All"],
  ] as const;
  const content = `<h1>Online submission review</h1>
    <p class="muted">Reviewing here works without the school server. Decisions are copied into the local question bank on its next successful sync; approval does not publish an exam.</p>
    <nav class="actions" aria-label="Submission filters">${filters.map(([value, label]) =>
      `<a class="button secondary" href="/admin?status=${value}"${status === value ? ' aria-current="page"' : ""}>${label}</a>`,
    ).join("")}</nav>
    ${submissions.length ? submissions.map((item) => `<section class="panel">
      <h2>${escapeHtml(item.subject)} · ${escapeHtml(item.topic)}</h2>
      <p class="muted">${escapeHtml(item.teacher_name)} (${escapeHtml(item.teacher_username)}) · ${escapeHtml(item.class_name || "All classes")} · ${escapeHtml(item.submitted_at)}</p>
      <p><strong>Status:</strong> ${escapeHtml(item.status)}</p>
      ${item.image_key ? `<img class="submission-image" src="/admin/submissions/${encodeURIComponent(item.id)}/image" alt="Question image">` : ""}
      <p><strong>${escapeHtml(item.stem)}</strong></p>
      <ol type="A"><li>${escapeHtml(item.option_a)}</li><li>${escapeHtml(item.option_b)}</li><li>${escapeHtml(item.option_c)}</li><li>${escapeHtml(item.option_d)}</li></ol>
      <p>Correct option: <strong>${escapeHtml(item.correct_option)}</strong> · Difficulty: ${escapeHtml(item.difficulty)}</p>
      ${item.explanation ? `<p><strong>Explanation:</strong> ${escapeHtml(item.explanation)}</p>` : ""}
      ${item.standard ? `<p><strong>Standard:</strong> ${escapeHtml(item.standard)}</p>` : ""}
      ${item.feedback ? `<p class="notice"><strong>Feedback:</strong> ${escapeHtml(item.feedback)}</p>` : ""}
      ${item.status === "pending" ? `<form method="post" action="/admin/submissions/${encodeURIComponent(item.id)}/review" class="grid">
        <label class="full">Optional note<textarea name="feedback" maxlength="1000"></textarea></label>
        <div class="full actions"><button name="status" value="approved">Approve</button><button class="secondary" name="status" value="rejected">Reject</button></div>
      </form>` : ""}
    </section>`).join("") : `<section class="panel"><p>No submissions in this view.</p></section>`}`;
  return page("Online submission review", content, undefined, notice, imageSource, "", admin, branding, portalOrigin);
}

async function login(request: Request, env: Env) {
  const branding = await env.store.getBranding();
  const portalOrigin = requestPortalOrigin(request);
  if (!validOrigin(request)) return loginPage("The sign-in request could not be verified.", false, branding, portalOrigin);
  const rateState = await rateLimitState(env, request, "login");
  if (rateState.limited) {
    return loginPage("Too many sign-in attempts. Please wait 15 minutes and try again.", false, branding, portalOrigin);
  }
  const form = await request.formData();
  const username = normalizeUsername(text(form, "username"));
  const password = formValue(form, "password");
  const teacher = await env.store.findTeacherForLogin(username);
  if (!teacher || password.length > 128 || !await verifyPassword(password, teacher.password_hash)) {
    await recordRateLimitedAttempt(env, rateState);
    return loginPage("Username or password is incorrect.", false, branding, portalOrigin);
  }
  const sessionToken = toBase64Url(crypto.getRandomValues(new Uint8Array(32)));
  const expiresAt = Math.floor(Date.now() / 1000) + SESSION_SECONDS;
  await env.store.deleteExpiredSessions(Math.floor(Date.now() / 1000));
  await env.store.createSession({
    token_hash: await sha256(sessionToken),
    teacher_id: teacher.id,
    expires_at: expiresAt,
  });
  return redirect("/", {
    "Set-Cookie": setCookie(sessionToken, SESSION_SECONDS, new URL(request.url).protocol === "https:"),
  });
}

async function loginAdmin(request: Request, env: Env) {
  const branding = await env.store.getBranding();
  const portalOrigin = requestPortalOrigin(request);
  if (!validOrigin(request)) return adminLoginPage("The sign-in request could not be verified.", branding, portalOrigin);
  const rateState = await rateLimitState(env, request, "admin-login");
  if (rateState.limited) return adminLoginPage("Too many sign-in attempts. Wait 15 minutes and try again.", branding, portalOrigin);
  const form = await request.formData();
  const username = normalizeUsername(text(form, "username"));
  const password = formValue(form, "password");
  const admin = await env.store.findAdminForLogin(username);
  if (!admin || password.length > 128 || !await verifyPassword(password, admin.password_hash)) {
    await recordRateLimitedAttempt(env, rateState);
    return adminLoginPage("Username or password is incorrect.", branding, portalOrigin);
  }
  const token = toBase64Url(crypto.getRandomValues(new Uint8Array(32)));
  await env.store.createAdminSession({
    token_hash: await sha256(token),
    username: admin.username,
    expires_at: Math.floor(Date.now() / 1000) + SESSION_SECONDS,
  });
  return redirect("/admin", {
    "Set-Cookie": setAdminCookie(token, new URL(request.url).protocol === "https:"),
  });
}

async function register(request: Request, env: Env) {
  const branding = await env.store.getBranding();
  const portalOrigin = requestPortalOrigin(request);
  if (!validOrigin(request)) return registerPage("The registration request could not be verified.", branding, portalOrigin);
  const rateState = await rateLimitState(env, request, "register");
  if (rateState.limited) {
    return registerPage("Too many account attempts. Please wait 15 minutes and try again.", branding, portalOrigin);
  }
  const form = await request.formData();
  const username = normalizeUsername(text(form, "username"));
  const fullName = text(form, "full_name").replace(/\s+/g, " ");
  const password = formValue(form, "password");
  const code = formValue(form, "signup_code");
  if (!env.SCHOOL_SIGNUP_CODE || !await sameSecret(env.SCHOOL_SIGNUP_CODE, code)) {
    await recordRateLimitedAttempt(env, rateState);
    return registerPage("The school signup code is not valid.", branding, portalOrigin);
  }
  if (!/^[a-z0-9._-]{3,64}$/.test(username)) {
    await recordRateLimitedAttempt(env, rateState);
    return registerPage("Use 3–64 letters, numbers, dots, underscores, or hyphens for your username.", branding, portalOrigin);
  }
  if (fullName.length < 2 || fullName.length > 100) {
    await recordRateLimitedAttempt(env, rateState);
    return registerPage("Enter a name between 2 and 100 characters.", branding, portalOrigin);
  }
  if (password.length < 8 || password.length > 128) {
    await recordRateLimitedAttempt(env, rateState);
    return registerPage("Choose a password between 8 and 128 characters.", branding, portalOrigin);
  }
  const created = await env.store.createTeacher({
    id: username,
    username,
    full_name: fullName,
    password_hash: await hashPassword(password),
    created_at: new Date().toISOString(),
  });
  if (!created) return registerPage("That username is already in use. Choose another one.", branding, portalOrigin);
  return loginPage("Your teacher account was created. Sign in to submit questions.", true, branding, portalOrigin);
}

async function submitQuestion(request: Request, env: Env, teacher: Teacher) {
  const branding = await env.store.getBranding();
  const portalOrigin = requestPortalOrigin(request);
  if (!validOrigin(request)) return json({ error: "The submission request could not be verified." }, 403);
  const contentLength = Number(request.headers.get("Content-Length") ?? 0);
  if (contentLength > IMAGE_MAX_BYTES + 128 * 1024) {
    return dashboardPage(
      teacher,
      await ownSubmissions(env, teacher.id),
      "Submission exceeds the 5 MB image limit.",
      env.images.getAllowedImageSource(),
      branding,
      portalOrigin,
    );
  }
  const showError = async (message: string) =>
    dashboardPage(teacher, await ownSubmissions(env, teacher.id), message, env.images.getAllowedImageSource(), branding, portalOrigin);
  const form = await request.formData();
  const submission = {
    subject: text(form, "subject"),
    topic: text(form, "topic"),
    class_name: text(form, "class_name"),
    stem: text(form, "stem"),
    option_a: text(form, "option_a"),
    option_b: text(form, "option_b"),
    option_c: text(form, "option_c"),
    option_d: text(form, "option_d"),
    correct_option: text(form, "correct_option").toUpperCase(),
    difficulty: text(form, "difficulty"),
    explanation: text(form, "explanation"),
    standard: text(form, "standard"),
  };
  const limits: Record<string, number> = {
    subject: 120, topic: 200, class_name: 120, stem: 5000,
    option_a: 2000, option_b: 2000, option_c: 2000, option_d: 2000,
    explanation: 5000, standard: 500,
  };
  for (const [field, maxLength] of Object.entries(limits)) {
    if (submission[field as keyof typeof submission].length > maxLength) {
      return showError(`${field.replace("_", " ")} is too long.`);
    }
  }
  if (!submission.subject || !submission.topic || !submission.stem ||
      !submission.option_a || !submission.option_b || !submission.option_c || !submission.option_d) {
    return showError("Subject, topic, question, and all four options are required.");
  }
  if (!["A", "B", "C", "D"].includes(submission.correct_option)) {
    return showError("Choose the correct option from A, B, C, or D.");
  }
  if (!["easy", "medium", "hard"].includes(submission.difficulty)) {
    return showError("Choose a valid difficulty.");
  }

  let imageKey: string | null = null;
  let imageUploadKey: string | undefined;
  const submittedImageKey = text(form, "question_image_key");
  const image = form.get("question_image");
  if (submittedImageKey) {
    const prefix = `teacher-submissions/images/${teacher.id}/`;
    const imageId = submittedImageKey.startsWith(prefix)
      ? submittedImageKey.slice(prefix.length)
      : "";
    if (!UUID_PATTERN.test(imageId) || !await env.store.ownsImageUpload(
      submittedImageKey,
      teacher.id,
      Math.floor(Date.now() / 1000),
    )) {
      return showError("The uploaded image is invalid or expired. Please upload it again.");
    }
    const uploadedImage = await env.images.get(submittedImageKey);
    if (
      !uploadedImage ||
      uploadedImage.data.length > IMAGE_MAX_BYTES ||
      !IMAGE_MIME_TYPES.has(uploadedImage.contentType) ||
      !validImageSignature(uploadedImage.data, uploadedImage.contentType)
    ) {
      return showError("The uploaded file is invalid. Please choose a PNG, JPG, WEBP, or GIF image up to 5 MB.");
    }
    imageKey = submittedImageKey;
    imageUploadKey = submittedImageKey;
  } else if (image && typeof image !== "string" && image.size > 0) {
    if (image.size > IMAGE_MAX_BYTES || !IMAGE_MIME_TYPES.has(image.type)) {
      return showError("Choose a PNG, JPG, WEBP, or GIF image up to 5 MB.");
    }
    const data = new Uint8Array(await image.arrayBuffer());
    if (!validImageSignature(data, image.type)) {
      return showError("The uploaded file does not match its image type.");
    }
    imageKey = `teacher-submissions/images/${crypto.randomUUID()}`;
    await env.images.put(imageKey, data, image.type);
  }

  const id = crypto.randomUUID();
  const submittedAt = new Date().toISOString();
  try {
    if (imageUploadKey) await env.images.finalizeUpload(imageUploadKey);
    await env.store.createSubmission({
      id,
      teacher_id: teacher.id,
      teacher_name: teacher.full_name,
      teacher_username: teacher.username,
      ...submission,
      image_key: imageKey,
      status: "pending",
      feedback: "",
      submitted_at: submittedAt,
    }, imageUploadKey);
  } catch (error) {
    if (imageKey) await env.images.delete(imageKey);
    if (imageUploadKey) await env.store.removeImageUpload(imageUploadKey);
    throw error;
  }
  return redirect("/", { "Location": "/?notice=Question%20submitted%20for%20administrator%20review." });
}

function validImageSignature(data: Uint8Array, mime: string) {
  if (mime === "image/png") {
    return data.length >= 8 && [137, 80, 78, 71, 13, 10, 26, 10].every((byte, index) => data[index] === byte);
  }
  if (mime === "image/jpeg") return data.length >= 3 && data[0] === 255 && data[1] === 216 && data[2] === 255;
  if (mime === "image/gif") {
    const signature = new TextDecoder().decode(data.slice(0, 6));
    return signature === "GIF87a" || signature === "GIF89a";
  }
  if (mime === "image/webp") {
    return data.length >= 12 &&
      new TextDecoder().decode(data.slice(0, 4)) === "RIFF" &&
      new TextDecoder().decode(data.slice(8, 12)) === "WEBP";
  }
  return false;
}

async function changePassword(request: Request, env: Env, teacher: Teacher) {
  const branding = await env.store.getBranding();
  const portalOrigin = requestPortalOrigin(request);
  if (!validOrigin(request)) return loginPage("The password-change request could not be verified.", false, branding, portalOrigin);
  const form = await request.formData();
  const currentPassword = formValue(form, "current_password");
  const newPassword = formValue(form, "new_password");
  const account = await env.store.getTeacherPassword(teacher.id);
  if (!account || !await verifyPassword(currentPassword, account.password_hash)) {
    const submissions = await ownSubmissions(env, teacher.id);
    return dashboardPage(teacher, submissions, "Current password is incorrect.", env.images.getAllowedImageSource(), branding, portalOrigin);
  }
  if (newPassword.length < 8 || newPassword.length > 128) {
    const submissions = await ownSubmissions(env, teacher.id);
    return dashboardPage(
      teacher,
      submissions,
      "New password must be between 8 and 128 characters.",
      env.images.getAllowedImageSource(),
      branding,
      portalOrigin,
    );
  }
  await env.store.updateTeacherPassword(teacher.id, await hashPassword(newPassword));
  await env.store.deleteTeacherSessions(teacher.id);
  const secure = new URL(request.url).protocol === "https:";
  return redirect("/login?notice=Password%20changed.%20Please%20sign%20in%20again.", {
    "Set-Cookie": clearCookie(secure),
  });
}

async function ownSubmissions(env: Env, teacherId: string) {
  return env.store.listTeacherSubmissions(teacherId);
}

async function serveTeacherImage(request: Request, env: Env, teacher: Teacher, id: string) {
  const imageKey = await env.store.getTeacherSubmissionImageKey(id, teacher.id);
  if (!imageKey) return new Response("Not found", { status: 404 });
  return serveImage(env, imageKey);
}

async function serveImage(env: Env, key: string) {
  const signedUrl = await env.images.getReadUrl(key);
  if (signedUrl) {
    return redirect(signedUrl, {
      "Cache-Control": "private, no-store",
      "Referrer-Policy": "no-referrer",
    });
  }
  const object = await env.images.get(key);
  if (!object) return new Response("Not found", { status: 404 });
  return new Response(new Uint8Array(object.data), {
    headers: {
      "Content-Type": object.contentType || "application/octet-stream",
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

async function syncPending(request: Request, env: Env) {
  if (!await requireSyncToken(request, env)) return json({ error: "Unauthorized." }, 401);
  const url = new URL(request.url);
  const cursor = url.searchParams.get("cursor") ?? "";
  if (cursor && !/^[0-9a-fA-F-]{36}$/.test(cursor)) return json({ error: "Invalid cursor." }, 400);
  const submissions = await env.store.listPendingSubmissions(cursor);
  const hasMore = submissions.length > 100;
  const pageItems = submissions.slice(0, 100).map(({ image, ...item }) => ({
    ...item,
    image: Boolean(image),
  }));
  return json({
    submissions: pageItems,
    next_cursor: hasMore ? pageItems[pageItems.length - 1].id : "",
  });
}

async function syncReviewed(request: Request, env: Env) {
  if (!await requireSyncToken(request, env)) return json({ error: "Unauthorized." }, 401);
  const cursor = new URL(request.url).searchParams.get("cursor") ?? "";
  if (cursor && !UUID_PATTERN.test(cursor)) return json({ error: "Invalid cursor." }, 400);
  const submissions = await env.store.listReviewedSubmissions(cursor);
  const hasMore = submissions.length > 100;
  const pageItems = submissions.slice(0, 100).map(({ image_key, ...item }) => ({
    ...item,
    image: Boolean(image_key),
  }));
  return json({
    submissions: pageItems,
    next_cursor: hasMore ? pageItems[pageItems.length - 1].id : "",
  });
}

async function syncSubmissionImage(request: Request, env: Env, id: string) {
  if (!await requireSyncToken(request, env)) return json({ error: "Unauthorized." }, 401);
  if (!/^[0-9a-fA-F-]{36}$/.test(id)) return json({ error: "Not found." }, 404);
  const imageKey = await env.store.getSubmissionImageKey(id);
  if (!imageKey) return json({ error: "Image not found." }, 404);
  return serveImage(env, imageKey);
}

async function syncTeacherAccounts(request: Request, env: Env) {
  if (!await requireSyncToken(request, env)) return json({ error: "Unauthorized." }, 401);
  return json({ teachers: await env.store.listTeacherAccounts() });
}

async function syncBranding(request: Request, env: Env) {
  if (!await requireSyncToken(request, env)) return json({ error: "Unauthorized." }, 401);
  let body: Record<string, unknown>;
  try {
    body = await readJson(request, 7 * 1024 * 1024);
  } catch {
    return json({ error: "Invalid or oversized school branding request." }, 400);
  }
  const schoolName = typeof body.school_name === "string" ? body.school_name.trim() : "";
  if (typeof body.logo_content_type !== "string" || typeof body.logo_base64 !== "string") {
    return json({ error: "School name and logo fields are required." }, 400);
  }
  const contentType = body.logo_content_type;
  const encodedLogo = body.logo_base64;
  if (!schoolName || schoolName.length > 200) {
    return json({ error: "School name must contain 1–200 characters." }, 400);
  }

  let logo: Uint8Array | null = null;
  if (encodedLogo) {
    if (!BRAND_LOGO_TYPES.has(contentType) || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(encodedLogo)) {
      return json({ error: "School logo must be a PNG, JPG, or WEBP image." }, 400);
    }
    try {
      const decoded = atob(encodedLogo);
      if (!decoded.length || decoded.length > BRAND_LOGO_MAX_BYTES) {
        return json({ error: "School logo must be no larger than 4 MB." }, 400);
      }
      logo = Uint8Array.from(decoded, (character) => character.charCodeAt(0));
    } catch {
      return json({ error: "School logo data is invalid." }, 400);
    }
    if (!validImageSignature(logo, contentType)) {
      return json({ error: "School logo data does not match its image type." }, 400);
    }
  } else if (contentType) {
    return json({ error: "A logo image is required when a logo type is provided." }, 400);
  }

  if (logo) {
    await env.images.put(BRAND_LOGO_KEY, logo, contentType);
  } else {
    await env.images.delete(BRAND_LOGO_KEY);
  }
  await env.store.saveBranding({ school_name: schoolName, logo_present: Boolean(logo) });
  return json({ ok: true });
}

async function serveBrandLogo(env: Env) {
  const branding = await env.store.getBranding();
  if (!branding.logo_present) return new Response("Not found", { status: 404 });
  const logo = await env.images.get(BRAND_LOGO_KEY);
  if (!logo || !BRAND_LOGO_TYPES.has(logo.contentType)) return new Response("Not found", { status: 404 });
  return new Response(new Uint8Array(logo.data), {
    headers: {
      "Content-Type": logo.contentType,
      "Cache-Control": "public, max-age=60",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

async function syncTeacherAccount(request: Request, env: Env) {
  if (!await requireSyncToken(request, env)) return json({ error: "Unauthorized." }, 401);
  let body: Record<string, unknown>;
  try {
    body = await readJson(request);
  } catch {
    return json({ error: "Invalid or oversized teacher account." }, 400);
  }
  const username = typeof body.username === "string" ? normalizeUsername(body.username) : "";
  const fullName = typeof body.full_name === "string" ? body.full_name.trim() : "";
  if (
    !/^[a-z0-9._-]{3,64}$/.test(username) ||
    fullName.length < 2 ||
    fullName.length > 100 ||
    !isPortablePasswordHash(body.password_hash) ||
    typeof body.active !== "boolean"
  ) {
    return json({ error: "Teacher account fields are invalid." }, 400);
  }
  await env.store.upsertTeacherAccount({
    username,
    full_name: fullName,
    password_hash: body.password_hash,
    active: body.active,
  });
  return json({ ok: true });
}

async function setPortalAdmin(request: Request, env: Env) {
  if (!await requireSyncToken(request, env)) return json({ error: "Unauthorized." }, 401);
  let body: Record<string, unknown>;
  try {
    body = await readJson(request);
  } catch {
    return json({ error: "Invalid administrator setup request." }, 400);
  }
  const username = typeof body.username === "string" ? normalizeUsername(body.username) : "";
  const fullName = typeof body.full_name === "string" ? body.full_name.trim() : "";
  const password = typeof body.password === "string" ? body.password : "";
  if (!/^[a-z0-9._-]{3,64}$/.test(username) || fullName.length < 2 || fullName.length > 100 ||
      password.length < 12 || password.length > 128) {
    return json({ error: "Use a valid username, name, and password of at least 12 characters." }, 400);
  }
  await env.store.saveAdmin({ username, full_name: fullName, password_hash: await hashPassword(password) });
  return json({ ok: true });
}

async function reviewPortalSubmission(request: Request, env: Env, admin: PortalAdmin, id: string) {
  const branding = await env.store.getBranding();
  const portalOrigin = requestPortalOrigin(request);
  if (!validOrigin(request)) return portalAdminPage(admin, [], "pending", "The review request could not be verified.", null, branding, portalOrigin);
  const form = await request.formData();
  const status = text(form, "status");
  const feedback = text(form, "feedback").trim();
  if (!UUID_PATTERN.test(id) || !["approved", "rejected"].includes(status) || feedback.length > 1000) {
    return portalAdminPage(admin, [], "pending", "The review choice or feedback is invalid.", null, branding, portalOrigin);
  }
  const outcome = await env.store.applyDecision(
    id,
    status as "approved" | "rejected",
    feedback,
    new Date().toISOString(),
  );
  if (outcome === "conflict") {
    return redirect("/admin?notice=This%20submission%20was%20already%20reviewed.");
  }
  return redirect("/admin?notice=Review%20decision%20saved.%20It%20will%20sync%20to%20the%20school%20server.");
}

async function prepareImageUpload(request: Request, env: Env) {
  if (!validOrigin(request)) return json({ error: "The upload request could not be verified." }, 403);
  const teacher = await getTeacher(request, env);
  if (!teacher) return json({ error: "Sign in again before uploading an image." }, 401);
  let body: Record<string, unknown>;
  try {
    body = await readJson(request);
  } catch {
    return json({ error: "Invalid upload request." }, 400);
  }
  if (
    typeof body.content_type !== "string" ||
    !IMAGE_MIME_TYPES.has(body.content_type) ||
    typeof body.size !== "number" ||
    !Number.isInteger(body.size) ||
    body.size < 1 ||
    body.size > IMAGE_MAX_BYTES
  ) {
    return json({ error: "Choose a PNG, JPG, WEBP, or GIF image up to 5 MB." }, 400);
  }
  const uploadKey = `teacher-submissions/images/${teacher.id}/${crypto.randomUUID()}`;
  const upload = await env.images.getUploadUrl(uploadKey, body.content_type, body.size);
  if (!upload) return json({ error: "Direct image uploads are not available on this portal." }, 501);
  await env.store.createImageUpload(uploadKey, teacher.id, Math.floor(Date.now() / 1000) + 300);
  return json({
    image_key: uploadKey,
    upload_url: upload.url,
    upload_headers: upload.headers,
  });
}

async function submitBatch(request: Request, env: Env) {
  if (!validOrigin(request)) return json({ error: "The batch request could not be verified." }, 403);
  const teacher = await getTeacher(request, env);
  if (!teacher) return json({ error: "Sign in again before submitting questions." }, 401);
  let body: Record<string, unknown>;
  try {
    body = await readJson(request);
  } catch {
    return json({ error: "Invalid or oversized batch request." }, 400);
  }
  if (!Array.isArray(body.questions) || body.questions.length < 1 || body.questions.length > 50) {
    return json({ error: "Submit between 1 and 50 questions in a batch." }, 400);
  }
  const textFields = [
    "subject", "topic", "class_name", "difficulty", "stem",
    "option_a", "option_b", "option_c", "option_d", "correct_option",
    "explanation", "standard",
  ];
  if (textFields.some((field) => body[field] !== undefined && typeof body[field] !== "string")) {
    return json({ error: "Batch metadata fields must be text." }, 400);
  }
  const limits: Record<string, number> = {
    subject: 120, topic: 200, class_name: 120, stem: 5000,
    option_a: 2000, option_b: 2000, option_c: 2000, option_d: 2000,
    explanation: 5000, standard: 500,
  };
  const submissions: NewSubmission[] = [];
  for (const [index, entry] of body.questions.entries()) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
      return json({ error: `Question ${index + 1} is invalid.` }, 400);
    }
    const item = entry as Record<string, unknown>;
    if (textFields.some((field) => item[field] !== undefined && typeof item[field] !== "string")) {
      return json({ error: `Question ${index + 1} fields must be text.` }, 400);
    }
    const submission = {
      subject: String(item.subject ?? body.subject ?? "").trim(),
      topic: String(item.topic ?? body.topic ?? "").trim(),
      class_name: String(item.class_name ?? body.class_name ?? "").trim(),
      stem: String(item.stem ?? "").trim(),
      option_a: String(item.option_a ?? "").trim(),
      option_b: String(item.option_b ?? "").trim(),
      option_c: String(item.option_c ?? "").trim(),
      option_d: String(item.option_d ?? "").trim(),
      correct_option: String(item.correct_option ?? "").trim().toUpperCase(),
      difficulty: String(item.difficulty ?? body.difficulty ?? "medium").trim().toLowerCase(),
      explanation: String(item.explanation ?? "").trim(),
      standard: String(item.standard ?? "").trim(),
    };
    for (const [field, maxLength] of Object.entries(limits)) {
      if (submission[field as keyof typeof submission].length > maxLength) {
        return json({ error: `Question ${index + 1}: ${field.replace("_", " ")} is too long.` }, 400);
      }
    }
    const missing = ["subject", "topic", "stem", "option_a", "option_b", "option_c", "option_d"]
      .filter((field) => !submission[field as keyof typeof submission]);
    if (missing.length) return json({ error: `Question ${index + 1} is missing ${missing.join(", ")}.` }, 400);
    if (!["A", "B", "C", "D"].includes(submission.correct_option)) {
      return json({ error: `Question ${index + 1} needs a correct answer of A, B, C, or D.` }, 400);
    }
    if (!["easy", "medium", "hard"].includes(submission.difficulty)) {
      return json({ error: `Question ${index + 1} has an invalid difficulty.` }, 400);
    }
    submissions.push({
      id: crypto.randomUUID(),
      teacher_id: teacher.id,
      teacher_name: teacher.full_name,
      teacher_username: teacher.username,
      ...submission,
      image_key: null,
      status: "pending",
      feedback: "",
      submitted_at: new Date().toISOString(),
    });
  }
  for (const submission of submissions) await env.store.createSubmission(submission);
  return json({ submitted: submissions.length }, 201);
}

async function syncDecisions(request: Request, env: Env) {
  if (!await requireSyncToken(request, env)) return json({ error: "Unauthorized." }, 401);
  let body: Record<string, unknown>;
  try {
    body = await readJson(request);
  } catch {
    return json({ error: "Invalid or oversized request body." }, 400);
  }
  const decisions = body.decisions;
  if (!Array.isArray(decisions) || decisions.length > 100) {
    return json({ error: "Submit between 1 and 100 decisions." }, 400);
  }
  const syncedIds: string[] = [];
  const conflicts: string[] = [];
  for (const entry of decisions) {
    if (!entry || typeof entry !== "object") return json({ error: "Invalid decision item." }, 400);
    const item = entry as Record<string, unknown>;
    const id = item.id;
    const status = item.status;
    const feedback = item.feedback;
    if (typeof id !== "string" || !/^[0-9a-fA-F-]{36}$/.test(id) ||
        (status !== "approved" && status !== "rejected") ||
        typeof feedback !== "string" || feedback.length > 1000) {
      return json({ error: "Invalid decision item." }, 400);
    }
    const result = await env.store.applyDecision(id, status, feedback.trim(), new Date().toISOString());
    if (result !== "conflict") syncedIds.push(id);
    else conflicts.push(id);
  }
  return json({ synced_ids: syncedIds, conflicts });
}

async function resetTeacherPassword(request: Request, env: Env) {
  if (!await requireSyncToken(request, env)) return json({ error: "Unauthorized." }, 401);
  let body: Record<string, unknown>;
  try {
    body = await readJson(request);
  } catch {
    return json({ error: "Invalid or oversized request body." }, 400);
  }
  if (typeof body.username !== "string" || typeof body.password !== "string") {
    return json({ error: "Username and password are required." }, 400);
  }
  const username = normalizeUsername(body.username);
  if (!/^[a-z0-9._-]{3,64}$/.test(username) || body.password.length < 8 || body.password.length > 128) {
    return json({ error: "Username or password does not meet the requirements." }, 400);
  }
  const teacher = await env.store.findTeacherByUsername(username);
  if (!teacher?.active) return json({ error: "No active teacher account matches that username." }, 404);
  await env.store.updateTeacherPassword(teacher.id, await hashPassword(body.password));
  await env.store.deleteTeacherSessions(teacher.id);
  return json({ ok: true });
}

async function setTeacherActive(request: Request, env: Env) {
  if (!await requireSyncToken(request, env)) return json({ error: "Unauthorized." }, 401);
  let body: Record<string, unknown>;
  try {
    body = await readJson(request);
  } catch {
    return json({ error: "Invalid or oversized request body." }, 400);
  }
  if (typeof body.username !== "string" || typeof body.active !== "boolean") {
    return json({ error: "Username and an active status are required." }, 400);
  }
  const username = normalizeUsername(body.username);
  if (!/^[a-z0-9._-]{3,64}$/.test(username)) {
    return json({ error: "Invalid portal username." }, 400);
  }
  const teacher = await env.store.findTeacherByUsername(username);
  if (!teacher) return json({ error: "No portal account matches that username." }, 404);
  await env.store.setTeacherActive(teacher.id, body.active);
  if (!body.active) await env.store.deleteTeacherSessions(teacher.id);
  return json({ ok: true });
}

async function router(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const path = url.pathname;
  const method = request.method.toUpperCase();

  if (method === "GET" && path === "/brand/logo") return serveBrandLogo(env);
  if (method === "GET" && path === "/login") {
    return loginPage(url.searchParams.get("notice") ?? "", false, await env.store.getBranding(), requestPortalOrigin(request));
  }
  if (method === "GET" && path === "/register") {
    return registerPage("", await env.store.getBranding(), requestPortalOrigin(request));
  }
  if (method === "GET" && path === "/batch-template.json") {
    return new Response(JSON.stringify({
      subject: "Mathematics",
      topic: "Fractions",
      class_name: "",
      difficulty: "medium",
      questions: [{
        stem: "What is 1/2 + 1/4?",
        option_a: "1/4",
        option_b: "2/4",
        option_c: "3/4",
        option_d: "1",
        correct_option: "C",
        explanation: "Convert to quarters and add.",
        standard: "",
      }],
    }, null, 2), {
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Disposition": 'attachment; filename="teacher-question-batch-template.json"',
        "Cache-Control": "no-store",
      },
    });
  }
  if (method === "POST" && path === "/login") return login(request, env);
  if (method === "POST" && path === "/register") return register(request, env);
  if (method === "GET" && path === "/admin/login") {
    return adminLoginPage(url.searchParams.get("notice") ?? "", await env.store.getBranding(), requestPortalOrigin(request));
  }
  if (method === "POST" && path === "/admin/login") return loginAdmin(request, env);
  if (method === "POST" && path === "/api/image-upload") return prepareImageUpload(request, env);
  if (method === "POST" && path === "/api/batch-submissions") return submitBatch(request, env);
  if (method === "POST" && path === "/logout") {
    if (!validOrigin(request)) return new Response("Forbidden", { status: 403 });
    const token = request.headers.get("Cookie")?.match(/(?:^|;\s*)portal_session=([A-Za-z0-9_-]+)/)?.[1];
    if (token) await env.store.deleteSession(await sha256(token));
    return redirect("/login", {
      "Set-Cookie": clearCookie(new URL(request.url).protocol === "https:"),
    });
  }

  if (path.startsWith("/api/sync/")) {
    if (method === "GET" && path === "/api/sync/pending") return syncPending(request, env);
    if (method === "GET" && path === "/api/sync/reviewed") return syncReviewed(request, env);
    if (method === "GET" && path === "/api/sync/teachers") return syncTeacherAccounts(request, env);
    if (method === "POST" && path === "/api/sync/branding") return syncBranding(request, env);
    if (method === "POST" && path === "/api/sync/teachers/upsert") return syncTeacherAccount(request, env);
    if (method === "POST" && path === "/api/sync/admin/set-password") return setPortalAdmin(request, env);
    if (method === "POST" && path === "/api/sync/decisions") return syncDecisions(request, env);
    if (method === "POST" && path === "/api/sync/teachers/reset-password") {
      return resetTeacherPassword(request, env);
    }
    if (method === "POST" && path === "/api/sync/teachers/set-active") {
      return setTeacherActive(request, env);
    }
    const imageMatch = path.match(/^\/api\/sync\/submissions\/([0-9a-fA-F-]{36})\/image$/);
    if (method === "GET" && imageMatch) return syncSubmissionImage(request, env, imageMatch[1]);
    return json({ error: "Not found." }, 404);
  }

  if (path === "/admin" || path.startsWith("/admin/")) {
    if (method === "POST" && path === "/admin/logout") {
      if (!validOrigin(request)) return new Response("Forbidden", { status: 403 });
      const token = request.headers.get("Cookie")?.match(/(?:^|;\s*)portal_admin_session=([A-Za-z0-9_-]+)/)?.[1];
      if (token) await env.store.deleteAdminSession(await sha256(token));
      return redirect("/admin/login", { "Set-Cookie": clearAdminCookie(new URL(request.url).protocol === "https:") });
    }
    const admin = await getPortalAdmin(request, env);
    if (!admin) return redirect("/admin/login");
    if (method === "GET" && path === "/admin") {
      const requestedStatus = url.searchParams.get("status") ?? "pending";
      const status = ["pending", "approved", "rejected", "all"].includes(requestedStatus)
        ? requestedStatus as Submission["status"] | "all"
        : "pending";
      return portalAdminPage(
        admin,
        await env.store.listAdminSubmissions(status),
        status,
        url.searchParams.get("notice") ?? "",
        env.images.getAllowedImageSource(),
        await env.store.getBranding(),
        requestPortalOrigin(request),
      );
    }
    const imageMatch = path.match(/^\/admin\/submissions\/([0-9a-fA-F-]{36})\/image$/);
    if (method === "GET" && imageMatch) {
      const imageKey = await env.store.getSubmissionImageKey(imageMatch[1]);
      return imageKey ? serveImage(env, imageKey) : new Response("Not found", { status: 404 });
    }
    const reviewMatch = path.match(/^\/admin\/submissions\/([0-9a-fA-F-]{36})\/review$/);
    if (method === "POST" && reviewMatch) return reviewPortalSubmission(request, env, admin, reviewMatch[1]);
    return new Response("Not found", { status: 404 });
  }

  const teacher = await getTeacher(request, env);
  if (path === "/") {
    const branding = await env.store.getBranding();
    if (!teacher) return loginPage(url.searchParams.get("notice") ?? "", true, branding, requestPortalOrigin(request));
    const submissions = await ownSubmissions(env, teacher.id);
    const notice = url.searchParams.get("notice") ?? "";
    return dashboardPage(teacher, submissions, notice, env.images.getAllowedImageSource(), branding, requestPortalOrigin(request));
  }
  if (method === "POST" && path === "/submit") {
    if (!teacher) return redirect("/login");
    return submitQuestion(request, env, teacher);
  }
  if (method === "POST" && path === "/change-password") {
    if (!teacher) return redirect("/login");
    return changePassword(request, env, teacher);
  }
  const teacherImageMatch = path.match(/^\/submissions\/([0-9a-fA-F-]{36})\/image$/);
  if (method === "GET" && teacherImageMatch) {
    if (!teacher) return redirect("/login");
    return serveTeacherImage(request, env, teacher, teacherImageMatch[1]);
  }
  return new Response("Not found", { status: 404 });
}

export async function handleRequest(request: Request, env: Env): Promise<Response> {
  try {
    return await router(request, env);
  } catch (error) {
    console.error("Teacher portal request failed.", error);
    if (new URL(request.url).pathname.startsWith("/api/")) {
      return json({ error: "The portal could not complete the request. Try again later." }, 500);
    }
    return new Response(
      "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><title>Portal error</title><h1>Something went wrong</h1><p>Please try again later or contact your school administrator.</p></html>",
      { status: 500, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } },
    );
  }
}

export default {
  fetch: handleRequest,
};
