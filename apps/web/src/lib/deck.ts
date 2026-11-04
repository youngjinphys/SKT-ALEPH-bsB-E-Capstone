/** Shared, browser-safe presentation model. Keep authored JSON in deck.server.ts. */
export type Point = { title: string; body: string; probe?: string };
export type Reading = {
  title: string;
  columns: string[];
  rows: string[][];
  takeaway?: string;
  source: string;
  sourceLabel?: string;
};
export type IndependentSeries = {title:string;sourceKey:string;additionalSourceKeys?:string[]} & (
 | {context:string;unit?:never;max?:never;values?:never;periods?:never}
 | {context?:never;unit:string;max:number;values:number[];periods:string[]}
);
export type Visual =
  | { type: "independent-trends"; title:string; left:IndependentSeries;right:IndependentSeries;caveat:string }
  | { type: "comparison-bars"; title: string; sourceKey: string; unit: string; measurements: { label: string; value: number }[]; caveat: string }
  | { type: "cname-chain"; title: string; sourceKey: string; nodes: { label: string; value: string; state: string }[]; links: string[]; caveat: string }
  | { type: "planet" | "dns-policy" | "policy-lifecycle" | "protocol-boundary" | "governance" | "evidence" | "source-directory" }
  | { type: "topology"; mode: "lab" | "proposal" };
export type DeckSlide = {
  id: string;
  title: string;
  subtitle: string;
  credits?: string;
  chapter: string;
  kind: string;
  status: string;
  seconds: number;
  points: Point[];
  notes: string;
  sources: string[];
  presentation?: { compactTitle?: string; title?: string; subtitle?: string; cue?: string; reviewNote?: string; points?: Point[] };
  headline?: { focus: string; tone: string };
  reading?: Reading;
  visual?: Visual;
};
export type CitationSource = { label: string; url: string; note?: string };
export type SourceRegistry = Record<string, CitationSource>;

export function slideIndexFromHash(hash: string, deck: readonly Pick<DeckSlide,"id">[]): number {
  const named = /^#([a-z][a-z0-9-]{0,63})$/.exec(hash);
  if (named) {
    const found = deck.findIndex(slide => slide.id === named[1]);
    return found >= 0 ? found : 0;
  }
  const numeric = /^#(0|[1-9][0-9]*)$/.exec(hash);
  if (!numeric) return 0;
  const index = Number(numeric[1]);
  return Number.isSafeInteger(index) && index < deck.length ? index : 0;
}
export function clampSlideIndex(index: number, count: number): number {
  return Math.max(0, Math.min(Math.max(0, count-1), Number.isFinite(index) ? Math.trunc(index) : 0));
}
export function plannedSeconds(until: number, deck: readonly Pick<DeckSlide,"seconds">[]): number {
  return deck.slice(0, Math.max(0, until)).reduce((sum, slide) => sum + slide.seconds, 0);
}
