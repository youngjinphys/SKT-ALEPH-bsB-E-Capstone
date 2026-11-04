import type { NextConfig } from "next";
import { PHASE_PRODUCTION_BUILD } from "next/constants";

const securityHeaders = [
  { key: "X-Robots-Tag", value: "noindex, nofollow, noarchive, nosnippet, noimageindex" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
];

const config: NextConfig = {
  reactStrictMode: true,
  // JSON is intentionally loaded by the server filesystem registry.
  outputFileTracingIncludes: {
    '/capstone': ['./capstone/data/**/*.json'],
    '/capstone/references': ['./capstone/data/**/*.json', './docs/presentation/final-20min-scenario.md'],
    '/': ['./capstone/data/**/*.json'],
  },
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders },
      {source:"/capstone",headers:[{key:"Permissions-Policy",value:"camera=(), microphone=(self), geolocation=(), payment=()"}]}];
  },
};
// Capture the build server's clock once, not the request/server-start/browser time.
// Next replaces this exact env access in the compiled artifact. Reusing the
// artifact (including a cached deployment) therefore keeps its original time.
let productionBuildTime: string | undefined;
export default function nextConfig(phase: string): NextConfig {
  return {
    ...config,
    env: {
      NEXT_PUBLIC_ALEPH_BUILD_TIME: phase === PHASE_PRODUCTION_BUILD
        ? (productionBuildTime ??= new Date().toISOString())
        : "",
    },
  };
}
