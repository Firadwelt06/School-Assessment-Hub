import { DynamoPortalStore, S3ImageStore } from "./aws-store.js";
import { handleRequest } from "./index.js";
import type { PortalEnv } from "./portal-store.js";

interface FunctionUrlEvent {
  version: "2.0";
  rawPath: string;
  rawQueryString: string;
  headers: Record<string, string | undefined>;
  cookies?: string[];
  body?: string;
  isBase64Encoded?: boolean;
  requestContext: {
    http: {
      method: string;
      sourceIp: string;
    };
  };
}

const portalEnv: PortalEnv = {
  store: new DynamoPortalStore(),
  images: new S3ImageStore(),
  SCHOOL_SIGNUP_CODE: process.env.SCHOOL_SIGNUP_CODE ?? "",
  SYNC_TOKEN: process.env.SYNC_TOKEN ?? "",
};

export async function handleAwsEvent(event: FunctionUrlEvent, env: PortalEnv) {
  try {
    const headers = new Headers();
    for (const [name, value] of Object.entries(event.headers ?? {})) {
      if (value !== undefined) headers.set(name, value);
    }
    if (event.cookies?.length) headers.set("Cookie", event.cookies.join("; "));
    headers.set("x-portal-client-ip", event.requestContext.http.sourceIp);

    const host = headers.get("host");
    if (!host) throw new Error("AWS did not provide the request host.");
    const query = event.rawQueryString ? `?${event.rawQueryString}` : "";
    const url = `https://${host}${event.rawPath}${query}`;
    const method = event.requestContext.http.method.toUpperCase();
    const body = event.body
      ? event.isBase64Encoded
        ? Uint8Array.from(Buffer.from(event.body, "base64"))
        : new TextEncoder().encode(event.body)
      : undefined;
    const request = new Request(url, {
      method,
      headers,
      ...(body && method !== "GET" && method !== "HEAD" ? { body } : {}),
    });
    const response = await handleRequest(request, env);
    const responseHeaders: Record<string, string> = {};
    response.headers.forEach((value, name) => {
      if (name.toLowerCase() !== "set-cookie") responseHeaders[name] = value;
    });
    const cookies = response.headers.getSetCookie();
    const contentType = response.headers.get("content-type") ?? "";
    const binary = !/^(text\/|application\/(json|javascript|xml)|image\/svg\+xml)/i.test(contentType);
    const responseBody = Buffer.from(await response.arrayBuffer());
    return {
      statusCode: response.status,
      headers: responseHeaders,
      ...(cookies.length ? { cookies } : {}),
      isBase64Encoded: binary,
      body: binary ? responseBody.toString("base64") : responseBody.toString("utf8"),
    };
  } catch (error) {
    console.error("AWS teacher portal handler failed.", error);
    return {
      statusCode: 500,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
      },
      body: JSON.stringify({ error: "The portal could not complete the request. Try again later." }),
    };
  }
}

export async function handler(event: FunctionUrlEvent) {
  return handleAwsEvent(event, portalEnv);
}
