const assert = require("node:assert/strict");
const fs = require("node:fs");
const test = require("node:test");
const path = require("node:path");

process.env.TEACHERS_TABLE = "teachers";
process.env.SESSIONS_TABLE = "sessions";
process.env.SUBMISSIONS_TABLE = "submissions";
process.env.RATE_LIMITS_TABLE = "rate-limits";
process.env.IMAGE_UPLOADS_TABLE = "image-uploads";
process.env.SETTINGS_TABLE = "settings";
process.env.SUBMISSION_IMAGES_BUCKET = "private-images";
delete process.env.SCHOOL_SIGNUP_CODE;
delete process.env.SYNC_TOKEN;

const { handler, handleAwsEvent } = require("../dist/aws.js");

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

test("AWS Lambda context is not mistaken for portal services", async () => {
  const lambdaContext = { awsRequestId: "test-request-id" };
  const response = await handler(event("/api/sync/pending"), lambdaContext);
  assert.equal(response.statusCode, 401);
  assert.deepEqual(JSON.parse(response.body), { error: "Unauthorized." });
});

test("AWS HTTP API adapter serves branded teacher registration metadata", async () => {
  const response = await handleAwsEvent(event("/register"), {
    store: {
      getBranding: async () => ({ school_name: "North School", logo_present: true }),
    },
  });
  assert.equal(response.statusCode, 200);
  assert.match(response.headers["content-type"], /text\/html/);
  assert.match(response.body, /Create teacher account/);
  assert.match(response.body, /<title>Create teacher account · North School<\/title>/);
  assert.match(response.body, /property="og:image" content="https:\/\/portal\.execute-api\.us-east-1\.amazonaws\.com\/brand\/logo"/);
  assert.equal(response.isBase64Encoded, false);
});

test("portal URL serves the branded sign-in page with HTTPS preview image metadata", async () => {
  const response = await handleAwsEvent(event("/"), {
    store: {
      getBranding: async () => ({ school_name: "North School", logo_present: true }),
      findTeacherForSession: async () => null,
    },
  });
  assert.equal(response.statusCode, 200);
  assert.match(response.body, /Teacher sign in/);
  assert.match(response.body, /property="og:description"/);
  assert.match(response.body, /property="og:image:secure_url" content="https:\/\/portal\.execute-api\.us-east-1\.amazonaws\.com\/brand\/logo"/);
  assert.equal(response.headers.location, undefined);
});

test("AWS HTTP API adapter serves only the fixed public school logo route", async () => {
  const logo = Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const response = await handleAwsEvent(event("/brand/logo"), {
    store: {
      getBranding: async () => ({ school_name: "North School", logo_present: true }),
    },
    images: {
      get: async (key) => {
        assert.equal(key, "school-branding/logo");
        return { data: logo, contentType: "image/png" };
      },
    },
  });
  assert.equal(response.statusCode, 200);
  assert.equal(response.headers["content-type"], "image/png");
  assert.equal(response.isBase64Encoded, true);
  assert.deepEqual(Buffer.from(response.body, "base64"), Buffer.from(logo));
});

test("branding sync validates the token and stores a private logo object", async () => {
  const stored = {};
  const logo = Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const token = "private-test-sync-token-value-longer-than-32-characters";
  const response = await handleAwsEvent(event("/api/sync/branding", "POST", {
    headers: {
      host: "portal.execute-api.us-east-1.amazonaws.com",
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      school_name: "North School",
      logo_content_type: "image/png",
      logo_base64: Buffer.from(logo).toString("base64"),
    }),
  }), {
    SYNC_TOKEN: token,
    store: {
      saveBranding: async (branding) => { stored.branding = branding; },
    },
    images: {
      put: async (key, data, contentType) => { stored.image = { key, data, contentType }; },
      delete: async () => assert.fail("Logo should not be deleted."),
    },
  });
  assert.equal(response.statusCode, 200);
  assert.deepEqual(JSON.parse(response.body), { ok: true });
  assert.deepEqual(stored.branding, { school_name: "North School", logo_present: true });
  assert.equal(stored.image.key, "school-branding/logo");
  assert.equal(stored.image.contentType, "image/png");
  assert.deepEqual(Buffer.from(stored.image.data), Buffer.from(logo));
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
