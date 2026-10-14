export type ApiErrorBody = { error?: { code?: string; message?: string } };

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(status: number, body: ApiErrorBody) {
    super(body.error?.message || "The request could not be completed.");
    this.status = status;
    this.code = body.error?.code;
  }
}

function csrfToken() {
  if (typeof document === "undefined") return "";
  const entry = document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith("skillmentor_csrf="));
  return entry ? decodeURIComponent(entry.slice("skillmentor_csrf=".length)) : "";
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers);
  // FormData bodies need the browser-generated multipart boundary.
  if (options.body && !(options.body instanceof FormData) && !headers.has("content-type")) headers.set("content-type", "application/json");
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const token = csrfToken();
    if (token) headers.set("x-csrf-token", token);
  }
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, { ...options, method, headers, credentials: "same-origin", cache: "no-store" });
  } catch {
    throw new Error("Can’t reach the service. Check your connection and try again.");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, body as ApiErrorBody);
  return body as T;
}

export function feedbackObject(feedback: string | null) {
  if (!feedback) return null;
  try { return JSON.parse(feedback) as { summary?: string; strengths?: string[]; improvements?: string[]; score?: number; automated?: boolean; reference_solution?: string }; }
  catch { return { summary: feedback }; }
}
