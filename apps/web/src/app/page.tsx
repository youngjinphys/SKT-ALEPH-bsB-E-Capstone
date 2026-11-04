import type {Metadata} from "next";
import landingContent from "../../capstone/data/landing.json";
import {Landing} from "@/components/Landing";
import {slides,mainSlideCount} from "@/lib/deck.server";
import {plannedSeconds} from "@/lib/deck";

export const metadata:Metadata={title:"보안 연구실 · 피라냥"};
export default function HomePage(){
 return <Landing content={landingContent} stats={{
  main:mainSlideCount,
  appendix:slides.length-mainSlideCount,
  seconds:plannedSeconds(mainSlideCount,slides),
 }}/>;
}
