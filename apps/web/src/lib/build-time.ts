export type BuildTimeDisplay = {label: string; timeZone: string};

/** Only accept the canonical UTC instant produced by the build, never "now". */
export function buildTimeUtc(builtAt: string | undefined): BuildTimeDisplay | null {
  if (!builtAt || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(builtAt)) return null;
  const instant = new Date(builtAt);
  if (!Number.isFinite(instant.getTime()) || instant.toISOString() !== builtAt) return null;
  return {label: `${builtAt.slice(0, 10)} ${builtAt.slice(11, 19)} UTC`, timeZone: "UTC"};
}

/** Omitting timeZone uses the browser's zone, including DST at the build instant. */
export function buildTimeLocal(builtAt: string | undefined, timeZone?: string): BuildTimeDisplay | null {
  const fallback = buildTimeUtc(builtAt);
  if (!fallback || !builtAt) return fallback;
  try {
    const formatter = new Intl.DateTimeFormat("en-CA", {
      calendar: "gregory", numberingSystem: "latn", hourCycle: "h23",
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit", timeZoneName: "shortOffset",
      ...(timeZone ? {timeZone} : {}),
    });
    const parts = Object.fromEntries(formatter.formatToParts(new Date(builtAt)).map(part => [part.type, part.value]));
    const zone = formatter.resolvedOptions().timeZone;
    if (!zone || !/^\d{4}$/.test(parts.year) || ![parts.month, parts.day, parts.hour, parts.minute, parts.second].every(part => /^\d{2}$/.test(part)) || !/^GMT(?:[+-]\d{1,2}(?::\d{2})?)?$/.test(parts.timeZoneName)) return fallback;
    const offset = /^GMT(?:[+-]0(?::00)?)?$/.test(parts.timeZoneName) ? "UTC" : parts.timeZoneName;
    return {label: `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second} ${offset}`, timeZone: zone};
  } catch {
    // Unsupported Intl/timezone data must not hide a valid build or show Invalid Date.
    return fallback;
  }
}
