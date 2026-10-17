import {
  DynamoDBClient,
} from "@aws-sdk/client-dynamodb";
import {
  DeleteCommand,
  DynamoDBDocumentClient,
  GetCommand,
  PutCommand,
  QueryCommand,
  TransactWriteCommand,
  UpdateCommand,
} from "@aws-sdk/lib-dynamodb";
import {
  DeleteObjectCommand,
  GetObjectCommand,
  PutObjectCommand,
  PutObjectTaggingCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import type {
  ImageStore,
  NewSubmission,
  PortalStore,
  RateLimitRecord,
  Submission,
  Teacher,
} from "./portal-store.js";

type AwsPortalConfig = {
  teachersTable: string;
  sessionsTable: string;
  submissionsTable: string;
  rateLimitsTable: string;
  imageUploadsTable: string;
  imagesBucket: string;
};

const config: AwsPortalConfig = {
  teachersTable: requiredEnvironment("TEACHERS_TABLE"),
  sessionsTable: requiredEnvironment("SESSIONS_TABLE"),
  submissionsTable: requiredEnvironment("SUBMISSIONS_TABLE"),
  rateLimitsTable: requiredEnvironment("RATE_LIMITS_TABLE"),
  imageUploadsTable: requiredEnvironment("IMAGE_UPLOADS_TABLE"),
  imagesBucket: requiredEnvironment("SUBMISSION_IMAGES_BUCKET"),
};

const dynamo = DynamoDBDocumentClient.from(new DynamoDBClient({}), {
  marshallOptions: { removeUndefinedValues: true },
});
const s3 = new S3Client({});

function requiredEnvironment(name: string) {
  const value = process.env[name];
  if (!value) throw new Error(`Missing required environment variable ${name}.`);
  return value;
}

function isConditionalFailure(error: unknown) {
  return error instanceof Error && error.name === "ConditionalCheckFailedException";
}

function teacherIdKey(teacherId: string) {
  return teacherId;
}

export class DynamoPortalStore implements PortalStore {
  async deleteExpiredSessions(_now: number) {
    // The sessions table's DynamoDB TTL setting expires these records asynchronously.
  }

  async getRateLimit(rateKey: string): Promise<RateLimitRecord | null> {
    const result = await dynamo.send(new GetCommand({
      TableName: config.rateLimitsTable,
      Key: { rate_key: rateKey },
      ConsistentRead: true,
    }));
    const item = result.Item;
    if (!item) return null;
    return {
      attempts: Number(item.attempts),
      window_started: Number(item.window_started),
    };
  }

  async recordRateLimitedAttempt(rateKey: string, now: number) {
    for (let attempt = 0; attempt < 5; attempt++) {
      const current = await this.getRateLimit(rateKey);
      try {
        if (!current) {
          await dynamo.send(new PutCommand({
            TableName: config.rateLimitsTable,
            Item: { rate_key: rateKey, attempts: 1, window_started: now, expires_at: now + 900 },
            ConditionExpression: "attribute_not_exists(rate_key)",
          }));
        } else if (now - current.window_started >= 15 * 60) {
          await dynamo.send(new UpdateCommand({
            TableName: config.rateLimitsTable,
            Key: { rate_key: rateKey },
            UpdateExpression: "SET attempts = :one, window_started = :now, expires_at = :expires_at",
            ConditionExpression: "window_started = :previous",
            ExpressionAttributeValues: {
              ":one": 1,
              ":now": now,
              ":expires_at": now + 900,
              ":previous": current.window_started,
            },
          }));
        } else {
          await dynamo.send(new UpdateCommand({
            TableName: config.rateLimitsTable,
            Key: { rate_key: rateKey },
            UpdateExpression: "ADD attempts :one",
            ConditionExpression: "window_started = :previous",
            ExpressionAttributeValues: {
              ":one": 1,
              ":previous": current.window_started,
            },
          }));
        }
        return;
      } catch (error) {
        if (!isConditionalFailure(error)) throw error;
      }
    }
    throw new Error("Could not safely update the portal rate limit after concurrent changes.");
  }

  async findTeacherForSession(tokenHash: string, now: number): Promise<Teacher | null> {
    const session = await dynamo.send(new GetCommand({
      TableName: config.sessionsTable,
      Key: { token_hash: tokenHash },
      ConsistentRead: true,
    }));
    if (!session.Item || Number(session.Item.expires_at) <= now) return null;
    const teacher = await dynamo.send(new GetCommand({
      TableName: config.teachersTable,
      Key: { username: String(session.Item.teacher_id) },
      ConsistentRead: true,
    }));
    if (!teacher.Item || !teacher.Item.active) return null;
    return {
      id: String(teacher.Item.id),
      username: String(teacher.Item.username),
      full_name: String(teacher.Item.full_name),
    };
  }

  async findTeacherForLogin(username: string): Promise<(Teacher & { password_hash: string; active: boolean }) | null> {
    const result = await dynamo.send(new GetCommand({
      TableName: config.teachersTable,
      Key: { username },
      ConsistentRead: true,
    }));
    const item = result.Item;
    if (!item?.active) return null;
    return {
      id: String(item.id),
      username: String(item.username),
      full_name: String(item.full_name),
      password_hash: String(item.password_hash),
      active: Boolean(item.active),
    };
  }

  async createTeacher(input: {
    id: string;
    username: string;
    full_name: string;
    password_hash: string;
    created_at: string;
  }) {
    try {
      await dynamo.send(new PutCommand({
        TableName: config.teachersTable,
        Item: { ...input, active: true },
        ConditionExpression: "attribute_not_exists(username)",
      }));
      return true;
    } catch (error) {
      if (isConditionalFailure(error)) return false;
      throw error;
    }
  }

  async createSession(input: { token_hash: string; teacher_id: string; expires_at: number }) {
    await dynamo.send(new PutCommand({
      TableName: config.sessionsTable,
      Item: input,
      ConditionExpression: "attribute_not_exists(token_hash)",
    }));
  }

  async deleteSession(tokenHash: string) {
    await dynamo.send(new DeleteCommand({
      TableName: config.sessionsTable,
      Key: { token_hash: tokenHash },
    }));
  }

  async getTeacherPassword(teacherId: string) {
    const result = await dynamo.send(new GetCommand({
      TableName: config.teachersTable,
      Key: { username: teacherIdKey(teacherId) },
      ConsistentRead: true,
    }));
    if (!result.Item?.active) return null;
    return { password_hash: String(result.Item.password_hash) };
  }

  async updateTeacherPassword(teacherId: string, passwordHash: string) {
    await dynamo.send(new UpdateCommand({
      TableName: config.teachersTable,
      Key: { username: teacherIdKey(teacherId) },
      UpdateExpression: "SET password_hash = :password",
      ExpressionAttributeValues: { ":password": passwordHash },
      ConditionExpression: "attribute_exists(username)",
    }));
  }

  async deleteTeacherSessions(teacherId: string) {
    let lastKey: Record<string, unknown> | undefined;
    do {
      const page = await dynamo.send(new QueryCommand({
        TableName: config.sessionsTable,
        IndexName: "TeacherSessionsIndex",
        KeyConditionExpression: "teacher_id = :teacher_id",
        ExpressionAttributeValues: { ":teacher_id": teacherId },
        ExclusiveStartKey: lastKey,
      }));
      for (const item of page.Items ?? []) {
        await this.deleteSession(String(item.token_hash));
      }
      lastKey = page.LastEvaluatedKey;
    } while (lastKey);
  }

  async createSubmission(submission: NewSubmission, imageUploadKey?: string) {
    const put = {
      TableName: config.submissionsTable,
      Item: {
        ...submission,
        teacher_submitted: `${submission.submitted_at}#${submission.id}`,
      },
      ConditionExpression: "attribute_not_exists(id)",
    };
    if (imageUploadKey) {
      await dynamo.send(new TransactWriteCommand({
        TransactItems: [
          { Put: put },
          {
            Delete: {
              TableName: config.imageUploadsTable,
              Key: { image_key: imageUploadKey },
              ConditionExpression: "teacher_id = :teacher_id AND expires_at > :now",
              ExpressionAttributeValues: {
                ":teacher_id": submission.teacher_id,
                ":now": Math.floor(Date.now() / 1000),
              },
            },
          },
        ],
      }));
      return;
    }
    await dynamo.send(new PutCommand(put));
  }

  async createImageUpload(key: string, teacherId: string, expiresAt: number) {
    await dynamo.send(new PutCommand({
      TableName: config.imageUploadsTable,
      Item: { image_key: key, teacher_id: teacherId, expires_at: expiresAt },
      ConditionExpression: "attribute_not_exists(image_key)",
    }));
  }

  async ownsImageUpload(key: string, teacherId: string, now: number) {
    const result = await dynamo.send(new GetCommand({
      TableName: config.imageUploadsTable,
      Key: { image_key: key },
      ConsistentRead: true,
    }));
    return result.Item?.teacher_id === teacherId && Number(result.Item.expires_at) > now;
  }

  async removeImageUpload(key: string) {
    await dynamo.send(new DeleteCommand({
      TableName: config.imageUploadsTable,
      Key: { image_key: key },
    }));
  }

  async listTeacherSubmissions(teacherId: string): Promise<Submission[]> {
    const result = await dynamo.send(new QueryCommand({
      TableName: config.submissionsTable,
      IndexName: "TeacherSubmissionsIndex",
      KeyConditionExpression: "teacher_id = :teacher_id",
      ExpressionAttributeValues: { ":teacher_id": teacherId },
      ScanIndexForward: false,
      Limit: 100,
    }));
    return (result.Items ?? []) as Submission[];
  }

  async getTeacherSubmissionImageKey(id: string, teacherId: string) {
    const result = await dynamo.send(new GetCommand({
      TableName: config.submissionsTable,
      Key: { id },
      ConsistentRead: true,
    }));
    if (result.Item?.teacher_id !== teacherId || !result.Item.image_key) return null;
    return String(result.Item.image_key);
  }

  async getSubmissionImageKey(id: string) {
    const result = await dynamo.send(new GetCommand({
      TableName: config.submissionsTable,
      Key: { id },
      ConsistentRead: true,
    }));
    return result.Item?.image_key ? String(result.Item.image_key) : null;
  }

  async listPendingSubmissions(cursor: string): Promise<Array<Omit<Submission, "image_key" | "status" | "feedback"> & { image: boolean }>> {
    const result = await dynamo.send(new QueryCommand({
      TableName: config.submissionsTable,
      IndexName: "PendingSubmissionsIndex",
      KeyConditionExpression: cursor ? "#status = :pending AND id > :cursor" : "#status = :pending",
      ExpressionAttributeNames: { "#status": "status" },
      ExpressionAttributeValues: cursor
        ? { ":pending": "pending", ":cursor": cursor }
        : { ":pending": "pending" },
      ScanIndexForward: true,
      Limit: 101,
    }));
    return (result.Items ?? []).map((item) => ({
      id: String(item.id),
      teacher_id: String(item.teacher_id),
      teacher_name: String(item.teacher_name),
      teacher_username: String(item.teacher_username),
      subject: String(item.subject),
      topic: String(item.topic),
      class_name: String(item.class_name ?? ""),
      stem: String(item.stem),
      option_a: String(item.option_a),
      option_b: String(item.option_b),
      option_c: String(item.option_c),
      option_d: String(item.option_d),
      correct_option: String(item.correct_option),
      difficulty: String(item.difficulty),
      explanation: String(item.explanation ?? ""),
      standard: String(item.standard ?? ""),
      submitted_at: String(item.submitted_at),
      image: Boolean(item.image_key),
    }));
  }

  async applyDecision(
    id: string,
    status: "approved" | "rejected",
    feedback: string,
    decidedAt: string,
  ): Promise<"updated" | "already_synced" | "conflict"> {
    try {
      await dynamo.send(new UpdateCommand({
        TableName: config.submissionsTable,
        Key: { id },
        UpdateExpression: "SET #status = :status, feedback = :feedback, decided_at = :decided_at",
        ConditionExpression: "#status = :pending",
        ExpressionAttributeNames: { "#status": "status" },
        ExpressionAttributeValues: {
          ":status": status,
          ":feedback": feedback,
          ":decided_at": decidedAt,
          ":pending": "pending",
        },
      }));
      return "updated";
    } catch (error) {
      if (!isConditionalFailure(error)) throw error;
      const result = await dynamo.send(new GetCommand({
        TableName: config.submissionsTable,
        Key: { id },
        ConsistentRead: true,
      }));
      return result.Item?.status === status ? "already_synced" : "conflict";
    }
  }

  async findTeacherByUsername(username: string) {
    const result = await dynamo.send(new GetCommand({
      TableName: config.teachersTable,
      Key: { username },
      ConsistentRead: true,
    }));
    if (!result.Item) return null;
    return { id: String(result.Item.id), active: Boolean(result.Item.active) };
  }

  async setTeacherActive(teacherId: string, active: boolean) {
    await dynamo.send(new UpdateCommand({
      TableName: config.teachersTable,
      Key: { username: teacherIdKey(teacherId) },
      UpdateExpression: "SET active = :active",
      ExpressionAttributeValues: { ":active": active },
      ConditionExpression: "attribute_exists(username)",
    }));
  }
}

export class S3ImageStore implements ImageStore {
  async put(key: string, data: Uint8Array, contentType: string) {
    await s3.send(new PutObjectCommand({
      Bucket: config.imagesBucket,
      Key: key,
      Body: data,
      ContentType: contentType,
      CacheControl: "private, no-store",
      ServerSideEncryption: "AES256",
    }));
  }

  async get(key: string) {
    try {
      const result = await s3.send(new GetObjectCommand({
        Bucket: config.imagesBucket,
        Key: key,
      }));
      if (!result.Body) return null;
      return {
        data: await result.Body.transformToByteArray(),
        contentType: result.ContentType ?? "application/octet-stream",
      };
    } catch (error) {
      if (error instanceof Error && error.name === "NoSuchKey") return null;
      throw error;
    }
  }

  async getReadUrl(key: string) {
    return getSignedUrl(
      s3,
      new GetObjectCommand({ Bucket: config.imagesBucket, Key: key }),
      { expiresIn: 120 },
    );
  }

  async getUploadUrl(key: string, contentType: string, size: number) {
    const url = await getSignedUrl(
      s3,
      new PutObjectCommand({
        Bucket: config.imagesBucket,
        Key: key,
        ContentType: contentType,
        Tagging: "portal-image-state=staged",
        ContentLength: size,
        IfNoneMatch: "*",
      }),
      {
        expiresIn: 300,
        unhoistableHeaders: new Set(["x-amz-tagging"]),
        signableHeaders: new Set(["content-length", "if-none-match"]),
      },
    );
    return {
      url,
      headers: {
        "Content-Type": contentType,
        "If-None-Match": "*",
        "x-amz-tagging": "portal-image-state=staged",
      },
    };
  }

  getAllowedImageSource() {
    const region = process.env.AWS_REGION ?? "us-east-1";
    const domain = region.startsWith("cn-") ? "amazonaws.com.cn" : "amazonaws.com";
    return `https://*.s3.${region}.${domain}`;
  }

  async finalizeUpload(key: string) {
    await s3.send(new PutObjectTaggingCommand({
      Bucket: config.imagesBucket,
      Key: key,
      Tagging: { TagSet: [{ Key: "portal-image-state", Value: "stored" }] },
    }));
  }

  async delete(key: string) {
    await s3.send(new DeleteObjectCommand({ Bucket: config.imagesBucket, Key: key }));
  }
}
