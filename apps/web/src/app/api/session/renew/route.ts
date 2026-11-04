import {NextRequest,NextResponse} from "next/server";
import {ACCESS_COOKIE,REFRESH_COOKIE,session,setSessionCookies,clearSessionCookies,noStore} from "@/lib/auth";
export const dynamic="force-dynamic";
export const runtime="nodejs";
export async function GET(request:NextRequest){
  const result=await session(request.cookies.get(ACCESS_COOKIE)?.value,request.cookies.get(REFRESH_COOKIE)?.value);
  const response=NextResponse.redirect(new URL(result.status===200?"/app":result.status===403?"/?auth_error=access_denied":result.status===503?"/?auth_error=auth_unavailable":"/?auth_error=expired_flow",request.url),303);
  if(result.status===200 && result.tokens)setSessionCookies(response,result.tokens);
  if(result.status!==200 && result.clear)clearSessionCookies(response);
  return noStore(response);
}
