import { NextRequest, NextResponse } from "next/server";

/** Request-local nonce: Next.js hydration can run without weakening script-src. */
export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  // WebKit upgrades even loopback subresources under this directive. The test
  // server is HTTP-only; production keeps the directive. Next normalizes other
  // 127/8 addresses to localhost, so verify the original Host as well.
  const localHttpTest = process.env.PLAYWRIGHT_LOCAL_HTTP === "1"
    && request.nextUrl.protocol === "http:"
    && ["localhost", "127.0.0.1", "[::1]"].includes(request.nextUrl.hostname)
    && /^(localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?$/i.test(request.headers.get("host") || "");
  const isDev = process.env.NODE_ENV === "development";
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "form-action 'none'",
    "base-uri 'none'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    ...(!localHttpTest ? ["upgrade-insecure-requests"] : []),
  ].join("; ");
  const forwarded = new Headers(request.headers);
  forwarded.set("x-nonce", nonce);
  forwarded.set("Content-Security-Policy", csp);
  const response = NextResponse.next({request:{headers:forwarded}});
  response.headers.set("Content-Security-Policy", csp);
  return response;
}
export const config = {
  matcher: ["/((?!api/|_next/|assets/|capstone/assets/|favicon.ico|robots.txt).*)"],
};
