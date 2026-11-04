import {NextRequest,NextResponse} from "next/server";
import {authReturnPath,authFailurePath} from "@/lib/auth-destination";
import {authConfig,authFetch,canonicalOrigin,clearFlowCookie,createChallenge,isValidVerifier,noStore,setSessionCookies,FLOW_COOKIE} from "@/lib/auth";

export const dynamic="force-dynamic";
export const runtime="nodejs";
export async function GET(request:NextRequest) {
  const origin=canonicalOrigin(),config=authConfig();
  const returnTo=authReturnPath(request.cookies.get("__Host-capstone_return")?.value);
  const failure=(code:string)=>{
    const response=NextResponse.redirect(new URL(authFailurePath(returnTo,code),origin||request.url),303);
    clearFlowCookie(response);response.cookies.set("__Host-capstone_return","",{httpOnly:true,secure:true,path:"/",maxAge:0});return noStore(response);
  };
  if(!origin||!config)return failure("not_configured");
  const verifier=request.cookies.get(FLOW_COOKIE)?.value;
  if(!isValidVerifier(verifier))return failure("expired_flow");
  if(request.nextUrl.searchParams.has("error"))return failure("cancelled");
  const code=request.nextUrl.searchParams.get("code");
  if(!code || code.length<12 || code.length>512 || !/^[A-Za-z0-9._~-]+$/.test(code))return failure("invalid_callback");
  try{
    const token=await authFetch(config,"token?grant_type=pkce",{method:"POST",body:{auth_code:code,code_verifier:verifier}});
    if(token.status!==200 || !token.data || typeof token.data!=="object")return failure("exchange_failed");
    const tokens=token.data as {access_token:string;refresh_token:string;expires_in?:number};
    const who=await authFetch(config,"user",{accessToken:tokens.access_token});
    if(who.status!==200 || !who.data || typeof who.data!=="object")return failure("access_denied");
    const user=who.data as {id?:string;email?:string;email_confirmed_at?:string;confirmed_at?:string};
    if(!user.id || !user.email || !(user.email_confirmed_at||user.confirmed_at))return failure("access_denied");
    const allowed=(process.env.CAPSTONE_ALLOWED_EMAILS||"").split(",").map(s=>s.trim().toLowerCase()).filter(Boolean);
    if(allowed.length && !allowed.includes(user.email.toLowerCase()))return failure("access_denied");
    const response=NextResponse.redirect(new URL(returnTo,origin),303);
    response.cookies.set("__Host-capstone_return","",{httpOnly:true,secure:true,path:"/",maxAge:0});
    clearFlowCookie(response);
    setSessionCookies(response,tokens);
    return noStore(response);
  }catch{return failure("auth_unavailable");}
}
