"use client";
import {useEffect, useState} from "react";
import {buildTimeLocal, buildTimeUtc} from "@/lib/build-time";

/** Build metadata is compiled into both server and client output by next.config. */
export function BuildTimestamp() {
  const builtAt = process.env.NEXT_PUBLIC_ALEPH_BUILD_TIME;
  // Server markup and the first client render must agree. Localize only after
  // hydration; the original UTC datetime remains the same artifact instant.
  const [display, setDisplay] = useState(() => buildTimeUtc(builtAt));
  useEffect(() => { setDisplay(buildTimeLocal(builtAt)); }, [builtAt]);
  // Development/invalid metadata never substitute a server or viewer clock.
  if (!display) return null;
  return <small className="build-timestamp" title={`웹 빌드 시작 시각 · 표시 시간대: ${display.timeZone}`}>
    Updated at <time dateTime={builtAt} aria-label={`웹 빌드 시각: ${display.label}`}>{display.label}</time>
  </small>;
}
