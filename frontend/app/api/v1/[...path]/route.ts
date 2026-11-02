import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
// AI planning and transcription can take several seconds; allow more than serverless defaults.
export const maxDuration = 60;

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  if (!path.length || path.some((segment) => !/^[A-Za-z0-9_-]+$/.test(segment))) {
    return NextResponse.json({ error: { code: "invalid_path", message: "The requested API path is invalid." } }, { status: 400, headers: { "cache-control": "no-store" } });
  }
  const configured = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  const base = /^https?:\/\//i.test(configured) ? configured : `http://${configured}`;
  const target = `${base}/api/v1/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  const headers = new Headers();
  for (const name of ["accept", "content-type", "cookie", "origin", "x-csrf-token"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  // Proves to the API that the request came through this web app (required when the API is public).
  const proxySecret = process.env.API_PROXY_SECRET;
  if (proxySecret) headers.set("x-proxy-secret", proxySecret);
  const controller = new AbortController();
  // Long enough for a free-tier API to wake from sleep (often 30-50 s), within maxDuration.
  const timeout = setTimeout(() => controller.abort(), 55_000);
  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer(),
      cache: "no-store",
      signal: controller.signal,
    });
    const responseHeaders = new Headers({
      "content-type": upstream.headers.get("content-type") || "application/json",
      "cache-control": "no-store, max-age=0",
    });
    const cookies = upstream.headers.getSetCookie?.() || [];
    for (const cookie of cookies) responseHeaders.append("set-cookie", cookie);
    return new NextResponse(await upstream.arrayBuffer(), { status: upstream.status, headers: responseHeaders });
  } catch (error) {
    const timedOut = error instanceof Error && error.name === "AbortError";
    return NextResponse.json({ error: { code: timedOut ? "upstream_timeout" : "upstream_unavailable", message: "The service is temporarily unavailable. Try again shortly." } }, { status: 503, headers: { "cache-control": "no-store" } });
  } finally {
    clearTimeout(timeout);
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
