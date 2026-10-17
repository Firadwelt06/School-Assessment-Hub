const assert = require("node:assert/strict");
const fs = require("node:fs");
const test = require("node:test");
const path = require("node:path");

process.env.TEACHERS_TABLE = "teachers";
process.env.SESSIONS_TABLE = "sessions";
process.env.SUBMISSIONS_TABLE = "submissions";
process.env.RATE_LIMITS_TABLE = "rate-limits";
process.env.IMAGE_UPLOADS_TABLE = "image-uploads";
process.env.SUBMISSION_IMAGES_BUCKET = "private-images";
delete process.env.SCHOOL_SIGNUP_CODE;
delete process.env.SYNC_TOKEN;

const { handler } = require("../dist/aws.js");

function event(path, method = "GET", extra = {}) {
  return {
    version: "2.0",
    rawPath: path,
    rawQueryString: "",
    headers: { host: "portal.execute-api.us-east-1.amazonaws.com" },
    requestContext: { http: { method, sourceIp: "192.0.2.1" } },
    ...extra,
  };
}

test("AWS HTTP API adapter routes unauthenticated sync calls to token validation", async () => {
  const response = await handler(event("/api/sync/pending"));
  assert.equal(response.statusCode, 401);
  assert.deepEqual(JSON.parse(response.body), { error: "Unauthorized." });
});

test("AWS HTTP API adapter serves the public teacher registration form", async () => {
  const response = await handler(event("/register"));
  assert.equal(response.statusCode, 200);
  assert.match(response.headers["content-type"], /text\/html/);
  assert.match(response.body, /Create teacher account/);
  assert.equal(response.isBase64Encoded, false);
});

test("AWS HTTP API adapter requires a teacher session before preparing image uploads", async () => {
  const response = await handler(event("/api/image-upload", "POST", {
    headers: {
      host: "portal.execute-api.us-east-1.amazonaws.com",
      origin: "https://portal.execute-api.us-east-1.amazonaws.com",
      "content-type": "application/json",
    },
    body: JSON.stringify({ content_type: "image/png", size: 32 }),
  }));
  assert.equal(response.statusCode, 401);
  assert.deepEqual(JSON.parse(response.body), { error: "Sign in again before uploading an image." });
});

test("AWS portal exposes a downloadable no-image batch template", async () => {
  const response = await handler(event("/batch-template.json"));
  assert.equal(response.statusCode, 200);
  assert.match(response.headers["content-type"], /application\/json/);
  assert.match(response.headers["content-disposition"], /teacher-question-batch-template\.json/);
  assert.equal(JSON.parse(response.body).questions.length, 1);
});

test("online review dashboard requires its separate administrator session", async () => {
  const response = await handler(event("/admin"));
  assert.equal(response.statusCode, 303);
  assert.equal(response.headers.location, "/admin/login");
});

test("teacher account sync APIs reject requests without the sync token", async () => {
  const response = await handler(event("/api/sync/teachers"));
  assert.equal(response.statusCode, 401);
  assert.deepEqual(JSON.parse(response.body), { error: "Unauthorized." });
});

test("AWS function role can scan the teacher directory for account sync", () => {
  const template = fs.readFileSync(path.join(__dirname, "..", "template.yaml"), "utf8");
  assert.match(template, /- dynamodb:Scan/);
});
