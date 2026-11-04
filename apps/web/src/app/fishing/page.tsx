import type {Metadata} from "next";
import {FishingDemo} from "@/components/FishingDemo";
export const metadata:Metadata={title:"태양썬 가상 사이트 · 교육용 실습",description:"실제 개인정보와 금전 거래를 수집하지 않는 가상 법무법인 피싱 인식 실습"};
export default function FishingPage(){return <FishingDemo/>}
