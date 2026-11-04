import type {Metadata,Viewport} from "next";
import "./globals.css";
import "./refactor.css";
import "./restored-design.css";
import "./restored-motion.css";
import "./audience.css";
import "./glass-theme.css";
import "./desktop-presentation.css";
import "./mobile-presentation.css";
import "./unified-dashboard.css";
import "./build-timestamp.css";
import {BuildTimestamp} from "@/components/BuildTimestamp";
import {headers} from "next/headers";
export const metadata:Metadata={
  title:{default:"ALEPH · 보안 연구실",template:"%s | ALEPH"},
  description:"SKT ALEPH E조 Protective DNS. 검증된 실험, 적용 경계, 운영 책임을 구분하는 보안 프로젝트.",
  robots:{index:false,follow:false,noarchive:true,nosnippet:true,noimageindex:true},
  icons:{icon:"/assets/guardian/guardian-smile-open.webp"},
};
export const viewport:Viewport={themeColor:"#071421",width:"device-width",initialScale:1};
export default async function RootLayout({children}:{children:React.ReactNode}){
 // Force request-time HTML so Next.js can attach the per-request CSP nonce to hydration scripts.
 // Static prerendering with a random nonce would block the client-side presentation.
 const nonce=(await headers()).get("x-nonce");
 return <html lang="ko" data-csp={nonce?"nonce":"standard"}><body>{children}<BuildTimestamp/></body></html>;
}
