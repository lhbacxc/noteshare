interface Env {
  SHARES: KVNamespace;
  FILES: R2Bucket;
  ADMIN_TOKEN: string;
  R2_BUCKET_NAME?: string;
}

type ShareStatus = "active" | "revoked";

interface ShareRecord {
  token: string;
  bucket: string;
  object_key: string;
  status: ShareStatus;
  content_mode: "auto";
  created_at: string;
  expires_at: string;
}

interface CreateShareBody {
  bucket: string;
  object_key: string;
  expire_seconds: number;
}

interface RevokeShareBody {
  token: string;
}

const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      return await routeRequest(request, env);
    } catch (error) {
      console.error("Unexpected worker error", error);
      return jsonError("Worker 内部错误。", 500);
    }
  },
};

async function routeRequest(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const pathname = url.pathname;

  if (request.method === "POST" && pathname === "/api/shares") {
    return handleCreateShare(request, env);
  }
  if (request.method === "POST" && pathname === "/api/shares/revoke") {
    return handleRevokeShare(request, env);
  }
  if (request.method === "GET" && pathname.startsWith("/api/shares/")) {
    const token = pathname.slice("/api/shares/".length).trim();
    return handleGetShare(request, env, token);
  }
  if (request.method === "GET" && pathname.startsWith("/s/")) {
    const token = pathname.slice("/s/".length).trim();
    return handlePublicShare(env, token);
  }

  return notFound();
}

async function handleCreateShare(request: Request, env: Env): Promise<Response> {
  const unauthorized = authorizeRequest(request, env);
  if (unauthorized) {
    return unauthorized;
  }

  const body = await readJson<CreateShareBody>(request);
  if (!body) {
    return jsonError("请求体必须是 JSON。", 400);
  }

  const bucket = String(body.bucket ?? "").trim();
  const objectKey = String(body.object_key ?? "").trim();
  const expireSeconds = Number(body.expire_seconds);

  if (!bucket || !objectKey || !Number.isInteger(expireSeconds) || expireSeconds < 1) {
    return jsonError("缺少必要参数或参数不合法。", 400);
  }

  if (env.R2_BUCKET_NAME && bucket !== env.R2_BUCKET_NAME) {
    return jsonError(
      `当前 Worker 仅绑定 bucket：${env.R2_BUCKET_NAME}。`,
      400,
    );
  }

  const object = await env.FILES.head(objectKey);
  if (!object) {
    return jsonError("对象不存在。", 404);
  }

  const createdAt = new Date();
  const expiresAt = new Date(createdAt.getTime() + expireSeconds * 1000);
  const token = createToken();
  const record: ShareRecord = {
    token,
    bucket,
    object_key: objectKey,
    status: "active",
    content_mode: "auto",
    created_at: createdAt.toISOString(),
    expires_at: expiresAt.toISOString(),
  };

  await env.SHARES.put(getShareStorageKey(token), JSON.stringify(record));

  return jsonResponse({
    token,
    share_url: `${new URL(request.url).origin}/s/${token}`,
    status: record.status,
    created_at: record.created_at,
    expires_at: record.expires_at,
  });
}

async function handleRevokeShare(request: Request, env: Env): Promise<Response> {
  const unauthorized = authorizeRequest(request, env);
  if (unauthorized) {
    return unauthorized;
  }

  const body = await readJson<RevokeShareBody>(request);
  if (!body) {
    return jsonError("请求体必须是 JSON。", 400);
  }

  const token = String(body.token ?? "").trim();
  if (!token) {
    return jsonError("token 不能为空。", 400);
  }

  const record = await loadShareRecord(env, token);
  if (!record) {
    return jsonError("分享记录不存在。", 404);
  }

  record.status = "revoked";
  await env.SHARES.put(getShareStorageKey(token), JSON.stringify(record));

  return jsonResponse({
    token: record.token,
    status: record.status,
    created_at: record.created_at,
    expires_at: record.expires_at,
  });
}

async function handleGetShare(
  request: Request,
  env: Env,
  token: string,
): Promise<Response> {
  const unauthorized = authorizeRequest(request, env);
  if (unauthorized) {
    return unauthorized;
  }

  if (!token) {
    return jsonError("token 不能为空。", 400);
  }

  const record = await loadShareRecord(env, token);
  if (!record) {
    return jsonError("分享记录不存在。", 404);
  }

  return jsonResponse(record);
}

async function handlePublicShare(env: Env, token: string): Promise<Response> {
  if (!token) {
    return notFound();
  }

  const record = await loadShareRecord(env, token);
  if (!record) {
    return notFound();
  }
  if (record.status !== "active") {
    return notFound();
  }

  const expiresAt = Date.parse(record.expires_at);
  if (Number.isNaN(expiresAt) || Date.now() >= expiresAt) {
    return notFound();
  }

  const object = await env.FILES.get(record.object_key);
  if (!object) {
    return notFound();
  }

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("etag", object.httpEtag);

  const contentType =
    headers.get("content-type")?.trim() || guessContentType(record.object_key);
  headers.set("content-type", contentType);

  if (isPreviewType(contentType)) {
    headers.set("content-disposition", "inline");
  } else {
    headers.set(
      "content-disposition",
      buildAttachmentDisposition(record.object_key),
    );
  }

  return new Response(object.body, { headers });
}

function authorizeRequest(request: Request, env: Env): Response | null {
  const authHeader = request.headers.get("authorization") ?? "";
  const expected = `Bearer ${env.ADMIN_TOKEN}`;
  if (authHeader !== expected) {
    return jsonError("鉴权失败。", 401);
  }
  return null;
}

async function readJson<T>(request: Request): Promise<T | null> {
  try {
    const parsed = await request.json();
    if (parsed && typeof parsed === "object") {
      return parsed as T;
    }
    return null;
  } catch {
    return null;
  }
}

async function loadShareRecord(env: Env, token: string): Promise<ShareRecord | null> {
  const raw = await env.SHARES.get(getShareStorageKey(token));
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw) as Partial<ShareRecord>;
    if (
      typeof parsed.token !== "string" ||
      typeof parsed.bucket !== "string" ||
      typeof parsed.object_key !== "string" ||
      (parsed.status !== "active" && parsed.status !== "revoked") ||
      typeof parsed.created_at !== "string" ||
      typeof parsed.expires_at !== "string"
    ) {
      return null;
    }

    return {
      token: parsed.token,
      bucket: parsed.bucket,
      object_key: parsed.object_key,
      status: parsed.status,
      content_mode: "auto",
      created_at: parsed.created_at,
      expires_at: parsed.expires_at,
    };
  } catch {
    return null;
  }
}

function getShareStorageKey(token: string): string {
  return `share:${token}`;
}

function createToken(): string {
  return crypto.randomUUID().replaceAll("-", "");
}

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: JSON_HEADERS,
  });
}

function jsonError(message: string, status: number): Response {
  return jsonResponse({ error: message }, status);
}

function notFound(): Response {
  return new Response("Not Found", { status: 404 });
}

function buildAttachmentDisposition(objectKey: string): string {
  const filename = objectKey.split("/").pop() || "download";
  return `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`;
}

function guessContentType(objectKey: string): string {
  const lower = objectKey.toLowerCase();

  if (lower.endsWith(".txt") || lower.endsWith(".log") || lower.endsWith(".md")) {
    return "text/plain; charset=utf-8";
  }
  if (lower.endsWith(".json")) {
    return "application/json; charset=utf-8";
  }
  if (lower.endsWith(".html")) {
    return "text/html; charset=utf-8";
  }
  if (lower.endsWith(".css")) {
    return "text/css; charset=utf-8";
  }
  if (lower.endsWith(".js") || lower.endsWith(".mjs")) {
    return "application/javascript; charset=utf-8";
  }
  if (lower.endsWith(".xml")) {
    return "application/xml; charset=utf-8";
  }
  if (lower.endsWith(".svg")) {
    return "image/svg+xml";
  }
  if (lower.endsWith(".png")) {
    return "image/png";
  }
  if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) {
    return "image/jpeg";
  }
  if (lower.endsWith(".gif")) {
    return "image/gif";
  }
  if (lower.endsWith(".webp")) {
    return "image/webp";
  }
  if (lower.endsWith(".pdf")) {
    return "application/pdf";
  }

  return "application/octet-stream";
}

function isPreviewType(contentType: string): boolean {
  const normalized = contentType.toLowerCase();
  return (
    normalized.startsWith("text/") ||
    normalized.startsWith("image/") ||
    normalized.startsWith("application/json") ||
    normalized.startsWith("application/javascript") ||
    normalized.startsWith("application/xml") ||
    normalized.startsWith("application/pdf") ||
    normalized === "image/svg+xml"
  );
}
