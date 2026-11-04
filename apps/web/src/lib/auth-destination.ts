/** OAuth may return only to an explicitly supported local destination. */
export function authReturnPath(value: unknown): "/app" | "/dashboard" {
  return value === "/dashboard" ? "/dashboard" : "/app";
}

const failureCodes = new Set([
  "not_configured", "google_disabled", "provider_unavailable", "expired_flow",
  "cancelled", "invalid_callback", "exchange_failed", "access_denied", "auth_unavailable",
]);

export function authFailurePath(destination: unknown, reason: string): string {
  const path = authReturnPath(destination) === "/dashboard" ? "/dashboard" : "/";
  const code = failureCodes.has(reason) ? reason : "auth_unavailable";
  return `${path}?auth_error=${code}`;
}
