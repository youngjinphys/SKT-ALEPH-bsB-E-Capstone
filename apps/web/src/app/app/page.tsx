import {cookies} from "next/headers";
import {redirect} from "next/navigation";
import {Workspace} from "@/components/Workspace";
import {ACCESS_COOKIE,REFRESH_COOKIE,session} from "@/lib/auth";

export const dynamic="force-dynamic";
export const metadata={title:"내 보안 연구실"};
export default async function ProtectedWorkspacePage(){
 const jar=await cookies();
 const access=jar.get(ACCESS_COOKIE)?.value;
 const refresh=jar.get(REFRESH_COOKIE)?.value;
 if(!access&&!refresh)redirect("/");
 const result=await session(access,undefined);
 if(result.status===401 && refresh)redirect("/api/session/renew");
 if(result.status===401)redirect("/");
 if(result.status===503)return <main className="error-page"><h1>인증 서버 연결을 확인할 수 없습니다.</h1><p>접근 허가를 추정하지 않고 중단했습니다.</p><a href="/">연구실 홈으로</a></main>;
 if(result.status===403)return <main className="error-page"><h1>연구실 접근 권한이 없습니다.</h1><p>Google 인증과 연구실 입장 승인은 다른 절차입니다.</p><a href="/">연구실 홈으로</a></main>;
 if(result.status===200)return <Workspace email={result.email}/>;
 redirect("/");
}
