import type { Metadata, Viewport } from "next";
import { SlideDeck } from "@/components/SlideDeck";
import { slides, sources, mainSlideCount } from "@/lib/deck.server";

export const viewport: Viewport = { width:"device-width", initialScale:1, viewportFit:"cover", themeColor:"#071421" };

export const metadata: Metadata = {
  title: "Protective DNS · 캡스톤 발표",
  description: "SKT ALEPH E조 Protective DNS. 관리형 네트워크의 정책 승인·DNS 집행·철회와 실제 검증을 다루는 표지 포함 14장, 20분 단일 발표",
};
export default function CapstonePage() {
  return <SlideDeck deck={slides} sources={sources} mainSlideCount={mainSlideCount} />;
}

