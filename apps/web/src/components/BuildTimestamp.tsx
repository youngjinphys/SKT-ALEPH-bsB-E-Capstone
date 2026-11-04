/** Build metadata is compiled into both server and client output by next.config. */
export function BuildTimestamp() {
  const builtAt = process.env.NEXT_PUBLIC_ALEPH_BUILD_TIME;
  // Development has no production build. Never substitute the viewer's clock.
  if (!builtAt) return null;
  const label = `${builtAt.slice(0, 10)} ${builtAt.slice(11, 19)} UTC`;
  return <small className="build-timestamp" title="웹 빌드 시작 시각 · 빌드 서버 기준">
    Updated at <time dateTime={builtAt}>{label}</time>
  </small>;
}
